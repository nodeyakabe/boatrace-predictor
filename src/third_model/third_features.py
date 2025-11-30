"""
3着予測用特徴量生成
Phase 2: 1着・2着確定後の条件付き特徴量
"""
import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class ThirdPlaceFeatureGenerator:
    """
    3着予測用特徴量生成クラス

    特徴量:
    - 混戦時の余り目パターン
    - 伸び足の強弱
    - モーター伸び指数
    - 2着艇の斜行率（どこに壁ができるか）
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def calculate_third_rate_history(self, racer_number: str,
                                      target_date: str,
                                      n_races: int = 100) -> Dict[str, float]:
        """
        3着率の履歴を計算

        Args:
            racer_number: 選手番号
            target_date: 基準日
            n_races: 参照するレース数

        Returns:
            3着関連特徴量
        """
        query = """
            SELECT
                res.rank,
                rd.actual_course
            FROM results res
            JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
            JOIN races r ON res.race_id = r.id
            LEFT JOIN race_details rd ON res.race_id = rd.race_id AND res.pit_number = rd.pit_number
            WHERE e.racer_number = ?
              AND r.race_date < ?
              AND res.rank IS NOT NULL
            ORDER BY r.race_date DESC
            LIMIT ?
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (racer_number, target_date, n_races))
        results = cursor.fetchall()
        conn.close()

        if len(results) < 10:
            return {
                'third_rate': 0.0,
                'fukusho_rate': 0.0,
                'outside_third_rate': 0.0,
                'amari_tendency': 0.0,
            }

        total = 0
        thirds = 0
        fukusho = 0  # 3着以内
        outside_thirds = 0
        outside_total = 0

        for row in results:
            try:
                rank = int(row['rank'])
            except (ValueError, TypeError):
                continue

            total += 1
            course = row['actual_course']

            if rank <= 3:
                fukusho += 1
            if rank == 3:
                thirds += 1
                if course and course >= 4:
                    outside_thirds += 1

            if course and course >= 4:
                outside_total += 1

        if total == 0:
            return {
                'third_rate': 0.0,
                'fukusho_rate': 0.0,
                'outside_third_rate': 0.0,
                'amari_tendency': 0.0,
            }

        third_rate = thirds / total
        fukusho_rate = fukusho / total
        outside_third_rate = outside_thirds / outside_total if outside_total > 0 else 0

        # 余り傾向: 3着率が高く、1-2着率が低い
        top2_rate = (fukusho - thirds) / total
        amari_tendency = third_rate * (1 - top2_rate + 0.1)

        return {
            'third_rate': third_rate,
            'fukusho_rate': fukusho_rate,
            'outside_third_rate': outside_third_rate,
            'amari_tendency': amari_tendency,
        }

    def calculate_motor_stretch(self, motor_number: int,
                                 venue_code: str,
                                 target_date: str) -> Dict[str, float]:
        """
        モーターの伸び指数を計算

        Args:
            motor_number: モーター番号
            venue_code: 会場コード
            target_date: 基準日

        Returns:
            伸び関連特徴量
        """
        query = """
            SELECT
                rd.exhibition_time,
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
            LIMIT 30
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (motor_number, venue_code, target_date))
        results = cursor.fetchall()
        conn.close()

        if len(results) < 5:
            return {
                'motor_stretch_score': 0.5,
                'motor_outside_performance': 0.5,
            }

        # 展示タイムと着順から伸び性能を推定
        exhibition_times = []
        outside_wins = 0
        outside_total = 0

        for row in results:
            if row['exhibition_time']:
                exhibition_times.append(row['exhibition_time'])

            course = row['actual_course']
            rank = row['rank']

            if course and course >= 4:
                outside_total += 1
                try:
                    if int(rank) <= 3:
                        outside_wins += 1
                except (ValueError, TypeError):
                    pass

        # 伸びスコア: 展示タイムが速いほど高い
        if exhibition_times:
            avg_exhibition = np.mean(exhibition_times)
            # 6.7秒を基準として正規化
            stretch_score = max(0, (6.9 - avg_exhibition) / 0.4)
        else:
            stretch_score = 0.5

        # 外からの成績
        outside_performance = outside_wins / outside_total if outside_total > 0 else 0.5

        return {
            'motor_stretch_score': min(1.0, stretch_score),
            'motor_outside_performance': outside_performance,
        }

    def calculate_second_shakou_rate(self, second_racer_number: str,
                                      second_course: int,
                                      target_date: str) -> Dict[str, float]:
        """
        2着艇の斜行率を計算

        斜行が多い = 3着候補の進路が狭まる

        Args:
            second_racer_number: 2着選手番号
            second_course: 2着艇のコース
            target_date: 基準日

        Returns:
            斜行関連特徴量
        """
        # 2着艇が勝った時のレースを分析して斜行傾向を推定
        query = """
            SELECT
                rd_this.actual_course as this_course,
                res_this.rank as this_rank
            FROM results res_this
            JOIN entries e_this ON res_this.race_id = e_this.race_id
                AND res_this.pit_number = e_this.pit_number
            JOIN races r ON res_this.race_id = r.id
            JOIN race_details rd_this ON res_this.race_id = rd_this.race_id
                AND res_this.pit_number = rd_this.pit_number
            WHERE e_this.racer_number = ?
              AND r.race_date < ?
              AND res_this.rank IN ('1', '2')
            ORDER BY r.race_date DESC
            LIMIT 30
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (second_racer_number, target_date))
        results = cursor.fetchall()
        conn.close()

        if len(results) < 5:
            return {
                'second_shakou_tendency': 0.5,
                'wall_effect': 0.5,
            }

        # 攻め手傾向（まくり/まくり差しが多い=斜行傾向）
        aggressive_count = 0
        for row in results:
            course = row['this_course']
            rank = row['this_rank']

            # 外コースから連対 = 攻め傾向
            try:
                if course and course >= 3 and int(rank) <= 2:
                    aggressive_count += 1
            except (ValueError, TypeError):
                pass

        shakou_tendency = aggressive_count / len(results)

        # 壁効果: 斜行傾向が高いと外の艇にスペースができにくい
        wall_effect = shakou_tendency

        return {
            'second_shakou_tendency': shakou_tendency,
            'wall_effect': wall_effect,
        }

    def generate_third_features(self, race_features: pd.DataFrame,
                                 winner_idx: int,
                                 second_idx: int,
                                 winner_course: int,
                                 second_course: int,
                                 race_date: str) -> pd.DataFrame:
        """
        3着予測用の特徴量を生成

        Args:
            race_features: 6艇分の特徴量
            winner_idx: 1着艇のインデックス
            second_idx: 2着艇のインデックス
            winner_course: 1着艇のコース
            second_course: 2着艇のコース
            race_date: レース日

        Returns:
            4艇分（1着・2着除く）の3着予測用特徴量
        """
        features_list = []

        # 1着・2着艇の情報
        winner_row = race_features.iloc[winner_idx]
        second_row = race_features.iloc[second_idx]

        winner_st = winner_row.get('st_time', 0.15) or 0.15
        second_st = second_row.get('st_time', 0.15) or 0.15
        second_racer = second_row.get('racer_number', '')

        # 2着艇の斜行傾向
        shakou = self.calculate_second_shakou_rate(second_racer, second_course, race_date)

        for i, row in race_features.iterrows():
            if i == winner_idx or i == second_idx:
                continue

            racer_number = row.get('racer_number', '')
            pit_number = row.get('pit_number', i + 1)
            actual_course = row.get('actual_course', pit_number)

            # 基本特徴量
            features = row.to_dict()

            # 1着・2着艇情報
            features['winner_course'] = winner_course
            features['second_course'] = second_course
            features['winner_st'] = winner_st
            features['second_st'] = second_st

            # 相対特徴量
            my_st = row.get('st_time', 0.15) or 0.15
            features['relative_st_to_winner'] = winner_st - my_st
            features['relative_st_to_second'] = second_st - my_st

            # コース関連
            features['course_diff_from_winner'] = actual_course - winner_course
            features['course_diff_from_second'] = actual_course - second_course
            features['is_between'] = 1 if (
                min(winner_course, second_course) < actual_course < max(winner_course, second_course)
            ) else 0
            features['is_outermost'] = 1 if actual_course > max(winner_course, second_course) else 0

            # 3着履歴
            third_history = self.calculate_third_rate_history(racer_number, race_date)
            features.update(third_history)

            # 2着艇の斜行傾向
            features.update(shakou)

            # 余りスペース: 1着・2着の間にどれだけスペースがあるか
            gap = abs(winner_course - second_course)
            features['gap_space'] = gap

            features_list.append(features)

        return pd.DataFrame(features_list)


