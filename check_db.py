import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cur = conn.cursor()

# race_predictionsのサンプル
cur.execute("SELECT race_id, prediction_type FROM race_predictions WHERE prediction_type='before' LIMIT 5")
print("race_predictions (before):")
for r in cur.fetchall():
    print(f"  race_id={r[0]}, type={r[1]}")

# racesテーブルのサンプル
cur.execute("SELECT id, race_date FROM races LIMIT 5")
print("\nraces:")
for r in cur.fetchall():
    print(f"  id={r[0]}, date={r[1]}")

# 2020年レースのID範囲
cur.execute("SELECT MIN(id), MAX(id), COUNT(*) FROM races WHERE race_date LIKE '2020%'")
row = cur.fetchone()
print(f"\n2020年レースのID範囲: {row[0]}〜{row[1]}、合計{row[2]}件")

# 2020年のbefore予想件数（正しいJOIN）
cur.execute("""
    SELECT COUNT(*)
    FROM race_predictions rp
    JOIN races r ON r.id = rp.race_id
    WHERE r.race_date LIKE '2020%'
    AND rp.prediction_type = 'before'
""")
print(f"\n2020年のbefore予想件数（JOIN）: {cur.fetchone()[0]:,}件")

conn.close()
