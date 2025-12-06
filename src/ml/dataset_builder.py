"""
機械学習用データセットビルダー
XGBoost + SHAP用の特徴量データセットを生成

2025-12-06: ボーターズ分析を参考にした新規特徴量を追加
- コース別成績（course_win_rate, course_2ren_rate, course_avg_rank）
- 今節成績（node_avg_rank, node_trend）
- 予測ST（predicted_st, st_stability）
- モーター会場順位（motor_venue_rank, motor_venue_2ren）

2025-12-06: 会場×コース特徴量を追加（Opus深掘り分析結果）
- venue_course_advantage: 会場コース有利度（最大25%差）
- racer_venue_course_skill: ベイズ推定による選手×会場×コース適性
- recent_course_win_rate: 直近10走のコース別成績
- wind/wave_course_factor: 条件×コース調整係数

2025-12-06: バッチ処理による高速化
- 従来の行ごとDBクエリからバッチ処理に変更
- 32,000行で5分以上 → 30秒程度に高速化
"""
import sqlite3
import pandas as pd
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from src.features.racer_features import RacerFeatureExtractor
from src.features.boaters_inspired_features import BoatersInspiredFeatureExtractor
from src.features.venue_course_features import VenueCourseFeatureExtractor
from src.features.batch_feature_extractor import BatchFeatureExtractor


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

    def _add_boaters_features(self, df: pd.DataFrame, use_top_features_only: bool = True) -> pd.DataFrame:
        """
        ボーターズ分析を参考にした特徴量を追加

        重要度が高い特徴量:
        - course_win_rate: コース別勝率（最重要）
        - course_2ren_rate: コース別2連率
        - course_avg_rank: コース別平均着順
        - node_avg_rank: 今節平均着順
        - predicted_st: 予測ST
        - motor_venue_rank: モーター会場順位
        - motor_venue_2ren: モーター会場2連率

        Args:
            df: データフレーム
            use_top_features_only: 上位重要度の特徴量のみ使用（高速化）

        Returns:
            pd.DataFrame: ボーターズ特徴量追加後のデータフレーム
        """
        df = df.copy()

        required_cols = ['racer_number', 'motor_number', 'venue_code', 'race_date', 'race_number']
        if not all(col in df.columns for col in required_cols):
            print(f"[WARNING] ボーターズ特徴量追加スキップ: 必要なカラムが不足")
            return df

        extractor = BoatersInspiredFeatureExtractor(db_path=self.db_path)
        conn = sqlite3.connect(self.db_path)

        boaters_features_list = []
        total = len(df)
        print(f"[INFO] ボーターズ特徴量計算中... ({total}行)")

        for idx, row in df.iterrows():
            if idx % 10000 == 0 and idx > 0:
                print(f"  Progress: {idx}/{total} ({idx/total*100:.1f}%)")

            try:
                # 進入コース推定
                target_course = row.get('actual_course') or row.get('pit_number') or 1
                target_course = int(target_course) if not pd.isna(target_course) else int(row.get('pit_number', 1))

                if use_top_features_only:
                    # 高速化: 最重要特徴量のみ計算
                    features = {}

                    # コース別成績（最重要）
                    course_stats = extractor.compute_course_specific_rate(
                        str(row['racer_number']),
                        target_course,
                        str(row['race_date']),
                        conn=conn
                    )
                    features['course_win_rate'] = course_stats['course_win_rate']
                    features['course_2ren_rate'] = course_stats['course_2ren_rate']
                    features['course_avg_rank'] = course_stats['course_avg_rank']

                    # 今節成績
                    node_perf = extractor.compute_current_node_performance(
                        str(row['racer_number']),
                        str(row['venue_code']),
                        str(row['race_date']),
                        int(row['race_number']),
                        conn=conn
                    )
                    features['node_avg_rank'] = node_perf['node_avg_rank']
                    features['node_trend'] = node_perf['node_trend']

                    # 予測ST
                    predicted_st, st_stability = extractor.compute_predicted_st(
                        str(row['racer_number']),
                        str(row['race_date']),
                        conn=conn
                    )
                    features['predicted_st'] = predicted_st
                    features['st_stability'] = st_stability

                else:
                    # 全特徴量を計算
                    motor_num = int(row['motor_number']) if pd.notna(row['motor_number']) else 0
                    features = extractor.extract_all_features(
                        str(row['racer_number']),
                        motor_num,
                        str(row['venue_code']),
                        str(row['race_date']),
                        int(row['race_number']),
                        target_course,
                        conn=conn
                    )

            except Exception as e:
                features = {
                    'course_win_rate': 0.17,
                    'course_2ren_rate': 0.33,
                    'course_avg_rank': 3.5,
                    'node_avg_rank': 3.5,
                    'node_trend': 0.0,
                    'predicted_st': 0.15,
                    'st_stability': 0.05
                }

            boaters_features_list.append(features)

        conn.close()

        df_boaters = pd.DataFrame(boaters_features_list, index=df.index)
        df = pd.concat([df, df_boaters], axis=1)

        print(f"[INFO] ボーターズ特徴量を追加: {len(df_boaters.columns)}個")

        return df

    def _add_venue_course_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        会場×コース特徴量を追加（Opus深掘り分析結果）

        重要度が高い特徴量:
        - racer_venue_course_skill: ベイズ推定による適性（重要度0.162）
        - racer_venue_course_combined: 統合スコア（重要度0.142）
        - venue_course_advantage: 会場コース有利度

        Args:
            df: データフレーム

        Returns:
            pd.DataFrame: 会場×コース特徴量追加後のデータフレーム
        """
        df = df.copy()

        required_cols = ['racer_number', 'venue_code', 'race_date', 'pit_number']
        if not all(col in df.columns for col in required_cols):
            print(f"[WARNING] 会場×コース特徴量追加スキップ: 必要なカラムが不足")
            return df

        extractor = VenueCourseFeatureExtractor(db_path=self.db_path)
        conn = sqlite3.connect(self.db_path)

        venue_course_features_list = []
        total = len(df)
        print(f"[INFO] 会場×コース特徴量計算中... ({total}行)")

        for idx, row in df.iterrows():
            if idx % 10000 == 0 and idx > 0:
                print(f"  Progress: {idx}/{total} ({idx/total*100:.1f}%)")

            try:
                # 進入コース推定
                target_course = row.get('actual_course') or row.get('pit_number') or 1
                target_course = int(target_course) if not pd.isna(target_course) else int(row.get('pit_number', 1))

                # 風速・波高
                wind_speed = row.get('wind_speed') if pd.notna(row.get('wind_speed')) else None
                wave_height = row.get('wave_height') if pd.notna(row.get('wave_height')) else None

                features = extractor.extract_all_features(
                    racer_number=str(row['racer_number']),
                    venue_code=str(row['venue_code']),
                    target_course=target_course,
                    race_date=str(row['race_date']),
                    wind_speed=wind_speed,
                    wave_height=wave_height,
                    conn=conn
                )

            except Exception as e:
                features = {
                    'venue_course_advantage': 0.0,
                    'recent_course_win_rate': 0.17,
                    'recent_course_2ren_rate': 0.33,
                    'recent_course_avg_rank': 3.5,
                    'wind_course_factor': 0.0,
                    'wave_course_factor': 0.0,
                    'condition_course_factor': 0.0,
                    'racer_venue_skill': 0.17,
                    'racer_course_skill': 0.17,
                    'racer_venue_course_skill': 0.17,
                    'racer_venue_course_combined': 0.17
                }

            venue_course_features_list.append(features)

        conn.close()

        df_venue_course = pd.DataFrame(venue_course_features_list, index=df.index)
        df = pd.concat([df, df_venue_course], axis=1)

        print(f"[INFO] 会場×コース特徴量を追加: {len(df_venue_course.columns)}個")

        return df

    def add_all_derived_features(
        self,
        df: pd.DataFrame,
        include_boaters: bool = True,
        include_venue_course: bool = True,
        use_batch: bool = True
    ) -> pd.DataFrame:
        """
        全ての派生特徴量を追加（ボーターズ特徴量・会場×コース特徴量含む）

        Args:
            df: ベースデータフレーム
            include_boaters: ボーターズ特徴量を含めるか
            include_venue_course: 会場×コース特徴量を含めるか
            use_batch: バッチ処理を使用するか（高速化、デフォルトTrue）

        Returns:
            pd.DataFrame: 全特徴量追加後のデータフレーム
        """
        # 基本派生特徴量
        df = self.add_derived_features(df)

        if use_batch and (include_boaters or include_venue_course):
            # バッチ処理による高速特徴量抽出
            batch_extractor = BatchFeatureExtractor(db_path=self.db_path)
            df = batch_extractor.add_all_features_batch(
                df,
                include_boaters=include_boaters,
                include_venue_course=include_venue_course
            )
        else:
            # 従来の行ごと処理（互換性のため残す）
            if include_boaters:
                df = self._add_boaters_features(df, use_top_features_only=True)

            if include_venue_course:
                df = self._add_venue_course_features(df)

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
