# -*- coding: utf-8 -*-
"""
オッズ統合の簡易テストスクリプト
"""
import sys
import sqlite3
from pathlib import Path
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# バックアップDBを使用
db_path = str(ROOT_DIR / 'data' / 'boatrace_backup_20251212_145413.db')

print(f"Using database: {db_path}")

from src.analysis.race_predictor import RacePredictor
from src.analysis.scorers.odds_calibrator import OddsCalibrator
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus

def run_test(max_races=200):
    """簡易テスト実行"""
    # 対象レース取得
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        INNER JOIN trifecta_odds o ON r.id = o.race_id
        INNER JOIN results res ON r.id = res.race_id
        WHERE r.race_date BETWEEN '2025-11-28' AND '2025-12-10'
        AND res.is_invalid = 0
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = [dict(row) for row in cursor.fetchall()]
    print(f'対象レース数: {len(races)}')

    # 予測器
    predictor = RacePredictor(db_path)
    evaluator = BetTargetEvaluator()

    # 結果格納
    all_results = {}

    for alpha in [0.0, 0.1, 0.2, 0.3]:
        print(f"\n--- alpha={alpha} テスト開始 ---")

        calibrator = OddsCalibrator(db_path, rank23_alpha=alpha) if alpha > 0 else None

        stats = {
            'purchased': 0, 'hit': 0,
            'rank1_hit': 0, 'rank2_hit': 0, 'rank3_hit': 0,
            'bet_amount': 0, 'payout': 0
        }

        processed = 0
        for race in races[:max_races]:
            race_id = race['race_id']

            try:
                predictions = predictor.predict_race(race_id)
            except Exception as e:
                continue

            if not predictions or len(predictions) < 6:
                continue

            # alpha > 0の場合は校正
            if alpha > 0 and calibrator:
                predictions = calibrator.calibrate_rank23_predictions(
                    [p.copy() for p in predictions], race_id, alpha=alpha
                )

            confidence = predictions[0].get('confidence', 'E')
            if confidence in ['A', 'B']:
                continue

            top3 = [p['pit_number'] for p in predictions[:3]]
            combo = f'{top3[0]}-{top3[1]}-{top3[2]}'

            cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?', (race_id, combo))
            odds_row = cursor.fetchone()
            if not odds_row:
                continue

            cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
            c1_row = cursor.fetchone()
            c1_rank = c1_row['racer_rank'] if c1_row else 'B1'

            eval_result = evaluator.evaluate(
                confidence=confidence, c1_rank=c1_rank,
                old_combo=combo, new_combo=combo,
                old_odds=odds_row['odds'], new_odds=odds_row['odds'],
                has_beforeinfo=True, venue_code=race['venue_code']
            )

            if eval_result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                continue

            stats['purchased'] += 1
            stats['bet_amount'] += eval_result.bet_amount

            cursor.execute('''
                SELECT pit_number FROM results WHERE race_id = ? AND is_invalid = 0 AND rank IN ('1', '2', '3') ORDER BY rank
            ''', (race_id,))
            res_rows = cursor.fetchall()

            if len(res_rows) < 3:
                continue

            actual = [res_rows[0]['pit_number'], res_rows[1]['pit_number'], res_rows[2]['pit_number']]
            actual_combo = f'{actual[0]}-{actual[1]}-{actual[2]}'

            if top3[0] == actual[0]: stats['rank1_hit'] += 1
            if top3[1] == actual[1]: stats['rank2_hit'] += 1
            if top3[2] == actual[2]: stats['rank3_hit'] += 1

            if combo == actual_combo:
                stats['hit'] += 1
                cursor.execute('SELECT amount FROM payouts WHERE race_id = ? AND bet_type = "trifecta" AND combination = ?', (race_id, actual_combo))
                payout_row = cursor.fetchone()
                if payout_row:
                    stats['payout'] += (eval_result.bet_amount / 100) * payout_row['amount']

            processed += 1
            if processed % 50 == 0:
                print(f'  {processed}レース処理完了')

        all_results[alpha] = stats
        print(f"  購入: {stats['purchased']}, 的中: {stats['hit']}")

    conn.close()

    # 結果表示
    print("\n" + "=" * 100)
    print("オッズ統合による2着・3着予測精度改善バックテスト結果")
    print("=" * 100)

    print("\n【全体サマリー】")
    print(f"{'alpha':<10} {'購入数':<10} {'的中数':<10} {'的中率':<12} {'投資額':<14} {'払戻額':<14} {'ROI':<10} {'収支':<14}")
    print("-" * 100)

    for alpha, stats in all_results.items():
        purchased = stats['purchased']
        if purchased == 0:
            continue

        hit = stats['hit']
        hit_rate = hit / purchased * 100
        bet = stats['bet_amount']
        payout = stats['payout']
        roi = payout / bet * 100 if bet > 0 else 0
        profit = payout - bet

        print(f"{alpha:<10} {purchased:<10} {hit:<10} {hit_rate:>8.2f}% "
              f"{bet:>12,.0f}円 {payout:>12,.0f}円 {roi:>8.1f}% {profit:>+12,.0f}円")

    print("\n【各順位の的中率】")
    print(f"{'alpha':<10} {'1着的中率':<14} {'2着的中率':<14} {'3着的中率':<14}")
    print("-" * 60)

    for alpha, stats in all_results.items():
        purchased = stats['purchased']
        if purchased == 0:
            continue

        rank1 = stats['rank1_hit'] / purchased * 100
        rank2 = stats['rank2_hit'] / purchased * 100
        rank3 = stats['rank3_hit'] / purchased * 100

        print(f"{alpha:<10} {rank1:>10.2f}% {rank2:>10.2f}% {rank3:>10.2f}%")

    # baselineとの比較
    if 0.0 in all_results and all_results[0.0]['purchased'] > 0:
        baseline = all_results[0.0]
        baseline_roi = baseline['payout'] / baseline['bet_amount'] * 100 if baseline['bet_amount'] > 0 else 0
        baseline_rank2 = baseline['rank2_hit'] / baseline['purchased'] * 100
        baseline_rank3 = baseline['rank3_hit'] / baseline['purchased'] * 100

        print("\n【baselineとの比較】")
        print(f"{'alpha':<10} {'ROI差':<12} {'2着的中率差':<14} {'3着的中率差':<14}")
        print("-" * 60)

        for alpha, stats in all_results.items():
            if alpha == 0.0 or stats['purchased'] == 0:
                continue

            roi = stats['payout'] / stats['bet_amount'] * 100 if stats['bet_amount'] > 0 else 0
            rank2 = stats['rank2_hit'] / stats['purchased'] * 100
            rank3 = stats['rank3_hit'] / stats['purchased'] * 100

            roi_diff = roi - baseline_roi
            rank2_diff = rank2 - baseline_rank2
            rank3_diff = rank3 - baseline_rank3

            print(f"{alpha:<10} {roi_diff:>+10.2f}pt {rank2_diff:>+12.2f}pt {rank3_diff:>+12.2f}pt")

    print("\n" + "=" * 100)

    return all_results


if __name__ == "__main__":
    results = run_test(max_races=300)
