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

from config.bet_conditions import STANDARD_BET_CONDITIONS, get_active_conditions
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

    active_conds = get_active_conditions()  # active=False（凍結監視中）の条件を除外
    sorted_conditions = sorted(
        active_conds,
        key=lambda x: (x.get('priority', 999), active_conds.index(x))
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
    パターンH / p142 / p143 / p132 / p124 / 1点買い対応。

    Returns:
        dict with is_candidate=False (購入対象) or is_candidate=True (候補)
        or None (予測不足等でスキップ)
    """
    use_pattern_h = cond.get('use_pattern_h', False)
    use_pattern_p142 = cond.get('use_pattern_p142', False)
    use_pattern_p143 = cond.get('use_pattern_p143', False)
    use_pattern_p132 = cond.get('use_pattern_p132', False)
    use_pattern_p124 = cond.get('use_pattern_p124', False)
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

    elif use_pattern_p142:
        # p1-p4-p2 パターン
        if not p4:
            return None
        combo = f"{p1}-{p4}-{p2}"
        odds_val = get_odds(combo)
        is_candidate = not (odds_min <= odds_val < odds_max)
        bets_str = combo
        ref_odds = odds_val if is_candidate else None
        if is_candidate:
            total_bet = 0
            total_payout = 0
            is_hit = has_result and actual_combo == combo
        else:
            total_bet = 100
            is_hit = has_result and actual_combo == combo
            total_payout = int(odds_val * 100) if is_hit else 0

    elif use_pattern_p143:
        # p1-p4-p3 パターン
        if not p4:
            return None
        combo = f"{p1}-{p4}-{p3}"
        odds_val = get_odds(combo)
        is_candidate = not (odds_min <= odds_val < odds_max)
        bets_str = combo
        ref_odds = odds_val if is_candidate else None
        if is_candidate:
            total_bet = 0
            total_payout = 0
            is_hit = has_result and actual_combo == combo
        else:
            total_bet = 100
            is_hit = has_result and actual_combo == combo
            total_payout = int(odds_val * 100) if is_hit else 0

    elif use_pattern_p132:
        # p1-p3-p2 パターン
        combo = f"{p1}-{p3}-{p2}"
        odds_val = get_odds(combo)
        is_candidate = not (odds_min <= odds_val < odds_max)
        bets_str = combo
        ref_odds = odds_val if is_candidate else None
        if is_candidate:
            total_bet = 0
            total_payout = 0
            is_hit = has_result and actual_combo == combo
        else:
            total_bet = 100
            is_hit = has_result and actual_combo == combo
            total_payout = int(odds_val * 100) if is_hit else 0

    elif use_pattern_p124:
        # p1-p2-p4 パターン
        if not p4:
            return None
        combo = f"{p1}-{p2}-{p4}"
        odds_val = get_odds(combo)
        is_candidate = not (odds_min <= odds_val < odds_max)
        bets_str = combo
        ref_odds = odds_val if is_candidate else None
        if is_candidate:
            total_bet = 0
            total_payout = 0
            is_hit = has_result and actual_combo == combo
        else:
            total_bet = 100
            is_hit = has_result and actual_combo == combo
            total_payout = int(odds_val * 100) if is_hit else 0

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


def _bet_notifications_table_exists(cursor) -> bool:
    """bet_notifications テーブルが存在するか確認"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='bet_notifications'"
    )
    return cursor.fetchone() is not None


def _get_notified_bets(cursor, target_date: str) -> List[Dict]:
    """
    bet_notifications テーブルから通知済みレースを取得。
    notification_type='confirmed' のみ（購入通知）を返す。
    """
    cursor.execute("""
        SELECT bn.race_id, bn.combinations, bn.odds_at_notification,
               bn.bet_amount, bn.condition_id, bn.notified_at, bn.bet_amounts
        FROM bet_notifications bn
        JOIN races r ON bn.race_id = r.id
        WHERE r.race_date = ? AND bn.notification_type = 'confirmed'
        ORDER BY bn.notified_at
    """, (target_date,))
    return [dict(zip(
        ['race_id', 'combinations', 'odds_at_notification', 'bet_amount', 'condition_id', 'notified_at', 'bet_amounts'],
        row
    )) for row in cursor.fetchall()]


