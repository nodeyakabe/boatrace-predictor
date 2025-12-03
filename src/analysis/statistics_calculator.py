"""
基礎統計計算モジュール

コース別勝率、選手成績、場所別特性など
予想システムの基盤となる統計データを計算
"""

from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import sqlite3
from src.analysis.smoothing import LaplaceSmoothing
from src.utils.db_connection_pool import get_connection


class StatisticsCalculator:
    """統計計算クラス"""

    def __init__(self, db_path="data/boatrace.db"):
        self.db_path = db_path
        self.smoother = LaplaceSmoothing()

    def _connect(self):
        """データベース接続（接続プールから取得）"""
        return get_connection(self.db_path)

    def _fetch_all(self, query, params=None):
        """クエリ実行（複数行取得）"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params or [])
        results = cursor.fetchall()
        cursor.close()
        return results

    def _fetch_one(self, query, params=None):
        """クエリ実行（1行取得）"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params or [])
        result = cursor.fetchone()
        cursor.close()
        return result

    # ========================================
    # コース別統計
    # ========================================

    def calculate_course_stats(self, venue_code: Optional[str] = None,
                               days: int = 90) -> Dict[int, Dict]:
        """
        コース別の1着率・2着率・3着率を計算

        Args:
            venue_code: 競艇場コード（Noneの場合は全国）
            days: 集計期間（日数）

        Returns:
            {
                1: {'total_races': 500, 'win_rate': 0.55, 'place_rate_2': 0.18, 'place_rate_3': 0.10},
                2: {'total_races': 500, 'win_rate': 0.15, 'place_rate_2': 0.25, 'place_rate_3': 0.20},
                ...
            }
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # 各コースごとに、そのコースから出走したレースでの着順を集計
        query = """
            SELECT
                rd.actual_course as course,
                COUNT(*) as total_races,
                SUM(CASE WHEN res.rank = 1 THEN 1 ELSE 0 END) as first_place,
                SUM(CASE WHEN res.rank = 2 THEN 1 ELSE 0 END) as second_place,
                SUM(CASE WHEN res.rank = 3 THEN 1 ELSE 0 END) as third_place
            FROM race_details rd
            JOIN races ra ON rd.race_id = ra.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE ra.race_date >= ?
              AND rd.actual_course IS NOT NULL
        """

        params = [start_date]

        if venue_code:
            query += " AND ra.venue_code = ?"
            params.append(venue_code)

        query += """
            GROUP BY rd.actual_course
            ORDER BY rd.actual_course
        """

        rows = self._fetch_all(query, params)

        stats = {}
        for row in rows:
            course = row['course']
            total = row['total_races']

            if total > 0:
                # Laplace平滑化を適用
                wins = row['first_place']
                smoothed_win_rate = self.smoother.smooth_win_rate(wins, total, k=2)

                stats[course] = {
                    'total_races': total,
                    'win_rate': smoothed_win_rate,
                    'raw_win_rate': row['first_place'] / total,  # 元の勝率も保存
                    'place_rate_2': row['second_place'] / total,
                    'place_rate_3': row['third_place'] / total,
                    'smoothing_applied': self.smoother.enabled
                }

        return stats

    def calculate_escape_rate(self, venue_code: Optional[str] = None,
                             days: int = 90) -> float:
        """
        1号艇の逃げ率を計算

        Args:
            venue_code: 競艇場コード（Noneの場合は全国）
            days: 集計期間（日数）

        Returns:
            逃げ率（0.0-1.0）
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as wins
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            WHERE ra.race_date >= ?
              AND rd.actual_course = 1
        """

        params = [start_date]

        if venue_code:
            query += " AND ra.venue_code = ?"
            params.append(venue_code)

        row = self._fetch_one(query, params)

        if row and row['total'] > 0:
            return row['wins'] / row['total']
        return 0.0

    # ========================================
    # 選手成績統計
    # ========================================

    def calculate_racer_stats(self, racer_number: int, days: int = 180) -> Dict:
        """
        選手の成績統計を計算

        Args:
            racer_number: 選手登録番号
            days: 集計期間（日数）

        Returns:
            {
                'total_races': 50,
                'win_rate': 0.25,
                'place_rate_2': 0.40,
                'place_rate_3': 0.52,
                'avg_st': 0.14
            }
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as first_place,
                SUM(CASE WHEN r.rank = 2 THEN 1 ELSE 0 END) as second_place,
                SUM(CASE WHEN r.rank = 3 THEN 1 ELSE 0 END) as third_place,
                AVG(rd.st_time) as avg_st
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            LEFT JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date >= ?
        """

        row = self._fetch_one(query, [racer_number, start_date])

        if row and row['total_races'] > 0:
            total = row['total_races']
            return {
                'total_races': total,
                'win_rate': row['first_place'] / total,
                'place_rate_2': (row['first_place'] + row['second_place']) / total,
                'place_rate_3': (row['first_place'] + row['second_place'] + row['third_place']) / total,
                'avg_st': row['avg_st'] if row['avg_st'] else None
            }

        return {
            'total_races': 0,
            'win_rate': 0.0,
            'place_rate_2': 0.0,
            'place_rate_3': 0.0,
            'avg_st': None
        }

    def calculate_racer_course_stats(self, racer_number: int, course: int,
                                    days: int = 180) -> Dict:
        """
        選手のコース別成績を計算

        Args:
            racer_number: 選手登録番号
            course: コース番号（1-6）
            days: 集計期間（日数）

        Returns:
            {
                'total_races': 20,
                'win_rate': 0.30,
                'place_rate_2': 0.50
            }
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as first_place,
                SUM(CASE WHEN r.rank <= 2 THEN 1 ELSE 0 END) as top_two
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            WHERE e.racer_number = ?
              AND rd.actual_course = ?
              AND ra.race_date >= ?
        """

        row = self._fetch_one(query, [racer_number, course, start_date])

        if row and row['total_races'] > 0:
            total = row['total_races']
            return {
                'total_races': total,
                'win_rate': row['first_place'] / total,
                'place_rate_2': row['top_two'] / total
            }

        return {
            'total_races': 0,
            'win_rate': 0.0,
            'place_rate_2': 0.0
        }

    # ========================================
    # モーター成績統計
    # ========================================

    def calculate_motor_stats(self, venue_code: str, motor_number: int,
                             days: int = 90) -> Dict:
        """
        モーターの成績統計を計算

        Args:
            venue_code: 競艇場コード
            motor_number: モーター番号
            days: 集計期間（日数）

        Returns:
            {
                'total_races': 30,
                'second_rate': 0.40,
                'third_rate': 0.55
            }
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank <= 2 THEN 1 ELSE 0 END) as top_two,
                SUM(CASE WHEN r.rank <= 3 THEN 1 ELSE 0 END) as top_three
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE ra.venue_code = ?
              AND e.motor_number = ?
              AND ra.race_date >= ?
        """

        row = self._fetch_one(query, [venue_code, motor_number, start_date])

        if row and row['total_races'] > 0:
            total = row['total_races']
            return {
                'total_races': total,
                'second_rate': row['top_two'] / total,
                'third_rate': row['top_three'] / total
            }

        return {
            'total_races': 0,
            'second_rate': 0.0,
            'third_rate': 0.0
        }

    # ========================================
    # 場所別統計
    # ========================================

    def calculate_venue_characteristics(self, venue_code: str,
                                       days: int = 90) -> Dict:
        """
        場所別の特性を計算

        Args:
            venue_code: 競艇場コード
            days: 集計期間（日数）

        Returns:
            {
                'escape_rate': 0.55,  # 1号艇逃げ率
                'inside_win_rate': 0.75,  # イン勝率（1-3コース）
                'avg_payout': 1250.5,  # 平均配当
                'high_payout_rate': 0.05  # 万舟率
            }
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # 1号艇逃げ率
        escape_rate = self.calculate_escape_rate(venue_code, days)

        # イン勝率（1-3コース）
        query_inside = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as wins
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            WHERE ra.venue_code = ?
              AND ra.race_date >= ?
              AND rd.actual_course IN (1, 2, 3)
        """
        row_inside = self._fetch_one(query_inside, [venue_code, start_date])
        inside_win_rate = row_inside['wins'] / row_inside['total'] if row_inside['total'] > 0 else 0.0

        # 平均配当・万舟率
        query_payout = """
            SELECT
                AVG(trifecta_odds) as avg_payout,
                SUM(CASE WHEN trifecta_odds >= 10000 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as high_payout_rate
            FROM results
            WHERE race_id IN (
                SELECT id FROM races WHERE venue_code = ? AND race_date >= ?
            )
            AND rank = 1
            AND trifecta_odds IS NOT NULL
        """
        row_payout = self._fetch_one(query_payout, [venue_code, start_date])

        return {
            'escape_rate': escape_rate,
            'inside_win_rate': inside_win_rate,
            'avg_payout': row_payout['avg_payout'] if row_payout['avg_payout'] else 0.0,
            'high_payout_rate': row_payout['high_payout_rate'] if row_payout['high_payout_rate'] else 0.0
        }

    def calculate_kimarite_distribution(self, venue_code: Optional[str] = None,
                                       days: int = 90) -> Dict[str, Dict]:
        """
        決まり手の分布を計算

        Args:
            venue_code: 競艇場コード（Noneの場合は全国）
            days: 集計期間（日数）

        Returns:
            {
                '逃げ': {'count': 100, 'rate': 0.45},
                'まくり': {'count': 50, 'rate': 0.23},
                '差し': {'count': 40, 'rate': 0.18},
                'まくり差し': {'count': 20, 'rate': 0.09},
                '抜き': {'count': 8, 'rate': 0.04},
                '恵まれ': {'count': 2, 'rate': 0.01}
            }
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                res.kimarite,
                COUNT(*) as count
            FROM results res
            JOIN races ra ON res.race_id = ra.id
            WHERE ra.race_date >= ?
              AND res.kimarite IS NOT NULL
              AND res.kimarite != ''
              AND res.rank = '1'
        """

        params = [start_date]

        if venue_code:
            query += " AND ra.venue_code = ?"
            params.append(venue_code)

        query += """
            GROUP BY res.kimarite
            ORDER BY count DESC
        """

        rows = self._fetch_all(query, params)

        total = sum(row['count'] for row in rows)
        distribution = {}

        for row in rows:
            kimarite = row['kimarite']
            count = row['count']
            distribution[kimarite] = {
                'count': count,
                'rate': count / total if total > 0 else 0.0
            }

        return distribution

    def calculate_course_kimarite_stats(self, venue_code: Optional[str] = None,
                                       days: int = 90) -> Dict[int, Dict]:
        """
        コース別の決まり手確率を計算

        Args:
            venue_code: 競艇場コード（Noneの場合は全国）
            days: 集計期間（日数）

        Returns:
            {
                1: {'逃げ': 0.95, 'まくり': 0.02, '差し': 0.03, ...},
                2: {'逃げ': 0.05, 'まくり': 0.30, '差し': 0.60, ...},
                ...
            }
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                rd.actual_course as course,
                res.kimarite,
                COUNT(*) as count
            FROM results res
            JOIN races ra ON res.race_id = ra.id
            JOIN race_details rd ON res.race_id = rd.race_id AND res.pit_number = rd.pit_number
            WHERE ra.race_date >= ?
              AND res.kimarite IS NOT NULL
              AND res.kimarite != ''
              AND res.rank = '1'
              AND rd.actual_course IS NOT NULL
        """

        params = [start_date]

        if venue_code:
            query += " AND ra.venue_code = ?"
            params.append(venue_code)

        query += """
            GROUP BY rd.actual_course, res.kimarite
        """

        rows = self._fetch_all(query, params)

        # コース別の合計を計算
        course_totals = {}
        course_kimarite = {}

        for row in rows:
            course = row['course']
            kimarite = row['kimarite']
            count = row['count']

            if course not in course_totals:
                course_totals[course] = 0
                course_kimarite[course] = {}

            course_totals[course] += count
            course_kimarite[course][kimarite] = count

        # 確率に変換
        stats = {}
        for course in course_kimarite:
            stats[course] = {}
            total = course_totals[course]
            for kimarite, count in course_kimarite[course].items():
                stats[course][kimarite] = count / total if total > 0 else 0.0

        return stats

    def rank_venues_by_solidity(self, days: int = 90) -> List[Tuple[str, float]]:
        """
        固い場ランキング

        Args:
            days: 集計期間（日数）

        Returns:
            [(venue_code, escape_rate), ...] 逃げ率降順
        """
        venue_codes = [f"{i:02d}" for i in range(1, 25)]  # 01-24
        rankings = []

        for venue_code in venue_codes:
            escape_rate = self.calculate_escape_rate(venue_code, days)
            rankings.append((venue_code, escape_rate))

        # 逃げ率降順でソート
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def rank_venues_by_upset_rate(self, days: int = 90) -> List[Tuple[str, float]]:
        """
        荒れる場ランキング

        Args:
            days: 集計期間（日数）

        Returns:
            [(venue_code, upset_rate), ...] 万舟率降順
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                ra.venue_code,
                SUM(CASE WHEN r.trifecta_odds >= 10000 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as upset_rate
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            WHERE ra.race_date >= ?
              AND r.rank = 1
              AND r.trifecta_odds IS NOT NULL
            GROUP BY ra.venue_code
            ORDER BY upset_rate DESC
        """

        rows = self._fetch_all(query, [start_date])
        return [(row['venue_code'], row['upset_rate']) for row in rows]

    # ========================================
    # レース単位の統計
    # ========================================

    def analyze_race(self, race_id: int) -> Dict:
        """
        特定レースの詳細分析

        Args:
            race_id: レースID

        Returns:
            {
                'course_stats': {...},
                'racer_stats': [{...}, ...],
                'motor_stats': [{...}, ...],
                'venue_characteristics': {...}
            }
        """
        # レース情報取得
        query_race = """
            SELECT venue_code, race_date, race_number
            FROM races
            WHERE id = ?
        """
        race_info = self._fetch_one(query_race, [race_id])

        if not race_info:
            return {}

        venue_code = race_info['venue_code']

        # エントリー情報取得
        query_entries = """
            SELECT
                e.pit_number,
                e.racer_number,
                e.racer_name,
                e.motor_number,
                rd.actual_course
            FROM entries e
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        """
        entries = self._fetch_all(query_entries, [race_id])

        # 各艇の詳細統計を取得
        racer_stats = []
        motor_stats = []

        for entry in entries:
            # 選手成績
            r_stats = self.calculate_racer_stats(entry['racer_number'])
            r_stats['pit_number'] = entry['pit_number']
            r_stats['racer_name'] = entry['racer_name']
            racer_stats.append(r_stats)

            # モーター成績
            m_stats = self.calculate_motor_stats(venue_code, entry['motor_number'])
            m_stats['pit_number'] = entry['pit_number']
            m_stats['motor_number'] = entry['motor_number']
            motor_stats.append(m_stats)

        # コース別統計
        course_stats = self.calculate_course_stats(venue_code)

        # 場所別特性
        venue_characteristics = self.calculate_venue_characteristics(venue_code)

        return {
            'race_info': dict(race_info),
            'course_stats': course_stats,
            'racer_stats': racer_stats,
            'motor_stats': motor_stats,
            'venue_characteristics': venue_characteristics
        }


if __name__ == "__main__":
    # テスト実行
    calc = StatisticsCalculator()

    print("=" * 60)
    print("基礎統計計算テスト")
    print("=" * 60)

    # コース別統計
    print("\n【コース別勝率（全国・過去90日）】")
    course_stats = calc.calculate_course_stats()
    for course, stats in course_stats.items():
        print(f"  {course}コース: 1着率 {stats['win_rate']:.1%}, "
              f"2着率 {stats['place_rate_2']:.1%}, 3着率 {stats['place_rate_3']:.1%}")

    # 場所別1号艇逃げ率
    print("\n【場所別1号艇逃げ率（トップ5）】")
    solid_venues = calc.rank_venues_by_solidity()[:5]
    for venue_code, escape_rate in solid_venues:
        print(f"  場所{venue_code}: {escape_rate:.1%}")

    # 荒れる場ランキング
    print("\n【荒れる場ランキング（トップ5）】")
    upset_venues = calc.rank_venues_by_upset_rate()[:5]
    for venue_code, upset_rate in upset_venues:
        print(f"  場所{venue_code}: 万舟率 {upset_rate:.1%}")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
