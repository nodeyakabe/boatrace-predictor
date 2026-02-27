"""
特徴量事前計算システム

選手特徴量と会場特徴量を事前に計算してDBに保存し、
学習時に高速に読み込めるようにする。

2026-02-26 最適化: N+1クエリを一括ロード+pandasに置き換え（95%以上の高速化）
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
            batch_size: 互換性のため残存（一括処理では未使用）
        """
        conn = sqlite3.connect(self.db_path)
        print(f"\n選手特徴量計算: {start_date} 〜 {end_date}")

        # 既存データの範囲確認
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM racer_features")
        min_d, max_d = cursor.fetchone()
        conn.close()

        if min_d:
            print(f"既存データ範囲: {min_d} 〜 {max_d}")
            if min_d <= start_date and max_d >= end_date:
                print("[OK] 既に全期間のデータが存在します")
                return

        self._compute_racer_features_bulk(start_date, end_date)
        print("[OK] 選手特徴量計算完了")

    def _compute_racer_features_bulk(self, start_date: str, end_date: str) -> int:
        """
        選手特徴量一括計算（高速版）

        全結果データを一括メモリロードし、pandas+numpyで処理することで
        N+1クエリ問題を解消。推定処理時間: ~10分（旧版: 2〜5時間）

        Returns:
            保存件数
        """
        conn = sqlite3.connect(self.db_path)
        computed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ---- Step 1: 全結果データを一括ロード ----
        print("  [Bulk] 全結果データ読み込み中...")
        hist_df = pd.read_sql_query("""
            SELECT
                e.racer_number,
                r.race_date,
                r.race_number,
                CAST(res.rank AS INTEGER) AS rank
            FROM results res
            JOIN races r ON res.race_id = r.id
            JOIN entries e ON res.race_id = e.race_id
                          AND res.pit_number = e.pit_number
            WHERE res.rank IN ('1', '2', '3', '4', '5', '6')
            ORDER BY e.racer_number, r.race_date, r.race_number
        """, conn)
        print(f"  [Bulk] 結果データ: {len(hist_df):,}件")

        # ---- Step 2: 対象（racer_number, race_date）を取得 ----
        target_df = pd.read_sql_query("""
            SELECT DISTINCT
                e.racer_number,
                r.race_date
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date BETWEEN ? AND ?
            ORDER BY e.racer_number, r.race_date
        """, conn, params=(start_date, end_date))
        total = len(target_df)
        print(f"  [Bulk] 対象: {total:,}件")

        conn.close()

        # ---- Step 3: 選手別に履歴をインデックス化 ----
        hist_by_racer = {}
        for racer, grp in hist_df.groupby('racer_number', sort=False):
            hist_by_racer[racer] = (
                grp['race_date'].values,
                grp['rank'].values
            )

        # ---- Step 4: シーケンシャルスキャンで特徴量計算 ----
        rows = []
        for racer, grp_tgt in target_df.groupby('racer_number', sort=False):
            target_dates = np.sort(grp_tgt['race_date'].values)
            hist_dates, hist_ranks = hist_by_racer.get(
                racer, (np.array([]), np.array([]))
            )

            ptr = 0  # hist_dates内で race_date 未満の境界ポインタ
            for race_date in target_dates:
                # race_date より前のデータを全て取得（シーケンシャル）
                while ptr < len(hist_dates) and hist_dates[ptr] < race_date:
                    ptr += 1

                past = hist_ranks[:ptr]
                n = len(past)

                rows.append((
                    racer,
                    race_date,
                    float(np.mean(past[-3:])) if n >= 3 else None,
                    float(np.mean(past[-5:])) if n >= 5 else None,
                    float(np.mean(past[-10:])) if n >= 10 else None,
                    float(np.mean(past[-3:] == 1)) if n >= 3 else None,
                    float(np.mean(past[-5:] == 1)) if n >= 5 else None,
                    float(np.mean(past[-10:] == 1)) if n >= 10 else None,
                    n,
                    computed_at,
                ))

        # ---- Step 5: バルクINSERT ----
        print(f"  [Bulk] INSERT: {len(rows):,}件...")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT OR REPLACE INTO racer_features (
                racer_number, race_date,
                recent_avg_rank_3, recent_avg_rank_5, recent_avg_rank_10,
                recent_win_rate_3, recent_win_rate_5, recent_win_rate_10,
                total_races, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
        conn.close()

        print(f"  [Bulk] {len(rows):,}件 保存完了")
        return len(rows)

    def _calculate_racer_recent_performance(
        self,
        conn: sqlite3.Connection,
        racer_number: str,
        race_date: str
    ) -> dict:
        """選手の直近N戦成績を計算（レガシー: 単一行処理用）"""

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
        """選手特徴量をバッチ保存（レガシー）"""
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

        # 既存データの範囲確認
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM racer_venue_features")
        min_d, max_d = cursor.fetchone()
        conn.close()

        if min_d:
            print(f"既存データ範囲: {min_d} 〜 {max_d}")
            if min_d <= start_date and max_d >= end_date:
                print("[OK] 既に全期間のデータが存在します")
                return

        self._compute_venue_features_bulk(start_date, end_date)
        print("[OK] 会場別選手特徴量計算完了")

    def _compute_venue_features_bulk(self, start_date: str, end_date: str) -> int:
        """
        会場別選手特徴量一括計算（高速版）

        Returns:
            保存件数
        """
        conn = sqlite3.connect(self.db_path)
        computed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ---- Step 1: 全結果データを一括ロード（venue_code付き） ----
        print("  [Bulk] 全会場別結果データ読み込み中...")
        hist_df = pd.read_sql_query("""
            SELECT
                e.racer_number,
                r.venue_code,
                r.race_date,
                r.race_number,
                CAST(res.rank AS INTEGER) AS rank
            FROM results res
            JOIN races r ON res.race_id = r.id
            JOIN entries e ON res.race_id = e.race_id
                          AND res.pit_number = e.pit_number
            WHERE res.rank IN ('1', '2', '3', '4', '5', '6')
            ORDER BY e.racer_number, r.venue_code, r.race_date, r.race_number
        """, conn)
        print(f"  [Bulk] 結果データ: {len(hist_df):,}件")

        # ---- Step 2: 対象取得 ----
        target_df = pd.read_sql_query("""
            SELECT DISTINCT
                e.racer_number,
                r.venue_code,
                r.race_date
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date BETWEEN ? AND ?
            ORDER BY e.racer_number, r.venue_code, r.race_date
        """, conn, params=(start_date, end_date))
        total = len(target_df)
        print(f"  [Bulk] 対象: {total:,}件")

        conn.close()

        # ---- Step 3: (racer, venue)別に履歴をインデックス化 ----
        hist_by_key = {}
        for key, grp in hist_df.groupby(
            ['racer_number', 'venue_code'], sort=False
        ):
            hist_by_key[key] = (
                grp['race_date'].values,
                grp['rank'].values
            )

        # ---- Step 4: シーケンシャルスキャンで特徴量計算 ----
        rows = []
        for key, grp_tgt in target_df.groupby(
            ['racer_number', 'venue_code'], sort=False
        ):
            racer, venue = key
            target_dates = np.sort(grp_tgt['race_date'].values)
            hist_dates, hist_ranks = hist_by_key.get(
                key, (np.array([]), np.array([]))
            )

            ptr = 0
            for race_date in target_dates:
                while ptr < len(hist_dates) and hist_dates[ptr] < race_date:
                    ptr += 1

                past = hist_ranks[:ptr]
                n = len(past)

                rows.append((
                    racer,
                    venue,
                    race_date,
                    float(np.mean(past == 1)) if n > 0 else None,
                    float(np.mean(past)) if n > 0 else None,
                    n,
                    computed_at,
                ))

        # ---- Step 5: バルクINSERT ----
        print(f"  [Bulk] INSERT: {len(rows):,}件...")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT OR REPLACE INTO racer_venue_features (
                racer_number, venue_code, race_date,
                venue_win_rate, venue_avg_rank, venue_races, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
        conn.close()

        print(f"  [Bulk] {len(rows):,}件 保存完了")
        return len(rows)

    def _calculate_venue_performance(
        self,
        conn: sqlite3.Connection,
        racer_number: str,
        venue_code: str,
        race_date: str
    ) -> dict:
        """会場別選手成績を計算（レガシー: 単一行処理用）"""

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
        """会場別特徴量をバッチ保存（レガシー）"""
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