def _get_dismissed_bets(cursor, target_date: str) -> List[Dict]:
    """
    bet_notifications テーブルから見送りレースを取得。
    notification_type='dismissed'（最終確認でオッズ範囲外になったもの）を返す。
    """
    cursor.execute("""
        SELECT bn.race_id, bn.combinations, bn.odds_at_notification,
               bn.condition_id, bn.notified_at, bn.bet_amounts
        FROM bet_notifications bn
        JOIN races r ON bn.race_id = r.id
        WHERE r.race_date = ? AND bn.notification_type = 'dismissed'
        ORDER BY bn.notified_at
    """, (target_date,))
    return [dict(zip(
        ['race_id', 'combinations', 'odds_at_notification', 'condition_id', 'notified_at', 'bet_amounts'],
        row
    )) for row in cursor.fetchall()]


def _get_dismissed_detail(cursor, notif: Dict) -> Optional[Dict]:
    """見送りレースの詳細・実結果・的中可否を返す"""
    race_id = notif['race_id']
    cursor.execute("SELECT venue_code, race_number FROM races WHERE id = ?", (race_id,))
    row = cursor.fetchone()
    if not row:
        return None
    venue_name = VENUE_MAP.get(str(row[0]).zfill(2), f'会場{row[0]}')
    race_number = row[1]
    stored_combos = [c.strip() for c in notif['combinations'].split(',') if c.strip()]
    combos_str = ', '.join(stored_combos)
    odds = notif.get('odds_at_notification')
    cond_id = notif.get('condition_id') or '?'

    # 組合せごとの投資額を復元（パターンH: "200,100,100" 等）
    raw_amounts = notif.get('bet_amounts') or ''
    amount_parts = [int(a.strip()) for a in raw_amounts.split(',') if a.strip().isdigit()]
    if len(amount_parts) == len(stored_combos) and stored_combos:
        combo_amount_map = dict(zip(stored_combos, amount_parts))
    else:
        combo_amount_map = {c: 100 for c in stored_combos}

    # 実際の着順を取得
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
    is_hit = has_result and actual_combo in stored_combos

    # 的中時は確定払戻オッズを取得（組合せごとの投資額を使用）
    payout = 0
    if is_hit:
        cursor.execute(
            "SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?",
            (race_id, actual_combo)
        )
        r = cursor.fetchone()
        if r and r[0]:
            per_bet = combo_amount_map.get(actual_combo, 100)
            payout = int(r[0] * per_bet)

    odds_str = f"{odds:.1f}倍" if odds else ''
    status = '的中' if is_hit else ('結果未取得' if not has_result else '不的中')
    hit_str = '[HIT]' if is_hit else ('[?]' if not has_result else '[NG]')
    payout_str = f" +{payout:,}円" if is_hit else ""
    print(f"  {hit_str} [見送] {venue_name}{race_number}R [{cond_id}] "
          f"買={combos_str} 実={actual_combo or 'N/A'} {odds_str}{payout_str}")
    return {
        'venue': venue_name,
        'race_num': race_number,
        'condition_id': cond_id,
        'combinations': combos_str,
        'final_odds': odds,
        'actual': actual_combo or 'N/A',
        'is_hit': is_hit,
        'payout': payout,
        'status': status,
    }


