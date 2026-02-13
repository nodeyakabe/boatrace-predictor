#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
直前情報CSVデータのDB投入スクリプト

CSV形式で保存された直前情報データをデータベースに一括投入します。

使用例:
    # 全年度のCSVを投入
    python scripts/data_collection/import_beforeinfo_csv_to_db.py --input data/csv/beforeinfo

    # 特定年度のみ
    python scripts/data_collection/import_beforeinfo_csv_to_db.py --input data/csv/beforeinfo/2020-2023
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import csv
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def import_csv_to_db(csv_file_path: Path, db_path: Path, batch_size: int = 500):
    """
    CSVファイルからデータベースに直前情報データを投入

    Args:
        csv_file_path: CSVファイルパス
        db_path: データベースパス
        batch_size: バッチサイズ
    """
    if not csv_file_path.exists():
        print(f"CSVファイルが見つかりません: {csv_file_path}")
        return 0

    print(f"\n処理中: {csv_file_path}")

    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    # WALモード有効化
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")

    inserted = 0
    updated = 0
    batch_buffer = []

    try:
        with open(csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                race_id = int(row['race_id'])
                pit_number = int(row['pit_number'])

                # NULL値の処理
                def parse_value(value):
                    if value is None or value == '' or value == 'None':
                        return None
                    return value

                def parse_float(value):
                    try:
                        return float(value) if value and value != 'None' else None
                    except:
                        return None

                def parse_int(value):
                    try:
                        return int(value) if value and value != 'None' else None
                    except:
                        return None

                batch_buffer.append((
                    parse_float(row.get('exhibition_time')),
                    parse_float(row.get('tilt_angle')),
                    parse_value(row.get('parts_replacement')),
                    parse_float(row.get('adjusted_weight')),
                    parse_float(row.get('st_time')),
                    parse_int(row.get('exhibition_course')),
                    parse_int(row.get('prev_race_course')),
                    parse_float(row.get('prev_race_st')),
                    parse_int(row.get('prev_race_rank')),
                    race_id,
                    pit_number
                ))

                # バッチサイズに達したら投入
                if len(batch_buffer) >= batch_size:
                    cursor.execute("BEGIN IMMEDIATE")
                    cursor.executemany("""
                        INSERT OR REPLACE INTO race_details (
                            race_id, pit_number,
                            exhibition_time, tilt_angle, parts_replacement,
                            adjusted_weight, st_time, exhibition_course,
                            prev_race_course, prev_race_st, prev_race_rank
                        )
                        VALUES (
                            ?, ?,
                            ?, ?, ?,
                            ?, ?, ?,
                            ?, ?, ?
                        )
                        ON CONFLICT(race_id, pit_number) DO UPDATE SET
                            exhibition_time = COALESCE(excluded.exhibition_time, race_details.exhibition_time),
                            tilt_angle = COALESCE(excluded.tilt_angle, race_details.tilt_angle),
                            parts_replacement = COALESCE(excluded.parts_replacement, race_details.parts_replacement),
                            adjusted_weight = COALESCE(excluded.adjusted_weight, race_details.adjusted_weight),
                            st_time = COALESCE(excluded.st_time, race_details.st_time),
                            exhibition_course = COALESCE(excluded.exhibition_course, race_details.exhibition_course),
                            prev_race_course = COALESCE(excluded.prev_race_course, race_details.prev_race_course),
                            prev_race_st = COALESCE(excluded.prev_race_st, race_details.prev_race_st),
                            prev_race_rank = COALESCE(excluded.prev_race_rank, race_details.prev_race_rank)
                    """, [(race_id, pit, et, ta, pr, aw, st, ec, prc, prs, prr)
                          for et, ta, pr, aw, st, ec, prc, prs, prr, race_id, pit in batch_buffer])
                    conn.commit()

                    inserted += len(batch_buffer)
                    batch_buffer.clear()

                    if inserted % 5000 == 0:
                        print(f"  投入済み: {inserted:,}件")

        # 残りのバッチを投入
        if batch_buffer:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.executemany("""
                INSERT OR REPLACE INTO race_details (
                    race_id, pit_number,
                    exhibition_time, tilt_angle, parts_replacement,
                    adjusted_weight, st_time, exhibition_course,
                    prev_race_course, prev_race_st, prev_race_rank
                )
                VALUES (
                    ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?
                )
                ON CONFLICT(race_id, pit_number) DO UPDATE SET
                    exhibition_time = COALESCE(excluded.exhibition_time, race_details.exhibition_time),
                    tilt_angle = COALESCE(excluded.tilt_angle, race_details.tilt_angle),
                    parts_replacement = COALESCE(excluded.parts_replacement, race_details.parts_replacement),
                    adjusted_weight = COALESCE(excluded.adjusted_weight, race_details.adjusted_weight),
                    st_time = COALESCE(excluded.st_time, race_details.st_time),
                    exhibition_course = COALESCE(excluded.exhibition_course, race_details.exhibition_course),
                    prev_race_course = COALESCE(excluded.prev_race_course, race_details.prev_race_course),
                    prev_race_st = COALESCE(excluded.prev_race_st, race_details.prev_race_st),
                    prev_race_rank = COALESCE(excluded.prev_race_rank, race_details.prev_race_rank)
            """, [(race_id, pit, et, ta, pr, aw, st, ec, prc, prs, prr)
                  for et, ta, pr, aw, st, ec, prc, prs, prr, race_id, pit in batch_buffer])
            conn.commit()
            inserted += len(batch_buffer)

    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()

    finally:
        conn.close()

    print(f"  完了: {inserted:,}件投入")
    return inserted


def main():
    parser = argparse.ArgumentParser(description='直前情報CSVデータのDB投入')
    parser.add_argument('--input', type=str, required=True, help='CSVディレクトリまたはファイル')
    parser.add_argument('--batch-size', type=int, default=500, help='バッチサイズ')

    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    input_path = Path(args.input)

    print("=" * 80)
    print("直前情報CSVデータのDB投入")
    print("=" * 80)
    print(f"入力: {input_path}")
    print(f"DB: {db_path}")
    print("=" * 80)

    start_time = time.time()
    total_inserted = 0

    # ディレクトリの場合は全CSVファイルを処理
    if input_path.is_dir():
        csv_files = list(input_path.glob("**/beforeinfo.csv"))
        print(f"\nCSVファイル数: {len(csv_files)}")

        for csv_file in csv_files:
            inserted = import_csv_to_db(csv_file, db_path, args.batch_size)
            total_inserted += inserted
    else:
        # ファイル指定の場合
        total_inserted = import_csv_to_db(input_path, db_path, args.batch_size)

    elapsed = time.time() - start_time

    print("\n" + "=" * 80)
    print("投入完了")
    print("=" * 80)
    print(f"総投入件数: {total_inserted:,}件")
    print(f"処理時間: {elapsed/60:.1f}分")
    print(f"処理速度: {total_inserted/elapsed:.0f}件/秒")
    print("=" * 80)


if __name__ == "__main__":
    main()
