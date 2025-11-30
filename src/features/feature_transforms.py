"""
特徴量変換モジュール
Phase 1: 展示相対特徴量・ST相対特徴量の実装

2着・3着予測精度向上のための「レース内相対評価」特徴量を生成
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from scipy import stats


class FeatureTransformer:
    """
    レース内相対評価特徴量を生成するクラス

    主な機能:
    - 展示タイムの相対評価（レース内順位、差分、zスコア）
    - STタイムの相対評価
    - コース別補正
    """

    def __init__(self):
        # コース別展示タイム補正係数（インコースは展示タイムが遅くても有利）
        self.course_exh_adjustment = {
            1: -0.02,  # 1コースは0.02秒遅くても同等評価
            2: -0.01,
            3: 0.0,
            4: 0.0,
            5: 0.01,
            6: 0.02   # 6コースは0.02秒速くないと同等評価にならない
        }

        # コース別STタイム期待値（秒）
        self.course_st_expectation = {
            1: 0.15,  # 1コースは慎重なSTが多い
            2: 0.14,
            3: 0.13,
            4: 0.12,
            5: 0.11,
            6: 0.10   # 6コースは攻めるSTが多い
        }

    def add_exhibition_features(self, df: pd.DataFrame,
                                 exh_col: str = 'exhibition_time',
                                 course_col: str = 'actual_course',
                                 race_id_col: str = 'race_id') -> pd.DataFrame:
        """
        展示タイム相対評価特徴量を追加

        Args:
            df: 入力DataFrame（1レース6艇分のデータを含む）
            exh_col: 展示タイムのカラム名
            course_col: コースのカラム名
            race_id_col: レースIDのカラム名

        Returns:
            展示相対特徴量が追加されたDataFrame
        """
        result_df = df.copy()

        # 欠損値処理
        if exh_col not in result_df.columns:
            result_df[exh_col] = np.nan

        # コース別補正した展示タイム
        result_df['exh_adjusted'] = result_df.apply(
            lambda row: self._adjust_exhibition_time(
                row.get(exh_col, np.nan),
                row.get(course_col, 3)
            ),
            axis=1
        )

        # レース内統計量を計算
        race_groups = result_df.groupby(race_id_col)

        # 展示タイム順位（1が最速）
        result_df['exh_rank'] = race_groups['exh_adjusted'].rank(method='min', na_option='bottom')

        # レース平均との差分
        race_means = race_groups['exh_adjusted'].transform('mean')
        result_df['exh_diff'] = result_df['exh_adjusted'] - race_means

        # レース内zスコア（標準化）
        race_stds = race_groups['exh_adjusted'].transform('std')
        race_stds = race_stds.replace(0, np.nan)  # ゼロ除算防止
        result_df['exh_zscore'] = (result_df['exh_adjusted'] - race_means) / race_stds
        result_df['exh_zscore'] = result_df['exh_zscore'].fillna(0)

        # レース内最速との差
        race_mins = race_groups['exh_adjusted'].transform('min')
        result_df['exh_gap_to_best'] = result_df['exh_adjusted'] - race_mins

        # レース内最遅との差（相対的な位置）
        race_maxs = race_groups['exh_adjusted'].transform('max')
        race_range = race_maxs - race_mins
        race_range = race_range.replace(0, np.nan)
        result_df['exh_relative_position'] = (result_df['exh_adjusted'] - race_mins) / race_range
        result_df['exh_relative_position'] = result_df['exh_relative_position'].fillna(0.5)

        # 一時カラム削除
        result_df = result_df.drop('exh_adjusted', axis=1)

        return result_df

    def add_st_features(self, df: pd.DataFrame,
                        st_col: str = 'avg_st',
                        course_col: str = 'actual_course',
                        race_id_col: str = 'race_id') -> pd.DataFrame:
        """
        STタイム相対評価特徴量を追加

        Args:
            df: 入力DataFrame
            st_col: STタイムのカラム名（平均ST）
            course_col: コースのカラム名
            race_id_col: レースIDのカラム名

        Returns:
            ST相対特徴量が追加されたDataFrame
        """
        result_df = df.copy()

        # 欠損値処理
        if st_col not in result_df.columns:
            result_df[st_col] = 0.15  # デフォルト値

        # コース別期待値との差
        result_df['st_vs_expectation'] = result_df.apply(
            lambda row: self._compare_st_to_expectation(
                row.get(st_col, 0.15),
                row.get(course_col, 3)
            ),
            axis=1
        )

        # レース内統計量を計算
        race_groups = result_df.groupby(race_id_col)

        # ST順位（1が最速=最小値）
        result_df['st_rank'] = race_groups[st_col].rank(method='min', na_option='bottom')

        # レース平均との差分
        race_means = race_groups[st_col].transform('mean')
        result_df['st_diff'] = result_df[st_col] - race_means

        # レース内zスコア
        race_stds = race_groups[st_col].transform('std')
        race_stds = race_stds.replace(0, np.nan)
        result_df['st_zscore'] = (result_df[st_col] - race_means) / race_stds
        result_df['st_zscore'] = result_df['st_zscore'].fillna(0)

        # 相対ST（レース内での相対的な速さ）
        race_mins = race_groups[st_col].transform('min')
        race_maxs = race_groups[st_col].transform('max')
        race_range = race_maxs - race_mins
        race_range = race_range.replace(0, np.nan)
        result_df['st_relative'] = (result_df[st_col] - race_mins) / race_range
        result_df['st_relative'] = result_df['st_relative'].fillna(0.5)

        return result_df

    def add_winner_context_features(self, df: pd.DataFrame,
                                     winner_pit: int,
                                     race_id_col: str = 'race_id') -> pd.DataFrame:
        """
        1着艇の情報をコンテキストとして追加（Stage2用）

        Args:
            df: 入力DataFrame（残り5艇分）
            winner_pit: 1着艇のピット番号
            race_id_col: レースIDのカラム名

        Returns:
            1着艇コンテキスト特徴量が追加されたDataFrame
        """
        result_df = df.copy()

        # 1着艇との差分特徴量
        result_df['gap_to_winner_course'] = abs(result_df['actual_course'] - winner_pit)
        result_df['is_adjacent_to_winner'] = (result_df['gap_to_winner_course'] == 1).astype(int)

        # 1着艇がインコースの場合の評価
        result_df['winner_is_inner'] = int(winner_pit <= 2)
        result_df['winner_is_outer'] = int(winner_pit >= 5)

        return result_df

    def add_second_context_features(self, df: pd.DataFrame,
                                      winner_pit: int,
                                      second_pit: int,
                                      race_id_col: str = 'race_id') -> pd.DataFrame:
        """
        1着・2着艇の情報をコンテキストとして追加（Stage3用）

        Args:
            df: 入力DataFrame（残り4艇分）
            winner_pit: 1着艇のピット番号
            second_pit: 2着艇のピット番号
            race_id_col: レースIDのカラム名

        Returns:
            1着・2着艇コンテキスト特徴量が追加されたDataFrame
        """
        result_df = df.copy()

        # 1着・2着艇との差分特徴量
        result_df['gap_to_winner_course'] = abs(result_df['actual_course'] - winner_pit)
        result_df['gap_to_second_course'] = abs(result_df['actual_course'] - second_pit)

        # 1着・2着艇の間に位置するか
        min_course = min(winner_pit, second_pit)
        max_course = max(winner_pit, second_pit)
        result_df['between_top2'] = (
            (result_df['actual_course'] > min_course) &
            (result_df['actual_course'] < max_course)
        ).astype(int)

        # インナーバイアス（1着2着がインコースに偏っているか）
        result_df['top2_inner_bias'] = int((winner_pit + second_pit) <= 5)

        return result_df

    def _adjust_exhibition_time(self, exh_time: float, course: int) -> float:
        """コース別補正した展示タイムを計算"""
        if pd.isna(exh_time) or exh_time <= 0:
            return np.nan
        adjustment = self.course_exh_adjustment.get(course, 0)
        return exh_time + adjustment

    def _compare_st_to_expectation(self, st_time: float, course: int) -> float:
        """コース別期待値との差を計算（負の値=期待より速い）"""
        if pd.isna(st_time):
            return 0
        expectation = self.course_st_expectation.get(course, 0.13)
        return st_time - expectation


class RaceRelativeFeatureBuilder:
    """
    レース単位で相対特徴量を構築するビルダークラス
    """

    def __init__(self, db_connection=None):
        self.conn = db_connection
        self.transformer = FeatureTransformer()

    def build_race_features(self, race_id: str,
                            entries_df: pd.DataFrame = None) -> pd.DataFrame:
        """
        レースIDを指定して相対特徴量を構築

        Args:
            race_id: レースID
            entries_df: 既に取得済みのエントリーデータ（省略時はDBから取得）

        Returns:
            相対特徴量が追加されたDataFrame
        """
        if entries_df is None and self.conn is not None:
            entries_df = self._fetch_race_entries(race_id)

        if entries_df is None or len(entries_df) == 0:
            return pd.DataFrame()

        # 各種相対特徴量を追加
        result_df = entries_df.copy()
        result_df['race_id'] = race_id

        result_df = self.transformer.add_exhibition_features(result_df)
        result_df = self.transformer.add_st_features(result_df)

        return result_df

    def build_training_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        学習用データに相対特徴量を一括追加

        Args:
            df: race_id, pit_number, 各種特徴量を含むDataFrame

        Returns:
            相対特徴量が追加されたDataFrame
        """
        if df is None or len(df) == 0:
            return df

        result_df = df.copy()
        result_df = self.transformer.add_exhibition_features(result_df)
        result_df = self.transformer.add_st_features(result_df)

        return result_df

    def _fetch_race_entries(self, race_id: str) -> pd.DataFrame:
        """DBからレースエントリーを取得"""
        if self.conn is None:
            return None

        query = """
            SELECT
                e.pit_number,
                e.racer_number,
                rd.exhibition_time,
                rd.start_timing as avg_st,
                COALESCE(rd.actual_course, e.pit_number) as actual_course,
                e.win_rate,
                e.second_rate,
                e.motor_second_rate,
                e.boat_second_rate
            FROM entries e
            LEFT JOIN race_details rd
                ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        """

        import sqlite3
        cursor = self.conn.cursor()
        cursor.execute(query, (race_id,))
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        return pd.DataFrame(rows, columns=columns)


