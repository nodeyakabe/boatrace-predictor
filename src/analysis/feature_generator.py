"""
特徴量生成モジュール

Phase 3で使用する特徴量を生成
"""

import pandas as pd
import numpy as np
from datetime import datetime


class FeatureGenerator:
    """
    特徴量生成クラス

    データベースから取得した生データを機械学習用の特徴量に変換
    """

    def __init__(self):
        """初期化"""
        self.feature_columns = []

    def generate_basic_features(self, df):
        """
        基本特徴量を生成

        Phase 3.1で使用する最優先の特徴量
        - 選手基本情報
        - モーター・ボート情報
        - レース条件

        Args:
            df: 生データのDataFrame

        Returns:
            DataFrame: 基本特徴量が追加されたDataFrame
        """
        result_df = df.copy()

        # 1. 選手関連特徴量（既に存在する列をそのまま使用）
        # win_rate, second_rate, third_rate
        # local_win_rate, local_second_rate, local_third_rate
        # avg_st, f_count, l_count

        # 2. モーター・ボート関連特徴量
        # motor_second_rate, motor_third_rate
        # boat_second_rate, boat_third_rate

        # 3. レース条件関連特徴量
        # pit_number (1-6)
        # venue_code

        # 4. 枠番優位性スコア（統計的に計算）
        result_df['pit_advantage'] = self._calculate_pit_advantage(result_df['pit_number'])

        # 5. 級別スコア（A1=4, A2=3, B1=2, B2=1）
        result_df['class_score'] = result_df['racer_rank'].map({
            'A1': 4,
            'A2': 3,
            'B1': 2,
            'B2': 1
        }).fillna(0)

        return result_df

    def generate_derived_features(self, df):
        """
        派生特徴量を生成

        Phase 3.2で使用する中優先の特徴量
        - 選手の経験値スコア
        - 機材総合性能スコア
        - レース内相対評価

        Args:
            df: 基本特徴量が含まれるDataFrame

        Returns:
            DataFrame: 派生特徴量が追加されたDataFrame
        """
        result_df = df.copy()

        # 1. 経験値スコア（勝率 × 級別スコア）
        result_df['experience_score'] = result_df['win_rate'] * result_df['class_score']

        # 2. モーター性能スコア（2連対率 + 3連対率）
        result_df['motor_performance'] = (
            result_df['motor_second_rate'].fillna(0) +
            result_df['motor_third_rate'].fillna(0)
        )

        # 3. ボート性能スコア
        result_df['boat_performance'] = (
            result_df['boat_second_rate'].fillna(0) +
            result_df['boat_third_rate'].fillna(0)
        )

        # 4. 機材総合優位性
        result_df['equipment_advantage'] = (
            result_df['motor_performance'] + result_df['boat_performance']
        )

        # 5. レース内での勝率順位（同じレース内での相対評価）
        if 'race_id' in result_df.columns:
            result_df['rank_in_race_by_win_rate'] = result_df.groupby('race_id')['win_rate'].rank(
                ascending=False, method='dense'
            )

            result_df['rank_in_race_by_avg_st'] = result_df.groupby('race_id')['avg_st'].rank(
                ascending=True, method='dense'  # STは小さい方が良い
            )

            result_df['rank_in_race_by_class'] = result_df.groupby('race_id')['class_score'].rank(
                ascending=False, method='dense'
            )

        return result_df

    def generate_advanced_features(self, df, historical_results=None):
        """
        高度な特徴量を生成

        Phase 3.3で使用する低優先の特徴量
        - 直近成績（過去N戦の平均着順）
        - 当地相性
        - 天候・水面条件

        Args:
            df: 派生特徴量が含まれるDataFrame
            historical_results: 過去の成績データ（オプション）

        Returns:
            DataFrame: 高度な特徴量が追加されたDataFrame
        """
        result_df = df.copy()

        # TODO: Phase 3.3で実装
        # 1. 直近成績（過去10レースの平均着順）
        # 2. 当地相性（venue_codeごとの成績）
        # 3. 天候・水面条件（別途取得が必要）

        return result_df

    def _calculate_pit_advantage(self, pit_numbers):
        """
        枠番優位性を計算

        統計的に1号艇が有利という前提でスコアを付与

        Args:
            pit_numbers: 枠番のSeries

        Returns:
            優位性スコアのSeries
        """
        # 1号艇を最も有利、6号艇を最も不利とする
        advantage_map = {
            1: 6,
            2: 5,
            3: 4,
            4: 3,
            5: 2,
            6: 1
        }

        return pit_numbers.map(advantage_map).fillna(0)

    def encode_categorical_features(self, df):
        """
        カテゴリカル変数をエンコーディング

        Args:
            df: エンコード前のDataFrame

        Returns:
            DataFrame: エンコード後のDataFrame
        """
        result_df = df.copy()

        # 1. One-Hot Encoding
        if 'racer_rank' in result_df.columns:
            rank_dummies = pd.get_dummies(result_df['racer_rank'], prefix='rank')
            result_df = pd.concat([result_df, rank_dummies], axis=1)

        if 'venue_code' in result_df.columns:
            venue_dummies = pd.get_dummies(result_df['venue_code'], prefix='venue')
            result_df = pd.concat([result_df, venue_dummies], axis=1)

        if 'pit_number' in result_df.columns:
            pit_dummies = pd.get_dummies(result_df['pit_number'], prefix='pit')
            result_df = pd.concat([result_df, pit_dummies], axis=1)

        # 2. Label Encoding（選択的に使用）
        # racer_home など、カーディナリティが高い場合

        return result_df

    def get_feature_list(self, phase='3.1'):
        """
        使用する特徴量のリストを取得

        Args:
            phase: フェーズ ('3.1', '3.2', '3.3')

        Returns:
            list: 特徴量名のリスト
        """
        if phase == '3.1':
            # Phase 3.1: 基本特徴量のみ
            return [
                'win_rate', 'second_rate', 'third_rate',
                'local_win_rate', 'local_second_rate', 'local_third_rate',
                'avg_st', 'f_count', 'l_count',
                'motor_second_rate', 'motor_third_rate',
                'boat_second_rate', 'boat_third_rate',
                'pit_number', 'pit_advantage', 'class_score'
            ]

        elif phase == '3.2':
            # Phase 3.2: 基本 + 派生特徴量
            base_features = self.get_feature_list('3.1')
            derived_features = [
                'experience_score', 'motor_performance', 'boat_performance',
                'equipment_advantage', 'rank_in_race_by_win_rate',
                'rank_in_race_by_avg_st', 'rank_in_race_by_class'
            ]
            return base_features + derived_features

        elif phase == '3.3':
            # Phase 3.3: すべて
            base_features = self.get_feature_list('3.2')
            advanced_features = [
                # TODO: Phase 3.3で追加
            ]
            return base_features + advanced_features

        else:
            raise ValueError(f"未知のフェーズ: {phase}")


