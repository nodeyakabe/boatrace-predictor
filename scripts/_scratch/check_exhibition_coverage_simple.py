# -*- coding: utf-8 -*-
"""展示データ カバレッジ確認（シンプル版）"""
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print("="*80)
print("年度別カバレッジ")
print("="*80)

cursor.execute("""
    SELECT
        SUBSTR(r.race_date, 1, 4) AS year,
        COUNT(*) AS total_races,
        SUM(CASE WHEN rd.exhibition_time IS NOT NULL THEN 1 ELSE 0 END) AS exhibition_time_count,
        ROUND(100.0 * SUM(CASE WHEN rd.exhibition_time IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS exhibition_time_pct,
        SUM(CASE WHEN rd.chikusen_time IS NOT NULL THEN 1 ELSE 0 END) AS chikusen_time_count,
        ROUND(100.0 * SUM(CASE WHEN rd.chikusen_time IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS chikusen_time_pct
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    WHERE rd.pit_number = 1
    GROUP BY year
    ORDER BY year
""")

print(f"{'年度':<8} {'全レース':>10} {'exhibition':>12} {'chikusen':>12}")
print("-"*80)
for row in cursor.fetchall():
    year, total, ex_cnt, ex_pct, ch_cnt, ch_pct = row
    print(f"{year:<8} {total:>10,} {ex_pct:>10.1f}% {ch_pct:>10.1f}%")

print()
print("補完が必要な期間:")
cursor.execute("""
    SELECT
        SUBSTR(r.race_date, 1, 4) AS year,
        COUNT(DISTINCT SUBSTR(r.race_date, 1, 7)) AS missing_months,
        SUM(CASE WHEN rd.exhibition_time IS NULL THEN 1 ELSE 0 END) AS missing_ex,
        SUM(CASE WHEN rd.chikusen_time IS NULL THEN 1 ELSE 0 END) AS missing_ch
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    WHERE rd.pit_number = 1
        AND SUBSTR(r.race_date, 1, 4) BETWEEN '2020' AND '2024'
    GROUP BY year
    ORDER BY year
""")

total_months = 0
for row in cursor.fetchall():
    year, months, missing_ex, missing_ch = row
    total_months += months
    print(f"{year}: {months}ヶ月 (exhibition欠損:{missing_ex:,}, chikusen欠損:{missing_ch:,})")

print()
print(f"合計: {total_months}ヶ月")
print(f"推定時間: {total_months * 0.5:.0f}時間 (1ヶ月=30分換算)")

conn.close()
