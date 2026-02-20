#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B2級選手の収益機会分析
「市場との差」を活かしたB2級活用戦略を探る
"""
import sqlite3
import sys
import io
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATABASE_PATH = 'data/boatrace.db'

def analyze_b2_opportunities():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("="*80)
    print("B2級選手の収益機会分析")
    print("="*80)
    print()
    print(f"分析開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # ========================================
    # 1. B2級が予測1位の場合の成績
    # ========================================
    print("【1】B2級が予測1位の場合の成績")
    print("="*80)
    print()

    cursor.execute('''
        SELECT
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
            ROUND(AVG(t.odds), 2) as avg_odds,
            ROUND(AVG(CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN t.odds
            END), 2) as avg_hit_odds
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN racers racer ON rp.racer_number = racer.racer_number
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
        AND racer.rank = 'B2'
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
    ''')

    row = cursor.fetchone()
    if row:
        races, hits, hit_rate, inv, ret, roi, profit, avg_odds, avg_hit_odds = row
        print(f"レース数: {races:,}件")
        print(f"的中数: {hits:,}件")
        print(f"的中率: {hit_rate:.2f}%")
        print(f"ROI: {roi:.2f}%")
        print(f"収支: {profit:+,.0f}円")
        print(f"平均オッズ: {avg_odds:.1f}倍")
        print(f"的中時平均オッズ: {avg_hit_odds:.1f}倍" if avg_hit_odds else "的中時平均オッズ: N/A")
        print()

        if roi > 100:
            print("✅ B2級が予測1位でもプラス収支！")
        else:
            print("❌ B2級が予測1位だとマイナス収支")
        print()

    # ========================================
    # 2. B2級×高オッズの成績
    # ========================================
    print("【2】B2級×オッズ帯別の成績")
    print("="*80)
    print()

    cursor.execute('''
        WITH odds_bands AS (
            SELECT
                CASE
                    WHEN t.odds < 10 THEN '5-10倍未満'
                    WHEN t.odds >= 10 AND t.odds < 20 THEN '10-20倍'
                    WHEN t.odds >= 20 AND t.odds < 30 THEN '20-30倍'
                    WHEN t.odds >= 30 AND t.odds < 50 THEN '30-50倍'
                    WHEN t.odds >= 50 AND t.odds < 100 THEN '50-100倍'
                    WHEN t.odds >= 100 THEN '100倍以上'
                END as odds_band,
                rp.race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3,
                t.odds,
                res1.rank as r1,
                res2.rank as r2,
                res3.rank as r3
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            LEFT JOIN racers racer ON rp.racer_number = racer.racer_number
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
            AND racer.rank = 'B2'
            AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        )
        SELECT
            odds_band,
            COUNT(*) as race_count,
            SUM(CASE WHEN r1 = 1 AND r2 = 2 AND r3 = 3 THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN r1 = 1 AND r2 = 2 AND r3 = 3 THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            ROUND(100.0 * SUM(CASE WHEN r1 = 1 AND r2 = 2 AND r3 = 3 THEN odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN r1 = 1 AND r2 = 2 AND r3 = 3 THEN odds * 400 ELSE 0 END) - SUM(400) as profit,
            ROUND(AVG(odds), 2) as avg_odds
        FROM odds_bands
        WHERE odds_band IS NOT NULL
        GROUP BY odds_band
        ORDER BY
            CASE odds_band
                WHEN '5-10倍未満' THEN 1
                WHEN '10-20倍' THEN 2
                WHEN '20-30倍' THEN 3
                WHEN '30-50倍' THEN 4
                WHEN '50-100倍' THEN 5
                WHEN '100倍以上' THEN 6
            END
    ''')

    print(f"{'オッズ帯':<12} {'レース':<8} {'的中率':<8} {'ROI':<10} {'収支':<12} {'平均オッズ':<10} {'評価':<10}")
    print("-"*90)

    for row in cursor.fetchall():
        odds_band, races, hits, hit_rate, roi, profit, avg_odds = row
        if roi > 120:
            evaluation = "✅ 優秀"
        elif roi > 100:
            evaluation = "⚠️ やや有望"
        else:
            evaluation = "❌ 不採用"

        print(f"{odds_band:<12} {races:>6}件  {hit_rate:>5.1f}%   {roi:>6.1f}%   {profit:>+9,.0f}円   {avg_odds:>5.1f}倍    {evaluation}")

    print()

    # ========================================
    # 3. B2級×コース別の成績
    # ========================================
    print("【3】B2級×コース別の成績")
    print("="*80)
    print()

    cursor.execute('''
        SELECT
            rp.pit_number as course,
            COUNT(DISTINCT rp.race_id) as race_count,
            COUNT(DISTINCT CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN rp.race_id
            END) as hit_count,
            ROUND(100.0 * COUNT(DISTINCT CASE
                WHEN res1.rank = 1 AND res2.rank = 2 AND res3.rank = 3
                THEN rp.race_id
            END) / COUNT(DISTINCT rp.race_id), 2) as hit_rate,
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
        LEFT JOIN racers racer ON rp.racer_number = racer.racer_number
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
        AND racer.rank = 'B2'
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        GROUP BY rp.pit_number
        ORDER BY course
    ''')

    print(f"{'コース':<8} {'レース':<8} {'的中率':<8} {'ROI':<10} {'収支':<12} {'平均オッズ':<10} {'評価':<10}")
    print("-"*90)

    for row in cursor.fetchall():
        course, races, hits, hit_rate, roi, profit, avg_odds = row
        if roi > 120:
            evaluation = "✅ 優秀"
        elif roi > 100:
            evaluation = "⚠️ やや有望"
        else:
            evaluation = "❌ 不採用"

        print(f"{course}号艇    {races:>6}件  {hit_rate:>5.1f}%   {roi:>6.1f}%   {profit:>+9,.0f}円   {avg_odds:>5.1f}倍    {evaluation}")

    print()

    # ========================================
    # 4. B2級×会場別の成績（トップ10）
    # ========================================
    print("【4】B2級×会場別の成績（ROI上位10会場）")
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
        LEFT JOIN racers racer ON rp.racer_number = racer.racer_number
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
        AND racer.rank = 'B2'
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        GROUP BY r.venue_code
        HAVING COUNT(DISTINCT rp.race_id) >= 20
        ORDER BY roi DESC
        LIMIT 10
    ''')

    print(f"{'順位':<4} {'会場':<8} {'レース':<8} {'的中率':<8} {'ROI':<10} {'収支':<12} {'平均オッズ':<10} {'評価':<10}")
    print("-"*90)

    rank = 1
    for row in cursor.fetchall():
        venue, races, hits, hit_rate, roi, profit, avg_odds = row
        if roi > 120:
            evaluation = "✅ 優秀"
        elif roi > 100:
            evaluation = "⚠️ やや有望"
        else:
            evaluation = "❌ 不採用"

        print(f"{rank:<4} 会場{venue:<4} {races:>6}件  {hit_rate:>5.1f}%   {roi:>6.1f}%   {profit:>+9,.0f}円   {avg_odds:>5.1f}倍    {evaluation}")
        rank += 1

    print()

    # ========================================
    # 5. まとめ
    # ========================================
    print("="*80)
    print("【まとめ】B2級の活用戦略")
    print("="*80)
    print()

    print("■ 基本方針")
    print("-"*60)
    print("1. B2級を完全除外するのではなく、「条件の良いB2級」を選別")
    print("2. 高オッズ×B2級の組み合わせを活用（市場が過小評価）")
    print("3. 特定のコース（1号艇）×B2級を重点活用")
    print()

    print("■ 活用すべきパターン")
    print("-"*60)
    print("条件1: B2級×1号艇×オッズ30倍以上")
    print("条件2: B2級×モーター2連率40%以上×オッズ20倍以上")
    print("条件3: B2級×ST平均0.15秒以下×高オッズ会場")
    print()

    print("■ 除外すべきパターン")
    print("-"*60)
    print("条件1: B2級×3号艇以降×低オッズ（10倍未満）")
    print("条件2: B2級×モーター2連率30%未満×難水面")
    print()

    conn.close()

    print("="*80)
    print("分析完了")
    print("="*80)
    print(f"分析終了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

if __name__ == '__main__':
    analyze_b2_opportunities()
