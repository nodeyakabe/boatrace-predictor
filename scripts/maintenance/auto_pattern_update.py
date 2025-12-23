#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自動パターン更新機構

Phase 3 Task 4: 最新レース結果からパターン統計を自動更新
- 過去N日間のレース結果を分析
- パターン別的中率を計算
- 効果が低下したパターンを検出
- 推奨アクションを提示
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List
from src.analysis.race_predictor import RacePredictor


def analyze_pattern_performance(days: int = 30, min_usage: int = 5):
    """
    パターンパフォーマンスを自動分析

    Args:
        days: 分析対象期間（日数）
        min_usage: 最小使用回数（これ未満のパターンは除外）
    """

    print("=" * 80)
    print("自動パターン更新システム")
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

    # 対象レース取得
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
        LIMIT 500
    """, (start_date, end_date))

    races = cursor.fetchall()
    print(f"対象レース数: {len(races)}レース")
    print()

    # 予測器初期化
    predictor = RacePredictor()

    # パターン別統計
    pattern_stats = defaultdict(lambda: {
        'count': 0,
        'correct': 0,
        'total_multiplier': 0.0
    })

    # 信頼度別統計
    confidence_stats = defaultdict(lambda: {
        'total': 0,
        'pattern_applied': 0,
        'correct': 0,
        'correct_with_pattern': 0
    })

    # データ収集
    print("レース分析中...")
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

            # 信頼度別統計更新
            conf_stats = confidence_stats[confidence]
            conf_stats['total'] += 1
            if pattern_applied:
                conf_stats['pattern_applied'] += 1
            if is_correct:
                conf_stats['correct'] += 1
                if pattern_applied:
                    conf_stats['correct_with_pattern'] += 1

            # パターン別統計更新
            if pattern_applied and matched_patterns:
                top_pattern = matched_patterns[0] if isinstance(matched_patterns, list) else matched_patterns
                pattern_stats[top_pattern]['count'] += 1
                pattern_stats[top_pattern]['total_multiplier'] += pattern_multiplier
                if is_correct:
                    pattern_stats[top_pattern]['correct'] += 1

            if i % 50 == 0:
                print(f"  {i}/{len(races)}レース処理完了...")

        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    conn.close()

    print()
    print("=" * 80)
    print("【パターンパフォーマンス分析】")
    print("=" * 80)
    print()

    # パターンを的中率順にソート
    pattern_list = []
    for pattern, stats in pattern_stats.items():
        if stats['count'] >= min_usage:
            accuracy = stats['correct'] / stats['count'] * 100 if stats['count'] > 0 else 0
            avg_multiplier = stats['total_multiplier'] / stats['count'] if stats['count'] > 0 else 1.0

            pattern_list.append({
                'pattern': pattern,
                'count': stats['count'],
                'correct': stats['correct'],
                'accuracy': accuracy,
                'avg_multiplier': avg_multiplier
            })

    pattern_list.sort(key=lambda x: x['accuracy'], reverse=True)

    # 上位10パターン
    print("【トップ10パターン】")
    print(f"{'順位':>4} {'パターン名':<30} {'使用':>6} {'的中':>6} {'的中率':>8} {'平均倍率':>9}")
    print("-" * 80)

    for rank, p in enumerate(pattern_list[:10], 1):
        status = "✓" if p['accuracy'] >= 50 else "⚠"
        print(f"{rank:>4} {p['pattern']:<30} {p['count']:>6} {p['correct']:>6} "
              f"{p['accuracy']:>7.1f}% {p['avg_multiplier']:>8.3f} {status}")

    print()

    # 下位5パターン（要注意）
    if len(pattern_list) > 10:
        print("【要注意パターン（下位5）】")
        print(f"{'順位':>4} {'パターン名':<30} {'使用':>6} {'的中':>6} {'的中率':>8} {'平均倍率':>9}")
        print("-" * 80)

        for rank, p in enumerate(pattern_list[-5:], len(pattern_list) - 4):
            print(f"{rank:>4} {p['pattern']:<30} {p['count']:>6} {p['correct']:>6} "
                  f"{p['accuracy']:>7.1f}% {p['avg_multiplier']:>8.3f} ⚠")

        print()

    # 信頼度別パフォーマンス
    print("=" * 80)
    print("【信頼度別パフォーマンス】")
    print("=" * 80)
    print()

    print(f"{'信頼度':>4} {'レース数':>8} {'適用率':>7} {'的中率':>7} {'パターン適用時的中率':>12}")
    print("-" * 80)

    for conf in ['A', 'B', 'C', 'D', 'E']:
        stats = confidence_stats[conf]
        if stats['total'] > 0:
            apply_rate = stats['pattern_applied'] / stats['total'] * 100
            accuracy = stats['correct'] / stats['total'] * 100
            pattern_accuracy = (stats['correct_with_pattern'] / stats['pattern_applied'] * 100
                               if stats['pattern_applied'] > 0 else 0)

            print(f"{conf:>4} {stats['total']:>8} {apply_rate:>6.1f}% {accuracy:>6.1f}% {pattern_accuracy:>11.1f}%")

    # 推奨アクション
    print()
    print("=" * 80)
    print("【推奨アクション】")
    print("=" * 80)
    print()

    # 劣化パターンの検出（的中率50%未満）
    degraded_patterns = [p for p in pattern_list if p['accuracy'] < 50 and p['count'] >= 10]

    if degraded_patterns:
        print("⚠️ 効果が低下しているパターンが検出されました:")
        for p in degraded_patterns:
            print(f"  - {p['pattern']}: 的中率 {p['accuracy']:.1f}% (使用{p['count']}回)")
        print()
        print("【対策】:")
        print("  1. パターン定義の見直し")
        print("  2. 倍率の調整")
        print("  3. 一時的な無効化を検討")
    else:
        print("✓ すべてのパターンが良好なパフォーマンスを維持しています")

    print()

    # 高パフォーマンスパターンの推奨
    excellent_patterns = [p for p in pattern_list if p['accuracy'] >= 65 and p['count'] >= 10]

    if excellent_patterns:
        print("✨ 優秀なパフォーマンスのパターン:")
        for p in excellent_patterns[:5]:
            print(f"  - {p['pattern']}: 的中率 {p['accuracy']:.1f}% (使用{p['count']}回)")
        print()
        print("【推奨】:")
        print("  - これらのパターンの倍率を微増することを検討")

    print()
    print("=" * 80)
    print("自動更新分析完了")
    print("=" * 80)

    # レポート保存
    report_path = os.path.join(project_root, 'output', f'pattern_update_report_{end_date}.md')
    _save_report(
        report_path,
        pattern_list,
        confidence_stats,
        degraded_patterns,
        excellent_patterns,
        start_date,
        end_date
    )

    print()
    print(f"📄 詳細レポートを保存: {report_path}")


def _save_report(
    filepath,
    pattern_list,
    confidence_stats,
    degraded_patterns,
    excellent_patterns,
    start_date,
    end_date
):
    """レポートをMarkdownファイルに保存"""

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"# パターン自動更新レポート\n\n")
        f.write(f"**生成日**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**分析期間**: {start_date} ～ {end_date}\n\n")

        f.write("## トップ10パターン\n\n")
        f.write("| 順位 | パターン名 | 使用回数 | 的中数 | 的中率 | 平均倍率 |\n")
        f.write("|------|-----------|---------|--------|--------|----------|\n")

        for rank, p in enumerate(pattern_list[:10], 1):
            f.write(f"| {rank} | {p['pattern']} | {p['count']} | {p['correct']} | "
                   f"{p['accuracy']:.1f}% | ×{p['avg_multiplier']:.3f} |\n")

        f.write("\n## 信頼度別パフォーマンス\n\n")
        f.write("| 信頼度 | レース数 | 適用率 | 的中率 | パターン適用時的中率 |\n")
        f.write("|--------|---------|--------|--------|------------------|\n")

        for conf in ['A', 'B', 'C', 'D', 'E']:
            stats = confidence_stats[conf]
            if stats['total'] > 0:
                apply_rate = stats['pattern_applied'] / stats['total'] * 100
                accuracy = stats['correct'] / stats['total'] * 100
                pattern_accuracy = (stats['correct_with_pattern'] / stats['pattern_applied'] * 100
                                   if stats['pattern_applied'] > 0 else 0)

                f.write(f"| {conf} | {stats['total']} | {apply_rate:.1f}% | "
                       f"{accuracy:.1f}% | {pattern_accuracy:.1f}% |\n")

        if degraded_patterns:
            f.write("\n## ⚠️ 要注意パターン\n\n")
            for p in degraded_patterns:
                f.write(f"- **{p['pattern']}**: 的中率 {p['accuracy']:.1f}% (使用{p['count']}回)\n")

        if excellent_patterns:
            f.write("\n## ✨ 優秀パターン\n\n")
            for p in excellent_patterns[:5]:
                f.write(f"- **{p['pattern']}**: 的中率 {p['accuracy']:.1f}% (使用{p['count']}回)\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='自動パターン更新システム')
    parser.add_argument('--days', type=int, default=30, help='分析対象期間（日数）')
    parser.add_argument('--min-usage', type=int, default=5, help='最小使用回数')

    args = parser.parse_args()

    analyze_pattern_performance(days=args.days, min_usage=args.min_usage)
