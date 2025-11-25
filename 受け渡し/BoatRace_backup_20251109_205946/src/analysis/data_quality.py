"""
データ品質モニタリングモジュール

収集データの充実度・欠損状況を分析
"""

import sqlite3
from typing import Dict, List
from datetime import datetime, timedelta
from collections import defaultdict


class DataQualityMonitor:
    """データ品質監視クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def get_overall_statistics(self) -> Dict:
        """全体統計を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {}

        # 総レース数
        cursor.execute("SELECT COUNT(*) FROM races")
        stats['total_races'] = cursor.fetchone()[0]

        # 結果データのあるレース数
        cursor.execute("""
            SELECT COUNT(DISTINCT race_id)
            FROM results
            WHERE is_invalid = 0
        """)
        stats['races_with_results'] = cursor.fetchone()[0]

        # 出走表データのあるレース数
        cursor.execute("""
            SELECT COUNT(DISTINCT race_id)
            FROM entries
        """)
        stats['races_with_entries'] = cursor.fetchone()[0]

        # 登録選手数
        cursor.execute("SELECT COUNT(DISTINCT racer_number) FROM entries")
        stats['unique_racers'] = cursor.fetchone()[0]

        # 日付範囲
        cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
        min_date, max_date = cursor.fetchone()
        stats['date_range'] = {
            'start': min_date,
            'end': max_date
        }

        # データ完全性
        stats['data_completeness'] = {
            'entries_rate': stats['races_with_entries'] / stats['total_races'] if stats['total_races'] > 0 else 0,
            'results_rate': stats['races_with_results'] / stats['total_races'] if stats['total_races'] > 0 else 0
        }

        conn.close()
        return stats

    def get_daily_progress(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """日別の収集進捗を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if start_date and end_date:
            query = """
                SELECT
                    race_date,
                    COUNT(*) as total_races,
                    COUNT(DISTINCT venue_code) as venues,
                    SUM(CASE WHEN EXISTS (
                        SELECT 1 FROM results r
                        WHERE r.race_id = races.id AND r.is_invalid = 0
                    ) THEN 1 ELSE 0 END) as races_with_results
                FROM races
                WHERE race_date BETWEEN ? AND ?
                GROUP BY race_date
                ORDER BY race_date
            """
            cursor.execute(query, (start_date, end_date))
        else:
            query = """
                SELECT
                    race_date,
                    COUNT(*) as total_races,
                    COUNT(DISTINCT venue_code) as venues,
                    SUM(CASE WHEN EXISTS (
                        SELECT 1 FROM results r
                        WHERE r.race_id = races.id AND r.is_invalid = 0
                    ) THEN 1 ELSE 0 END) as races_with_results
                FROM races
                GROUP BY race_date
                ORDER BY race_date
            """
            cursor.execute(query)

        rows = cursor.fetchall()
        conn.close()

        progress = []
        for race_date, total_races, venues, races_with_results in rows:
            progress.append({
                'date': race_date,
                'total_races': total_races,
                'venues': venues,
                'races_with_results': races_with_results,
                'completeness': races_with_results / total_races if total_races > 0 else 0
            })

        return progress

    def get_venue_coverage(self) -> List[Dict]:
        """競艇場別のデータ充実度を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                venue_code,
                COUNT(*) as total_races,
                COUNT(DISTINCT race_date) as race_days,
                SUM(CASE WHEN EXISTS (
                    SELECT 1 FROM results r
                    WHERE r.race_id = races.id AND r.is_invalid = 0
                ) THEN 1 ELSE 0 END) as races_with_results,
                MIN(race_date) as first_date,
                MAX(race_date) as last_date
            FROM races
            GROUP BY venue_code
            ORDER BY venue_code
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        coverage = []
        for venue_code, total_races, race_days, races_with_results, first_date, last_date in rows:
            coverage.append({
                'venue_code': venue_code,
                'total_races': total_races,
                'race_days': race_days,
                'races_with_results': races_with_results,
                'completeness': races_with_results / total_races if total_races > 0 else 0,
                'date_range': {
                    'start': first_date,
                    'end': last_date
                }
            })

        return coverage

    def detect_missing_data(self, start_date: str, end_date: str) -> Dict:
        """欠損データを検出"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        missing_data = {
            'missing_race_days': [],
            'incomplete_days': [],
            'races_without_results': []
        }

        # 期間内の全日付を生成
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        all_dates = []
        current_dt = start_dt
        while current_dt <= end_dt:
            all_dates.append(current_dt.strftime("%Y-%m-%d"))
            current_dt += timedelta(days=1)

        # 各日付のデータ状況を確認
        for date in all_dates:
            cursor.execute("""
                SELECT COUNT(*) FROM races WHERE race_date = ?
            """, (date,))
            race_count = cursor.fetchone()[0]

            if race_count == 0:
                # レースデータなし（開催なしの可能性）
                missing_data['missing_race_days'].append(date)
            else:
                # 結果データの充実度をチェック
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM races r
                    WHERE r.race_date = ?
                    AND EXISTS (
                        SELECT 1 FROM results res
                        WHERE res.race_id = r.id AND res.is_invalid = 0
                    )
                """, (date,))
                complete_count = cursor.fetchone()[0]

                if complete_count < race_count:
                    missing_data['incomplete_days'].append({
                        'date': date,
                        'total_races': race_count,
                        'complete_races': complete_count,
                        'missing_count': race_count - complete_count
                    })

        # 結果データのないレース
        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            WHERE NOT EXISTS (
                SELECT 1 FROM results res
                WHERE res.race_id = r.id AND res.is_invalid = 0
            )
            AND r.race_date BETWEEN ? AND ?
            ORDER BY r.race_date, r.venue_code, r.race_number
            LIMIT 100
        """, (start_date, end_date))

        for race_id, venue_code, race_date, race_number in cursor.fetchall():
            missing_data['races_without_results'].append({
                'race_id': race_id,
                'venue_code': venue_code,
                'race_date': race_date,
                'race_number': race_number
            })

        conn.close()
        return missing_data

    def get_racer_data_quality(self, min_races: int = 10) -> List[Dict]:
        """選手データの品質を確認"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                e.racer_number,
                e.racer_name,
                COUNT(DISTINCT e.race_id) as appearances,
                COUNT(DISTINCT r.race_id) as races_with_results,
                AVG(CASE WHEN e.avg_st IS NOT NULL THEN 1 ELSE 0 END) as st_data_rate
            FROM entries e
            LEFT JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number AND r.is_invalid = 0
            GROUP BY e.racer_number, e.racer_name
            HAVING appearances >= ?
            ORDER BY appearances DESC
            LIMIT 100
        """

        cursor.execute(query, (min_races,))
        rows = cursor.fetchall()
        conn.close()

        racer_quality = []
        for racer_number, racer_name, appearances, races_with_results, st_data_rate in rows:
            racer_quality.append({
                'racer_number': racer_number,
                'racer_name': racer_name,
                'appearances': appearances,
                'races_with_results': races_with_results,
                'result_data_rate': races_with_results / appearances if appearances > 0 else 0,
                'st_data_rate': st_data_rate
            })

        return racer_quality

    def generate_quality_report(self) -> str:
        """データ品質レポートを生成"""
        report = []
        report.append("=" * 80)
        report.append("データ品質レポート")
        report.append("=" * 80)

        # 全体統計
        stats = self.get_overall_statistics()
        report.append(f"\n【全体統計】")
        report.append(f"  総レース数: {stats['total_races']}")
        report.append(f"  出走表データ: {stats['races_with_entries']}レース ({stats['data_completeness']['entries_rate']:.1%})")
        report.append(f"  結果データ: {stats['races_with_results']}レース ({stats['data_completeness']['results_rate']:.1%})")
        report.append(f"  登録選手数: {stats['unique_racers']}人")

        if stats['date_range']['start']:
            report.append(f"  データ期間: {stats['date_range']['start']} ～ {stats['date_range']['end']}")

        # 競艇場別カバレッジ
        venue_coverage = self.get_venue_coverage()
        report.append(f"\n【競艇場別データ充実度】")
        report.append(f"  {'場':>4} | {'レース数':>8} | {'開催日数':>8} | {'完全性':>6}")
        report.append("  " + "-" * 40)

        for vc in sorted(venue_coverage, key=lambda x: x['total_races'], reverse=True)[:10]:
            report.append(f"  {vc['venue_code']:>4} | {vc['total_races']:>8} | {vc['race_days']:>8} | {vc['completeness']:>6.1%}")

        return "\n".join(report)
