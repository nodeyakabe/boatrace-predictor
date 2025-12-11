#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
複合パターンボーナスの効果検証A/Bテスト

Phase 3: 複数パターンマッチ時の相乗効果を検証
- フィーチャーフラグOFF（単一パターン選択）vs ON（複合ボーナス）
- 的中率、倍率向上効果を比較
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


def test_compound_pattern_effectiveness(num_races: int = 50):
    """
    複合パターンボーナスの効果をA/Bテスト

    Args:
        num_races: テスト対象レース数
    """

    print("=" * 80)
    print("複合パターンボーナス 効果検証テスト")
    print("=" * 80)
    print()
    print(f"テスト対象: {num_races}レース")
    print()

    # データベース接続
    db_path = os.path.join(project_root, 'data', 'boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # テスト対象レースを取得（2025年の最新データ）
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01'
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

    test_races = cursor.fetchall()
    actual_races = len(test_races)

    if actual_races < num_races:
        print(f"⚠️ 警告: 対象レースが{actual_races}件のみ（目標: {num_races}件）")
        print()

    # ===================================================================
    # テスト1: 複合パターンボーナスOFF（ベースライン）
    # ===================================================================
    print("=" * 80)
    print("【テスト1】複合パターンボーナスOFF（ベースライン）")
    print("=" * 80)
    set_feature_flag('compound_pattern_bonus', False)
    print(f"compound_pattern_bonus: False")
    print()

    predictor_off = RacePredictor(db_path)
    results_off = []
    multi_pattern_count_off = 0

    for i, (race_id, venue_code, race_date, race_number) in enumerate(test_races, 1):
        try:
            predictions = predictor_off.predict_race(race_id)

            if not predictions:
                continue

            # トップ予測
            top_pred = predictions[0]
            predicted_pit = top_pred.get('pit_number')
            multiplier = top_pred.get('pattern_multiplier', 1.0)
            matched_patterns = top_pred.get('matched_patterns', [])

            if len(matched_patterns) > 1:
                multi_pattern_count_off += 1

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

            results_off.append({
                'race_id': race_id,
                'predicted': predicted_pit,
                'actual': actual_winner,
                'correct': is_correct,
                'multiplier': multiplier,
                'pattern_count': len(matched_patterns)
            })

            if i % 10 == 0:
                print(f"  {i}/{actual_races}レース処理完了...")

        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    correct_off = sum(1 for r in results_off if r['correct'])
    accuracy_off = correct_off / len(results_off) * 100 if results_off else 0
    avg_multiplier_off = sum(r['multiplier'] for r in results_off) / len(results_off) if results_off else 0

    print()
    print(f"結果: {correct_off}/{len(results_off)}レース的中")
    print(f"的中率: {accuracy_off:.2f}%")
    print(f"平均倍率: {avg_multiplier_off:.3f}")
    print(f"複数パターンマッチ: {multi_pattern_count_off}レース")
    print()

    # ===================================================================
    # テスト2: 複合パターンボーナスON
    # ===================================================================
    print("=" * 80)
    print("【テスト2】複合パターンボーナスON")
    print("=" * 80)
    set_feature_flag('compound_pattern_bonus', True)
    print(f"compound_pattern_bonus: True")
    print()

    predictor_on = RacePredictor(db_path)
    results_on = []
    multi_pattern_count_on = 0
    compound_bonus_applied = 0

    for i, (race_id, venue_code, race_date, race_number) in enumerate(test_races, 1):
        try:
            predictions = predictor_on.predict_race(race_id)

            if not predictions:
                continue

            # トップ予測
            top_pred = predictions[0]
            predicted_pit = top_pred.get('pit_number')
            multiplier = top_pred.get('pattern_multiplier', 1.0)
            matched_patterns = top_pred.get('matched_patterns', [])
            selected_pattern = top_pred.get('selected_pattern', '')

            if len(matched_patterns) > 1:
                multi_pattern_count_on += 1
                if '+' in selected_pattern:  # 複合ボーナス適用の印
                    compound_bonus_applied += 1

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

            results_on.append({
                'race_id': race_id,
                'predicted': predicted_pit,
                'actual': actual_winner,
                'correct': is_correct,
                'multiplier': multiplier,
                'pattern_count': len(matched_patterns)
            })

            if i % 10 == 0:
                print(f"  {i}/{actual_races}レース処理完了...")

        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    correct_on = sum(1 for r in results_on if r['correct'])
    accuracy_on = correct_on / len(results_on) * 100 if results_on else 0
    avg_multiplier_on = sum(r['multiplier'] for r in results_on) / len(results_on) if results_on else 0

    print()
    print(f"結果: {correct_on}/{len(results_on)}レース的中")
    print(f"的中率: {accuracy_on:.2f}%")
    print(f"平均倍率: {avg_multiplier_on:.3f}")
    print(f"複数パターンマッチ: {multi_pattern_count_on}レース")
    print(f"複合ボーナス適用: {compound_bonus_applied}レース")
    print()

    # ===================================================================
    # 比較分析
    # ===================================================================
    print("=" * 80)
    print("【比較分析】")
    print("=" * 80)
    print()

    diff_accuracy = accuracy_on - accuracy_off
    diff_multiplier = avg_multiplier_on - avg_multiplier_off
    improvement = correct_on - correct_off

    print(f"複合ボーナスOFF: {accuracy_off:.2f}% | 平均倍率{avg_multiplier_off:.3f}")
    print(f"複合ボーナスON:  {accuracy_on:.2f}% | 平均倍率{avg_multiplier_on:.3f}")
    print(f"差分: {diff_accuracy:+.2f}pt | 倍率{diff_multiplier:+.3f}")
    print()

    print("【詳細】")
    print(f"OFF: {correct_off}/{len(results_off)}レース的中")
    print(f"ON:  {correct_on}/{len(results_on)}レース的中")
    print()

    # 予測変化の分析
    prediction_changes = 0
    improved_predictions = 0
    worsened_predictions = 0

    for i in range(min(len(results_off), len(results_on))):
        if results_off[i]['predicted'] != results_on[i]['predicted']:
            prediction_changes += 1

            # OFF不的中 → ON的中
            if not results_off[i]['correct'] and results_on[i]['correct']:
                improved_predictions += 1
            # OFF的中 → ON不的中
            elif results_off[i]['correct'] and not results_on[i]['correct']:
                worsened_predictions += 1

    print("【予測変化の分析】")
    print(f"予測が変化したレース: {prediction_changes}レース")
    print(f"  - 改善（OFF不的中→ON的中）: {improved_predictions}レース")
    print(f"  - 悪化（OFF的中→ON不的中）: {worsened_predictions}レース")
    print(f"  - 純改善: {improved_predictions - worsened_predictions}レース")
    print()

    # 複数パターンマッチレースの分析
    multi_pattern_results_off = [r for r in results_off if r['pattern_count'] > 1]
    multi_pattern_results_on = [r for r in results_on if r['pattern_count'] > 1]

    if multi_pattern_results_off and multi_pattern_results_on:
        multi_correct_off = sum(1 for r in multi_pattern_results_off if r['correct'])
        multi_correct_on = sum(1 for r in multi_pattern_results_on if r['correct'])
        multi_acc_off = multi_correct_off / len(multi_pattern_results_off) * 100
        multi_acc_on = multi_correct_on / len(multi_pattern_results_on) * 100

        print("【複数パターンマッチレースのみ】")
        print(f"OFF: {multi_acc_off:.1f}% ({multi_correct_off}/{len(multi_pattern_results_off)})")
        print(f"ON:  {multi_acc_on:.1f}% ({multi_correct_on}/{len(multi_pattern_results_on)})")
        print(f"差分: {multi_acc_on - multi_acc_off:+.1f}pt")
        print()

    # ===================================================================
    # 推奨アクション
    # ===================================================================
    print("=" * 80)
    print("【推奨アクション】")
    print("=" * 80)
    print()

    if diff_accuracy > 1.0:
        print("✓ 複合パターンボーナスが効果的に機能しています")
        print("  → フィーチャーフラグを有効化することを推奨")
    elif diff_accuracy > 0:
        print("△ 複合パターンボーナスに一定の効果が見られます")
        print("  → さらなるデータで検証後、有効化を検討")
    else:
        print("✗ 複合パターンボーナスの効果が確認できませんでした")
        print("  → フィーチャーフラグは無効のまま維持")

    # 倍率の変化についても言及
    if diff_multiplier > 0.01:
        print()
        print(f"ℹ️ 平均倍率が{diff_multiplier:+.3f}向上しています")
        print("  → 期待値（ROI）の改善が見込まれます")

    print()
    print("=" * 80)

    conn.close()

    # フラグをリセット
    set_feature_flag('compound_pattern_bonus', False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='複合パターンボーナスの効果検証')
    parser.add_argument('--races', type=int, default=50,
                        help='テスト対象レース数（デフォルト: 50）')

    args = parser.parse_args()

    test_compound_pattern_effectiveness(num_races=args.races)
