# -*- coding: utf-8 -*-
"""
会場別フィルター詳細分析

会場を一律除外するのではなく、以下の条件で詳細分析:
1. 会場別×スコア帯別の的中率
2. 会場別×月別の的中率
3. サンプル数も考慮した判断
"""
import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config.settings import DATABASE_PATH, VENUES

def analyze_venue_score_patterns(start_date='2025-01-01', end_date='2025-12-31'):
    """会場別×スコア帯別の的中率分析"""

    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()

    # 全データ取得（BEFORE予測、信頼度B）
    cur.execute("""
        SELECT
            r.venue_code,
            rp.total_score,
            SUBSTR(r.race_date, 6, 2) as month,
            rp.race_id,
            (SELECT COUNT(*) FROM results res
             WHERE res.race_id = r.id
               AND res.pit_number = (
                   SELECT pit_number FROM race_predictions
                   WHERE race_id = r.id
                     AND prediction_type = 'before'
                     AND rank_prediction = 1
                   LIMIT 1
               )
               AND res.rank = 1) as is_hit
        FROM races r
        INNER JOIN race_predictions rp ON r.id = rp.race_id
        WHERE rp.prediction_type = 'before'
            AND rp.confidence = 'B'
            AND rp.rank_prediction = 1
            AND r.race_date >= ?
            AND r.race_date <= ?
    """, (start_date, end_date))

    data = cur.fetchall()

    # 会場名マッピング
    venue_names = {}
    for venue_id, venue_info in VENUES.items():
        venue_names[venue_info['code']] = venue_info['name']

    print("=" * 100)
    print("会場別×スコア帯別 的中率分析（2025年BEFORE予測）")
    print("=" * 100)

    # スコア帯の定義
    score_ranges = [
        (0, 80, "~80"),
        (80, 90, "80-90"),
        (90, 100, "90-100"),
        (100, 110, "100-110"),
        (110, 999, "110+")
    ]

    # 会場別×スコア帯別に集計
    stats = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'hits': 0}))

    for venue_code, score, month, race_id, is_hit in data:
        for min_s, max_s, range_name in score_ranges:
            if min_s <= score < max_s:
                stats[venue_code][range_name]['total'] += 1
                stats[venue_code][range_name]['hits'] += is_hit
                break

    # 結果表示（サンプル数10以上のみ）
    print(f"\n{'会場':8s} | {'スコア帯':10s} | {'件数':>6s} | {'的中':>6s} | {'的中率':>8s}")
    print("-" * 100)

    for venue_code in sorted(stats.keys()):
        venue_name = venue_names.get(venue_code, f"会場{venue_code}")

        for min_s, max_s, range_name in score_ranges:
            s = stats[venue_code][range_name]
            if s['total'] >= 10:  # サンプル数10以上
                hit_rate = s['hits'] / s['total'] * 100 if s['total'] > 0 else 0
                marker = " [!]" if hit_rate < 5.0 else ""
                print(f"{venue_name:8s} | {range_name:10s} | {s['total']:6d} | {s['hits']:6d} | {hit_rate:7.2f}%{marker}")

    print("\n" + "=" * 100)
    print("会場別×月別 的中率分析")
    print("=" * 100)

    # 会場別×月別に集計
    monthly_stats = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'hits': 0}))

    for venue_code, score, month, race_id, is_hit in data:
        monthly_stats[venue_code][month]['total'] += 1
        monthly_stats[venue_code][month]['hits'] += is_hit

    # 低的中率パターンを検出（サンプル数10以上）
    print(f"\n{'会場':8s} | {'月':>4s} | {'件数':>6s} | {'的中':>6s} | {'的中率':>8s}")
    print("-" * 100)

    low_hit_patterns = []

    for venue_code in sorted(monthly_stats.keys()):
        venue_name = venue_names.get(venue_code, f"会場{venue_code}")

        for month in sorted(monthly_stats[venue_code].keys()):
            s = monthly_stats[venue_code][month]
            if s['total'] >= 10:
                hit_rate = s['hits'] / s['total'] * 100 if s['total'] > 0 else 0
                if hit_rate < 5.0:
                    low_hit_patterns.append((venue_name, month, s['total'], s['hits'], hit_rate))
                    print(f"{venue_name:8s} | {month:>4s} | {s['total']:6d} | {s['hits']:6d} | {hit_rate:7.2f}% [!]")

    if not low_hit_patterns:
        print("  [サンプル数10以上で的中率5%未満のパターンなし]")

    conn.close()

    return low_hit_patterns


def analyze_monthly_patterns(start_date='2025-01-01', end_date='2025-12-31'):
    """月別の詳細パターン分析（複数年対応）"""

    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()

    # 年別×月別のデータ取得
    cur.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            SUBSTR(r.race_date, 6, 2) as month,
            rp.total_score,
            (SELECT COUNT(*) FROM results res
             WHERE res.race_id = r.id
               AND res.pit_number = (
                   SELECT pit_number FROM race_predictions
                   WHERE race_id = r.id
                     AND prediction_type = 'before'
                     AND rank_prediction = 1
                   LIMIT 1
               )
               AND res.rank = 1) as is_hit
        FROM races r
        INNER JOIN race_predictions rp ON r.id = rp.race_id
        WHERE rp.prediction_type = 'before'
            AND rp.confidence = 'B'
            AND rp.rank_prediction = 1
            AND r.race_date >= ?
            AND r.race_date <= ?
    """, (start_date, end_date))

    data = cur.fetchall()

    print("\n" + "=" * 100)
    print("年別×月別 的中率分析（サンプル数チェック）")
    print("=" * 100)

    # 年別×月別に集計
    yearly_monthly = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'hits': 0}))

    for year, month, score, is_hit in data:
        yearly_monthly[year][month]['total'] += 1
        yearly_monthly[year][month]['hits'] += is_hit

    print(f"\n{'年':>6s} | {'月':>4s} | {'件数':>6s} | {'的中':>6s} | {'的中率':>8s} | {'判定':10s}")
    print("-" * 100)

    for year in sorted(yearly_monthly.keys()):
        for month in sorted(yearly_monthly[year].keys()):
            s = yearly_monthly[year][month]
            hit_rate = s['hits'] / s['total'] * 100 if s['total'] > 0 else 0

            # 判定
            if s['total'] < 10:
                judgment = "データ不足"
            elif hit_rate < 5.0:
                judgment = "要注意"
            else:
                judgment = "OK"

            marker = " [!]" if s['total'] < 10 else ""
            print(f"{year:>6s} | {month:>4s} | {s['total']:6d} | {s['hits']:6d} | {hit_rate:7.2f}% | {judgment:10s}{marker}")

    conn.close()


if __name__ == '__main__':
    print("2025年データで詳細分析開始...\n")

    # 会場別詳細分析
    low_patterns = analyze_venue_score_patterns('2025-01-01', '2025-12-31')

    # 月別詳細分析
    analyze_monthly_patterns('2025-01-01', '2025-12-31')

    print("\n" + "=" * 100)
    print("分析完了")
    print("=" * 100)
