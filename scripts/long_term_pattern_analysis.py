#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
長期間（2025年全体）でのBEFOREパターン効果検証
信頼度別・会場別の詳細分析を含む
"""

import os
import sys
import sqlite3
from collections import defaultdict
from datetime import datetime

# プロジェクトルートをパスに追加
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from src.analysis.race_predictor import RacePredictor


def analyze_patterns_long_term(db_path=None, year=2025, sample_size=1000):
    """
    長期間でのパターン効果分析

    Args:
        db_path: データベースパス（Noneの場合はデフォルト）
        year: 分析対象年
        sample_size: サンプル数（None=全件、数値=最新N件）
    """
    if db_path is None:
        db_path = os.path.join(project_root, 'data', 'boatrace.db')

    print("=" * 80)
    sample_text = f"（最新{sample_size}レース）" if sample_size else "（全体）"
    print(f"BEFOREパターン長期分析（{year}年{sample_text}）")
    print("=" * 80)
    print()

    # データベース接続
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 対象レース取得
    query = """
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ?
          AND r.race_date < ?
          AND EXISTS (
              SELECT 1 FROM results res
              WHERE res.race_id = r.id
                AND res.rank IS NOT NULL
          )
          AND EXISTS (
              SELECT 1 FROM race_details rd
              WHERE rd.race_id = r.id
                AND rd.exhibition_time IS NOT NULL
                AND rd.st_time IS NOT NULL
          )
        ORDER BY r.race_date DESC, r.id DESC
    """
    if sample_size:
        query += f" LIMIT {sample_size}"

    cursor.execute(query, (f"{year}-01-01", f"{year+1}-01-01"))

    races = cursor.fetchall()
    total_races = len(races)

    print(f"[OK] 対象レース数: {total_races}レース")

    if total_races == 0:
        print("[ERROR] データが見つかりません")
        return

    # 統計情報の初期化
    overall_stats = {
        'with_pattern': {'total': 0, 'hits': 0},
        'without_pattern': {'total': 0, 'hits': 0}
    }

    pattern_stats = defaultdict(lambda: {'count': 0, 'hits': 0})
    confidence_stats = defaultdict(lambda: {
        'with_pattern': {'total': 0, 'hits': 0},
        'without_pattern': {'total': 0, 'hits': 0}
    })
    venue_stats = defaultdict(lambda: {
        'with_pattern': {'total': 0, 'hits': 0},
        'without_pattern': {'total': 0, 'hits': 0}
    })

    # 予測器の初期化
    predictor = RacePredictor()

    print("処理開始...\n")

    # 各レースを分析
    for i, (race_id, venue_code, race_date, race_number) in enumerate(races):
        if (i + 1) % 100 == 0:
            print(f"処理中... {i + 1}/{total_races}", end='\r')

        # 予測実行
        try:
            predictions = predictor.predict_race(race_id)
        except Exception as e:
            print(f"\n[WARNING] Race {race_id}: {e}")
            continue

        if not predictions:
            continue

        # トップ予測を取得
        top_pred = predictions[0]
        pit_number = top_pred['pit_number']
        confidence = top_pred.get('confidence', 'E')

        # パターン適用有無
        has_pattern = (
            'pattern_multiplier' in top_pred and
            top_pred.get('pattern_multiplier', 1.0) > 1.0
        )

        # パターン名を取得
        pattern_names = top_pred.get('applied_patterns', [])

        # 実際の勝者を取得
        cursor.execute("""
            SELECT pit_number
            FROM results
            WHERE race_id = ? AND rank = '1'
        """, (race_id,))

        winner_row = cursor.fetchone()
        if not winner_row:
            continue

        winner = winner_row[0]
        is_hit = (pit_number == winner)

        # 統計更新
        if has_pattern:
            overall_stats['with_pattern']['total'] += 1
            if is_hit:
                overall_stats['with_pattern']['hits'] += 1

            # パターン別統計
            for pattern_name in pattern_names:
                pattern_stats[pattern_name]['count'] += 1
                if is_hit:
                    pattern_stats[pattern_name]['hits'] += 1

            # 信頼度別統計
            confidence_stats[confidence]['with_pattern']['total'] += 1
            if is_hit:
                confidence_stats[confidence]['with_pattern']['hits'] += 1

            # 会場別統計
            venue_stats[venue_code]['with_pattern']['total'] += 1
            if is_hit:
                venue_stats[venue_code]['with_pattern']['hits'] += 1
        else:
            overall_stats['without_pattern']['total'] += 1
            if is_hit:
                overall_stats['without_pattern']['hits'] += 1

            confidence_stats[confidence]['without_pattern']['total'] += 1
            if is_hit:
                confidence_stats[confidence]['without_pattern']['hits'] += 1

            venue_stats[venue_code]['without_pattern']['total'] += 1
            if is_hit:
                venue_stats[venue_code]['without_pattern']['hits'] += 1

    print(f"\n処理完了: {total_races}レース\n")

    # 結果出力
    print("=" * 80)
    print("【全体統計】")
    print("=" * 80)

    with_total = overall_stats['with_pattern']['total']
    with_hits = overall_stats['with_pattern']['hits']
    without_total = overall_stats['without_pattern']['total']
    without_hits = overall_stats['without_pattern']['hits']

    print(f"総レース数: {total_races}")
    print()
    print(f"パターン適用あり: {with_total}レース ({100*with_total/total_races:.1f}%)")
    print(f"  的中数: {with_hits}")
    print(f"  的中率: {100*with_hits/with_total:.1f}%" if with_total > 0 else "  的中率: N/A")
    print()
    print(f"パターン適用なし: {without_total}レース ({100*without_total/total_races:.1f}%)")
    print(f"  的中数: {without_hits}")
    print(f"  的中率: {100*without_hits/without_total:.1f}%" if without_total > 0 else "  的中率: N/A")
    print()

    # 信頼度別統計
    print("=" * 80)
    print("【信頼度別統計】")
    print("=" * 80)

    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf not in confidence_stats:
            continue

        stats = confidence_stats[conf]
        with_total = stats['with_pattern']['total']
        with_hits = stats['with_pattern']['hits']
        without_total = stats['without_pattern']['total']
        without_hits = stats['without_pattern']['hits']

        print(f"\n信頼度 {conf}:")
        print(f"  パターンあり: {with_total}レース, {with_hits}的中 ({100*with_hits/with_total:.1f}%)" if with_total > 0 else f"  パターンあり: 0レース")
        print(f"  パターンなし: {without_total}レース, {without_hits}的中 ({100*without_hits/without_total:.1f}%)" if without_total > 0 else f"  パターンなし: 0レース")

        if with_total > 0 and without_total > 0:
            diff = (with_hits/with_total - without_hits/without_total) * 100
            print(f"  → パターン効果: {diff:+.1f}ポイント")

    # 会場別統計（上位10会場）
    print("\n" + "=" * 80)
    print("【会場別統計（上位10会場）】")
    print("=" * 80)

    venue_list = []
    for venue_code, stats in venue_stats.items():
        total = stats['with_pattern']['total'] + stats['without_pattern']['total']
        venue_list.append((venue_code, total, stats))

    venue_list.sort(key=lambda x: x[1], reverse=True)

    for venue_code, total, stats in venue_list[:10]:
        with_total = stats['with_pattern']['total']
        with_hits = stats['with_pattern']['hits']
        without_total = stats['without_pattern']['total']
        without_hits = stats['without_pattern']['hits']

        print(f"\n会場 {venue_code:02d}: {total}レース")
        print(f"  パターンあり: {with_total}レース, {with_hits}的中 ({100*with_hits/with_total:.1f}%)" if with_total > 0 else f"  パターンあり: 0レース")
        print(f"  パターンなし: {without_total}レース, {without_hits}的中 ({100*without_hits/without_total:.1f}%)" if without_total > 0 else f"  パターンなし: 0レース")

    # パターン別統計（上位20パターン）
    print("\n" + "=" * 80)
    print("【パターン別統計（上位20パターン）】")
    print("=" * 80)

    pattern_list = [(name, stats['count'], stats['hits'])
                    for name, stats in pattern_stats.items()]
    pattern_list.sort(key=lambda x: x[1], reverse=True)

    for name, count, hits in pattern_list[:20]:
        hit_rate = 100 * hits / count if count > 0 else 0
        print(f"{name:30s}: {count:4d}回適用, {hits:4d}回的中 ({hit_rate:5.1f}%)")

    conn.close()
    print("\n" + "=" * 80)


if __name__ == "__main__":
    analyze_patterns_long_term()
