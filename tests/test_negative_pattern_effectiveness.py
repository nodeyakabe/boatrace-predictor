#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ネガティブパターン有効化テスト

Phase 3 Task 1: ネガティブパターンの効果を検証
- フィーチャーフラグOFF vs ON の比較
- 的中率、スコア調整の影響分析
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag, is_feature_enabled


def test_negative_pattern_effectiveness():
    """
    ネガティブパターン有効化の効果をテスト
    """

    print("=" * 80)
    print("ネガティブパターン有効化テスト")
    print("=" * 80)
    print()

    # データベース接続
    db_path = os.path.join(project_root, 'data', 'boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # テスト対象レース取得（2025年の最新50レース）
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
        LIMIT 50
    """)

    races = cursor.fetchall()
    print(f"テスト対象: {len(races)}レース")
    print()

    # === テスト1: ネガティブパターンOFF（デフォルト） ===
    print("=" * 80)
    print("【テスト1】ネガティブパターンOFF（ベースライン）")
    print("=" * 80)

    set_feature_flag('negative_patterns', False)
    print(f"negative_patterns: {is_feature_enabled('negative_patterns')}")
    print()

    predictor_off = RacePredictor()

    results_off = {
        'total': 0,
        'correct': 0,
        'predictions': []
    }

    for i, (race_id, venue_code, race_date, race_number) in enumerate(races, 1):
        try:
            # 予測実行
            predictions = predictor_off.predict_race(race_id)

            if not predictions:
                continue

            # トップ予測
            top_pred = predictions[0]
            predicted_pit = top_pred.get('pit_number')
            pre_score = top_pred.get('pre_score', top_pred.get('total_score'))

            # 実際の1着
            cursor.execute("SELECT pit_number FROM results WHERE race_id = ? AND rank = 1", (race_id,))
            actual_winner_row = cursor.fetchone()

            if not actual_winner_row:
                continue

            actual_winner = actual_winner_row[0]
            is_correct = (predicted_pit == actual_winner)

            results_off['total'] += 1
            if is_correct:
                results_off['correct'] += 1

            results_off['predictions'].append({
                'race_id': race_id,
                'predicted': predicted_pit,
                'actual': actual_winner,
                'correct': is_correct,
                'score': pre_score
            })

            if i % 10 == 0:
                print(f"  {i}/{len(races)}レース処理完了...")

        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    accuracy_off = results_off['correct'] / results_off['total'] * 100 if results_off['total'] > 0 else 0

    print()
    print(f"結果: {results_off['correct']}/{results_off['total']}レース的中")
    print(f"的中率: {accuracy_off:.2f}%")
    print()

    # === テスト2: ネガティブパターンON ===
    print("=" * 80)
    print("【テスト2】ネガティブパターンON")
    print("=" * 80)

    set_feature_flag('negative_patterns', True)
    print(f"negative_patterns: {is_feature_enabled('negative_patterns')}")
    print()

    predictor_on = RacePredictor()

    results_on = {
        'total': 0,
        'correct': 0,
        'predictions': [],
        'negative_detected': 0,
        'negative_correct': 0,
        'negative_incorrect': 0
    }

    for i, (race_id, venue_code, race_date, race_number) in enumerate(races, 1):
        try:
            # 予測実行
            predictions = predictor_on.predict_race(race_id)

            if not predictions:
                continue

            # トップ予測
            top_pred = predictions[0]
            predicted_pit = top_pred.get('pit_number')
            pre_score = top_pred.get('pre_score', top_pred.get('total_score'))

            # ネガティブパターン検出確認
            has_negative = False
            for pred in predictions:
                if pred.get('has_negative_pattern', False):
                    has_negative = True
                    break

            # 実際の1着
            cursor.execute("SELECT pit_number FROM results WHERE race_id = ? AND rank = 1", (race_id,))
            actual_winner_row = cursor.fetchone()

            if not actual_winner_row:
                continue

            actual_winner = actual_winner_row[0]
            is_correct = (predicted_pit == actual_winner)

            results_on['total'] += 1
            if is_correct:
                results_on['correct'] += 1

            if has_negative:
                results_on['negative_detected'] += 1
                if is_correct:
                    results_on['negative_correct'] += 1
                else:
                    results_on['negative_incorrect'] += 1

            results_on['predictions'].append({
                'race_id': race_id,
                'predicted': predicted_pit,
                'actual': actual_winner,
                'correct': is_correct,
                'score': pre_score,
                'has_negative': has_negative
            })

            if i % 10 == 0:
                print(f"  {i}/{len(races)}レース処理完了...")

        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    accuracy_on = results_on['correct'] / results_on['total'] * 100 if results_on['total'] > 0 else 0

    print()
    print(f"結果: {results_on['correct']}/{results_on['total']}レース的中")
    print(f"的中率: {accuracy_on:.2f}%")
    print(f"ネガティブパターン検出: {results_on['negative_detected']}レース")
    if results_on['negative_detected'] > 0:
        negative_accuracy = results_on['negative_correct'] / results_on['negative_detected'] * 100
        print(f"ネガティブ検出時の的中率: {negative_accuracy:.1f}%")
    print()

    # === 比較分析 ===
    print("=" * 80)
    print("【比較分析】")
    print("=" * 80)
    print()

    print(f"ネガティブパターンOFF: {accuracy_off:.2f}%")
    print(f"ネガティブパターンON:  {accuracy_on:.2f}%")
    print(f"差分: {accuracy_on - accuracy_off:+.2f}pt")
    print()

    # 詳細比較
    print("【詳細】")
    print(f"OFF: {results_off['correct']}/{results_off['total']}レース的中")
    print(f"ON:  {results_on['correct']}/{results_on['total']}レース的中")
    print()

    # レース単位での変化を分析
    changed_predictions = 0
    improved = 0
    worsened = 0

    for i in range(min(len(results_off['predictions']), len(results_on['predictions']))):
        pred_off = results_off['predictions'][i]
        pred_on = results_on['predictions'][i]

        if pred_off['race_id'] == pred_on['race_id']:
            if pred_off['predicted'] != pred_on['predicted']:
                changed_predictions += 1

            if pred_off['correct'] != pred_on['correct']:
                if pred_on['correct'] and not pred_off['correct']:
                    improved += 1
                elif not pred_on['correct'] and pred_off['correct']:
                    worsened += 1

    print("【予測変化の分析】")
    print(f"予測が変化したレース: {changed_predictions}レース")
    print(f"  - 改善（OFF不的中→ON的中）: {improved}レース")
    print(f"  - 悪化（OFF的中→ON不的中）: {worsened}レース")
    print(f"  - 純改善: {improved - worsened}レース")
    print()

    # 推奨事項
    print("=" * 80)
    print("【推奨アクション】")
    print("=" * 80)
    print()

    if accuracy_on > accuracy_off + 2:
        print("✓ ネガティブパターンが効果的に機能しています")
        print("  → フィーチャーフラグを有効化することを推奨")
    elif accuracy_on > accuracy_off:
        print("⚙️ ネガティブパターンは軽微な効果を示しています")
        print("  → A/Bテストでの継続監視を推奨")
    else:
        print("⚠ ネガティブパターンが逆効果になっています")
        print("  → フィーチャーフラグは無効のまま維持することを推奨")

    print()
    print("=" * 80)

    conn.close()

    # フィーチャーフラグを元に戻す
    set_feature_flag('negative_patterns', False)

    return accuracy_on >= accuracy_off


if __name__ == "__main__":
    success = test_negative_pattern_effectiveness()
    sys.exit(0 if success else 1)
