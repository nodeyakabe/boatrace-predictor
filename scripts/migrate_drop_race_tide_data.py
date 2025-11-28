#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不要テーブル削除マイグレーション

race_tide_dataテーブルを削除
- 使用箇所なし
- データは全てinferred（推定）
- tideテーブルから計算可能
"""
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from config.settings import DATABASE_PATH


def migrate():
    """マイグレーション実行"""
    print("="*70)
    print("不要テーブル削除マイグレーション")
    print("="*70)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # race_tide_dataテーブルの存在確認
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='race_tide_data'
        """)

        if not cursor.fetchone():
            print("\n❌ race_tide_dataテーブルは既に削除されています")
            return

        # データ件数を確認
        cursor.execute("SELECT COUNT(*) FROM race_tide_data")
        count = cursor.fetchone()[0]
        print(f"\nrace_tide_dataテーブル: {count:,}件のデータ")

        # バックアップ作成（念のため）
        print("\n[1/2] バックアップテーブルを作成中...")
        cursor.execute("""
            CREATE TABLE race_tide_data_backup AS
            SELECT * FROM race_tide_data
        """)
        print("  ✓ race_tide_data_backupテーブルを作成しました")

        # テーブル削除
        print("\n[2/2] race_tide_dataテーブルを削除中...")
        cursor.execute("DROP TABLE race_tide_data")
        print("  ✓ race_tide_dataテーブルを削除しました")

        conn.commit()

        print("\n" + "="*70)
        print("マイグレーション完了")
        print("="*70)
        print(f"\n削除: race_tide_data ({count:,}件)")
        print("バックアップ: race_tide_data_backup")
        print("\n※バックアップテーブルは問題なければ後で削除してください:")
        print("  DROP TABLE race_tide_data_backup;")
        print("\n" + "="*70)

    except Exception as e:
        print(f"\n✗ エラー: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
