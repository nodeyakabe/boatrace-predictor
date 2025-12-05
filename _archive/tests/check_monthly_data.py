"""
月別データ取得状況確認
"""

import sqlite3

DB_PATH = 'data/boatrace_readonly.db'

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 月別データ取得状況
cursor.execute("""
    SELECT
        SUBSTR(race_date, 1, 7) as month,
        COUNT(*) as count,
        COUNT(DISTINCT venue_code) as venues
    FROM races
    GROUP BY month
    ORDER BY month DESC
""")

months = cursor.fetchall()

print("取得済みの月別データ:")
print("=" * 60)
print(f"{'月':10s} | {'レース数':>8s} | {'会場数':>6s}")
print("-" * 60)

for month, count, venues in months:
    print(f"{month:10s} | {count:8,d} | {venues:6d}")

print("-" * 60)

cursor.execute("SELECT COUNT(*) FROM races")
total = cursor.fetchone()[0]
print(f"{'合計':10s} | {total:8,d}")

print("\n" + "=" * 60)

# 結果データがある月
cursor.execute("""
    SELECT
        SUBSTR(r.race_date, 1, 7) as month,
        COUNT(DISTINCT res.race_id) as result_count
    FROM races r
    LEFT JOIN results res ON r.id = res.race_id
    GROUP BY month
    ORDER BY month DESC
""")

results_months = cursor.fetchall()

print("\n結果データ取得状況:")
print("=" * 60)
print(f"{'月':10s} | {'結果数':>8s}")
print("-" * 60)

for month, count in results_months:
    print(f"{month:10s} | {count:8,d}")

conn.close()
