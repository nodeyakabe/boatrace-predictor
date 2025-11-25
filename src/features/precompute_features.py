"""
特徴量事前計算システム

選手特徴量と会場特徴量を事前に計算してDBに保存し、
学習時に高速に読み込めるようにする。
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from pathlib import Path


class FeaturePrecomputer:
    """特徴量事前計算クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def create_feature_tables(self):
        """特徴量保存用テーブルを作成"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 選手特徴量テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS racer_features (
                racer_number TEXT,
                race_date TEXT,
                recent_avg_rank_3 REAL,
                recent_avg_rank_5 REAL,
                recent_avg_rank_10 REAL,
                recent_win_rate_3 REAL,
                recent_win_rate_5 REAL,
                recent_win_rate_10 REAL,
                total_races INTEGER,
                computed_at TEXT,
                PRIMARY KEY (racer_number, race_date)
            )
        """)

        # 会場別選手成績テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS racer_venue_features (
                racer_number TEXT,
                venue_code TEXT,
                race_date TEXT,
                venue_win_rate REAL,
                venue_avg_rank REAL,
                venue_races INTEGER,
                computed_at TEXT,
                PRIMARY KEY (racer_number, venue_code, race_date)
            )
        """)

        # モーター特徴量テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS motor_features (
                race_id INTEGER,
                pit_number INTEGER,
                motor_recent_2rate_diff REAL,
                motor_trend REAL,
                computed_at TEXT,
                PRIMARY KEY (race_id, pit_number)
            )
        """)

        # インデックス作成
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_racer_features_date
            ON racer_features(race_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_racer_venue_features_date
            ON racer_venue_features(race_date)
        """)

        conn.commit()
        conn.close()

        print("[OK] 特徴量テーブル作成完了")

    def compute_racer_features(
        self,
        start_date: str,
        end_date: str,
        batch_size: int = 1000
    ):
        """
        選手特徴量を一括計算してDBに保存

        Args:
            start_date: 開始日（YYYY-MM-DD）
            end_date: 終了日（YYYY-MM-DD）
            batch_size: バッチサイズ
        """
        conn = sqlite3.connect(self.db_path)

        print(f"\n選手特徴量計算: {start_date} 〜 {end_date}")

        # 既存データの最大日付を取得
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(race_date) FROM racer_features")
        max_date_result = cursor.fetchone()[0]

        # 既存データがある場合は、既存データの範囲を確認
        if max_date_result:
            print(f"既存データ: 〜 {max_date_result}")
            # 既存データの最小日付も取得
            cursor.execute("SELECT MIN(race_date) FROM racer_features")
            min_date_result = cursor.fetchone()[0]
            print(f"既存データ範囲: {min_date_result} 〜 {max_date_result}")

            # 要求期間が既存データに完全に含まれているかチェック
            if min_date_result and min_date_result <= start_date and max_date_result >= end_date:
                print("[OK] 既に全期間のデータが存在します")
                conn.close()
                return

        # 対象期間のレース一覧取得
        query = """
            SELECT DISTINCT
                e.racer_number,
                r.race_date
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date BETWEEN ? AND ?
            ORDER BY r.race_date, e.racer_number
        """

        df_targets = pd.read_sql_query(query, conn, params=(start_date, end_date))
        total = len(df_targets)

        print(f"対象: {total:,}件")

        # バッチ処理
        computed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        batch_data = []

        for idx, row in df_targets.iterrows():
            racer_number = row['racer_number']
            race_date = row['race_date']

            # 直近N戦の成績を取得
            features = self._calculate_racer_recent_performance(
                conn, racer_number, race_date
            )

            features['racer_number'] = racer_number
            features['race_date'] = race_date
            features['computed_at'] = computed_at

            batch_data.append(features)

            # バッチ保存
            if len(batch_data) >= batch_size:
                self._save_racer_features_batch(conn, batch_data)
                batch_data = []
                print(f"  進捗: {idx+1:,}/{total:,} ({(idx+1)/total*100:.1f}%)")

        # 残りを保存
        if batch_data:
            self._save_racer_features_batch(conn, batch_data)

        conn.close()
        print("[OK] 選手特徴量計算完了")

    def _calculate_racer_recent_performance(
        self,
        conn: sqlite3.Connection,
        racer_number: str,
        race_date: str
    ) -> dict:
        """選手の直近N戦成績を計算"""

        # race_dateより前の直近レース結果を取得
        query = """
            SELECT
                CAST(res.rank AS INTEGER) as rank
            FROM results res
            JOIN races r ON res.race_id = r.id
            JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND r.race_date < ?
              AND res.rank IN ('1', '2', '3', '4', '5', '6')
            ORDER BY r.race_date DESC, r.race_number DESC
            LIMIT 10
        """

        df = pd.read_sql_query(query, conn, params=(racer_number, race_date))

        features = {
            'recent_avg_rank_3': None,
            'recent_avg_rank_5': None,
            'recent_avg_rank_10': None,
            'recent_win_rate_3': None,
            'recent_win_rate_5': None,
            'recent_win_rate_10': None,
            'total_races': len(df)
        }

        if len(df) >= 3:
            features['recent_avg_rank_3'] = df['rank'].iloc[:3].mean()
            features['recent_win_rate_3'] = (df['rank'].iloc[:3] == 1).mean()

        if len(df) >= 5:
            features['recent_avg_rank_5'] = df['rank'].iloc[:5].mean()
            features['recent_win_rate_5'] = (df['rank'].iloc[:5] == 1).mean()

        if len(df) >= 10:
            features['recent_avg_rank_10'] = df['rank'].mean()
            features['recent_win_rate_10'] = (df['rank'] == 1).mean()

        return features

    def _save_racer_features_batch(
        self,
        conn: sqlite3.Connection,
        batch_data: List[dict]
    ):
        """選手特徴量をバッチ保存"""
        cursor = conn.cursor()

        for data in batch_data:
            cursor.execute("""
                INSERT OR REPLACE INTO racer_features (
                    racer_number, race_date, recent_avg_rank_3, recent_avg_rank_5,
                    recent_avg_rank_10, recent_win_rate_3, recent_win_rate_5,
                    recent_win_rate_10, total_races, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data['racer_number'], data['race_date'],
                data['recent_avg_rank_3'], data['recent_avg_rank_5'],
                data['recent_avg_rank_10'], data['recent_win_rate_3'],
                data['recent_win_rate_5'], data['recent_win_rate_10'],
                data['total_races'], data['computed_at']
            ))

        conn.commit()

    def compute_venue_features(
        self,
        start_date: str,
        end_date: str,
        batch_size: int = 1000
    ):
        """会場別選手成績を一括計算"""
        conn = sqlite3.connect(self.db_path)

        print(f"\n会場別選手特徴量計算: {start_date} 〜 {end_date}")

        # 既存データの最大日付を取得
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(race_date) FROM racer_venue_features")
        max_date_result = cursor.fetchone()[0]

        # 既存データがある場合は、既存データの範囲を確認
        if max_date_result:
            print(f"既存データ: 〜 {max_date_result}")
            # 既存データの最小日付も取得
            cursor.execute("SELECT MIN(race_date) FROM racer_venue_features")
            min_date_result = cursor.fetchone()[0]
            print(f"既存データ範囲: {min_date_result} 〜 {max_date_result}")

            # 要求期間が既存データに完全に含まれているかチェック
            if min_date_result and min_date_result <= start_date and max_date_result >= end_date:
                print("[OK] 既に全期間のデータが存在します")
                conn.close()
                return

        # 対象取得
        query = """
            SELECT DISTINCT
                e.racer_number,
                r.venue_code,
                r.race_date
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date BETWEEN ? AND ?
            ORDER BY r.race_date, e.racer_number, r.venue_code
        """

        df_targets = pd.read_sql_query(query, conn, params=(start_date, end_date))
        total = len(df_targets)

        print(f"対象: {total:,}件")

        computed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        batch_data = []

        for idx, row in df_targets.iterrows():
            racer_number = row['racer_number']
            venue_code = row['venue_code']
            race_date = row['race_date']

            # 会場別成績計算
            features = self._calculate_venue_performance(
                conn, racer_number, venue_code, race_date
            )

            features['racer_number'] = racer_number
            features['venue_code'] = venue_code
            features['race_date'] = race_date
            features['computed_at'] = computed_at

            batch_data.append(features)

            if len(batch_data) >= batch_size:
                self._save_venue_features_batch(conn, batch_data)
                batch_data = []
                print(f"  進捗: {idx+1:,}/{total:,} ({(idx+1)/total*100:.1f}%)")

        if batch_data:
            self._save_venue_features_batch(conn, batch_data)

        conn.close()
        print("[OK] 会場別選手特徴量計算完了")

    def _calculate_venue_performance(
        self,
        conn: sqlite3.Connection,
        racer_number: str,
        venue_code: str,
        race_date: str
    ) -> dict:
        """会場別選手成績を計算"""

        query = """
            SELECT
                CAST(res.rank AS INTEGER) as rank
            FROM results res
            JOIN races r ON res.race_id = r.id
            JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND r.venue_code = ?
              AND r.race_date < ?
              AND res.rank IN ('1', '2', '3', '4', '5', '6')
        """

        df = pd.read_sql_query(query, conn, params=(racer_number, venue_code, race_date))

        features = {
            'venue_win_rate': None,
            'venue_avg_rank': None,
            'venue_races': len(df)
        }

        if len(df) > 0:
            features['venue_win_rate'] = (df['rank'] == 1).mean()
            features['venue_avg_rank'] = df['rank'].mean()

        return features

    def _save_venue_features_batch(
        self,
        conn: sqlite3.Connection,
        batch_data: List[dict]
    ):
        """会場別特徴量をバッチ保存"""
        cursor = conn.cursor()

        for data in batch_data:
            cursor.execute("""
                INSERT OR REPLACE INTO racer_venue_features (
                    racer_number, venue_code, race_date,
                    venue_win_rate, venue_avg_rank, venue_races, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                data['racer_number'], data['venue_code'], data['race_date'],
                data['venue_win_rate'], data['venue_avg_rank'],
                data['venue_races'], data['computed_at']
            ))

        conn.commit()


def main():
    """メイン処理"""
    print("=" * 70)
    print("特徴量事前計算システム")
    print("=" * 70)

    precomputer = FeaturePrecomputer()

    # テーブル作成
    print("\n[Step 1] テーブル作成")
    precomputer.create_feature_tables()

    # 計算期間（バックテスト期間に絞る）
    start_date = "2024-04-01"
    end_date = "2024-06-30"

    # 選手特徴量計算
    print(f"\n[Step 2] 選手特徴量計算")
    precomputer.compute_racer_features(start_date, end_date, batch_size=500)

    # 会場別特徴量計算
    print(f"\n[Step 3] 会場別選手特徴量計算")
    precomputer.compute_venue_features(start_date, end_date, batch_size=500)

    print("\n" + "=" * 70)
    print("特徴量事前計算完了")
    print("=" * 70)


if __name__ == "__main__":
    main()
