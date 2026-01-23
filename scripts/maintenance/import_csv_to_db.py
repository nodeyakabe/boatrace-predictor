"""
CSVデータをDBにインポートするスクリプト

使用方法:
    python scripts/maintenance/import_csv_to_db.py --input data/csv/2020_09_to_2021_12 --dry-run
    python scripts/maintenance/import_csv_to_db.py --input data/csv/2020_09_to_2021_12
"""

import argparse
import sys
import csv
from pathlib import Path
import sqlite3
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


class CSVImporter:
    """CSV→DBインポーター"""

    def __init__(self, db_path, dry_run=False):
        self.db_path = db_path
        self.dry_run = dry_run
        self.stats = {
            'races': {'total': 0, 'inserted': 0, 'skipped': 0, 'errors': 0},
            'results': {'total': 0, 'inserted': 0, 'skipped': 0, 'errors': 0},
            'entries': {'total': 0, 'inserted': 0, 'skipped': 0, 'errors': 0},
            'payouts': {'total': 0, 'inserted': 0, 'skipped': 0, 'errors': 0},
            'race_conditions': {'total': 0, 'inserted': 0, 'skipped': 0, 'errors': 0},
            'race_details': {'total': 0, 'inserted': 0, 'skipped': 0, 'errors': 0}
        }

    def import_races(self, conn, csv_path):
        """レースデータを投入"""
        print("\nレースデータ投入中...")
        cursor = conn.cursor()

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                self.stats['races']['total'] += 1

                try:
                    if not self.dry_run:
                        cursor.execute('''
                            INSERT OR IGNORE INTO races
                            (venue_code, race_date, race_number, race_time, race_grade,
                             race_distance, race_status, is_nighter, is_ladies, is_rookie, is_shinnyuu_kotei)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            row['venue_code'],
                            row['race_date'],
                            int(row['race_number']),
                            row.get('race_time', ''),
                            row.get('race_grade', ''),
                            int(row['race_distance']) if row.get('race_distance') else None,
                            row.get('race_status', 'completed'),
                            int(row.get('is_nighter', 0)),
                            int(row.get('is_ladies', 0)),
                            int(row.get('is_rookie', 0)),
                            int(row.get('is_shinnyuu_kotei', 0))
                        ))

                        if cursor.rowcount > 0:
                            self.stats['races']['inserted'] += 1
                        else:
                            self.stats['races']['skipped'] += 1
                    else:
                        self.stats['races']['inserted'] += 1

                except Exception as e:
                    self.stats['races']['errors'] += 1
                    if self.stats['races']['errors'] <= 5:
                        print(f"  エラー: {row.get('venue_code')}-{row.get('race_date')}-{row.get('race_number')}: {e}")

                if self.stats['races']['total'] % 5000 == 0:
                    print(f"  処理中... {self.stats['races']['total']:,}件")
                    if not self.dry_run:
                        conn.commit()

        if not self.dry_run:
            conn.commit()

    def import_results(self, conn, csv_path):
        """結果データを投入"""
        print("\n結果データ投入中...")
        cursor = conn.cursor()

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                self.stats['results']['total'] += 1

                try:
                    if not self.dry_run:
                        # race_idを取得
                        cursor.execute('''
                            SELECT id FROM races
                            WHERE venue_code = ? AND race_date = ? AND race_number = ?
                        ''', (row['venue_code'], row['race_date'], int(row['race_number'])))

                        race_result = cursor.fetchone()
                        if not race_result:
                            self.stats['results']['skipped'] += 1
                            continue

                        race_id = race_result[0]

                        cursor.execute('''
                            INSERT OR IGNORE INTO race_results
                            (race_id, pit_number, finish_position, finish_time, start_timing)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (
                            race_id,
                            int(row['pit_number']),
                            int(row['finish_position']) if row.get('finish_position') else None,
                            float(row['finish_time']) if row.get('finish_time') else None,
                            float(row['start_timing']) if row.get('start_timing') else None
                        ))

                        if cursor.rowcount > 0:
                            self.stats['results']['inserted'] += 1
                        else:
                            self.stats['results']['skipped'] += 1
                    else:
                        self.stats['results']['inserted'] += 1

                except Exception as e:
                    self.stats['results']['errors'] += 1
                    if self.stats['results']['errors'] <= 5:
                        print(f"  エラー: {e}")

                if self.stats['results']['total'] % 10000 == 0:
                    print(f"  処理中... {self.stats['results']['total']:,}件")
                    if not self.dry_run:
                        conn.commit()

        if not self.dry_run:
            conn.commit()

    def import_entries(self, conn, csv_path):
        """出走表データを投入"""
        print("\n出走表データ投入中...")
        cursor = conn.cursor()

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                self.stats['entries']['total'] += 1

                try:
                    if not self.dry_run:
                        # race_idを取得
                        cursor.execute('''
                            SELECT id FROM races
                            WHERE venue_code = ? AND race_date = ? AND race_number = ?
                        ''', (row['venue_code'], row['race_date'], int(row['race_number'])))

                        race_result = cursor.fetchone()
                        if not race_result:
                            self.stats['entries']['skipped'] += 1
                            continue

                        race_id = race_result[0]

                        cursor.execute('''
                            INSERT OR IGNORE INTO race_entries
                            (race_id, pit_number, racer_id, racer_name, racer_class, weight,
                             boat_no, motor_no, exhibition_time, national_win_rate, national_place_rate_2,
                             national_place_rate_3, local_win_rate, local_place_rate_2, local_place_rate_3)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            race_id,
                            int(row['pit_number']),
                            int(row['racer_id']) if row.get('racer_id') else None,
                            row.get('racer_name', ''),
                            row.get('racer_class', ''),
                            float(row['weight']) if row.get('weight') else None,
                            int(row['boat_no']) if row.get('boat_no') else None,
                            int(row['motor_no']) if row.get('motor_no') else None,
                            float(row['exhibition_time']) if row.get('exhibition_time') else None,
                            float(row['national_win_rate']) if row.get('national_win_rate') else None,
                            float(row['national_place_rate_2']) if row.get('national_place_rate_2') else None,
                            float(row['national_place_rate_3']) if row.get('national_place_rate_3') else None,
                            float(row['local_win_rate']) if row.get('local_win_rate') else None,
                            float(row['local_place_rate_2']) if row.get('local_place_rate_2') else None,
                            float(row['local_place_rate_3']) if row.get('local_place_rate_3') else None
                        ))

                        if cursor.rowcount > 0:
                            self.stats['entries']['inserted'] += 1
                        else:
                            self.stats['entries']['skipped'] += 1
                    else:
                        self.stats['entries']['inserted'] += 1

                except Exception as e:
                    self.stats['entries']['errors'] += 1
                    if self.stats['entries']['errors'] <= 5:
                        print(f"  エラー: {e}")

                if self.stats['entries']['total'] % 10000 == 0:
                    print(f"  処理中... {self.stats['entries']['total']:,}件")
                    if not self.dry_run:
                        conn.commit()

        if not self.dry_run:
            conn.commit()

    def import_payouts(self, conn, csv_path):
        """払戻データを投入"""
        print("\n払戻データ投入中...")
        cursor = conn.cursor()

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                self.stats['payouts']['total'] += 1

                try:
                    if not self.dry_run:
                        # race_idを取得
                        cursor.execute('''
                            SELECT id FROM races
                            WHERE venue_code = ? AND race_date = ? AND race_number = ?
                        ''', (row['venue_code'], row['race_date'], int(row['race_number'])))

                        race_result = cursor.fetchone()
                        if not race_result:
                            self.stats['payouts']['skipped'] += 1
                            continue

                        race_id = race_result[0]

                        cursor.execute('''
                            INSERT OR IGNORE INTO payouts
                            (race_id, bet_type, combination, payout, popularity)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (
                            race_id,
                            row['bet_type'],
                            row['combination'],
                            int(row['payout']) if row.get('payout') else None,
                            int(row['popularity']) if row.get('popularity') else None
                        ))

                        if cursor.rowcount > 0:
                            self.stats['payouts']['inserted'] += 1
                        else:
                            self.stats['payouts']['skipped'] += 1
                    else:
                        self.stats['payouts']['inserted'] += 1

                except Exception as e:
                    self.stats['payouts']['errors'] += 1
                    if self.stats['payouts']['errors'] <= 5:
                        print(f"  エラー: {e}")

                if self.stats['payouts']['total'] % 10000 == 0:
                    print(f"  処理中... {self.stats['payouts']['total']:,}件")
                    if not self.dry_run:
                        conn.commit()

        if not self.dry_run:
            conn.commit()

    def import_from_directory(self, input_dir):
        """ディレクトリ内のCSVファイルを一括投入"""
        input_path = Path(input_dir)

        if not input_path.exists():
            print(f"エラー: ディレクトリが存在しません: {input_dir}")
            return

        print("=" * 70)
        print("CSVデータDB投入")
        print("=" * 70)
        print(f"入力ディレクトリ: {input_dir}")
        print(f"DBファイル: {self.db_path}")
        print(f"モード: {'検証モード（dry-run）' if self.dry_run else '本番投入'}")
        print("=" * 70)

        conn = sqlite3.connect(self.db_path)

        try:
            # レースデータ（必須）
            races_csv = input_path / 'races.csv'
            if races_csv.exists():
                self.import_races(conn, races_csv)
            else:
                print("エラー: races.csvが見つかりません")
                return

            # 結果データ
            results_csv = input_path / 'results.csv'
            if results_csv.exists():
                self.import_results(conn, results_csv)

            # 出走表データ
            entries_csv = input_path / 'entries.csv'
            if entries_csv.exists():
                self.import_entries(conn, entries_csv)

            # 払戻データ
            payouts_csv = input_path / 'payouts.csv'
            if payouts_csv.exists():
                self.import_payouts(conn, payouts_csv)

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
    parser = argparse.ArgumentParser(description='CSVデータDB投入')
    parser.add_argument('--input', required=True, help='CSV入力ディレクトリ')
    parser.add_argument('--db', default='data/boatrace.db', help='DBファイルパス')
    parser.add_argument('--dry-run', action='store_true', help='検証モード（実際には投入しない）')

    args = parser.parse_args()

    importer = CSVImporter(args.db, args.dry_run)
    importer.import_from_directory(args.input)


if __name__ == "__main__":
    main()
