#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
パターン別的中率分析

各BEFOREパターンの実際の的中率を大規模データで計測し、
最適な倍率を算出する
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
from collections import defaultdict
from src.analysis.race_predictor import RacePredictor


def analyze_pattern_accuracy(num_races: int = 200):
    """
    パターン別の的中率を分析

    Args:
        num_races: 分析対象レース数
    """

    print("=" * 80)
    print("パターン別的中率分析")
    print("=" * 80)
    print()
    print(f"分析対象: {num_races}レース")
    print()

    # データベース接続
    db_path = os.path.join(project_root, 'data', 'boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 分析対象レースを取得
    cursor.execute("""
        SELECT r.id
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

    race_ids = [row[0] for row in cursor.fetchall()]
    actual_races = len(race_ids)

    print(f"対象レース: {actual_races}レース")
    print()

    # 予測器初期化
    predictor = RacePredictor(db_path)

    # パターン別統計
    pattern_stats = defaultdict(lambda: {'total': 0, 'correct': 0, 'multipliers': []})

    print("分析中...")
    for i, race_id in enumerate(race_ids, 1):
        try:
            # 予測実行
            predictions = predictor.predict_race(race_id)

            if not predictions:
                continue

            # 実際の1着を取得
            cursor.execute("""
                SELECT pit_number FROM results
                WHERE race_id = ? AND rank = 1
            """, (race_id,))
            actual_row = cursor.fetchone()

            if not actual_row:
                continue

            actual_winner = actual_row[0]

            # 各艇の予測を分析
            for pred in predictions:
                pit_number = pred.get('pit_number')
                matched_patterns = pred.get('matched_patterns', [])
                pattern_multiplier = pred.get('pattern_multiplier', 1.0)
                selected_pattern = pred.get('selected_pattern', '')

                # パターンが適用されている場合
                if matched_patterns and pattern_multiplier > 1.0:
                    is_correct = (pit_number == actual_winner)

                    # 選択されたパターンの統計を更新
                    if selected_pattern:
                        pattern_stats[selected_pattern]['total'] += 1
                        pattern_stats[selected_pattern]['multipliers'].append(pattern_multiplier)
                        if is_correct:
                            pattern_stats[selected_pattern]['correct'] += 1

            if i % 50 == 0:
                print(f"  {i}/{actual_races}レース処理完了...")

        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    conn.close()

    # 結果表示
    print()
    print("=" * 80)
    print("【パターン別的中率】")
    print("=" * 80)
    print()

    # パターンを使用回数の多い順にソート
    sorted_patterns = sorted(
        pattern_stats.items(),
        key=lambda x: x[1]['total'],
        reverse=True
    )

    print(f"{'パターン名':<30} {'使用回数':>8} {'的中数':>8} {'的中率':>8} {'現在倍率':>10} {'推奨倍率':>10}")
    print("-" * 80)

    recommendations = []

    for pattern_name, stats in sorted_patterns:
        total = stats['total']
        correct = stats['correct']
        accuracy = correct / total * 100 if total > 0 else 0
        current_multiplier = sum(stats['multipliers']) / len(stats['multipliers']) if stats['multipliers'] else 1.0

        # 推奨倍率の計算
        # 基本方針: 的中率が高いパターンは倍率を上げる
        # 50%以下 → 倍率を下げる
        # 50-60% → 現状維持
        # 60-70% → 倍率を5-10%上げる
        # 70%以上 → 倍率を10-20%上げる
        if accuracy < 50:
            recommended_multiplier = current_multiplier * 0.95
        elif accuracy < 60:
            recommended_multiplier = current_multiplier
        elif accuracy < 70:
            recommended_multiplier = current_multiplier * 1.05
        else:
            recommended_multiplier = current_multiplier * 1.15

        # 上限を1.5、下限を1.0に設定
        recommended_multiplier = max(1.0, min(recommended_multiplier, 1.5))

        change_indicator = ""
        if abs(recommended_multiplier - current_multiplier) > 0.01:
            if recommended_multiplier > current_multiplier:
                change_indicator = "📈"
            else:
                change_indicator = "📉"

        print(f"{pattern_name:<30} {total:>8} {correct:>8} {accuracy:>7.1f}% {current_multiplier:>9.3f} {recommended_multiplier:>9.3f} {change_indicator}")

        if abs(recommended_multiplier - current_multiplier) > 0.02:  # 2%以上の変更推奨
            recommendations.append({
                'pattern': pattern_name,
                'current': current_multiplier,
                'recommended': recommended_multiplier,
                'accuracy': accuracy,
                'sample_size': total
            })

    print()
    print("=" * 80)
    print("【変更推奨パターン】（2%以上の変更）")
    print("=" * 80)
    print()

    if recommendations:
        for rec in sorted(recommendations, key=lambda x: abs(x['recommended'] - x['current']), reverse=True):
            change_pct = (rec['recommended'] - rec['current']) / rec['current'] * 100
            print(f"📌 {rec['pattern']}")
            print(f"   現在: {rec['current']:.3f} → 推奨: {rec['recommended']:.3f} ({change_pct:+.1f}%)")
            print(f"   的中率: {rec['accuracy']:.1f}% ({rec['sample_size']}回使用)")
            print()
    else:
        print("変更推奨なし（現在の倍率が適切です）")
        print()

    print("=" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='パターン別的中率分析')
    parser.add_argument('--races', type=int, default=200,
                        help='分析対象レース数（デフォルト: 200）')

    args = parser.parse_args()

    analyze_pattern_accuracy(num_races=args.races)
