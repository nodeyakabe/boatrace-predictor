# -*- coding: utf-8 -*-
"""CSVファイルから展示データをDBに一括投入

使用例:
    # 検証モード（dry-run）
    python scripts/maintenance/import_exhibition_data_from_csv.py \
        --input data/csv/exhibition_data/2020_01 \
        --dry-run

    # 本番投入
    python scripts/maintenance/import_exhibition_data_from_csv.py \
        --input data/csv/exhibition_data/2020_01

    # 既存データを上書き
    python scripts/maintenance/import_exhibition_data_from_csv.py \
        --input data/csv/exhibition_data/2020_01 \
        --overwrite
"""

import sys
import os
import csv
import sqlite3
import argparse
from pathlib import Path
from typing import Dict, List

# Windows文字コード対策
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))


def load_csv(csv_file: Path) -> List[Dict]:
    """CSVファイルを読み込み"""
    data = []

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)

    return data


def get_race_id(conn: sqlite3.Connection, venue_code: str, race_date: str, race_number: int):
    """venue_code + race_date + race_numberからrace_idを取得"""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM races
        WHERE venue_code = ? AND race_date = ? AND race_number = ?
    """, (venue_code, race_date, race_number))

    result = cursor.fetchone()
    cursor.close()

    return result[0] if result else None


def insert_exhibition_data(
    conn: sqlite3.Connection,
    data: List[Dict],
    overwrite: bool = False,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    展示データをrace_detailsに投入

    Returns:
        dict: {
            'inserted': 投入件数,
            'skipped': スキップ件数（既存データ）,
            'failed': 失敗件数（race_idなし）
        }
    """
    cursor = conn.cursor()

    inserted = 0
    skipped = 0
    failed = 0

    for i, row in enumerate(data, 1):
        venue_code = row['venue_code']
        race_date = row['race_date']
        race_number = int(row['race_number'])
        pit_number = int(row['pit_number'])

        # race_idを取得
        race_id = get_race_id(conn, venue_code, race_date, race_number)

        if not race_id:
            failed += 1
            if i % 1000 == 0:
                print(f"  [{i}/{len(data)}] race_id未発見: {venue_code} {race_date} R{race_number}")
            continue

        # 既存レコードをチェック
        cursor.execute("""
            SELECT id FROM race_details
            WHERE race_id = ? AND pit_number = ?
        """, (race_id, pit_number))
        existing = cursor.fetchone()

        if existing and not overwrite:
            skipped += 1
            continue

        if dry_run:
            inserted += 1
            continue

        # データ投入（INSERT or UPDATE）
        try:
            if existing:
                # UPDATE（NULLでない値のみ更新）
                update_fields = []
                update_values = []

                if row.get('exhibition_time'):
                    update_fields.append('exhibition_time = ?')
                    update_values.append(float(row['exhibition_time']))

                if row.get('tilt'):
                    update_fields.append('tilt_angle = ?')
                    update_values.append(float(row['tilt']))

                if row.get('st_time'):
                    update_fields.append('st_time = ?')
                    update_values.append(float(row['st_time']))

                if row.get('exhibition_course'):
                    update_fields.append('exhibition_course = ?')
                    update_values.append(int(row['exhibition_course']))

                if update_fields:
                    update_values.append(race_id)
                    update_values.append(pit_number)
                    cursor.execute(f"""
                        UPDATE race_details SET
                            {', '.join(update_fields)}
                        WHERE race_id = ? AND pit_number = ?
                    """, update_values)
            else:
                # INSERT
                cursor.execute("""
                    INSERT INTO race_details (
                        race_id, pit_number, exhibition_time, tilt_angle,
                        st_time, exhibition_course
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    race_id,
                    pit_number,
                    float(row['exhibition_time']) if row.get('exhibition_time') else None,
                    float(row['tilt']) if row.get('tilt') else None,
                    float(row['st_time']) if row.get('st_time') else None,
                    int(row['exhibition_course']) if row.get('exhibition_course') else None
                ))

            inserted += 1

            # 進捗表示
            if i % 1000 == 0:
                print(f"  [{i}/{len(data)}] 投入中... (成功: {inserted}, スキップ: {skipped}, 失敗: {failed})")

        except Exception as e:
            failed += 1
            print(f"  エラー: {venue_code} {race_date} R{race_number} 枠{pit_number} - {e}")

    cursor.close()

    return {
        'inserted': inserted,
        'skipped': skipped,
        'failed': failed
    }


def main():
    parser = argparse.ArgumentParser(description='CSVから展示データをDB投入')
    parser.add_argument('--input', required=True, help='CSV入力ディレクトリ')
    parser.add_argument('--db', default='data/boatrace.db', help='DBファイルパス')
    parser.add_argument('--overwrite', action='store_true', help='既存データを上書き')
    parser.add_argument('--dry-run', action='store_true', help='検証モード（実際には投入しない）')
    args = parser.parse_args()

    input_dir = Path(args.input)
    csv_file = input_dir / 'exhibition_data.csv'

    if not csv_file.exists():
        print(f"エラー: CSVファイルが見つかりません: {csv_file}")
        sys.exit(1)

    print("="*80)
    if args.dry_run:
        print("展示データ DB投入（検証モード）")
    else:
        print("展示データ DB投入")
    print("="*80)
    print(f"入力CSV: {csv_file}")
    print(f"DBファイル: {args.db}")
    print(f"上書きモード: {'ON' if args.overwrite else 'OFF'}")
    print()

    # CSVロード
    print("CSVファイルを読み込み中...")
    data = load_csv(csv_file)
    print(f"  読み込み完了: {len(data):,}件")
    print()

    # DB接続
    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        # トランザクション開始
        conn.execute("BEGIN TRANSACTION")

        # データ投入
        print("展示データを投入中...")
        result = insert_exhibition_data(conn, data, args.overwrite, args.dry_run)

        print()
        print("-"*80)
        print(f"投入完了: {result['inserted']:,}件")
        print(f"スキップ: {result['skipped']:,}件（既存データ）")
        print(f"失敗: {result['failed']:,}件（race_id未発見）")
        print()

        if args.dry_run:
            print("検証モードのため、実際にはDBに投入していません。")
            print("問題がなければ --dry-run なしで実行してください。")
            conn.rollback()
        else:
            # コミット
            conn.commit()
            print("コミット完了。DBに投入されました。")

    except Exception as e:
        conn.rollback()
        print(f"エラーが発生しました。ロールバックします: {e}")
        sys.exit(1)

    finally:
        conn.close()

    print("="*80)


if __name__ == '__main__':
    main()
