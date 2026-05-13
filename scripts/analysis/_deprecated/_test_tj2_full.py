#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""TJ-2 全Step動作確認用テストスクリプト（2024年1年分で高速確認）"""
import sqlite3
import sys
import io
from pathlib import Path
import pandas as pd
import numpy as np

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
MIN_SAMPLE = 30  # テスト用に緩めに

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

KIMARITE_ORDER = ['逃げ', 'まくり', '差し', 'まくり差し', '抜き', 'その他']

START_YEAR = 2024
END_YEAR = 2024

def main():
    conn = sqlite3.connect(str(DB_PATH))

    print(f"TJ-2テスト: {START_YEAR}-{END_YEAR}年")

    # Step 1
    print("\n=== Step 1: データ充足率 ===")
    query1 = """
    SELECT
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT rp.race_id) as predicted_races,
        COUNT(DISTINCT ki.race_id) as kimarite_races,
        COUNT(DISTINCT CASE WHEN rp.race_id IS NOT NULL AND ki.race_id IS NOT NULL
                            THEN r.id END) as both_available
    FROM races r
    LEFT JOIN (
        SELECT DISTINCT race_id FROM race_predictions WHERE prediction_type='before' AND rank_prediction=1
    ) rp ON r.id = rp.race_id
    LEFT JOIN (
        SELECT DISTINCT race_id FROM results
        WHERE is_invalid=0 AND CAST(rank AS INTEGER)=1 AND kimarite IS NOT NULL AND kimarite != ''
    ) ki ON r.id = ki.race_id
    WHERE r.race_date BETWEEN '{sy}-01-01' AND '{ey}-12-31'
    """.format(sy=START_YEAR, ey=END_YEAR)
    df1 = pd.read_sql_query(query1, conn)
    row = df1.iloc[0]
    total = int(row['total_races'])
    both = int(row['both_available'])
    print(f"  総レース数: {total:,}, 分析可能: {both:,} ({both/total*100:.1f}%)")

    # Step 2
    print("\n=== Step 2: 決まり手分布 ===")
    query2 = """
    SELECT
        CASE WHEN kimarite IN ('逃げ','まくり','差し','まくり差し','抜き')
             THEN kimarite ELSE 'その他' END as km,
        COUNT(*) as cnt
    FROM results res
    JOIN races r ON res.race_id = r.id
    WHERE r.race_date BETWEEN '{sy}-01-01' AND '{ey}-12-31'
      AND res.is_invalid = 0 AND CAST(res.rank AS INTEGER) = 1
      AND res.kimarite IS NOT NULL AND res.kimarite != ''
    GROUP BY km ORDER BY cnt DESC
    """.format(sy=START_YEAR, ey=END_YEAR)
    df2 = pd.read_sql_query(query2, conn)
    total2 = df2['cnt'].sum()
    for _, row in df2.iterrows():
        print(f"  {row['km']:>10} {int(row['cnt']):>6,} ({row['cnt']/total2*100:.1f}%)")

    # Step 3
    print("\n=== Step 3: 予測コース × 決まり手 的中率 ===")
    query3 = """
    SELECT
        rp.pit_number AS pred_pit,
        CASE WHEN res_1st.kimarite IN ('逃げ','まくり','差し','まくり差し','抜き')
             THEN res_1st.kimarite ELSE 'その他' END AS km,
        CASE WHEN res_pred.pit_number = res_1st.pit_number THEN 1 ELSE 0 END AS hit
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    JOIN results res_1st ON rp.race_id = res_1st.race_id
        AND res_1st.is_invalid = 0 AND CAST(res_1st.rank AS INTEGER) = 1
        AND res_1st.kimarite IS NOT NULL AND res_1st.kimarite != ''
    LEFT JOIN results res_pred ON rp.race_id = res_pred.race_id
        AND res_pred.pit_number = rp.pit_number AND res_pred.is_invalid = 0
    WHERE rp.prediction_type = 'before' AND rp.rank_prediction = 1
      AND r.race_date BETWEEN '{sy}-01-01' AND '{ey}-12-31'
    """.format(sy=START_YEAR, ey=END_YEAR)
    df3 = pd.read_sql_query(query3, conn)
    cross = df3.groupby(['pred_pit', 'km']).agg(
        cnt=('hit', 'count'), hit_cnt=('hit', 'sum')
    ).reset_index()
    cross['hit_rate'] = (cross['hit_cnt'] / cross['cnt'] * 100).round(2)
    cross_filtered = cross[cross['cnt'] >= MIN_SAMPLE]
    print(f"  (サンプル>={MIN_SAMPLE}の組み合わせ数: {len(cross_filtered)})")
    print(cross_filtered.sort_values('hit_rate', ascending=False).head(10).to_string())

    # Step 4 ROI
    print("\n=== Step 4: ROI分析 ===")
    query4 = """
    WITH race_data AS (
        SELECT
            rp1.race_id,
            rp1.pit_number AS pred1,
            rp2.pit_number AS pred2,
            rp3.pit_number AS pred3,
            rp1.confidence,
            res_1st.pit_number AS actual_1st_pit,
            CASE WHEN res_1st.kimarite IN ('逃げ','まくり','差し','まくり差し','抜き')
                 THEN res_1st.kimarite ELSE 'その他' END AS km,
            CASE WHEN res_1st.pit_number = rp1.pit_number
                  AND res_2nd.pit_number = rp2.pit_number
                  AND res_3rd.pit_number = rp3.pit_number
                 THEN 1 ELSE 0 END AS hit,
            t.odds
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races r ON rp1.race_id = r.id
        JOIN results res_1st ON rp1.race_id = res_1st.race_id
            AND res_1st.is_invalid = 0 AND CAST(res_1st.rank AS INTEGER) = 1
            AND res_1st.kimarite IS NOT NULL AND res_1st.kimarite != ''
        LEFT JOIN results res_2nd ON rp1.race_id = res_2nd.race_id
            AND res_2nd.is_invalid = 0 AND CAST(res_2nd.rank AS INTEGER) = 2
        LEFT JOIN results res_3rd ON rp1.race_id = res_3rd.race_id
            AND res_3rd.is_invalid = 0 AND CAST(res_3rd.rank AS INTEGER) = 3
        LEFT JOIN trifecta_odds t ON rp1.race_id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                             || CAST(rp2.pit_number AS TEXT) || '-'
                             || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND r.race_date BETWEEN '{sy}-01-01' AND '{ey}-12-31'
          AND t.odds IS NOT NULL
    )
    SELECT
        pred1, km,
        COUNT(*) as total,
        SUM(hit) as hits,
        ROUND(100.0 * SUM(hit) / COUNT(*), 2) as hit_rate,
        ROUND(100.0 * SUM(CASE WHEN hit=1 THEN odds * 100 ELSE 0 END) / (COUNT(*) * 100), 2) as roi
    FROM race_data
    GROUP BY pred1, km
    """.format(sy=START_YEAR, ey=END_YEAR)
    df4 = pd.read_sql_query(query4, conn)
    if df4.empty:
        print("  データなし")
    else:
        df4_filtered = df4[df4['total'] >= MIN_SAMPLE].sort_values('roi', ascending=False)
        print(df4_filtered.to_string())
        print(f"\n  全体データ行数: {len(df4)}, フィルター後: {len(df4_filtered)}")

    # Step 5
    print("\n=== Step 5: 信頼度 × 決まり手 ROI ===")
    query5 = """
    WITH race_data AS (
        SELECT
            rp1.race_id, rp1.pit_number AS pred1, rp2.pit_number AS pred2, rp3.pit_number AS pred3,
            rp1.confidence,
            CASE WHEN res_1st.kimarite IN ('逃げ','まくり','差し','まくり差し','抜き')
                 THEN res_1st.kimarite ELSE 'その他' END AS km,
            CASE WHEN res_1st.pit_number = rp1.pit_number
                  AND res_2nd.pit_number = rp2.pit_number
                  AND res_3rd.pit_number = rp3.pit_number THEN 1 ELSE 0 END AS hit,
            t.odds
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races r ON rp1.race_id = r.id
        JOIN results res_1st ON rp1.race_id = res_1st.race_id
            AND res_1st.is_invalid = 0 AND CAST(res_1st.rank AS INTEGER) = 1
            AND res_1st.kimarite IS NOT NULL AND res_1st.kimarite != ''
        LEFT JOIN results res_2nd ON rp1.race_id = res_2nd.race_id
            AND res_2nd.is_invalid = 0 AND CAST(res_2nd.rank AS INTEGER) = 2
        LEFT JOIN results res_3rd ON rp1.race_id = res_3rd.race_id
            AND res_3rd.is_invalid = 0 AND CAST(res_3rd.rank AS INTEGER) = 3
        LEFT JOIN trifecta_odds t ON rp1.race_id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                             || CAST(rp2.pit_number AS TEXT) || '-'
                             || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND r.race_date BETWEEN '{sy}-01-01' AND '{ey}-12-31'
          AND t.odds IS NOT NULL
    )
    SELECT confidence, km,
        COUNT(*) as total, SUM(hit) as hits,
        ROUND(100.0 * SUM(hit) / COUNT(*), 2) as hit_rate,
        ROUND(100.0 * SUM(CASE WHEN hit=1 THEN odds * 100 ELSE 0 END) / (COUNT(*) * 100), 2) as roi
    FROM race_data
    GROUP BY confidence, km
    ORDER BY confidence, roi DESC
    """.format(sy=START_YEAR, ey=END_YEAR)
    df5 = pd.read_sql_query(query5, conn)
    df5_filtered = df5[df5['total'] >= MIN_SAMPLE]
    print(df5_filtered.to_string())

    # Step 6
    print("\n=== Step 6: 会場別 × 決まり手 ROI（上位5件） ===")
    query6 = """
    WITH race_data AS (
        SELECT
            r.venue_code, rp1.pit_number AS pred1, rp2.pit_number AS pred2, rp3.pit_number AS pred3,
            CASE WHEN res_1st.kimarite IN ('逃げ','まくり','差し','まくり差し','抜き')
                 THEN res_1st.kimarite ELSE 'その他' END AS km,
            CASE WHEN res_1st.pit_number = rp1.pit_number
                  AND res_2nd.pit_number = rp2.pit_number
                  AND res_3rd.pit_number = rp3.pit_number THEN 1 ELSE 0 END AS hit,
            t.odds
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races r ON rp1.race_id = r.id
        JOIN results res_1st ON rp1.race_id = res_1st.race_id
            AND res_1st.is_invalid = 0 AND CAST(res_1st.rank AS INTEGER) = 1
            AND res_1st.kimarite IS NOT NULL AND res_1st.kimarite != ''
        LEFT JOIN results res_2nd ON rp1.race_id = res_2nd.race_id
            AND res_2nd.is_invalid = 0 AND CAST(res_2nd.rank AS INTEGER) = 2
        LEFT JOIN results res_3rd ON rp1.race_id = res_3rd.race_id
            AND res_3rd.is_invalid = 0 AND CAST(res_3rd.rank AS INTEGER) = 3
        LEFT JOIN trifecta_odds t ON rp1.race_id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                             || CAST(rp2.pit_number AS TEXT) || '-'
                             || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND r.race_date BETWEEN '{sy}-01-01' AND '{ey}-12-31'
          AND t.odds IS NOT NULL
    )
    SELECT venue_code, km,
        COUNT(*) as total, SUM(hit) as hits,
        ROUND(100.0 * SUM(hit) / COUNT(*), 2) as hit_rate,
        ROUND(100.0 * SUM(CASE WHEN hit=1 THEN odds * 100 ELSE 0 END) / (COUNT(*) * 100), 2) as roi
    FROM race_data
    GROUP BY venue_code, km
    """.format(sy=START_YEAR, ey=END_YEAR)
    df6 = pd.read_sql_query(query6, conn)
    df6_filtered = df6[df6['total'] >= MIN_SAMPLE].sort_values('roi', ascending=False).head(5)
    print(df6_filtered.to_string())

    conn.close()
    print("\n=== 全Step動作確認完了 ===")

if __name__ == "__main__":
    main()
