"""
オッズ取得タイミングの詳細調査
"""
import sqlite3
import pandas as pd

DB_PATH = r'c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db'

conn = sqlite3.connect(DB_PATH)

print("=" * 80)
print("【調査】オッズ取得タイミングの分析")
print("=" * 80)

# 2026年1月の各レースのオッズ取得時刻とレース時刻を比較
query = """
SELECT
    r.id as race_id,
    r.race_date,
    r.venue_code,
    r.race_number,
    r.race_time,
    MIN(t.fetched_at) as odds_fetched_at,
    JULIANDAY(r.race_date || ' ' || r.race_time) - JULIANDAY(MIN(t.fetched_at)) as hours_before_race
FROM races r
INNER JOIN trifecta_odds t ON r.id = t.race_id
WHERE r.race_date >= '2026-01-15' AND r.race_date <= '2026-01-18'
  AND r.race_time IS NOT NULL
GROUP BY r.id, r.race_date, r.venue_code, r.race_number, r.race_time
ORDER BY r.race_date, r.venue_code, r.race_number
LIMIT 30
"""

df = pd.read_sql_query(query, conn)
print(df.to_string(index=False))
print()

# 該当2レースの詳細
print("=" * 80)
print("【該当2レース詳細】")
print("=" * 80)

for race_id in [169834, 169274]:
    print(f"\nrace_id={race_id}:")
    race_info = pd.read_sql_query(f"""
        SELECT
            r.id,
            r.race_date,
            r.venue_code,
            r.race_number,
            r.race_time
        FROM races r
        WHERE r.id = '{race_id}'
    """, conn)
    print("レース情報:")
    print(race_info.to_string(index=False))

    odds_info = pd.read_sql_query(f"""
        SELECT
            MIN(fetched_at) as earliest_fetch,
            MAX(fetched_at) as latest_fetch,
            COUNT(DISTINCT fetched_at) as fetch_count
        FROM trifecta_odds
        WHERE race_id = '{race_id}'
    """, conn)
    print("\nオッズ取得情報:")
    print(odds_info.to_string(index=False))
    print()

# オッズ取得タイミングの統計（2026年1月）
print("=" * 80)
print("【2026年1月のオッズ取得タイミング統計】")
print("=" * 80)

timing_stats = pd.read_sql_query("""
SELECT
    CASE
        WHEN hours_before < 0 THEN 'レース後'
        WHEN hours_before < 1 THEN 'レース1時間前以内'
        WHEN hours_before < 6 THEN 'レース6時間前以内'
        WHEN hours_before < 12 THEN 'レース12時間前以内'
        WHEN hours_before < 24 THEN 'レース24時間前以内'
        ELSE 'レース24時間以上前'
    END as timing_category,
    COUNT(*) as race_count
FROM (
    SELECT
        r.id,
        JULIANDAY(r.race_date || ' ' || r.race_time) - JULIANDAY(MIN(t.fetched_at)) as hours_before
    FROM races r
    INNER JOIN trifecta_odds t ON r.id = t.race_id
    WHERE r.race_date >= '2026-01-01' AND r.race_date <= '2026-01-23'
      AND r.race_time IS NOT NULL
    GROUP BY r.id
) sub
GROUP BY timing_category
ORDER BY
    CASE timing_category
        WHEN 'レース後' THEN 1
        WHEN 'レース1時間前以内' THEN 2
        WHEN 'レース6時間前以内' THEN 3
        WHEN 'レース12時間前以内' THEN 4
        WHEN 'レース24時間前以内' THEN 5
        ELSE 6
    END
""", conn)
print(timing_stats.to_string(index=False))

conn.close()
