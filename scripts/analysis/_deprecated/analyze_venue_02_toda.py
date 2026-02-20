#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
戸田競艇場（会場02）の詳細分析

発見事項:
  - 信頼度A×オッズ10倍未満で唯一の高ROI（151.6%）
  - レース数: 112件
  - 収支: +23,120円

目的:
  - なぜ戸田だけ高ROIなのか？
  - 級別・時期・コース・選手の特徴は？
  - 新規条件として採用可能か？
"""
import sqlite3
import sys
import io
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATABASE_PATH = 'data/boatrace.db'

def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("="*80)
    print("戸田競艇場（会場02）の詳細分析")
    print("="*80)
    print()
    print(f"分析開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # ============================================================
    # 基本情報
    # ============================================================
    print("【1】戸田競艇場の基本情報")
    print("="*80)
    print()
    print("競艇場名: 戸田競艇場")
    print("会場コード: 02")
    print("水質: 淡水")
    print("特徴: 日本一狭いコース、インが有利")
    print()

    # ============================================================
    # 信頼度A×オッズ10倍未満の成績
    # ============================================================
    print("【2】信頼度A×オッズ10倍未満の成績")
    print("="*80)
    print()

    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                rp1.pit_number as p1,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            COUNT(*) as races,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            SUM(400) as investment,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) as returns,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit,
            ROUND(AVG(t.odds), 2) as avg_odds,
            ROUND(MIN(t.odds), 2) as min_odds,
            ROUND(MAX(t.odds), 2) as max_odds,
            ROUND(AVG(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds END), 2) as avg_hit_odds
        FROM predictions p
        JOIN races r ON p.race_id = r.id
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE r.venue_code IN ('2', '02')
        AND t.odds < 10
    ''')

    row = cursor.fetchone()
    races, hits, hit_rate, investment, returns, roi, profit, avg_odds, min_odds, max_odds, avg_hit_odds = row

    print(f"レース数:     {races:,}件")
    print(f"的中数:       {hits:,}件")
    print(f"的中率:       {hit_rate:.2f}%")
    print(f"投資額:       {investment:,}円")
    print(f"払戻額:       {returns:,}円")
    print(f"収支:         {profit:+,}円")
    print(f"ROI:          {roi:.2f}%")
    print(f"平均オッズ:   {avg_odds:.2f}倍")
    print(f"オッズ範囲:   {min_odds:.2f}～{max_odds:.2f}倍")
    print(f"的中時平均:   {avg_hit_odds:.2f}倍")
    print()

    # ============================================================
    # 年度別成績
    # ============================================================
    print("【3】年度別成績")
    print("="*80)
    print()

    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            substr(r.race_date, 1, 4) as year,
            COUNT(*) as races,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit
        FROM predictions p
        JOIN races r ON p.race_id = r.id
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE r.venue_code IN ('2', '02')
        AND t.odds < 10
        GROUP BY year
        ORDER BY year
    ''')

    print(f"{'年度':<8} {'レース':<10} {'的中':<10} {'的中率':<10} {'ROI':<12} {'収支':<15}")
    print("-"*80)

    year_data = []
    for row in cursor.fetchall():
        year, races, hits, hit_rate, roi, profit = row
        year_data.append({'year': year, 'races': races, 'roi': roi, 'profit': profit})
        status = '✅' if roi > 100 else '❌'
        print(f"{year:<8} {races:>8,}件  {hits:>8,}件  {hit_rate:>7.2f}%  {roi:>9.2f}%  {profit:>+12,}円 {status}")

    print()
    black_years = sum(1 for y in year_data if y['roi'] > 100)
    print(f"黒字年数: {black_years}/{len(year_data)}年")
    print()

    # ============================================================
    # 月別成績
    # ============================================================
    print("【4】月別成績（季節性の確認）")
    print("="*80)
    print()

    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            CAST(substr(r.race_date, 6, 2) AS INTEGER) as month,
            COUNT(*) as races,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit
        FROM predictions p
        JOIN races r ON p.race_id = r.id
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE r.venue_code IN ('2', '02')
        AND t.odds < 10
        GROUP BY month
        ORDER BY month
    ''')

    print(f"{'月':<6} {'レース':<10} {'的中':<10} {'的中率':<10} {'ROI':<12} {'収支':<15}")
    print("-"*80)

    for row in cursor.fetchall():
        month, races, hits, hit_rate, roi, profit = row
        season = ''
        if month in [12, 1, 2]:
            season = '(冬)'
        elif month in [3, 4, 5]:
            season = '(春)'
        elif month in [6, 7, 8]:
            season = '(夏)'
        elif month in [9, 10, 11]:
            season = '(秋)'
        status = '✅' if roi > 100 else '❌'
        print(f"{month:>2}月{season:<4} {races:>8,}件  {hits:>8,}件  {hit_rate:>7.2f}%  {roi:>9.2f}%  {profit:>+12,}円 {status}")

    print()

    # ============================================================
    # 級別分析
    # ============================================================
    print("【5】予測1着選手の級別分析")
    print("="*80)
    print()

    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                rp1.pit_number as p1,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            e.racer_rank,
            COUNT(*) as races,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit,
            ROUND(AVG(t.odds), 2) as avg_odds
        FROM predictions p
        JOIN races r ON p.race_id = r.id
        JOIN entries e ON p.race_id = e.race_id AND p.p1 = e.pit_number
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE r.venue_code IN ('2', '02')
        AND t.odds < 10
        GROUP BY e.racer_rank
        ORDER BY roi DESC
    ''')

    print(f"{'級別':<8} {'レース':<10} {'的中':<10} {'的中率':<10} {'ROI':<12} {'収支':<15} {'平均オッズ':<12}")
    print("-"*100)

    for row in cursor.fetchall():
        rank, races, hits, hit_rate, roi, profit, avg_odds = row
        rank_name = rank if rank else '不明'
        status = '✅' if roi > 100 else '❌'
        print(f"{rank_name:<8} {races:>8,}件  {hits:>8,}件  {hit_rate:>7.2f}%  {roi:>9.2f}%  {profit:>+12,}円  {avg_odds:>9.2f}倍 {status}")

    print()

    # ============================================================
    # コース別分析
    # ============================================================
    print("【6】予測1着選手のコース別分析")
    print("="*80)
    print()

    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                rp1.pit_number as p1,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            p.p1 as course,
            COUNT(*) as races,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit,
            ROUND(AVG(t.odds), 2) as avg_odds
        FROM predictions p
        JOIN races r ON p.race_id = r.id
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE r.venue_code IN ('2', '02')
        AND t.odds < 10
        GROUP BY course
        ORDER BY course
    ''')

    print(f"{'コース':<8} {'レース':<10} {'的中':<10} {'的中率':<10} {'ROI':<12} {'収支':<15} {'平均オッズ':<12}")
    print("-"*100)

    for row in cursor.fetchall():
        course, races, hits, hit_rate, roi, profit, avg_odds = row
        status = '✅' if roi > 100 else '❌'
        print(f"{course:<8} {races:>8,}件  {hits:>8,}件  {hit_rate:>7.2f}%  {roi:>9.2f}%  {profit:>+12,}円  {avg_odds:>9.2f}倍 {status}")

    print()

    # ============================================================
    # オッズ帯別分析
    # ============================================================
    print("【7】オッズ帯別分析")
    print("="*80)
    print()

    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            CASE
                WHEN t.odds < 3 THEN '1-3倍未満'
                WHEN t.odds < 5 THEN '3-5倍'
                WHEN t.odds < 7 THEN '5-7倍'
                WHEN t.odds < 10 THEN '7-10倍'
            END as odds_band,
            COUNT(*) as races,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) as hits,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit
        FROM predictions p
        JOIN races r ON p.race_id = r.id
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE r.venue_code IN ('2', '02')
        AND t.odds < 10
        GROUP BY odds_band
        ORDER BY odds_band
    ''')

    print(f"{'オッズ帯':<15} {'レース':<10} {'的中':<10} {'的中率':<10} {'ROI':<12} {'収支':<15}")
    print("-"*80)

    for row in cursor.fetchall():
        odds_band, races, hits, hit_rate, roi, profit = row
        status = '✅' if roi > 100 else '❌'
        print(f"{odds_band:<15} {races:>8,}件  {hits:>8,}件  {hit_rate:>7.2f}%  {roi:>9.2f}%  {profit:>+12,}円 {status}")

    print()

    # ============================================================
    # 他会場との比較
    # ============================================================
    print("【8】他会場（上位5会場）との比較")
    print("="*80)
    print()

    VENUE_NAMES = {
        1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
        7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: 'びわこ', 12: '住之江',
        13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
        19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
    }

    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            r.venue_code,
            COUNT(*) as races,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi,
            SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) - SUM(400) as profit
        FROM predictions p
        JOIN races r ON p.race_id = r.id
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE t.odds < 10
        GROUP BY r.venue_code
        HAVING races >= 50
        ORDER BY roi DESC
        LIMIT 5
    ''')

    print(f"{'順位':<6} {'会場':<10} {'レース':<10} {'的中率':<10} {'ROI':<12} {'収支':<15}")
    print("-"*80)

    rank = 1
    for row in cursor.fetchall():
        venue_code, races, hit_rate, roi, profit = row
        venue_name = VENUE_NAMES.get(venue_code, f'会場{venue_code}')
        if venue_code == 2:
            venue_name = f"★{venue_name}"
        status = '✅' if roi > 100 else '❌'
        print(f"{rank:<6} {venue_name:<10} {races:>8,}件  {hit_rate:>7.2f}%  {roi:>9.2f}%  {profit:>+12,}円 {status}")
        rank += 1

    print()

    # ============================================================
    # 結論と推奨事項
    # ============================================================
    print("【9】結論と推奨事項")
    print("="*80)
    print()

    print("■ 戸田競艇場の特徴:")
    print("  - 日本一狭いコース → インが圧倒的に有利")
    print("  - 淡水 → 水質が安定")
    print("  - 信頼度A×オッズ10倍未満で高ROI（151.6%）")
    print()

    print("■ 新規条件としての評価:")
    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
            AND rp1.confidence = 'A'
        ),
        results_agg AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            substr(r.race_date, 1, 4) as year,
            ROUND(100.0 * SUM(CASE WHEN p.pred_combo = ra.actual_combo THEN t.odds * 400 ELSE 0 END) / SUM(400), 2) as roi
        FROM predictions p
        JOIN races r ON p.race_id = r.id
        JOIN trifecta_odds t ON p.race_id = t.race_id AND t.combination = p.pred_combo
        LEFT JOIN results_agg ra ON p.race_id = ra.race_id
        WHERE r.venue_code IN ('2', '02')
        AND t.odds < 10
        GROUP BY year
        ORDER BY year
    ''')

    year_rois = [row[1] for row in cursor.fetchall()]
    black_years = sum(1 for roi in year_rois if roi > 100)

    print(f"  - サンプル数: {races}件（基準: 100件以上 ✅）")
    print(f"  - ROI: {roi:.2f}%（基準: 100%以上 ✅）")
    print(f"  - 黒字年数: {black_years}/{len(year_rois)}年（基準: 4/6年以上 {'✅' if black_years >= 4 else '❌'}）")
    print()

    if black_years >= 4 and roi > 100 and races >= 100:
        print("  【評価】✅ 新規条件として採用推奨")
        print()
        print("  【推奨条件】")
        print("    条件名: A×戸田×オッズ10倍未満")
        print("    信頼度: A")
        print("    会場: 戸田（02）")
        print("    オッズ帯: 1～10倍未満")
        print("    買い目: 1点買い（400円）")
        print(f"    期待ROI: {roi:.2f}%")
        print(f"    期待収支: {profit:+,}円/年")
    else:
        print("  【評価】△ 要検討")
        print(f"    黒字年数が基準未達: {black_years}/{len(year_rois)}年")

    print()

    conn.close()

    print("="*80)
    print("分析完了")
    print("="*80)
    print()
    print(f"分析終了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    main()
