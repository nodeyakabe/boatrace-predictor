"""
選手ベースの特徴量計算モジュール

改善アドバイスに基づく選手特徴量:
- recent_avg_rank_3/5/10: 直近N戦平均着順
- recent_win_rate_N: 直近N戦勝率
- motor_recent_2rate_diff: モーター直近2連率差分
"""

import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, Optional


class RacerFeatureExtractor:
    """選手特徴量の抽出クラス"""

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path

    def compute_recent_avg_rank(
        self,
        racer_number: str,
        race_date: str,
        n_races: int = 5,
        conn: Optional[sqlite3.Connection] = None
    ) -> float:
        """
        直近N戦の平均着順を計算

        Args:
            racer_number: 選手登録番号
            race_date: 対象レース日（この日より前のレースを参照）
            n_races: 直近何戦を見るか（3, 5, 10推奨）
            conn: DBコネクション（Noneなら新規作成）

        Returns:
            平均着順（float）。データなしの場合は3.5（中央値）を返す
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            query = """
            SELECT
                r.rank
            FROM results r
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            JOIN races rc ON r.race_id = rc.id
            WHERE e.racer_number = ?
              AND rc.race_date < ?
              AND r.rank IS NOT NULL
              AND r.rank != ''
            ORDER BY rc.race_date DESC, rc.race_number DESC
            LIMIT ?
            """

            df = pd.read_sql_query(query, conn, params=(racer_number, race_date, n_races))

            if len(df) == 0:
                return 3.5  # デフォルト（1〜6着の中央値）

            # rankを数値に変換（'1', '2', ..., '6', '不', 'F'など）
            ranks = []
            for rank_str in df['rank']:
                try:
                    rank_num = int(rank_str)
                    # 1〜6着のみ有効
                    if 1 <= rank_num <= 6:
                        ranks.append(rank_num)
                    else:
                        ranks.append(6)  # 異常値は最下位扱い
                except (ValueError, TypeError):
                    # 不明・失格などは最下位扱い
                    ranks.append(6)

            if len(ranks) == 0:
                return 3.5

            return float(np.mean(ranks))

        finally:
            if close_conn:
                conn.close()

    def compute_recent_win_rate(
        self,
        racer_number: str,
        race_date: str,
        n_races: int = 5,
        conn: Optional[sqlite3.Connection] = None
    ) -> float:
        """
        直近N戦の勝率（1着率）を計算

        Args:
            racer_number: 選手登録番号
            race_date: 対象レース日
            n_races: 直近何戦を見るか
            conn: DBコネクション

        Returns:
            勝率（0.0〜1.0）
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            query = """
            SELECT
                r.rank
            FROM results r
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            JOIN races rc ON r.race_id = rc.id
            WHERE e.racer_number = ?
              AND rc.race_date < ?
              AND r.rank IS NOT NULL
              AND r.rank != ''
            ORDER BY rc.race_date DESC, rc.race_number DESC
            LIMIT ?
            """

            df = pd.read_sql_query(query, conn, params=(racer_number, race_date, n_races))

            if len(df) == 0:
                return 0.0

            # 1着の回数をカウント
            wins = sum(1 for rank_str in df['rank'] if str(rank_str) == '1')

            return wins / len(df)

        finally:
            if close_conn:
                conn.close()

    def compute_motor_recent_2rate_diff(
        self,
        racer_number: str,
        motor_number: int,
        race_date: str,
        conn: Optional[sqlite3.Connection] = None
    ) -> float:
        """
        モーター直近2連率と選手全国2連率の差分

        モーターの性能が選手の平均より高いか低いかを示す指標

        Args:
            racer_number: 選手登録番号
            motor_number: モーター番号
            race_date: 対象レース日
            conn: DBコネクション

        Returns:
            差分（motor_2rate - racer_2rate）
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            # 選手の全国2連率（entries.second_rateが既に持っている）
            query_racer = """
            SELECT e.second_rate
            FROM entries e
            JOIN races rc ON e.race_id = rc.id
            WHERE e.racer_number = ?
              AND rc.race_date <= ?
              AND e.second_rate IS NOT NULL
            ORDER BY rc.race_date DESC
            LIMIT 1
            """
            df_racer = pd.read_sql_query(query_racer, conn, params=(racer_number, race_date))

            if len(df_racer) == 0 or df_racer['second_rate'].iloc[0] is None:
                racer_2rate = 0.0
            else:
                racer_2rate = float(df_racer['second_rate'].iloc[0])

            # モーターの直近2連率（entries.motor_second_rateが既に持っている）
            query_motor = """
            SELECT e.motor_second_rate
            FROM entries e
            JOIN races rc ON e.race_id = rc.id
            WHERE e.motor_number = ?
              AND rc.race_date <= ?
              AND e.motor_second_rate IS NOT NULL
            ORDER BY rc.race_date DESC
            LIMIT 1
            """
            df_motor = pd.read_sql_query(query_motor, conn, params=(motor_number, race_date))

            if len(df_motor) == 0 or df_motor['motor_second_rate'].iloc[0] is None:
                motor_2rate = 0.0
            else:
                motor_2rate = float(df_motor['motor_second_rate'].iloc[0])

            return motor_2rate - racer_2rate

        finally:
            if close_conn:
                conn.close()

    def extract_all_features(
        self,
        racer_number: str,
        motor_number: int,
        race_date: str,
        conn: Optional[sqlite3.Connection] = None
    ) -> Dict[str, float]:
        """
        全ての選手特徴量を一括抽出

        Args:
            racer_number: 選手登録番号
            motor_number: モーター番号
            race_date: 対象レース日
            conn: DBコネクション

        Returns:
            特徴量辞書
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            features = {}

            # 直近N戦平均着順（3, 5, 10）
            features['recent_avg_rank_3'] = self.compute_recent_avg_rank(
                racer_number, race_date, n_races=3, conn=conn
            )
            features['recent_avg_rank_5'] = self.compute_recent_avg_rank(
                racer_number, race_date, n_races=5, conn=conn
            )
            features['recent_avg_rank_10'] = self.compute_recent_avg_rank(
                racer_number, race_date, n_races=10, conn=conn
            )

            # 直近N戦勝率
            features['recent_win_rate_3'] = self.compute_recent_win_rate(
                racer_number, race_date, n_races=3, conn=conn
            )
            features['recent_win_rate_5'] = self.compute_recent_win_rate(
                racer_number, race_date, n_races=5, conn=conn
            )
            features['recent_win_rate_10'] = self.compute_recent_win_rate(
                racer_number, race_date, n_races=10, conn=conn
            )

            # モーター2連率差分
            features['motor_recent_2rate_diff'] = self.compute_motor_recent_2rate_diff(
                racer_number, motor_number, race_date, conn=conn
            )

            return features

        finally:
            if close_conn:
                conn.close()


# 便利関数
def extract_racer_features(
    racer_number: str,
    motor_number: int,
    race_date: str,
    db_path: str = 'data/boatrace.db'
) -> Dict[str, float]:
    """
    選手特徴量を抽出（関数形式のインターフェース）

    Args:
        racer_number: 選手登録番号
        motor_number: モーター番号
        race_date: レース日（YYYY-MM-DD形式）
        db_path: データベースパス

    Returns:
        特徴量辞書

    Example:
        >>> features = extract_racer_features('4444', 12, '2024-06-15')
        >>> print(features['recent_avg_rank_5'])
        2.8
    """
    extractor = RacerFeatureExtractor(db_path)
    return extractor.extract_all_features(racer_number, motor_number, race_date)