def main():
    """
    特徴量生成のテスト実行
    """
    print("=" * 80)
    print("特徴量生成 テスト")
    print("=" * 80)

    # ダミーデータで動作確認
    np.random.seed(42)

    # 2レース x 6艇 = 12行のダミーデータ
    n_samples = 12
    data = {
        'race_id': [1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2],
        'pit_number': [1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6],
        'racer_rank': ['A1', 'A2', 'B1', 'A1', 'B2', 'A2', 'A1', 'A1', 'B1', 'A2', 'B1', 'B2'],
        'win_rate': np.random.uniform(5.0, 8.0, n_samples),
        'second_rate': np.random.uniform(30, 70, n_samples),
        'third_rate': np.random.uniform(40, 80, n_samples),
        'local_win_rate': np.random.uniform(5.0, 8.0, n_samples),
        'local_second_rate': np.random.uniform(30, 70, n_samples),
        'local_third_rate': np.random.uniform(40, 80, n_samples),
        'avg_st': np.random.uniform(0.10, 0.20, n_samples),
        'f_count': np.random.randint(0, 3, n_samples),
        'l_count': np.random.randint(0, 3, n_samples),
        'motor_second_rate': np.random.uniform(20, 60, n_samples),
        'motor_third_rate': np.random.uniform(30, 70, n_samples),
        'boat_second_rate': np.random.uniform(20, 60, n_samples),
        'boat_third_rate': np.random.uniform(30, 70, n_samples),
        'venue_code': ['01'] * 6 + ['02'] * 6
    }

    df = pd.DataFrame(data)

    # 特徴量生成
    generator = FeatureGenerator()

    print("\n1. 基本特徴量生成")
    df_basic = generator.generate_basic_features(df)
    print(f"特徴量数: {len(df_basic.columns)}")
    print(f"新規追加: pit_advantage, class_score")

    print("\n2. 派生特徴量生成")
    df_derived = generator.generate_derived_features(df_basic)
    print(f"特徴量数: {len(df_derived.columns)}")
    print(f"新規追加: experience_score, motor_performance, boat_performance, equipment_advantage")

    print("\n3. カテゴリカル変数エンコーディング")
    df_encoded = generator.encode_categorical_features(df_derived)
    print(f"特徴量数: {len(df_encoded.columns)}")

    print("\n4. Phase 3.1 特徴量リスト")
    feature_list = generator.get_feature_list('3.1')
    print(f"特徴量数: {len(feature_list)}")
    for feat in feature_list:
        print(f"  - {feat}")

    print("\n5. サンプルデータ（1行目）")
    print(df_derived.iloc[0][['pit_advantage', 'class_score', 'experience_score', 'equipment_advantage']])

    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
