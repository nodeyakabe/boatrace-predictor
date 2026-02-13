#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
日付形式統一スクリプト（YYYY-MM-DD → YYYYMMDD）

DB内の日付形式をYYYYMMDD形式に統一します。
"""
import sys
import io
import sqlite3
from pathlib import Path
from datetime import datetime

# Windows文字コード対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH

def main():
    print("=" * 80)
    print("日付形式統一スクリプト（YYYY-MM-DD → YYYYMMDD）")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # バックアップ推奨メッセージ
    print("⚠️ 注意: この処理はデータを変更します。")
    print("   DBのバックアップを取ることを推奨します。")
    print()

    # 現在の状況確認
    print("=== 現在の日付形式分布 ===")
    cursor.execute("""
        SELECT
            CASE
                WHEN race_date LIKE '____-__-__' THEN 'YYYY-MM-DD'
                WHEN length(race_date) = 8 THEN 'YYYYMMDD'
                ELSE 'その他'
            END as format,
            COUNT(*) as cnt
        FROM races
        GROUP BY format
    """)
    for format_type, count in cursor.fetchall():
        print(f"  {format_type}: {count:,}件")
    print()

    # YYYY-MM-DD形式のデータを確認
    cursor.execute("""
        SELECT COUNT(*) FROM races
        WHERE race_date LIKE '____-__-__'
    """)
    to_convert = cursor.fetchone()[0]

    if to_convert == 0:
        print("✅ 変換対象のデータはありません。")
        conn.close()
        return 0

    print(f"変換対象: {to_convert:,}件")
    print()

    # 変換実行
    print("変換を実行中...")
    cursor.execute("BEGIN TRANSACTION")

    cursor.execute("""
        UPDATE races
        SET race_date = REPLACE(race_date, '-', '')
        WHERE race_date LIKE '____-__-__'
    """)
    updated = cursor.rowcount
    print(f"✓ races更新: {updated:,}件")

    cursor.execute("COMMIT")
    print()

    # 結果確認
    print("=== 変換後の日付形式分布 ===")
    cursor.execute("""
        SELECT
            CASE
                WHEN race_date LIKE '____-__-__' THEN 'YYYY-MM-DD'
                WHEN length(race_date) = 8 THEN 'YYYYMMDD'
                ELSE 'その他'
            END as format,
            COUNT(*) as cnt
        FROM races
        GROUP BY format
    """)
    for format_type, count in cursor.fetchall():
        print(f"  {format_type}: {count:,}件")
    print()

    print("✅ 日付形式の統一が完了しました")
    print()

    conn.close()
    return 0

if __name__ == '__main__':
    sys.exit(main())
