"""
時系列特徴量生成
Phase 2: 選手の調子波とモーター性能の経時変化
"""
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime, timedelta


class TimeseriesFeatureGenerator:
    """時系列特徴量生成クラス"""

    def __init__(self, db_connection_or_path):
        """
        初期化

        Args:
            db_connection_or_path: DB接続またはDBパス
                - sqlite3.Connection: 既存の接続（後方互換）
                - str: DBファイルパス（スレッドセーフ）
        """
        if isinstance(db_connection_or_path, str):
            self.db_path = db_connection_or_path
            self.conn = None  # 接続は都度作成
        else:
            # 後方互換: 既存の接続を使用
            self.db_path = None
            self.conn = db_connection_or_path

    def _get_connection(self):
        """スレッドセーフなDB接続を取得"""
        if self.db_path:
            return sqlite3.connect(self.db_path)
        return self.conn

    def _close_connection(self, conn):
        """接続を閉じる（db_pathモードの場合のみ）"""
        if self.db_path and conn:
            conn.close()

    def calculate_racer_momentum(self, racer_number, target_date, window_days=30):
        """
        選手の調子波（モメンタム）を計算

        Args:
            racer_number: 選手番号
            target_date: 基準日
            window_days: 計算期間（日数）

        Returns:
            dict: モメンタム特徴量
        """
        start_date = (datetime.strptime(target_date, '%Y-%m-%d') -
                     timedelta(days=window_days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                r.race_date,
                res.rank,
                e.pit_number
            FROM results res
            JOIN races r ON res.race_id = r.id
            JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND r.race_date BETWEEN ? AND ?
            ORDER BY r.race_date ASC
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (racer_number, start_date, target_date))
        results = cursor.fetchall()
        self._close_connection(conn)

        if len(results) < 3:
            return {
                'momentum_score': 0.0,
                'recent_trend': 0.0,
                'consistency': 0.0,
                'peak_performance': 0.0
            }

        # 日付とランクの配列
        dates = [datetime.strptime(r[0], '%Y-%m-%d') for r in results]
        ranks = np.array([r[1] for r in results])

        # モメンタムスコア: 最近の成績の重み付け平均
        time_weights = np.exp(np.linspace(-1, 0, len(ranks)))
        momentum = np.average(4 - ranks, weights=time_weights)  # 1位=3点、2位=2点、3位=1点

        # トレンド: 線形回帰の傾き
        x = np.arange(len(ranks))
        trend = -np.polyfit(x, ranks, 1)[0]  # 負号: ランクが下がる=良化

        # 一貫性: ランクの標準偏差の逆数
        consistency = 1.0 / (np.std(ranks) + 1.0)

        # ピークパフォーマンス: 最近N走での最高順位
        peak = 4 - np.min(ranks[-5:]) if len(ranks) >= 5 else 4 - np.min(ranks)

        return {
            'momentum_score': float(momentum),
            'recent_trend': float(trend),
            'consistency': float(consistency),
            'peak_performance': float(peak)
        }

    def calculate_motor_degradation(self, motor_number, venue_code, target_date):
        """
        モーター性能の経時変化を計算

        Args:
            motor_number: モーター番号
            venue_code: 会場コード
            target_date: 基準日

        Returns:
            dict: モーター劣化特徴量
        """
        # モーターの使用開始日を推定（通常は年初）
        target_year = int(target_date[:4])
        motor_start_date = f"{target_year}-01-01"

        query = """
            SELECT
                r.race_date,
                res.rank
            FROM results res
            JOIN races r ON res.race_id = r.id
            JOIN entries e ON res.race_id = e.race_id AND res.pit_number = res.pit_number
            WHERE e.motor_number = ?
              AND r.venue_code = ?
              AND r.race_date BETWEEN ? AND ?
            ORDER BY r.race_date ASC
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (motor_number, venue_code, motor_start_date, target_date))
        results = cursor.fetchall()
        self._close_connection(conn)

        if len(results) < 5:
            return {
                'motor_age_days': 0,
                'motor_performance_trend': 0.0,
                'motor_stability': 1.0,
                'motor_recent_performance': 0.5
            }

        # モーター年齢（日数）
        motor_age = (datetime.strptime(target_date, '%Y-%m-%d') -
                    datetime.strptime(motor_start_date, '%Y-%m-%d')).days

        # 性能トレンド
        ranks = np.array([r[1] for r in results])
        x = np.arange(len(ranks))
        trend = -np.polyfit(x, ranks, 1)[0]  # 負号: ランク改善=正のトレンド

        # 安定性
        stability = 1.0 / (np.std(ranks) + 1.0)

        # 直近性能
        recent_performance = np.mean(4 - ranks[-10:]) / 3.0  # 0-1に正規化

        return {
            'motor_age_days': motor_age,
            'motor_performance_trend': float(trend),
            'motor_stability': float(stability),
            'motor_recent_performance': float(recent_performance)
        }

    def calculate_venue_condition_change(self, venue_code, target_date, lookback_days=7):
        """
        会場コンディションの変化を計算

        Args:
            venue_code: 会場コード
            target_date: 基準日
            lookback_days: 遡る日数

        Returns:
            dict: 会場コンディション変化
        """
        start_date = (datetime.strptime(target_date, '%Y-%m-%d') -
                     timedelta(days=lookback_days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                race_date,
                wind_speed,
                wave_height,
                water_temperature
            FROM weather
            WHERE venue_code = ?
              AND race_date BETWEEN ? AND ?
            ORDER BY race_date ASC
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (venue_code, start_date, target_date))
        results = cursor.fetchall()
        self._close_connection(conn)

        if len(results) < 2:
            return {
                'wind_volatility': 0.0,
                'wave_volatility': 0.0,
                'temp_trend': 0.0,
                'condition_stability': 1.0
            }

        # データを配列に変換
        wind_speeds = np.array([r[1] for r in results if r[1] is not None])
        wave_heights = np.array([r[2] for r in results if r[2] is not None])
        water_temps = np.array([r[3] for r in results if r[3] is not None])

        # ボラティリティ（変動性）
        wind_vol = np.std(wind_speeds) if len(wind_speeds) > 0 else 0.0
        wave_vol = np.std(wave_heights) if len(wave_heights) > 0 else 0.0

        # 水温トレンド
        if len(water_temps) > 1:
            x = np.arange(len(water_temps))
            temp_trend = np.polyfit(x, water_temps, 1)[0]
        else:
            temp_trend = 0.0

        # コンディション安定性（総合）
        stability = 1.0 / (1.0 + wind_vol + wave_vol)

        return {
            'wind_volatility': float(wind_vol),
            'wave_volatility': float(wave_vol),
            'temp_trend': float(temp_trend),
            'condition_stability': float(stability)
        }

    def calculate_seasonal_patterns(self, target_date):
        """
        季節パターン特徴量

        Args:
            target_date: 基準日

        Returns:
            dict: 季節特徴量
        """
        date_obj = datetime.strptime(target_date, '%Y-%m-%d')

        # 月（1-12）
        month = date_obj.month

        # 季節（1-4）
        season = (month - 1) // 3 + 1  # 1=春, 2=夏, 3=秋, 4=冬

        # 月の進行度（0-1）
        days_in_month = (datetime(date_obj.year, date_obj.month + 1, 1) -
                        timedelta(days=1)).day if date_obj.month < 12 else 31
        month_progress = date_obj.day / days_in_month

        # sin/cosエンコーディング（周期性を捉える）
        month_sin = np.sin(2 * np.pi * month / 12)
        month_cos = np.cos(2 * np.pi * month / 12)

        return {
            'month': month,
            'season': season,
            'month_progress': float(month_progress),
            'month_sin': float(month_sin),
            'month_cos': float(month_cos),
            'is_summer': 1 if season == 2 else 0,
            'is_winter': 1 if season == 4 else 0
        }

    def generate_all_timeseries_features(self, racer_number, motor_number,
                                        venue_code, target_date):
        """
        すべての時系列特徴量を生成

        Args:
            racer_number: 選手番号
            motor_number: モーター番号
            venue_code: 会場コード
            target_date: 基準日

        Returns:
            dict: 時系列特徴量
        """
        features = {}

        # 選手モメンタム
        momentum = self.calculate_racer_momentum(racer_number, target_date)
        features.update(momentum)

        # モーター劣化
        motor = self.calculate_motor_degradation(motor_number, venue_code, target_date)
        features.update(motor)

        # 会場コンディション変化
        condition = self.calculate_venue_condition_change(venue_code, target_date)
        features.update(condition)

        # 季節パターン
        seasonal = self.calculate_seasonal_patterns(target_date)
        features.update(seasonal)

        return features