def create_training_dataset_with_relative_features(conn,
                                                    start_date: str = None,
                                                    end_date: str = None,
                                                    limit: int = None) -> pd.DataFrame:
    """
    学習用データセットを相対特徴量付きで作成

    Args:
        conn: SQLite接続
        start_date: 開始日（YYYY-MM-DD形式）
        end_date: 終了日（YYYY-MM-DD形式）
        limit: 取得件数制限

    Returns:
        相対特徴量付き学習データ
    """
    query = """
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            e.pit_number,
            e.racer_number,
            e.win_rate,
            e.second_rate,
            e.motor_second_rate,
            e.boat_second_rate,
            rd.exhibition_time,
            rd.st_time as avg_st,
            COALESCE(rd.actual_course, e.pit_number) as actual_course,
            CAST(res.rank AS INTEGER) as rank
        FROM races r
        JOIN entries e ON r.id = e.race_id
        JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
        WHERE res.rank IS NOT NULL
          AND res.rank NOT IN ('F', 'L', '欠', '失', '転', '落')
    """

    params = []

    if start_date:
        query += " AND r.race_date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND r.race_date <= ?"
        params.append(end_date)

    query += " ORDER BY r.race_date, r.id, e.pit_number"

    if limit:
        query += f" LIMIT {limit}"

    df = pd.read_sql_query(query, conn, params=params)

    if len(df) == 0:
        return df

    # 相対特徴量を追加
    builder = RaceRelativeFeatureBuilder()
    df = builder.build_training_data(df)

    return df
