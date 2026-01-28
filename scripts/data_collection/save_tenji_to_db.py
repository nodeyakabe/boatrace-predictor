"""
オリジナル展示データをDBに保存するスクリプト

collect_original_tenji.py で収集したJSONデータをDBに保存します。

使い方:
    # JSONファイルからDBに保存
    python scripts/data_collection/save_tenji_to_db.py data/tenji/boaters/tenji_20260115.json

    # 収集と保存を一度に実行
    python scripts/data_collection/collect_and_save_tenji.py --date 2026-01-15 --venue 01
"""

import sys
import os
from pathlib import Path
import json
import sqlite3
import argparse
from datetime import datetime

# Windows環境での文字化け対策
if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.utils.db_pool import ConnectionPool


def ensure_tenji_columns(conn):
    """
    exhibition_dataテーブルに必要なカラムを追加（存在しない場合）
    """
    cursor = conn.cursor()

    # 既存カラムを確認
    cursor.execute("PRAGMA table_info(exhibition_data)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    # 追加が必要なカラム
    new_columns = {
        'isshu_time': 'REAL',           # 1周タイム
        'mawariashi_time': 'REAL',      # 回り足タイム
        'chikusen_time': 'REAL',        # 直線タイム（畜舎タイム）
        'data_source': 'TEXT'           # データソース（boaters, venue_hp等）
    }

    added = []
    for col_name, col_type in new_columns.items():
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE exhibition_data ADD COLUMN {col_name} {col_type}")
                added.append(col_name)
            except sqlite3.OperationalError as e:
                print(f"  警告: カラム追加失敗 {col_name}: {e}")

    if added:
        conn.commit()
        print(f"  ✓ カラム追加: {', '.join(added)}")
    else:
        print(f"  ✓ カラムは既に存在します")


def get_race_id(conn, venue_code, race_date, race_no):
    """
    race_id を取得（存在しない場合は作成）

    Args:
        conn: DB接続
        venue_code: 場コード (1-24)
        race_date: レース日付 (YYYY-MM-DD)
        race_no: レース番号 (1-12)

    Returns:
        int: race_id
    """
    cursor = conn.cursor()

    # 既存のrace_idを検索
    cursor.execute("""
        SELECT id FROM races
        WHERE venue_code = ? AND race_date = ? AND race_number = ?
    """, (venue_code, race_date, race_no))

    result = cursor.fetchone()
    if result:
        return result[0]

    # 存在しない場合は新規作成
    cursor.execute("""
        INSERT INTO races (venue_code, race_date, race_number, created_at)
        VALUES (?, ?, ?, datetime('now', 'localtime'))
    """, (venue_code, race_date, race_no))

    conn.commit()
    return cursor.lastrowid


def save_tenji_data(json_file_path, db_path, update_existing=False):
    """
    JSONファイルのオリジナル展示データをDBに保存

    Args:
        json_file_path: JSONファイルパス
        db_path: DBファイルパス
        update_existing: 既存データを更新するか
    """
    # JSONデータを読み込み
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data:
        print("データが空です")
        return 0

    separator = "=" * 80
    print(separator)
    print(f"オリジナル展示データ DB保存")
    print(f"JSONファイル: {json_file_path}")
    print(f"データ件数: {len(data)}レース")
    print(separator)
    print()

    # DB接続
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        # カラム追加（必要に応じて）
        ensure_tenji_columns(conn)

        saved_count = 0
        skipped_count = 0
        updated_count = 0

        for race_data in data:
            venue_code = race_data['venue_code']
            race_date = race_data['date']
            race_no = race_data['race_no']
            racers = race_data['racers']

            print(f"[{venue_code:02d}] {race_date} {race_no}R - 保存中...")

            # race_idを取得または作成
            try:
                race_id = get_race_id(conn, venue_code, race_date, race_no)
            except Exception as e:
                print(f"  ✗ race_id取得エラー: {e}")
                continue

            # 各艇のデータを保存
            for pit_str, tenji_info in racers.items():
                pit_number = int(pit_str)

                isshu_time = tenji_info.get('isshu_time')
                mawariashi_time = tenji_info.get('mawariashi_time')
                chikusen_time = tenji_info.get('chikusen_time')

                # 既存データを確認
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, isshu_time, mawariashi_time, chikusen_time
                    FROM exhibition_data
                    WHERE race_id = ? AND pit_number = ?
                """, (race_id, pit_number))

                existing = cursor.fetchone()

                if existing:
                    if update_existing:
                        # 更新
                        cursor.execute("""
                            UPDATE exhibition_data
                            SET isshu_time = ?,
                                mawariashi_time = ?,
                                chikusen_time = ?,
                                data_source = 'boaters',
                                collected_at = datetime('now', 'localtime')
                            WHERE race_id = ? AND pit_number = ?
                        """, (isshu_time, mawariashi_time, chikusen_time, race_id, pit_number))
                        updated_count += 1
                    else:
                        skipped_count += 1
                        continue
                else:
                    # 新規挿入
                    cursor.execute("""
                        INSERT INTO exhibition_data (
                            race_id, pit_number,
                            isshu_time, mawariashi_time, chikusen_time,
                            data_source, collected_at
                        ) VALUES (?, ?, ?, ?, ?, 'boaters', datetime('now', 'localtime'))
                    """, (race_id, pit_number, isshu_time, mawariashi_time, chikusen_time))
                    saved_count += 1

            conn.commit()
            print(f"  ✓ 保存完了: {len(racers)}艇")

        print()
        print(separator)
        print(f"保存完了")
        print(f"  新規保存: {saved_count}件")
        print(f"  更新: {updated_count}件")
        print(f"  スキップ: {skipped_count}件")
        print(separator)

        return saved_count + updated_count

    finally:
        conn.close()


def main():
    """メイン処理"""

    parser = argparse.ArgumentParser(description='オリジナル展示データ DB保存')
    parser.add_argument('json_file', type=str, help='JSONファイルパス')
    parser.add_argument('--db', type=str, default='data/boatrace.db', help='DBファイルパス')
    parser.add_argument('--update', action='store_true', help='既存データを更新')
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"エラー: ファイルが見つかりません: {json_path}")
        return

    db_path = project_root / args.db

    save_tenji_data(json_path, db_path, update_existing=args.update)


if __name__ == '__main__':
    main()
