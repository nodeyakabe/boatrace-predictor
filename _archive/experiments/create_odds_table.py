"""
オッズテーブル作成スクリプト
"""
import sqlite3
from config.settings import DATABASE_PATH

def create_odds_tables():
    """オッズ関連テーブルを作成"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 3連単オッズテーブル
    print("Creating trifecta_odds table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trifecta_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            combination TEXT NOT NULL,
            odds REAL NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(race_id, combination),
            FOREIGN KEY (race_id) REFERENCES races(id)
        )
    """)

    # 単勝オッズテーブル
    print("Creating win_odds table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS win_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            pit_number INTEGER NOT NULL,
            odds REAL NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(race_id, pit_number),
            FOREIGN KEY (race_id) REFERENCES races(id)
        )
    """)

    # インデックス作成
    print("Creating indexes...")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_trifecta_odds_race_id
        ON trifecta_odds(race_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_win_odds_race_id
        ON win_odds(race_id)
    """)

    conn.commit()
    print("Done!\n")

    # テーブル構造を確認
    print("="*70)
    print("Table structures:")
    print("="*70)

    for table_name in ['trifecta_odds', 'win_odds']:
        print(f"\n{table_name}:")
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  {col[1]} ({col[2]})")

    conn.close()

if __name__ == "__main__":
    print("="*70)
    print("オッズテーブル作成")
    print("="*70)

    create_odds_tables()

    print("\n" + "="*70)
    print("完了")
    print("="*70)
