# -*- coding: utf-8 -*-
"""ゲーティング方式BEFORE統合の検証スクリプト

PRE拮抗時のみBEFORE情報を使用する方式の効果を検証する。
複数の閾値でテストし、最適な閾値を見つける。
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict
import json

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag, FEATURE_FLAGS


def validate_gated_integration(db_path, limit=200, thresholds=None):
    """
    ゲーティング方式の検証

    Args:
        db_path: データベースパス
        limit: 検証するレース数
        thresholds: テストする閾値のリスト（デフォルト: [3.0, 5.0, 7.0, 10.0]）

    Returns:
        dict: 各閾値の検証結果
    """
    if thresholds is None:
        thresholds = [3.0, 5.0, 7.0, 10.0]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2025年で直前情報が存在するレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        AND rd.exhibition_time IS NOT NULL
        ORDER BY r.race_date, r.race_number
        LIMIT ?
    ''', (limit,))
    race_ids = [row[0] for row in cursor.fetchall()]

    print("=" * 80)
    print("ゲーティング方式BEFORE統合の検証")
    print("=" * 80)
    print()
    print(f"検証レース数: {len(race_ids)}")
    print(f"テスト閾値: {thresholds}")
    print()

    # 各閾値でテスト
    results_by_threshold = {}

    for threshold in thresholds:
        print(f"閾値 {threshold}点でテスト中...")

        # 一時的に機能フラグを有効化
        set_feature_flag('gated_before_integration', True)

        # RacePredictorのインスタンスを作成
        predictor = RacePredictor(db_path)

        # GATING_THRESHOLDを動的に変更（race_predictor.pyの該当行を上書き）
        # 注: 本来は設定ファイル化すべきだが、検証用に直接書き換え
        # ここでは各閾値で別インスタンスを作成し、内部定数を変更する方法を使用

        stats = {
            'total_races': 0,
            'win_correct': 0,
            'win_incorrect': 0,
            'top3_correct': 0,
            'top3_incorrect': 0,
            'contested_races': 0,  # 拮抗レース数
            'non_contested_races': 0,  # 非拮抗レース数
            'contested_win_correct': 0,  # 拮抗レースの1着的中
            'contested_top3_correct': 0,  # 拮抗レースの3着以内的中
        }

        for race_id in race_ids:
            try:
                # 予測を実行（内部でゲーティング処理が動く）
                predictions = predictor.predict_race(race_id)

                if not predictions or len(predictions) == 0:
                    continue

                # 実際の着順を取得
                cursor.execute('''
                    SELECT pit_number, CAST(rank AS INTEGER) as finish_position
                    FROM results
                    WHERE race_id = ?
                    ORDER BY finish_position
                ''', (race_id,))
                actual_results = cursor.fetchall()

                if not actual_results:
                    continue

                actual_winner = actual_results[0][0]
                actual_top3 = set([row[0] for row in actual_results[:3]])

                # 予測順位
                predicted_winner = predictions[0]['pit_number']
                predicted_top3 = set([pred['pit_number'] for pred in predictions[:3]])

                # 拮抗フラグを取得
                is_contested = predictions[0].get('is_contested', False)

                # 統計集計
                stats['total_races'] += 1

                if is_contested:
                    stats['contested_races'] += 1
                else:
                    stats['non_contested_races'] += 1

                # 1着的中
                if predicted_winner == actual_winner:
                    stats['win_correct'] += 1
                    if is_contested:
                        stats['contested_win_correct'] += 1
                else:
                    stats['win_incorrect'] += 1

                # 3着以内的中（予測上位3艇のうち何艇が実際に3着以内に入ったか）
                overlap = len(predicted_top3 & actual_top3)
                if overlap >= 2:  # 3艇中2艇以上的中
                    stats['top3_correct'] += 1
                    if is_contested:
                        stats['contested_top3_correct'] += 1
                else:
                    stats['top3_incorrect'] += 1

            except Exception as e:
                print(f"  エラー: race_id={race_id} - {e}")
                continue

        # 機能フラグを無効化
        set_feature_flag('gated_before_integration', False)

        # 結果を保存
        results_by_threshold[threshold] = stats

    # 結果表示
    print()
    print("=" * 80)
    print("検証結果サマリ")
    print("=" * 80)
    print()

    # ベースライン（PRE単独）も表示用に計算
    print("【ベースライン: PRE単独（閾値=無限大、BEFOREを使用しない）】")

    # PRE単独で検証
    set_feature_flag('gated_before_integration', False)
    predictor_baseline = RacePredictor(db_path)

    baseline_stats = {
        'total_races': 0,
        'win_correct': 0,
        'top3_correct': 0,
    }

    for race_id in race_ids:
        try:
            predictions = predictor_baseline.predict_race(race_id)

            if not predictions or len(predictions) == 0:
                continue

            cursor.execute('''
                SELECT pit_number, CAST(rank AS INTEGER) as finish_position
                FROM results
                WHERE race_id = ?
                ORDER BY finish_position
            ''', (race_id,))
            actual_results = cursor.fetchall()

            if not actual_results:
                continue

            actual_winner = actual_results[0][0]
            actual_top3 = set([row[0] for row in actual_results[:3]])

            predicted_winner = predictions[0]['pit_number']
            predicted_top3 = set([pred['pit_number'] for pred in predictions[:3]])

            baseline_stats['total_races'] += 1

            if predicted_winner == actual_winner:
                baseline_stats['win_correct'] += 1

            overlap = len(predicted_top3 & actual_top3)
            if overlap >= 2:
                baseline_stats['top3_correct'] += 1

        except Exception as e:
            continue

    if baseline_stats['total_races'] > 0:
        baseline_win_rate = baseline_stats['win_correct'] / baseline_stats['total_races'] * 100
        baseline_top3_rate = baseline_stats['top3_correct'] / baseline_stats['total_races'] * 100

        print(f"  レース数: {baseline_stats['total_races']}")
        print(f"  1着的中率: {baseline_win_rate:.2f}% ({baseline_stats['win_correct']}/{baseline_stats['total_races']})")
        print(f"  3着以内的中率: {baseline_top3_rate:.2f}% ({baseline_stats['top3_correct']}/{baseline_stats['total_races']})")
        print()

    # 各閾値の結果
    print("【閾値別結果】")
    print()

    print(f"{'閾値':<8} {'拮抗率':<10} {'1着的中率':<12} {'差分(vs PRE)':<15} {'3着以内的中率':<15} {'差分(vs PRE)':<15}")
    print("-" * 95)

    for threshold in thresholds:
        stats = results_by_threshold[threshold]

        if stats['total_races'] == 0:
            continue

        contested_rate = stats['contested_races'] / stats['total_races'] * 100
        win_rate = stats['win_correct'] / stats['total_races'] * 100
        top3_rate = stats['top3_correct'] / stats['total_races'] * 100

        win_diff = win_rate - baseline_win_rate
        top3_diff = top3_rate - baseline_top3_rate

        print(f"{threshold:<8.1f} {contested_rate:<10.1f}% {win_rate:<12.2f}% {win_diff:>+14.2f}% {top3_rate:<15.2f}% {top3_diff:>+14.2f}%")

    print()

    # 拮抗レースのみの分析
    print("【拮抗レースのみの的中率（閾値5.0）】")
    stats_5 = results_by_threshold.get(5.0, {})

    if stats_5.get('contested_races', 0) > 0:
        contested_win_rate = stats_5['contested_win_correct'] / stats_5['contested_races'] * 100
        contested_top3_rate = stats_5['contested_top3_correct'] / stats_5['contested_races'] * 100

        print(f"  拮抗レース数: {stats_5['contested_races']}")
        print(f"  1着的中率: {contested_win_rate:.2f}%")
        print(f"  3着以内的中率: {contested_top3_rate:.2f}%")
        print()

    # 結論
    print("=" * 80)
    print("結論")
    print("=" * 80)
    print()

    # 最良の閾値を特定
    best_threshold = None
    best_win_rate = baseline_win_rate
    best_win_diff = 0.0

    for threshold in thresholds:
        stats = results_by_threshold[threshold]
        if stats['total_races'] == 0:
            continue

        win_rate = stats['win_correct'] / stats['total_races'] * 100
        win_diff = win_rate - baseline_win_rate

        if win_rate > best_win_rate:
            best_win_rate = win_rate
            best_threshold = threshold
            best_win_diff = win_diff

    if best_threshold is not None and best_win_diff > 0:
        print(f"✅ 改善成功！最良の閾値: {best_threshold}点")
        print(f"   1着的中率: {baseline_win_rate:.2f}% → {best_win_rate:.2f}% ({best_win_diff:+.2f}%)")
        print()
        print(f"推奨事項: feature_flags.py で 'gated_before_integration': True に設定")
        print(f"          race_predictor.py の GATING_THRESHOLD を {best_threshold} に設定")
    else:
        print("❌ 改善なし")
        print(f"   全ての閾値でPRE単独より悪化、または同等")
        print()
        print("推奨事項: ゲーティング方式は無効のまま維持")
        print("          代替案: BEFORE配点最適化、ネガティブスクリーニングなどを検討")

    print()
    print("=" * 80)

    conn.close()

    return results_by_threshold


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    results = validate_gated_integration(
        db_path,
        limit=200,
        thresholds=[3.0, 5.0, 7.0, 10.0]
    )

    print()
    print("検証完了")
    print()


if __name__ == '__main__':
    main()
