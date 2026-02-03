# -*- coding: utf-8 -*-
"""展示データ（exhibition_time, chikusen_time）のカバレッジ確認"""
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print("=" * 80)
print("展示データ カバレッジ確認（年度別）")
print("=" * 80)
print()

# 年度別カバレッジ
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

results = cursor.fetchall()

print("年度別カバレッジ:")
print("-" * 80)
print(f"{'年度':<8} {'全レース':>10} {'exhibition_time':>18} {'chikusen_time':>18}")
print(f"{'':8} {'':10} {'件数':>10} {'%':>6} {'件数':>10} {'%':>6}")
print("-" * 80)

for row in results:
    year, total, ex_count, ex_pct, ch_count, ch_pct = row
    print(f"{year:<8} {total:>10,} {ex_count:>10,} {ex_pct:>5.1f}% {ch_count:>10,} {ch_pct:>5.1f}%")

# 全期間サマリー
cursor.execute("""
    SELECT
        COUNT(*) AS total_races,
        SUM(CASE WHEN rd.exhibition_time IS NOT NULL THEN 1 ELSE 0 END) AS exhibition_time_count,
        ROUND(100.0 * SUM(CASE WHEN rd.exhibition_time IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS exhibition_time_pct,
        SUM(CASE WHEN rd.chikusen_time IS NOT NULL THEN 1 ELSE 0 END) AS chikusen_time_count,
        ROUND(100.0 * SUM(CASE WHEN rd.chikusen_time IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS chikusen_time_pct
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    WHERE rd.pit_number = 1
""")

total_row = cursor.fetchone()
total, ex_count, ex_pct, ch_count, ch_pct = total_row

print("-" * 80)
print(f"{'全期間':<8} {total:>10,} {ex_count:>10,} {ex_pct:>5.1f}% {ch_count:>10,} {ch_pct:>5.1f}%")
print("=" * 80)

# 補完が必要な月の数を計算
cursor.execute("""
    SELECT
        SUBSTR(r.race_date, 1, 7) AS year_month,
        COUNT(*) AS total_races,
        SUM(CASE WHEN rd.exhibition_time IS NULL THEN 1 ELSE 0 END) AS missing_exhibition,
        SUM(CASE WHEN rd.chikusen_time IS NULL THEN 1 ELSE 0 END) AS missing_chikusen
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    WHERE rd.pit_number = 1
        AND SUBSTR(r.race_date, 1, 4) BETWEEN '2020' AND '2024'
        AND (rd.exhibition_time IS NULL OR rd.chikusen_time IS NULL)
    GROUP BY year_month
    HAVING missing_exhibition > 0 OR missing_chikusen > 0
    ORDER BY year_month
""")

missing_months = cursor.fetchall()

print()
print(f"補完が必要な月: {len(missing_months)}ヶ月")
print(f"推定所要時間: {len(missing_months) * 31:.0f}分 ≈ {len(missing_months) * 31 / 60:.1f}時間")
print()

# 最初の10ヶ月と最後の10ヶ月を表示
if len(missing_months) > 0:
    print("最初の10ヶ月:")
    for month, total, missing_ex, missing_ch in missing_months[:10]:
        print(f"  {month}: レース{total:,}件 (exhibition欠損:{missing_ex:,}, chikusen欠損:{missing_ch:,})")

    if len(missing_months) > 20:
        print(f"  ... ({len(missing_months) - 20}ヶ月省略)")

    if len(missing_months) > 10:
        print("最後の10ヶ月:")
        for month, total, missing_ex, missing_ch in missing_months[-10:]:
            print(f"  {month}: レース{total:,}件 (exhibition欠損:{missing_ex:,}, chikusen欠損:{missing_ch:,})")

conn.close()
