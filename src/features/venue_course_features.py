"""
会場×コース別特徴量モジュール

Opus分析による深掘り結果を基に実装:
1. venue_course_advantage - 会場コース有利度（最大25%差）
2. recent_course_win_rate_10 - 直近10走のコース別成績
3. wind_course_factor - 風条件×コース調整係数
4. wave_course_factor - 波高×コース調整係数
5. racer_venue_course_skill - ベイズ推定による選手×会場×コース適性
"""

import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple


class VenueCourseFeatureExtractor:
    """会場×コース別特徴量抽出クラス"""

    # 会場×コース別の事前計算された有利度（全国平均との差）
    # データから計算した静的値（定期的に更新推奨）
    VENUE_COURSE_ADVANTAGE = {
        # venue_code: {course: advantage}
        # 正の値 = 全国平均より有利、負の値 = 不利
        '01': {1: 0.02, 2: -0.01, 3: 0.00, 4: 0.01, 5: -0.01, 6: -0.01},  # 桐生
        '02': {1: -0.12, 2: 0.03, 3: 0.02, 4: 0.03, 5: 0.02, 6: 0.02},   # 戸田（イン弱い）
        '03': {1: -0.13, 2: 0.04, 3: 0.03, 4: 0.03, 5: 0.02, 6: 0.01},   # 江戸川（最も荒れる）
        '04': {1: -0.05, 2: 0.02, 3: 0.01, 4: 0.01, 5: 0.00, 6: 0.01},   # 平和島
        '05': {1: 0.03, 2: -0.01, 3: -0.01, 4: 0.00, 5: -0.01, 6: 0.00}, # 多摩川
        '06': {1: 0.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.00, 6: 0.00},    # 浜名湖
        '07': {1: 0.02, 2: -0.01, 3: 0.00, 4: 0.00, 5: -0.01, 6: 0.00},  # 蒲郡
        '08': {1: 0.06, 2: -0.02, 3: -0.01, 4: -0.01, 5: -0.01, 6: -0.01}, # 常滑
        '09': {1: 0.03, 2: -0.01, 3: 0.00, 4: -0.01, 5: -0.01, 6: 0.00}, # 津
        '10': {1: 0.01, 2: 0.00, 3: 0.00, 4: 0.00, 5: -0.01, 6: 0.00},   # 三国
        '11': {1: 0.02, 2: -0.01, 3: 0.00, 4: 0.00, 5: -0.01, 6: 0.00},  # びわこ
        '12': {1: 0.04, 2: -0.01, 3: -0.01, 4: -0.01, 5: -0.01, 6: 0.00}, # 住之江
        '13': {1: 0.01, 2: 0.00, 3: 0.00, 4: 0.00, 5: -0.01, 6: 0.00},   # 尼崎
        '14': {1: -0.02, 2: 0.01, 3: 0.00, 4: 0.00, 5: 0.00, 6: 0.01},   # 鳴門
        '15': {1: 0.03, 2: -0.01, 3: 0.00, 4: -0.01, 5: -0.01, 6: 0.00}, # 丸亀
        '16': {1: 0.02, 2: -0.01, 3: 0.00, 4: 0.00, 5: -0.01, 6: 0.00},  # 児島
        '17': {1: 0.05, 2: -0.01, 3: -0.01, 4: -0.01, 5: -0.01, 6: -0.01}, # 宮島
        '18': {1: 0.10, 2: -0.03, 3: -0.02, 4: -0.02, 5: -0.02, 6: -0.01}, # 徳山（最もイン強い）
        '19': {1: 0.06, 2: -0.02, 3: -0.01, 4: -0.01, 5: -0.01, 6: -0.01}, # 下関
        '20': {1: 0.01, 2: 0.00, 3: 0.00, 4: 0.00, 5: -0.01, 6: 0.00},   # 若松
        '21': {1: 0.03, 2: -0.01, 3: 0.00, 4: -0.01, 5: -0.01, 6: 0.00}, # 芦屋
        '22': {1: 0.02, 2: -0.01, 3: 0.00, 4: 0.00, 5: -0.01, 6: 0.00},  # 福岡
        '23': {1: 0.04, 2: -0.01, 3: -0.01, 4: -0.01, 5: -0.01, 6: 0.00}, # 唐津
        '24': {1: 0.09, 2: -0.02, 3: -0.02, 4: -0.02, 5: -0.02, 6: -0.01}, # 大村（イン強い）
    }

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path

    def get_venue_course_advantage(self, venue_code: str, course: int) -> float:
        """
        会場×コースの有利度を取得（静的テーブルから）

        Args:
            venue_code: 会場コード
            course: コース番号（1-6）

        Returns:
            float: 有利度（正=有利、負=不利）
        """
        venue_data = self.VENUE_COURSE_ADVANTAGE.get(venue_code, {})
        return venue_data.get(course, 0.0)

    def compute_venue_course_stats_from_db(
        self,
        venue_code: str,
        course: int,
        conn: Optional[sqlite3.Connection] = None
    ) -> Dict[str, float]:
        """
        データベースから会場×コースの統計を計算（動的）

        Args:
            venue_code: 会場コード
            course: コース番号
            conn: DBコネクション

        Returns:
            dict: {win_rate, 2ren_rate, sample_count}
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            query = """
            SELECT
                COUNT(*) as sample_count,
                AVG(CASE WHEN r.rank = '1' THEN 1.0 ELSE 0.0 END) as win_rate,
                AVG(CASE WHEN r.rank IN ('1', '2') THEN 1.0 ELSE 0.0 END) as rate_2ren
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            WHERE ra.venue_code = ?
              AND rd.actual_course = ?
              AND r.rank NOT IN ('F', 'L', 'K', '')
              AND r.rank IS NOT NULL
            """

            cursor = conn.cursor()
            cursor.execute(query, (venue_code, course))
            row = cursor.fetchone()

            if row and row[0] > 0:
                return {
                    'venue_course_win_rate': row[1],
                    'venue_course_2ren_rate': row[2],
                    'venue_course_sample': row[0]
                }
            else:
                return {
                    'venue_course_win_rate': 0.17,
                    'venue_course_2ren_rate': 0.33,
                    'venue_course_sample': 0
                }

        finally:
            if close_conn:
                conn.close()

    def compute_recent_course_performance(
        self,
        racer_number: str,
        target_course: int,
        race_date: str,
        n_races: int = 10,
        conn: Optional[sqlite3.Connection] = None
    ) -> Dict[str, float]:
        """
        選手の直近N走のコース別成績を計算

        Args:
            racer_number: 選手登録番号
            target_course: 対象コース（1-6）
            race_date: 対象レース日
            n_races: 直近何走を見るか
            conn: DBコネクション

        Returns:
            dict: {recent_course_win_rate, recent_course_2ren_rate, recent_course_avg_rank, sample}
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            query = """
            SELECT r.rank
            FROM results r
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            JOIN races ra ON r.race_id = ra.id
            WHERE e.racer_number = ?
              AND rd.actual_course = ?
              AND ra.race_date < ?
              AND r.rank NOT IN ('F', 'L', 'K', '')
              AND r.rank IS NOT NULL
            ORDER BY ra.race_date DESC, ra.race_number DESC
            LIMIT ?
            """

            df = pd.read_sql_query(query, conn, params=(racer_number, target_course, race_date, n_races))

            if len(df) == 0:
                # デフォルト値（コース別の平均的な成績）
                default_rates = {
                    1: {'win': 0.55, '2ren': 0.70, 'avg': 2.0},
                    2: {'win': 0.14, '2ren': 0.35, 'avg': 3.2},
                    3: {'win': 0.12, '2ren': 0.30, 'avg': 3.4},
                    4: {'win': 0.11, '2ren': 0.28, 'avg': 3.5},
                    5: {'win': 0.06, '2ren': 0.18, 'avg': 3.9},
                    6: {'win': 0.04, '2ren': 0.12, 'avg': 4.2}
                }
                d = default_rates.get(target_course, default_rates[3])
                return {
                    'recent_course_win_rate': d['win'],
                    'recent_course_2ren_rate': d['2ren'],
                    'recent_course_avg_rank': d['avg'],
                    'recent_course_sample': 0
                }

            # 着順を数値に変換
            ranks = []
            for rank_str in df['rank']:
                try:
                    rank_num = int(rank_str)
                    if 1 <= rank_num <= 6:
                        ranks.append(rank_num)
                    else:
                        ranks.append(6)
                except (ValueError, TypeError):
                    ranks.append(6)

            if len(ranks) == 0:
                return {
                    'recent_course_win_rate': 0.17,
                    'recent_course_2ren_rate': 0.33,
                    'recent_course_avg_rank': 3.5,
                    'recent_course_sample': 0
                }

            count = len(ranks)
            return {
                'recent_course_win_rate': sum(1 for r in ranks if r == 1) / count,
                'recent_course_2ren_rate': sum(1 for r in ranks if r <= 2) / count,
                'recent_course_avg_rank': np.mean(ranks),
                'recent_course_sample': count
            }

        finally:
            if close_conn:
                conn.close()

    def compute_condition_course_factor(
        self,
        wind_speed: Optional[float],
        wave_height: Optional[float],
        course: int
    ) -> Dict[str, float]:
        """
        風・波条件によるコース調整係数を計算

        データ分析結果:
        - 強風(5m+): 1コース勝率 -5.8%
        - 荒水(6cm+): 1コース勝率 -9.8%

        Args:
            wind_speed: 風速（m）
            wave_height: 波高（cm）
            course: コース番号（1-6）

        Returns:
            dict: {wind_course_factor, wave_course_factor, condition_course_factor}
        """
        # 風の影響
        if wind_speed is None:
            wind_factor = 0.0
        elif wind_speed <= 2:
            # 弱風時はイン有利
            wind_factors = {1: 0.02, 2: -0.01, 3: -0.01, 4: 0.00, 5: 0.00, 6: 0.00}
            wind_factor = wind_factors.get(course, 0.0)
        elif wind_speed <= 4:
            # 中風は基準
            wind_factor = 0.0
        else:
            # 強風(5m+)はイン不利
            wind_factors = {1: -0.06, 2: 0.03, 3: 0.02, 4: 0.01, 5: 0.00, 6: 0.00}
            wind_factor = wind_factors.get(course, 0.0)

        # 波の影響
        if wave_height is None:
            wave_factor = 0.0
        elif wave_height <= 2:
            # 静水時はイン有利
            wave_factors = {1: 0.02, 2: -0.01, 3: 0.00, 4: 0.00, 5: -0.01, 6: 0.00}
            wave_factor = wave_factors.get(course, 0.0)
        elif wave_height <= 5:
            # 中波
            wave_factors = {1: -0.04, 2: 0.01, 3: 0.01, 4: 0.01, 5: 0.01, 6: 0.00}
            wave_factor = wave_factors.get(course, 0.0)
        else:
            # 荒水(6cm+)はイン大幅不利
            wave_factors = {1: -0.10, 2: 0.04, 3: 0.02, 4: 0.02, 5: 0.01, 6: 0.01}
            wave_factor = wave_factors.get(course, 0.0)

        return {
            'wind_course_factor': wind_factor,
            'wave_course_factor': wave_factor,
            'condition_course_factor': wind_factor + wave_factor
        }

    def compute_racer_venue_course_skill(
        self,
        racer_number: str,
        venue_code: str,
        target_course: int,
        race_date: str,
        conn: Optional[sqlite3.Connection] = None
    ) -> Dict[str, float]:
        """
        ベイズ推定による選手×会場×コース適性スコア

        サンプルが少ない場合は全国コース成績を重視し、
        サンプルが多い場合は会場×コース成績を重視する

        Args:
            racer_number: 選手登録番号
            venue_code: 会場コード
            target_course: 対象コース
            race_date: 対象レース日
            conn: DBコネクション

        Returns:
            dict: {racer_venue_skill, racer_course_skill, racer_venue_course_skill}
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            # 1. 選手の会場別成績
            query_venue = """
            SELECT
                COUNT(*) as races,
                AVG(CASE WHEN r.rank = '1' THEN 1.0 ELSE 0.0 END) as win_rate
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND ra.venue_code = ?
              AND ra.race_date < ?
              AND r.rank NOT IN ('F', 'L', 'K', '')
              AND r.rank IS NOT NULL
            """

            cursor = conn.cursor()
            cursor.execute(query_venue, (racer_number, venue_code, race_date))
            venue_row = cursor.fetchone()

            venue_races = venue_row[0] if venue_row else 0
            venue_win_rate = venue_row[1] if venue_row and venue_row[1] else 0.17

            # 2. 選手の全国コース別成績
            query_course = """
            SELECT
                COUNT(*) as races,
                AVG(CASE WHEN r.rank = '1' THEN 1.0 ELSE 0.0 END) as win_rate
            FROM results r
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            JOIN races ra ON r.race_id = ra.id
            WHERE e.racer_number = ?
              AND rd.actual_course = ?
              AND ra.race_date < ?
              AND r.rank NOT IN ('F', 'L', 'K', '')
              AND r.rank IS NOT NULL
            """

            cursor.execute(query_course, (racer_number, target_course, race_date))
            course_row = cursor.fetchone()

            course_races = course_row[0] if course_row else 0
            course_win_rate = course_row[1] if course_row and course_row[1] else 0.17

            # 3. 選手の会場×コース成績
            query_venue_course = """
            SELECT
                COUNT(*) as races,
                AVG(CASE WHEN r.rank = '1' THEN 1.0 ELSE 0.0 END) as win_rate
            FROM results r
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            JOIN races ra ON r.race_id = ra.id
            WHERE e.racer_number = ?
              AND ra.venue_code = ?
              AND rd.actual_course = ?
              AND ra.race_date < ?
              AND r.rank NOT IN ('F', 'L', 'K', '')
              AND r.rank IS NOT NULL
            """

            cursor.execute(query_venue_course, (racer_number, venue_code, target_course, race_date))
            vc_row = cursor.fetchone()

            vc_races = vc_row[0] if vc_row else 0
            vc_win_rate = vc_row[1] if vc_row and vc_row[1] else 0.17

            # 4. ベイズ推定でスムージング
            # 事前分布: コース別の全国平均
            prior_rates = {1: 0.55, 2: 0.14, 3: 0.12, 4: 0.11, 5: 0.06, 6: 0.04}
            prior = prior_rates.get(target_course, 0.17)
            prior_strength = 10  # 事前分布の強さ（仮想サンプル数）

            # 会場成績のベイズ推定
            venue_skill = (venue_races * venue_win_rate + prior_strength * prior) / (venue_races + prior_strength)

            # コース成績のベイズ推定
            course_skill = (course_races * course_win_rate + prior_strength * prior) / (course_races + prior_strength)

            # 会場×コース成績のベイズ推定（サンプル少ないのでより保守的に）
            vc_prior_strength = 20
            venue_course_skill = (vc_races * vc_win_rate + vc_prior_strength * prior) / (vc_races + vc_prior_strength)

            # 5. 統合スコア（加重平均）
            # サンプル数に応じて重みを調整
            total_weight = 0
            weighted_sum = 0

            # コース成績（基本重視）
            course_weight = min(course_races / 30, 1.0) * 0.5
            weighted_sum += course_skill * course_weight
            total_weight += course_weight

            # 会場成績
            venue_weight = min(venue_races / 20, 1.0) * 0.3
            weighted_sum += venue_skill * venue_weight
            total_weight += venue_weight

            # 会場×コース成績（サンプルが十分な場合のみ）
            if vc_races >= 5:
                vc_weight = min(vc_races / 10, 1.0) * 0.4
                weighted_sum += venue_course_skill * vc_weight
                total_weight += vc_weight

            if total_weight > 0:
                combined_skill = weighted_sum / total_weight
            else:
                combined_skill = prior

            return {
                'racer_venue_skill': venue_skill,
                'racer_course_skill': course_skill,
                'racer_venue_course_skill': venue_course_skill,
                'racer_venue_course_combined': combined_skill,
                'venue_sample': venue_races,
                'course_sample': course_races,
                'venue_course_sample': vc_races
            }

        finally:
            if close_conn:
                conn.close()

    def extract_all_features(
        self,
        racer_number: str,
        venue_code: str,
        target_course: int,
        race_date: str,
        race_number: int = 1,
        wind_speed: Optional[float] = None,
        wave_height: Optional[float] = None,
        conn: Optional[sqlite3.Connection] = None
    ) -> Dict[str, float]:
        """
        全ての会場×コース特徴量を一括抽出

        Args:
            racer_number: 選手登録番号
            venue_code: 会場コード
            target_course: 対象コース
            race_date: レース日
            race_number: レース番号
            wind_speed: 風速
            wave_height: 波高
            conn: DBコネクション

        Returns:
            dict: 全特徴量
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            features = {}

            # 1. 会場×コース有利度（静的）
            features['venue_course_advantage'] = self.get_venue_course_advantage(venue_code, target_course)

            # 2. 直近10走のコース別成績
            recent = self.compute_recent_course_performance(
                racer_number, target_course, race_date, n_races=10, conn=conn
            )
            features['recent_course_win_rate'] = recent['recent_course_win_rate']
            features['recent_course_2ren_rate'] = recent['recent_course_2ren_rate']
            features['recent_course_avg_rank'] = recent['recent_course_avg_rank']

            # 3. 条件×コース調整係数
            condition = self.compute_condition_course_factor(wind_speed, wave_height, target_course)
            features['wind_course_factor'] = condition['wind_course_factor']
            features['wave_course_factor'] = condition['wave_course_factor']
            features['condition_course_factor'] = condition['condition_course_factor']

            # 4. ベイズ推定による選手×会場×コース適性
            skill = self.compute_racer_venue_course_skill(
                racer_number, venue_code, target_course, race_date, conn=conn
            )
            features['racer_venue_skill'] = skill['racer_venue_skill']
            features['racer_course_skill'] = skill['racer_course_skill']
            features['racer_venue_course_skill'] = skill['racer_venue_course_skill']
            features['racer_venue_course_combined'] = skill['racer_venue_course_combined']

            return features

        finally:
            if close_conn:
                conn.close()


