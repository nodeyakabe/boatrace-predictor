"""
ˆóÇü¿İX(ÆüÖë’ı Y‹Ş¤°ìü·çó¹¯ê×È
"""
import sqlite3
from config.settings import DATABASE_PATH

def add_predictions_table():
    """ˆóÇü¿ÆüÖë’ı """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # ˆóÇü¿ÆüÖë’\
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
    print(" race_predictions ÆüÖë’\W~W_")

    # ÆüÖëË ’º
    cursor.execute("PRAGMA table_info(race_predictions)")
    columns = cursor.fetchall()

    print("\nÆüÖëË :")
    for col in columns:
        print(f"  {col[1]} ({col[2]})")

    conn.close()

if __name__ == "__main__":
    print("="*70)
    print("ˆóÇü¿ÆüÖë\¹¯ê×È")
    print("="*70)

    add_predictions_table()

    print("\n" + "="*70)
    print("Œ†")
    print("="*70)
