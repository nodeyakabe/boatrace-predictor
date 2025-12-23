# -*- coding: utf-8 -*-
"""
P-3/P-6-2 調整幅の全件検証

2024-2025年の全購入対象レースで各調整幅の効果を検証
"""
import sys
import sqlite3
import io
from pathlib import Path
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config.feature_flags as ff
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def simulate_adjustment_for_race(cursor, race_id, venue_code, adjustment_pct, evaluator):
    """1レースに対して調整シミュレーション"""

    cursor.execute('''
        SELECT pit_number, total_score, confidence
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY total_score DESC
    ''', (race_id,))
    preds = cursor.fetchall()

    if len(preds) < 6:
        return None

    # 元のTop3
    original_top3 = [p['pit_number'] for p in preds[:3]]
    original_combo = f"{original_top3[0]}-{original_top3[1]}-{original_top3[2]}"
    confidence = preds[0]['confidence']

    # 4位・5位を2着・3着候補として調整
    adjusted_preds = []
    for i, p in enumerate(preds):
        new_score = p['total_score']
        if i == 3:  # 4位 → 2着候補
            new_score = p['total_score'] * (1 + adjustment_pct / 100)
        elif i == 4:  # 5位 → 3着候補
            new_score = p['total_score'] * (1 + adjustment_pct / 100 * 0.5)
        adjusted_preds.append({
            'pit_number': p['pit_number'],
            'total_score': new_score,
            'confidence': p['confidence']
        })

    adjusted_preds.sort(key=lambda x: x['total_score'], reverse=True)
    adjusted_top3 = [p['pit_number'] for p in adjusted_preds[:3]]
    adjusted_combo = f"{adjusted_top3[0]}-{adjusted_top3[1]}-{adjusted_top3[2]}"

    top3_changed = original_top3 != adjusted_top3

    # 実際の結果
    cursor.execute('''
        SELECT pit_number FROM results
        WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
        ORDER BY rank
    ''', (race_id,))
    actual_results = cursor.fetchall()

    if len(actual_results) < 3:
        return None

    actual_combo = f"{actual_results[0]['pit_number']}-{actual_results[1]['pit_number']}-{actual_results[2]['pit_number']}"

    # 1コース級別
    cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
    c1 = cursor.fetchone()
    c1_rank = c1['racer_rank'] if c1 else 'B1'

    results = {
        'top3_changed': top3_changed,
        'original': {'target': False, 'hit': False, 'bet': 0, 'payout': 0},
        'adjusted': {'target': False, 'hit': False, 'bet': 0, 'payout': 0}
    }

    # 元の予測
    cursor.execute(
        'SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
        (race_id, original_combo))
    odds_row = cursor.fetchone()

    if odds_row:
        odds = odds_row['odds']
        result = evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=original_combo,
            new_combo=original_combo,
            old_odds=odds,
            new_odds=odds,
            has_beforeinfo=True,
            venue_code=venue_code
        )

        if result.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            bet_amount = result.bet_amount
            results['original']['target'] = True
            results['original']['bet'] = bet_amount

            if original_combo == actual_combo:
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()
                if payout_row:
                    payout = (bet_amount / 100) * payout_row['amount']
                    results['original']['hit'] = True
                    results['original']['payout'] = payout

    # 調整後の予測
    cursor.execute(
        'SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
        (race_id, adjusted_combo))
    odds_row_adj = cursor.fetchone()

    if odds_row_adj:
        odds_adj = odds_row_adj['odds']
        result_adj = evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=adjusted_combo,
            new_combo=adjusted_combo,
            old_odds=odds_adj,
            new_odds=odds_adj,
            has_beforeinfo=True,
            venue_code=venue_code
        )

        if result_adj.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            bet_amount = result_adj.bet_amount
            results['adjusted']['target'] = True
            results['adjusted']['bet'] = bet_amount

            if adjusted_combo == actual_combo:
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()
                if payout_row:
                    payout = (bet_amount / 100) * payout_row['amount']
                    results['adjusted']['hit'] = True
                    results['adjusted']['payout'] = payout

    return results


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True
    evaluator = BetTargetEvaluator()

    print("=" * 120)
    print("P-3/P-6-2 調整幅の全件検証（2024-2025年）")
    print("=" * 120)
    print()

    # 全レース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code
        FROM races r
        WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
    ''')
    all_races = cursor.fetchall()
    print(f"対象レース数: {len(all_races):,}件")
    print()

    # 各調整幅でシミュレーション
    adjustment_levels = [0, 5, 10, 15, 20, 30]

    results_by_adj = {}

    for adj_pct in adjustment_levels:
        print(f"調整幅 {adj_pct}% 検証中...")

        stats = {
            'total': 0,
            'top3_changed': 0,
            'original': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'adjusted': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
        }

        for race in all_races:
            race_id = race['race_id']
            venue_code = int(race['venue_code']) if race['venue_code'] else 0

            result = simulate_adjustment_for_race(cursor, race_id, venue_code, adj_pct, evaluator)

            if result is None:
                continue

            stats['total'] += 1
            if result['top3_changed']:
                stats['top3_changed'] += 1

            if result['original']['target']:
                stats['original']['target'] += 1
                stats['original']['bet'] += result['original']['bet']
                if result['original']['hit']:
                    stats['original']['hit'] += 1
                    stats['original']['payout'] += result['original']['payout']

            if result['adjusted']['target']:
                stats['adjusted']['target'] += 1
                stats['adjusted']['bet'] += result['adjusted']['bet']
                if result['adjusted']['hit']:
                    stats['adjusted']['hit'] += 1
                    stats['adjusted']['payout'] += result['adjusted']['payout']

        results_by_adj[adj_pct] = stats

    conn.close()

    # 結果表示
    print()
    print("=" * 140)
    print("検証結果")
    print("=" * 140)

    baseline = results_by_adj[0]
    baseline_roi = baseline['original']['payout'] / baseline['original']['bet'] * 100 if baseline['original']['bet'] > 0 else 0
    baseline_profit = baseline['original']['payout'] - baseline['original']['bet']

    print(f"\nベースライン（調整なし）: 購入{baseline['original']['target']}件, 的中{baseline['original']['hit']}件, ROI {baseline_roi:.1f}%, 収支 {baseline_profit:+,.0f}円")
    print()

    print(f"{'調整幅':>8} | {'Top3変化':>10} | {'変化率':>8} | {'購入数':>8} | {'的中数':>8} | {'的中率':>8} | {'ROI':>10} | {'収支':>15} | {'ROI差':>10}")
    print("-" * 130)

    for adj_pct in adjustment_levels:
        stats = results_by_adj[adj_pct]

        change_rate = stats['top3_changed'] / stats['total'] * 100 if stats['total'] > 0 else 0

        adj_target = stats['adjusted']['target']
        adj_hit = stats['adjusted']['hit']
        adj_bet = stats['adjusted']['bet']
        adj_payout = stats['adjusted']['payout']

        adj_hit_rate = adj_hit / adj_target * 100 if adj_target > 0 else 0
        adj_roi = adj_payout / adj_bet * 100 if adj_bet > 0 else 0
        adj_profit = adj_payout - adj_bet
        roi_diff = adj_roi - baseline_roi

        print(f"{adj_pct:>7}% | {stats['top3_changed']:>10,} | {change_rate:>7.1f}% | {adj_target:>8,} | {adj_hit:>8} | {adj_hit_rate:>7.2f}% | {adj_roi:>9.1f}% | {adj_profit:>+14,.0f}円 | {roi_diff:>+9.1f}pt")

    # 最適値の特定
    print()
    print("=" * 140)
    print("結論")
    print("=" * 140)

    best_adj = max(adjustment_levels, key=lambda x: results_by_adj[x]['adjusted']['payout'] / results_by_adj[x]['adjusted']['bet'] if results_by_adj[x]['adjusted']['bet'] > 0 else 0)
    best_stats = results_by_adj[best_adj]
    best_roi = best_stats['adjusted']['payout'] / best_stats['adjusted']['bet'] * 100 if best_stats['adjusted']['bet'] > 0 else 0
    best_profit = best_stats['adjusted']['payout'] - best_stats['adjusted']['bet']

    print(f"\n最適調整幅: {best_adj}%")
    print(f"  ROI: {best_roi:.1f}% (ベースライン比: {best_roi - baseline_roi:+.1f}pt)")
    print(f"  収支: {best_profit:+,.0f}円 (ベースライン比: {best_profit - baseline_profit:+,.0f}円)")

    if best_adj > 0 and best_roi > baseline_roi:
        print(f"\n→ 調整幅を{best_adj}%に変更すべき！")
    else:
        print(f"\n→ 調整による改善効果なし。現状維持が最適。")


if __name__ == "__main__":
    main()
