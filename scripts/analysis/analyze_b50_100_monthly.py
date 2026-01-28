# -*- coding: utf-8 -*-
"""
B×50-100条件の月別パフォーマンス分析

現在の条件: 信頼度B、オッズ50-100倍、12/1/2月除外
検証目的: 4月除外の効果を確認

実行方法:
    python scripts/analysis/analyze_b50_100_monthly.py
"""

import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import sqlite3
from config.settings import DATABASE_PATH
from collections import defaultdict

def analyze_monthly_performance():
    """B×50-100条件の月別パフォーマンス分析"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # B×50-100条件のクエリ（冬季除外なし版）
    query = """
    SELECT
        r.race_date,
        strftime('%m', r.race_date) as month,
        strftime('%Y', r.race_date) as year,
        t.odds,
        CASE
            WHEN t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                              || CAST(rp2.pit_number AS TEXT) || '-'
                              || CAST(rp3.pit_number AS TEXT)
            THEN t.odds * 100
            ELSE 0
        END as payout
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.rank_prediction = 3
    JOIN trifecta_odds t ON r.id = t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                         || CAST(rp2.pit_number AS TEXT) || '-'
                         || CAST(rp3.pit_number AS TEXT)
    WHERE rp.confidence = 'B'
      AND t.odds >= 50 AND t.odds <= 100
      AND r.race_date >= '2020-01-01' AND r.race_date <= '2025-12-31'
    ORDER BY r.race_date
    """

    cursor.execute(query)
    results = cursor.fetchall()

    # 月別・年別の集計
    monthly_stats = defaultdict(lambda: {
        'count': 0,
        'hits': 0,
        'bet': 0,
        'return': 0
    })

    yearly_monthly_stats = defaultdict(lambda: defaultdict(lambda: {
        'count': 0,
        'hits': 0,
        'bet': 0,
        'return': 0
    }))

    for race_date, month, year, odds, payout in results:
        month = int(month)
        year = int(year)

        # 月別集計
        monthly_stats[month]['count'] += 1
        monthly_stats[month]['bet'] += 100
        monthly_stats[month]['return'] += payout
        if payout > 0:
            monthly_stats[month]['hits'] += 1

        # 年度別月別集計
        yearly_monthly_stats[year][month]['count'] += 1
        yearly_monthly_stats[year][month]['bet'] += 100
        yearly_monthly_stats[year][month]['return'] += payout
        if payout > 0:
            yearly_monthly_stats[year][month]['hits'] += 1

    conn.close()

    # 結果表示
    print("=" * 80)
    print("B×50-100条件の月別パフォーマンス分析（2020-2025年）")
    print("=" * 80)
    print()

    print("【全期間 月別サマリー】")
    print("-" * 80)
    print(f"{'月':>4s} | {'購入数':>6s} | {'的中':>4s} | {'的中率':>7s} | {'ROI':>7s} | {'収支':>10s}")
    print("-" * 80)

    for month in range(1, 13):
        if month in monthly_stats:
            stats = monthly_stats[month]
            hit_rate = stats['hits'] / stats['count'] * 100 if stats['count'] > 0 else 0
            roi = stats['return'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
            profit = stats['return'] - stats['bet']

            print(f"{month:4d} | {stats['count']:6d} | {stats['hits']:4d} | {hit_rate:6.1f}% | {roi:6.1f}% | {profit:+9,.0f}円")
        else:
            print(f"{month:4d} | {'--':>6s} | {'--':>4s} | {'--':>7s} | {'--':>7s} | {'--':>10s}")

    # 全体統計
    total_count = sum(s['count'] for s in monthly_stats.values())
    total_hits = sum(s['hits'] for s in monthly_stats.values())
    total_bet = sum(s['bet'] for s in monthly_stats.values())
    total_return = sum(s['return'] for s in monthly_stats.values())
    overall_hit_rate = total_hits / total_count * 100 if total_count > 0 else 0
    overall_roi = total_return / total_bet * 100 if total_bet > 0 else 0
    overall_profit = total_return - total_bet

    print("-" * 80)
    print(f"{'計':>4s} | {total_count:6d} | {total_hits:4d} | {overall_hit_rate:6.1f}% | {overall_roi:6.1f}% | {overall_profit:+9,.0f}円")
    print()

    # 4月の詳細分析
    print("【4月の年度別詳細】")
    print("-" * 80)
    print(f"{'年度':>6s} | {'購入数':>6s} | {'的中':>4s} | {'的中率':>7s} | {'ROI':>7s} | {'収支':>10s}")
    print("-" * 80)

    april_years = []
    for year in range(2020, 2026):
        if 4 in yearly_monthly_stats.get(str(year), {}):
            stats = yearly_monthly_stats[str(year)][4]
            hit_rate = stats['hits'] / stats['count'] * 100 if stats['count'] > 0 else 0
            roi = stats['return'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
            profit = stats['return'] - stats['bet']

            april_years.append({
                'year': year,
                'roi': roi,
                'profit': profit,
                'count': stats['count']
            })

            print(f"{year:6d} | {stats['count']:6d} | {stats['hits']:4d} | {hit_rate:6.1f}% | {roi:6.1f}% | {profit:+9,.0f}円")
        else:
            print(f"{year:6d} | {'--':>6s} | {'--':>4s} | {'--':>7s} | {'--':>7s} | {'--':>10s}")

    print()

    # 4月除外の効果試算
    if 4 in monthly_stats:
        april_stats = monthly_stats[4]

        print("【4月除外の効果試算】")
        print("-" * 80)

        # 4月を除外した場合の統計
        non_april_count = total_count - april_stats['count']
        non_april_hits = total_hits - april_stats['hits']
        non_april_bet = total_bet - april_stats['bet']
        non_april_return = total_return - april_stats['return']
        non_april_roi = non_april_return / non_april_bet * 100 if non_april_bet > 0 else 0
        non_april_profit = non_april_return - non_april_bet

        print(f"4月を含む場合:")
        print(f"  購入数: {total_count}件")
        print(f"  ROI: {overall_roi:.1f}%")
        print(f"  収支: {overall_profit:+,.0f}円")
        print()
        print(f"4月を除外した場合:")
        print(f"  購入数: {non_april_count}件")
        print(f"  ROI: {non_april_roi:.1f}%")
        print(f"  収支: {non_april_profit:+,.0f}円")
        print()
        print(f"効果:")
        print(f"  ROI改善: {non_april_roi - overall_roi:+.1f}pt")
        print(f"  収支改善: {non_april_profit - overall_profit:+,.0f}円")
        print()

        # 4月の年度別赤字年数をカウント
        losing_years = sum(1 for y in april_years if y['profit'] < 0)

        print(f"4月の赤字年数: {losing_years}/6年")
        if losing_years >= 5:
            print("判定: 【除外推奨】 6年中5年以上赤字")
        elif losing_years >= 4:
            print("判定: 【除外検討】 6年中4年以上赤字")
        elif losing_years >= 3:
            print("判定: 【慎重判断】 6年中3年赤字")
        else:
            print("判定: 【除外不要】 赤字年数が少ない")

    print()
    print("=" * 80)

if __name__ == '__main__':
    analyze_monthly_performance()