def create_third_training_dataset(db_path: str,
                                   start_date: str = None,
                                   end_date: str = None) -> pd.DataFrame:
    """
    3着予測モデルの学習データセットを作成

    Args:
        db_path: DBパス
        start_date: 開始日
        end_date: 終了日

    Returns:
        学習用DataFrame
    """
    conn = sqlite3.connect(db_path)

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
            e.second_rate as racer_second_rate,
            e.third_rate as racer_third_rate,
            rd.exhibition_time,
            rd.st_time,
            rd.actual_course,
            res.rank
        FROM races r
        JOIN entries e ON r.id = e.race_id
        JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
        JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE rd.actual_course IS NOT NULL
          AND res.rank IN ('1', '2', '3', '4', '5', '6')
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
        print("データがありません")
        return pd.DataFrame()

    print(f"データ読み込み: {len(df):,}件")

    all_features = []
    race_groups = df.groupby('race_id')
    processed = 0
    total = len(race_groups)

    for race_id, group in race_groups:
        if len(group) != 6:
            continue

        # 1着・2着艇を特定
        winner_row = group[group['rank'] == '1']
        second_row = group[group['rank'] == '2']

        if len(winner_row) != 1 or len(second_row) != 1:
            continue

        winner_idx = winner_row.index[0]
        second_idx = second_row.index[0]
        winner_course = winner_row['actual_course'].iloc[0]
        second_course = second_row['actual_course'].iloc[0]
        race_date = group['race_date'].iloc[0]

        # 残り4艇の特徴量を生成
        for idx, row in group.iterrows():
            if idx == winner_idx or idx == second_idx:
                continue

            features = {
                'race_id': race_id,
                'pit_number': row['pit_number'],
                'is_third': 1 if row['rank'] == '3' else 0,  # ターゲット
                'race_date': race_date,
                'win_rate': row['win_rate'] or 0.0,
                'racer_second_rate': row['racer_second_rate'] or 0.0,
                'racer_third_rate': row['racer_third_rate'] or 0.0,
                'exhibition_time': row['exhibition_time'] or 0.0,
                'st_time': row['st_time'] or 0.0,
                'actual_course': row['actual_course'] or row['pit_number'],
            }

            # 級別スコア
            rank_map = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
            features['rank_score'] = rank_map.get(row['racer_rank'], 2)

            # 1着・2着艇との関係
            features['winner_course'] = winner_course
            features['second_course'] = second_course
            features['winner_st'] = winner_row['st_time'].iloc[0] or 0.15
            features['second_st'] = second_row['st_time'].iloc[0] or 0.15

            my_course = features['actual_course']
            features['course_diff_from_winner'] = my_course - winner_course
            features['course_diff_from_second'] = my_course - second_course
            features['is_between'] = 1 if (
                min(winner_course, second_course) < my_course < max(winner_course, second_course)
            ) else 0

            all_features.append(features)

        processed += 1
        if processed % 2000 == 0:
            print(f"進捗: {processed}/{total} レース")

    result_df = pd.DataFrame(all_features)
    print(f"学習データセット作成完了: {len(result_df):,}件")

    return result_df
