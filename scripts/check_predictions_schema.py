import sqlite3

conn = sqlite3.connect("data/boatrace.db")
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(race_predictions)")
columns = cursor.fetchall()

for col in columns:
    print(col)

conn.close()
