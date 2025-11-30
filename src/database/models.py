"""
データベースモデル定義
SQLiteを使用したテーブル構造
"""

import sqlite3
from datetime import datetime
from pathlib import Path


class Database:
    """データベース管理クラス"""

    def __init__(self, db_path="data/boatrace.db"):
        """
        データベース初期化

        Args:
            db_path: データベースファイルのパス
        """
        self.db_path = db_path
        # データディレクトリが存在しない場合は作成
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = None

    def __enter__(self):
        """コンテキストマネージャー: with文の開始時に実行"""
        self.connection = self.connect()
        return self.connection

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャー: with文の終了時に実行"""
        if exc_type is not None:
            # 例外発生時はロールバック
            if self.connection:
                self.connection.rollback()
        else:
            # 正常終了時はコミット
            if self.connection:
                self.connection.commit()
        self.close()
        return False  # 例外を再送出

    def connect(self):
        """データベースに接続"""
        self.connection = sqlite3.connect(
            self.db_path,
            timeout=30.0,  # 30秒のタイムアウトを設定
            check_same_thread=False  # マルチスレッド対応
        )
        self.connection.row_factory = sqlite3.Row  # カラム名でアクセス可能にする
        return self.connection

    def close(self):
        """データベース接続を閉じる"""
        if self.connection:
            self.connection.close()

    def create_tables(self):
        """全テーブルを作成"""
        conn = self.connect()
        cursor = conn.cursor()

        # 競艇場マスタテーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS venues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # レーステーブル
        # is_shinnyuu_kotei: 進入固定レースか（1=固定、0=通常）
        # grade: グレード（SG/G1/G2/G3/一般）
        # is_nighter: ナイターレースか
        # is_ladies: 女子戦か
        # is_rookie: 新人戦か
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS races (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_code TEXT NOT NULL,
                race_date DATE NOT NULL,
                race_number INTEGER NOT NULL,
                race_time TEXT,
                grade TEXT DEFAULT '',
                is_nighter INTEGER DEFAULT 0,
                is_ladies INTEGER DEFAULT 0,
                is_rookie INTEGER DEFAULT 0,
                is_shinnyuu_kotei INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(venue_code, race_date, race_number),
                FOREIGN KEY (venue_code) REFERENCES venues(code)
            )
        """)

        # 出走表テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                pit_number INTEGER NOT NULL,
                racer_number TEXT,
                racer_name TEXT,
                racer_rank TEXT,
                racer_home TEXT,
                racer_age INTEGER,
                racer_weight REAL,
                motor_number INTEGER,
                boat_number INTEGER,
                win_rate REAL,
                second_rate REAL,
                third_rate REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (race_id) REFERENCES races(id)
            )
        """)

        # 天気テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weather (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_code TEXT NOT NULL,
                weather_date DATE NOT NULL,
                temperature REAL,
                weather_condition TEXT,
                wind_speed REAL,
                wind_direction TEXT,
                water_temperature REAL,
                wave_height REAL,
                humidity INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(venue_code, weather_date),
                FOREIGN KEY (venue_code) REFERENCES venues(code)
            )
        """)

        # 潮汐テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tide (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_code TEXT NOT NULL,
                tide_date DATE NOT NULL,
                tide_time TEXT,
                tide_type TEXT,
                tide_level REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (venue_code) REFERENCES venues(code)
            )
        """)

        # レース詳細テーブル（展示タイム、チルト、部品交換、進入コース等）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS race_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                pit_number INTEGER NOT NULL,
                exhibition_time REAL,
                tilt_angle REAL,
                parts_replacement TEXT,
                actual_course INTEGER,
                st_time REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(race_id, pit_number),
                FOREIGN KEY (race_id) REFERENCES races(id)
            )
        """)

        # レース結果テーブル（各艇の着順を記録）
        # rank: 通常は1-6の整数、イレギュラー時は'F'(フライング), 'L'(欠場), 'K'(転覆), 'S'(失格)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                pit_number INTEGER NOT NULL,
                rank TEXT,
                is_invalid INTEGER DEFAULT 0,
                trifecta_odds REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(race_id, pit_number),
                FOREIGN KEY (race_id) REFERENCES races(id)
            )
        """)

        # おすすめレーステーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                recommend_date DATE NOT NULL,
                confidence_score REAL,
                reason TEXT,
                prediction_1st INTEGER,
                prediction_2nd INTEGER,
                prediction_3rd INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (race_id) REFERENCES races(id)
            )
        """)

        conn.commit()
        self.close()
        print("データベーステーブルを作成しました")

    def initialize_venues(self, venues_data):
        """
        競艇場マスタデータを初期投入

        Args:
            venues_data: 競艇場情報の辞書
        """
        conn = self.connect()
        cursor = conn.cursor()

        for key, venue in venues_data.items():
            cursor.execute("""
                INSERT OR IGNORE INTO venues (code, name, latitude, longitude)
                VALUES (?, ?, ?, ?)
            """, (venue['code'], venue['name'], venue['latitude'], venue['longitude']))

        conn.commit()
        self.close()
        print(f"{len(venues_data)}件の競艇場情報を登録しました")

    def migrate_add_race_columns(self):
        """
        既存のracesテーブルに新カラムを追加するマイグレーション

        追加カラム:
        - grade: グレード（SG/G1/G2/G3/一般）
        - is_nighter: ナイターレースか
        - is_ladies: 女子戦か
        - is_rookie: 新人戦か
        - is_shinnyuu_kotei: 進入固定レースか
        """
        conn = self.connect()
        cursor = conn.cursor()

        # 既存カラムを確認
        cursor.execute("PRAGMA table_info(races)")
        existing_columns = [row[1] for row in cursor.fetchall()]

        new_columns = [
            ('grade', "TEXT DEFAULT ''"),
            ('is_nighter', 'INTEGER DEFAULT 0'),
            ('is_ladies', 'INTEGER DEFAULT 0'),
            ('is_rookie', 'INTEGER DEFAULT 0'),
            ('is_shinnyuu_kotei', 'INTEGER DEFAULT 0'),
        ]

        added = []
        for col_name, col_def in new_columns:
            if col_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE races ADD COLUMN {col_name} {col_def}")
                    added.append(col_name)
                except sqlite3.OperationalError as e:
                    print(f"カラム追加エラー ({col_name}): {e}")

        conn.commit()
        self.close()

        if added:
            print(f"racesテーブルにカラムを追加しました: {', '.join(added)}")
        else:
            print("追加するカラムはありませんでした（既に存在）")

        return added
