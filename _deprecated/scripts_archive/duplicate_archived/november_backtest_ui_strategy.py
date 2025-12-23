# -*- coding: utf-8 -*-
"""
11月バックテスト - UI総合タブの購入戦略に基づく

UIの「購入対象判定」と同じ条件で11月をシミュレーション:
- 信頼度C + 従来方式 + オッズ30-60倍 + 1コースA1級 → 500円
- 信頼度C + 従来方式 + オッズ50倍+ + 1コースA級 → 500円
- 信頼度D + 新方式 + オッズ30倍+ + 1コースA級 → 300円
- 信頼度D + 新方式 + オッズ20倍+ + 1コースA級 → 300円

除外: 信頼度A/B, 1コースB級

使用方法:
    python scripts/november_backtest_ui_strategy.py
"""

import sys
import os
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def get_november_races_with_all_data(db_path: str) -> list:
    """11月のレースを取得（予測・オッズ・1コース級別つき）"""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                r.race_number,
                e.racer_rank as c1_rank
            FROM races r
            JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
            WHERE r.race_date >= '2025-11-01' AND r.race_date <= '2025-11-30'
            ORDER BY r.race_date, r.venue_code, r.race_number
        ''')
        return cursor.fetchall()


def get_prediction(db_path: str, race_id: int) -> dict:
    """予測データを取得（信頼度と順位予想）"""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT pit_number, rank_prediction, confidence, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        rows = cursor.fetchall()

        if len(rows) < 6:
            return None

        sorted_rows = sorted(rows, key=lambda x: x[1])
        predicted_ranks = [r[0] for r in sorted_rows]
        confidence = sorted_rows[0][2]  # 1位予想の信頼度

        # 従来方式の買い目（スコア順1-2-3位）
        old_combo = f"{predicted_ranks[0]}-{predicted_ranks[1]}-{predicted_ranks[2]}"

        return {
            'confidence': confidence,
            'predicted_ranks': predicted_ranks,
            'old_combo': old_combo,
            'new_combo': old_combo  # 今回は同じ（新方式ロジックは別途必要）
        }


def get_race_odds(db_path: str, race_id: int) -> dict:
    """オッズを取得"""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ?
        ''', (race_id,))
        return {row[0]: row[1] for row in cursor.fetchall()}


