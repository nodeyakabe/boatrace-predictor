# -*- coding: utf-8 -*-
"""
D×40-50×B1×2連率20-30%条件の会場別ROI分析

現在の条件: D×B1級×40-50倍×1コース2連率20-30%
検証目的: 黒字会場のみに限定する効果を確認

実行方法:
    python scripts/analysis/analyze_d40_50_venue_roi.py
"""

import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import sqlite3
from config.settings import DATABASE_PATH
from collections import defaultdict

# 会場名マッピング
VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: 'びわこ', 12: 'びわこ',
    13: '住之江', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

def analyze_venue_roi():
    """D×40-50×B1×2連率20-30%条件の会場別ROI分析"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # D×40-50×B1×2連率20-30%条件のクエリ（standard_backtest.pyと同じ構造）
    query = """
    SELECT
        r.venue_code,
        r.race_date,
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
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e_c1 ON r.id = e_c1.race_id AND e_c1.pit_number = 1
    JOIN trifecta_odds t ON r.id = t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                         || CAST(rp2.pit_number AS TEXT) || '-'
                         || CAST(rp3.pit_number AS TEXT)
    WHERE rp.rank_prediction = 1
      AND rp.confidence = 'D'
      AND t.odds >= 40 AND t.odds < 50
      AND e_c1.racer_rank = 'B1'
      AND e_c1.second_rate >= 20 AND e_c1.second_rate < 30
      AND r.race_date >= '2020-01-01' AND r.race_date <= '2025-12-31'
    ORDER BY r.venue_code, r.race_date
    """

    cursor.execute(query)
    results = cursor.fetchall()

    # 会場別集計
    venue_stats = defaultdict(lambda: {
        'count': 0,
        'hits': 0,
        'bet': 0,
        'return': 0,
        'years': set()
    })

    # 会場別・年度別集計
    venue_year_stats = defaultdict(lambda: defaultdict(lambda: {
        'count': 0,
        'hits': 0,
        'bet': 0,
        'return': 0
    }))

    for venue_code, race_date, year, odds, payout in results:
        venue_code = int(venue_code)
        year = int(year)

        # 会場別集計
        venue_stats[venue_code]['count'] += 1
        venue_stats[venue_code]['bet'] += 100
        venue_stats[venue_code]['return'] += payout
        venue_stats[venue_code]['years'].add(year)
        if payout > 0:
            venue_stats[venue_code]['hits'] += 1

        # 会場別・年度別集計
        venue_year_stats[venue_code][year]['count'] += 1
        venue_year_stats[venue_code][year]['bet'] += 100
        venue_year_stats[venue_code][year]['return'] += payout
        if payout > 0:
            venue_year_stats[venue_code][year]['hits'] += 1

    conn.close()

    # 結果表示
    print("=" * 100)
    print("D×40-50×B1×2連率20-30%条件の会場別ROI分析（2020-2025年）")
    print("=" * 100)
    print()

    # 全体サマリー
    total_count = sum(s['count'] for s in venue_stats.values())
    total_hits = sum(s['hits'] for s in venue_stats.values())
    total_bet = sum(s['bet'] for s in venue_stats.values())
    total_return = sum(s['return'] for s in venue_stats.values())
    overall_hit_rate = total_hits / total_count * 100 if total_count > 0 else 0
    overall_roi = total_return / total_bet * 100 if total_bet > 0 else 0
    overall_profit = total_return - total_bet

    print(f"【全体サマリー】")
    print(f"  購入数: {total_count}件")
    print(f"  的中: {total_hits}件")
    print(f"  的中率: {overall_hit_rate:.1f}%")
    print(f"  ROI: {overall_roi:.1f}%")
    print(f"  収支: {overall_profit:+,.0f}円")
    print()

    # 会場別サマリー（ROI降順）
    print("【会場別ROIサマリー】")
    print("-" * 100)
    print(f"{'会場':>6s} | {'購入数':>6s} | {'的中':>4s} | {'的中率':>7s} | {'ROI':>7s} | {'収支':>10s} | {'出現年数':>8s}")
    print("-" * 100)

    # ROI順にソート
    sorted_venues = sorted(venue_stats.items(), key=lambda x: x[1]['return'] / x[1]['bet'] if x[1]['bet'] > 0 else 0, reverse=True)

    profitable_venues = []
    for venue_code, stats in sorted_venues:
        venue_name = VENUE_NAMES.get(venue_code, f'不明{venue_code:02d}')
        hit_rate = stats['hits'] / stats['count'] * 100 if stats['count'] > 0 else 0
        roi = stats['return'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
        profit = stats['return'] - stats['bet']

        # 黒字会場かどうか
        is_profitable = profit > 0

        marker = '○' if is_profitable else '×'
        print(f"{venue_name:>6s} | {stats['count']:6d} | {stats['hits']:4d} | {hit_rate:6.1f}% | {roi:6.1f}% | {profit:+9,.0f}円 | {len(stats['years'])}年 {marker}")

        if is_profitable:
            profitable_venues.append(venue_code)

    print()

    # 黒字会場のみに限定した場合の試算
    if profitable_venues:
        print("【黒字会場のみに限定した場合の試算】")
        print("-" * 100)

        # 黒字会場のデータを集計
        filtered_count = sum(venue_stats[v]['count'] for v in profitable_venues)
        filtered_hits = sum(venue_stats[v]['hits'] for v in profitable_venues)
        filtered_bet = sum(venue_stats[v]['bet'] for v in profitable_venues)
        filtered_return = sum(venue_stats[v]['return'] for v in profitable_venues)
        filtered_roi = filtered_return / filtered_bet * 100 if filtered_bet > 0 else 0
        filtered_profit = filtered_return - filtered_bet

        print(f"現状（全会場）:")
        print(f"  購入数: {total_count}件")
        print(f"  ROI: {overall_roi:.1f}%")
        print(f"  収支: {overall_profit:+,.0f}円")
        print()
        print(f"黒字会場のみに限定:")
        print(f"  購入数: {filtered_count}件 ({filtered_count/total_count*100:.1f}%)")
        print(f"  ROI: {filtered_roi:.1f}%")
        print(f"  収支: {filtered_profit:+,.0f}円")
        print()
        print(f"効果:")
        print(f"  ROI改善: {filtered_roi - overall_roi:+.1f}pt")
        print(f"  収支改善: {filtered_profit - overall_profit:+,.0f}円")
        print()

        # 黒字会場リスト
        print(f"黒字会場（{len(profitable_venues)}会場）:")
        venue_names_str = ', '.join([f"{VENUE_NAMES.get(v, f'不明{v:02d}')}({v:02d})" for v in sorted(profitable_venues)])
        print(f"  {venue_names_str}")
        print()

        # 年度別の黒字年数を確認
        print("【黒字会場の年度別パフォーマンス】")
        print("-" * 100)

        yearly_profits = defaultdict(int)
        for venue_code in profitable_venues:
            for year in range(2020, 2026):
                if year in venue_year_stats[venue_code]:
                    stats = venue_year_stats[venue_code][year]
                    profit = stats['return'] - stats['bet']
                    yearly_profits[year] += profit

        profitable_years = sum(1 for profit in yearly_profits.values() if profit > 0)

        print(f"{'年度':>6s} | {'購入数':>6s} | {'ROI':>7s} | {'収支':>10s} | {'判定':>4s}")
        print("-" * 100)

        for year in range(2020, 2026):
            if yearly_profits[year] != 0 or any(venue_code in venue_year_stats and year in venue_year_stats[venue_code] for venue_code in profitable_venues):
                # 購入数を計算
                year_count = sum(venue_year_stats[v][year]['count'] for v in profitable_venues if year in venue_year_stats[v])
                year_bet = sum(venue_year_stats[v][year]['bet'] for v in profitable_venues if year in venue_year_stats[v])
                year_return = sum(venue_year_stats[v][year]['return'] for v in profitable_venues if year in venue_year_stats[v])
                year_roi = year_return / year_bet * 100 if year_bet > 0 else 0
                year_profit = yearly_profits[year]

                marker = '黒字' if year_profit > 0 else '赤字'
                print(f"{year:6d} | {year_count:6d} | {year_roi:6.1f}% | {year_profit:+9,.0f}円 | {marker:>4s}")

        print("-" * 100)
        print(f"黒字年数: {profitable_years}/6年")
        print()

        # 採用判定
        if profitable_years >= 4 and filtered_roi >= 100:
            print("判定: 【採用推奨】 黒字年数4/6年以上、ROI 100%以上")
        elif profitable_years >= 4:
            print("判定: 【要慎重検討】 黒字年数4/6年以上だがROI 100%未満")
        elif filtered_roi >= 150:
            print("判定: 【要慎重検討】 ROI 150%以上だが黒字年数不足")
        else:
            print("判定: 【不採用】 採用基準未達")

    else:
        print("黒字会場がありません。")

    print()
    print("=" * 100)

if __name__ == '__main__':
    analyze_venue_roi()
