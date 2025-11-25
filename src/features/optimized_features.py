"""
最適化された特徴量エンジニアリング
Phase 1: 不要特徴量削除 + 新規特徴量追加
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class OptimizedFeatureGenerator:
    """最適化された特徴量生成クラス"""

    # 削除する不要特徴量
    EXCLUDED_FEATURES = [
        'temperature',           # 気温（影響極小）
        'water_temperature',     # 水温（季節性で代替可能）
        'racer_weight',          # 選手体重（他特徴で代替）
        'motor_number',          # モーター番号（2連率で十分）
        'boat_number',           # ボート番号（2連率で十分）
    ]

    def __init__(self, db_connection):
        self.conn = db_connection

    def calculate_recent_form(self, racer_number, target_date, n_races=5):
        """
        直近N走の成績を計算（新規特徴量）

        Args:
            racer_number: 選手番号
            target_date: 基準日
            n_races: 直近何走を見るか

        Returns:
            dict: recent_win_rate, recent_place_rate等
        """
        query = """
            SELECT
                res.rank,
                r.race_date
            FROM results res
            JOIN races r ON res.race_id = r.id
            JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND r.race_date < ?
            ORDER BY r.race_date DESC
            LIMIT ?
        """

        cursor = self.conn.cursor()
        cursor.execute(query, (racer_number, target_date, n_races))
        results = cursor.fetchall()

        if len(results) < 2:
            return {
                'recent_win_rate': 0.0,
                'recent_place_rate': 0.0,
                'recent_avg_rank': 3.5,
                'recent_form_score': 0.0
            }

        ranks = [r[0] for r in results]
        wins = sum(1 for r in ranks if r == 1)
        places = sum(1 for r in ranks if r <= 3)

        # フォームスコア: 最近の成績ほど重み付け
        weights = np.linspace(1.0, 0.5, len(ranks))
        form_score = sum(w * (4 - r) for w, r in zip(weights, ranks)) / sum(weights)

        return {
            'recent_win_rate': wins / len(results),
            'recent_place_rate': places / len(results),
            'recent_avg_rank': np.mean(ranks),
            'recent_form_score': form_score
        }

    def calculate_venue_experience(self, racer_number, venue_code):
        """
        会場別出走回数（新規特徴量）

        Args:
            racer_number: 選手番号
            venue_code: 会場コード

        Returns:
            int: 出走回数
        """
        query = """
            SELECT COUNT(*) as count
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE e.racer_number = ?
              AND r.venue_code = ?
        """

        cursor = self.conn.cursor()
        cursor.execute(query, (racer_number, venue_code))
        result = cursor.fetchone()

        return result[0] if result else 0

    def calculate_head_to_head(self, racer1, racer2):
        """
        対戦成績（新規特徴量）

        Args:
            racer1: 選手1の番号
            racer2: 選手2の番号

        Returns:
            dict: racer1がracer2に勝った回数等
        """
        query = """
            SELECT
                e1.pit_number as pit1,
                e2.pit_number as pit2,
                res1.rank as rank1,
                res2.rank as rank2
            FROM entries e1
            JOIN entries e2 ON e1.race_id = e2.race_id
            JOIN results res1 ON e1.race_id = res1.race_id AND e1.pit_number = res1.pit_number
            JOIN results res2 ON e2.race_id = res2.race_id AND e2.pit_number = res2.pit_number
            WHERE e1.racer_number = ?
              AND e2.racer_number = ?
              AND e1.racer_number != e2.racer_number
        """

        cursor = self.conn.cursor()
        cursor.execute(query, (racer1, racer2))
        results = cursor.fetchall()

        if len(results) == 0:
            return {
                'head_to_head_wins': 0,
                'head_to_head_races': 0,
                'head_to_head_win_rate': 0.0
            }

        wins = sum(1 for r in results if r[2] < r[3])  # rank1 < rank2
        total = len(results)

        return {
            'head_to_head_wins': wins,
            'head_to_head_races': total,
            'head_to_head_win_rate': wins / total if total > 0 else 0.0
        }

    def calculate_weather_change(self, venue_code, race_date):
        """
        気象変化率（新規特徴量）

        Args:
            venue_code: 会場コード
            race_date: レース日付

        Returns:
            dict: wind_change, wave_change等
        """
        query = """
            SELECT
                wind_speed,
                wave_height
            FROM weather
            WHERE venue_code = ?
              AND race_date BETWEEN ? AND ?
            ORDER BY race_date DESC
            LIMIT 2
        """

        # 前日との比較
        yesterday = (datetime.strptime(race_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

        cursor = self.conn.cursor()
        cursor.execute(query, (venue_code, yesterday, race_date))
        results = cursor.fetchall()

        if len(results) < 2:
            return {
                'wind_change': 0.0,
                'wave_change': 0.0,
                'weather_stability': 1.0
            }

        today = results[0]
        yesterday = results[1]

        wind_change = (today[0] - yesterday[0]) if today[0] and yesterday[0] else 0
        wave_change = (today[1] - yesterday[1]) if today[1] and yesterday[1] else 0

        # 安定度スコア（変化が小さいほど高い）
        stability = 1.0 / (1.0 + abs(wind_change) + abs(wave_change))

        return {
            'wind_change': wind_change,
            'wave_change': wave_change,
            'weather_stability': stability
        }

    def calculate_race_importance(self, race_grade):
        """
        レース重要度スコア（新規特徴量）

        Args:
            race_grade: レースグレード

        Returns:
            float: 重要度スコア（0-1）
        """
        importance_map = {
            'SG': 1.0,      # 最高峰
            'G1': 0.8,      # プレミアム
            'G2': 0.6,      # 一般A
            'G3': 0.4,      # 一般B
            '一般': 0.2,    # 一般戦
        }

        return importance_map.get(race_grade, 0.2)

    def generate_optimized_features(self, race_data, include_new_features=True):
        """
        最適化された特徴量セットを生成

        Args:
            race_data: レースデータ（dict）
            include_new_features: 新規特徴量を含めるか

        Returns:
            dict: 最適化された特徴量
        """
        features = {}

        # 基本特徴量（重要度：高）
        features['actual_course'] = race_data.get('actual_course', 0)
        features['pit_number'] = race_data.get('pit_number', 0)
        features['win_rate'] = race_data.get('win_rate', 0.0)
        features['exhibition_time'] = race_data.get('exhibition_time', 0.0)
        features['st_time'] = race_data.get('st_time', 0.0)

        # 会場・グレード関連（重要度：高）
        features['venue_pit1_win_rate'] = race_data.get('venue_pit1_win_rate', 0.0)
        features['grade_win_rate'] = race_data.get('grade_win_rate', 0.0)
        features['venue_inner_bias'] = race_data.get('venue_inner_bias', 0.0)
        features['pit1_venue_inner'] = race_data.get('pit1_venue_inner', 0.0)
        features['grade_rank'] = race_data.get('grade_rank', 0)

        # 選手関連（重要度：中）
        features['racer_age'] = race_data.get('racer_age', 0)
        features['avg_st'] = race_data.get('avg_st', 0.0)
        features['f_count'] = race_data.get('f_count', 0)
        features['l_count'] = race_data.get('l_count', 0)
        features['second_rate'] = race_data.get('second_rate', 0.0)

        # モーター・ボート関連（重要度：中）
        features['motor_second_rate'] = race_data.get('motor_second_rate', 0.0)
        features['boat_second_rate'] = race_data.get('boat_second_rate', 0.0)
        features['tilt_angle'] = race_data.get('tilt_angle', 0.0)

        # 新規特徴量（Phase 1）
        if include_new_features:
            racer_number = race_data.get('racer_number')
            venue_code = race_data.get('venue_code')
            race_date = race_data.get('race_date')
            race_grade = race_data.get('race_grade', '一般')

            if racer_number and race_date:
                # 直近フォーム
                recent_form = self.calculate_recent_form(racer_number, race_date)
                features.update(recent_form)

            if racer_number and venue_code:
                # 会場経験
                features['venue_experience'] = self.calculate_venue_experience(racer_number, venue_code)

            if venue_code and race_date:
                # 気象変化
                weather = self.calculate_weather_change(venue_code, race_date)
                features.update(weather)

            # レース重要度
            features['race_importance'] = self.calculate_race_importance(race_grade)

        return features

    def filter_features(self, features_df):
        """
        不要特徴量を除外

        Args:
            features_df: 特徴量DataFrame

        Returns:
            DataFrame: フィルタリング後の特徴量
        """
        # 不要特徴量を除外
        columns_to_keep = [col for col in features_df.columns
                          if col not in self.EXCLUDED_FEATURES]

        return features_df[columns_to_keep]
