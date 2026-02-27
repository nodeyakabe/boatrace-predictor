#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""TJ-2動作確認用テストスクリプト"""
import sqlite3
import sys
import io
from pathlib import Path
import pandas as pd

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

def main():
    conn = sqlite3.connect(str(DB_PATH))

    print("=== Step 1 テスト ===")
    query = """
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
    WHERE r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    """
    df = pd.read_sql_query(query, conn)
    print(df.to_string())

    print("\n=== Step 2 テスト（決まり手分布） ===")
    query2 = """
    SELECT
        CASE WHEN kimarite IN ('逃げ','まくり','差し','まくり差し','抜き')
             THEN kimarite ELSE 'その他' END as km,
        COUNT(*) as cnt
    FROM results res
    JOIN races r ON res.race_id = r.id
    WHERE r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
      AND res.is_invalid = 0
      AND CAST(res.rank AS INTEGER) = 1
      AND res.kimarite IS NOT NULL AND res.kimarite != ''
    GROUP BY km
    ORDER BY cnt DESC
    """
    df2 = pd.read_sql_query(query2, conn)
    print(df2.to_string())

    print("\n=== Step 4 テスト（ROIクエリ - 小範囲） ===")
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
          AND r.race_date BETWEEN '2024-01-01' AND '2024-12-31'
          AND t.odds IS NOT NULL
    )
    SELECT
        pred1,
        km,
        COUNT(*) as total,
        SUM(hit) as hits,
        ROUND(100.0 * SUM(hit) / COUNT(*), 2) as hit_rate,
        ROUND(100.0 * SUM(CASE WHEN hit=1 THEN odds * 100 ELSE 0 END) / (COUNT(*) * 100), 2) as roi
    FROM race_data
    GROUP BY pred1, km
    ORDER BY roi DESC
    LIMIT 20
    """
    df4 = pd.read_sql_query(query4, conn)
    if df4.empty:
        print("  オッズデータなし（2024年）")
    else:
        print(df4.to_string())

    conn.close()
    print("\n=== テスト完了 ===")

if __name__ == "__main__":
    main()
