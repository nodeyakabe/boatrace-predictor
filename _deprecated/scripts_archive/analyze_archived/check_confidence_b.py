"""Check confidence B data structure"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check race_predictions table structure
print("race_predictions table sample:")
cursor.execute("SELECT * FROM race_predictions LIMIT 3")
rows = cursor.fetchall()
for row in rows:
    print(row)

# Check if confidence B exists
print("\nConfidence B count:")
cursor.execute("SELECT COUNT(*) FROM race_predictions WHERE confidence = 'B'")
print(f"Total: {cursor.fetchone()[0]}")

# Check prediction types
print("\nPrediction types:")
cursor.execute("SELECT DISTINCT prediction_type FROM race_predictions")
for row in cursor.fetchall():
    print(f"  {row[0]}")

# Check confidence values
print("\nConfidence values:")
cursor.execute("SELECT confidence, COUNT(*) FROM race_predictions GROUP BY confidence")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Sample confidence B data
print("\nSample confidence B data:")
cursor.execute("""
    SELECT race_id, pit_number, confidence, total_score, rank_prediction
    FROM race_predictions
    WHERE confidence = 'B' AND prediction_type = 'advance'
    LIMIT 5
""")
for row in cursor.fetchall():
    print(row)

conn.close()
