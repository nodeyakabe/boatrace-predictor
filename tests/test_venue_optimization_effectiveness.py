#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会場別最適化の効果検証A/Bテスト

Phase 3: 会場別パターン最適化の効果を定量的に検証
- フィーチャーフラグOFF（ベースライン）vs ON（会場別最適化）
- 的中率、会場別パフォーマンスを比較
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
from datetime import datetime, timedelta
from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag


def test_venue_optimization_effectiveness(num_races: int = 50):
    """
    会場別最適化の効果をA/Bテスト

    Args:
        num_races: テスト対象レース数
    """

    print("=" * 80)
    print("会場別最適化 効果検証テスト")
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
    # テスト1: 会場別最適化OFF（ベースライン）
    # ===================================================================
    print("=" * 80)
    print("【テスト1】会場別最適化OFF（ベースライン）")
    print("=" * 80)
    set_feature_flag('venue_pattern_optimization', False)
    print(f"venue_pattern_optimization: False")
    print()

    predictor_off = RacePredictor(db_path)
    results_off = []
    venue_stats_off = {}

    for i, (race_id, venue_code, race_date, race_number) in enumerate(test_races, 1):
        try:
            predictions = predictor_off.predict_race(race_id)

            if not predictions:
                continue

            # トップ予測
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

            results_off.append({
                'race_id': race_id,
                'venue_code': venue_code,
                'predicted': predicted_pit,
                'actual': actual_winner,
                'correct': is_correct,
                'multiplier': multiplier
            })

            # 会場別統計
            if venue_code not in venue_stats_off:
                venue_stats_off[venue_code] = {'total': 0, 'correct': 0}
            venue_stats_off[venue_code]['total'] += 1
            if is_correct:
                venue_stats_off[venue_code]['correct'] += 1

            if i % 10 == 0:
                print(f"  {i}/{actual_races}レース処理完了...")

        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    correct_off = sum(1 for r in results_off if r['correct'])
    accuracy_off = correct_off / len(results_off) * 100 if results_off else 0

    print()
    print(f"結果: {correct_off}/{len(results_off)}レース的中")
    print(f"的中率: {accuracy_off:.2f}%")
    print()

    # ===================================================================
    # テスト2: 会場別最適化ON
    # ===================================================================
    print("=" * 80)
    print("【テスト2】会場別最適化ON")
    print("=" * 80)
    set_feature_flag('venue_pattern_optimization', True)
    print(f"venue_pattern_optimization: True")
    print()

    predictor_on = RacePredictor(db_path)
    results_on = []
    venue_stats_on = {}

    for i, (race_id, venue_code, race_date, race_number) in enumerate(test_races, 1):
        try:
            predictions = predictor_on.predict_race(race_id)

            if not predictions:
                continue

            # トップ予測
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

            results_on.append({
                'race_id': race_id,
                'venue_code': venue_code,
                'predicted': predicted_pit,
                'actual': actual_winner,
                'correct': is_correct,
                'multiplier': multiplier
            })

            # 会場別統計
            if venue_code not in venue_stats_on:
                venue_stats_on[venue_code] = {'total': 0, 'correct': 0}
            venue_stats_on[venue_code]['total'] += 1
            if is_correct:
                venue_stats_on[venue_code]['correct'] += 1

            if i % 10 == 0:
                print(f"  {i}/{actual_races}レース処理完了...")

        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    correct_on = sum(1 for r in results_on if r['correct'])
    accuracy_on = correct_on / len(results_on) * 100 if results_on else 0

    print()
    print(f"結果: {correct_on}/{len(results_on)}レース的中")
    print(f"的中率: {accuracy_on:.2f}%")
    print()

    # ===================================================================
    # 比較分析
    # ===================================================================
    print("=" * 80)
    print("【比較分析】")
    print("=" * 80)
    print()

    diff = accuracy_on - accuracy_off
    improvement = correct_on - correct_off

    print(f"会場別最適化OFF: {accuracy_off:.2f}%")
    print(f"会場別最適化ON:  {accuracy_on:.2f}%")
    print(f"差分: {diff:+.2f}pt")
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

    # 会場別パフォーマンス比較（サンプル数が多い会場のみ）
    print("【会場別パフォーマンス比較】（5レース以上）")
    print()

    venue_comparison = []
    for venue_code in set(list(venue_stats_off.keys()) + list(venue_stats_on.keys())):
        stats_off = venue_stats_off.get(venue_code, {'total': 0, 'correct': 0})
        stats_on = venue_stats_on.get(venue_code, {'total': 0, 'correct': 0})

        if stats_off['total'] >= 5 or stats_on['total'] >= 5:
            acc_off = stats_off['correct'] / stats_off['total'] * 100 if stats_off['total'] > 0 else 0
            acc_on = stats_on['correct'] / stats_on['total'] * 100 if stats_on['total'] > 0 else 0
            diff_venue = acc_on - acc_off

            venue_comparison.append({
                'venue_code': venue_code,
                'acc_off': acc_off,
                'acc_on': acc_on,
                'diff': diff_venue,
                'total': max(stats_off['total'], stats_on['total'])
            })

    # 差分の大きい順にソート
    venue_comparison.sort(key=lambda x: abs(x['diff']), reverse=True)

    for vc in venue_comparison[:10]:  # トップ10表示
        venue_code = vc['venue_code']
        acc_off = vc['acc_off']
        acc_on = vc['acc_on']
        diff_venue = vc['diff']
        total = vc['total']

        icon = "📈" if diff_venue > 0 else "📉" if diff_venue < 0 else "➡️"
        # venue_codeが文字列の場合に対応
        venue_str = str(venue_code).zfill(2) if isinstance(venue_code, int) else str(venue_code)
        print(f"{icon} 会場{venue_str}: {acc_off:5.1f}% → {acc_on:5.1f}% ({diff_venue:+5.1f}pt) [{total}レース]")

    print()

    # ===================================================================
    # 推奨アクション
    # ===================================================================
    print("=" * 80)
    print("【推奨アクション】")
    print("=" * 80)
    print()

    if diff > 1.0:
        print("✓ 会場別最適化が効果的に機能しています")
        print("  → フィーチャーフラグを有効化することを推奨")
    elif diff > 0:
        print("△ 会場別最適化に一定の効果が見られます")
        print("  → さらなるデータで検証後、有効化を検討")
    else:
        print("✗ 会場別最適化の効果が確認できませんでした")
        print("  → フィーチャーフラグは無効のまま維持")

    print()
    print("=" * 80)

    conn.close()

    # フラグをリセット
    set_feature_flag('venue_pattern_optimization', False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='会場別最適化の効果検証')
    parser.add_argument('--races', type=int, default=50,
                        help='テスト対象レース数（デフォルト: 50）')

    args = parser.parse_args()

    test_venue_optimization_effectiveness(num_races=args.races)
