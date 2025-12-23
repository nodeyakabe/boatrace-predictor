"""
モンテカルロシミュレーション（アプローチ5）のバックテストスクリプト

評価期間: 2025-11-28 〜 2025-12-10（607レース）
評価指標: ROI、1着・2着・3着的中率、3連単的中率、購入数、実行時間

使用方法:
    python scripts/test_monte_carlo_simulation.py
"""

import sys
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
import numpy as np
from typing import Dict, List, Tuple
from collections import defaultdict

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import enable_feature, disable_feature, is_feature_enabled


def get_test_races(db_path: str, start_date: str, end_date: str) -> List[Dict]:
    """テスト対象レースを取得"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 6艇のレースのみを対象（データ品質チェック）
    cursor.execute("""
        SELECT
            r.id, r.race_date, r.venue_code, r.race_number, r.race_grade,
            rc.wind_speed, rc.wave_height, rc.wind_direction
        FROM races r
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date BETWEEN ? AND ?
        AND EXISTS (
            SELECT 1 FROM results res
            WHERE res.race_id = r.id
        )
        AND (SELECT COUNT(*) FROM entries e WHERE e.race_id = r.id) = 6
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, (start_date, end_date))

    races = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    return races


def get_race_result(db_path: str, race_id: int) -> Dict:
    """レース結果を取得"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 確定着順を取得（rankは'1','2'...や'1着'など文字列の可能性がある）
    cursor.execute("""
        SELECT pit_number, rank
        FROM results
        WHERE race_id = ?
        AND is_invalid = 0
        ORDER BY
            CASE
                WHEN rank LIKE '%1%' THEN 1
                WHEN rank LIKE '%2%' THEN 2
                WHEN rank LIKE '%3%' THEN 3
                WHEN rank LIKE '%4%' THEN 4
                WHEN rank LIKE '%5%' THEN 5
                WHEN rank LIKE '%6%' THEN 6
                ELSE 7
            END
    """, (race_id,))

    results = cursor.fetchall()
    result_dict = {}

    if results:
        for i, row in enumerate(results):
            # rankを数値に変換
            rank_str = str(row['rank'])
            try:
                # "1", "1着", "1位" などから数値を抽出
                rank_num = int(''.join(c for c in rank_str if c.isdigit())[:1])
            except (ValueError, IndexError):
                rank_num = i + 1  # フォールバック

            result_dict[rank_num] = row['pit_number']

    # 三連単配当を取得
    cursor.execute("""
        SELECT combination, amount
        FROM payouts
        WHERE race_id = ? AND bet_type = '3連単'
        LIMIT 1
    """, (race_id,))

    payout_row = cursor.fetchone()
    if payout_row and payout_row['amount']:
        result_dict['trifecta_payout'] = payout_row['amount']
        # combination は "1-2-3" 形式
        try:
            parts = payout_row['combination'].split('-')
            if len(parts) == 3:
                result_dict['trifecta'] = (
                    int(parts[0]),
                    int(parts[1]),
                    int(parts[2])
                )
        except (ValueError, AttributeError):
            pass

    cursor.close()
    conn.close()

    return result_dict


def run_backtest(
    predictor: RacePredictor,
    races: List[Dict],
    db_path: str,
    label: str = "baseline"
) -> Dict:
    """バックテストを実行"""

    results = {
        'label': label,
        'total_races': 0,
        'purchased_races': 0,
        'total_bet': 0,
        'total_payout': 0,
        '1st_correct': 0,
        '2nd_correct': 0,
        '3rd_correct': 0,
        'trifecta_correct': 0,
        'execution_times': [],
        'confidence_stats': defaultdict(lambda: {'count': 0, 'correct': 0}),
    }

    for race in races:
        race_id = race['id']

        try:
            # 予測実行（時間計測）
            start_time = time.time()
            predictions = predictor.predict_race(race_id)
            execution_time = (time.time() - start_time) * 1000  # ミリ秒
            results['execution_times'].append(execution_time)

            if not predictions or len(predictions) < 3:
                continue

            results['total_races'] += 1

            # 信頼度を取得
            top_confidence = predictions[0]['confidence']

            # 信頼度B, C のみ購入（現行戦略と同じ）
            if top_confidence not in ['B', 'C']:
                continue

            results['purchased_races'] += 1
            results['total_bet'] += 100  # 100円ベット

            # 実際の結果
            actual_result = get_race_result(db_path, race_id)

            if not actual_result or 1 not in actual_result:
                continue

            # 予測順位
            pred_1st = predictions[0]['pit_number']
            pred_2nd = predictions[1]['pit_number']
            pred_3rd = predictions[2]['pit_number']

            # 実際の順位
            actual_1st = actual_result.get(1)
            actual_2nd = actual_result.get(2)
            actual_3rd = actual_result.get(3)

            # 的中判定
            is_1st_correct = pred_1st == actual_1st
            is_2nd_correct = pred_2nd == actual_2nd
            is_3rd_correct = pred_3rd == actual_3rd

            if is_1st_correct:
                results['1st_correct'] += 1
            if is_2nd_correct:
                results['2nd_correct'] += 1
            if is_3rd_correct:
                results['3rd_correct'] += 1

            # 三連単的中判定
            if is_1st_correct and is_2nd_correct and is_3rd_correct:
                results['trifecta_correct'] += 1
                if 'trifecta_payout' in actual_result:
                    results['total_payout'] += actual_result['trifecta_payout']

            # 信頼度別統計
            results['confidence_stats'][top_confidence]['count'] += 1
            if is_1st_correct and is_2nd_correct and is_3rd_correct:
                results['confidence_stats'][top_confidence]['correct'] += 1

        except Exception as e:
            print(f"  Race {race_id} error: {e}")
            continue

    # 統計計算
    if results['purchased_races'] > 0:
        results['roi'] = (results['total_payout'] / results['total_bet']) * 100
        results['1st_accuracy'] = (results['1st_correct'] / results['purchased_races']) * 100
        results['2nd_accuracy'] = (results['2nd_correct'] / results['purchased_races']) * 100
        results['3rd_accuracy'] = (results['3rd_correct'] / results['purchased_races']) * 100
        results['trifecta_accuracy'] = (results['trifecta_correct'] / results['purchased_races']) * 100
    else:
        results['roi'] = 0
        results['1st_accuracy'] = 0
        results['2nd_accuracy'] = 0
        results['3rd_accuracy'] = 0
        results['trifecta_accuracy'] = 0

    if results['execution_times']:
        results['avg_execution_time'] = np.mean(results['execution_times'])
        results['max_execution_time'] = np.max(results['execution_times'])
    else:
        results['avg_execution_time'] = 0
        results['max_execution_time'] = 0

    return results


def compare_results(baseline: Dict, test: Dict) -> Dict:
    """結果を比較"""
    comparison = {
        'roi_diff': test['roi'] - baseline['roi'],
        '1st_diff': test['1st_accuracy'] - baseline['1st_accuracy'],
        '2nd_diff': test['2nd_accuracy'] - baseline['2nd_accuracy'],
        '3rd_diff': test['3rd_accuracy'] - baseline['3rd_accuracy'],
        'trifecta_diff': test['trifecta_accuracy'] - baseline['trifecta_accuracy'],
        'time_diff': test['avg_execution_time'] - baseline['avg_execution_time'],
        'purchase_diff': test['purchased_races'] - baseline['purchased_races'],
    }
    return comparison


def print_results(results: Dict):
    """結果を表示"""
    print(f"\n=== {results['label']} ===")
    print(f"総レース数: {results['total_races']}")
    print(f"購入レース数: {results['purchased_races']}")
    print(f"ROI: {results['roi']:.1f}%")
    print(f"1着的中率: {results['1st_accuracy']:.1f}%")
    print(f"2着的中率: {results['2nd_accuracy']:.1f}%")
    print(f"3着的中率: {results['3rd_accuracy']:.1f}%")
    print(f"三連単的中率: {results['trifecta_accuracy']:.2f}%")
    print(f"的中数: {results['trifecta_correct']}")
    print(f"平均実行時間: {results['avg_execution_time']:.1f}ms")
    print(f"最大実行時間: {results['max_execution_time']:.1f}ms")

    print("\n信頼度別:")
    for conf in ['B', 'C', 'D']:
        stats = results['confidence_stats'].get(conf, {'count': 0, 'correct': 0})
        if stats['count'] > 0:
            rate = (stats['correct'] / stats['count']) * 100
            print(f"  {conf}: {stats['count']}件, 的中{stats['correct']}件 ({rate:.2f}%)")


def print_comparison(comparison: Dict):
    """比較結果を表示"""
    print("\n=== 比較結果 ===")
    print(f"ROI変化: {comparison['roi_diff']:+.1f}pt")
    print(f"1着的中率変化: {comparison['1st_diff']:+.1f}pt")
    print(f"2着的中率変化: {comparison['2nd_diff']:+.1f}pt")
    print(f"3着的中率変化: {comparison['3rd_diff']:+.1f}pt")
    print(f"三連単的中率変化: {comparison['trifecta_diff']:+.2f}pt")
    print(f"実行時間変化: {comparison['time_diff']:+.1f}ms")
    print(f"購入数変化: {comparison['purchase_diff']:+d}件")

    # 評価
    print("\n=== 評価 ===")
    if comparison['roi_diff'] >= 0:
        print("[OK] ROI維持または向上")
    else:
        print("[NG] ROI低下")

    if comparison['2nd_diff'] >= 3.0 or comparison['3rd_diff'] >= 3.0:
        print("[OK] 2着・3着的中率が+3pt以上向上")
    elif comparison['2nd_diff'] >= 0 or comparison['3rd_diff'] >= 0:
        print("[WARN] 2着・3着的中率は向上したが+3pt未満")
    else:
        print("[NG] 2着・3着的中率低下")

    if comparison['time_diff'] < 10000:  # 10秒未満
        print("[OK] 実行時間は実用的")
    else:
        print("[WARN] 実行時間が10秒を超える")


def main():
    """メイン実行"""
    print("=" * 70)
    print("モンテカルロシミュレーション（アプローチ5）バックテスト")
    print("=" * 70)

    # 設定
    db_path = "data/boatrace.db"
    start_date = "2025-11-28"
    end_date = "2025-12-10"

    print(f"\n期間: {start_date} 〜 {end_date}")

    # テスト対象レースを取得
    races = get_test_races(db_path, start_date, end_date)
    print(f"対象レース数: {len(races)}")

    if not races:
        print("テスト対象レースがありません")
        return

    # === ベースライン（モンテカルロなし） ===
    print("\n" + "=" * 50)
    print("ベースライン評価中...")
    disable_feature('monte_carlo_simulation')

    predictor_baseline = RacePredictor(db_path=db_path, use_cache=False)
    baseline_results = run_backtest(
        predictor_baseline, races, db_path,
        label="Baseline (without Monte Carlo)"
    )
    print_results(baseline_results)

    # === モンテカルロあり ===
    print("\n" + "=" * 50)
    print("モンテカルロシミュレーション評価中...")
    enable_feature('monte_carlo_simulation')

    predictor_mc = RacePredictor(db_path=db_path, use_cache=False)
    mc_results = run_backtest(
        predictor_mc, races, db_path,
        label="With Monte Carlo Simulation"
    )
    print_results(mc_results)

    # === 比較 ===
    comparison = compare_results(baseline_results, mc_results)
    print_comparison(comparison)

    # フラグを戻す
    disable_feature('monte_carlo_simulation')

    # 結果サマリーを返す
    return {
        'baseline': baseline_results,
        'monte_carlo': mc_results,
        'comparison': comparison
    }


def test_simulation_speed():
    """シミュレーション速度のテスト"""
    print("\n" + "=" * 70)
    print("シミュレーション速度テスト")
    print("=" * 70)

    from src.simulation.race_simulator import MonteCarloRaceSimulator
    from src.simulation.race_physics import RacePhysicsModel

    # テスト用の予測データ
    test_predictions = [
        {'pit_number': 1, 'total_score': 80.0, 'motor_score': 15.0, 'racer_rank': 'A1'},
        {'pit_number': 2, 'total_score': 70.0, 'motor_score': 12.0, 'racer_rank': 'A2'},
        {'pit_number': 3, 'total_score': 65.0, 'motor_score': 10.0, 'racer_rank': 'B1'},
        {'pit_number': 4, 'total_score': 60.0, 'motor_score': 8.0, 'racer_rank': 'B1'},
        {'pit_number': 5, 'total_score': 55.0, 'motor_score': 6.0, 'racer_rank': 'B2'},
        {'pit_number': 6, 'total_score': 50.0, 'motor_score': 5.0, 'racer_rank': 'B2'},
    ]

    # シミュレーション回数別の速度テスト
    n_simulations_list = [1000, 5000, 10000, 50000]

    for n_sims in n_simulations_list:
        simulator = MonteCarloRaceSimulator(n_simulations=n_sims)

        start_time = time.time()
        result = simulator.simulate_race(test_predictions)
        elapsed = (time.time() - start_time) * 1000

        print(f"\nシミュレーション回数: {n_sims}")
        print(f"  実行時間: {elapsed:.1f}ms")
        print(f"  1着確率分布: {result.win_probs}")


if __name__ == "__main__":
    # 速度テスト
    test_simulation_speed()

    # メインバックテスト
    results = main()
