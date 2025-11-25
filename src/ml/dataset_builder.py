"""
機械学習用データセットビルダー
XGBoost + SHAP用の特徴量データセットを生成
"""
import sqlite3
import pandas as pd
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from src.features.racer_features import RacerFeatureExtractor


class DatasetBuilder:
    """機械学習用データセットビルダー"""

    def __init__(self, db_path="data/boatrace.db"):
        self.db_path = db_path

    def build_training_dataset(
        self,
        start_date: str,
        end_date: str,
        venue_codes: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        学習用データセットを構築

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)
            venue_codes: 競艇場コードリスト（Noneの場合は全競艇場）

        Returns:
            pd.DataFrame: 特徴量データセット
        """
        conn = sqlite3.connect(self.db_path)

        # ベースクエリ
        where_clauses = [
            "r.race_date BETWEEN ? AND ?"
        ]
        params = [start_date, end_date]

        if venue_codes:
            placeholders = ','.join('?' * len(venue_codes))
            where_clauses.append(f"r.venue_code IN ({placeholders})")
            params.extend(venue_codes)

        where_sql = " AND ".join(where_clauses)

        query = f"""
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                r.race_number,
                r.race_time,

                e.pit_number,
                e.racer_number,
                e.racer_name,
                e.racer_rank,
                e.racer_age,
                e.racer_weight,
                e.motor_number,
                e.boat_number,
                e.win_rate,
                e.second_rate,
                e.third_rate,

                rd.exhibition_time,
                rd.tilt_angle,
                rd.parts_replacement,
                rd.actual_course,
                rd.st_time,

                w.temperature,
                w.weather_condition,
                w.wind_speed,
                w.wind_direction,
                w.water_temperature,
                w.wave_height,

                res.rank as result_rank

            FROM entries e
            JOIN races r ON e.race_id = r.id
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            LEFT JOIN weather w ON r.venue_code = w.venue_code
                AND DATE(r.race_date) = DATE(w.weather_date)
            LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            WHERE {where_sql}
            ORDER BY r.race_date, r.venue_code, r.race_number, e.pit_number
        """

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        return df

    def add_derived_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        派生特徴量を追加

        Args:
            df: ベースデータフレーム

        Returns:
            pd.DataFrame: 派生特徴量追加後のデータフレーム
        """
        # コピーを作成
        df = df.copy()

        # 1. 目的変数：勝利フラグ
        df['is_win'] = (df['result_rank'] == '1').astype(int)

        # 2. 目的変数：2着以内フラグ
        df['is_place_2'] = df['result_rank'].apply(
            lambda x: 1 if x in ['1', '2'] else 0
        )

        # 3. 目的変数：3着以内フラグ
        df['is_place_3'] = df['result_rank'].apply(
            lambda x: 1 if x in ['1', '2', '3'] else 0
        )

        # 4. 枠番がインコースか
        df['is_inner_pit'] = (df['pit_number'] == 1).astype(int)

        # 5. 実際のコースがインコースか
        df['is_inner_course'] = (df['actual_course'] == 1).astype(int)

        # 6. 枠番とコースのずれ
        df['pit_course_diff'] = df['pit_number'] - df['actual_course'].fillna(df['pit_number'])

        # 7. 級別をダミー変数化
        if 'racer_rank' in df.columns:
            rank_dummies = pd.get_dummies(df['racer_rank'], prefix='rank')
            df = pd.concat([df, rank_dummies], axis=1)

        # 8. 風向をダミー変数化
        if 'wind_direction' in df.columns:
            wind_dummies = pd.get_dummies(df['wind_direction'], prefix='wind')
            df = pd.concat([df, wind_dummies], axis=1)

        # 9. 天候をダミー変数化
        if 'weather_condition' in df.columns:
            weather_dummies = pd.get_dummies(df['weather_condition'], prefix='weather')
            df = pd.concat([df, weather_dummies], axis=1)

        # 10. 展示タイムの順位（レース内での相対順位）
        df['exhibition_time_rank'] = df.groupby('race_id')['exhibition_time'].rank(method='min')

        # 11. STタイムの順位
        df['st_time_rank'] = df.groupby('race_id')['st_time'].rank(method='min')

        # 12. 勝率の順位（レース内）
        df['win_rate_rank'] = df.groupby('race_id')['win_rate'].rank(method='min', ascending=False)

        # 13. 年齢グループ
        if 'racer_age' in df.columns:
            df['age_group'] = pd.cut(
                df['racer_age'],
                bins=[0, 25, 35, 45, 100],
                labels=['young', 'prime', 'veteran', 'senior']
            )
            age_dummies = pd.get_dummies(df['age_group'], prefix='age')
            df = pd.concat([df, age_dummies], axis=1)

        # 14. 選手特徴量（改善アドバイスに基づく）
        df = self._add_racer_features(df)

        return df

    def _add_racer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        選手ベースの特徴量を追加（改善アドバイスに基づく）

        追加特徴量:
        - recent_avg_rank_3/5/10: 直近N戦平均着順
        - recent_win_rate_3/5/10: 直近N戦勝率
        - motor_recent_2rate_diff: モーター直近2連率差分

        Args:
            df: データフレーム

        Returns:
            pd.DataFrame: 選手特徴量追加後のデータフレーム
        """
        # コピーを作成
        df = df.copy()

        # 必要なカラムがあるか確認
        required_cols = ['racer_number', 'motor_number', 'race_date']
        if not all(col in df.columns for col in required_cols):
            print(f"[WARNING] 選手特徴量追加スキップ: 必要なカラムが不足 {required_cols}")
            return df

        # RacerFeatureExtractor インスタンス作成
        extractor = RacerFeatureExtractor(db_path=self.db_path)

        # SQLite接続を開く
        conn = sqlite3.connect(self.db_path)

        # 各行の選手特徴量を計算
        racer_features_list = []

        for idx, row in df.iterrows():
            racer_number = row['racer_number']
            motor_number = row['motor_number']
            race_date = row['race_date']

            # データが欠損している場合はスキップ
            if pd.isna(racer_number) or pd.isna(motor_number) or pd.isna(race_date):
                racer_features = {
                    'recent_avg_rank_3': 3.5,
                    'recent_avg_rank_5': 3.5,
                    'recent_avg_rank_10': 3.5,
                    'recent_win_rate_3': 0.0,
                    'recent_win_rate_5': 0.0,
                    'recent_win_rate_10': 0.0,
                    'motor_recent_2rate_diff': 0.0
                }
            else:
                # 特徴量抽出
                racer_features = extractor.extract_all_features(
                    racer_number=str(racer_number),
                    motor_number=int(motor_number),
                    race_date=str(race_date),
                    conn=conn
                )

            racer_features_list.append(racer_features)

        # 接続を閉じる
        conn.close()

        # DataFrameに変換して結合
        df_racer_features = pd.DataFrame(racer_features_list, index=df.index)
        df = pd.concat([df, df_racer_features], axis=1)

        print(f"[INFO] 選手特徴量を追加: {len(df_racer_features.columns)}個 ({', '.join(df_racer_features.columns)})")

        return df

    def export_to_csv(
        self,
        df: pd.DataFrame,
        output_path: str,
        include_target: bool = True
    ) -> str:
        """
        データセットをCSVにエクスポート

        Args:
            df: データフレーム
            output_path: 出力パス
            include_target: 目的変数を含めるか

        Returns:
            str: 出力ファイルパス
        """
        if not include_target:
            # 目的変数を除外
            target_cols = ['result_rank', 'is_win', 'is_place_2', 'is_place_3']
            df = df.drop(columns=[col for col in target_cols if col in df.columns])

        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        return output_path

    def export_to_json(
        self,
        df: pd.DataFrame,
        output_path: str,
        orient: str = 'records'
    ) -> str:
        """
        データセットをJSONにエクスポート

        Args:
            df: データフレーム
            output_path: 出力パス
            orient: JSON形式 ('records', 'split', 'index')

        Returns:
            str: 出力ファイルパス
        """
        df.to_json(output_path, orient=orient, force_ascii=False, indent=2)
        return output_path

    def get_feature_summary(self, df: pd.DataFrame) -> Dict:
        """
        特徴量の統計サマリーを取得

        Args:
            df: データフレーム

        Returns:
            Dict: サマリー情報
        """
        summary = {
            "total_records": len(df),
            "total_races": df['race_id'].nunique() if 'race_id' in df.columns else 0,
            "date_range": {
                "start": df['race_date'].min() if 'race_date' in df.columns else None,
                "end": df['race_date'].max() if 'race_date' in df.columns else None
            },
            "venues": df['venue_code'].nunique() if 'venue_code' in df.columns else 0,
            "features": {
                "total": len(df.columns),
                "numeric": len(df.select_dtypes(include=['int64', 'float64']).columns),
                "categorical": len(df.select_dtypes(include=['object']).columns)
            },
            "missing_data": {
                col: int(df[col].isna().sum())
                for col in df.columns if df[col].isna().sum() > 0
            },
            "target_distribution": {}
        }

        # 目的変数の分布
        if 'is_win' in df.columns:
            summary["target_distribution"]["wins"] = int(df['is_win'].sum())
            summary["target_distribution"]["losses"] = int((df['is_win'] == 0).sum())
            summary["target_distribution"]["win_rate"] = float(df['is_win'].mean())

        return summary

    def split_by_date(
        self,
        df: pd.DataFrame,
        train_end_date: str,
        valid_end_date: str
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        時系列に基づいてデータを分割

        Args:
            df: データフレーム
            train_end_date: 訓練データの終了日 (YYYY-MM-DD)
            valid_end_date: 検証データの終了日 (YYYY-MM-DD)

        Returns:
            Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]: (train, valid, test)
        """
        df = df.sort_values('race_date')

        train = df[df['race_date'] <= train_end_date]
        valid = df[(df['race_date'] > train_end_date) & (df['race_date'] <= valid_end_date)]
        test = df[df['race_date'] > valid_end_date]

        return train, valid, test

    def get_feature_list(self, df: pd.DataFrame, exclude_cols: Optional[List[str]] = None) -> List[str]:
        """
        機械学習に使用する特徴量リストを取得

        Args:
            df: データフレーム
            exclude_cols: 除外するカラムリスト

        Returns:
            List[str]: 特徴量カラム名リスト
        """
        # デフォルトで除外するカラム
        default_exclude = [
            'race_id', 'race_date', 'racer_number', 'racer_name',
            'result_rank', 'is_win', 'is_place_2', 'is_place_3',
            'age_group'  # ダミー変数化済みのため元のカテゴリカル列は除外
        ]

        if exclude_cols:
            default_exclude.extend(exclude_cols)

        # 数値型とブール型のカラムを抽出
        feature_cols = []
        for col in df.columns:
            if col not in default_exclude:
                if df[col].dtype in ['int64', 'float64', 'bool']:
                    feature_cols.append(col)
                elif col.startswith(('rank_', 'wind_', 'weather_', 'age_')):
                    # ダミー変数
                    feature_cols.append(col)

        return feature_cols

    def prepare_for_xgboost(
        self,
        df: pd.DataFrame,
        target_col: str = 'is_win'
    ) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
        """
        XGBoost用にデータを準備

        Args:
            df: データフレーム
            target_col: 目的変数カラム名

        Returns:
            Tuple[pd.DataFrame, pd.Series, List[str]]: (X, y, feature_names)
        """
        # 特徴量リストを取得
        feature_cols = self.get_feature_list(df)

        # 欠損値を処理
        X = df[feature_cols].copy()

        # Categorical型の列を通常の型に変換してから欠損値を埋める
        for col in X.columns:
            if X[col].dtype.name == 'category':
                X[col] = X[col].astype('object')

        X = X.fillna(-999)  # XGBoostは欠損値を扱えるが、明示的に埋める

        # 目的変数
        y = df[target_col].copy()

        return X, y, feature_cols
