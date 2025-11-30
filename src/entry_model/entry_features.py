"""
進入予測用特徴量生成
Phase 1: 進入コース予測のための特徴量
"""
import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta


class EntryFeatureGenerator:
    """
    進入予測用特徴量生成クラス

    特徴量:
    - 選手の進入癖（過去100走の進入偏差）
    - 選手の進入別勝率
    - モーターの出足/伸び傾向
    - レースグレード
    - 風向（追い/向い）
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """DB接続を取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def calculate_entry_tendency(self, racer_number: str,
                                  target_date: str,
                                  n_races: int = 100) -> Dict[str, float]:
        """
        選手の進入傾向を計算

        Args:
            racer_number: 選手番号
            target_date: 基準日
            n_races: 参照するレース数

        Returns:
            進入傾向特徴量
        """
        query = """
            SELECT
                e.pit_number,
                rd.actual_course,
                r.race_date
            FROM entries e
            JOIN races r ON e.race_id = r.id
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.racer_number = ?
              AND r.race_date < ?
              AND rd.actual_course IS NOT NULL
            ORDER BY r.race_date DESC
            LIMIT ?
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (racer_number, target_date, n_races))
        results = cursor.fetchall()
        conn.close()

        if len(results) < 5:
            return {
                'entry_deviation_mean': 0.0,
                'entry_deviation_std': 0.0,
                'inner_entry_rate': 0.0,
                'outer_entry_rate': 0.0,
                'same_entry_rate': 0.0,
                'entry_aggression': 0.0,
            }

        deviations = []
        inner_count = 0  # 内側に入った回数
        outer_count = 0  # 外側に出た回数
        same_count = 0   # 同じコース

        for row in results:
            pit = row['pit_number']
            course = row['actual_course']
            deviation = course - pit
            deviations.append(deviation)

            if deviation < 0:
                inner_count += 1
            elif deviation > 0:
                outer_count += 1
            else:
                same_count += 1

        n = len(results)
        return {
            'entry_deviation_mean': np.mean(deviations),
            'entry_deviation_std': np.std(deviations),
            'inner_entry_rate': inner_count / n,
            'outer_entry_rate': outer_count / n,
            'same_entry_rate': same_count / n,
            'entry_aggression': (inner_count - outer_count) / n,  # 正=攻め、負=待ち
        }

    def calculate_entry_win_rate(self, racer_number: str,
                                  target_date: str,
                                  n_races: int = 200) -> Dict[str, float]:
        """
        進入コース別の勝率を計算

        Args:
            racer_number: 選手番号
            target_date: 基準日
            n_races: 参照するレース数

        Returns:
            コース別勝率
        """
        query = """
            SELECT
                rd.actual_course,
                res.rank
            FROM entries e
            JOIN races r ON e.race_id = r.id
            JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            WHERE e.racer_number = ?
              AND r.race_date < ?
              AND rd.actual_course IS NOT NULL
              AND res.rank IS NOT NULL
            ORDER BY r.race_date DESC
            LIMIT ?
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (racer_number, target_date, n_races))
        results = cursor.fetchall()
        conn.close()

        # コース別の成績を集計
        course_stats = {i: {'wins': 0, 'total': 0} for i in range(1, 7)}

        for row in results:
            course = row['actual_course']
            rank = row['rank']
            if course and 1 <= course <= 6:
                course_stats[course]['total'] += 1
                try:
                    if int(rank) == 1:
                        course_stats[course]['wins'] += 1
                except (ValueError, TypeError):
                    pass

        # コース別勝率を計算
        features = {}
        for course in range(1, 7):
            total = course_stats[course]['total']
            if total >= 3:
                win_rate = course_stats[course]['wins'] / total
            else:
                win_rate = 0.0
            features[f'entry_course{course}_winrate'] = win_rate

        return features

    def calculate_motor_characteristics(self, motor_number: int,
                                         venue_code: str,
                                         target_date: str) -> Dict[str, float]:
        """
        モーターの出足/伸び特性を計算

        Args:
            motor_number: モーター番号
            venue_code: 会場コード
            target_date: 基準日

        Returns:
            モーター特性
        """
        # 展示タイムからモーター特性を推定
        query = """
            SELECT
                rd.exhibition_time,
                rd.st_time,
                rd.actual_course,
                res.rank
            FROM race_details rd
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE e.motor_number = ?
              AND r.venue_code = ?
              AND r.race_date < ?
              AND rd.exhibition_time IS NOT NULL
            ORDER BY r.race_date DESC
            LIMIT 50
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (motor_number, venue_code, target_date))
        results = cursor.fetchall()
        conn.close()

        if len(results) < 5:
            return {
                'motor_exhibition_avg': 0.0,
                'motor_exhibition_std': 0.0,
                'motor_st_avg': 0.0,
                'motor_inner_winrate': 0.0,
                'motor_outer_winrate': 0.0,
            }

        exhibition_times = []
        st_times = []
        inner_wins = 0
        inner_total = 0
        outer_wins = 0
        outer_total = 0

        for row in results:
            if row['exhibition_time']:
                exhibition_times.append(row['exhibition_time'])
            if row['st_time']:
                st_times.append(row['st_time'])

            course = row['actual_course']
            rank = row['rank']

            if course and rank:
                try:
                    is_win = int(rank) == 1
                    if course <= 2:
                        inner_total += 1
                        if is_win:
                            inner_wins += 1
                    elif course >= 5:
                        outer_total += 1
                        if is_win:
                            outer_wins += 1
                except (ValueError, TypeError):
                    pass

        return {
            'motor_exhibition_avg': np.mean(exhibition_times) if exhibition_times else 0.0,
            'motor_exhibition_std': np.std(exhibition_times) if len(exhibition_times) > 1 else 0.0,
            'motor_st_avg': np.mean(st_times) if st_times else 0.0,
            'motor_inner_winrate': inner_wins / inner_total if inner_total > 0 else 0.0,
            'motor_outer_winrate': outer_wins / outer_total if outer_total > 0 else 0.0,
        }

    def calculate_wind_features(self, venue_code: str,
                                 race_date: str) -> Dict[str, float]:
        """
        風向特徴量を計算

        追い風/向い風で進入に影響

        Args:
            venue_code: 会場コード
            race_date: レース日

        Returns:
            風向特徴量
        """
        query = """
            SELECT wind_speed, wind_direction
            FROM weather
            WHERE venue_code = ? AND weather_date = ?
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (venue_code, race_date))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {
                'wind_speed': 0.0,
                'is_headwind': 0,
                'is_tailwind': 0,
                'wind_strength': 0.0,
            }

        wind_speed = row['wind_speed'] or 0.0
        wind_direction = row['wind_direction'] or ''

        # 追い風/向い風の判定
        is_headwind = 1 if '向' in wind_direction else 0
        is_tailwind = 1 if '追' in wind_direction else 0

        return {
            'wind_speed': wind_speed,
            'is_headwind': is_headwind,
            'is_tailwind': is_tailwind,
            'wind_strength': wind_speed * (1 if is_tailwind else -1 if is_headwind else 0),
        }

    def generate_entry_features(self, race_id: int,
                                 venue_code: str,
                                 race_date: str) -> pd.DataFrame:
        """
        レースの全艇に対して進入予測用特徴量を生成

        Args:
            race_id: レースID
            venue_code: 会場コード
            race_date: レース日

        Returns:
            6艇分の特徴量DataFrame
        """
        # 出走表取得
        query = """
            SELECT
                e.pit_number,
                e.racer_number,
                e.racer_rank,
                e.motor_number,
                e.win_rate,
                rd.exhibition_time,
                rd.st_time
            FROM entries e
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        """

        conn = self._get_connection()
        df = pd.read_sql_query(query, conn, params=(race_id,))
        conn.close()

        if len(df) != 6:
            return pd.DataFrame()

        # 風向特徴量（全艇共通）
        wind_features = self.calculate_wind_features(venue_code, race_date)

        features_list = []

        for _, row in df.iterrows():
            features = {
                'pit_number': row['pit_number'],
                'racer_number': row['racer_number'],
                'win_rate': row['win_rate'] or 0.0,
                'exhibition_time': row['exhibition_time'] or 0.0,
                'st_time': row['st_time'] or 0.0,
            }

            # 級別スコア
            rank_map = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
            features['rank_score'] = rank_map.get(row['racer_rank'], 2)

            # 選手の進入傾向
            entry_tendency = self.calculate_entry_tendency(
                row['racer_number'], race_date
            )
            features.update(entry_tendency)

            # 進入コース別勝率
            entry_winrate = self.calculate_entry_win_rate(
                row['racer_number'], race_date
            )
            features.update(entry_winrate)

            # モーター特性
            motor_chars = self.calculate_motor_characteristics(
                row['motor_number'], venue_code, race_date
            )
            features.update(motor_chars)

            # 風向特徴量
            features.update(wind_features)

            features_list.append(features)

        return pd.DataFrame(features_list)


