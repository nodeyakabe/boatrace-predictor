#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最適化パターン倍率の効果検証A/Bテスト

200レースの実績データに基づいて最適化された倍率を検証
- デフォルト倍率 vs 最適化倍率
- 的中率への影響を測定
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag


def test_optimized_multipliers_effectiveness(num_races: int = 100):
    """
    最適化パターン倍率の効果をA/Bテスト

    Args:
        num_races: テスト対象レース数
    """

    print("=" * 80)
    print("最適化パターン倍率 効果検証テスト")
    print("=" * 80)
    print()
    print(f"テスト対象: {num_races}レース")
    print()

    # データベース接続
    db_path = os.path.join(project_root, 'data', 'boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # テスト対象レースを取得（分析に使用した200レースとは別のデータを使用）
    cursor.execute("""
        SELECT r.id
        FROM races r
        WHERE r.race_date >= '2024-12-01' AND r.race_date < '2025-01-01'
          AND EXISTS (
              SELECT 1 FROM results res
              WHERE res.race_id = r.id AND res.rank = 1
          )
          AND EXISTS (
              SELECT 1 FROM race_details rd
              WHERE rd.race_id = r.id
                AND rd.exhibition_time IS NOT NULL
                AND rd.st_time IS NOT NULL
          )
        ORDER BY r.race_date DESC, r.race_number DESC
        LIMIT ?
    """, (num_races,))

    test_races = [row[0] for row in cursor.fetchall()]
    actual_races = len(test_races)

    if actual_races < num_races:
        print(f"⚠️ 警告: 対象レースが{actual_races}件のみ（目標: {num_races}件）")
        print()

    # ===================================================================
    # テスト1: デフォルト倍率
    # ===================================================================
    print("=" * 80)
    print("【テスト1】デフォルト倍率")
    print("=" * 80)
    set_feature_flag('optimized_pattern_multipliers', False)
    print(f"optimized_pattern_multipliers: False")
    print()

    predictor_default = RacePredictor(db_path)
    results_default = []

    for i, race_id in enumerate(test_races, 1):
        try:
            predictions = predictor_default.predict_race(race_id)

            if not predictions:
                continue

            top_pred = predictions[0]
            predicted_pit = top_pred.get('pit_number')
            multiplier = top_pred.get('pattern_multiplier', 1.0)

            # 実際の1着
            cursor.execute("""
                SELECT pit_number FROM results
                WHERE race_id = ? AND rank = 1
            """, (race_id,))
            actual_row = cursor.fetchone()

            if not actual_row:
                continue

            actual_winner = actual_row[0]
            is_correct = (predicted_pit == actual_winner)

            results_default.append({
                'race_id': race_id,
                'predicted': predicted_pit,
                'actual': actual_winner,
                'correct': is_correct,
                'multiplier': multiplier
            })

            if i % 25 == 0:
                print(f"  {i}/{actual_races}レース処理完了...")

        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    correct_default = sum(1 for r in results_default if r['correct'])
    accuracy_default = correct_default / len(results_default) * 100 if results_default else 0
    avg_mult_default = sum(r['multiplier'] for r in results_default) / len(results_default) if results_default else 0

    print()
    print(f"結果: {correct_default}/{len(results_default)}レース的中")
    print(f"的中率: {accuracy_default:.2f}%")
    print(f"平均倍率: {avg_mult_default:.3f}")
    print()

    # ===================================================================
    # テスト2: 最適化倍率
    # ===================================================================
    print("=" * 80)
    print("【テスト2】最適化倍率")
    print("=" * 80)
    set_feature_flag('optimized_pattern_multipliers', True)
    print(f"optimized_pattern_multipliers: True")
    print()

    predictor_optimized = RacePredictor(db_path)
    results_optimized = []

    for i, race_id in enumerate(test_races, 1):
        try:
            predictions = predictor_optimized.predict_race(race_id)

            if not predictions:
                continue

            top_pred = predictions[0]
            predicted_pit = top_pred.get('pit_number')
            multiplier = top_pred.get('pattern_multiplier', 1.0)

            # 実際の1着
            cursor.execute("""
                SELECT pit_number FROM results
                WHERE race_id = ? AND rank = 1
            """, (race_id,))
            actual_row = cursor.fetchone()

            if not actual_row:
                continue

            actual_winner = actual_row[0]
            is_correct = (predicted_pit == actual_winner)

            results_optimized.append({
                'race_id': race_id,
                'predicted': predicted_pit,
                'actual': actual_winner,
                'correct': is_correct,
                'multiplier': multiplier
            })

            if i % 25 == 0:
                print(f"  {i}/{actual_races}レース処理完了...")

        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    correct_optimized = sum(1 for r in results_optimized if r['correct'])
    accuracy_optimized = correct_optimized / len(results_optimized) * 100 if results_optimized else 0
    avg_mult_optimized = sum(r['multiplier'] for r in results_optimized) / len(results_optimized) if results_optimized else 0

    print()
    print(f"結果: {correct_optimized}/{len(results_optimized)}レース的中")
    print(f"的中率: {accuracy_optimized:.2f}%")
    print(f"平均倍率: {avg_mult_optimized:.3f}")
    print()

    # ===================================================================
    # 比較分析
    # ===================================================================
    print("=" * 80)
    print("【比較分析】")
    print("=" * 80)
    print()

    diff_accuracy = accuracy_optimized - accuracy_default
    diff_multiplier = avg_mult_optimized - avg_mult_default
    improvement = correct_optimized - correct_default

    print(f"デフォルト倍率: {accuracy_default:.2f}% | 平均倍率{avg_mult_default:.3f}")
    print(f"最適化倍率:     {accuracy_optimized:.2f}% | 平均倍率{avg_mult_optimized:.3f}")
    print(f"差分:           {diff_accuracy:+.2f}pt | 倍率{diff_multiplier:+.3f}")
    print()

    # 予測変化の分析
    prediction_changes = 0
    improved_predictions = 0
    worsened_predictions = 0

    for i in range(min(len(results_default), len(results_optimized))):
        if results_default[i]['predicted'] != results_optimized[i]['predicted']:
            prediction_changes += 1

            if not results_default[i]['correct'] and results_optimized[i]['correct']:
                improved_predictions += 1
            elif results_default[i]['correct'] and not results_optimized[i]['correct']:
                worsened_predictions += 1

    print("【予測変化の分析】")
    print(f"予測が変化したレース: {prediction_changes}レース")
    print(f"  - 改善（デフォルト不的中→最適化的中）: {improved_predictions}レース")
    print(f"  - 悪化（デフォルト的中→最適化不的中）: {worsened_predictions}レース")
    print(f"  - 純改善: {improved_predictions - worsened_predictions}レース")
    print()

    # ===================================================================
    # 推奨アクション
    # ===================================================================
    print("=" * 80)
    print("【推奨アクション】")
    print("=" * 80)
    print()

    if diff_accuracy > 1.0:
        print("✓ 最適化パターン倍率が効果的に機能しています")
        print("  → フィーチャーフラグを有効化することを強く推奨")
    elif diff_accuracy > 0:
        print("△ 最適化パターン倍率に一定の効果が見られます")
        print("  → フィーチャーフラグを有効化することを推奨")
    else:
        print("✗ 最適化パターン倍率の効果が確認できませんでした")
        print("  → フィーチャーフラグは無効のまま維持")

    print()
    print("=" * 80)

    conn.close()

    # フラグをリセット
    set_feature_flag('optimized_pattern_multipliers', False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='最適化パターン倍率の効果検証')
    parser.add_argument('--races', type=int, default=100,
                        help='テスト対象レース数（デフォルト: 100）')

    args = parser.parse_args()

    test_optimized_multipliers_effectiveness(num_races=args.races)
