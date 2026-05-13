#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
データ品質チェックスクリプト（全体版）

全年度（2020-2025）のデータ品質を包括的にチェックします。
- データ充足率
- テーブル間整合性
- 欠損パターン分析
- 異常値検出
- レポート出力（JSON）
"""
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH


class DataQualityChecker:
    """データ品質チェッカー"""

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.report = {
            'timestamp': datetime.now().isoformat(),
            'database': str(db_path),
            'checks': {}
        }

    def run_all_checks(self) -> Dict[str, Any]:
        """全チェックを実行"""
        print("=" * 100)
        print("データ品質チェック（全体版）")
        print("=" * 100)
        print()

        self.check_data_coverage()
        self.check_table_consistency()
        self.check_missing_patterns()
        self.check_related_tables()  # ★新規追加（見落とし防止）
        self.check_abnormal_values()
        self.check_unused_columns()

        return self.report

    def check_data_coverage(self):
        """1. データ充足率チェック（年度別）"""
        print("[1] データ充足率チェック（年度別）")
        print("-" * 100)

        years = [2020, 2021, 2022, 2023, 2024, 2025]
        coverage_data = []

        for year in years:
            start_date = f"{year}-01-01"
            end_date = f"{year+1}-01-01"

            # レース数
            self.cursor.execute("""
                SELECT COUNT(*) FROM races
                WHERE race_date >= ? AND race_date < ?
            """, (start_date, end_date))
            total_races = self.cursor.fetchone()[0]

            # 結果データ
            self.cursor.execute("""
                SELECT COUNT(DISTINCT race_id) FROM results r
                JOIN races ON r.race_id = races.id
                WHERE races.race_date >= ? AND races.race_date < ?
            """, (start_date, end_date))
            races_with_results = self.cursor.fetchone()[0]

            # オッズデータ
            self.cursor.execute("""
                SELECT COUNT(DISTINCT race_id) FROM trifecta_odds t
                JOIN races ON t.race_id = races.id
                WHERE races.race_date >= ? AND races.race_date < ?
            """, (start_date, end_date))
            races_with_odds = self.cursor.fetchone()[0]

            # 予測データ（advance）
            self.cursor.execute("""
                SELECT COUNT(DISTINCT race_id) FROM race_predictions rp
                JOIN races ON rp.race_id = races.id
                WHERE races.race_date >= ? AND races.race_date < ?
                    AND rp.prediction_type = 'advance'
            """, (start_date, end_date))
            races_with_advance = self.cursor.fetchone()[0]

            # 予測データ（before）
            self.cursor.execute("""
                SELECT COUNT(DISTINCT race_id) FROM race_predictions rp
                JOIN races ON rp.race_id = races.id
                WHERE races.race_date >= ? AND races.race_date < ?
                    AND rp.prediction_type = 'before'
            """, (start_date, end_date))
            races_with_before = self.cursor.fetchone()[0]

            # エントリーデータ
            self.cursor.execute("""
                SELECT COUNT(DISTINCT race_id) FROM entries e
                JOIN races ON e.race_id = races.id
                WHERE races.race_date >= ? AND races.race_date < ?
            """, (start_date, end_date))
            races_with_entries = self.cursor.fetchone()[0]

            # レース詳細データ
            self.cursor.execute("""
                SELECT COUNT(DISTINCT race_id) FROM race_details rd
                JOIN races ON rd.race_id = races.id
                WHERE races.race_date >= ? AND races.race_date < ?
            """, (start_date, end_date))
            races_with_details = self.cursor.fetchone()[0]

            result_cov = races_with_results / total_races * 100 if total_races > 0 else 0
            odds_cov = races_with_odds / total_races * 100 if total_races > 0 else 0
            advance_cov = races_with_advance / total_races * 100 if total_races > 0 else 0
            before_cov = races_with_before / total_races * 100 if total_races > 0 else 0
            entries_cov = races_with_entries / total_races * 100 if total_races > 0 else 0
            details_cov = races_with_details / total_races * 100 if total_races > 0 else 0

            year_data = {
                'year': year,
                'total_races': total_races,
                'results': {'count': races_with_results, 'coverage': round(result_cov, 1)},
                'odds': {'count': races_with_odds, 'coverage': round(odds_cov, 1)},
                'advance_predictions': {'count': races_with_advance, 'coverage': round(advance_cov, 1)},
                'before_predictions': {'count': races_with_before, 'coverage': round(before_cov, 1)},
                'entries': {'count': races_with_entries, 'coverage': round(entries_cov, 1)},
                'details': {'count': races_with_details, 'coverage': round(details_cov, 1)}
            }
            coverage_data.append(year_data)

            print(f"{year}年:")
            print(f"  総レース数: {total_races:,}件")
            print(f"  結果データ: {races_with_results:,}件 ({result_cov:.1f}%)")
            print(f"  オッズデータ: {races_with_odds:,}件 ({odds_cov:.1f}%)")
            print(f"  事前予測: {races_with_advance:,}件 ({advance_cov:.1f}%)")
            print(f"  直前予測: {races_with_before:,}件 ({before_cov:.1f}%)")
            print(f"  エントリー: {races_with_entries:,}件 ({entries_cov:.1f}%)")
            print(f"  レース詳細: {races_with_details:,}件 ({details_cov:.1f}%)")

            # 問題のある年度を検出
            if result_cov < 90 or odds_cov < 90:
                print(f"  [!] 警告: データ充足率が90%未満")

            print()

        self.report['checks']['data_coverage'] = coverage_data

    def check_table_consistency(self):
        """2. テーブル間整合性チェック"""
        print("[2] テーブル間整合性チェック")
        print("-" * 100)

        issues = []

        # 2-1. 孤立レコードチェック（resultsに存在するがracesに存在しない）
        self.cursor.execute("""
            SELECT COUNT(*) FROM results
            WHERE race_id NOT IN (SELECT id FROM races)
        """)
        orphan_results = self.cursor.fetchone()[0]
        print(f"孤立resultsレコード: {orphan_results}件")
        if orphan_results > 0:
            issues.append({'type': 'orphan_results', 'count': orphan_results})

        # 2-2. 孤立レコードチェック（trifecta_oddsに存在するがracesに存在しない）
        self.cursor.execute("""
            SELECT COUNT(*) FROM trifecta_odds
            WHERE race_id NOT IN (SELECT id FROM races)
        """)
        orphan_odds = self.cursor.fetchone()[0]
        print(f"孤立trifecta_oddsレコード: {orphan_odds}件")
        if orphan_odds > 0:
            issues.append({'type': 'orphan_odds', 'count': orphan_odds})

        # 2-3. 孤立レコードチェック（race_predictionsに存在するがracesに存在しない）
        self.cursor.execute("""
            SELECT COUNT(*) FROM race_predictions
            WHERE race_id NOT IN (SELECT id FROM races)
        """)
        orphan_predictions = self.cursor.fetchone()[0]
        print(f"孤立race_predictionsレコード: {orphan_predictions}件")
        if orphan_predictions > 0:
            issues.append({'type': 'orphan_predictions', 'count': orphan_predictions})

        # 2-4. エントリー数異常チェック（6艇でないレース）
        self.cursor.execute("""
            SELECT r.id, r.race_date, r.venue_code, r.race_number, COUNT(e.id) as entry_count
            FROM races r
            LEFT JOIN entries e ON r.id = e.race_id
            GROUP BY r.id
            HAVING COUNT(e.id) != 6
            ORDER BY r.race_date DESC
            LIMIT 10
        """)
        abnormal_entries = self.cursor.fetchall()
        abnormal_count = len(abnormal_entries)
        print(f"エントリー数異常レース: {abnormal_count}件（サンプル表示）")
        if abnormal_count > 0:
            for row in abnormal_entries[:5]:
                print(f"  {row['race_date']} 会場{row['venue_code']:02d} R{row['race_number']:02d}: {row['entry_count']}艇")
            issues.append({'type': 'abnormal_entries', 'count': abnormal_count})

        # 2-5. 結果データ異常チェック（6件でないレース）
        self.cursor.execute("""
            SELECT r.id, r.race_date, r.venue_code, r.race_number, COUNT(res.id) as result_count
            FROM races r
            LEFT JOIN results res ON r.id = res.race_id
            GROUP BY r.id
            HAVING COUNT(res.id) != 0 AND COUNT(res.id) != 6
            ORDER BY r.race_date DESC
            LIMIT 10
        """)
        abnormal_results = self.cursor.fetchall()
        abnormal_result_count = len(abnormal_results)
        print(f"結果データ異常レース: {abnormal_result_count}件（サンプル表示）")
        if abnormal_result_count > 0:
            for row in abnormal_results[:5]:
                print(f"  {row['race_date']} 会場{row['venue_code']:02d} R{row['race_number']:02d}: {row['result_count']}件")
            issues.append({'type': 'abnormal_results', 'count': abnormal_result_count})

        print()
        self.report['checks']['table_consistency'] = {
            'issues': issues,
            'total_issues': len(issues)
        }

    def check_missing_patterns(self):
        """3. 欠損パターン分析"""
        print("[3] 欠損パターン分析")
        print("-" * 100)

        # 3-1. 会場別のデータ欠損率
        print("3-1. 会場別のデータ欠損率（2020-2025年）")
        print("-" * 100)

        self.cursor.execute("""
            SELECT
                r.venue_code,
                v.name as venue_name,
                COUNT(r.id) as total_races,
                COUNT(DISTINCT res.race_id) as has_result,
                COUNT(DISTINCT t.race_id) as has_odds,
                COUNT(DISTINCT rp.race_id) as has_pred
            FROM races r
            LEFT JOIN venues v ON r.venue_code = v.code
            LEFT JOIN results res ON r.id = res.race_id
            LEFT JOIN trifecta_odds t ON r.id = t.race_id
            LEFT JOIN race_predictions rp ON r.id = rp.race_id
                AND rp.prediction_type = 'advance'
            WHERE r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
            GROUP BY r.venue_code
            ORDER BY r.venue_code
        """)

        venue_stats = []
        print("会場 | 総レース | 結果率 | オッズ率 | 予測率")
        print("-" * 80)
        for row in self.cursor.fetchall():
            venue_code = row['venue_code']
            venue_name = row['venue_name'] or f"会場{venue_code:02d}"
            total = row['total_races']
            result_rate = row['has_result'] / total * 100 if total > 0 else 0
            odds_rate = row['has_odds'] / total * 100 if total > 0 else 0
            pred_rate = row['has_pred'] / total * 100 if total > 0 else 0

            venue_data = {
                'venue_code': venue_code,
                'venue_name': venue_name,
                'total_races': total,
                'result_rate': round(result_rate, 1),
                'odds_rate': round(odds_rate, 1),
                'pred_rate': round(pred_rate, 1)
            }
            venue_stats.append(venue_data)

            print(f"{venue_code:02d} {venue_name:6s} | {total:8,d} | {result_rate:5.1f}% | {odds_rate:6.1f}% | {pred_rate:5.1f}%")

        print()

        # 3-2. グレード別のデータ欠損率
        print("3-2. グレード別のデータ欠損率（2020-2025年）")
        print("-" * 100)

        self.cursor.execute("""
            SELECT
                r.race_grade,
                COUNT(r.id) as total_races,
                COUNT(DISTINCT res.race_id) as has_result,
                COUNT(DISTINCT t.race_id) as has_odds,
                COUNT(DISTINCT rp.race_id) as has_pred
            FROM races r
            LEFT JOIN results res ON r.id = res.race_id
            LEFT JOIN trifecta_odds t ON r.id = t.race_id
            LEFT JOIN race_predictions rp ON r.id = rp.race_id
                AND rp.prediction_type = 'advance'
            WHERE r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
            GROUP BY r.race_grade
            ORDER BY r.race_grade
        """)

        grade_stats = []
        print("グレード | 総レース | 結果率 | オッズ率 | 予測率")
        print("-" * 80)
        for row in self.cursor.fetchall():
            grade = row['race_grade'] or 'NULL'
            total = row['total_races']
            result_rate = row['has_result'] / total * 100 if total > 0 else 0
            odds_rate = row['has_odds'] / total * 100 if total > 0 else 0
            pred_rate = row['has_pred'] / total * 100 if total > 0 else 0

            grade_data = {
                'grade': grade,
                'total_races': total,
                'result_rate': round(result_rate, 1),
                'odds_rate': round(odds_rate, 1),
                'pred_rate': round(pred_rate, 1)
            }
            grade_stats.append(grade_data)

            print(f"{grade:8s} | {total:8,d} | {result_rate:5.1f}% | {odds_rate:6.1f}% | {pred_rate:5.1f}%")

        print()

        self.report['checks']['missing_patterns'] = {
            'venue_stats': venue_stats,
            'grade_stats': grade_stats
        }

    def check_related_tables(self):
        """4. 関連テーブル・類似データのチェック"""
        print("[4] 関連テーブル・類似データのチェック（見落とし防止）")
        print("-" * 100)

        related_checks = {}

        # 4-1. 天候データ（2つのソースを比較）
        print("4-1. 天候データ（2つのソースを比較）")
        print("-" * 100)

        # race_conditions.weather
        self.cursor.execute("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN weather IS NOT NULL THEN 1 END) as has_weather
            FROM race_conditions
        """)
        row = self.cursor.fetchone()
        rc_total = row['total']
        rc_weather = row['has_weather']
        rc_coverage = rc_weather / rc_total * 100 if rc_total > 0 else 0

        # weatherテーブル
        self.cursor.execute("""
            SELECT COUNT(*) FROM weather
        """)
        weather_count = self.cursor.fetchone()[0]

        # racesとweatherの結合可能性
        self.cursor.execute("""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            JOIN weather w ON r.venue_code = w.venue_code
                AND r.race_date = w.weather_date
            WHERE r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        """)
        races_with_weather = self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM races
            WHERE race_date >= '2020-01-01' AND race_date < '2026-01-01'
        """)
        total_races = self.cursor.fetchone()[0]
        weather_coverage = races_with_weather / total_races * 100 if total_races > 0 else 0

        print(f"race_conditions.weather: {rc_weather:,}件 / {rc_total:,}件 ({rc_coverage:.1f}%)")
        print(f"weatherテーブル: {weather_count:,}件")
        print(f"racesとweatherの結合: {races_with_weather:,}件 / {total_races:,}件 ({weather_coverage:.1f}%)")
        print()
        print(f"[!] 推奨: race_conditions.weatherではなく、**weatherテーブル**を使用")
        print()

        related_checks['weather_sources'] = {
            'race_conditions_weather': {'count': rc_weather, 'coverage': round(rc_coverage, 1)},
            'weather_table': {'count': weather_count},
            'weather_join_coverage': {'count': races_with_weather, 'coverage': round(weather_coverage, 1)}
        }

        # 4-2. 展示データ（2つのソースを比較）
        print("4-2. 展示データ（2つのソースを比較）")
        print("-" * 100)

        # race_details.exhibition_time
        self.cursor.execute("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN exhibition_time IS NOT NULL THEN 1 END) as has_exh
            FROM race_details
        """)
        row = self.cursor.fetchone()
        rd_total = row['total']
        rd_exh = row['has_exh']
        rd_coverage = rd_exh / rd_total * 100 if rd_total > 0 else 0

        # exhibition_data
        self.cursor.execute("""
            SELECT COUNT(*) FROM exhibition_data
        """)
        exh_data_count = self.cursor.fetchone()[0]

        print(f"race_details.exhibition_time: {rd_exh:,}件 / {rd_total:,}件 ({rd_coverage:.1f}%)")
        print(f"exhibition_dataテーブル: {exh_data_count:,}件")
        print()
        print(f"[!] 推奨: race_details.exhibition_timeを優先使用")
        print()

        related_checks['exhibition_sources'] = {
            'race_details_exhibition_time': {'count': rd_exh, 'coverage': round(rd_coverage, 1)},
            'exhibition_data_table': {'count': exh_data_count}
        }

        self.report['checks']['related_tables'] = related_checks

    def check_abnormal_values(self):
        """5. 異常値検出"""
        print("[5] 異常値検出")
        print("-" * 100)

        abnormal_data = {}

        # 4-1. オッズ異常値
        print("4-1. オッズ異常値")
        print("-" * 80)

        self.cursor.execute("""
            SELECT COUNT(*) FROM trifecta_odds
            WHERE odds <= 0 OR odds > 999999
        """)
        abnormal_odds_count = self.cursor.fetchone()[0]
        print(f"異常オッズ件数（0以下または999999超）: {abnormal_odds_count:,}件")
        abnormal_data['abnormal_odds'] = abnormal_odds_count

        self.cursor.execute("""
            SELECT MIN(odds) as min_odds, MAX(odds) as max_odds, AVG(odds) as avg_odds
            FROM trifecta_odds
        """)
        row = self.cursor.fetchone()
        print(f"オッズ範囲: {row['min_odds']:.1f} ～ {row['max_odds']:.1f}（平均: {row['avg_odds']:.1f}）")
        abnormal_data['odds_range'] = {
            'min': row['min_odds'],
            'max': row['max_odds'],
            'avg': row['avg_odds']
        }
        print()

        # 4-2. 展示タイム異常値
        print("4-2. 展示タイム異常値（race_details.exhibition_time）")
        print("-" * 80)

        self.cursor.execute("""
            SELECT COUNT(*) FROM race_details
            WHERE exhibition_time IS NOT NULL
                AND (exhibition_time <= 0 OR exhibition_time > 100)
        """)
        abnormal_exh_time = self.cursor.fetchone()[0]
        print(f"異常展示タイム件数（0以下または100超）: {abnormal_exh_time:,}件")
        abnormal_data['abnormal_exhibition_time'] = abnormal_exh_time

        self.cursor.execute("""
            SELECT
                MIN(exhibition_time) as min_time,
                MAX(exhibition_time) as max_time,
                AVG(exhibition_time) as avg_time
            FROM race_details
            WHERE exhibition_time IS NOT NULL
        """)
        row = self.cursor.fetchone()
        if row['min_time'] is not None:
            print(f"展示タイム範囲: {row['min_time']:.2f}秒 ～ {row['max_time']:.2f}秒（平均: {row['avg_time']:.2f}秒）")
            abnormal_data['exhibition_time_range'] = {
                'min': row['min_time'],
                'max': row['max_time'],
                'avg': row['avg_time']
            }
        else:
            print("展示タイムデータなし")
        print()

        # 4-3. 選手勝率異常値
        print("4-3. 選手勝率異常値（entries.win_rate）")
        print("-" * 80)

        self.cursor.execute("""
            SELECT COUNT(*) FROM entries
            WHERE win_rate IS NOT NULL
                AND (win_rate < 0 OR win_rate > 100)
        """)
        abnormal_win_rate = self.cursor.fetchone()[0]
        print(f"異常勝率件数（0未満または100超）: {abnormal_win_rate:,}件")
        abnormal_data['abnormal_win_rate'] = abnormal_win_rate

        self.cursor.execute("""
            SELECT
                MIN(win_rate) as min_rate,
                MAX(win_rate) as max_rate,
                AVG(win_rate) as avg_rate
            FROM entries
            WHERE win_rate IS NOT NULL
        """)
        row = self.cursor.fetchone()
        if row['min_rate'] is not None:
            print(f"勝率範囲: {row['min_rate']:.2f}% ～ {row['max_rate']:.2f}%（平均: {row['avg_rate']:.2f}%）")
            abnormal_data['win_rate_range'] = {
                'min': row['min_rate'],
                'max': row['max_rate'],
                'avg': row['avg_rate']
            }
        else:
            print("勝率データなし")
        print()

        # 4-4. STタイム異常値
        print("4-4. STタイム異常値（race_details.st_time）")
        print("-" * 80)

        self.cursor.execute("""
            SELECT COUNT(*) FROM race_details
            WHERE st_time IS NOT NULL
                AND (st_time < -1.0 OR st_time > 3.0)
        """)
        abnormal_st_time = self.cursor.fetchone()[0]
        print(f"異常STタイム件数（-1.0未満または3.0超）: {abnormal_st_time:,}件")
        abnormal_data['abnormal_st_time'] = abnormal_st_time

        self.cursor.execute("""
            SELECT
                MIN(st_time) as min_st,
                MAX(st_time) as max_st,
                AVG(st_time) as avg_st
            FROM race_details
            WHERE st_time IS NOT NULL
        """)
        row = self.cursor.fetchone()
        if row['min_st'] is not None:
            print(f"STタイム範囲: {row['min_st']:.2f}秒 ～ {row['max_st']:.2f}秒（平均: {row['avg_st']:.2f}秒）")
            abnormal_data['st_time_range'] = {
                'min': row['min_st'],
                'max': row['max_st'],
                'avg': row['avg_st']
            }
        else:
            print("STタイムデータなし")
        print()

        self.report['checks']['abnormal_values'] = abnormal_data

    def check_unused_columns(self):
        """6. 未活用カラムの検出"""
        print("[6] 未活用カラムの検出（充足率チェック）")
        print("-" * 100)

        # 重要テーブルのカラム充足率をチェック
        tables_to_check = {
            'entries': ['local_win_rate', 'f_count', 'boat_second_rate', 'motor_second_rate'],
            'race_details': ['chikusen_time', 'st_time', 'exhibition_time', 'prev_race_rank'],
            'race_conditions': ['wave_height', 'wind_speed', 'wind_direction', 'weather']
        }

        unused_columns = {}

        for table, columns in tables_to_check.items():
            print(f"テーブル: {table}")
            print("-" * 80)

            # テーブルの総レコード数
            self.cursor.execute(f"SELECT COUNT(*) FROM {table}")
            total_records = self.cursor.fetchone()[0]

            table_data = {'total_records': total_records, 'columns': {}}

            for column in columns:
                # NULL以外のレコード数
                self.cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL")
                non_null_count = self.cursor.fetchone()[0]
                coverage = non_null_count / total_records * 100 if total_records > 0 else 0

                table_data['columns'][column] = {
                    'non_null_count': non_null_count,
                    'coverage': round(coverage, 2)
                }

                status = "[OK]" if coverage >= 80 else "[--]" if coverage >= 50 else "[NG]"
                print(f"  {column:25s}: {non_null_count:10,d} / {total_records:10,d} ({coverage:6.2f}%) {status}")

            unused_columns[table] = table_data
            print()

        self.report['checks']['unused_columns'] = unused_columns

    def save_report(self, output_path: str = None):
        """レポートをJSON形式で保存"""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"data/data_quality_report_{timestamp}.json"

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.report, f, ensure_ascii=False, indent=2)

        print("=" * 100)
        print(f"レポート保存完了: {output_file}")
        print("=" * 100)

        return output_file

    def close(self):
        """データベース接続を閉じる"""
        self.conn.close()


def main():
    """メイン処理"""
    checker = DataQualityChecker()

    try:
        # 全チェックを実行
        checker.run_all_checks()

        # レポートを保存
        checker.save_report()

    finally:
        checker.close()


if __name__ == "__main__":
    main()
