# -*- coding: utf-8 -*-
"""
指標データテーブル定義

逃げ率・まくり率・差し率の計算結果を保存するテーブル
"""

import sqlite3
from typing import Optional


class IndicatorTables:
    """指標データ用テーブル管理"""

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path

    def create_tables(self):
        """指標テーブルを作成"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 選手別逃げ率テーブル
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS player_escape_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id TEXT NOT NULL,
                    stadium_id TEXT,
                    races_1course INTEGER NOT NULL,
                    wins_1course INTEGER NOT NULL,
                    escape_rate REAL,
                    period_start DATE NOT NULL,
                    period_end DATE NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(player_id, stadium_id, period_start, period_end)
                )
            ''')

            # インデックス作成
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_player_escape_player
                ON player_escape_stats(player_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_player_escape_stadium
                ON player_escape_stats(stadium_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_player_escape_period
                ON player_escape_stats(period_start, period_end)
            ''')

            # 会場別まくり率・差し率テーブル
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stadium_attack_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stadium_id TEXT NOT NULL,
                    total_races INTEGER NOT NULL,
                    course2_wins INTEGER NOT NULL,
                    course3_wins INTEGER NOT NULL,
                    course4_wins INTEGER NOT NULL,
                    course5_wins INTEGER NOT NULL,
                    makuri_rate REAL NOT NULL,
                    sashi_rate REAL NOT NULL,
                    period_start DATE NOT NULL,
                    period_end DATE NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stadium_id, period_start, period_end)
                )
            ''')

            # インデックス作成
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_stadium_attack_stadium
                ON stadium_attack_stats(stadium_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_stadium_attack_period
                ON stadium_attack_stats(period_start, period_end)
            ''')

            conn.commit()
            print("[OK] 指標テーブルを作成しました")

    def drop_tables(self):
        """指標テーブルを削除（再作成用）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DROP TABLE IF EXISTS player_escape_stats')
            cursor.execute('DROP TABLE IF EXISTS stadium_attack_stats')
            conn.commit()
            print("[OK] 指標テーブルを削除しました")

    def get_table_stats(self) -> dict:
        """テーブルの統計情報を取得"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            stats = {}

            # player_escape_stats
            cursor.execute('SELECT COUNT(*) FROM player_escape_stats')
            stats['player_escape_stats'] = cursor.fetchone()[0]

            # stadium_attack_stats
            cursor.execute('SELECT COUNT(*) FROM stadium_attack_stats')
            stats['stadium_attack_stats'] = cursor.fetchone()[0]

            return stats


if __name__ == "__main__":
    tables = IndicatorTables()
    tables.create_tables()
    print("\nテーブル統計:")
    print(tables.get_table_stats())
