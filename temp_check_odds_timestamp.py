"""
trifecta_oddsテーブルのスキーマとデータ取得時刻を確認
"""
import sqlite3
import pandas as pd

DB_PATH = r'c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db'

conn = sqlite3.connect(DB_PATH)

# スキーマ確認
print("=" * 80)
print("【trifecta_oddsテーブル スキーマ】")
print("=" * 80)
schema = pd.read_sql_query("PRAGMA table_info(trifecta_odds)", conn)
print(schema)
print()

# 該当レースのオッズデータ詳細
print("=" * 80)
print("【該当2レースのtrifecta_oddsデータ詳細】")
print("=" * 80)

for race_id in [169834, 169274]:
    print(f"\nrace_id={race_id}:")
    data = pd.read_sql_query(f"""
        SELECT *
        FROM trifecta_odds
        WHERE race_id = '{race_id}'
        LIMIT 5
    """, conn)
    print(data)
    print()

# 全データ件数
print("=" * 80)
print("【trifecta_oddsテーブル全体統計】")
print("=" * 80)
stats = pd.read_sql_query("""
    SELECT
        COUNT(*) as total_records,
        COUNT(DISTINCT race_id) as total_races
    FROM trifecta_odds
""", conn)
print(stats)
print()

# オッズデータがあるレースの日付範囲
print("=" * 80)
print("【オッズデータがあるレースの日付範囲】")
print("=" * 80)
date_range = pd.read_sql_query("""
    SELECT
        MIN(r.race_date) as earliest_date,
        MAX(r.race_date) as latest_date
    FROM races r
    INNER JOIN trifecta_odds t ON r.id = t.race_id
""", conn)
print(date_range)
print()

# 2026年のオッズデータ
print("=" * 80)
print("【2026年のオッズデータ件数（日付別）】")
print("=" * 80)
recent_odds = pd.read_sql_query("""
    SELECT
        r.race_date,
        COUNT(DISTINCT r.id) as race_count,
        COUNT(*) as odds_count
    FROM races r
    INNER JOIN trifecta_odds t ON r.id = t.race_id
    WHERE r.race_date >= '2026-01-01'
    GROUP BY r.race_date
    ORDER BY r.race_date DESC
    LIMIT 20
""", conn)
print(recent_odds)

conn.close()
