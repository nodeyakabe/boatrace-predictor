"""
過去データ（2020-2025年）のオッズ取得タイミングを確認
"""
import sqlite3
import pandas as pd

DB_PATH = r'c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db'

conn = sqlite3.connect(DB_PATH)

print("=" * 80)
print("【過去データのオッズ取得タイミング調査】")
print("=" * 80)

# 年度別のオッズ取得時刻統計
query = """
SELECT
    year,
    COUNT(*) as race_count,
    AVG(hours_before) as avg_hours_before
FROM (
    SELECT
        SUBSTR(r.race_date, 1, 4) as year,
        r.id,
        JULIANDAY(r.race_date || ' ' || r.race_time) - JULIANDAY(MIN(t.fetched_at)) as hours_before
    FROM races r
    INNER JOIN trifecta_odds t ON r.id = t.race_id
    WHERE r.race_time IS NOT NULL
      AND r.race_date >= '2020-01-01'
    GROUP BY r.id
) sub
GROUP BY year
ORDER BY year
"""

df = pd.read_sql_query(query, conn)
print("\n年度別のオッズ取得タイミング（平均）:")
print(df.to_string(index=False))
print()

# 2025年のサンプルデータ（ランダムに10レース）
print("=" * 80)
print("【2025年のサンプルレース（10件）】")
print("=" * 80)

sample_query = """
SELECT
    r.id,
    r.race_date,
    r.venue_code,
    r.race_number,
    r.race_time,
    MIN(t.fetched_at) as odds_fetched_at,
    JULIANDAY(r.race_date || ' ' || r.race_time) - JULIANDAY(MIN(t.fetched_at)) as hours_before
FROM races r
INNER JOIN trifecta_odds t ON r.id = t.race_id
WHERE r.race_date BETWEEN '2025-01-01' AND '2025-12-31'
  AND r.race_time IS NOT NULL
GROUP BY r.id
ORDER BY RANDOM()
LIMIT 10
"""

sample_df = pd.read_sql_query(sample_query, conn)
print(sample_df.to_string(index=False))
print()

# fetched_atがNULLのデータ確認
print("=" * 80)
print("【fetched_atがNULLのオッズデータ】")
print("=" * 80)

null_check = pd.read_sql_query("""
SELECT
    COUNT(*) as null_count,
    (SELECT COUNT(*) FROM trifecta_odds) as total_count,
    CAST(COUNT(*) AS REAL) / (SELECT COUNT(*) FROM trifecta_odds) * 100 as null_percentage
FROM trifecta_odds
WHERE fetched_at IS NULL
""", conn)
print(null_check.to_string(index=False))

conn.close()
