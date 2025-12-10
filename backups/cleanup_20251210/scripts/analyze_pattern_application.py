# -*- coding: utf-8 -*-
"""
導入済み20パターンの実戦効果測定

目的:
- 2025年全データでの各パターンの適用状況を分析
- パターン別の的中率、適用頻度、ROIを測定
- 信頼度別の効果を測定
- 効果が低いパターンを特定
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor


def analyze_pattern_effectiveness(db_path, year=2025):
    """
    パターン適用状況の詳細分析

    Args:
        db_path: データベースパス
        year: 分析対象年（デフォルト: 2025）

    Returns:
        dict: 分析結果
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 対象年で直前情報が存在するレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE strftime('%Y', r.race_date) = ?
        AND rd.exhibition_time IS NOT NULL
        ORDER BY r.race_date, r.race_number
    ''', (str(year),))
    race_ids = [row[0] for row in cursor.fetchall()]

    print("=" * 80)
    print(f"導入済みパターンの実戦効果測定（{year}年）")
    print("=" * 80)
    print()
    print(f"分析対象レース数: {len(race_ids)}")
    print()

    # 統計用データ構造
    overall_stats = {
        'total_races': 0,
        'total_hits': 0,
        'pattern_applied_races': 0,
        'pattern_applied_hits': 0,
        'pattern_not_applied_races': 0,
        'pattern_not_applied_hits': 0,
    }

    # パターン別統計
    pattern_stats = defaultdict(lambda: {
        'applied_count': 0,
        'hit_count': 0,
        'win_rate': 0.0,
        'races': []  # レースID記録
    })

    # 信頼度別統計
    confidence_stats = defaultdict(lambda: {
        'total_races': 0,
        'total_hits': 0,
        'pattern_applied_races': 0,
        'pattern_applied_hits': 0,
    })

    # パターン重複統計
    overlap_stats = defaultdict(int)

    # PRE予測器を初期化
    predictor = RacePredictor(db_path)

    # 各レースを分析
    for i, race_id in enumerate(race_ids, 1):
        if i % 100 == 0:
            print(f"処理中... {i}/{len(race_ids)} レース")

        # 予測実行
        try:
            predictions = predictor.predict_race(race_id)
        except Exception as e:
            print(f"レースID {race_id} でエラー: {e}")
            continue

        if not predictions or len(predictions) < 6:
            continue

        # 実際の1着を取得
        cursor.execute('''
            SELECT pit_number
            FROM results
            WHERE race_id = ? AND rank = 1
        ''', (race_id,))
        winner_row = cursor.fetchone()

        if not winner_row:
            continue

        actual_winner = winner_row[0]

        # 予測1位
        predicted_winner = predictions[0]['pit_number']
        is_hit = (predicted_winner == actual_winner)

        # 信頼度
        confidence = predictions[0].get('confidence', 'E')

        # 全体統計
        overall_stats['total_races'] += 1
        if is_hit:
            overall_stats['total_hits'] += 1

        # パターン適用状況をチェック
        pattern_multiplier = predictions[0].get('pattern_multiplier', 1.0)
        matched_patterns = predictions[0].get('matched_patterns', [])
        pattern_applied = (pattern_multiplier > 1.0 and len(matched_patterns) > 0)

        if pattern_applied:
            overall_stats['pattern_applied_races'] += 1
            if is_hit:
                overall_stats['pattern_applied_hits'] += 1

            # パターン別統計
            for pattern in matched_patterns:
                pattern_name = pattern['name']
                pattern_stats[pattern_name]['applied_count'] += 1
                if is_hit:
                    pattern_stats[pattern_name]['hit_count'] += 1
                pattern_stats[pattern_name]['races'].append(race_id)

            # パターン重複統計
            overlap_key = len(matched_patterns)
            overlap_stats[overlap_key] += 1
        else:
            overall_stats['pattern_not_applied_races'] += 1
            if is_hit:
                overall_stats['pattern_not_applied_hits'] += 1

        # 信頼度別統計
        confidence_stats[confidence]['total_races'] += 1
        if is_hit:
            confidence_stats[confidence]['total_hits'] += 1
        if pattern_applied:
            confidence_stats[confidence]['pattern_applied_races'] += 1
            if is_hit:
                confidence_stats[confidence]['pattern_applied_hits'] += 1

    cursor.close()

    # 結果を表示
    print()
    print("=" * 80)
    print("全体統計")
    print("=" * 80)
    print()

    total_races = overall_stats['total_races']
    total_hits = overall_stats['total_hits']
    overall_win_rate = (total_hits / total_races * 100) if total_races > 0 else 0.0

    print(f"総レース数: {total_races}")
    print(f"総的中数: {total_hits}")
    print(f"全体的中率: {overall_win_rate:.2f}%")
    print()

    # パターン適用 vs 非適用
    pattern_applied_races = overall_stats['pattern_applied_races']
    pattern_applied_hits = overall_stats['pattern_applied_hits']
    pattern_applied_rate = (pattern_applied_hits / pattern_applied_races * 100) if pattern_applied_races > 0 else 0.0

    pattern_not_applied_races = overall_stats['pattern_not_applied_races']
    pattern_not_applied_hits = overall_stats['pattern_not_applied_hits']
    pattern_not_applied_rate = (pattern_not_applied_hits / pattern_not_applied_races * 100) if pattern_not_applied_races > 0 else 0.0

    print("【パターン適用状況】")
    print(f"パターン適用レース: {pattern_applied_races} ({pattern_applied_races/total_races*100:.1f}%)")
    print(f"  的中数: {pattern_applied_hits}")
    print(f"  的中率: {pattern_applied_rate:.2f}%")
    print()
    print(f"パターン非適用レース: {pattern_not_applied_races} ({pattern_not_applied_races/total_races*100:.1f}%)")
    print(f"  的中数: {pattern_not_applied_hits}")
    print(f"  的中率: {pattern_not_applied_rate:.2f}%")
    print()

    improvement = pattern_applied_rate - pattern_not_applied_rate
    print(f"パターン適用による改善度: {improvement:+.2f}%")
    print()

    # パターン別統計
    print("=" * 80)
    print("パターン別統計（適用回数順）")
    print("=" * 80)
    print()

    # パターン別勝率を計算
    for pattern_name, stats in pattern_stats.items():
        if stats['applied_count'] > 0:
            stats['win_rate'] = (stats['hit_count'] / stats['applied_count']) * 100

    # 適用回数順にソート
    sorted_patterns = sorted(
        pattern_stats.items(),
        key=lambda x: x[1]['applied_count'],
        reverse=True
    )

    print(f"{'パターン名':<40} {'適用回数':<10} {'的中数':<10} {'的中率':<10} {'適用率':<10}")
    print("-" * 90)

    for pattern_name, stats in sorted_patterns:
        applied_count = stats['applied_count']
        hit_count = stats['hit_count']
        win_rate = stats['win_rate']
        application_rate = (applied_count / total_races * 100) if total_races > 0 else 0.0

        print(f"{pattern_name:<40} {applied_count:<10} {hit_count:<10} {win_rate:>6.2f}% {application_rate:>8.1f}%")

    print()

    # 効果が低いパターンを特定
    print("=" * 80)
    print("効果評価")
    print("=" * 80)
    print()

    baseline_rate = overall_win_rate  # 全体平均を基準

    print("【高効果パターン】（的中率がベースライン+5%以上）")
    high_performers = [
        (name, stats) for name, stats in sorted_patterns
        if stats['win_rate'] >= baseline_rate + 5.0 and stats['applied_count'] >= 10
    ]

    if high_performers:
        for pattern_name, stats in high_performers:
            improvement = stats['win_rate'] - baseline_rate
            print(f"  ✓ {pattern_name}: {stats['win_rate']:.2f}% ({improvement:+.2f}%, {stats['applied_count']}回)")
    else:
        print("  該当なし")

    print()
    print("【低効果パターン】（的中率がベースライン未満）")
    low_performers = [
        (name, stats) for name, stats in sorted_patterns
        if stats['win_rate'] < baseline_rate and stats['applied_count'] >= 10
    ]

    if low_performers:
        for pattern_name, stats in low_performers:
            degradation = stats['win_rate'] - baseline_rate
            print(f"  ✗ {pattern_name}: {stats['win_rate']:.2f}% ({degradation:.2f}%, {stats['applied_count']}回) ← 要検討")
    else:
        print("  該当なし")

    print()

    # 信頼度別統計
    print("=" * 80)
    print("信頼度別統計")
    print("=" * 80)
    print()

    print(f"{'信頼度':<8} {'総レース数':<12} {'的中数':<10} {'的中率':<10} {'パターン適用率':<15} {'適用時的中率':<15}")
    print("-" * 90)

    for confidence in ['A', 'B', 'C', 'D', 'E']:
        if confidence not in confidence_stats:
            continue

        stats = confidence_stats[confidence]
        total_races_conf = stats['total_races']
        total_hits_conf = stats['total_hits']
        win_rate_conf = (total_hits_conf / total_races_conf * 100) if total_races_conf > 0 else 0.0

        pattern_applied_conf = stats['pattern_applied_races']
        pattern_applied_rate_conf = (pattern_applied_conf / total_races_conf * 100) if total_races_conf > 0 else 0.0

        pattern_applied_hits_conf = stats['pattern_applied_hits']
        pattern_applied_win_rate_conf = (pattern_applied_hits_conf / pattern_applied_conf * 100) if pattern_applied_conf > 0 else 0.0

        print(f"{confidence:<8} {total_races_conf:<12} {total_hits_conf:<10} {win_rate_conf:>6.2f}% "
              f"{pattern_applied_rate_conf:>12.1f}% {pattern_applied_win_rate_conf:>12.2f}%")

    print()

    # パターン重複統計
    print("=" * 80)
    print("パターン重複統計")
    print("=" * 80)
    print()

    print(f"{'重複パターン数':<15} {'レース数':<10}")
    print("-" * 30)

    for overlap_count in sorted(overlap_stats.keys()):
        race_count = overlap_stats[overlap_count]
        print(f"{overlap_count}個 {race_count:<10}")

    print()

    return {
        'overall_stats': overall_stats,
        'pattern_stats': dict(pattern_stats),
        'confidence_stats': dict(confidence_stats),
        'overlap_stats': dict(overlap_stats),
    }


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    # 2025年データで分析
    results = analyze_pattern_effectiveness(db_path, year=2025)

    print()
    print("=" * 80)
    print("分析完了")
    print("=" * 80)
    print()


if __name__ == '__main__':
    main()
