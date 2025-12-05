import sqlite3

conn = sqlite3.connect('data/boatrace_readonly.db')
cursor = conn.cursor()

# 月別のデータ数を確認
cursor.execute("""
    SELECT
        substr(race_date, 1, 7) as month,
        COUNT(*) as race_count
    FROM races
    GROUP BY month
    ORDER BY month
""")

rows = cursor.fetchall()

print("月別レース数:")
for row in rows:
    print(f"  {row[0]}: {row[1]}レース")

print(f"\n総計: {sum(r[1] for r in rows)}レース")

conn.close()
