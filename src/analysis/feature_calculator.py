"""
特徴量計算モジュール
機械学習用の派生特徴量を計算
"""
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class FeatureCalculator:
    """特徴量計算クラス"""

    def __init__(self, db_path="data/boatrace.db"):
        self.db_path = db_path

    def calculate_motor_stats(self, venue_code: str, days: int = 180) -> Dict:
        """
        モーター連対率を計算

        Args:
            venue_code: 競艇場コード
            days: 集計期間（日数）

        Returns:
            Dict: モーター番号 -> {win_rate, place_rate_2, place_rate_3, races}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                e.motor_number,
                COUNT(*) as total_races,
                SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 2 THEN 1 ELSE 0 END) as place_2,
                SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as place_3
            FROM entries e
            JOIN races r ON e.race_id = r.id
            LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            WHERE r.venue_code = ?
              AND r.race_date >= date('now', '-' || ? || ' days')
              AND e.motor_number IS NOT NULL
              AND res.rank IS NOT NULL
              AND res.rank NOT IN ('F', 'L', 'K', 'S')
            GROUP BY e.motor_number
            HAVING total_races >= 3
        """

        cursor.execute(query, [venue_code, days])
        rows = cursor.fetchall()
        conn.close()

        motor_stats = {}
        for row in rows:
            motor_no, total, wins, place_2, place_3 = row
            motor_stats[motor_no] = {
                "motor_number": motor_no,
                "total_races": total,
                "win_rate": wins / total if total > 0 else 0.0,
                "place_rate_2": place_2 / total if total > 0 else 0.0,
                "place_rate_3": place_3 / total if total > 0 else 0.0
            }

        return motor_stats

    def calculate_boat_stats(self, venue_code: str, days: int = 180) -> Dict:
        """
        ボート連対率を計算

        Args:
            venue_code: 競艇場コード
            days: 集計期間（日数）

        Returns:
            Dict: ボート番号 -> {win_rate, place_rate_2, place_rate_3, races}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                e.boat_number,
                COUNT(*) as total_races,
                SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 2 THEN 1 ELSE 0 END) as place_2,
                SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as place_3
            FROM entries e
            JOIN races r ON e.race_id = r.id
            LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            WHERE r.venue_code = ?
              AND r.race_date >= date('now', '-' || ? || ' days')
              AND e.boat_number IS NOT NULL
              AND res.rank IS NOT NULL
              AND res.rank NOT IN ('F', 'L', 'K', 'S')
            GROUP BY e.boat_number
            HAVING total_races >= 3
        """

        cursor.execute(query, [venue_code, days])
        rows = cursor.fetchall()
        conn.close()

        boat_stats = {}
        for row in rows:
            boat_no, total, wins, place_2, place_3 = row
            boat_stats[boat_no] = {
                "boat_number": boat_no,
                "total_races": total,
                "win_rate": wins / total if total > 0 else 0.0,
                "place_rate_2": place_2 / total if total > 0 else 0.0,
                "place_rate_3": place_3 / total if total > 0 else 0.0
            }

        return boat_stats

    def calculate_racer_course_stats(self, racer_number: str, days: int = 365) -> Dict:
        """
        選手のコース別成績を計算

        Args:
            racer_number: 選手登録番号
            days: 集計期間（日数）

        Returns:
            Dict: コース番号 -> {win_rate, place_rate_2, place_rate_3, races}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                rd.actual_course,
                COUNT(*) as total_races,
                SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 2 THEN 1 ELSE 0 END) as place_2,
                SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as place_3
            FROM entries e
            JOIN races r ON e.race_id = r.id
            JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            WHERE e.racer_number = ?
              AND r.race_date >= date('now', '-' || ? || ' days')
              AND rd.actual_course IS NOT NULL
              AND res.rank IS NOT NULL
              AND res.rank NOT IN ('F', 'L', 'K', 'S')
            GROUP BY rd.actual_course
        """

        cursor.execute(query, [racer_number, days])
        rows = cursor.fetchall()
        conn.close()

        course_stats = {}
        for row in rows:
            course, total, wins, place_2, place_3 = row
            course_stats[course] = {
                "course": course,
                "total_races": total,
                "win_rate": wins / total if total > 0 else 0.0,
                "place_rate_2": place_2 / total if total > 0 else 0.0,
                "place_rate_3": place_3 / total if total > 0 else 0.0
            }

        return course_stats

    def calculate_escape_rate(self, venue_code: Optional[str] = None, days: int = 90) -> float:
        """
        1号艇（1コース）逃げ率を計算

        Args:
            venue_code: 競艇場コード（Noneの場合は全国）
            days: 集計期間（日数）

        Returns:
            float: 逃げ率（0.0 ~ 1.0）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if venue_code:
            query = """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
                FROM race_details rd
                JOIN races r ON rd.race_id = r.id
                LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
                WHERE rd.actual_course = 1
                  AND r.venue_code = ?
                  AND r.race_date >= date('now', '-' || ? || ' days')
                  AND res.rank IS NOT NULL
                  AND res.rank NOT IN ('F', 'L', 'K', 'S')
            """
            cursor.execute(query, [venue_code, days])
        else:
            query = """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
                FROM race_details rd
                JOIN races r ON rd.race_id = r.id
                LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
                WHERE rd.actual_course = 1
                  AND r.race_date >= date('now', '-' || ? || ' days')
                  AND res.rank IS NOT NULL
                  AND res.rank NOT IN ('F', 'L', 'K', 'S')
            """
            cursor.execute(query, [days])

        row = cursor.fetchone()
        conn.close()

        if row and row[0] > 0:
            return row[1] / row[0]
        return 0.0

    def calculate_course_entry_pattern(self, venue_code: str, days: int = 90) -> Dict:
        """
        コース進入パターンの統計

        Args:
            venue_code: 競艇場コード
            days: 集計期間（日数）

        Returns:
            Dict: 進入パターンの統計情報
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 枠番とコースが一致しているレース数
        query_fixed = """
            SELECT COUNT(DISTINCT rd.race_id) as fixed_races
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.venue_code = ?
              AND r.race_date >= date('now', '-' || ? || ' days')
              AND rd.pit_number = rd.actual_course
        """
        cursor.execute(query_fixed, [venue_code, days])
        fixed_races = cursor.fetchone()[0]

        # 総レース数
        query_total = """
            SELECT COUNT(DISTINCT r.id) as total_races
            FROM races r
            WHERE r.venue_code = ?
              AND r.race_date >= date('now', '-' || ? || ' days')
        """
        cursor.execute(query_total, [venue_code, days])
        total_races = cursor.fetchone()[0]

        conn.close()

        if total_races > 0:
            fixed_rate = fixed_races / total_races
        else:
            fixed_rate = 0.0

        return {
            "total_races": total_races,
            "fixed_entry_races": fixed_races,
            "fixed_entry_rate": fixed_rate,
            "irregular_entry_rate": 1.0 - fixed_rate
        }

    def get_all_venue_features(self, venue_code: str, days: int = 90) -> Dict:
        """
        競艇場の全特徴量を一括取得

        Args:
            venue_code: 競艇場コード
            days: 集計期間（日数）

        Returns:
            Dict: 全特徴量
        """
        features = {
            "venue_code": venue_code,
            "analysis_period_days": days,
            "motor_stats": self.calculate_motor_stats(venue_code, days),
            "boat_stats": self.calculate_boat_stats(venue_code, days),
            "escape_rate": self.calculate_escape_rate(venue_code, days),
            "course_entry_pattern": self.calculate_course_entry_pattern(venue_code, days)
        }

        return features

    def export_features_summary(self, venue_code: str, days: int = 90) -> Dict:
        """
        特徴量サマリーをエクスポート用に整形

        Args:
            venue_code: 競艇場コード
            days: 集計期間（日数）

        Returns:
            Dict: サマリー情報
        """
        features = self.get_all_venue_features(venue_code, days)

        motor_count = len(features["motor_stats"])
        boat_count = len(features["boat_stats"])

        # モーター平均連対率
        if motor_count > 0:
            avg_motor_place_rate = sum(
                m["place_rate_2"] for m in features["motor_stats"].values()
            ) / motor_count
        else:
            avg_motor_place_rate = 0.0

        # ボート平均連対率
        if boat_count > 0:
            avg_boat_place_rate = sum(
                b["place_rate_2"] for b in features["boat_stats"].values()
            ) / boat_count
        else:
            avg_boat_place_rate = 0.0

        summary = {
            "venue_code": venue_code,
            "period_days": days,
            "motor_count": motor_count,
            "boat_count": boat_count,
            "avg_motor_place_rate_2": avg_motor_place_rate,
            "avg_boat_place_rate_2": avg_boat_place_rate,
            "escape_rate": features["escape_rate"],
            "fixed_entry_rate": features["course_entry_pattern"]["fixed_entry_rate"]
        }

        return summary
