# -*- coding: utf-8 -*-
"""
exacta_oddsテーブル作成スクリプト

2連単オッズを格納するテーブルを作成する。
"""

import sys
import os
import sqlite3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def create_exacta_odds_table():
    """exacta_oddsテーブルを作成"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # テーブル作成
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exacta_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            combination TEXT NOT NULL,          -- '1-2', '1-3', etc. (30通り)
            odds REAL NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (race_id) REFERENCES races(id),
            UNIQUE(race_id, combination)
        )
    """)

    # インデックス作成
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_exacta_odds_race_id
        ON exacta_odds(race_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_exacta_odds_combination
        ON exacta_odds(combination)
    """)

    conn.commit()

    # 確認
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='exacta_odds'")
    result = cursor.fetchone()

    if result:
        print("[OK] exacta_oddsテーブル作成成功")

        # テーブル情報を表示
        cursor.execute("PRAGMA table_info(exacta_odds)")
        columns = cursor.fetchall()
        print("\n[カラム構成]")
        for col in columns:
            print(f"  {col[1]:15s} {col[2]:10s} {'NOT NULL' if col[3] else ''}")

        # インデックス確認
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='exacta_odds'")
        indexes = cursor.fetchall()
        print("\n[インデックス]")
        for idx in indexes:
            print(f"  - {idx[0]}")
    else:
        print("[ERROR] テーブル作成失敗")

    conn.close()


if __name__ == '__main__':
    print("=== exacta_oddsテーブル作成 ===\n")
    create_exacta_odds_table()
    print("\n完了")