def get_race_result(db_path: str, race_id: int) -> dict:
    """結果を取得"""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # 着順
        cursor.execute('''
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        rows = cursor.fetchall()

        if len(rows) < 3:
            return None

        actual_combo = f"{rows[0][0]}-{rows[1][0]}-{rows[2][0]}"

        # 払戻金
        cursor.execute('''
            SELECT amount FROM payouts
            WHERE race_id = ? AND bet_type = 'trifecta'
        ''', (race_id,))
        payout_row = cursor.fetchone()
        payout = payout_row[0] if payout_row else 0

        return {
            'actual_combo': actual_combo,
            'payout': payout
        }


def evaluate_bet_target(confidence: str, c1_rank: str, combo: str, odds: float) -> dict:
    """
    購入対象を判定（BetTargetEvaluatorと同じロジック）

    Returns:
        {'is_target': bool, 'bet_amount': int, 'method': str, 'reason': str}
    """
    # 信頼度A/Bは除外
    if confidence in ['A', 'B']:
        return {'is_target': False, 'bet_amount': 0, 'method': '-', 'reason': f'信頼度{confidence}は対象外'}

    # 1コースB級は除外
    if c1_rank not in ['A1', 'A2']:
        return {'is_target': False, 'bet_amount': 0, 'method': '-', 'reason': f'1コース{c1_rank}は対象外'}

    # オッズがない場合は除外
    if not odds or odds == 0:
        return {'is_target': False, 'bet_amount': 0, 'method': '-', 'reason': 'オッズなし'}

    # 信頼度Cの条件
    if confidence == 'C':
        # 条件1: 30-60倍 + A1のみ
        if c1_rank == 'A1' and 30 <= odds < 60:
            return {'is_target': True, 'bet_amount': 500, 'method': '従来',
                    'reason': f'C+従来+30-60倍+A1', 'expected_roi': 127.2}
        # 条件2: 50倍+ + A級
        if odds >= 50:
            return {'is_target': True, 'bet_amount': 500, 'method': '従来',
                    'reason': f'C+従来+50倍+A級', 'expected_roi': 121.0}
        return {'is_target': False, 'bet_amount': 0, 'method': '-', 'reason': f'C+オッズ{odds:.1f}倍は範囲外'}

    # 信頼度Dの条件
    if confidence == 'D':
        # 条件1: 30倍+
        if odds >= 30:
            return {'is_target': True, 'bet_amount': 300, 'method': '新方式',
                    'reason': f'D+新方式+30倍+A級', 'expected_roi': 209.1}
        # 条件2: 20倍+
        if odds >= 20:
            return {'is_target': True, 'bet_amount': 300, 'method': '新方式',
                    'reason': f'D+新方式+20倍+A級', 'expected_roi': 178.9}
        return {'is_target': False, 'bet_amount': 0, 'method': '-', 'reason': f'D+オッズ{odds:.1f}倍は範囲外'}

    # 信頼度Eは対象外
    return {'is_target': False, 'bet_amount': 0, 'method': '-', 'reason': f'信頼度{confidence}は対象外'}


def run_ui_strategy_backtest(db_path: str):
    """UI戦略に基づくバックテスト"""
    print("=" * 80)
    print("11月バックテスト - UI総合タブ購入戦略")
    print("=" * 80)
    print("購入条件:")
    print("  - 信頼度C + 従来 + 30-60倍 + 1コースA1 → 500円")
    print("  - 信頼度C + 従来 + 50倍+ + 1コースA級 → 500円")
    print("  - 信頼度D + 新方式 + 30倍+ + 1コースA級 → 300円")
    print("  - 信頼度D + 新方式 + 20倍+ + 1コースA級 → 300円")
    print("除外: 信頼度A/B, 1コースB級")
    print("=" * 80)
    print()

    # レース取得
    races = get_november_races_with_all_data(db_path)
    print(f"11月総レース数: {len(races)}")

    # 統計
    daily_stats = defaultdict(lambda: {
        'total_races': 0,
        'target_races': 0,
        'hits': 0,
        'bet_amount': 0,
        'payout': 0
    })

    condition_stats = defaultdict(lambda: {
        'count': 0,
        'hits': 0,
        'bet_amount': 0,
        'payout': 0
    })

    # 詳細記録
    bet_details = []

    total_target = 0
    total_hits = 0
    total_bet = 0
    total_payout = 0
    skipped = 0
    excluded_by_condition = defaultdict(int)

    for race_id, race_date, venue_code, race_number, c1_rank in races:
        # 予測取得
        pred = get_prediction(db_path, race_id)
        if not pred:
            skipped += 1
            continue

        # オッズ取得
        odds_data = get_race_odds(db_path, race_id)
        if not odds_data:
            skipped += 1
            continue

        # 結果取得
        result = get_race_result(db_path, race_id)
        if not result:
            skipped += 1
            continue

        confidence = pred['confidence']
        combo = pred['old_combo']  # 従来方式の買い目
        odds = odds_data.get(combo, 0)

        daily_stats[race_date]['total_races'] += 1

        # 購入対象判定
        evaluation = evaluate_bet_target(confidence, c1_rank, combo, odds)

        if not evaluation['is_target']:
            excluded_by_condition[evaluation['reason']] += 1
            continue

        # 購入対象
        total_target += 1
        bet_amount = evaluation['bet_amount']
        total_bet += bet_amount

        daily_stats[race_date]['target_races'] += 1
        daily_stats[race_date]['bet_amount'] += bet_amount

        condition_key = evaluation['reason']
        condition_stats[condition_key]['count'] += 1
        condition_stats[condition_key]['bet_amount'] += bet_amount

        # 的中判定
        hit = (combo == result['actual_combo'])
        payout = result['payout'] if hit else 0

        if hit:
            total_hits += 1
            total_payout += payout
            daily_stats[race_date]['hits'] += 1
            daily_stats[race_date]['payout'] += payout
            condition_stats[condition_key]['hits'] += 1
            condition_stats[condition_key]['payout'] += payout

        # 詳細記録
        bet_details.append({
            'date': race_date,
            'venue': venue_code,
            'race': race_number,
            'confidence': confidence,
            'c1_rank': c1_rank,
            'combo': combo,
            'odds': odds,
            'bet_amount': bet_amount,
            'hit': hit,
            'payout': payout,
            'actual': result['actual_combo'],
            'condition': condition_key
        })

    # 結果出力
    print(f"\n{'='*80}")
    print("総合成績")
    print("=" * 80)
    print(f"全レース数: {len(races)}")
    print(f"スキップ: {skipped} (予測/オッズ/結果なし)")
    print(f"購入対象: {total_target}レース")
    print(f"的中数: {total_hits}")
    print(f"的中率: {total_hits/total_target*100:.2f}%" if total_target > 0 else "的中率: N/A")
    print(f"投資額: {total_bet:,}円")
    print(f"払戻額: {total_payout:,}円")
    print(f"収支: {total_payout - total_bet:+,}円")
    print(f"ROI: {total_payout/total_bet*100:.1f}%" if total_bet > 0 else "ROI: N/A")

    # 除外理由別
    print(f"\n{'='*80}")
    print("除外理由別レース数")
    print("=" * 80)
    for reason, count in sorted(excluded_by_condition.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}レース")

    # 条件別成績
    print(f"\n{'='*80}")
    print("条件別成績")
    print("=" * 80)
    print(f"{'条件':<30} {'購入数':>8} {'的中':>6} {'的中率':>8} {'投資額':>12} {'払戻':>12} {'ROI':>8}")
    print("-" * 90)

    for cond in sorted(condition_stats.keys()):
        stats = condition_stats[cond]
        hit_rate = stats['hits']/stats['count']*100 if stats['count'] > 0 else 0
        roi = stats['payout']/stats['bet_amount']*100 if stats['bet_amount'] > 0 else 0
        print(f"{cond:<30} {stats['count']:>8} {stats['hits']:>6} {hit_rate:>7.1f}% "
              f"{stats['bet_amount']:>12,} {stats['payout']:>12,} {roi:>7.1f}%")

    # 日別成績
    print(f"\n{'='*80}")
    print("日別成績")
    print("=" * 80)
    print(f"{'日付':<12} {'全R':>6} {'購入':>6} {'的中':>6} {'投資額':>10} {'払戻':>12} {'収支':>12} {'ROI':>8}")
    print("-" * 80)

    cum_bet = 0
    cum_payout = 0

    for date in sorted(daily_stats.keys()):
        stats = daily_stats[date]
        if stats['target_races'] == 0:
            continue
        roi = stats['payout']/stats['bet_amount']*100 if stats['bet_amount'] > 0 else 0
        profit = stats['payout'] - stats['bet_amount']
        cum_bet += stats['bet_amount']
        cum_payout += stats['payout']

        print(f"{date:<12} {stats['total_races']:>6} {stats['target_races']:>6} {stats['hits']:>6} "
              f"{stats['bet_amount']:>10,} {stats['payout']:>12,} {profit:>+12,} {roi:>7.1f}%")

    print("-" * 80)
    if cum_bet > 0:
        print(f"{'累計':<12} {'-':>6} {total_target:>6} {total_hits:>6} "
              f"{cum_bet:>10,} {cum_payout:>12,} {cum_payout-cum_bet:>+12,} {cum_payout/cum_bet*100:.1f}%")

    # 高配当的中
    print(f"\n{'='*80}")
    print("的中一覧")
    print("=" * 80)

    hits = [d for d in bet_details if d['hit']]
    hits.sort(key=lambda x: -x['payout'])

    if hits:
        print(f"{'日付':<12} {'会場':>4} {'R':>3} {'信頼度':>4} {'1コース':>6} {'買い目':<10} {'オッズ':>8} {'払戻':>10}")
        print("-" * 70)
        for h in hits:
            print(f"{h['date']:<12} {h['venue']:>4} {h['race']:>3}R {h['confidence']:>4} "
                  f"{h['c1_rank']:>6} {h['combo']:<10} {h['odds']:>7.1f}倍 {h['payout']:>10,}円")
    else:
        print("的中なし")

    print(f"\n{'='*80}")
    print("バックテスト完了")
    print("=" * 80)

    return {
        'total_target': total_target,
        'total_hits': total_hits,
        'total_bet': total_bet,
        'total_payout': total_payout,
        'roi': total_payout/total_bet*100 if total_bet > 0 else 0
    }


if __name__ == '__main__':
    run_ui_strategy_backtest(DATABASE_PATH)