def _get_race_detail_from_notification(cursor, notif: Dict) -> Optional[Dict]:
    """
    bet_notifications の1レースについて実結果と突合せ。

    - 通知時に記録した買い目 (combinations) vs 実際の着順
    - 払戻はtrifecta_oddsの確定オッズを使用
    """
    race_id = notif['race_id']
    stored_combos = [c.strip() for c in notif['combinations'].split(',') if c.strip()]
    bet_amount = notif['bet_amount'] or 100
    condition_id = notif['condition_id'] or '?'

    # 組合せごとの投資額を復元（bet_amounts="200,100,100" 等）
    raw_amounts = notif.get('bet_amounts') or ''
    amount_parts = [int(a.strip()) for a in raw_amounts.split(',') if a.strip().isdigit()]
    if len(amount_parts) == len(stored_combos) and stored_combos:
        combo_amount_map = dict(zip(stored_combos, amount_parts))
    else:
        # 旧レコード（bet_amounts未記録）または組数不一致: 均等割りで近似
        per_each = (bet_amount // len(stored_combos)) if stored_combos else 100
        combo_amount_map = {c: per_each for c in stored_combos}

    cursor.execute("SELECT venue_code, race_number FROM races WHERE id = ?", (race_id,))
    row = cursor.fetchone()
    if not row:
        return None
    venue_name = VENUE_MAP.get(str(row[0]).zfill(2), f'会場{row[0]}')
    race_number = row[1]

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

    is_hit = has_result and actual_combo in stored_combos
    total_payout = 0
    if is_hit:
        for combo in stored_combos:
            if actual_combo == combo:
                cursor.execute(
                    "SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?",
                    (race_id, combo)
                )
                r = cursor.fetchone()
                if r and r[0]:
                    per_bet = combo_amount_map.get(combo, 100)
                    total_payout = int(r[0] * per_bet)
                break

    if is_hit:
        status = '的中'
        hit_str = '[OK]'
    elif not has_result:
        status = '結果未取得'
        hit_str = '[?]'
    else:
        status = '不的中'
        hit_str = '[NG]'

    combos_str = ', '.join(stored_combos)
    odds_str = f"{notif['odds_at_notification']:.1f}倍" if notif.get('odds_at_notification') else ''
    print(f"  {hit_str} {venue_name}{race_number}R [{condition_id}] "
          f"買={combos_str} 実={actual_combo or 'N/A'} {odds_str} +{total_payout}円")

    return {
        'venue': venue_name,
        'race_num': race_number,
        'condition_id': condition_id,
        'combinations': combos_str,
        'bet_amount': bet_amount,
        'status': status,
        'return_amount': total_payout,
        'actual': actual_combo or 'N/A',
        'is_candidate': False,
        'odds_reason': None,
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
    dismissed_details = []
    total_bet = 0
    total_return = 0
    no_result_count = 0

    try:
        cursor = conn.cursor()

        print(f"  突合せ対象日: {target_date}")

        if _bet_notifications_table_exists(cursor):
            # bet_amounts カラムがない古いテーブルへの移行対応
            try:
                cursor.execute("ALTER TABLE bet_notifications ADD COLUMN bet_amounts TEXT")
                conn.commit()
            except Exception:
                pass  # カラム既存の場合は無視
            # 新方式: 通知時に記録した buy notification をベースに突合せ
            notified = _get_notified_bets(cursor, target_date)
            print(f"  [新方式] bet_notifications 使用: {len(notified)}件の通知記録")
            for notif in notified:
                detail = _get_race_detail_from_notification(cursor, notif)
                if detail is None:
                    continue
                details.append(detail)
                total_bet += detail['bet_amount']
                total_return += detail['return_amount']
                if detail['status'] == '結果未取得':
                    no_result_count += 1
            # 見送りレース（最終確認でオッズ範囲外になったもの）
            dismissed = _get_dismissed_bets(cursor, target_date)
            if dismissed:
                print(f"  [見送り] {len(dismissed)}件の見送り記録")
                for notif in dismissed:
                    d = _get_dismissed_detail(cursor, notif)
                    if d:
                        dismissed_details.append(d)
        else:
            # 旧方式（後方互換）: バックテストと同一ロジックで再導出
            print(f"  [旧方式] bet_notifications テーブルなし → バックテストロジックで再導出")
            cond_id_map = {c['id']: c for c in get_active_conditions()}  # active=False除外
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

        # shadow 5点突合せ（bet_notifications の有無に関わらず実行）
        shadow_details = []
        try:
            shadow_details = _reconcile_shadow_bets(cursor, target_date)
            if shadow_details:
                print(f"  [shadow] {len(shadow_details)}件突合せ完了")
        except Exception as _se:
            print(f"  [WARN] shadow突合せ失敗: {_se}")

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
        'dismissed_details': dismissed_details,
        'shadow_details': shadow_details,
    }


def _reconcile_shadow_bets(cursor, target_date: str) -> list:
    """
    shadow_bets の突合せ（対象日分）。
    actual_result / hit_combination / odds_if_hit / reconciled_at を更新し、
    サマリーリストを返す。
    """
    # テーブルが存在しなければスキップ
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shadow_bets'")
    if not cursor.fetchone():
        return []

    cursor.execute("""
        SELECT sb.id, sb.race_id, sb.combinations,
               r.venue_code, r.race_number
        FROM shadow_bets sb
        JOIN races r ON sb.race_id = r.id
        WHERE r.race_date = ? AND sb.reconciled_at IS NULL
        ORDER BY r.race_number
    """, (target_date,))
    rows = cursor.fetchall()
    if not rows:
        return []

    results = []
    now_str = datetime.now().isoformat()

    for row in rows:
        sb_id = row[0]
        race_id = row[1]
        combos_str = row[2]
        venue_name = VENUE_MAP.get(str(row[3]).zfill(2), f'会場{row[3]}')
        race_number = row[4]
        combos = [c.strip() for c in combos_str.split(',') if c.strip()]

        # 実着順を取得
        cursor.execute("""
            SELECT pit_number, rank FROM results
            WHERE race_id = ? AND is_invalid = 0
            ORDER BY rank
        """, (race_id,))
        rank_map = {}
        for pit, rank in cursor.fetchall():
            try:
                rank_map[int(rank)] = int(pit)
            except (ValueError, TypeError):
                pass

        has_result = 1 in rank_map and 2 in rank_map and 3 in rank_map
        actual_combo = f"{rank_map[1]}-{rank_map[2]}-{rank_map[3]}" if has_result else None
        hit_combo = actual_combo if (has_result and actual_combo in combos) else None

        # 的中時のオッズを取得
        odds_if_hit = None
        if hit_combo:
            cursor.execute(
                "SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?",
                (race_id, hit_combo)
            )
            r = cursor.fetchone()
            if r and r[0]:
                odds_if_hit = float(r[0])

        # 結果未取得の場合は reconciled_at を立てずスキップ（翌日以降に再突合せ可能）
        if not has_result:
            results.append({
                'venue': venue_name, 'race_num': race_number,
                'combinations': combos_str, 'actual': None,
                'hit_combination': None, 'odds_if_hit': None, 'has_result': False,
            })
            continue

        # shadow_bets を更新
        cursor.execute("""
            UPDATE shadow_bets
            SET actual_result = ?, hit_combination = ?, odds_if_hit = ?, reconciled_at = ?
            WHERE id = ?
        """, (actual_combo, hit_combo, odds_if_hit, now_str, sb_id))

        results.append({
            'venue': venue_name,
            'race_num': race_number,
            'combinations': combos_str,
            'actual': actual_combo or 'N/A',
            'hit_combination': hit_combo,
            'odds_if_hit': odds_if_hit,
            'has_result': True,
        })

    cursor.connection.commit()
    return results


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

    dismissed_details = result.get('dismissed_details', [])

    if target_count == 0 and not candidate_details and not dismissed_details:
        return f"📊 **{short_date}** 購入なし"

    profit_sign = '+' if profit >= 0 else ''

    lines = []
    if target_count > 0:
        lines.append(f"📊 **{short_date}** {hit_count}/{target_count}的中  {profit_sign}{profit:,}円")
    else:
        lines.append(f"📊 **{short_date}** 購入なし")

    # 的中レース
    hits = [d for d in result['details'] if d['status'] == '的中']
    if hits:
        lines.append("")
        for d in hits:
            lines.append(f"✅ {d['venue']} {d['race_num']}R  `{d['combinations']}`  +{d['return_amount']:,}円")

    # 不的中レース（買い目 vs 実着順を表示）
    misses = [d for d in result['details'] if d['status'] == '不的中']
    if misses:
        lines.append("")
        for d in misses:
            lines.append(f"❌ {d['venue']} {d['race_num']}R  買=`{d['combinations']}`  実=`{d['actual']}`")

    # 結果未取得レース
    no_results = [d for d in result['details'] if d['status'] == '結果未取得']
    if no_results:
        lines.append("")
        for d in no_results:
            lines.append(f"⏳ {d['venue']} {d['race_num']}R  `{d['combinations']}`  結果未取得")

    # 見送りレース（最終オッズ確認で範囲外になったもの）
    if dismissed_details:
        dismissed_hit = [d for d in dismissed_details if d.get('is_hit')]
        header = f"⚪ 見送り {len(dismissed_details)}件（最終確認でオッズ範囲外）"
        if dismissed_hit:
            header += f"  ※{len(dismissed_hit)}件的中"
        lines.append("")
        lines.append(header)
        for d in dismissed_details:
            odds_str = f"  {d['final_odds']:.1f}倍" if d.get('final_odds') else ''
            actual = d.get('actual', 'N/A')
            status = d.get('status', '')
            if d.get('is_hit'):
                payout = d.get('payout', 0)
                lines.append(f"  ✅ {d['venue']} {d['race_num']}R  買=`{d['combinations']}`{odds_str}  実=`{actual}`  +{payout:,}円(見送)")
            elif status == '結果未取得':
                lines.append(f"  ⏳ {d['venue']} {d['race_num']}R  買=`{d['combinations']}`{odds_str}  結果未取得")
            else:
                lines.append(f"  ⚪ {d['venue']} {d['race_num']}R  買=`{d['combinations']}`{odds_str}  実=`{actual}`")

    # 候補: 的中のみ表示
    if candidate_details:
        lines.append("")
        lines.append(f"候補 {candidate_hit_count}/{candidate_count}的中")
        for d in candidate_details:
            if d['status'] == '的中(候補)':
                odds_str = f"  {d['odds_reason']}" if d.get('odds_reason') else ''
                lines.append(f"  ✅ {d['venue']} {d['race_num']}R  `{d['combinations']}`{odds_str}")

    # shadow 多点観測（hit/miss + 実結果表示）
    shadow_details = result.get('shadow_details', [])
    if shadow_details:
        sh_hit = sum(1 for d in shadow_details if d.get('hit_combination'))
        lines.append("")
        lines.append(f"👁 **shadow** {sh_hit}/{len(shadow_details)}的中")
        for d in shadow_details:
            combos_list = [c.strip() for c in d['combinations'].split(',') if c.strip()]
            actual = d.get('actual', 'N/A')
            hit = d.get('hit_combination')
            odds_h = d.get('odds_if_hit')
            if not d.get('has_result'):
                lines.append(f"  ⏳ {d['venue']} {d['race_num']}R  実=未取得  {'/'.join(combos_list)}")
            elif hit:
                odds_str = f"  {odds_h:.1f}倍" if odds_h else ''
                lines.append(f"  ✅ {d['venue']} {d['race_num']}R  実=`{actual}`  hit=`{hit}`{odds_str}")
            else:
                lines.append(f"  ❌ {d['venue']} {d['race_num']}R  実=`{actual}`  {'/'.join(combos_list)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# reconcile_log: 送信済み日付トラッキング（キャッチアップ重複送信防止用）
# ---------------------------------------------------------------------------

def _ensure_reconcile_log(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reconcile_log (
            date TEXT PRIMARY KEY,
            sent_at TEXT NOT NULL,
            target_count INTEGER
        )
    """)


def log_reconcile_sent(db_path: str, target_date: str, target_count: int) -> None:
    """reconcile 送信完了を DB に記録（block_a から呼ぶ）"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        _ensure_reconcile_log(conn)
        conn.execute(
            "INSERT OR REPLACE INTO reconcile_log (date, sent_at, target_count) VALUES (?, ?, ?)",
            (target_date, datetime.now().isoformat(), target_count)
        )
        conn.commit()
    except Exception as e:
        print(f"  [WARN] reconcile_log 記録失敗: {e}")
    finally:
        if conn:
            conn.close()


def get_unreconciled_purchase_dates(db_path: str, lookback_days: int = 14) -> list:
    """
    直近 lookback_days 日間で confirmed 購入があるが reconcile_log に記録されていない日付を返す。
    block_a キャッチアップ用。今日・未来日付は除外（結果未確定のため）。
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        _ensure_reconcile_log(conn)
        conn.commit()
        cur = conn.cursor()
        # r.race_date < date('now','localtime') で今日以降を除外
        cur.execute("""
            SELECT DISTINCT r.race_date
            FROM bet_notifications bn
            JOIN races r ON bn.race_id = r.id
            WHERE bn.notification_type = 'confirmed'
              AND r.race_date >= date('now', 'localtime', ?)
              AND r.race_date < date('now', 'localtime')
              AND r.race_date NOT IN (SELECT date FROM reconcile_log)
            ORDER BY r.race_date
        """, (f'-{lookback_days} days',))
        dates = [row[0] for row in cur.fetchall()]
        return dates
    except Exception as e:
        print(f"  [WARN] 未reconcile日付取得失敗: {e}")
        return []
    finally:
        if conn:
            conn.close()
