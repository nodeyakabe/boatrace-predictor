"""
2着予測用特徴量生成
Phase 2: 1着確定後の条件付き特徴量
"""
import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class SecondPlaceFeatureGenerator:
    """
    2着予測用特徴量生成クラス

    特徴量:
    - 2着率の高い"差し屋"判定
    - インの外の艇の相対ST
    - 4カド攻めの成功率
    - 1着艇の膨れ率（外が差せるか）
    - 1着艇のコース
    - 1着艇の走法タイプ
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def calculate_sashiya_score(self, racer_number: str,
                                 target_date: str,
                                 n_races: int = 100) -> Dict[str, float]:
        """
        差し屋スコアを計算

        2着以内に入る確率が高く、差しで決まる傾向が強い選手

        Args:
            racer_number: 選手番号
            target_date: 基準日
            n_races: 参照するレース数

        Returns:
            差し屋関連特徴量
        """
        query = """
            SELECT
                res.rank,
                rd.actual_course,
                e.pit_number
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
                'second_rate': 0.0,
                'rentai_rate': 0.0,
                'sashiya_score': 0.0,
                'outside_second_rate': 0.0,
            }

        total = 0
        wins = 0
        seconds = 0
        rentai = 0
        outside_seconds = 0
        outside_total = 0

        for row in results:
            try:
                rank = int(row['rank'])
            except (ValueError, TypeError):
                continue

            total += 1
            course = row['actual_course'] or row['pit_number']

            if rank == 1:
                wins += 1
                rentai += 1
            elif rank == 2:
                seconds += 1
                rentai += 1

                # 外コース（4-6）からの2着
                if course and course >= 4:
                    outside_seconds += 1

            if course and course >= 4:
                outside_total += 1

        if total == 0:
            return {
                'second_rate': 0.0,
                'rentai_rate': 0.0,
                'sashiya_score': 0.0,
                'outside_second_rate': 0.0,
            }

        second_rate = seconds / total
        rentai_rate = rentai / total
        outside_second_rate = outside_seconds / outside_total if outside_total > 0 else 0

        # 差し屋スコア: 2着率が高く、勝率は低い（差し向き）
        win_rate = wins / total
        sashiya_score = second_rate * (1 - win_rate + 0.1)  # 勝率低いほど差し屋

        return {
            'second_rate': second_rate,
            'rentai_rate': rentai_rate,
            'sashiya_score': sashiya_score,
            'outside_second_rate': outside_second_rate,
        }

    def calculate_cado_attack_rate(self, racer_number: str,
                                    target_date: str,
                                    n_races: int = 100) -> Dict[str, float]:
        """
        4カド攻め成功率を計算

        Args:
            racer_number: 選手番号
            target_date: 基準日
            n_races: 参照するレース数

        Returns:
            カド攻め関連特徴量
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
              AND rd.actual_course = 4
            ORDER BY r.race_date DESC
            LIMIT ?
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (racer_number, target_date, n_races))
        results = cursor.fetchall()
        conn.close()

        if len(results) < 3:
            return {
                'cado_win_rate': 0.0,
                'cado_rentai_rate': 0.0,
                'cado_attack_score': 0.0,
            }

        wins = 0
        rentai = 0
        total = len(results)

        for row in results:
            try:
                rank = int(row['rank'])
                if rank == 1:
                    wins += 1
                    rentai += 1
                elif rank == 2:
                    rentai += 1
            except (ValueError, TypeError):
                continue

        return {
            'cado_win_rate': wins / total,
            'cado_rentai_rate': rentai / total,
            'cado_attack_score': (wins * 2 + rentai) / (total * 3),  # 重み付けスコア
        }

    def calculate_winner_fukure_rate(self, winner_racer_number: str,
                                      winner_course: int,
                                      target_date: str,
                                      n_races: int = 50) -> Dict[str, float]:
        """
        1着艇（勝者）の膨れ率を計算

        膨れ率が高い = 外の艇が差しやすい

        Args:
            winner_racer_number: 1着選手番号
            winner_course: 1着艇のコース
            target_date: 基準日
            n_races: 参照するレース数

        Returns:
            膨れ関連特徴量
        """
        # 同じコースで勝った時の2着艇のコースを分析
        query = """
            SELECT
                res_winner.race_id,
                res_second.pit_number as second_pit,
                rd_second.actual_course as second_course
            FROM results res_winner
            JOIN entries e_winner ON res_winner.race_id = e_winner.race_id
                AND res_winner.pit_number = e_winner.pit_number
            JOIN races r ON res_winner.race_id = r.id
            JOIN race_details rd_winner ON res_winner.race_id = rd_winner.race_id
                AND res_winner.pit_number = rd_winner.pit_number
            JOIN results res_second ON res_winner.race_id = res_second.race_id
                AND res_second.rank = '2'
            JOIN race_details rd_second ON res_second.race_id = rd_second.race_id
                AND res_second.pit_number = rd_second.pit_number
            WHERE e_winner.racer_number = ?
              AND rd_winner.actual_course = ?
              AND res_winner.rank = '1'
              AND r.race_date < ?
            ORDER BY r.race_date DESC
            LIMIT ?
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (winner_racer_number, winner_course, target_date, n_races))
        results = cursor.fetchall()
        conn.close()

        if len(results) < 3:
            return {
                'fukure_rate': 0.0,
                'sashi_allowed_rate': 0.0,
            }

        outer_seconds = 0
        total = len(results)

        for row in results:
            second_course = row['second_course']
            if second_course and second_course > winner_course:
                outer_seconds += 1

        fukure_rate = outer_seconds / total

        return {
            'fukure_rate': fukure_rate,
            'sashi_allowed_rate': fukure_rate,  # 差されやすさ
        }

    def calculate_relative_st(self, race_features: pd.DataFrame,
                               winner_idx: int) -> Dict[int, float]:
        """
        1着艇との相対ST差を計算

        Args:
            race_features: 6艇分の特徴量
            winner_idx: 1着艇のインデックス

        Returns:
            各艇の相対ST差
        """
        winner_st = race_features.iloc[winner_idx].get('st_time', 0.15) or 0.15

        relative_sts = {}
        for i, row in race_features.iterrows():
            if i == winner_idx:
                relative_sts[i] = 0.0
            else:
                st = row.get('st_time', 0.15) or 0.15
                relative_sts[i] = winner_st - st  # 正=自分が速い

        return relative_sts

    def generate_second_features(self, race_features: pd.DataFrame,
                                  winner_idx: int,
                                  winner_course: int,
                                  race_date: str) -> pd.DataFrame:
        """
        2着予測用の特徴量を生成

        Args:
            race_features: 6艇分の特徴量
            winner_idx: 1着艇のインデックス
            winner_course: 1着艇のコース
            race_date: レース日

        Returns:
            5艇分（1着除く）の2着予測用特徴量
        """
        features_list = []

        # 1着艇の情報
        winner_row = race_features.iloc[winner_idx]
        winner_racer = winner_row.get('racer_number', '')
        winner_st = winner_row.get('st_time', 0.15) or 0.15
        winner_exhibition = winner_row.get('exhibition_time', 6.8) or 6.8

        # 1着艇の膨れ率
        fukure = self.calculate_winner_fukure_rate(
            winner_racer, winner_course, race_date
        )

        for i, row in race_features.iterrows():
            if i == winner_idx:
                continue

            racer_number = row.get('racer_number', '')
            pit_number = row.get('pit_number', i + 1)
            actual_course = row.get('actual_course', pit_number)

            # 基本特徴量をコピー
            features = row.to_dict()

            # 1着艇情報
            features['winner_course'] = winner_course
            features['winner_st'] = winner_st
            features['winner_exhibition'] = winner_exhibition

            # 相対特徴量
            st = row.get('st_time', 0.15) or 0.15
            features['relative_st'] = winner_st - st
            features['st_advantage'] = 1 if st < winner_st else 0

            exhibition = row.get('exhibition_time', 6.8) or 6.8
            features['relative_exhibition'] = winner_exhibition - exhibition

            # コース関連
            features['course_diff_from_winner'] = actual_course - winner_course
            features['is_outside_winner'] = 1 if actual_course > winner_course else 0
            features['is_next_to_winner'] = 1 if abs(actual_course - winner_course) == 1 else 0

            # 差し屋スコア
            sashiya = self.calculate_sashiya_score(racer_number, race_date)
            features.update(sashiya)

            # カド攻め成功率
            if actual_course == 4:
                cado = self.calculate_cado_attack_rate(racer_number, race_date)
                features.update(cado)
            else:
                features['cado_win_rate'] = 0.0
                features['cado_rentai_rate'] = 0.0
                features['cado_attack_score'] = 0.0

            # 1着艇の膨れ率
            features.update(fukure)

            features_list.append(features)

        return pd.DataFrame(features_list)


