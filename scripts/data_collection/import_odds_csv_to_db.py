#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
オッズCSVデータのDB投入スクリプト

CSV形式で保存されたオッズデータをデータベースに一括投入します。

使用例:
    # 全年度のCSVを投入
    python scripts/data_collection/import_odds_csv_to_db.py --input data/csv/odds

    # 特定年度のみ
    python scripts/data_collection/import_odds_csv_to_db.py --input data/csv/odds/2023
"""
import sys
import os
import csv
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH


def import_csv_to_db(csv_file_path: Path, db_path: Path, batch_size: int = 1000):
    """
    CSVファイルからデータベースにオッズデータを投入

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
    batch_buffer = []

    try:
        with open(csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                race_id = int(row['race_id'])
                combination = row['combination']
                odds = float(row['odds'])
                fetched_at = row.get('fetched_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

                batch_buffer.append((race_id, combination, odds, fetched_at))

                # バッチサイズに達したら投入
                if len(batch_buffer) >= batch_size:
                    cursor.execute("BEGIN IMMEDIATE")
                    cursor.executemany("""
                        INSERT OR REPLACE INTO trifecta_odds (race_id, combination, odds, fetched_at)
                        VALUES (?, ?, ?, ?)
                    """, batch_buffer)
                    conn.commit()

                    inserted += len(batch_buffer)
                    batch_buffer.clear()

                    if inserted % 10000 == 0:
                        print(f"  投入済み: {inserted:,}件")

        # 残りのバッチを投入
        if batch_buffer:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.executemany("""
                INSERT OR REPLACE INTO trifecta_odds (race_id, combination, odds, fetched_at)
                VALUES (?, ?, ?, ?)
            """, batch_buffer)
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
    parser = argparse.ArgumentParser(description='オッズCSVデータのDB投入')
    parser.add_argument('--input', type=str, required=True, help='CSVディレクトリまたはファイルパス')
    parser.add_argument('--db', type=str, default=None, help='データベースパス（省略時は設定ファイルから取得）')
    parser.add_argument('--batch-size', type=int, default=1000, help='バッチサイズ')
    args = parser.parse_args()

    # データベースパス
    db_path = Path(args.db) if args.db else Path(DATABASE_PATH)

    if not db_path.exists():
        print(f"データベースが見つかりません: {db_path}")
        return

    input_path = Path(args.input)

    print("=" * 80)
    print("オッズCSVデータのDB投入")
    print("=" * 80)
    print(f"入力: {input_path}")
    print(f"DB: {db_path}")
    print(f"バッチサイズ: {args.batch_size:,}件")
    print()

    start_time = time.time()
    total_inserted = 0

    # CSVファイルを検索
    if input_path.is_file():
        # 単一ファイル
        csv_files = [input_path]
    else:
        # ディレクトリ内のCSVを再帰的に検索
        csv_files = sorted(input_path.rglob('trifecta_odds.csv'))

    if not csv_files:
        print(f"CSVファイルが見つかりません: {input_path}")
        return

    print(f"対象ファイル数: {len(csv_files)}")
    print()

    # 各CSVファイルを処理
    for i, csv_file in enumerate(csv_files, 1):
        print(f"[{i}/{len(csv_files)}] {csv_file.parent.name}/{csv_file.name}")
        inserted = import_csv_to_db(csv_file, db_path, args.batch_size)
        total_inserted += inserted

    elapsed = time.time() - start_time

    print()
    print("=" * 80)
    print("処理完了")
    print("=" * 80)
    print(f"投入ファイル数: {len(csv_files)}")
    print(f"総投入件数: {total_inserted:,}件")
    print(f"処理時間: {elapsed/60:.1f}分")
    if elapsed > 0:
        print(f"速度: {total_inserted/elapsed:.0f}件/秒")
    print("=" * 80)


if __name__ == '__main__':
    main()
