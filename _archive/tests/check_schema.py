"""
Database schema checker and migration
"""
import sqlite3
from config.settings import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

# Create race_predictions table
print("Creating race_predictions table...")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS race_predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        race_id INTEGER NOT NULL,
        pit_number INTEGER NOT NULL,
        rank_prediction INTEGER NOT NULL,
        total_score REAL NOT NULL,
        confidence TEXT,
        racer_name TEXT,
        racer_number TEXT,
        applied_rules TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(race_id, pit_number),
        FOREIGN KEY (race_id) REFERENCES races(id)
    )
""")
conn.commit()
print("Done!\n")

print("="*70)
print("Checking table structure:")
print("="*70)
cursor.execute("PRAGMA table_info(race_predictions)")
columns = cursor.fetchall()

for col in columns:
    print(f"{col[1]} ({col[2]})")

print("\n" + "="*70)
print("All tables:")
print("="*70)

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()

for table in tables:
    print(table[0])

conn.close()
