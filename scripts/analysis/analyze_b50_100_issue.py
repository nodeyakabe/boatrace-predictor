# -*- coding: utf-8 -*-
"""
B×50-100条件の1着的中率が低い原因を深掘り分析

分析項目:
1. B予想全体 vs B×50-100の比較
2. 6コース予測のROI検証
3. 会場×環境データの深掘り
4. 改善提案
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH


def get_db_connection():
    """データベース接続を取得"""
    return sqlite3.connect(DATABASE_PATH)


def analyze_b_prediction_overall():
    """B予想全体の1着的中率を確認"""
    print("=" * 80)
    print("【分析1】B予想全体 vs B×50-100の比較")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # B予想全体の1着的中率（before予測、2020-2025年）
    query = """
    SELECT
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) as first_hit,
        ROUND(100.0 * SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) / COUNT(*), 2) as first_hit_rate
    FROM races ra
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    """
    cursor.execute(query)
    result = cursor.fetchone()
    print(f"\n■ B予想全体（信頼度B、before予測、2020-2025年）")
    print(f"  総レース数: {result[0]:,}件")
    print(f"  1着的中: {result[1]:,}件")
    print(f"  1着的中率: {result[2]:.1f}%")

    # B×50-100の1着的中率
    query = """
    SELECT
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) as first_hit,
        ROUND(100.0 * SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) / COUNT(*), 2) as first_hit_rate
    FROM races ra
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    """
    cursor.execute(query)
    result = cursor.fetchone()
    print(f"\n■ B×50-100（信頼度B、オッズ50-100倍）")
    print(f"  総レース数: {result[0]:,}件")
    print(f"  1着的中: {result[1]:,}件")
    print(f"  1着的中率: {result[2]:.1f}%")

    # オッズ帯別の1着的中率
    print(f"\n■ オッズ帯別 1着的中率（信頼度B）")
    print("-" * 60)

    odds_ranges = [
        (1, 10, "1-10倍"),
        (10, 20, "10-20倍"),
        (20, 30, "20-30倍"),
        (30, 50, "30-50倍"),
        (50, 100, "50-100倍"),
        (100, 200, "100-200倍"),
        (200, 9999, "200倍以上")
    ]

    for min_odds, max_odds, label in odds_ranges:
        query = f"""
        SELECT
            COUNT(*) as total_races,
            SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) as first_hit,
            ROUND(100.0 * SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as first_hit_rate,
            ROUND(AVG(t.odds), 1) as avg_odds
        FROM races ra
        JOIN race_predictions p1 ON ra.id = p1.race_id
            AND p1.prediction_type = 'before'
            AND p1.rank_prediction = 1
            AND p1.confidence = 'B'
        JOIN race_predictions p2 ON ra.id = p2.race_id
            AND p2.prediction_type = 'before'
            AND p2.rank_prediction = 2
        JOIN race_predictions p3 ON ra.id = p3.race_id
            AND p3.prediction_type = 'before'
            AND p3.rank_prediction = 3
        JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
        JOIN trifecta_odds t ON ra.id = t.race_id
            AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
        WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
            AND t.odds >= {min_odds} AND t.odds < {max_odds}
        """
        cursor.execute(query)
        result = cursor.fetchone()
        if result[0] > 0:
            print(f"  {label:12s}: {result[0]:5,}件, 1着的中 {result[2]:5.1f}%, 平均オッズ {result[3]:6.1f}倍")

    conn.close()


def analyze_predicted_course_distribution():
    """B×50-100で予測1着のコース分布を分析"""
    print("\n" + "=" * 80)
    print("【分析2】B×50-100における予測1着コースと実際の1着の分析")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 予測1着コース別の分析
    print(f"\n■ 予測1着コース別の1着的中率（B×50-100）")
    print("-" * 70)

    for course in range(1, 7):
        query = f"""
        SELECT
            COUNT(*) as total_races,
            SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) as first_hit,
            ROUND(100.0 * SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as first_hit_rate
        FROM races ra
        JOIN race_predictions p1 ON ra.id = p1.race_id
            AND p1.prediction_type = 'before'
            AND p1.rank_prediction = 1
            AND p1.confidence = 'B'
            AND p1.pit_number = {course}
        JOIN race_predictions p2 ON ra.id = p2.race_id
            AND p2.prediction_type = 'before'
            AND p2.rank_prediction = 2
        JOIN race_predictions p3 ON ra.id = p3.race_id
            AND p3.prediction_type = 'before'
            AND p3.rank_prediction = 3
        JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
        JOIN trifecta_odds t ON ra.id = t.race_id
            AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
        WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
            AND t.odds >= 50 AND t.odds < 100
        """
        cursor.execute(query)
        result = cursor.fetchone()
        if result[0] > 0:
            print(f"  {course}コース予測1着: {result[0]:5,}件, 1着的中 {result[2]:5.1f}%")

    # 6コース予測のROI検証（パターンH: 3点買い400円）
    print(f"\n■ 6コース予測時のROI検証（B×50-100、パターンH）")
    print("-" * 70)

    query = """
    SELECT
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p2.pit_number
                  AND r3.pit_number = p3.pit_number THEN 1 ELSE 0 END) as trifecta_hit,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p2.pit_number
                  AND r3.pit_number = p3.pit_number THEN t.odds * 200 ELSE 0 END) as return_main,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p3.pit_number
                  AND r3.pit_number = p2.pit_number THEN t2.odds * 100 ELSE 0 END) as return_sub1,
        SUM(CASE WHEN r1.pit_number = p2.pit_number
                  AND r2.pit_number = p1.pit_number
                  AND r3.pit_number = p3.pit_number THEN t3.odds * 100 ELSE 0 END) as return_sub2
    FROM races ra
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
        AND p1.pit_number = 6
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN results r2 ON ra.id = r2.race_id AND r2.rank = '2'
    JOIN results r3 ON ra.id = r3.race_id AND r3.rank = '3'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    LEFT JOIN trifecta_odds t2 ON ra.id = t2.race_id
        AND t2.combination = printf('%d-%d-%d', p1.pit_number, p3.pit_number, p2.pit_number)
    LEFT JOIN trifecta_odds t3 ON ra.id = t3.race_id
        AND t3.combination = printf('%d-%d-%d', p2.pit_number, p1.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    """
    cursor.execute(query)
    result = cursor.fetchone()

    total = result[0]
    trifecta_hit = result[1]
    total_return = (result[2] or 0) + (result[3] or 0) + (result[4] or 0)
    investment = total * 400
    roi = 100.0 * total_return / investment if investment > 0 else 0

    print(f"  6コース予測のみ: {total:,}件")
    print(f"  三連単的中: {trifecta_hit}件")
    print(f"  投資額: {investment:,}円")
    print(f"  回収額: {total_return:,.0f}円")
    print(f"  ROI: {roi:.1f}%")

    # 全コースのROI比較
    print(f"\n■ 予測1着コース別ROI（B×50-100、パターンH）")
    print("-" * 70)

    for course in range(1, 7):
        query = f"""
        SELECT
            COUNT(*) as total_races,
            SUM(CASE WHEN r1.pit_number = p1.pit_number
                      AND r2.pit_number = p2.pit_number
                      AND r3.pit_number = p3.pit_number THEN t.odds * 200 ELSE 0 END) +
            SUM(CASE WHEN r1.pit_number = p1.pit_number
                      AND r2.pit_number = p3.pit_number
                      AND r3.pit_number = p2.pit_number THEN COALESCE(t2.odds, 0) * 100 ELSE 0 END) +
            SUM(CASE WHEN r1.pit_number = p2.pit_number
                      AND r2.pit_number = p1.pit_number
                      AND r3.pit_number = p3.pit_number THEN COALESCE(t3.odds, 0) * 100 ELSE 0 END) as total_return
        FROM races ra
        JOIN race_predictions p1 ON ra.id = p1.race_id
            AND p1.prediction_type = 'before'
            AND p1.rank_prediction = 1
            AND p1.confidence = 'B'
            AND p1.pit_number = {course}
        JOIN race_predictions p2 ON ra.id = p2.race_id
            AND p2.prediction_type = 'before'
            AND p2.rank_prediction = 2
        JOIN race_predictions p3 ON ra.id = p3.race_id
            AND p3.prediction_type = 'before'
            AND p3.rank_prediction = 3
        JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
        JOIN results r2 ON ra.id = r2.race_id AND r2.rank = '2'
        JOIN results r3 ON ra.id = r3.race_id AND r3.rank = '3'
        JOIN trifecta_odds t ON ra.id = t.race_id
            AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
        LEFT JOIN trifecta_odds t2 ON ra.id = t2.race_id
            AND t2.combination = printf('%d-%d-%d', p1.pit_number, p3.pit_number, p2.pit_number)
        LEFT JOIN trifecta_odds t3 ON ra.id = t3.race_id
            AND t3.combination = printf('%d-%d-%d', p2.pit_number, p1.pit_number, p3.pit_number)
        WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
            AND t.odds >= 50 AND t.odds < 100
        """
        cursor.execute(query)
        result = cursor.fetchone()
        if result[0] > 0:
            total = result[0]
            total_return = result[1] or 0
            investment = total * 400
            roi = 100.0 * total_return / investment if investment > 0 else 0
            profit = total_return - investment
            print(f"  {course}コース予測: {total:5,}件, ROI {roi:6.1f}%, 収支 {profit:+10,.0f}円")

    conn.close()


def analyze_venue_environment():
    """会場×環境データの深掘り"""
    print("\n" + "=" * 80)
    print("【分析3】会場×環境データの深掘り（B×50-100）")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 会場別1着的中率
    print(f"\n■ 会場別 1着的中率（B×50-100）")
    print("-" * 70)

    query = """
    SELECT
        ra.venue_code,
        v.name as venue_name,
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) as first_hit,
        ROUND(100.0 * SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as first_hit_rate
    FROM races ra
    JOIN venues v ON ra.venue_code = v.code
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    GROUP BY ra.venue_code, v.name
    ORDER BY first_hit_rate DESC
    """
    cursor.execute(query)
    results = cursor.fetchall()

    print(f"  {'会場':8s} {'件数':>6s} {'1着的中':>8s} {'的中率':>8s}")
    print("-" * 40)
    for row in results:
        venue_code, venue_name, total, hit, rate = row
        rate = rate or 0
        print(f"  {venue_name:8s} {total:6,}件 {hit:6,}件 {rate:7.1f}%")

    # 風速別1着的中率
    print(f"\n■ 風速別 1着的中率（B×50-100）")
    print("-" * 70)

    query = """
    SELECT
        CASE
            WHEN rc.wind_speed IS NULL THEN '不明'
            WHEN rc.wind_speed < 3 THEN '微風(0-2m)'
            WHEN rc.wind_speed < 5 THEN '弱風(3-4m)'
            ELSE '強風(5m+)'
        END as wind_category,
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) as first_hit,
        ROUND(100.0 * SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as first_hit_rate
    FROM races ra
    LEFT JOIN race_conditions rc ON ra.id = rc.race_id
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    GROUP BY wind_category
    ORDER BY
        CASE wind_category
            WHEN '微風(0-2m)' THEN 1
            WHEN '弱風(3-4m)' THEN 2
            WHEN '強風(5m+)' THEN 3
            ELSE 4
        END
    """
    cursor.execute(query)
    results = cursor.fetchall()

    for row in results:
        category, total, hit, rate = row
        rate = rate or 0
        print(f"  {category:12s}: {total:5,}件, 1着的中 {hit:4,}件, 的中率 {rate:5.1f}%")

    # 波高別1着的中率
    print(f"\n■ 波高別 1着的中率（B×50-100）")
    print("-" * 70)

    query = """
    SELECT
        CASE
            WHEN rc.wave_height IS NULL THEN '不明'
            WHEN rc.wave_height <= 3 THEN '穏やか(0-3cm)'
            WHEN rc.wave_height <= 6 THEN '普通(4-6cm)'
            ELSE '荒れ(7cm+)'
        END as wave_category,
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) as first_hit,
        ROUND(100.0 * SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as first_hit_rate
    FROM races ra
    LEFT JOIN race_conditions rc ON ra.id = rc.race_id
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    GROUP BY wave_category
    ORDER BY
        CASE wave_category
            WHEN '穏やか(0-3cm)' THEN 1
            WHEN '普通(4-6cm)' THEN 2
            WHEN '荒れ(7cm+)' THEN 3
            ELSE 4
        END
    """
    cursor.execute(query)
    results = cursor.fetchall()

    for row in results:
        category, total, hit, rate = row
        rate = rate or 0
        print(f"  {category:15s}: {total:5,}件, 1着的中 {hit:4,}件, 的中率 {rate:5.1f}%")

    # 天候別1着的中率
    print(f"\n■ 天候別 1着的中率（B×50-100）")
    print("-" * 70)

    query = """
    SELECT
        COALESCE(rc.weather, '不明') as weather,
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) as first_hit,
        ROUND(100.0 * SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as first_hit_rate
    FROM races ra
    LEFT JOIN race_conditions rc ON ra.id = rc.race_id
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    GROUP BY weather
    HAVING COUNT(*) >= 10
    ORDER BY first_hit_rate DESC
    """
    cursor.execute(query)
    results = cursor.fetchall()

    for row in results:
        weather, total, hit, rate = row
        rate = rate or 0
        print(f"  {weather:8s}: {total:5,}件, 1着的中 {hit:4,}件, 的中率 {rate:5.1f}%")

    conn.close()


def analyze_low_hit_rate_patterns():
    """1着的中率が特に低いパターンを特定"""
    print("\n" + "=" * 80)
    print("【分析4】1着的中率が特に低い/高いパターン（B×50-100）")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 会場×予測コース別
    print(f"\n■ 会場×予測1着コース別（1着的中率が低い順）")
    print("-" * 80)

    query = """
    SELECT
        v.name as venue_name,
        p1.pit_number as pred_course,
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) as first_hit,
        ROUND(100.0 * SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as first_hit_rate
    FROM races ra
    JOIN venues v ON ra.venue_code = v.code
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    GROUP BY v.name, p1.pit_number
    HAVING COUNT(*) >= 20
    ORDER BY first_hit_rate ASC
    LIMIT 20
    """
    cursor.execute(query)
    results = cursor.fetchall()

    print(f"  {'会場':6s} {'コース':>6s} {'件数':>6s} {'1着的中':>8s} {'的中率':>8s}")
    print("-" * 50)
    for row in results:
        venue, course, total, hit, rate = row
        rate = rate or 0
        print(f"  {venue:6s} {course}コース {total:5,}件 {hit:6,}件 {rate:7.1f}%")

    # 1着的中率が高いパターン
    print(f"\n■ 会場×予測1着コース別（1着的中率が高い順）")
    print("-" * 80)

    query = """
    SELECT
        v.name as venue_name,
        p1.pit_number as pred_course,
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) as first_hit,
        ROUND(100.0 * SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as first_hit_rate
    FROM races ra
    JOIN venues v ON ra.venue_code = v.code
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    GROUP BY v.name, p1.pit_number
    HAVING COUNT(*) >= 20
    ORDER BY first_hit_rate DESC
    LIMIT 20
    """
    cursor.execute(query)
    results = cursor.fetchall()

    print(f"  {'会場':6s} {'コース':>6s} {'件数':>6s} {'1着的中':>8s} {'的中率':>8s}")
    print("-" * 50)
    for row in results:
        venue, course, total, hit, rate = row
        rate = rate or 0
        print(f"  {venue:6s} {course}コース {total:5,}件 {hit:6,}件 {rate:7.1f}%")

    conn.close()


def analyze_roi_by_pattern():
    """パターン別のROI検証"""
    print("\n" + "=" * 80)
    print("【分析5】B×50-100 パターン別ROI検証（パターンH）")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 会場別ROI
    print(f"\n■ 会場別ROI（B×50-100、パターンH）")
    print("-" * 80)

    query = """
    SELECT
        ra.venue_code,
        v.name as venue_name,
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p2.pit_number
                  AND r3.pit_number = p3.pit_number THEN t.odds * 200 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p3.pit_number
                  AND r3.pit_number = p2.pit_number THEN COALESCE(t2.odds, 0) * 100 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p2.pit_number
                  AND r2.pit_number = p1.pit_number
                  AND r3.pit_number = p3.pit_number THEN COALESCE(t3.odds, 0) * 100 ELSE 0 END) as total_return
    FROM races ra
    JOIN venues v ON ra.venue_code = v.code
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN results r2 ON ra.id = r2.race_id AND r2.rank = '2'
    JOIN results r3 ON ra.id = r3.race_id AND r3.rank = '3'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    LEFT JOIN trifecta_odds t2 ON ra.id = t2.race_id
        AND t2.combination = printf('%d-%d-%d', p1.pit_number, p3.pit_number, p2.pit_number)
    LEFT JOIN trifecta_odds t3 ON ra.id = t3.race_id
        AND t3.combination = printf('%d-%d-%d', p2.pit_number, p1.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    GROUP BY ra.venue_code, v.name
    HAVING COUNT(*) >= 20
    ORDER BY (100.0 * total_return / (COUNT(*) * 400)) DESC
    """
    cursor.execute(query)
    results = cursor.fetchall()

    print(f"  {'会場':6s} {'件数':>6s} {'投資額':>10s} {'回収額':>12s} {'ROI':>8s} {'収支':>12s}")
    print("-" * 70)

    positive_venues = []
    negative_venues = []

    for row in results:
        venue_code, venue_name, total, total_return = row
        total_return = total_return or 0
        investment = total * 400
        roi = 100.0 * total_return / investment if investment > 0 else 0
        profit = total_return - investment
        print(f"  {venue_name:6s} {total:5,}件 {investment:9,}円 {total_return:11,.0f}円 {roi:7.1f}% {profit:+11,.0f}円")

        if roi >= 100:
            positive_venues.append(venue_name)
        else:
            negative_venues.append(venue_name)

    print(f"\n  ★ 黒字会場（ROI 100%+）: {', '.join(positive_venues)}")
    print(f"  ★ 赤字会場（ROI 100%-）: {', '.join(negative_venues)}")

    conn.close()


def generate_improvement_recommendations():
    """改善提案を生成"""
    print("\n" + "=" * 80)
    print("【分析6】改善提案")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. 6コース以外に絞った場合のROI
    print(f"\n■ 提案1: 6コース予測を除外した場合のROI")
    print("-" * 70)

    query = """
    SELECT
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p2.pit_number
                  AND r3.pit_number = p3.pit_number THEN t.odds * 200 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p3.pit_number
                  AND r3.pit_number = p2.pit_number THEN COALESCE(t2.odds, 0) * 100 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p2.pit_number
                  AND r2.pit_number = p1.pit_number
                  AND r3.pit_number = p3.pit_number THEN COALESCE(t3.odds, 0) * 100 ELSE 0 END) as total_return
    FROM races ra
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
        AND p1.pit_number != 6
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN results r2 ON ra.id = r2.race_id AND r2.rank = '2'
    JOIN results r3 ON ra.id = r3.race_id AND r3.rank = '3'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    LEFT JOIN trifecta_odds t2 ON ra.id = t2.race_id
        AND t2.combination = printf('%d-%d-%d', p1.pit_number, p3.pit_number, p2.pit_number)
    LEFT JOIN trifecta_odds t3 ON ra.id = t3.race_id
        AND t3.combination = printf('%d-%d-%d', p2.pit_number, p1.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    """
    cursor.execute(query)
    result = cursor.fetchone()

    total = result[0]
    total_return = result[1] or 0
    investment = total * 400
    roi = 100.0 * total_return / investment if investment > 0 else 0
    profit = total_return - investment

    print(f"  6コース除外時: {total:,}件, ROI {roi:.1f}%, 収支 {profit:+,.0f}円")

    # 全体のROI（比較用）
    query = """
    SELECT
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p2.pit_number
                  AND r3.pit_number = p3.pit_number THEN t.odds * 200 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p3.pit_number
                  AND r3.pit_number = p2.pit_number THEN COALESCE(t2.odds, 0) * 100 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p2.pit_number
                  AND r2.pit_number = p1.pit_number
                  AND r3.pit_number = p3.pit_number THEN COALESCE(t3.odds, 0) * 100 ELSE 0 END) as total_return
    FROM races ra
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN results r2 ON ra.id = r2.race_id AND r2.rank = '2'
    JOIN results r3 ON ra.id = r3.race_id AND r3.rank = '3'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    LEFT JOIN trifecta_odds t2 ON ra.id = t2.race_id
        AND t2.combination = printf('%d-%d-%d', p1.pit_number, p3.pit_number, p2.pit_number)
    LEFT JOIN trifecta_odds t3 ON ra.id = t3.race_id
        AND t3.combination = printf('%d-%d-%d', p2.pit_number, p1.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    """
    cursor.execute(query)
    result = cursor.fetchone()

    total_all = result[0]
    total_return_all = result[1] or 0
    investment_all = total_all * 400
    roi_all = 100.0 * total_return_all / investment_all if investment_all > 0 else 0

    print(f"  全体（参考）: {total_all:,}件, ROI {roi_all:.1f}%")

    # 2. 1-2コース予測のみに絞った場合
    print(f"\n■ 提案2: 1-2コース予測のみに絞った場合のROI")
    print("-" * 70)

    query = """
    SELECT
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p2.pit_number
                  AND r3.pit_number = p3.pit_number THEN t.odds * 200 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p3.pit_number
                  AND r3.pit_number = p2.pit_number THEN COALESCE(t2.odds, 0) * 100 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p2.pit_number
                  AND r2.pit_number = p1.pit_number
                  AND r3.pit_number = p3.pit_number THEN COALESCE(t3.odds, 0) * 100 ELSE 0 END) as total_return
    FROM races ra
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
        AND p1.pit_number IN (1, 2)
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN results r2 ON ra.id = r2.race_id AND r2.rank = '2'
    JOIN results r3 ON ra.id = r3.race_id AND r3.rank = '3'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    LEFT JOIN trifecta_odds t2 ON ra.id = t2.race_id
        AND t2.combination = printf('%d-%d-%d', p1.pit_number, p3.pit_number, p2.pit_number)
    LEFT JOIN trifecta_odds t3 ON ra.id = t3.race_id
        AND t3.combination = printf('%d-%d-%d', p2.pit_number, p1.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    """
    cursor.execute(query)
    result = cursor.fetchone()

    total = result[0]
    total_return = result[1] or 0
    investment = total * 400
    roi = 100.0 * total_return / investment if investment > 0 else 0
    profit = total_return - investment

    print(f"  1-2コース予測のみ: {total:,}件, ROI {roi:.1f}%, 収支 {profit:+,.0f}円")

    conn.close()


def main():
    """メイン関数"""
    print("=" * 80)
    print("B×50-100条件の1着的中率が低い原因を深掘り分析")
    print("=" * 80)
    print(f"データベース: {DATABASE_PATH}")

    # 1. B予想全体 vs B×50-100の比較
    analyze_b_prediction_overall()

    # 2. 予測コース別の分析とROI検証
    analyze_predicted_course_distribution()

    # 3. 会場×環境データの深掘り
    analyze_venue_environment()

    # 4. 1着的中率が低い/高いパターン
    analyze_low_hit_rate_patterns()

    # 5. パターン別ROI
    analyze_roi_by_pattern()

    # 6. 改善提案
    generate_improvement_recommendations()

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
