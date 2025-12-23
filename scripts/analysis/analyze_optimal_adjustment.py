# -*- coding: utf-8 -*-
"""
P-3/P-6-2の最適調整幅を分析

現在の5%調整では効果がないため、どの程度の調整幅があれば
Top3順位が変わるか、また変わった場合の的中率への影響を検証
"""
import sys
import sqlite3
import io
import random
from pathlib import Path
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config.feature_flags as ff
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def analyze_score_gaps(cursor, sample_races):
    """Top3間のスコア差を分析"""
    gaps = []

    for race in sample_races:
        race_id = race['race_id']

        cursor.execute('''
            SELECT pit_number, total_score, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY total_score DESC
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        scores = [p['total_score'] for p in preds[:6]]

        # 各順位間のスコア差（パーセンテージ）
        for i in range(5):
            if scores[i] > 0:
                gap_pct = (scores[i] - scores[i+1]) / scores[i] * 100
                gaps.append({
                    'race_id': race_id,
                    'position': i + 1,
                    'score_high': scores[i],
                    'score_low': scores[i+1],
                    'gap_pct': gap_pct
                })

    return gaps


def simulate_adjustment(cursor, sample_races, adjustment_pct, evaluator):
    """特定の調整幅でシミュレーション"""

    results = {
        'original': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
        'adjusted': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
        'top3_changed': 0,
        'total_compared': 0
    }

    for race in sample_races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        cursor.execute('''
            SELECT pit_number, total_score, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY total_score DESC
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        # 元のTop3
        original_top3 = [p['pit_number'] for p in preds[:3]]
        original_combo = f"{original_top3[0]}-{original_top3[1]}-{original_top3[2]}"

        # 調整後（2着候補と3着候補のスコアを上げる）
        # シミュレーション: 4位と5位を2着・3着候補として調整
        adjusted_preds = []
        for i, p in enumerate(preds):
            new_score = p['total_score']
            if i == 3:  # 4位 → 2着候補として調整
                new_score = p['total_score'] * (1 + adjustment_pct / 100)
            elif i == 4:  # 5位 → 3着候補として調整
                new_score = p['total_score'] * (1 + adjustment_pct / 100 * 0.5)
            adjusted_preds.append({
                'pit_number': p['pit_number'],
                'total_score': new_score,
                'confidence': p['confidence']
            })

        adjusted_preds.sort(key=lambda x: x['total_score'], reverse=True)
        adjusted_top3 = [p['pit_number'] for p in adjusted_preds[:3]]
        adjusted_combo = f"{adjusted_top3[0]}-{adjusted_top3[1]}-{adjusted_top3[2]}"

        results['total_compared'] += 1
        if original_top3 != adjusted_top3:
            results['top3_changed'] += 1

        # 実際の結果
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        actual_results = cursor.fetchall()

        if len(actual_results) < 3:
            continue

        actual_combo = f"{actual_results[0]['pit_number']}-{actual_results[1]['pit_number']}-{actual_results[2]['pit_number']}"

        # 元の予測で的中判定
        confidence = preds[0]['confidence']

        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        cursor.execute(
            'SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
            (race_id, original_combo))
        odds_row = cursor.fetchone()
        if not odds_row:
            continue

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
            results['original']['target'] += 1
            results['original']['bet'] += bet_amount

            if original_combo == actual_combo:
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()
                if payout_row:
                    payout = (bet_amount / 100) * payout_row['amount']
                    results['original']['hit'] += 1
                    results['original']['payout'] += payout

        # 調整後の予測で的中判定
        cursor.execute(
            'SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
            (race_id, adjusted_combo))
        odds_row_adj = cursor.fetchone()
        if not odds_row_adj:
            continue

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
            results['adjusted']['target'] += 1
            results['adjusted']['bet'] += bet_amount

            if adjusted_combo == actual_combo:
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()
                if payout_row:
                    payout = (bet_amount / 100) * payout_row['amount']
                    results['adjusted']['hit'] += 1
                    results['adjusted']['payout'] += payout

    return results


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True
    evaluator = BetTargetEvaluator()

    print("=" * 100)
    print("P-3/P-6-2 最適調整幅分析")
    print("=" * 100)
    print()

    # 購入対象レースを取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    all_races = cursor.fetchall()

    # サンプル選択（購入対象になりそうなレース）
    target_races = []
    for race in all_races:
        race_id = race['race_id']

        cursor.execute('''
            SELECT confidence FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY total_score DESC LIMIT 1
        ''', (race_id,))
        pred = cursor.fetchone()

        if pred and pred['confidence'] in ['A', 'B', 'C']:
            target_races.append(race)

    sample_size = min(500, len(target_races))
    random.seed(42)
    sample_races = random.sample(target_races, sample_size)

    print(f"サンプルレース数: {sample_size}件")
    print()

    # 1. スコア差の分析
    print("=" * 100)
    print("1. Top6間のスコア差分析")
    print("=" * 100)

    gaps = analyze_score_gaps(cursor, sample_races)

    # 順位間のスコア差の統計
    for pos in range(1, 6):
        pos_gaps = [g['gap_pct'] for g in gaps if g['position'] == pos]
        if pos_gaps:
            avg_gap = sum(pos_gaps) / len(pos_gaps)
            min_gap = min(pos_gaps)
            max_gap = max(pos_gaps)
            print(f"{pos}位-{pos+1}位間: 平均 {avg_gap:.2f}%, 最小 {min_gap:.2f}%, 最大 {max_gap:.2f}%")

    # 2着-3着間のスコア差の分布
    gap_2_3 = [g['gap_pct'] for g in gaps if g['position'] == 2]
    gap_3_4 = [g['gap_pct'] for g in gaps if g['position'] == 3]

    print()
    print("2着-3着間のスコア差分布:")
    if gap_2_3:
        pct_5 = len([g for g in gap_2_3 if g < 5]) / len(gap_2_3) * 100
        pct_10 = len([g for g in gap_2_3 if g < 10]) / len(gap_2_3) * 100
        pct_20 = len([g for g in gap_2_3 if g < 20]) / len(gap_2_3) * 100
        print(f"  5%未満: {pct_5:.1f}%")
        print(f"  10%未満: {pct_10:.1f}%")
        print(f"  20%未満: {pct_20:.1f}%")

    # 2. 調整幅別シミュレーション
    print()
    print("=" * 100)
    print("2. 調整幅別シミュレーション")
    print("=" * 100)
    print()
    print(f"{'調整幅':>8} | {'Top3変化':>10} | {'変化率':>8} | {'元的中':>8} | {'調整後的中':>10} | {'元ROI':>10} | {'調整後ROI':>10} | {'ROI差':>10}")
    print("-" * 100)

    for adj_pct in [5, 10, 15, 20, 30, 50]:
        results = simulate_adjustment(cursor, sample_races, adj_pct, evaluator)

        change_rate = results['top3_changed'] / results['total_compared'] * 100 if results['total_compared'] > 0 else 0

        orig_roi = results['original']['payout'] / results['original']['bet'] * 100 if results['original']['bet'] > 0 else 0
        adj_roi = results['adjusted']['payout'] / results['adjusted']['bet'] * 100 if results['adjusted']['bet'] > 0 else 0
        roi_diff = adj_roi - orig_roi

        print(f"{adj_pct:>7}% | {results['top3_changed']:>10} | {change_rate:>7.1f}% | {results['original']['hit']:>8} | {results['adjusted']['hit']:>10} | {orig_roi:>9.1f}% | {adj_roi:>9.1f}% | {roi_diff:>+9.1f}pt")

    conn.close()

    # 結論
    print()
    print("=" * 100)
    print("3. 分析結論")
    print("=" * 100)
    print()
    print("考察ポイント:")
    print("1. 現在の5%調整では2着-3着間のスコア差を超えられないケースが多い")
    print("2. Top3を変更するには少なくとも10-20%程度の調整が必要")
    print("3. ただし、調整幅を大きくすると「当たっていた予測を外す」リスクも増加")
    print("4. 最適な調整幅は「正しく変更できるケース」と「誤って変更するケース」のバランス")


if __name__ == "__main__":
    main()
