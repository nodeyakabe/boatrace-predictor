#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
オッズ10倍未満の全会場分析
戸田競艇場で成功した条件を他会場にも適用できるか調査
"""
import sqlite3
import sys
import io
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATABASE_PATH = 'data/boatrace.db'

VENUE_NAMES = {
    '1': '桐生', '2': '戸田', '3': '江戸川', '4': '平和島', '5': '多摩川',
    '6': '浜名湖', '7': '蒲郡', '8': '常滑', '9': '津', '10': '三国',
    '11': 'びわこ', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀',
    '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}

def analyze_all_venues():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("="*80)
    print("オッズ10倍未満の全会場分析")
    print("="*80)
    print()
    print(f"分析開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # ========================================
    # 1. 信頼度A × オッズ10倍未満（全会場）
    # ========================================
    print("【1】信頼度A × オッズ10倍未満（全会場）")
    print("="*80)
    print()

    cursor.execute('''
        SELECT
            r.venue_code,
            COUNT(DISTINCT rp.race_id) as race_count,
            COUNT(DISTINCT CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN rp.race_id
            END) as hit_count,
            ROUND(100.0 * COUNT(DISTINCT CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN rp.race_id
            END) / COUNT(DISTINCT rp.race_id), 2) as hit_rate,
            SUM(400) as investment,
            SUM(CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN t.odds * 400
                ELSE 0
            END) as returns,
            ROUND(100.0 * SUM(CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN t.odds * 400
                ELSE 0
            END) / SUM(400), 2) as roi,
            SUM(CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN t.odds * 400
                ELSE 0
            END) - SUM(400) as profit,
            ROUND(AVG(t.odds), 2) as avg_odds
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN race_predictions rp1 ON rp.race_id = rp1.race_id
            AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        LEFT JOIN race_predictions rp2 ON rp.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        LEFT JOIN race_predictions rp3 ON rp.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        LEFT JOIN results res1 ON rp.race_id = res1.race_id AND rp1.pit_number = res1.pit_number
        LEFT JOIN results res2 ON rp.race_id = res2.race_id AND rp2.pit_number = res2.pit_number
        LEFT JOIN results res3 ON rp.race_id = res3.race_id AND rp3.pit_number = res3.pit_number
        LEFT JOIN trifecta_odds t ON rp.race_id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                              || CAST(rp2.pit_number AS TEXT) || '-'
                              || CAST(rp3.pit_number AS TEXT)
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 1
        AND rp.confidence = 'A'
        AND t.odds < 10
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        GROUP BY r.venue_code
        HAVING COUNT(DISTINCT rp.race_id) >= 50
        ORDER BY roi DESC
    ''')

    print(f"{'順位':<4} {'会場':<10} {'レース':<8} {'的中率':<8} {'ROI':<10} {'収支':<12} {'平均オッズ':<10} {'評価':<10}")
    print("-"*90)

    rank = 1
    conf_a_results = []
    for row in cursor.fetchall():
        venue, races, hits, hit_rate, inv, ret, roi, profit, avg_odds = row
        venue_name = VENUE_NAMES.get(str(venue), f"会場{venue}")

        # 評価基準
        if roi >= 120 and races >= 100:
            evaluation = "✅ 採用候補"
        elif roi >= 120:
            evaluation = "△ 要検証"
        else:
            evaluation = "❌ 不採用"

        print(f"{rank:<4} {venue_name:<10} {races:>6}件  {hit_rate:>5.1f}%   {roi:>6.1f}%   {profit:>+9,.0f}円   {avg_odds:>5.1f}倍    {evaluation}")

        conf_a_results.append({
            'venue': venue_name,
            'venue_code': venue,
            'races': races,
            'roi': roi,
            'profit': profit,
            'evaluation': evaluation
        })

        rank += 1

    print()

    # ========================================
    # 2. 信頼度B × オッズ10倍未満（全会場）
    # ========================================
    print("【2】信頼度B × オッズ10倍未満（全会場）")
    print("="*80)
    print()

    cursor.execute('''
        SELECT
            r.venue_code,
            COUNT(DISTINCT rp.race_id) as race_count,
            COUNT(DISTINCT CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN rp.race_id
            END) as hit_count,
            ROUND(100.0 * COUNT(DISTINCT CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN rp.race_id
            END) / COUNT(DISTINCT rp.race_id), 2) as hit_rate,
            SUM(400) as investment,
            SUM(CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN t.odds * 400
                ELSE 0
            END) as returns,
            ROUND(100.0 * SUM(CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN t.odds * 400
                ELSE 0
            END) / SUM(400), 2) as roi,
            SUM(CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN t.odds * 400
                ELSE 0
            END) - SUM(400) as profit,
            ROUND(AVG(t.odds), 2) as avg_odds
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN race_predictions rp1 ON rp.race_id = rp1.race_id
            AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        LEFT JOIN race_predictions rp2 ON rp.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        LEFT JOIN race_predictions rp3 ON rp.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        LEFT JOIN results res1 ON rp.race_id = res1.race_id AND rp1.pit_number = res1.pit_number
        LEFT JOIN results res2 ON rp.race_id = res2.race_id AND rp2.pit_number = res2.pit_number
        LEFT JOIN results res3 ON rp.race_id = res3.race_id AND rp3.pit_number = res3.pit_number
        LEFT JOIN trifecta_odds t ON rp.race_id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                              || CAST(rp2.pit_number AS TEXT) || '-'
                              || CAST(rp3.pit_number AS TEXT)
        WHERE rp.prediction_type = 'before'
        AND rp.rank_prediction = 1
        AND rp.confidence = 'B'
        AND t.odds < 10
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        GROUP BY r.venue_code
        HAVING COUNT(DISTINCT rp.race_id) >= 50
        ORDER BY roi DESC
    ''')

    print(f"{'順位':<4} {'会場':<10} {'レース':<8} {'的中率':<8} {'ROI':<10} {'収支':<12} {'平均オッズ':<10} {'評価':<10}")
    print("-"*90)

    rank = 1
    conf_b_results = []
    for row in cursor.fetchall():
        venue, races, hits, hit_rate, inv, ret, roi, profit, avg_odds = row
        venue_name = VENUE_NAMES.get(str(venue), f"会場{venue}")

        # 評価基準
        if roi >= 120 and races >= 100:
            evaluation = "✅ 採用候補"
        elif roi >= 120:
            evaluation = "△ 要検証"
        else:
            evaluation = "❌ 不採用"

        print(f"{rank:<4} {venue_name:<10} {races:>6}件  {hit_rate:>5.1f}%   {roi:>6.1f}%   {profit:>+9,.0f}円   {avg_odds:>5.1f}倍    {evaluation}")

        conf_b_results.append({
            'venue': venue_name,
            'venue_code': venue,
            'races': races,
            'roi': roi,
            'profit': profit,
            'evaluation': evaluation
        })

        rank += 1

    print()

    # ========================================
    # 3. サマリー
    # ========================================
    print("="*80)
    print("【サマリー】")
    print("="*80)
    print()

    print("■ 採用候補（ROI 120%以上、サンプル100件以上）")
    print("-"*60)

    candidates_a = [r for r in conf_a_results if r['evaluation'] == "✅ 採用候補"]
    candidates_b = [r for r in conf_b_results if r['evaluation'] == "✅ 採用候補"]

    print(f"【信頼度A】{len(candidates_a)}会場")
    for c in candidates_a:
        print(f"  - {c['venue']}: ROI {c['roi']:.1f}%, 収支 {c['profit']:+,.0f}円 ({c['races']}件)")

    print()
    print(f"【信頼度B】{len(candidates_b)}会場")
    for c in candidates_b:
        print(f"  - {c['venue']}: ROI {c['roi']:.1f}%, 収支 {c['profit']:+,.0f}円 ({c['races']}件)")

    print()
    print(f"合計: {len(candidates_a) + len(candidates_b)}会場が採用候補")
    print()

    print("■ 要検証（ROI 120%以上、サンプル50-99件）")
    print("-"*60)

    verify_a = [r for r in conf_a_results if r['evaluation'] == "△ 要検証"]
    verify_b = [r for r in conf_b_results if r['evaluation'] == "△ 要検証"]

    print(f"信頼度A: {len(verify_a)}会場")
    print(f"信頼度B: {len(verify_b)}会場")
    print(f"→ データ補完後に再評価推奨")
    print()

    conn.close()

    print("="*80)
    print("分析完了")
    print("="*80)
    print(f"分析終了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

if __name__ == '__main__':
    analyze_all_venues()
