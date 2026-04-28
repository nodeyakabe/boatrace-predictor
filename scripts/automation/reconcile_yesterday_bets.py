"""
前日予想と結果の突合せモジュール

Aブロック タスク6として実行。
標準バックテスト（standard_backtest_unique.py）と同一ロジックで
前日の購入対象レースを特定し、実際の結果と照合して的中/収支をDiscord通知する。

ロジックの根拠:
- get_race_ids_for_condition() でバックテストと同じ条件フィルタを使用
- 優先度順の重複除外もバックテストと同一
- analyze_assigned_races() の的中判定SQLをPython化して各レース詳細を取得
- 収支は trifecta_odds 使用（payoutsはAブロック時点で未収集）
"""

import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.backtest_helpers import get_race_ids_for_condition

VENUE_MAP = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
    '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
    '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
    '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}


def _assign_races(cursor, target_date: str) -> Dict[str, List[int]]:
    """バックテストと同一の優先度順重複除外でレースを条件に割り当て"""
    all_race_ids = set()
    race_to_condition = {}

    sorted_conditions = sorted(
        STANDARD_BET_CONDITIONS,
        key=lambda x: (x.get('priority', 999), STANDARD_BET_CONDITIONS.index(x))
    )

    # backtest_helpersのSQLは race_date < end_date なので翌日を渡す
    from datetime import datetime, timedelta
    end_date = (datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

    for cond in sorted_conditions:
        race_ids = get_race_ids_for_condition(cursor, cond, target_date, end_date, enable_wind_filter=True)
        for race_id in race_ids:
            if race_id not in all_race_ids:
                all_race_ids.add(race_id)
                race_to_condition[race_id] = cond['id']

    condition_to_races: Dict[str, List[int]] = {}
    for race_id, cond_id in race_to_condition.items():
        condition_to_races.setdefault(cond_id, []).append(race_id)

    return condition_to_races


def _get_race_detail(cursor, race_id: int, cond: Dict) -> Optional[Dict]:
    """
    1レースの買い目・実結果・収支を計算して返す。
    パターンH / 1点買い対応。

    Returns:
        dict with is_candidate=False (購入対象) or is_candidate=True (候補)
        or None (予測不足等でスキップ)
    """
    use_pattern_h = cond.get('use_pattern_h', False)
    odds_min = cond['odds_min']
    odds_max = cond['odds_max']
    exclude_p5 = cond.get('pattern_h_exclude_p5', False)

    # 会場・レース番号
    cursor.execute(
        "SELECT venue_code, race_number FROM races WHERE id = ?", (race_id,)
    )
    row = cursor.fetchone()
    if not row:
        return None
    venue_name = VENUE_MAP.get(str(row[0]).zfill(2), f'会場{row[0]}')
    race_number = row[1]

    # before予測（1-5位）
    cursor.execute(
        "SELECT pit_number, rank_prediction FROM race_predictions "
        "WHERE race_id = ? AND prediction_type = 'before' AND rank_prediction <= 5 "
        "ORDER BY rank_prediction",
        (race_id,)
    )
    pred_rows = {r[1]: r[0] for r in cursor.fetchall()}
    if len(pred_rows) < 3:
        return None

    p1 = pred_rows.get(1)
    p2 = pred_rows.get(2)
    p3 = pred_rows.get(3)
    p4 = pred_rows.get(4)
    p5 = pred_rows.get(5)

    def get_odds(combo: str) -> float:
        cursor.execute(
            "SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?",
            (race_id, combo)
        )
        r = cursor.fetchone()
        return r[0] if r and r[0] else 0.0

    # 実際の着順
    cursor.execute(
        "SELECT pit_number, rank FROM results WHERE race_id = ? AND is_invalid = 0",
        (race_id,)
    )
    rank_map = {}
    for pit, rank in cursor.fetchall():
        try:
            rank_map[int(rank)] = pit
        except (ValueError, TypeError):
            pass

    has_result = 1 in rank_map and 2 in rank_map and 3 in rank_map
    actual_combo = f"{rank_map[1]}-{rank_map[2]}-{rank_map[3]}" if has_result else None

    if use_pattern_h:
        combo_123 = f"{p1}-{p2}-{p3}"
        odds_123 = get_odds(combo_123)
        bet_123 = 200 if (odds_min <= odds_123 < odds_max) else 0
        payout_123 = odds_123 * 200 if (bet_123 > 0 and actual_combo == combo_123) else 0

        combo_124 = f"{p1}-{p2}-{p4}" if p4 else None
        odds_124 = get_odds(combo_124) if combo_124 else 0
        bet_124 = 100 if (combo_124 and odds_min <= odds_124 < odds_max) else 0
        payout_124 = odds_124 * 100 if (bet_124 > 0 and actual_combo == combo_124) else 0

        combo_125 = f"{p1}-{p2}-{p5}" if (p5 and not exclude_p5) else None
        odds_125 = get_odds(combo_125) if combo_125 else 0
        bet_125 = 100 if (combo_125 and odds_min <= odds_125 < odds_max) else 0
        payout_125 = odds_125 * 100 if (bet_125 > 0 and actual_combo == combo_125) else 0

        total_bet = bet_123 + bet_124 + bet_125
        is_candidate = (total_bet == 0)  # 全買い目がオッズ範囲外 → 候補

        if is_candidate:
            # 候補: 全買い目のうち的中したものを確認
            hit_combo = None
            if has_result:
                for combo in filter(None, [combo_123, combo_124, combo_125]):
                    if actual_combo == combo:
                        hit_combo = combo
                        break
            is_hit = hit_combo is not None
            # 表示用: 的中買い目があればそれを先頭に、なければ combo_123
            bets_str = hit_combo if hit_combo else combo_123
            ref_odds = get_odds(bets_str)
            total_payout = 0
        else:
            total_payout = int(payout_123 + payout_124 + payout_125)
            is_hit = total_payout > 0
            bets_str = ', '.join(filter(None, [
                combo_123 if bet_123 > 0 else None,
                combo_124 if bet_124 > 0 else None,
                combo_125 if bet_125 > 0 else None,
            ]))
            ref_odds = None

    else:
        combo_123 = f"{p1}-{p2}-{p3}"
        odds_123 = get_odds(combo_123)
        is_candidate = not (odds_min <= odds_123 < odds_max)

        bets_str = combo_123
        ref_odds = odds_123 if is_candidate else None

        if is_candidate:
            total_bet = 0
            total_payout = 0
            is_hit = has_result and actual_combo == combo_123
        else:
            total_bet = 100
            is_hit = has_result and actual_combo == combo_123
            total_payout = int(odds_123 * 100) if is_hit else 0

    if is_candidate:
        odds_reason = f'{ref_odds:.1f}倍' if ref_odds else 'オッズ不明'
        status = '的中(候補)' if is_hit else ('結果未取得(候補)' if not has_result else '不的中(候補)')
        hit_str = '[候補-OK]' if is_hit else ('[候補-?]' if not has_result else '[候補-NG]')
    else:
        status = '的中' if is_hit else ('結果未取得' if not has_result else '不的中')
        hit_str = '[OK]' if is_hit else ('[?]' if not has_result else '[NG]')
        odds_reason = None

    print(f"  {hit_str} {venue_name}{race_number}R [{cond['id']}] 買={bets_str} 実={actual_combo or 'N/A'} +{total_payout}円{' ('+odds_reason+')' if odds_reason else ''}")

    return {
        'venue': venue_name,
        'race_num': race_number,
        'condition_id': cond['id'],
        'combinations': bets_str,
        'bet_amount': total_bet,
        'status': status,
        'return_amount': total_payout,
        'actual': actual_combo or 'N/A',
        'is_candidate': is_candidate,
        'odds_reason': odds_reason,
    }


def reconcile_yesterday_bets(db_path: str, target_date: str = None) -> Dict:
    """
    前日予想と結果を突合せ。

    Args:
        db_path: DBパス
        target_date: 対象日付（YYYY-MM-DD）。Noneなら昨日。

    Returns:
        dict: {
            'date', 'target_count', 'hit_count', 'total_bet',
            'total_return', 'profit', 'details', 'no_result_count'
        }
    """
    if target_date is None:
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    details = []
    total_bet = 0
    total_return = 0
    no_result_count = 0

    try:
        cursor = conn.cursor()
        cond_id_map = {c['id']: c for c in STANDARD_BET_CONDITIONS}

        print(f"  突合せ対象日: {target_date}")
        condition_to_races = _assign_races(cursor, target_date)

        total_assigned = sum(len(v) for v in condition_to_races.values())
        print(f"  条件割り当て: {total_assigned}レース（{len(condition_to_races)}条件）")

        for cond_id, race_ids in condition_to_races.items():
            cond = cond_id_map.get(cond_id)
            if not cond:
                continue
            for race_id in sorted(race_ids):
                detail = _get_race_detail(cursor, race_id, cond)
                if detail is None:
                    continue
                details.append(detail)
                total_bet += detail['bet_amount']
                total_return += detail['return_amount']
                if detail['status'] == '結果未取得':
                    no_result_count += 1

    finally:
        conn.close()

    purchase_details = [d for d in details if not d['is_candidate']]
    candidate_details = [d for d in details if d['is_candidate']]

    hit_count = sum(1 for d in purchase_details if d['status'] == '的中')
    candidate_hit_count = sum(1 for d in candidate_details if d['status'] == '的中(候補)')

    return {
        'date': target_date,
        'target_count': len(purchase_details),
        'hit_count': hit_count,
        'total_bet': total_bet,
        'total_return': total_return,
        'profit': total_return - total_bet,
        'details': purchase_details,
        'no_result_count': no_result_count,
        'candidate_count': len(candidate_details),
        'candidate_hit_count': candidate_hit_count,
        'candidate_details': candidate_details,
    }


def format_reconcile_message(result: Dict) -> str:
    """突合せ結果をDiscord通知用メッセージにフォーマット"""
    date = result['date']
    target_count = result['target_count']
    hit_count = result['hit_count']
    profit = result['profit']
    candidate_count = result.get('candidate_count', 0)
    candidate_hit_count = result.get('candidate_hit_count', 0)
    candidate_details = result.get('candidate_details', [])
    # 日付を MM/DD に短縮
    try:
        short_date = datetime.strptime(date, '%Y-%m-%d').strftime('%m/%d')
    except Exception:
        short_date = date

    if target_count == 0 and not candidate_details:
        return f"📊 **{short_date}** 購入なし"

    profit_sign = '+' if profit >= 0 else ''

    lines = []
    if target_count > 0:
        lines.append(f"📊 **{short_date}** {hit_count}/{target_count}的中  {profit_sign}{profit:,}円")
    else:
        lines.append(f"📊 **{short_date}** 購入なし")

    # 的中レースのみ表示
    hits = [d for d in result['details'] if d['status'] == '的中']
    if hits:
        lines.append("")
        for d in hits:
            lines.append(f"✅ {d['venue']} {d['race_num']}R  `{d['combinations']}`  +{d['return_amount']:,}円")

    # 候補: 的中のみ表示
    if candidate_details:
        lines.append("")
        lines.append(f"候補 {candidate_hit_count}/{candidate_count}的中")
        for d in candidate_details:
            if d['status'] == '的中(候補)':
                odds_str = f"  {d['odds_reason']}" if d.get('odds_reason') else ''
                lines.append(f"  ✅ {d['venue']} {d['race_num']}R  `{d['combinations']}`{odds_str}")

    return "\n".join(lines)
