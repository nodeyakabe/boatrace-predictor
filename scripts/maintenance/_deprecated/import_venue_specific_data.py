"""
競艇場独自データのDB投入スクリプト

CSV経由で収集した競艇場独自データをDBに投入します。

使用方法:
    # 検証モード（実際には投入しない）
    python scripts/maintenance/import_venue_specific_data.py \\
        --input data/csv/venue_specific_2024 \\
        --dry-run

    # 本番投入
    python scripts/maintenance/import_venue_specific_data.py \\
        --input data/csv/venue_specific_2024
"""

import argparse
import sys
import csv
from pathlib import Path
from datetime import datetime
import sqlite3

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.database.connection import get_db_connection


class VenueSpecificDataImporter:
    """競艇場独自データインポーター"""

    def __init__(self, db_path, dry_run=False):
        """
        初期化

        Args:
            db_path: DBファイルパス
            dry_run: True の場合は検証のみ
        """
        self.db_path = db_path
        self.dry_run = dry_run
        self.stats = {
            'tide': {'total': 0, 'inserted': 0, 'skipped': 0, 'errors': 0},
            'weather': {'total': 0, 'inserted': 0, 'skipped': 0, 'errors': 0},
            'zenken': {'total': 0, 'inserted': 0, 'skipped': 0, 'errors': 0},
            'course': {'total': 0, 'inserted': 0, 'skipped': 0, 'errors': 0}
        }

    def _create_tables_if_not_exists(self, conn):
        """必要なテーブルを作成"""
        cursor = conn.cursor()

        # 潮汐データテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tide_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_code TEXT NOT NULL,
                race_date TEXT NOT NULL,
                tide_time TEXT NOT NULL,
                tide_type TEXT NOT NULL,
                tide_level_cm REAL,
                UNIQUE(venue_code, race_date, tide_time)
            )
        ''')

        # 気象データテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS venue_weather_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_code TEXT NOT NULL,
                race_date TEXT NOT NULL,
                wind_speed REAL,
                wind_direction TEXT,
                temperature REAL,
                water_temperature REAL,
                weather TEXT,
                wave_height REAL,
                UNIQUE(venue_code, race_date)
            )
        ''')

        # 前検タイムテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS zenken_time_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_code TEXT NOT NULL,
                race_date TEXT NOT NULL,
                racer_id INTEGER NOT NULL,
                pit INTEGER,
                zenken_time REAL,
                motor_no INTEGER,
                UNIQUE(venue_code, race_date, racer_id)
            )
        ''')

        # 進入コース別成績テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS course_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_code TEXT NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                course INTEGER NOT NULL,
                win_rate REAL,
                place_rate_2 REAL,
                place_rate_3 REAL,
                samples INTEGER,
                UNIQUE(venue_code, year, month, course)
            )
        ''')

        conn.commit()

    def import_tide_data(self, conn, csv_path):
        """潮汐データを投入"""
        print("\n潮汐データ投入中...")

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                self.stats['tide']['total'] += 1

                try:
                    if not self.dry_run:
                        conn.execute('''
                            INSERT OR IGNORE INTO tide_data
                            (venue_code, race_date, tide_time, tide_type, tide_level_cm)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (
                            row['venue_code'],
                            row['race_date'],
                            row['tide_time'],
                            row['tide_type'],
                            float(row['tide_level_cm']) if row['tide_level_cm'] else None
                        ))

                        if conn.total_changes > 0:
                            self.stats['tide']['inserted'] += 1
                        else:
                            self.stats['tide']['skipped'] += 1
                    else:
                        self.stats['tide']['inserted'] += 1

                except Exception as e:
                    self.stats['tide']['errors'] += 1
                    print(f"  エラー: {row}: {e}")

                if self.stats['tide']['total'] % 1000 == 0:
                    print(f"  処理中... {self.stats['tide']['total']}件")

        if not self.dry_run:
            conn.commit()

    def import_weather_data(self, conn, csv_path):
        """気象データを投入"""
        print("\n気象データ投入中...")

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                self.stats['weather']['total'] += 1

                try:
                    if not self.dry_run:
                        conn.execute('''
                            INSERT OR REPLACE INTO venue_weather_data
                            (venue_code, race_date, wind_speed, wind_direction,
                             temperature, water_temperature, weather, wave_height)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            row['venue_code'],
                            row['race_date'],
                            float(row['wind_speed']) if row['wind_speed'] else None,
                            row['wind_direction'] if row['wind_direction'] else None,
                            float(row['temperature']) if row['temperature'] else None,
                            float(row['water_temperature']) if row['water_temperature'] else None,
                            row['weather'] if row['weather'] else None,
                            float(row['wave_height']) if row['wave_height'] else None
                        ))

                        self.stats['weather']['inserted'] += 1
                    else:
                        self.stats['weather']['inserted'] += 1

                except Exception as e:
                    self.stats['weather']['errors'] += 1
                    print(f"  エラー: {row}: {e}")

                if self.stats['weather']['total'] % 1000 == 0:
                    print(f"  処理中... {self.stats['weather']['total']}件")

        if not self.dry_run:
            conn.commit()

    def import_zenken_time(self, conn, csv_path):
        """前検タイムデータを投入"""
        print("\n前検タイムデータ投入中...")

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                self.stats['zenken']['total'] += 1

                try:
                    if not self.dry_run:
                        conn.execute('''
                            INSERT OR REPLACE INTO zenken_time_data
                            (venue_code, race_date, racer_id, pit, zenken_time, motor_no)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            row['venue_code'],
                            row['race_date'],
                            int(row['racer_id']),
                            int(row['pit']) if row['pit'] else None,
                            float(row['zenken_time']) if row['zenken_time'] else None,
                            int(row['motor_no']) if row['motor_no'] else None
                        ))

                        self.stats['zenken']['inserted'] += 1
                    else:
                        self.stats['zenken']['inserted'] += 1

                except Exception as e:
                    self.stats['zenken']['errors'] += 1
                    print(f"  エラー: {row}: {e}")

                if self.stats['zenken']['total'] % 1000 == 0:
                    print(f"  処理中... {self.stats['zenken']['total']}件")

        if not self.dry_run:
            conn.commit()

    def import_course_stats(self, conn, csv_path):
        """進入コース別成績を投入"""
        print("\n進入コース別成績投入中...")

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                self.stats['course']['total'] += 1

                try:
                    if not self.dry_run:
                        conn.execute('''
                            INSERT OR REPLACE INTO course_statistics
                            (venue_code, year, month, course,
                             win_rate, place_rate_2, place_rate_3, samples)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            row['venue_code'],
                            int(row['year']),
                            int(row['month']),
                            int(row['course']),
                            float(row['win_rate']) if row['win_rate'] else None,
                            float(row['place_rate_2']) if row['place_rate_2'] else None,
                            float(row['place_rate_3']) if row['place_rate_3'] else None,
                            int(row['samples']) if row['samples'] else None
                        ))

                        self.stats['course']['inserted'] += 1
                    else:
                        self.stats['course']['inserted'] += 1

                except Exception as e:
                    self.stats['course']['errors'] += 1
                    print(f"  エラー: {row}: {e}")

                if self.stats['course']['total'] % 1000 == 0:
                    print(f"  処理中... {self.stats['course']['total']}件")

        if not self.dry_run:
            conn.commit()

    def import_from_directory(self, input_dir):
        """ディレクトリ内のCSVファイルを一括投入"""
        input_path = Path(input_dir)

        if not input_path.exists():
            print(f"エラー: ディレクトリが存在しません: {input_dir}")
            return

        print("=" * 70)
        print("競艇場独自データDB投入")
        print("=" * 70)
        print(f"入力ディレクトリ: {input_dir}")
        print(f"DBファイル: {self.db_path}")
        print(f"モード: {'検証モード（dry-run）' if self.dry_run else '本番投入'}")
        print("=" * 70)

        conn = sqlite3.connect(self.db_path)

        try:
            # テーブル作成
            if not self.dry_run:
                self._create_tables_if_not_exists(conn)

            # 潮汐データ
            tide_csv = input_path / 'tide_data.csv'
            if tide_csv.exists():
                self.import_tide_data(conn, tide_csv)

            # 気象データ
            weather_csv = input_path / 'weather_data.csv'
            if weather_csv.exists():
                self.import_weather_data(conn, weather_csv)

            # 前検タイム
            zenken_csv = input_path / 'zenken_time.csv'
            if zenken_csv.exists():
                self.import_zenken_time(conn, zenken_csv)

            # 進入コース別成績
            course_csv = input_path / 'course_stats.csv'
            if course_csv.exists():
                self.import_course_stats(conn, course_csv)

        finally:
            conn.close()

        # 統計表示
        print("\n" + "=" * 70)
        print("投入結果サマリー")
        print("=" * 70)

        for data_type, stats in self.stats.items():
            if stats['total'] > 0:
                print(f"\n【{data_type}】")
                print(f"  総件数:     {stats['total']:,}")
                print(f"  投入成功:   {stats['inserted']:,}")
                print(f"  スキップ:   {stats['skipped']:,}")
                print(f"  エラー:     {stats['errors']:,}")

        if self.dry_run:
            print("\n※ 検証モードのため、実際には投入していません")

        print("\n完了")


def main():
    parser = argparse.ArgumentParser(description='競艇場独自データDB投入')
    parser.add_argument('--input', required=True, help='CSV入力ディレクトリ')
    parser.add_argument('--db', default='data/boatrace.db', help='DBファイルパス')
    parser.add_argument('--dry-run', action='store_true', help='検証モード（実際には投入しない）')

    args = parser.parse_args()

    importer = VenueSpecificDataImporter(args.db, args.dry_run)
    importer.import_from_directory(args.input)


if __name__ == "__main__":
    main()
