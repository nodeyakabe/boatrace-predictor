#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
パターンボーナス効果の可視化

Phase 2: パターン適用状況のビジュアル分析
- 信頼度別パターン適用率のグラフ
- パターン別的中率の比較
- 時系列トレンド分析
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from src.analysis.race_predictor import RacePredictor


def visualize_pattern_effectiveness(days: int = 30):
    """
    パターンボーナス効果を可視化

    Args:
        days: 分析対象期間（日数）
    """

    print("=" * 80)
    print("パターンボーナス効果 可視化レポート")
    print("=" * 80)
    print()

    # データベース接続
    db_path = os.path.join(project_root, 'data', 'boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 分析対象期間
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)

    print(f"分析期間: {start_date} ～ {end_date} ({days}日間)")
    print()

    # 対象レースを取得
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
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
        ORDER BY r.race_date, r.race_number
        LIMIT 500
    """, (start_date, end_date))

    races = cursor.fetchall()
    print(f"対象レース数: {len(races)}レース")
    print()

    # 予測器初期化
    predictor = RacePredictor()

    # データ収集
    confidence_data = {
        'A': {'total': 0, 'pattern_applied': 0, 'correct': 0, 'correct_with_pattern': 0},
        'B': {'total': 0, 'pattern_applied': 0, 'correct': 0, 'correct_with_pattern': 0},
        'C': {'total': 0, 'pattern_applied': 0, 'correct': 0, 'correct_with_pattern': 0},
        'D': {'total': 0, 'pattern_applied': 0, 'correct': 0, 'correct_with_pattern': 0},
        'E': {'total': 0, 'pattern_applied': 0, 'correct': 0, 'correct_with_pattern': 0},
    }

    pattern_data = defaultdict(lambda: {'count': 0, 'correct': 0})

    daily_data = defaultdict(lambda: {
        'total': 0,
        'pattern_applied': 0,
        'correct': 0,
        'correct_with_pattern': 0
    })

    print("データ収集中...")
    for i, (race_id, venue_code, race_date, race_number) in enumerate(races, 1):
        try:
            # 予測実行
            predictions = predictor.predict_race(race_id)

            if not predictions:
                continue

            # トップ予測
            top_pred = predictions[0]
            predicted_pit = top_pred.get('pit_number')
            confidence = top_pred.get('confidence', 'C')
            pattern_multiplier = top_pred.get('pattern_multiplier', 1.0)
            matched_patterns = top_pred.get('matched_patterns', [])

            # パターン適用判定
            pattern_applied = (pattern_multiplier > 1.0 or len(matched_patterns) > 0)

            # 実際の1着
            cursor.execute("SELECT pit_number FROM results WHERE race_id = ? AND rank = 1", (race_id,))
            actual_winner_row = cursor.fetchone()

            if not actual_winner_row:
                continue

            actual_winner = actual_winner_row[0]
            is_correct = (predicted_pit == actual_winner)

            # 信頼度別データ
            conf_data = confidence_data[confidence]
            conf_data['total'] += 1
            if pattern_applied:
                conf_data['pattern_applied'] += 1
            if is_correct:
                conf_data['correct'] += 1
                if pattern_applied:
                    conf_data['correct_with_pattern'] += 1

            # パターン別データ
            if pattern_applied and matched_patterns:
                top_pattern = matched_patterns[0] if isinstance(matched_patterns, list) else matched_patterns
                pattern_data[top_pattern]['count'] += 1
                if is_correct:
                    pattern_data[top_pattern]['correct'] += 1

            # 日別データ
            day_key = race_date
            day_data = daily_data[day_key]
            day_data['total'] += 1
            if pattern_applied:
                day_data['pattern_applied'] += 1
            if is_correct:
                day_data['correct'] += 1
                if pattern_applied:
                    day_data['correct_with_pattern'] += 1

            if i % 50 == 0:
                print(f"  {i}/{len(races)}レース処理完了...")

        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    conn.close()

    # === 可視化1: 信頼度別パターン適用率 ===
    print()
    print("=" * 80)
    print("【グラフ1】信頼度別パターン適用率と的中率")
    print("=" * 80)
    print()

    print(f"{'信頼度':>4} {'レース数':>8} {'適用率':>7} {'的中率':>7} {'パターン適用時的中率':>12}")
    print("-" * 80)

    for conf in ['A', 'B', 'C', 'D', 'E']:
        data = confidence_data[conf]
        if data['total'] > 0:
            apply_rate = data['pattern_applied'] / data['total'] * 100
            accuracy = data['correct'] / data['total'] * 100
            pattern_accuracy = (data['correct_with_pattern'] / data['pattern_applied'] * 100
                               if data['pattern_applied'] > 0 else 0)

            # バーグラフ表示（ASCII）
            apply_bar = '█' * int(apply_rate / 5)  # 5%刻み
            accuracy_bar = '█' * int(accuracy / 5)

            print(f"{conf:>4} {data['total']:>8} {apply_rate:>6.1f}% {accuracy:>6.1f}% {pattern_accuracy:>11.1f}%")
            print(f"     適用: {apply_bar}")
            print(f"     的中: {accuracy_bar}")
            print()

    # === 可視化2: トップパターンの効果 ===
    print("=" * 80)
    print("【グラフ2】トップ10パターンの的中率")
    print("=" * 80)
    print()

    # パターンを的中率順にソート
    pattern_list = [
        (pattern, data['count'], data['correct'], data['correct'] / data['count'] * 100 if data['count'] > 0 else 0)
        for pattern, data in pattern_data.items()
        if data['count'] >= 5  # 5回以上使用
    ]
    pattern_list.sort(key=lambda x: x[3], reverse=True)

    if pattern_list:
        print(f"{'順位':>4} {'パターン名':<25} {'使用回数':>8} {'的中数':>6} {'的中率':>8} {'グラフ'}")
        print("-" * 80)

        for rank, (pattern, count, correct, accuracy) in enumerate(pattern_list[:10], 1):
            bar = '█' * int(accuracy / 5)  # 5%刻み
            print(f"{rank:>4} {pattern:<25} {count:>8} {correct:>6} {accuracy:>7.1f}% {bar}")
    else:
        print("（パターンデータ不足）")

    # === 可視化3: 日別トレンド ===
    print()
    print("=" * 80)
    print("【グラフ3】日別パフォーマンストレンド（直近14日）")
    print("=" * 80)
    print()

    # 日付順にソート
    daily_list = sorted(daily_data.items(), key=lambda x: x[0], reverse=True)[:14]
    daily_list.reverse()  # 古い順に並び替え

    if daily_list:
        print(f"{'日付':>10} {'レース':>6} {'適用率':>7} {'的中率':>7} {'パターン適用時的中率':>12}")
        print("-" * 80)

        for date, data in daily_list:
            if data['total'] > 0:
                apply_rate = data['pattern_applied'] / data['total'] * 100
                accuracy = data['correct'] / data['total'] * 100
                pattern_accuracy = (data['correct_with_pattern'] / data['pattern_applied'] * 100
                                   if data['pattern_applied'] > 0 else 0)

                print(f"{date} {data['total']:>6} {apply_rate:>6.1f}% {accuracy:>6.1f}% {pattern_accuracy:>11.1f}%")
    else:
        print("（日別データなし）")

    # === サマリー ===
    print()
    print("=" * 80)
    print("【サマリー】")
    print("=" * 80)
    print()

    total_races = sum(d['total'] for d in confidence_data.values())
    total_pattern_applied = sum(d['pattern_applied'] for d in confidence_data.values())
    total_correct = sum(d['correct'] for d in confidence_data.values())
    total_correct_with_pattern = sum(d['correct_with_pattern'] for d in confidence_data.values())

    if total_races > 0:
        overall_apply_rate = total_pattern_applied / total_races * 100
        overall_accuracy = total_correct / total_races * 100
        pattern_accuracy = (total_correct_with_pattern / total_pattern_applied * 100
                           if total_pattern_applied > 0 else 0)
        non_pattern_accuracy = ((total_correct - total_correct_with_pattern) /
                               (total_races - total_pattern_applied) * 100
                               if (total_races - total_pattern_applied) > 0 else 0)

        print(f"総レース数: {total_races}レース")
        print(f"パターン適用率: {overall_apply_rate:.1f}%")
        print(f"全体的中率: {overall_accuracy:.1f}%")
        print()
        print(f"パターン適用時の的中率: {pattern_accuracy:.1f}%")
        print(f"パターン未適用時の的中率: {non_pattern_accuracy:.1f}%")
        print(f"改善幅: {pattern_accuracy - non_pattern_accuracy:+.1f}pt")

        # 推奨事項
        print()
        print("【推奨アクション】")
        if pattern_accuracy > non_pattern_accuracy + 5:
            print("✓ パターンボーナスが効果的に機能しています")
            print("  - 信頼度B/Cでの適用率を維持してください")
        elif pattern_accuracy > non_pattern_accuracy:
            print("⚙️ パターンボーナスは軽微な効果を示しています")
            print("  - パターン精度の見直しを検討してください")
        else:
            print("⚠ パターンボーナスが逆効果になっている可能性があります")
            print("  - フィーチャーフラグで無効化を検討してください")

    print()
    print("=" * 80)
    print("可視化レポート完了")
    print("=" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='パターンボーナス効果の可視化')
    parser.add_argument('--days', type=int, default=30, help='分析対象期間（日数）')

    args = parser.parse_args()

    visualize_pattern_effectiveness(days=args.days)
