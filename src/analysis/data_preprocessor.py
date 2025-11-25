"""
データ前処理パイプライン

データベースから機械学習用データセットへの変換を一元管理
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.model_selection import train_test_split
import sqlite3

from src.analysis.feature_generator import FeatureGenerator


class DataPreprocessor:
    """
    データ前処理パイプライン

    1. データベースからデータ読み込み
    2. 欠損値処理
    3. 特徴量生成
    4. エンコーディング
    5. 正規化
    6. 訓練/テストデータ分割
    """

    def __init__(self, db_path='data/boatrace.db'):
        """
        初期化

        Args:
            db_path: データベースのパス
        """
        self.db_path = db_path
        self.feature_generator = FeatureGenerator()
        self.scaler = StandardScaler()
        self.age_scaler = MinMaxScaler()
        self.weight_scaler = MinMaxScaler()

    def load_data(self, start_date=None, end_date=None, venue_codes=None):
        """
        データベースからデータを読み込み

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)
            venue_codes: 競艇場コードのリスト

        Returns:
            DataFrame: 読み込んだデータ
        """
        conn = sqlite3.connect(self.db_path)

        # SQLクエリを構築
        query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            r.race_time,
            e.pit_number,
            e.racer_number,
            e.racer_name,
            e.racer_rank,
            e.racer_home,
            e.racer_age,
            e.racer_weight,
            e.motor_number,
            e.boat_number,
            e.win_rate,
            e.second_rate,
            e.third_rate,
            e.f_count,
            e.l_count,
            e.avg_st,
            e.local_win_rate,
            e.local_second_rate,
            e.local_third_rate,
            e.motor_second_rate,
            e.motor_third_rate,
            e.boat_second_rate,
            e.boat_third_rate,
            res.rank as result
        FROM races r
        JOIN entries e ON r.id = e.race_id
        LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE 1=1
        """

        params = []

        if start_date:
            query += " AND r.race_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND r.race_date <= ?"
            params.append(end_date)

        if venue_codes:
            placeholders = ','.join(['?'] * len(venue_codes))
            query += f" AND r.venue_code IN ({placeholders})"
            params.extend(venue_codes)

        query += " ORDER BY r.race_date, r.venue_code, r.race_number, e.pit_number"

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        print(f"データ読み込み完了: {len(df):,}行")
        return df

    def handle_missing_values(self, df, strategy='fill_zero'):
        """
        欠損値を処理

        Args:
            df: 処理対象のDataFrame
            strategy: 処理戦略
                'fill_zero': 0で埋める（デフォルト）
                'fill_mean': 平均値で埋める
                'drop': 欠損値のある行を削除

        Returns:
            DataFrame: 処理後のDataFrame
        """
        result_df = df.copy()

        # 数値カラムを特定
        numeric_cols = [
            'win_rate', 'second_rate', 'third_rate',
            'local_win_rate', 'local_second_rate', 'local_third_rate',
            'avg_st', 'f_count', 'l_count',
            'motor_second_rate', 'motor_third_rate',
            'boat_second_rate', 'boat_third_rate',
            'racer_age', 'racer_weight'
        ]

        if strategy == 'fill_zero':
            # 注意: fill_zeroは推奨されません。統計的意味を歪める可能性があります
            print("警告: fill_zeroは統計的意味を歪める可能性があります。fill_medianまたはfill_mean推奨")
            result_df[numeric_cols] = result_df[numeric_cols].fillna(0)

        elif strategy == 'fill_mean':
            # 欠損値を平均値で埋める
            for col in numeric_cols:
                if col in result_df.columns:
                    result_df[col] = result_df[col].fillna(result_df[col].mean())

        elif strategy == 'fill_median':
            # 欠損値を中央値で埋める（外れ値に頑健）
            for col in numeric_cols:
                if col in result_df.columns:
                    result_df[col] = result_df[col].fillna(result_df[col].median())

        elif strategy == 'fill_with_indicator':
            # 欠損値を中央値で埋め、欠損フラグを追加
            for col in numeric_cols:
                if col in result_df.columns:
                    result_df[f'{col}_is_missing'] = result_df[col].isna().astype(int)
                    result_df[col] = result_df[col].fillna(result_df[col].median())

        elif strategy == 'drop':
            # 欠損値を含む行を削除
            result_df = result_df.dropna(subset=numeric_cols)

        else:
            raise ValueError(f"不明な戦略: {strategy}. 'fill_zero', 'fill_mean', 'fill_median', 'fill_with_indicator', 'drop'のいずれかを指定してください")

        print(f"欠損値処理完了 (strategy={strategy}): {len(result_df):,}行")
        return result_df

    def generate_features(self, df, phase='3.1'):
        """
        特徴量を生成

        Args:
            df: 処理対象のDataFrame
            phase: フェーズ ('3.1', '3.2', '3.3')

        Returns:
            DataFrame: 特徴量生成後のDataFrame
        """
        result_df = df.copy()

        # Phase 3.1: 基本特徴量
        result_df = self.feature_generator.generate_basic_features(result_df)

        # Phase 3.2: 派生特徴量
        if phase in ['3.2', '3.3']:
            result_df = self.feature_generator.generate_derived_features(result_df)

        # Phase 3.3: 高度な特徴量
        if phase == '3.3':
            result_df = self.feature_generator.generate_advanced_features(result_df)

        print(f"特徴量生成完了 (phase={phase}): {len(result_df.columns)}カラム")
        return result_df

    def normalize_features(self, df, feature_cols, fit=True):
        """
        特徴量を正規化

        Args:
            df: 処理対象のDataFrame
            feature_cols: 正規化する特徴量のリスト
            fit: Trueの場合はfit_transform、Falseの場合はtransformのみ

        Returns:
            DataFrame: 正規化後のDataFrame
        """
        result_df = df.copy()

        # StandardScalerで正規化する列
        standard_cols = [
            'win_rate', 'second_rate', 'third_rate',
            'local_win_rate', 'local_second_rate', 'local_third_rate',
            'motor_second_rate', 'motor_third_rate',
            'boat_second_rate', 'boat_third_rate',
            'avg_st'
        ]

        # MinMaxScalerで正規化する列
        minmax_cols = ['racer_age', 'racer_weight']

        # StandardScaler適用
        available_standard_cols = [col for col in standard_cols if col in result_df.columns]
        if available_standard_cols:
            if fit:
                result_df[available_standard_cols] = self.scaler.fit_transform(
                    result_df[available_standard_cols]
                )
            else:
                result_df[available_standard_cols] = self.scaler.transform(
                    result_df[available_standard_cols]
                )

        # MinMaxScaler適用
        available_minmax_cols = [col for col in minmax_cols if col in result_df.columns]
        if available_minmax_cols:
            if fit:
                result_df[available_minmax_cols] = self.age_scaler.fit_transform(
                    result_df[available_minmax_cols]
                )
            else:
                result_df[available_minmax_cols] = self.age_scaler.transform(
                    result_df[available_minmax_cols]
                )

        print(f"正規化完了: {len(available_standard_cols)}列 (Standard), {len(available_minmax_cols)}列 (MinMax)")
        return result_df

    def prepare_dataset(self, df, phase='3.1', target_col='result', test_size=0.2, random_state=42):
        """
        機械学習用データセットを準備

        Args:
            df: 処理対象のDataFrame
            phase: フェーズ ('3.1', '3.2', '3.3')
            target_col: 目的変数のカラム名
            test_size: テストデータの割合
            random_state: 乱数シード

        Returns:
            tuple: (X_train, X_test, y_train, y_test, feature_names)
        """
        # 1. 結果がないデータを除外
        df_with_result = df[df[target_col].notna()].copy()
        print(f"結果データあり: {len(df_with_result):,}行")

        # 2. 特徴量リストを取得
        feature_names = self.feature_generator.get_feature_list(phase)

        # 実際に存在する特徴量のみを使用
        available_features = [col for col in feature_names if col in df_with_result.columns]
        print(f"使用する特徴量: {len(available_features)}個")

        # 3. 特徴量行列と目的変数を分離
        X = df_with_result[available_features].values
        y = df_with_result[target_col].values

        # 4. 訓練/テストデータ分割
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state
        )

        print(f"データ分割完了:")
        print(f"  訓練データ: {len(X_train):,}行")
        print(f"  テストデータ: {len(X_test):,}行")

        return X_train, X_test, y_train, y_test, available_features

    def run_pipeline(self, start_date=None, end_date=None, venue_codes=None,
                     phase='3.1', test_size=0.2, random_state=42):
        """
        データ前処理パイプラインを一括実行

        Args:
            start_date: 開始日
            end_date: 終了日
            venue_codes: 競艇場コード
            phase: フェーズ
            test_size: テストデータ割合
            random_state: 乱数シード

        Returns:
            dict: パイプライン実行結果
        """
        print("=" * 80)
        print("データ前処理パイプライン実行")
        print("=" * 80)

        # 1. データ読み込み
        print("\n[1/6] データ読み込み")
        df = self.load_data(start_date, end_date, venue_codes)

        # 2. 欠損値処理
        print("\n[2/6] 欠損値処理")
        df = self.handle_missing_values(df, strategy='fill_zero')

        # 3. 特徴量生成
        print("\n[3/6] 特徴量生成")
        df = self.generate_features(df, phase=phase)

        # 4. 正規化
        print("\n[4/6] 正規化")
        df = self.normalize_features(df, feature_cols=None, fit=True)

        # 5. データセット準備
        print("\n[5/6] データセット準備")
        X_train, X_test, y_train, y_test, feature_names = self.prepare_dataset(
            df, phase=phase, test_size=test_size, random_state=random_state
        )

        # 6. 完了
        print("\n[6/6] 完了")
        print("=" * 80)

        return {
            'X_train': X_train,
            'X_test': X_test,
            'y_train': y_train,
            'y_test': y_test,
            'feature_names': feature_names,
            'preprocessor': self
        }


def main():
    """
    データ前処理パイプラインのテスト実行
    """
    print("=" * 80)
    print("データ前処理パイプライン テスト")
    print("=" * 80)

    preprocessor = DataPreprocessor(db_path='data/boatrace.db')

    # パイプライン実行
    result = preprocessor.run_pipeline(
        start_date='2024-10-01',
        end_date='2024-10-31',
        phase='3.1',
        test_size=0.2,
        random_state=42
    )

    print("\n=== 結果サマリー ===")
    print(f"訓練データ形状: {result['X_train'].shape}")
    print(f"テストデータ形状: {result['X_test'].shape}")
    print(f"特徴量数: {len(result['feature_names'])}")
    print(f"特徴量リスト:")
    for feat in result['feature_names']:
        print(f"  - {feat}")

    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
