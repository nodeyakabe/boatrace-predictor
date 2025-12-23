# -*- coding: utf-8 -*-
"""
各機能の個別影響調査スクリプト

目的:
- P-1, P-3, P-6-1, P-6-2 のどれがマイナス効果かを特定
- 各機能を個別にON/OFFして比較

検証パターン:
1. 全OFF（ベースライン再現確認）
2. P-1のみON
3. P-3のみON
4. P-6-1のみON
5. P-6-2のみON
"""
import sys
import sqlite3
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import warnings
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# feature_flagsを直接操作するためにインポート
import config.feature_flags as ff
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def set_feature_config(p1=False, p3=False, p6_1=False, p6_2=False):
    """機能フラグを設定"""
    ff.FEATURE_FLAGS['forward_mover_filter'] = p1
    ff.FEATURE_FLAGS['kimarite_flow_prediction'] = p3
    ff.FEATURE_FLAGS['third_place_specialized_scorer'] = p6_1
    ff.FEATURE_FLAGS['makuri_risk_adjustment'] = p6_2


def run_backtest_with_config(db_path, config_name, start_date='2025-01-01', end_date='2025-12-31'):
    """指定設定でバックテスト実行"""
    # RacePredictorを毎回新規作成（フラグ変更を反映するため）
    from src.analysis.race_predictor import RacePredictor

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()
    predictor = RacePredictor(db_path=str(db_path))

    # 対象レース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND EXISTS (SELECT 1 FROM race_details WHERE race_id = r.id)
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
          AND EXISTS (
              SELECT 1 FROM entries
              WHERE race_id = r.id
              GROUP BY race_id
              HAVING COUNT(DISTINCT pit_number) = 6
          )
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (start_date, end_date))
    races = cursor.fetchall()

    stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)

            if not predictions or len(predictions) < 6:
                continue

            confidence = predictions[0].get('confidence', 'D')
            if confidence in ['A', 'B']:
                continue

            top3 = [p['pit_number'] for p in predictions[:3]]
            combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

            cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
            c1 = cursor.fetchone()
            c1_rank = c1['racer_rank'] if c1 else 'B1'

            cursor.execute(
                'SELECT combination, odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                (race_id, combo))
            odds_row = cursor.fetchone()

            if not odds_row:
                continue

            odds = odds_row['odds']

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

            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            results = cursor.fetchall()

            if len(results) >= 3:
                actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

                if combo == actual_combo:
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        actual_payout = (bet_amount / 100) * payout_row['amount']
                        stats['hit'] += 1
                        stats['payout'] += actual_payout

        except Exception:
            continue

    conn.close()

    hit_rate = stats['hit'] / stats['target'] * 100 if stats['target'] > 0 else 0
    roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
    profit = stats['payout'] - stats['bet']

    return {
        'config': config_name,
        'target': stats['target'],
        'hit': stats['hit'],
        'hit_rate': hit_rate,
        'bet': stats['bet'],
        'payout': stats['payout'],
        'profit': profit,
        'roi': roi
    }


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print("=" * 100)
    print("各機能の個別影響調査")
    print("=" * 100)
    print(f"実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 検証パターン定義
    configs = [
        ('全OFF（ベースライン）', False, False, False, False),
        ('P-1のみON', True, False, False, False),
        ('P-3のみON', False, True, False, False),
        ('P-6-1のみON', False, False, True, False),
        ('P-6-2のみON', False, False, False, True),
        ('全ON（改善版）', True, True, True, True),
    ]

    results = []

    for config_name, p1, p3, p6_1, p6_2 in configs:
        print(f"\n[検証中] {config_name}")
        print(f"  P-1={p1}, P-3={p3}, P-6-1={p6_1}, P-6-2={p6_2}")

        set_feature_config(p1, p3, p6_1, p6_2)

        start_time = datetime.now()
        result = run_backtest_with_config(db_path, config_name)
        elapsed = (datetime.now() - start_time).total_seconds()

        results.append(result)

        print(f"  完了: {elapsed/60:.1f}分")
        print(f"  購入={result['target']}, 的中={result['hit']}, "
              f"的中率={result['hit_rate']:.2f}%, ROI={result['roi']:.1f}%, "
              f"収支={result['profit']:+,.0f}円")

    # 結果サマリー
    print("\n" + "=" * 100)
    print("結果サマリー")
    print("=" * 100)
    print(f"\n{'設定':<25} {'購入':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>15}")
    print("-" * 80)

    baseline = results[0]  # 全OFF

    for r in results:
        diff_roi = r['roi'] - baseline['roi']
        diff_profit = r['profit'] - baseline['profit']

        print(f"{r['config']:<25} {r['target']:>8} {r['hit']:>6} "
              f"{r['hit_rate']:>7.2f}% {r['roi']:>9.1f}% {r['profit']:>+14,.0f}円")

    # 差分表示
    print("\n" + "=" * 100)
    print("ベースライン（全OFF）からの差分")
    print("=" * 100)
    print(f"\n{'設定':<25} {'ROI差分':>12} {'収支差分':>15} {'判定':>10}")
    print("-" * 70)

    for r in results[1:]:  # 全OFF以外
        diff_roi = r['roi'] - baseline['roi']
        diff_profit = r['profit'] - baseline['profit']

        if diff_profit > 10000:
            judge = "効果あり"
        elif diff_profit > 0:
            judge = "微増"
        elif diff_profit > -10000:
            judge = "ほぼ変化なし"
        else:
            judge = "マイナス"

        print(f"{r['config']:<25} {diff_roi:>+11.1f}% {diff_profit:>+14,.0f}円 {judge:>10}")

    print("\n" + "=" * 100)
    print(f"実行完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)


if __name__ == "__main__":
    main()
