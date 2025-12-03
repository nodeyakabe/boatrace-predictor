"""
決まり手分析モジュール
選手の決まり手傾向、コース別決まり手パターンを分析
"""

import sqlite3
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from src.utils.db_connection_pool import get_connection


class KimariteAnalyzer:
    """決まり手分析クラス"""

    # 決まり手の定義
    KIMARITE_NAMES = {
        1: '逃げ',
        2: '差し',
        3: 'まくり',
        4: 'まくり差し',
        5: '抜き',
        6: '恵まれ'
    }

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def _connect(self):
        """データベース接続（接続プールから取得）"""
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_racer_kimarite_stats(self, racer_number: int, days: int = 180) -> Dict:
        """
        選手の決まり手傾向を分析

        Args:
            racer_number: 選手登録番号
            days: 過去何日間のデータを分析するか

        Returns:
            {
                'racer_number': 4320,
                'total_wins': 15,
                'kimarite_breakdown': {
                    1: {'name': '逃げ', 'count': 8, 'rate': 53.3},
                    2: {'name': '差し', 'count': 3, 'rate': 20.0},
                    ...
                },
                'by_course': {
                    1: {1: 5, 2: 0, 3: 0},  # 1コースでの決まり手分布
                    2: {1: 0, 2: 2, 3: 1},
                    ...
                }
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 期間を計算
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # 選手の1着結果を取得（決まり手付き）
        query = """
            SELECT
                r.winning_technique,
                e.pit_number as course
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND r.rank = 1
              AND r.winning_technique IS NOT NULL
              AND ra.race_date BETWEEN ? AND ?
            ORDER BY ra.race_date DESC
        """

        cursor.execute(query, (racer_number, start_date.isoformat(), end_date.isoformat()))
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return {
                'racer_number': racer_number,
                'total_wins': 0,
                'kimarite_breakdown': {},
                'by_course': {}
            }

        # 決まり手別集計
        kimarite_count = {}
        by_course = {}

        for row in rows:
            technique = row['winning_technique']
            course = row['course']

            # 決まり手カウント
            kimarite_count[technique] = kimarite_count.get(technique, 0) + 1

            # コース別決まり手
            if course not in by_course:
                by_course[course] = {}
            by_course[course][technique] = by_course[course].get(technique, 0) + 1

        total_wins = len(rows)

        # 決まり手の詳細情報を作成
        kimarite_breakdown = {}
        for technique_code, count in kimarite_count.items():
            kimarite_breakdown[technique_code] = {
                'name': self.KIMARITE_NAMES.get(technique_code, '不明'),
                'count': count,
                'rate': round(count / total_wins * 100, 1)
            }

        return {
            'racer_number': racer_number,
            'total_wins': total_wins,
            'kimarite_breakdown': kimarite_breakdown,
            'by_course': by_course
        }

    def get_venue_kimarite_trends(self, venue_code: str, days: int = 90) -> Dict:
        """
        競艇場の決まり手傾向を分析

        Args:
            venue_code: 会場コード（"01"-"24"）
            days: 過去何日間のデータを分析するか

        Returns:
            {
                'venue_code': '03',
                'total_races': 120,
                'kimarite_distribution': {
                    1: {'name': '逃げ', 'count': 60, 'rate': 50.0},
                    ...
                },
                'by_course': {
                    1: {1: 50, 2: 5, 3: 3},  # 1コースから1着時の決まり手分布
                    2: {1: 0, 2: 15, 3: 8},
                    ...
                }
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 期間を計算
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # 会場の1着結果を取得
        query = """
            SELECT
                r.winning_technique,
                r.pit_number as course
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            WHERE ra.venue_code = ?
              AND r.rank = 1
              AND r.winning_technique IS NOT NULL
              AND ra.race_date BETWEEN ? AND ?
        """

        cursor.execute(query, (venue_code, start_date.isoformat(), end_date.isoformat()))
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return {
                'venue_code': venue_code,
                'total_races': 0,
                'kimarite_distribution': {},
                'by_course': {}
            }

        # 集計
        kimarite_count = {}
        by_course = {}

        for row in rows:
            technique = row['winning_technique']
            course = row['course']

            kimarite_count[technique] = kimarite_count.get(technique, 0) + 1

            if course not in by_course:
                by_course[course] = {}
            by_course[course][technique] = by_course[course].get(technique, 0) + 1

        total_races = len(rows)

        # 決まり手分布を作成
        kimarite_distribution = {}
        for technique_code, count in kimarite_count.items():
            kimarite_distribution[technique_code] = {
                'name': self.KIMARITE_NAMES.get(technique_code, '不明'),
                'count': count,
                'rate': round(count / total_races * 100, 1)
            }

        return {
            'venue_code': venue_code,
            'total_races': total_races,
            'kimarite_distribution': kimarite_distribution,
            'by_course': by_course
        }

    def get_course_kimarite_pattern(self, venue_code: str, course: int, days: int = 90) -> Dict:
        """
        特定コースの決まり手パターンを分析

        Args:
            venue_code: 会場コード
            course: コース番号（1-6）
            days: 過去何日間のデータを分析するか

        Returns:
            {
                'venue_code': '03',
                'course': 1,
                'total_wins': 60,
                'kimarite_pattern': {
                    1: {'name': '逃げ', 'count': 55, 'rate': 91.7},
                    2: {'name': '差し', 'count': 3, 'rate': 5.0},
                    ...
                }
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        query = """
            SELECT r.winning_technique
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            WHERE ra.venue_code = ?
              AND r.pit_number = ?
              AND r.rank = 1
              AND r.winning_technique IS NOT NULL
              AND ra.race_date BETWEEN ? AND ?
        """

        cursor.execute(query, (venue_code, course, start_date.isoformat(), end_date.isoformat()))
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return {
                'venue_code': venue_code,
                'course': course,
                'total_wins': 0,
                'kimarite_pattern': {}
            }

        kimarite_count = {}
        for row in rows:
            technique = row['winning_technique']
            kimarite_count[technique] = kimarite_count.get(technique, 0) + 1

        total_wins = len(rows)

        kimarite_pattern = {}
        for technique_code, count in kimarite_count.items():
            kimarite_pattern[technique_code] = {
                'name': self.KIMARITE_NAMES.get(technique_code, '不明'),
                'count': count,
                'rate': round(count / total_wins * 100, 1)
            }

        return {
            'venue_code': venue_code,
            'course': course,
            'total_wins': total_wins,
            'kimarite_pattern': kimarite_pattern
        }

    def get_racer_course_affinity(self, racer_number: int, days: int = 180) -> Dict:
        """
        選手のコース別適性を分析（決まり手ベース）

        Args:
            racer_number: 選手登録番号
            days: 過去何日間のデータを分析するか

        Returns:
            {
                'racer_number': 4320,
                'course_affinity': {
                    1: {'wins': 8, 'races': 20, 'win_rate': 40.0, 'primary_kimarite': '逃げ'},
                    2: {'wins': 3, 'races': 15, 'win_rate': 20.0, 'primary_kimarite': '差し'},
                    ...
                }
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # コース別の出走数と勝利数を取得
        query = """
            SELECT
                e.pit_number as course,
                COUNT(*) as races,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as wins,
                r.winning_technique
            FROM entries e
            JOIN races ra ON e.race_id = ra.id
            LEFT JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date BETWEEN ? AND ?
            GROUP BY e.pit_number, r.winning_technique
        """

        cursor.execute(query, (racer_number, start_date.isoformat(), end_date.isoformat()))
        rows = cursor.fetchall()
        cursor.close()

        course_affinity = {}
        course_stats = {}

        # まずコース別の基本統計を集計
        for row in rows:
            course = row['course']
            if course not in course_stats:
                course_stats[course] = {'races': 0, 'wins': 0, 'kimarite': {}}

            course_stats[course]['races'] += row['races']
            course_stats[course]['wins'] += row['wins']

            if row['winning_technique'] and row['wins'] > 0:
                technique = row['winning_technique']
                course_stats[course]['kimarite'][technique] = course_stats[course]['kimarite'].get(technique, 0) + row['wins']

        # 結果を整形
        for course, stats in course_stats.items():
            win_rate = round(stats['wins'] / stats['races'] * 100, 1) if stats['races'] > 0 else 0.0

            # 最も多い決まり手を特定
            primary_kimarite = '不明'
            if stats['kimarite']:
                primary_technique = max(stats['kimarite'], key=stats['kimarite'].get)
                primary_kimarite = self.KIMARITE_NAMES.get(primary_technique, '不明')

            course_affinity[course] = {
                'wins': stats['wins'],
                'races': stats['races'],
                'win_rate': win_rate,
                'primary_kimarite': primary_kimarite
            }

        return {
            'racer_number': racer_number,
            'course_affinity': course_affinity
        }


if __name__ == "__main__":
    # テスト
    analyzer = KimariteAnalyzer()

    print("=" * 80)
    print("決まり手分析テスト")
    print("=" * 80)

    # テスト: 選手の決まり手傾向
    print("\n【1】 選手の決まり手傾向")
    racer_number = 4320  # テスト用選手番号
    stats = analyzer.get_racer_kimarite_stats(racer_number, days=180)

    print(f"選手番号: {stats['racer_number']}")
    print(f"総勝利数: {stats['total_wins']}回")

    if stats['kimarite_breakdown']:
        print("\n決まり手内訳:")
        for technique_code, data in sorted(stats['kimarite_breakdown'].items()):
            print(f"  {data['name']}: {data['count']}回 ({data['rate']}%)")

        print("\nコース別決まり手:")
        for course, techniques in sorted(stats['by_course'].items()):
            print(f"  {course}コース:")
            for technique_code, count in sorted(techniques.items()):
                technique_name = analyzer.KIMARITE_NAMES.get(technique_code, '不明')
                print(f"    {technique_name}: {count}回")

    # テスト: 会場の決まり手傾向
    print("\n" + "=" * 80)
    print("【2】 会場の決まり手傾向")
    venue_code = "03"  # 江戸川
    venue_stats = analyzer.get_venue_kimarite_trends(venue_code, days=90)

    print(f"会場コード: {venue_stats['venue_code']}")
    print(f"総レース数: {venue_stats['total_races']}R")

    if venue_stats['kimarite_distribution']:
        print("\n決まり手分布:")
        for technique_code, data in sorted(venue_stats['kimarite_distribution'].items()):
            print(f"  {data['name']}: {data['count']}回 ({data['rate']}%)")

    # テスト: コース別適性
    print("\n" + "=" * 80)
    print("【3】 選手のコース別適性")
    affinity = analyzer.get_racer_course_affinity(racer_number, days=180)

    print(f"選手番号: {affinity['racer_number']}")
    if affinity['course_affinity']:
        print("\nコース別成績:")
        for course in sorted(affinity['course_affinity'].keys()):
            data = affinity['course_affinity'][course]
            print(f"  {course}コース: {data['wins']}勝/{data['races']}走 ({data['win_rate']}%) - 主な決まり手: {data['primary_kimarite']}")

    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)
