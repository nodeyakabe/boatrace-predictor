"""
交互作用特徴量生成モジュール
Phase 1.3: 場×気象×潮×コースの複雑な関係性をモデル化
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from itertools import combinations


class InteractionFeatureGenerator:
    """交互作用特徴量を生成するクラス"""

    def __init__(self):
        self.interaction_pairs = [
            # 環境×コース
            ('wind_speed', 'pit_number'),
            ('wind_direction', 'pit_number'),
            ('wave_height', 'pit_number'),
            ('tide_level', 'pit_number'),

            # 環境×機材
            ('wind_speed', 'motor_2ren_rate'),
            ('wave_height', 'motor_2ren_rate'),
            ('tide_level', 'motor_2ren_rate'),

            # 環境×選手特性
            ('wind_speed', 'racer_weight'),
            ('wave_height', 'racer_weight'),
            ('wind_speed', 'exhibition_time'),

            # 機材×選手
            ('motor_2ren_rate', 'win_rate'),
            ('exhibition_time', 'win_rate'),
            ('st_time', 'win_rate'),

            # コース×選手特性
            ('pit_number', 'win_rate'),
            ('pit_number', 'st_time'),
            ('pit_number', 'exhibition_time'),
        ]

    def generate_interaction_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """基本的な交互作用特徴量を生成"""
        result_df = df.copy()

        for col1, col2 in self.interaction_pairs:
            if col1 in df.columns and col2 in df.columns:
                # 乗算交互作用
                feature_name = f'{col1}_x_{col2}'
                result_df[feature_name] = df[col1] * df[col2]

                # 比率交互作用（ゼロ除算を防ぐ）
                if col2 != 'pit_number':  # pit_numberは比率に使わない
                    ratio_name = f'{col1}_div_{col2}'
                    denominator = df[col2].replace(0, np.nan)
                    result_df[ratio_name] = df[col1] / denominator
                    result_df[ratio_name] = result_df[ratio_name].fillna(0)

        return result_df

    def generate_polynomial_features(self, df: pd.DataFrame, columns: List[str], degree: int = 2) -> pd.DataFrame:
        """多項式特徴量を生成"""
        result_df = df.copy()

        for col in columns:
            if col in df.columns:
                for d in range(2, degree + 1):
                    feature_name = f'{col}_pow{d}'
                    result_df[feature_name] = df[col] ** d

        return result_df

    def generate_relative_features(self, race_df: pd.DataFrame) -> pd.DataFrame:
        """レース内相対特徴量を生成（レースごとに計算）"""
        result_df = race_df.copy()

        # レース内での相対位置を計算する特徴量
        relative_cols = [
            'win_rate', 'motor_2ren_rate', 'exhibition_time',
            'st_time', 'racer_weight'
        ]

        for col in relative_cols:
            if col not in race_df.columns:
                continue

            # レース内平均との差
            race_mean = race_df[col].mean()
            result_df[f'{col}_diff_from_mean'] = race_df[col] - race_mean

            # レース内順位
            result_df[f'{col}_rank_in_race'] = race_df[col].rank(ascending=False)

            # レース内最大値との差
            race_max = race_df[col].max()
            result_df[f'{col}_diff_from_max'] = race_df[col] - race_max

            # レース内Zスコア
            race_std = race_df[col].std()
            if race_std > 0:
                result_df[f'{col}_zscore'] = (race_df[col] - race_mean) / race_std
            else:
                result_df[f'{col}_zscore'] = 0

        return result_df

    def generate_weather_course_interactions(self, df: pd.DataFrame) -> pd.DataFrame:
        """気象×コースの詳細交互作用"""
        result_df = df.copy()

        # 風向×コースの影響
        if 'wind_direction' in df.columns and 'pit_number' in df.columns:
            # 風向をラジアンに変換（0-7 → 0-2π）
            wind_rad = df['wind_direction'] * np.pi / 4

            # 向かい風・追い風の影響
            # コース1-3は向かい風が不利、4-6は追い風が不利
            for course in range(1, 7):
                if course <= 3:
                    # 内コースは向かい風（北風）で不利
                    penalty = np.cos(wind_rad)  # 北風(0)で最大ペナルティ
                else:
                    # 外コースは追い風で不利
                    penalty = -np.cos(wind_rad)  # 南風で最大ペナルティ

                mask = df['pit_number'] == course
                if mask.any():
                    result_df.loc[mask, f'wind_course_{course}_effect'] = penalty[mask]

        # 波高×体重の影響
        if 'wave_height' in df.columns and 'racer_weight' in df.columns:
            # 波が高いと軽量選手が有利
            result_df['wave_weight_advantage'] = (
                df['wave_height'] * (1 / (df['racer_weight'] + 1))
            )

        # 潮位×モーター性能
        if 'tide_level' in df.columns and 'motor_2ren_rate' in df.columns:
            # 潮位が高いとモーター性能が重要
            result_df['tide_motor_synergy'] = (
                df['tide_level'] / 100 * df['motor_2ren_rate']
            )

        return result_df

    def generate_temporal_interactions(self, df: pd.DataFrame) -> pd.DataFrame:
        """時間的交互作用（レース番号、時間帯など）"""
        result_df = df.copy()

        if 'race_number' in df.columns:
            # レース後半は荒れやすい（1号艇有利度低下）
            late_race = (df['race_number'] > 8).astype(int)

            if 'pit_number' in df.columns:
                # 1号艇の後半戦不利度
                result_df['late_race_course_effect'] = (
                    late_race * (7 - df['pit_number']) / 6
                )

            if 'win_rate' in df.columns:
                # 後半は実力差が出やすい
                result_df['late_race_skill_importance'] = (
                    late_race * df['win_rate']
                )

        return result_df

    def generate_all_interactions(self, df: pd.DataFrame, race_level: bool = False) -> pd.DataFrame:
        """全ての交互作用特徴量を生成"""
        result_df = df.copy()

        # 1. 基本交互作用
        result_df = self.generate_interaction_features(result_df)

        # 2. 多項式特徴量
        poly_cols = ['win_rate', 'motor_2ren_rate', 'exhibition_time']
        poly_cols = [c for c in poly_cols if c in df.columns]
        result_df = self.generate_polynomial_features(result_df, poly_cols, degree=2)

        # 3. 気象×コース交互作用
        result_df = self.generate_weather_course_interactions(result_df)

        # 4. 時間的交互作用
        result_df = self.generate_temporal_interactions(result_df)

        # 5. レース内相対特徴量（レースごとに処理する場合）
        if race_level and len(df) == 6:  # 1レース6艇
            result_df = self.generate_relative_features(result_df)

        return result_df


class VenueSpecificFeatureGenerator:
    """会場固有の特徴量を生成"""

    # 会場特性（事前定義）
    VENUE_CHARACTERISTICS = {
        '01': {'water_type': 'fresh', 'course_width': 'narrow', 'in_advantage': 0.55},
        '02': {'water_type': 'fresh', 'course_width': 'narrow', 'in_advantage': 0.53},
        '03': {'water_type': 'fresh', 'course_width': 'narrow', 'in_advantage': 0.48},  # 江戸川は荒れやすい
        '04': {'water_type': 'sea', 'course_width': 'wide', 'in_advantage': 0.52},
        '05': {'water_type': 'fresh', 'course_width': 'wide', 'in_advantage': 0.56},
        '06': {'water_type': 'brackish', 'course_width': 'wide', 'in_advantage': 0.54},
        '07': {'water_type': 'brackish', 'course_width': 'narrow', 'in_advantage': 0.57},
        '08': {'water_type': 'sea', 'course_width': 'wide', 'in_advantage': 0.55},
        '09': {'water_type': 'fresh', 'course_width': 'narrow', 'in_advantage': 0.54},
        '10': {'water_type': 'fresh', 'course_width': 'narrow', 'in_advantage': 0.53},
        '11': {'water_type': 'fresh', 'course_width': 'narrow', 'in_advantage': 0.55},
        '12': {'water_type': 'sea', 'course_width': 'narrow', 'in_advantage': 0.58},
        '13': {'water_type': 'sea', 'course_width': 'narrow', 'in_advantage': 0.54},
        '14': {'water_type': 'fresh', 'course_width': 'narrow', 'in_advantage': 0.55},
        '15': {'water_type': 'sea', 'course_width': 'narrow', 'in_advantage': 0.56},
        '16': {'water_type': 'fresh', 'course_width': 'narrow', 'in_advantage': 0.54},
        '17': {'water_type': 'sea', 'course_width': 'narrow', 'in_advantage': 0.55},
        '18': {'water_type': 'sea', 'course_width': 'narrow', 'in_advantage': 0.57},
        '19': {'water_type': 'sea', 'course_width': 'narrow', 'in_advantage': 0.56},
        '20': {'water_type': 'sea', 'course_width': 'narrow', 'in_advantage': 0.54},
        '21': {'water_type': 'sea', 'course_width': 'narrow', 'in_advantage': 0.55},
        '22': {'water_type': 'sea', 'course_width': 'narrow', 'in_advantage': 0.56},
        '23': {'water_type': 'sea', 'course_width': 'narrow', 'in_advantage': 0.55},
        '24': {'water_type': 'sea', 'course_width': 'narrow', 'in_advantage': 0.60},  # 大村はイン強い
    }

    def generate_venue_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """会場固有の特徴量を生成"""
        result_df = df.copy()

        if 'venue_code' not in df.columns:
            return result_df

        # 水質特性
        water_type_map = {}
        course_width_map = {}
        in_advantage_map = {}

        for venue_code, chars in self.VENUE_CHARACTERISTICS.items():
            water_type_map[venue_code] = {'fresh': 0, 'brackish': 1, 'sea': 2}.get(chars['water_type'], 0)
            course_width_map[venue_code] = {'narrow': 0, 'wide': 1}.get(chars['course_width'], 0)
            in_advantage_map[venue_code] = chars['in_advantage']

        result_df['venue_water_type'] = df['venue_code'].map(water_type_map).fillna(0)
        result_df['venue_course_width'] = df['venue_code'].map(course_width_map).fillna(0)
        result_df['venue_in_advantage'] = df['venue_code'].map(in_advantage_map).fillna(0.55)

        # 会場×コースの交互作用
        if 'pit_number' in df.columns:
            # イン有利度×枠番
            result_df['venue_pit_advantage'] = (
                result_df['venue_in_advantage'] *
                (7 - df['pit_number']) / 6  # 1コースが最大
            )

            # 海水会場×外枠は潮の影響大
            is_sea = (result_df['venue_water_type'] == 2).astype(int)
            is_outer_course = (df['pit_number'] >= 4).astype(int)
            result_df['sea_outer_course_effect'] = is_sea * is_outer_course

        return result_df


def create_feature_pipeline(df: pd.DataFrame, venue_code: str = None) -> pd.DataFrame:
    """全ての特徴量生成を統合したパイプライン"""
    # 1. 交互作用特徴量
    interaction_gen = InteractionFeatureGenerator()
    result_df = interaction_gen.generate_all_interactions(df, race_level=len(df) == 6)

    # 2. 会場固有特徴量
    venue_gen = VenueSpecificFeatureGenerator()
    result_df = venue_gen.generate_venue_features(result_df)

    # 3. 欠損値処理
    result_df = result_df.fillna(0)

    # 4. 無限大の処理
    result_df = result_df.replace([np.inf, -np.inf], 0)

    return result_df
