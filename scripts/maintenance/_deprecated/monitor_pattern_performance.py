#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
パターンボーナスシステム モニタリングダッシュボード

Phase 2: リアルタイム監視機能
- パターン適用率の追跡
- 的中率トレンドの監視
- 信頼度別パフォーマンス分析
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


def monitor_pattern_performance(days: int = 7):
    """
    パターンボーナスシステムのパフォーマンスを監視

    Args:
        days: 監視対象期間（日数）
    """

    print("=" * 80)
    print("パターンボーナスシステム モニタリングダッシュボード")
    print("=" * 80)
    print()

    # データベース接続
    db_path = os.path.join(project_root, 'data', 'boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 監視対象期間
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)

    print(f"監視期間: {start_date} ～ {end_date} ({days}日間)")
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
        ORDER BY r.race_date DESC, r.race_number DESC
        LIMIT 200
    """, (start_date, end_date))

    races = cursor.fetchall()
    print(f"対象レース数: {len(races)}レース")
    print()

    # 予測器初期化
    predictor = RacePredictor()

    # 統計データ
    stats = {
        'total': 0,
        'pattern_applied': 0,
        'pattern_skipped': 0,
        'correct': 0,
        'correct_with_pattern': 0,
        'correct_without_pattern': 0,
        'by_confidence': defaultdict(lambda: {
            'total': 0,
            'pattern_applied': 0,
            'correct': 0,
            'correct_with_pattern': 0
        }),
        'by_pattern': defaultdict(lambda: {
            'count': 0,
            'correct': 0
        }),
        'by_multiplier': defaultdict(lambda: {
            'count': 0,
            'correct': 0
        })
    }

    # 各レースを予測・検証
    print("=" * 80)
    print("レース分析中...")
    print("=" * 80)

    for i, (race_id, venue_code, race_date, race_number) in enumerate(races, 1):
        try:
            # 予測実行
            predictions = predictor.predict_race(race_id)

            if not predictions:
                continue

            # トップ予測を取得
            top_pred = predictions[0]
            predicted_pit = top_pred.get('pit_number')
            confidence = top_pred.get('confidence', 'C')
            integration_mode = top_pred.get('integration_mode', 'unknown')
            pattern_multiplier = top_pred.get('pattern_multiplier', 1.0)
            matched_patterns = top_pred.get('matched_patterns', [])

            # パターン適用判定
            pattern_applied = (
                pattern_multiplier > 1.0 or
                len(matched_patterns) > 0 or
                integration_mode.startswith('pattern_bonus')
            )

            # 実際の1着を取得
            cursor.execute("""
                SELECT pit_number FROM results
                WHERE race_id = ? AND rank = 1
            """, (race_id,))
            actual_winner_row = cursor.fetchone()

            if not actual_winner_row:
                continue

            actual_winner = actual_winner_row[0]
            is_correct = (predicted_pit == actual_winner)

            # 統計更新
            stats['total'] += 1
            if pattern_applied:
                stats['pattern_applied'] += 1
                if is_correct:
                    stats['correct_with_pattern'] += 1
            else:
                stats['pattern_skipped'] += 1
                if is_correct:
                    stats['correct_without_pattern'] += 1

            if is_correct:
                stats['correct'] += 1

            # 信頼度別統計
            conf_stats = stats['by_confidence'][confidence]
            conf_stats['total'] += 1
            if pattern_applied:
                conf_stats['pattern_applied'] += 1
            if is_correct:
                conf_stats['correct'] += 1
                if pattern_applied:
                    conf_stats['correct_with_pattern'] += 1

            # パターン別統計
            if pattern_applied and matched_patterns:
                # matched_patternsがリストの場合は最初の要素を取得
                if isinstance(matched_patterns, list) and len(matched_patterns) > 0:
                    top_pattern = matched_patterns[0]
                    # dict型の場合はパターン名を抽出（'name'キーまたは'pattern_name'キー）
                    if isinstance(top_pattern, dict):
                        pattern_name = top_pattern.get('name', top_pattern.get('pattern_name', 'unknown'))
                    else:
                        pattern_name = str(top_pattern)
                elif isinstance(matched_patterns, dict):
                    pattern_name = matched_patterns.get('name', matched_patterns.get('pattern_name', 'unknown'))
                else:
                    pattern_name = str(matched_patterns)

                stats['by_pattern'][pattern_name]['count'] += 1
                if is_correct:
                    stats['by_pattern'][pattern_name]['correct'] += 1

            # 倍率別統計
            if pattern_applied:
                multiplier_bin = f"{pattern_multiplier:.2f}"
                stats['by_multiplier'][multiplier_bin]['count'] += 1
                if is_correct:
                    stats['by_multiplier'][multiplier_bin]['correct'] += 1

            # 進捗表示
            if i % 50 == 0:
                print(f"  {i}/{len(races)}レース処理完了...")

        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    conn.close()

    # ダッシュボード表示
    print()
    print("=" * 80)
    print("【全体パフォーマンス】")
    print("=" * 80)
    print()

    total = stats['total']
    if total > 0:
        overall_accuracy = stats['correct'] / total * 100
        pattern_rate = stats['pattern_applied'] / total * 100
        skip_rate = stats['pattern_skipped'] / total * 100

        print(f"総レース数: {total}レース")
        print(f"全体的中率: {overall_accuracy:.2f}% ({stats['correct']}/{total})")
        print()
        print(f"パターン適用: {stats['pattern_applied']}レース ({pattern_rate:.1f}%)")
        print(f"パターンスキップ: {stats['pattern_skipped']}レース ({skip_rate:.1f}%)")
        print()

        # パターン適用時 vs スキップ時の的中率比較
        if stats['pattern_applied'] > 0:
            pattern_accuracy = stats['correct_with_pattern'] / stats['pattern_applied'] * 100
            print(f"パターン適用時の的中率: {pattern_accuracy:.2f}% ({stats['correct_with_pattern']}/{stats['pattern_applied']})")

        if stats['pattern_skipped'] > 0:
            skip_accuracy = stats['correct_without_pattern'] / stats['pattern_skipped'] * 100
            print(f"パターンスキップ時の的中率: {skip_accuracy:.2f}% ({stats['correct_without_pattern']}/{stats['pattern_skipped']})")

        if stats['pattern_applied'] > 0 and stats['pattern_skipped'] > 0:
            improvement = pattern_accuracy - skip_accuracy
            print()
            print(f"パターン適用による改善: {improvement:+.2f}pt")

    print()
    print("=" * 80)
    print("【信頼度別パフォーマンス】")
    print("=" * 80)
    print()

    for conf in ['A', 'B', 'C', 'D', 'E']:
        conf_stats = stats['by_confidence'][conf]
        if conf_stats['total'] > 0:
            conf_accuracy = conf_stats['correct'] / conf_stats['total'] * 100
            conf_pattern_rate = conf_stats['pattern_applied'] / conf_stats['total'] * 100

            status = ""
            if conf in ['A', 'E']:
                status = "✓ スキップ推奨" if conf_pattern_rate < 20 else "⚠ 過剰適用"
            elif conf in ['B', 'C']:
                status = "✓ 適用推奨" if conf_pattern_rate > 80 else "⚠ 適用不足"
            else:  # D
                status = "⚙️ フラグ制御"

            print(f"信頼度{conf}: {conf_stats['total']:3d}レース | "
                  f"的中率: {conf_accuracy:5.1f}% | "
                  f"パターン適用率: {conf_pattern_rate:5.1f}% | {status}")

    print()
    print("=" * 80)
    print("【トップ5パターン】")
    print("=" * 80)
    print()

    # パターンを的中率順にソート
    pattern_list = [
        (pattern, data['count'], data['correct'], data['correct'] / data['count'] * 100 if data['count'] > 0 else 0)
        for pattern, data in stats['by_pattern'].items()
        if data['count'] >= 3  # 3回以上使用されたパターンのみ
    ]
    pattern_list.sort(key=lambda x: x[3], reverse=True)

    if pattern_list:
        print(f"{'パターン名':<30} {'使用回数':>8} {'的中数':>6} {'的中率':>8}")
        print("-" * 80)
        for pattern, count, correct, accuracy in pattern_list[:5]:
            print(f"{pattern:<30} {count:>8} {correct:>6} {accuracy:>7.1f}%")
    else:
        print("（パターンデータなし）")

    print()
    print("=" * 80)
    print("【倍率別パフォーマンス】")
    print("=" * 80)
    print()

    # 倍率別統計をソート
    multiplier_list = [
        (multiplier, data['count'], data['correct'], data['correct'] / data['count'] * 100 if data['count'] > 0 else 0)
        for multiplier, data in stats['by_multiplier'].items()
        if data['count'] >= 2
    ]
    multiplier_list.sort(key=lambda x: float(x[0]), reverse=True)

    if multiplier_list:
        print(f"{'倍率':>6} {'使用回数':>8} {'的中数':>6} {'的中率':>8}")
        print("-" * 80)
        for multiplier, count, correct, accuracy in multiplier_list[:10]:
            print(f"{multiplier:>6} {count:>8} {correct:>6} {accuracy:>7.1f}%")
    else:
        print("（倍率データなし）")

    # キャッシュ統計
    print()
    print("=" * 80)
    print("【キャッシュ統計】")
    print("=" * 80)
    print()

    cache_stats = predictor.race_data_cache.get_all_stats()
    for cache_type, cache_data in cache_stats.items():
        if cache_data['hits'] + cache_data['misses'] > 0:
            print(f"{cache_type}:")
            print(f"  - Hit Rate: {cache_data['hit_rate']:.1%}")
            print(f"  - Hits: {cache_data['hits']}, Misses: {cache_data['misses']}")
            print(f"  - Size: {cache_data['size']}")
            print()

    print("=" * 80)
    print("モニタリング完了")
    print("=" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='パターンボーナスシステム モニタリングダッシュボード')
    parser.add_argument('--days', type=int, default=7, help='監視対象期間（日数）')

    args = parser.parse_args()

    monitor_pattern_performance(days=args.days)