def create_second_training_dataset(db_path: str,
                                    start_date: str = None,
                                    end_date: str = None) -> pd.DataFrame:
    """
    2着予測モデルの学習データセットを作成

    Args:
        db_path: DBパス
        start_date: 開始日
        end_date: 終了日

    Returns:
        学習用DataFrame
    """
    conn = sqlite3.connect(db_path)

    # 1着・2着が確定しているレースを取得
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

    # レースごとに処理
    feature_gen = SecondPlaceFeatureGenerator(db_path)
    all_features = []

    race_groups = df.groupby('race_id')
    processed = 0
    total = len(race_groups)

    for race_id, group in race_groups:
        if len(group) != 6:
            continue

        # 1着艇を特定
        winner_row = group[group['rank'] == '1']
        if len(winner_row) != 1:
            continue

        winner_idx = winner_row.index[0]
        winner_pit = winner_row['pit_number'].iloc[0]
        winner_course = winner_row['actual_course'].iloc[0]
        race_date = group['race_date'].iloc[0]

        # 残り5艇の特徴量を生成
        for idx, row in group.iterrows():
            if idx == winner_idx:
                continue

            features = {
                'race_id': race_id,
                'pit_number': row['pit_number'],
                'is_second': 1 if row['rank'] == '2' else 0,  # ターゲット
                'race_date': race_date,
                'win_rate': row['win_rate'] or 0.0,
                'racer_second_rate': row['racer_second_rate'] or 0.0,
                'exhibition_time': row['exhibition_time'] or 0.0,
                'st_time': row['st_time'] or 0.0,
                'actual_course': row['actual_course'] or row['pit_number'],
            }

            # 級別スコア
            rank_map = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
            features['rank_score'] = rank_map.get(row['racer_rank'], 2)

            # 1着艇との関係
            features['winner_course'] = winner_course
            features['winner_st'] = winner_row['st_time'].iloc[0] or 0.15
            features['winner_exhibition'] = winner_row['exhibition_time'].iloc[0] or 6.8

            winner_st = features['winner_st']
            my_st = features['st_time'] or 0.15
            features['relative_st'] = winner_st - my_st

            my_course = features['actual_course']
            features['course_diff_from_winner'] = my_course - winner_course
            features['is_outside_winner'] = 1 if my_course > winner_course else 0

            all_features.append(features)

        processed += 1
        if processed % 2000 == 0:
            print(f"進捗: {processed}/{total} レース")

    result_df = pd.DataFrame(all_features)
    print(f"学習データセット作成完了: {len(result_df):,}件")

    return result_df
