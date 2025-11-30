"""
ST時系列特徴量生成
Phase 4: 選手のSTパターンをシーケンスデータとして取得
"""
import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta


class STSequenceFeatureGenerator:
    """
    ST時系列特徴量生成クラス

    直近N走のSTをシーケンスとして取得し、
    パターン（揺らぎ・トレンド）を特徴量化
    """

    DEFAULT_SEQUENCE_LENGTH = 30  # 直近30走

    def __init__(self, db_path: str, sequence_length: int = 30):
        self.db_path = db_path
        self.sequence_length = sequence_length

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_st_sequence(self, racer_number: str,
                         target_date: str,
                         venue_code: str = None) -> np.ndarray:
        """
        選手のSTシーケンスを取得

        Args:
            racer_number: 選手番号
            target_date: 基準日
            venue_code: 会場コード（オプション、指定すると会場別）

        Returns:
            STシーケンス（sequence_length次元、古い順）
        """
        query = """
            SELECT rd.st_time
            FROM race_details rd
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            JOIN races r ON rd.race_id = r.id
            WHERE e.racer_number = ?
              AND r.race_date < ?
              AND rd.st_time IS NOT NULL
              AND rd.st_time > 0
        """
        params = [racer_number, target_date]

        if venue_code:
            query += " AND r.venue_code = ?"
            params.append(venue_code)

        query += " ORDER BY r.race_date DESC, r.race_number DESC LIMIT ?"
        params.append(self.sequence_length)

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()

        # シーケンスを作成（古い順に並べ直す）
        st_values = [row['st_time'] for row in reversed(results)]

        # パディング（不足分は平均値で埋める）
        if len(st_values) < self.sequence_length:
            avg_st = np.mean(st_values) if st_values else 0.15
            padding = [avg_st] * (self.sequence_length - len(st_values))
            st_values = padding + st_values

        return np.array(st_values[-self.sequence_length:])

    def calculate_st_statistics(self, st_sequence: np.ndarray) -> Dict[str, float]:
        """
        STシーケンスから統計特徴量を計算

        Args:
            st_sequence: STシーケンス

        Returns:
            統計特徴量
        """
        if len(st_sequence) == 0:
            return self._default_st_statistics()

        # 基本統計
        mean = np.mean(st_sequence)
        std = np.std(st_sequence)
        min_st = np.min(st_sequence)
        max_st = np.max(st_sequence)

        # 直近5走の統計
        recent = st_sequence[-5:]
        recent_mean = np.mean(recent)
        recent_std = np.std(recent)

        # トレンド（線形回帰の傾き）
        x = np.arange(len(st_sequence))
        if len(st_sequence) > 1:
            slope = np.polyfit(x, st_sequence, 1)[0]
        else:
            slope = 0.0

        # 揺らぎパターン
        # 連続して速い/遅いが続くか
        diffs = np.diff(st_sequence)
        sign_changes = np.sum(np.abs(np.diff(np.sign(diffs)))) / 2
        volatility = sign_changes / (len(diffs) - 1) if len(diffs) > 1 else 0.5

        # 極端なSTの頻度
        fast_rate = np.mean(st_sequence < 0.12)
        slow_rate = np.mean(st_sequence > 0.18)

        # 安定性スコア
        stability = 1.0 / (1.0 + std * 10)

        # 直近トレンドスコア（改善中か悪化中か）
        trend_score = -slope * 100  # 負の傾き（STが小さくなる）= 良化

        return {
            'st_mean': float(mean),
            'st_std': float(std),
            'st_min': float(min_st),
            'st_max': float(max_st),
            'st_range': float(max_st - min_st),
            'st_recent_mean': float(recent_mean),
            'st_recent_std': float(recent_std),
            'st_trend': float(slope),
            'st_trend_score': float(trend_score),
            'st_volatility': float(volatility),
            'st_fast_rate': float(fast_rate),
            'st_slow_rate': float(slow_rate),
            'st_stability': float(stability),
            'st_recent_vs_avg': float(recent_mean - mean),  # 直近が平均より速いか
        }

    def _default_st_statistics(self) -> Dict[str, float]:
        """デフォルトの統計値"""
        return {
            'st_mean': 0.15,
            'st_std': 0.03,
            'st_min': 0.10,
            'st_max': 0.20,
            'st_range': 0.10,
            'st_recent_mean': 0.15,
            'st_recent_std': 0.03,
            'st_trend': 0.0,
            'st_trend_score': 0.0,
            'st_volatility': 0.5,
            'st_fast_rate': 0.2,
            'st_slow_rate': 0.1,
            'st_stability': 0.5,
            'st_recent_vs_avg': 0.0,
        }

    def get_st_features(self, racer_number: str,
                         target_date: str,
                         venue_code: str = None) -> Dict[str, float]:
        """
        選手のST特徴量を取得（シーケンス→統計変換）

        Args:
            racer_number: 選手番号
            target_date: 基準日
            venue_code: 会場コード

        Returns:
            ST特徴量
        """
        sequence = self.get_st_sequence(racer_number, target_date, venue_code)
        return self.calculate_st_statistics(sequence)

    def get_st_pattern_features(self, st_sequence: np.ndarray) -> Dict[str, float]:
        """
        STシーケンスからパターン特徴量を抽出

        Args:
            st_sequence: STシーケンス

        Returns:
            パターン特徴量
        """
        if len(st_sequence) < 5:
            return {
                'pattern_improving': 0.0,
                'pattern_stable': 0.0,
                'pattern_volatile': 0.0,
                'pattern_burst': 0.0,
            }

        recent = st_sequence[-10:]
        older = st_sequence[:-10] if len(st_sequence) > 10 else st_sequence[:len(st_sequence)//2]

        # 改善パターン: 直近が過去より速い
        improving = np.mean(recent) < np.mean(older) - 0.01

        # 安定パターン: 標準偏差が小さい
        stable = np.std(st_sequence) < 0.02

        # 不安定パターン: 標準偏差が大きい
        volatile = np.std(st_sequence) > 0.04

        # バースト: 直近に極端に速いSTがある
        burst = np.min(recent) < 0.10

        return {
            'pattern_improving': 1.0 if improving else 0.0,
            'pattern_stable': 1.0 if stable else 0.0,
            'pattern_volatile': 1.0 if volatile else 0.0,
            'pattern_burst': 1.0 if burst else 0.0,
        }

    def calculate_relative_st_features(self, race_st_times: List[float]) -> Dict[str, float]:
        """
        レース内の相対ST特徴量を計算

        Args:
            race_st_times: 6艇のST時間リスト

        Returns:
            相対ST特徴量
        """
        st_array = np.array(race_st_times)
        valid_mask = st_array > 0

        if valid_mask.sum() == 0:
            return {f'relative_st_{i}': 0.0 for i in range(6)}

        valid_sts = st_array[valid_mask]
        mean_st = np.mean(valid_sts)
        std_st = np.std(valid_sts) if len(valid_sts) > 1 else 0.03

        features = {}
        for i, st in enumerate(st_array):
            if st > 0:
                # Zスコア
                z_score = (st - mean_st) / (std_st + 1e-10)
                features[f'st_zscore_{i+1}'] = float(z_score)

                # 順位（1が最速）
                rank = np.sum(valid_sts < st) + 1
                features[f'st_rank_{i+1}'] = float(rank)
            else:
                features[f'st_zscore_{i+1}'] = 0.0
                features[f'st_rank_{i+1}'] = 3.5  # 中間

        return features


def create_st_training_dataset(db_path: str,
                                start_date: str = None,
                                end_date: str = None,
                                sequence_length: int = 30) -> Tuple[np.ndarray, np.ndarray]:
    """
    ST時系列モデルの学習データセットを作成

    Args:
        db_path: DBパス
        start_date: 開始日
        end_date: 終了日
        sequence_length: シーケンス長

    Returns:
        (X: シーケンス, y: 次のST)
    """
    conn = sqlite3.connect(db_path)

    # 選手ごとのSTシーケンスを取得
    query = """
        SELECT
            e.racer_number,
            r.race_date,
            rd.st_time
        FROM race_details rd
        JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
        JOIN races r ON rd.race_id = r.id
        WHERE rd.st_time IS NOT NULL
          AND rd.st_time > 0
    """

    params = []
    if start_date:
        query += " AND r.race_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND r.race_date <= ?"
        params.append(end_date)

    query += " ORDER BY e.racer_number, r.race_date, r.race_number"

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    print(f"STデータ読み込み: {len(df):,}件")

    # 選手ごとにシーケンスを作成
    X_list = []
    y_list = []

    for racer, group in df.groupby('racer_number'):
        st_values = group['st_time'].values

        # シーケンスとターゲットを作成
        for i in range(len(st_values) - sequence_length):
            X_list.append(st_values[i:i+sequence_length])
            y_list.append(st_values[i+sequence_length])

    X = np.array(X_list)
    y = np.array(y_list)

    print(f"学習データ作成: X={X.shape}, y={y.shape}")

    return X, y
