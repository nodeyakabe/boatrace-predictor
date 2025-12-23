# -*- coding: utf-8 -*-
"""
前付けレース × オッズ帯フィルターのシミュレーション

20-30倍帯の前付けレースを除外したら収益改善するか？
"""
import sys
import sqlite3
import io
import json
from pathlib import Path
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config.feature_flags as ff
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def load_forward_movers():
    path = ROOT_DIR / "config" / "forward_movers.json"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(str(rn) for rn in data.get('racer_numbers', []))
    except:
        return set()


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    forward_movers = load_forward_movers()

    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True
    evaluator = BetTargetEvaluator()

    print("=" * 100)
    print("前付けレース × オッズ帯フィルターシミュレーション")
    print("=" * 100)
    print()

    # 2024-2025年データ
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code
        FROM races r
        WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
    ''')
    races = cursor.fetchall()

    # フィルターパターン
    patterns = {
        '現状（フィルターなし）': {'exclude_bands': []},
        '20-30倍帯除外': {'exclude_bands': [(20, 30)]},
        '20-50倍帯除外': {'exclude_bands': [(20, 50)]},
        '30倍未満除外': {'exclude_bands': [(0, 30)]},
    }

    results = {}

    for pattern_name, settings in patterns.items():
        exclude_bands = settings['exclude_bands']
        stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
        excluded_count = 0

        for race in races:
            race_id = race['race_id']
            venue_code = int(race['venue_code']) if race['venue_code'] else 0

            # 前付け常習者チェック
            cursor.execute('SELECT racer_number FROM entries WHERE race_id = ?', (race_id,))
            racer_numbers = [str(row['racer_number']) for row in cursor.fetchall()]
            has_forward = bool(set(racer_numbers) & forward_movers)

            # 予測取得
            cursor.execute('''
                SELECT pit_number, confidence, total_score
                FROM race_predictions
                WHERE race_id = ? AND prediction_type = 'before'
                ORDER BY total_score DESC
            ''', (race_id,))
            preds = cursor.fetchall()

            if len(preds) < 6:
                continue

            confidence = preds[0]['confidence']
            top3 = [p['pit_number'] for p in preds[:3]]
            combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

            # 1コース級別
            cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
            c1 = cursor.fetchone()
            c1_rank = c1['racer_rank'] if c1 else 'B1'

            # オッズ
            cursor.execute(
                'SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                (race_id, combo))
            odds_row = cursor.fetchone()
            if not odds_row:
                continue

            odds = odds_row['odds']

            # 前付けレースでオッズ帯フィルター適用
            if has_forward and exclude_bands:
                should_exclude = False
                for low, high in exclude_bands:
                    if low <= odds < high:
                        should_exclude = True
                        break
                if should_exclude:
                    excluded_count += 1
                    continue

            result = evaluator.evaluate(
                confidence=confidence,
                c1_rank=c1_rank,
                old_combo=combo,
                new_combo=combo,
                old_odds=odds,
                new_odds=odds,
                has_beforeinfo=True,
                venue_code=venue_code
            )

            if result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                continue

            bet_amount = result.bet_amount
            stats['target'] += 1
            stats['bet'] += bet_amount

            # 的中判定
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            actual_results = cursor.fetchall()

            if len(actual_results) >= 3:
                actual_combo = f"{actual_results[0]['pit_number']}-{actual_results[1]['pit_number']}-{actual_results[2]['pit_number']}"

                if combo == actual_combo:
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        payout = (bet_amount / 100) * payout_row['amount']
                        stats['hit'] += 1
                        stats['payout'] += payout

        results[pattern_name] = {
            'stats': stats,
            'excluded': excluded_count
        }

    conn.close()

    # 結果表示
    baseline = results['現状（フィルターなし）']['stats']
    baseline_roi = baseline['payout'] / baseline['bet'] * 100 if baseline['bet'] > 0 else 0
    baseline_profit = baseline['payout'] - baseline['bet']

    print(f"\n{'パターン':<25} {'購入数':>8} {'除外':>6} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>15} {'ROI差':>10}")
    print("-" * 110)

    for pattern_name, data in results.items():
        s = data['stats']
        excluded = data['excluded']
        roi = s['payout'] / s['bet'] * 100 if s['bet'] > 0 else 0
        hit_rate = s['hit'] / s['target'] * 100 if s['target'] > 0 else 0
        profit = s['payout'] - s['bet']
        roi_diff = roi - baseline_roi

        print(f"{pattern_name:<25} {s['target']:>8,} {excluded:>6} {s['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+14,.0f}円 {roi_diff:>+9.1f}pt")

    # 結論
    print()
    print("=" * 100)
    print("結論")
    print("=" * 100)

    best_pattern = max(results.items(), key=lambda x: x[1]['stats']['payout'] / x[1]['stats']['bet'] if x[1]['stats']['bet'] > 0 else 0)
    best_name = best_pattern[0]
    best_roi = best_pattern[1]['stats']['payout'] / best_pattern[1]['stats']['bet'] * 100 if best_pattern[1]['stats']['bet'] > 0 else 0

    if best_name == '現状（フィルターなし）':
        print("\n現状維持が最適。オッズ帯フィルターは不要。")
    else:
        improvement = best_roi - baseline_roi
        print(f"\n【推奨】{best_name}")
        print(f"ROI改善: +{improvement:.1f}pt")


if __name__ == "__main__":
    main()
