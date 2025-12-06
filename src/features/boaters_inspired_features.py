"""
ボーターズ分析を参考にした新規特徴量モジュール

ボーターズで使用されていて本プロジェクトで未活用だった指標:
1. モーター順位（会場内ランキング）
2. モーター展示タイム平均
3. 今節成績（コース別着順）
4. コース別連対率
5. 予測ST（過去STからの推定）
6. モーター優出回数/優勝数

公式サイトから取得可能なデータを元に計算
"""

import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta


class BoatersInspiredFeatureExtractor:
    """ボーターズ分析を参考にした特徴量抽出クラス"""

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path

    def compute_motor_venue_rank(
        self,
        motor_number: int,
        venue_code: str,
        race_date: str,
        conn: Optional[sqlite3.Connection] = None
    ) -> Tuple[int, float]:
        """
        会場内でのモーターランキングを計算

        Args:
            motor_number: モーター番号
            venue_code: 会場コード
            race_date: 対象レース日（この日より前のデータを使用）
            conn: DBコネクション

        Returns:
            (順位, 2連率) - 順位は1が最高、データなしの場合は(40, 0.3)
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            # 過去90日間のモーター成績を集計
            query = """
            WITH motor_stats AS (
                SELECT
                    e.motor_number,
                    COUNT(*) as race_count,
                    SUM(CASE WHEN r.rank IN ('1', '2') THEN 1.0 ELSE 0.0 END) / COUNT(*) as rate_2ren
                FROM entries e
                JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
                JOIN races rc ON e.race_id = rc.id
                WHERE rc.venue_code = ?
                    AND rc.race_date >= date(?, '-90 days')
                    AND rc.race_date < ?
                    AND e.motor_number IS NOT NULL
                    AND r.rank IS NOT NULL
                    AND r.rank != ''
                GROUP BY e.motor_number
                HAVING race_count >= 10
            ),
            ranked AS (
                SELECT
                    motor_number,
                    rate_2ren,
                    RANK() OVER (ORDER BY rate_2ren DESC) as motor_rank,
                    COUNT(*) OVER () as total_motors
                FROM motor_stats
            )
            SELECT motor_rank, rate_2ren, total_motors
            FROM ranked
            WHERE motor_number = ?
            """

            cursor = conn.cursor()
            cursor.execute(query, (venue_code, race_date, race_date, motor_number))
            row = cursor.fetchone()

            if row:
                return (row[0], row[1])
            else:
                return (40, 0.3)  # デフォルト（中位）

        finally:
            if close_conn:
                conn.close()

    def compute_motor_exhibition_avg(
        self,
        motor_number: int,
        venue_code: str,
        race_date: str,
        conn: Optional[sqlite3.Connection] = None
    ) -> Tuple[float, float]:
        """
        モーターの平均展示タイムと順位を計算

        Args:
            motor_number: モーター番号
            venue_code: 会場コード
            race_date: 対象レース日
            conn: DBコネクション

        Returns:
            (平均展示タイム, 会場平均との差) - データなしの場合は(6.80, 0.0)
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            query = """
            WITH motor_tenji AS (
                SELECT
                    e.motor_number,
                    AVG(rd.exhibition_time) as avg_tenji,
                    COUNT(*) as cnt
                FROM entries e
                JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                JOIN races rc ON e.race_id = rc.id
                WHERE rc.venue_code = ?
                    AND rc.race_date >= date(?, '-60 days')
                    AND rc.race_date < ?
                    AND rd.exhibition_time IS NOT NULL
                    AND rd.exhibition_time BETWEEN 6.0 AND 8.0
                GROUP BY e.motor_number
                HAVING cnt >= 5
            ),
            venue_avg AS (
                SELECT AVG(avg_tenji) as venue_tenji_avg
                FROM motor_tenji
            )
            SELECT
                mt.avg_tenji,
                mt.avg_tenji - va.venue_tenji_avg as diff_from_avg
            FROM motor_tenji mt, venue_avg va
            WHERE mt.motor_number = ?
            """

            cursor = conn.cursor()
            cursor.execute(query, (venue_code, race_date, race_date, motor_number))
            row = cursor.fetchone()

            if row and row[0]:
                return (row[0], row[1] if row[1] else 0.0)
            else:
                return (6.80, 0.0)

        finally:
            if close_conn:
                conn.close()

    def compute_current_node_performance(
        self,
        racer_number: str,
        venue_code: str,
        race_date: str,
        race_number: int,
        conn: Optional[sqlite3.Connection] = None
    ) -> Dict[str, float]:
        """
        今節成績を計算（現在のレースより前の節内成績）

        Args:
            racer_number: 選手登録番号
            venue_code: 会場コード
            race_date: 対象レース日
            race_number: レース番号（これより前のレースを参照）
            conn: DBコネクション

        Returns:
            {
                'node_race_count': int,      # 今節出走数
                'node_avg_rank': float,      # 今節平均着順
                'node_win_rate': float,      # 今節勝率
                'node_2ren_rate': float,     # 今節2連率
                'node_3ren_rate': float,     # 今節3連率
                'node_trend': float          # 調子トレンド（直近の着順変化）
            }
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            # 節の開始日を推定（通常4-7日間）
            # 同一会場で連続するレースを節とみなす
            query = """
            WITH node_races AS (
                SELECT
                    rc.race_date,
                    rc.race_number,
                    r.rank
                FROM races rc
                JOIN entries e ON rc.id = e.race_id
                JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
                WHERE e.racer_number = ?
                    AND rc.venue_code = ?
                    AND rc.race_date >= date(?, '-7 days')
                    AND (rc.race_date < ? OR (rc.race_date = ? AND rc.race_number < ?))
                    AND r.rank IS NOT NULL
                    AND r.rank != ''
                ORDER BY rc.race_date DESC, rc.race_number DESC
            )
            SELECT rank FROM node_races
            """

            df = pd.read_sql_query(
                query, conn,
                params=(racer_number, venue_code, race_date, race_date, race_date, race_number)
            )

            if len(df) == 0:
                return {
                    'node_race_count': 0,
                    'node_avg_rank': 3.5,
                    'node_win_rate': 0.0,
                    'node_2ren_rate': 0.0,
                    'node_3ren_rate': 0.0,
                    'node_trend': 0.0
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
                    'node_race_count': 0,
                    'node_avg_rank': 3.5,
                    'node_win_rate': 0.0,
                    'node_2ren_rate': 0.0,
                    'node_3ren_rate': 0.0,
                    'node_trend': 0.0
                }

            # 統計計算
            node_count = len(ranks)
            avg_rank = np.mean(ranks)
            win_rate = sum(1 for r in ranks if r == 1) / node_count
            rate_2ren = sum(1 for r in ranks if r <= 2) / node_count
            rate_3ren = sum(1 for r in ranks if r <= 3) / node_count

            # トレンド計算（最近のレースほど重み大）
            # 正の値 = 調子上昇、負の値 = 調子下降
            if node_count >= 2:
                weights = np.linspace(1, 2, node_count)
                weighted_avg_recent = np.average(ranks[:min(3, node_count)], weights=weights[:min(3, node_count)])
                weighted_avg_older = np.average(ranks, weights=weights)
                trend = weighted_avg_older - weighted_avg_recent  # 正なら調子上昇
            else:
                trend = 0.0

            return {
                'node_race_count': node_count,
                'node_avg_rank': avg_rank,
                'node_win_rate': win_rate,
                'node_2ren_rate': rate_2ren,
                'node_3ren_rate': rate_3ren,
                'node_trend': trend
            }

        finally:
            if close_conn:
                conn.close()

    def compute_course_specific_rate(
        self,
        racer_number: str,
        target_course: int,
        race_date: str,
        n_races: int = 30,
        conn: Optional[sqlite3.Connection] = None
    ) -> Dict[str, float]:
        """
        コース別成績を計算

        Args:
            racer_number: 選手登録番号
            target_course: 対象コース（1-6）
            race_date: 対象レース日
            n_races: 参照するレース数
            conn: DBコネクション

        Returns:
            {
                'course_race_count': int,    # 該当コースでの出走数
                'course_win_rate': float,    # コース別勝率
                'course_2ren_rate': float,   # コース別2連率
                'course_3ren_rate': float,   # コース別3連率
                'course_avg_rank': float     # コース別平均着順
            }
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
            JOIN races rc ON r.race_id = rc.id
            WHERE e.racer_number = ?
                AND rd.actual_course = ?
                AND rc.race_date < ?
                AND r.rank IS NOT NULL
                AND r.rank != ''
            ORDER BY rc.race_date DESC, rc.race_number DESC
            LIMIT ?
            """

            df = pd.read_sql_query(
                query, conn,
                params=(racer_number, target_course, race_date, n_races)
            )

            if len(df) == 0:
                # デフォルト値（コース別の平均的な成績）
                default_rates = {
                    1: {'win': 0.55, '2ren': 0.70, '3ren': 0.80, 'avg': 2.0},
                    2: {'win': 0.14, '2ren': 0.35, '3ren': 0.55, 'avg': 3.2},
                    3: {'win': 0.12, '2ren': 0.30, '3ren': 0.50, 'avg': 3.4},
                    4: {'win': 0.11, '2ren': 0.28, '3ren': 0.48, 'avg': 3.5},
                    5: {'win': 0.06, '2ren': 0.18, '3ren': 0.38, 'avg': 3.9},
                    6: {'win': 0.04, '2ren': 0.12, '3ren': 0.30, 'avg': 4.2}
                }
                d = default_rates.get(target_course, default_rates[1])
                return {
                    'course_race_count': 0,
                    'course_win_rate': d['win'],
                    'course_2ren_rate': d['2ren'],
                    'course_3ren_rate': d['3ren'],
                    'course_avg_rank': d['avg']
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
                    'course_race_count': 0,
                    'course_win_rate': 0.0,
                    'course_2ren_rate': 0.0,
                    'course_3ren_rate': 0.0,
                    'course_avg_rank': 3.5
                }

            count = len(ranks)
            return {
                'course_race_count': count,
                'course_win_rate': sum(1 for r in ranks if r == 1) / count,
                'course_2ren_rate': sum(1 for r in ranks if r <= 2) / count,
                'course_3ren_rate': sum(1 for r in ranks if r <= 3) / count,
                'course_avg_rank': np.mean(ranks)
            }

        finally:
            if close_conn:
                conn.close()

    def compute_predicted_st(
        self,
        racer_number: str,
        race_date: str,
        n_races: int = 20,
        conn: Optional[sqlite3.Connection] = None
    ) -> Tuple[float, float]:
        """
        予測STを計算（過去のSTから推定）

        Args:
            racer_number: 選手登録番号
            race_date: 対象レース日
            n_races: 参照するレース数
            conn: DBコネクション

        Returns:
            (予測ST, STの安定性（標準偏差）) - データなしの場合は(0.15, 0.05)
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            query = """
            SELECT rd.st_time
            FROM race_details rd
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            JOIN races rc ON rd.race_id = rc.id
            WHERE e.racer_number = ?
                AND rc.race_date < ?
                AND rd.st_time IS NOT NULL
                AND rd.st_time BETWEEN 0.0 AND 0.5
            ORDER BY rc.race_date DESC, rc.race_number DESC
            LIMIT ?
            """

            df = pd.read_sql_query(query, conn, params=(racer_number, race_date, n_races))

            if len(df) == 0:
                return (0.15, 0.05)

            st_times = df['st_time'].values

            # 指数移動平均で直近のSTをより重視
            weights = np.exp(-np.arange(len(st_times)) * 0.1)
            weights = weights / weights.sum()
            predicted_st = np.average(st_times, weights=weights)

            # 安定性（標準偏差）
            st_std = np.std(st_times) if len(st_times) > 1 else 0.05

            return (predicted_st, st_std)

        finally:
            if close_conn:
                conn.close()

    def compute_motor_grade_performance(
        self,
        motor_number: int,
        venue_code: str,
        race_date: str,
        conn: Optional[sqlite3.Connection] = None
    ) -> Dict[str, float]:
        """
        モーターのグレード別成績（優出回数、優勝数）

        Args:
            motor_number: モーター番号
            venue_code: 会場コード
            race_date: 対象レース日
            conn: DBコネクション

        Returns:
            {
                'motor_yushutsu_count': int,  # 優出回数（11R/12Rで1-2着）
                'motor_yusho_count': int,     # 優勝回数（12Rで1着）
                'motor_sg_g1_rate': float     # SG/G1での2連率
            }
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            # 優出・優勝カウント
            query = """
            SELECT
                SUM(CASE
                    WHEN rc.race_number IN (11, 12) AND r.rank IN ('1', '2')
                    THEN 1 ELSE 0
                END) as yushutsu_count,
                SUM(CASE
                    WHEN rc.race_number = 12 AND r.rank = '1'
                    THEN 1 ELSE 0
                END) as yusho_count
            FROM entries e
            JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
            JOIN races rc ON e.race_id = rc.id
            WHERE e.motor_number = ?
                AND rc.venue_code = ?
                AND rc.race_date >= date(?, '-180 days')
                AND rc.race_date < ?
            """

            cursor = conn.cursor()
            cursor.execute(query, (motor_number, venue_code, race_date, race_date))
            row = cursor.fetchone()

            yushutsu = row[0] if row and row[0] else 0
            yusho = row[1] if row and row[1] else 0

            # SG/G1での成績
            query2 = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN r.rank IN ('1', '2') THEN 1.0 ELSE 0.0 END) as wins
            FROM entries e
            JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
            JOIN races rc ON e.race_id = rc.id
            WHERE e.motor_number = ?
                AND rc.venue_code = ?
                AND rc.race_date >= date(?, '-365 days')
                AND rc.race_date < ?
                AND rc.grade IN ('SG', 'G1', 'G2')
            """

            cursor.execute(query2, (motor_number, venue_code, race_date, race_date))
            row2 = cursor.fetchone()

            if row2 and row2[0] and row2[0] > 0:
                sg_g1_rate = row2[1] / row2[0]
            else:
                sg_g1_rate = 0.3  # デフォルト

            return {
                'motor_yushutsu_count': yushutsu,
                'motor_yusho_count': yusho,
                'motor_sg_g1_rate': sg_g1_rate
            }

        finally:
            if close_conn:
                conn.close()

    def compute_flying_tendency(
        self,
        racer_number: str,
        race_date: str,
        n_races: int = 50,
        conn: Optional[sqlite3.Connection] = None
    ) -> Dict[str, float]:
        """
        フライング傾向を計算

        Args:
            racer_number: 選手登録番号
            race_date: 対象レース日
            n_races: 参照するレース数
            conn: DBコネクション

        Returns:
            {
                'early_st_rate': float,     # 0.10秒以下のST率
                'late_st_rate': float,      # 0.20秒以上のST率
                'st_variance': float,       # STのばらつき
                'aggressive_index': float   # 攻め度（低STと高STの比率）
            }
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            query = """
            SELECT rd.st_time
            FROM race_details rd
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            JOIN races rc ON rd.race_id = rc.id
            WHERE e.racer_number = ?
                AND rc.race_date < ?
                AND rd.st_time IS NOT NULL
                AND rd.st_time BETWEEN -0.1 AND 0.5
            ORDER BY rc.race_date DESC
            LIMIT ?
            """

            df = pd.read_sql_query(query, conn, params=(racer_number, race_date, n_races))

            if len(df) < 5:
                return {
                    'early_st_rate': 0.0,
                    'late_st_rate': 0.0,
                    'st_variance': 0.05,
                    'aggressive_index': 0.0
                }

            st_times = df['st_time'].values
            count = len(st_times)

            early_rate = sum(1 for st in st_times if st <= 0.10) / count
            late_rate = sum(1 for st in st_times if st >= 0.20) / count
            variance = np.var(st_times)

            # 攻め度（早いST率 - 遅いST率）
            aggressive = early_rate - late_rate

            return {
                'early_st_rate': early_rate,
                'late_st_rate': late_rate,
                'st_variance': variance,
                'aggressive_index': aggressive
            }

        finally:
            if close_conn:
                conn.close()

    def extract_all_features(
        self,
        racer_number: str,
        motor_number: int,
        venue_code: str,
        race_date: str,
        race_number: int,
        target_course: int = None,
        conn: Optional[sqlite3.Connection] = None
    ) -> Dict[str, float]:
        """
        全ての新規特徴量を一括抽出

        Args:
            racer_number: 選手登録番号
            motor_number: モーター番号
            venue_code: 会場コード
            race_date: レース日
            race_number: レース番号
            target_course: 予測進入コース（Noneの場合は枠番を使用）
            conn: DBコネクション

        Returns:
            特徴量辞書
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True

        try:
            features = {}

            # 1. モーター順位
            motor_rank, motor_2ren = self.compute_motor_venue_rank(
                motor_number, venue_code, race_date, conn
            )
            features['motor_venue_rank'] = motor_rank
            features['motor_venue_2ren'] = motor_2ren

            # 2. モーター展示タイム平均
            motor_tenji_avg, motor_tenji_diff = self.compute_motor_exhibition_avg(
                motor_number, venue_code, race_date, conn
            )
            features['motor_tenji_avg'] = motor_tenji_avg
            features['motor_tenji_diff_from_venue'] = motor_tenji_diff

            # 3. 今節成績
            node_perf = self.compute_current_node_performance(
                racer_number, venue_code, race_date, race_number, conn
            )
            for key, value in node_perf.items():
                features[key] = value

            # 4. コース別成績
            if target_course:
                course_stats = self.compute_course_specific_rate(
                    racer_number, target_course, race_date, conn=conn
                )
                for key, value in course_stats.items():
                    features[key] = value

            # 5. 予測ST
            predicted_st, st_std = self.compute_predicted_st(
                racer_number, race_date, conn=conn
            )
            features['predicted_st'] = predicted_st
            features['st_stability'] = st_std

            # 6. モーターグレード成績
            motor_grade = self.compute_motor_grade_performance(
                motor_number, venue_code, race_date, conn
            )
            for key, value in motor_grade.items():
                features[key] = value

            # 7. フライング傾向
            flying = self.compute_flying_tendency(
                racer_number, race_date, conn=conn
            )
            for key, value in flying.items():
                features[key] = value

            return features

        finally:
            if close_conn:
                conn.close()