def extract_venue_course_features(
    racer_number: str,
    venue_code: str,
    target_course: int,
    race_date: str,
    wind_speed: Optional[float] = None,
    wave_height: Optional[float] = None,
    db_path: str = 'data/boatrace.db'
) -> Dict[str, float]:
    """
    会場×コース特徴量を抽出（関数形式）
    """
    extractor = VenueCourseFeatureExtractor(db_path)
    return extractor.extract_all_features(
        racer_number, venue_code, target_course, race_date,
        wind_speed=wind_speed, wave_height=wave_height
    )


if __name__ == "__main__":
    # テスト実行
    print("=" * 70)
    print("会場×コース特徴量テスト")
    print("=" * 70)

    extractor = VenueCourseFeatureExtractor()

    # テストケース1: 戸田（イン弱い）の1コース
    print("\n【テスト1: 戸田 1コース】")
    features1 = extractor.extract_all_features(
        racer_number='4444',  # 峰竜太
        venue_code='02',      # 戸田
        target_course=1,
        race_date='2025-12-06',
        wind_speed=3,
        wave_height=2
    )
    for k, v in sorted(features1.items()):
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    # テストケース2: 大村（イン強い）の1コース
    print("\n【テスト2: 大村 1コース】")
    features2 = extractor.extract_all_features(
        racer_number='4444',
        venue_code='24',      # 大村
        target_course=1,
        race_date='2025-12-06',
        wind_speed=1,
        wave_height=1
    )
    for k, v in sorted(features2.items()):
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    # テストケース3: 荒れ条件
    print("\n【テスト3: 戸田 1コース（荒れ条件）】")
    features3 = extractor.extract_all_features(
        racer_number='4444',
        venue_code='02',
        target_course=1,
        race_date='2025-12-06',
        wind_speed=6,   # 強風
        wave_height=8   # 荒水
    )
    for k, v in sorted(features3.items()):
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")
