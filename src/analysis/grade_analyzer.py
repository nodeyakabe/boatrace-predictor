"""
グレード別成績分析モジュール
選手のグレード別パフォーマンスを分析
"""

import sqlite3
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from src.utils.db_connection_pool import get_connection


class GradeAnalyzer:
    """グレード別成績分析クラス"""

    # レースグレードの定義
    GRADE_HIERARCHY = {
        'SG': 6,        # 最高峰
        'G1': 5,
        'G2': 4,
        'G3': 3,
        'ルーキーシリーズ': 2,
        '一般': 1
    }

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def _connect(self):
        """データベース接続（接続プールから取得）"""
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_racer_grade_stats(self, racer_number: int, days: int = 365) -> Dict:
        """
        選手のグレード別成績を分析

        Args:
            racer_number: 選手登録番号
            days: 過去何日間のデータを分析するか

        Returns:
            {
                'racer_number': 4320,
                'overall': {
                    'total_races': 120,
                    'wins': 15,
                    'win_rate': 12.5,
                    'top2': 40,
                    'top2_rate': 33.3,
                    'top3': 60,
                    'top3_rate': 50.0
                },
                'by_grade': {
                    'SG': {
                        'total_races': 10,
                        'wins': 0,
                        'win_rate': 0.0,
                        'top2': 2,
                        'top2_rate': 20.0,
                        'top3': 3,
                        'top3_rate': 30.0,
                        'avg_rank': 3.5
                    },
                    'G1': {...},
                    ...
                }
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # 選手の全成績を取得（グレード付き）
        query = """
            SELECT
                ra.race_grade,
                r.rank,
                CASE WHEN r.rank = 1 THEN 1 ELSE 0 END as is_win,
                CASE WHEN r.rank <= 2 THEN 1 ELSE 0 END as is_top2,
                CASE WHEN r.rank <= 3 THEN 1 ELSE 0 END as is_top3
            FROM entries e
            JOIN races ra ON e.race_id = ra.id
            LEFT JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date BETWEEN ? AND ?
              AND ra.race_grade IS NOT NULL
              AND r.rank IS NOT NULL
            ORDER BY ra.race_date DESC
        """

        cursor.execute(query, (racer_number, start_date.isoformat(), end_date.isoformat()))
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return {
                'racer_number': racer_number,
                'overall': self._empty_stats(),
                'by_grade': {}
            }

        # 全体統計
        overall_stats = {
            'total_races': len(rows),
            'wins': sum(row['is_win'] for row in rows),
            'top2': sum(row['is_top2'] for row in rows),
            'top3': sum(row['is_top3'] for row in rows),
            'rank_sum': sum(row['rank'] for row in rows)
        }

        overall_stats['win_rate'] = round(overall_stats['wins'] / overall_stats['total_races'] * 100, 1) if overall_stats['total_races'] > 0 else 0.0
        overall_stats['top2_rate'] = round(overall_stats['top2'] / overall_stats['total_races'] * 100, 1) if overall_stats['total_races'] > 0 else 0.0
        overall_stats['top3_rate'] = round(overall_stats['top3'] / overall_stats['total_races'] * 100, 1) if overall_stats['total_races'] > 0 else 0.0
        overall_stats['avg_rank'] = round(overall_stats['rank_sum'] / overall_stats['total_races'], 2) if overall_stats['total_races'] > 0 else 0.0

        # グレード別集計
        by_grade = {}
        grade_data = {}

        for row in rows:
            grade = row['race_grade'] if row['race_grade'] else '一般'

            if grade not in grade_data:
                grade_data[grade] = {
                    'total_races': 0,
                    'wins': 0,
                    'top2': 0,
                    'top3': 0,
                    'rank_sum': 0
                }

            grade_data[grade]['total_races'] += 1
            grade_data[grade]['wins'] += row['is_win']
            grade_data[grade]['top2'] += row['is_top2']
            grade_data[grade]['top3'] += row['is_top3']
            grade_data[grade]['rank_sum'] += row['rank']

        # 各グレードの統計を計算
        for grade, data in grade_data.items():
            total = data['total_races']
            by_grade[grade] = {
                'total_races': total,
                'wins': data['wins'],
                'win_rate': round(data['wins'] / total * 100, 1) if total > 0 else 0.0,
                'top2': data['top2'],
                'top2_rate': round(data['top2'] / total * 100, 1) if total > 0 else 0.0,
                'top3': data['top3'],
                'top3_rate': round(data['top3'] / total * 100, 1) if total > 0 else 0.0,
                'avg_rank': round(data['rank_sum'] / total, 2) if total > 0 else 0.0
            }

        return {
            'racer_number': racer_number,
            'overall': overall_stats,
            'by_grade': by_grade
        }

    def get_grade_comparison(self, racer_numbers: List[int], days: int = 365) -> Dict:
        """
        複数選手のグレード別成績を比較

        Args:
            racer_numbers: 選手登録番号のリスト
            days: 過去何日間のデータを分析するか

        Returns:
            {
                4320: {
                    'racer_number': 4320,
                    'overall': {...},
                    'by_grade': {...}
                },
                4321: {...},
                ...
            }
        """
        comparison = {}

        for racer_number in racer_numbers:
            stats = self.get_racer_grade_stats(racer_number, days)
            comparison[racer_number] = stats

        return comparison

    def get_grade_level_assessment(self, racer_number: int, days: int = 365) -> Dict:
        """
        選手のグレード適応力を評価

        Args:
            racer_number: 選手登録番号
            days: 過去何日間のデータを分析するか

        Returns:
            {
                'racer_number': 4320,
                'grade_assessment': {
                    'strongest_grade': 'G3',
                    'strongest_win_rate': 25.0,
                    'weakest_grade': 'SG',
                    'weakest_win_rate': 0.0,
                    'grade_consistency': 'B',  # A-Eランク
                    'upward_potential': 'High'  # Low/Medium/High
                }
            }
        """
        stats = self.get_racer_grade_stats(racer_number, days)

        if not stats['by_grade']:
            return {
                'racer_number': racer_number,
                'grade_assessment': {
                    'strongest_grade': None,
                    'strongest_win_rate': 0.0,
                    'weakest_grade': None,
                    'weakest_win_rate': 0.0,
                    'grade_consistency': 'N/A',
                    'upward_potential': 'N/A'
                }
            }

        # 最強・最弱グレードを特定
        by_grade = stats['by_grade']

        # 少なくとも5レース以上出走しているグレードのみ対象
        valid_grades = {g: data for g, data in by_grade.items() if data['total_races'] >= 5}

        if not valid_grades:
            # データ不足
            strongest_grade = max(by_grade, key=lambda g: by_grade[g]['win_rate'])
            weakest_grade = min(by_grade, key=lambda g: by_grade[g]['win_rate'])
        else:
            strongest_grade = max(valid_grades, key=lambda g: valid_grades[g]['win_rate'])
            weakest_grade = min(valid_grades, key=lambda g: valid_grades[g]['win_rate'])

        strongest_win_rate = by_grade[strongest_grade]['win_rate']
        weakest_win_rate = by_grade[weakest_grade]['win_rate']

        # グレード一貫性を評価（勝率の標準偏差を計算）
        win_rates = [data['win_rate'] for data in valid_grades.values()] if valid_grades else [data['win_rate'] for data in by_grade.values()]

        if len(win_rates) > 1:
            import statistics
            std_dev = statistics.stdev(win_rates)

            # 標準偏差に基づいて一貫性を評価
            if std_dev < 5.0:
                consistency = 'A'  # 非常に安定
            elif std_dev < 10.0:
                consistency = 'B'  # 安定
            elif std_dev < 15.0:
                consistency = 'C'  # 普通
            elif std_dev < 20.0:
                consistency = 'D'  # 不安定
            else:
                consistency = 'E'  # 非常に不安定
        else:
            consistency = 'N/A'

        # 上昇志向を評価（高グレードでの成績）
        high_grade_performance = 0
        high_grades = ['SG', 'G1', 'G2']
        high_grade_races = sum(by_grade[g]['total_races'] for g in high_grades if g in by_grade)

        if high_grade_races >= 10:
            high_grade_wins = sum(by_grade[g]['wins'] for g in high_grades if g in by_grade)
            high_grade_win_rate = high_grade_wins / high_grade_races * 100

            if high_grade_win_rate >= 15.0:
                upward_potential = 'High'
            elif high_grade_win_rate >= 8.0:
                upward_potential = 'Medium'
            else:
                upward_potential = 'Low'
        else:
            upward_potential = 'Insufficient Data'

        return {
            'racer_number': racer_number,
            'grade_assessment': {
                'strongest_grade': strongest_grade,
                'strongest_win_rate': strongest_win_rate,
                'weakest_grade': weakest_grade,
                'weakest_win_rate': weakest_win_rate,
                'grade_consistency': consistency,
                'upward_potential': upward_potential
            }
        }

    def get_venue_grade_distribution(self, venue_code: str, days: int = 90) -> Dict:
        """
        競艇場のグレード別レース開催状況を分析

        Args:
            venue_code: 会場コード
            days: 過去何日間のデータを分析するか

        Returns:
            {
                'venue_code': '03',
                'total_races': 120,
                'grade_distribution': {
                    'SG': {'count': 12, 'rate': 10.0},
                    'G1': {'count': 24, 'rate': 20.0},
                    ...
                }
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        query = """
            SELECT race_grade, COUNT(*) as count
            FROM races
            WHERE venue_code = ?
              AND race_date BETWEEN ? AND ?
              AND race_grade IS NOT NULL
            GROUP BY race_grade
        """

        cursor.execute(query, (venue_code, start_date.isoformat(), end_date.isoformat()))
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return {
                'venue_code': venue_code,
                'total_races': 0,
                'grade_distribution': {}
            }

        total_races = sum(row['count'] for row in rows)
        grade_distribution = {}

        for row in rows:
            grade = row['race_grade'] if row['race_grade'] else '一般'
            count = row['count']
            grade_distribution[grade] = {
                'count': count,
                'rate': round(count / total_races * 100, 1)
            }

        return {
            'venue_code': venue_code,
            'total_races': total_races,
            'grade_distribution': grade_distribution
        }

    def _empty_stats(self) -> Dict:
        """空の統計データを返す"""
        return {
            'total_races': 0,
            'wins': 0,
            'win_rate': 0.0,
            'top2': 0,
            'top2_rate': 0.0,
            'top3': 0,
            'top3_rate': 0.0,
            'avg_rank': 0.0
        }


if __name__ == "__main__":
    # テスト
    analyzer = GradeAnalyzer()

    print("=" * 80)
    print("グレード別成績分析テスト")
    print("=" * 80)

    # テスト: 選手のグレード別成績
    print("\n【1】 選手のグレード別成績")
    racer_number = 4320
    stats = analyzer.get_racer_grade_stats(racer_number, days=365)

    print(f"選手番号: {stats['racer_number']}")
    print("\n全体成績:")
    overall = stats['overall']
    print(f"  総出走: {overall['total_races']}R")
    print(f"  1着: {overall['wins']}回 ({overall['win_rate']}%)")
    print(f"  2着内: {overall['top2']}回 ({overall['top2_rate']}%)")
    print(f"  3着内: {overall['top3']}回 ({overall['top3_rate']}%)")
    print(f"  平均着順: {overall['avg_rank']}")

    if stats['by_grade']:
        print("\nグレード別成績:")
        # グレードの優先順位でソート
        sorted_grades = sorted(
            stats['by_grade'].keys(),
            key=lambda g: analyzer.GRADE_HIERARCHY.get(g, 0),
            reverse=True
        )

        for grade in sorted_grades:
            data = stats['by_grade'][grade]
            print(f"\n  【{grade}】")
            print(f"    出走: {data['total_races']}R")
            print(f"    勝率: {data['win_rate']}%")
            print(f"    連対率: {data['top2_rate']}%")
            print(f"    複勝率: {data['top3_rate']}%")
            print(f"    平均着順: {data['avg_rank']}")

    # テスト: グレード適応力評価
    print("\n" + "=" * 80)
    print("【2】 グレード適応力評価")
    assessment = analyzer.get_grade_level_assessment(racer_number, days=365)

    print(f"選手番号: {assessment['racer_number']}")
    assess_data = assessment['grade_assessment']

    if assess_data['strongest_grade']:
        print(f"\n最も強いグレード: {assess_data['strongest_grade']} (勝率: {assess_data['strongest_win_rate']}%)")
        print(f"最も弱いグレード: {assess_data['weakest_grade']} (勝率: {assess_data['weakest_win_rate']}%)")
        print(f"グレード一貫性: {assess_data['grade_consistency']}")
        print(f"上位グレード適性: {assess_data['upward_potential']}")

    # テスト: 会場のグレード分布
    print("\n" + "=" * 80)
    print("【3】 会場のグレード分布")
    venue_code = "03"
    venue_dist = analyzer.get_venue_grade_distribution(venue_code, days=90)

    print(f"会場コード: {venue_dist['venue_code']}")
    print(f"総レース数: {venue_dist['total_races']}R")

    if venue_dist['grade_distribution']:
        print("\nグレード分布:")
        sorted_grades = sorted(
            venue_dist['grade_distribution'].keys(),
            key=lambda g: analyzer.GRADE_HIERARCHY.get(g, 0),
            reverse=True
        )

        for grade in sorted_grades:
            data = venue_dist['grade_distribution'][grade]
            print(f"  {grade}: {data['count']}R ({data['rate']}%)")

    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)