def extract_boaters_features(
    racer_number: str,
    motor_number: int,
    venue_code: str,
    race_date: str,
    race_number: int,
    target_course: int = None,
    db_path: str = 'data/boatrace.db'
) -> Dict[str, float]:
    """
    ボーターズインスパイアド特徴量を抽出（関数形式）

    Args:
        racer_number: 選手登録番号
        motor_number: モーター番号
        venue_code: 会場コード
        race_date: レース日（YYYY-MM-DD形式）
        race_number: レース番号
        target_course: 予測進入コース
        db_path: データベースパス

    Returns:
        特徴量辞書
    """
    extractor = BoatersInspiredFeatureExtractor(db_path)
    return extractor.extract_all_features(
        racer_number, motor_number, venue_code, race_date, race_number, target_course
    )


if __name__ == "__main__":
    # テスト実行
    import os

    print("=" * 70)
    print("ボーターズインスパイアド特徴量テスト")
    print("=" * 70)

    extractor = BoatersInspiredFeatureExtractor()

    # サンプルデータでテスト
    test_racer = "4839"  # 四宮与寛
    test_motor = 34
    test_venue = "02"  # 戸田
    test_date = "2025-12-06"
    test_race = 9

    print(f"\n選手: {test_racer}, モーター: {test_motor}")
    print(f"会場: {test_venue}, 日付: {test_date}, R{test_race}")

    features = extractor.extract_all_features(
        test_racer, test_motor, test_venue, test_date, test_race, target_course=1
    )

    print("\n【抽出された特徴量】")
    for key, value in sorted(features.items()):
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")
