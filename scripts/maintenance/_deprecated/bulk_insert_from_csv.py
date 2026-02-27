# -*- coding: utf-8 -*-
"""CSVファイルからDBへ一括投入（不整合防止機能付き）

不整合防止の仕組み:
1. venue_code + race_date + race_number の組み合わせでレースを一意に識別
2. 既存レースIDを検索・再利用（新規の場合のみINSERT）
3. トランザクション管理（全成功 or 全失敗）
4. 外部キー制約の検証

使用例:
    # CSVからDB投入
    python scripts/maintenance/bulk_insert_from_csv.py --input data/csv/2020

    # dry-runモード（実際には投入せず検証のみ）
    python scripts/maintenance/bulk_insert_from_csv.py --input data/csv/2020 --dry-run

    # 既存データの上書き
    python scripts/maintenance/bulk_insert_from_csv.py --input data/csv/2020 --overwrite
"""

import sys
import os
import csv
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

# Windows文字コード対策
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))


class CSVToDatabaseImporter:
    """CSV→DB一括投入クラス（不整合防止機能付き）"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.race_id_cache = {}  # (venue_code, race_date, race_number) -> race_id

    def connect(self):
        """DB接続"""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        # タイムアウト設定（30秒）
        self.conn.execute("PRAGMA busy_timeout = 30000")
        # WALモード（書き込み時のロック削減）
        self.cursor.execute("PRAGMA journal_mode=WAL")
        self.cursor.execute("PRAGMA foreign_keys=ON")  # 外部キー制約を有効化
        print("DB接続完了（外部キー制約: ON）")

    def close(self):
        """DB切断"""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None

    def begin_transaction(self):
        """トランザクション開始"""
        self.cursor.execute("BEGIN TRANSACTION")

    def commit(self):
        """コミット"""
        self.conn.commit()

    def rollback(self):
        """ロールバック"""
        self.conn.rollback()

    def get_or_create_race_id(self, venue_code: str, race_date: str, race_number: int) -> int:
        """レースIDを取得（存在しない場合は作成）

        Args:
            venue_code: 会場コード
            race_date: レース日（YYYYMMDD形式）
            race_number: レース番号

        Returns:
            race_id: レースID
        """
        # キャッシュチェック
        cache_key = (venue_code, race_date, race_number)
        if cache_key in self.race_id_cache:
            return self.race_id_cache[cache_key]

        # YYYYMMDD → YYYY-MM-DD に変換
        if len(race_date) == 8:
            race_date_formatted = f"{race_date[:4]}-{race_date[4:6]}-{race_date[6:8]}"
        else:
            race_date_formatted = race_date

        # 既存レースIDを検索
        self.cursor.execute('''
            SELECT id FROM races
            WHERE venue_code = ? AND race_date = ? AND race_number = ?
        ''', (venue_code, race_date_formatted, race_number))

        row = self.cursor.fetchone()
        if row:
            race_id = row[0]
            self.race_id_cache[cache_key] = race_id
            return race_id

        # 新規レースの場合はNoneを返す（後でINSERTする）
        return None

    def import_races(self, csv_path: Path, overwrite: bool = False):
        """racesテーブルにインポート

        Args:
            csv_path: races.csvのパス
            overwrite: True の場合、既存データを上書き

        Returns:
            (inserted_count, updated_count, skipped_count)
        """
        if not csv_path.exists():
            print(f"ファイルが見つかりません: {csv_path}")
            return 0, 0, 0

        inserted = 0
        updated = 0
        skipped = 0

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                venue_code = row['venue_code']
                race_date = row['race_date']
                race_number = int(row['race_number'])

                # YYYYMMDD → YYYY-MM-DD 変換
                if len(race_date) == 8:
                    race_date_formatted = f"{race_date[:4]}-{race_date[4:6]}-{race_date[6:8]}"
                else:
                    race_date_formatted = race_date

                # 既存チェック
                existing_id = self.get_or_create_race_id(venue_code, race_date, race_number)

                if existing_id and not overwrite:
                    # 既存データがあり、上書きしない
                    skipped += 1
                    continue

                if existing_id and overwrite:
                    # 上書きモード: UPDATE
                    self.cursor.execute('''
                        UPDATE races
                        SET race_time = ?, race_grade = ?, race_distance = ?,
                            is_nighter = ?, is_ladies = ?, is_rookie = ?, is_shinnyuu_kotei = ?
                        WHERE id = ?
                    ''', (
                        row.get('race_time', ''),
                        row.get('race_grade', ''),
                        int(row.get('race_distance', 1800)),
                        int(row.get('is_nighter', 0)),
                        int(row.get('is_ladies', 0)),
                        int(row.get('is_rookie', 0)),
                        int(row.get('is_shinnyuu_kotei', 0)),
                        existing_id
                    ))
                    updated += 1
                else:
                    # 新規INSERT
                    self.cursor.execute('''
                        INSERT INTO races (venue_code, race_date, race_number, race_time,
                                          race_grade, race_distance, is_nighter, is_ladies,
                                          is_rookie, is_shinnyuu_kotei, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (
                        venue_code,
                        race_date_formatted,
                        race_number,
                        row.get('race_time', ''),
                        row.get('race_grade', ''),
                        int(row.get('race_distance', 1800)),
                        int(row.get('is_nighter', 0)),
                        int(row.get('is_ladies', 0)),
                        int(row.get('is_rookie', 0)),
                        int(row.get('is_shinnyuu_kotei', 0)),
                    ))
                    # 新規レースIDをキャッシュ
                    new_id = self.cursor.lastrowid
                    cache_key = (venue_code, race_date, race_number)
                    self.race_id_cache[cache_key] = new_id
                    inserted += 1

        return inserted, updated, skipped

    def import_child_table(self, csv_path: Path, table_name: str, columns: list,
                          overwrite: bool = False):
        """子テーブルにインポート（race_idの解決付き）

        Args:
            csv_path: CSVファイルパス
            table_name: テーブル名
            columns: カラム名リスト（venue_code, race_date, race_number 以外）
            overwrite: True の場合、既存データを上書き

        Returns:
            (inserted_count, updated_count, skipped_count)
        """
        if not csv_path.exists():
            print(f"ファイルが見つかりません: {csv_path}")
            return 0, 0, 0

        inserted = 0
        updated = 0
        skipped = 0

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                venue_code = row['venue_code']
                race_date = row['race_date']
                race_number = int(row['race_number'])

                # race_idを解決
                race_id = self.get_or_create_race_id(venue_code, race_date, race_number)
                if not race_id:
                    print(f"警告: race_id が見つかりません (venue={venue_code}, "
                          f"date={race_date}, race={race_number})")
                    skipped += 1
                    continue

                # データを準備
                values = [race_id]
                for col in columns:
                    val = row.get(col, '')
                    # 数値型カラムの処理
                    if val == '' or val is None:
                        values.append(None)
                    else:
                        try:
                            # INT/REAL型の場合
                            if '.' in str(val):
                                values.append(float(val))
                            else:
                                values.append(int(val))
                        except ValueError:
                            # TEXT型の場合
                            values.append(val)

                # INSERT（重複は無視 or 上書き）
                placeholders = ','.join(['?'] * (len(columns) + 1))
                col_names = ','.join(['race_id'] + columns)

                if overwrite:
                    # REPLACE (DELETE + INSERT)
                    sql = f"REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})"
                else:
                    # INSERT OR IGNORE
                    sql = f"INSERT OR IGNORE INTO {table_name} ({col_names}) VALUES ({placeholders})"

                self.cursor.execute(sql, values)
                if self.cursor.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1

        return inserted, updated, skipped

    def verify_integrity(self) -> bool:
        """データ整合性の検証

        Returns:
            True: 整合性OK, False: 問題あり
        """
        print("\n=== データ整合性検証 ===")

        # 1. 外部キー制約チェック
        self.cursor.execute("PRAGMA foreign_key_check")
        violations = self.cursor.fetchall()
        if violations:
            print(f"❌ 外部キー制約違反: {len(violations)}件")
            for v in violations[:5]:
                print(f"  {v}")
            return False
        print("✅ 外部キー制約: OK")

        # 2. entries のレース存在チェック
        self.cursor.execute('''
            SELECT COUNT(*)
            FROM entries e
            LEFT JOIN races r ON e.race_id = r.id
            WHERE r.id IS NULL
        ''')
        orphan_entries = self.cursor.fetchone()[0]
        if orphan_entries > 0:
            print(f"❌ 孤立したentries: {orphan_entries}件")
            return False
        print("✅ entries の整合性: OK")

        # 3. results のレース存在チェック
        self.cursor.execute('''
            SELECT COUNT(*)
            FROM results res
            LEFT JOIN races r ON res.race_id = r.id
            WHERE r.id IS NULL
        ''')
        orphan_results = self.cursor.fetchone()[0]
        if orphan_results > 0:
            print(f"❌ 孤立したresults: {orphan_results}件")
            return False
        print("✅ results の整合性: OK")

        print("\n✅ 整合性検証: すべてOK")
        return True


def main():
    parser = argparse.ArgumentParser(description='CSVからDBへ一括投入（不整合防止付き）')
    parser.add_argument('--input', type=str, required=True, help='CSVディレクトリ')
    parser.add_argument('--db', type=str, default='data/boatrace.db', help='DBパス')
    parser.add_argument('--dry-run', action='store_true', help='検証のみ（実際には投入しない）')
    parser.add_argument('--overwrite', action='store_true', help='既存データを上書き')
    args = parser.parse_args()

    input_dir = Path(args.input)
    db_path = ROOT_DIR / args.db

    print("=" * 70)
    print("CSV → DB 一括投入（不整合防止付き）")
    print("=" * 70)
    print(f"入力ディレクトリ: {input_dir}")
    print(f"DB: {db_path}")
    print(f"Dry-run: {args.dry_run}")
    print(f"上書き: {args.overwrite}")
    print()

    importer = CSVToDatabaseImporter(str(db_path))
    importer.connect()

    try:
        importer.begin_transaction()

        # 1. races テーブル
        print("=== races テーブル ===")
        races_csv = input_dir / 'races.csv'
        r_ins, r_upd, r_skip = importer.import_races(races_csv, args.overwrite)
        print(f"挿入: {r_ins}, 更新: {r_upd}, スキップ: {r_skip}")

        # 2. entries テーブル
        print("\n=== entries テーブル ===")
        entries_csv = input_dir / 'entries.csv'
        entries_columns = ['pit_number', 'racer_number', 'racer_name', 'racer_rank',
                          'racer_home', 'racer_age', 'racer_weight', 'motor_number',
                          'boat_number', 'win_rate', 'second_rate', 'third_rate',
                          'f_count', 'l_count', 'avg_st', 'local_win_rate',
                          'local_second_rate', 'local_third_rate', 'motor_second_rate',
                          'motor_third_rate', 'boat_second_rate', 'boat_third_rate']
        e_ins, e_upd, e_skip = importer.import_child_table(
            entries_csv, 'entries', entries_columns, args.overwrite
        )
        print(f"挿入: {e_ins}, 更新: {e_upd}, スキップ: {e_skip}")

        # 3. race_conditions テーブル
        print("\n=== race_conditions テーブル ===")
        conditions_csv = input_dir / 'race_conditions.csv'
        conditions_columns = ['weather', 'wind_direction', 'wind_speed', 'wave_height',
                             'temperature', 'water_temperature']
        c_ins, c_upd, c_skip = importer.import_child_table(
            conditions_csv, 'race_conditions', conditions_columns, args.overwrite
        )
        print(f"挿入: {c_ins}, 更新: {c_upd}, スキップ: {c_skip}")

        # 4. race_details テーブル
        print("\n=== race_details テーブル ===")
        details_csv = input_dir / 'race_details.csv'
        details_columns = ['pit_number', 'exhibition_time', 'tilt_angle',
                          'parts_replacement', 'actual_course', 'st_time']
        d_ins, d_upd, d_skip = importer.import_child_table(
            details_csv, 'race_details', details_columns, args.overwrite
        )
        print(f"挿入: {d_ins}, 更新: {d_upd}, スキップ: {d_skip}")

        # 5. results テーブル
        print("\n=== results テーブル ===")
        results_csv = input_dir / 'results.csv'
        results_columns = ['pit_number', 'rank', 'is_invalid', 'kimarite']
        res_ins, res_upd, res_skip = importer.import_child_table(
            results_csv, 'results', results_columns, args.overwrite
        )
        print(f"挿入: {res_ins}, 更新: {res_upd}, スキップ: {res_skip}")

        # 6. payouts テーブル
        print("\n=== payouts テーブル ===")
        payouts_csv = input_dir / 'payouts.csv'
        payouts_columns = ['bet_type', 'combination', 'amount', 'popularity']
        p_ins, p_upd, p_skip = importer.import_child_table(
            payouts_csv, 'payouts', payouts_columns, args.overwrite
        )
        print(f"挿入: {p_ins}, 更新: {p_upd}, スキップ: {p_skip}")

        # 整合性検証
        if not importer.verify_integrity():
            print("\n❌ 整合性検証失敗: ロールバックします")
            importer.rollback()
            return

        # Dry-runモード
        if args.dry_run:
            print("\n🔍 Dry-runモード: ロールバックします")
            importer.rollback()
        else:
            print("\n✅ コミットします")
            importer.commit()

        # サマリー
        print()
        print("=" * 70)
        print("完了")
        print("=" * 70)
        total_ins = r_ins + e_ins + c_ins + d_ins + res_ins + p_ins
        total_skip = r_skip + e_skip + c_skip + d_skip + res_skip + p_skip
        print(f"総挿入: {total_ins}")
        print(f"総スキップ: {total_skip}")

    except Exception as e:
        print(f"\n❌ エラー発生: {e}")
        import traceback
        traceback.print_exc()
        importer.rollback()
        raise

    finally:
        importer.close()


if __name__ == '__main__':
    main()
