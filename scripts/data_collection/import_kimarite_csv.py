"""
決まり手CSVをDBにインポートするスクリプト

使用例:
  python scripts/data_collection/import_kimarite_csv.py --csv data/csv/kimarite/kimarite_20200101_20201231.csv
  python scripts/data_collection/import_kimarite_csv.py --csv data/csv/kimarite/  # ディレクトリ内の全CSV
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import argparse
import sqlite3
import csv
import glob

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')

def import_csv(csv_path):
    """1つのCSVをDBにインポート"""
    print(f"\n読み込み: {csv_path}")

    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"  レコード数: {len(rows):,}件")
    if len(rows) == 0:
        return 0

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    updated = 0
    for row in rows:
        cursor.execute("""
            UPDATE results
            SET kimarite = ?
            WHERE race_id = ? AND rank = '1'
        """, (row['kimarite'], int(row['race_id'])))
        updated += cursor.rowcount

    conn.commit()
    conn.close()
    print(f"  更新完了: {updated:,}件")
    return updated

def main():
    parser = argparse.ArgumentParser(description='決まり手CSV → DBインポート')
    parser.add_argument('--csv', type=str, required=True, help='CSVファイルパスまたはディレクトリ')
    args = parser.parse_args()

    print("=" * 70)
    print("決まり手CSV インポート")
    print("=" * 70)

    target = args.csv
    csv_files = []

    if os.path.isdir(target):
        csv_files = sorted(glob.glob(os.path.join(target, 'kimarite_*.csv')))
        print(f"ディレクトリ: {target} ({len(csv_files)}ファイル)")
    elif os.path.isfile(target):
        csv_files = [target]
    else:
        print(f"エラー: 指定されたパスが存在しません: {target}")
        sys.exit(1)

    if not csv_files:
        print("CSVファイルが見つかりません。")
        sys.exit(1)

    total_updated = 0
    for csv_path in csv_files:
        total_updated += import_csv(csv_path)

    print("\n" + "=" * 70)
    print(f"インポート完了: 合計 {total_updated:,}件更新")
    print("=" * 70)

if __name__ == "__main__":
    main()