def create_entry_training_dataset(db_path: str,
                                   start_date: str = None,
                                   end_date: str = None) -> pd.DataFrame:
    """
    進入予測モデルの学習データセットを作成

    Args:
        db_path: DBパス
        start_date: 開始日
        end_date: 終了日

    Returns:
        学習用DataFrame
    """
    conn = sqlite3.connect(db_path)

    # 進入コースが記録されているレースを取得
    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            e.pit_number,
            e.racer_number,
            e.racer_rank,
            e.motor_number,
            e.win_rate,
            rd.exhibition_time,
            rd.st_time,
            rd.actual_course
        FROM races r
        JOIN entries e ON r.id = e.race_id
        JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
        WHERE rd.actual_course IS NOT NULL
    """

    params = []
    if start_date:
        query += " AND r.race_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND r.race_date <= ?"
        params.append(end_date)

    query += " ORDER BY r.race_date, r.id, e.pit_number"

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if len(df) == 0:
        print("進入データがありません")
        return pd.DataFrame()

    print(f"進入データ読み込み: {len(df):,}件")

    # 特徴量生成
    feature_gen = EntryFeatureGenerator(db_path)

    # レースごとに特徴量を生成（重い処理なのでバッチ化）
    all_features = []
    race_groups = df.groupby('race_id')

    processed = 0
    total = len(race_groups)

    for race_id, group in race_groups:
        if len(group) != 6:
            continue

        venue_code = group['venue_code'].iloc[0]
        race_date = group['race_date'].iloc[0]

        # 風向特徴量（全艇共通）
        wind_features = feature_gen.calculate_wind_features(venue_code, race_date)

        for _, row in group.iterrows():
            features = {
                'race_id': race_id,
                'pit_number': row['pit_number'],
                'actual_course': row['actual_course'],  # ターゲット
                'venue_code': venue_code,
                'race_date': race_date,
                'win_rate': row['win_rate'] or 0.0,
                'exhibition_time': row['exhibition_time'] or 0.0,
                'st_time': row['st_time'] or 0.0,
            }

            # 級別スコア
            rank_map = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
            features['rank_score'] = rank_map.get(row['racer_rank'], 2)

            # 選手の進入傾向
            entry_tendency = feature_gen.calculate_entry_tendency(
                row['racer_number'], race_date
            )
            features.update(entry_tendency)

            # 風向特徴量
            features.update(wind_features)

            all_features.append(features)

        processed += 1
        if processed % 1000 == 0:
            print(f"進捗: {processed}/{total} レース処理完了")

    result_df = pd.DataFrame(all_features)
    print(f"学習データセット作成完了: {len(result_df):,}件")

    return result_df
