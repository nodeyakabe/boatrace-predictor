#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
古いYYYYMMDD形式データの削除

2021年1-8月の古いデータ（YYYYMMDD形式）を削除し、
YYYY-MM-DD形式に統一します。
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
    print("古いYYYYMMDD形式データの削除")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 削除対象の確認
    print("=== 削除対象データの確認 ===")
    cursor.execute("""
        SELECT COUNT(*) FROM races
        WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
    """)
    races_to_delete = cursor.fetchone()[0]
    print(f"削除対象レース数: {races_to_delete:,}件")

    # 関連データの確認
    cursor.execute("""
        SELECT COUNT(*) FROM entries
        WHERE race_id IN (
            SELECT id FROM races
            WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
        )
    """)
    entries_to_delete = cursor.fetchone()[0]
    print(f"削除対象エントリー数: {entries_to_delete:,}件")

    cursor.execute("""
        SELECT COUNT(*) FROM results
        WHERE race_id IN (
            SELECT id FROM races
            WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
        )
    """)
    results_to_delete = cursor.fetchone()[0]
    print(f"削除対象結果数: {results_to_delete:,}件")

    cursor.execute("""
        SELECT COUNT(*) FROM trifecta_odds
        WHERE race_id IN (
            SELECT id FROM races
            WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
        )
    """)
    odds_to_delete = cursor.fetchone()[0]
    print(f"削除対象オッズ数: {odds_to_delete:,}件")

    cursor.execute("""
        SELECT COUNT(*) FROM race_conditions
        WHERE race_id IN (
            SELECT id FROM races
            WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
        )
    """)
    conditions_to_delete = cursor.fetchone()[0]
    print(f"削除対象レース条件数: {conditions_to_delete:,}件")

    cursor.execute("""
        SELECT COUNT(*) FROM race_details
        WHERE race_id IN (
            SELECT id FROM races
            WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
        )
    """)
    details_to_delete = cursor.fetchone()[0]
    print(f"削除対象レース詳細数: {details_to_delete:,}件")

    print()

    if races_to_delete == 0:
        print("✅ 削除対象のデータはありません。")
        conn.close()
        return 0

    # 削除実行
    print("削除を実行中...")
    cursor.execute("BEGIN TRANSACTION")

    # entries削除
    cursor.execute("""
        DELETE FROM entries
        WHERE race_id IN (
            SELECT id FROM races
            WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
        )
    """)
    print(f"✓ エントリー削除: {cursor.rowcount:,}件")

    # results削除
    cursor.execute("""
        DELETE FROM results
        WHERE race_id IN (
            SELECT id FROM races
            WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
        )
    """)
    print(f"✓ 結果削除: {cursor.rowcount:,}件")

    # payouts削除
    cursor.execute("""
        DELETE FROM payouts
        WHERE race_id IN (
            SELECT id FROM races
            WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
        )
    """)
    print(f"✓ 払戻削除: {cursor.rowcount:,}件")

    # trifecta_odds削除
    cursor.execute("""
        DELETE FROM trifecta_odds
        WHERE race_id IN (
            SELECT id FROM races
            WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
        )
    """)
    print(f"✓ オッズ削除: {cursor.rowcount:,}件")

    # race_conditions削除
    cursor.execute("""
        DELETE FROM race_conditions
        WHERE race_id IN (
            SELECT id FROM races
            WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
        )
    """)
    print(f"✓ レース条件削除: {cursor.rowcount:,}件")

    # race_details削除
    cursor.execute("""
        DELETE FROM race_details
        WHERE race_id IN (
            SELECT id FROM races
            WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
        )
    """)
    print(f"✓ レース詳細削除: {cursor.rowcount:,}件")

    # races削除
    cursor.execute("""
        DELETE FROM races
        WHERE length(race_date) = 8 AND race_date NOT LIKE '%-%'
    """)
    print(f"✓ レース削除: {cursor.rowcount:,}件")

    # コミット
    cursor.execute("COMMIT")
    print()

    # 結果確認
    print("=== 削除後の状況 ===")
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
        print(f"{format_type}: {count:,}件")
    print()

    print("✅ 古いデータの削除が完了しました")
    print("   日付形式がYYYY-MM-DD形式に統一されました。")
    print()

    conn.close()
    return 0

if __name__ == '__main__':
    sys.exit(main())
