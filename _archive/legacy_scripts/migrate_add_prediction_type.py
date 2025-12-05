#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
race_predictionsテーブルにprediction_typeカラムを追加するマイグレーション

prediction_type:
  - 'advance': 事前予想（出走表確定後、展示データなし）
  - 'before': 直前予想（展示データ取得後）
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
    print("race_predictions テーブル マイグレーション")
    print("="*70)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 既存のカラムを確認
        cursor.execute("PRAGMA table_info(race_predictions)")
        columns = [row[1] for row in cursor.fetchall()]

        print(f"\n現在のカラム数: {len(columns)}")

        # prediction_typeカラムの追加
        if 'prediction_type' not in columns:
            print("\n[1/3] prediction_typeカラムを追加中...")
            cursor.execute("""
                ALTER TABLE race_predictions
                ADD COLUMN prediction_type TEXT DEFAULT 'advance'
            """)
            print("  ✓ prediction_typeカラムを追加しました")
        else:
            print("\n[1/3] prediction_typeカラムは既に存在します")

        # generated_atカラムの追加（NULLを許可、挿入時に指定）
        if 'generated_at' not in columns:
            print("\n[2/3] generated_atカラムを追加中...")
            cursor.execute("""
                ALTER TABLE race_predictions
                ADD COLUMN generated_at TIMESTAMP
            """)
            print("  ✓ generated_atカラムを追加しました")
        else:
            print("\n[2/3] generated_atカラムは既に存在します")

        # インデックスの作成
        print("\n[3/3] インデックスを作成中...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_type
            ON race_predictions(race_id, prediction_type)
        """)
        print("  ✓ インデックスを作成しました")

        conn.commit()

        # 結果確認
        cursor.execute("PRAGMA table_info(race_predictions)")
        new_columns = cursor.fetchall()

        print("\n" + "="*70)
        print("マイグレーション完了")
        print("="*70)
        print(f"\n更新後のカラム数: {len(new_columns)}")
        print("\n追加されたカラム:")
        for col in new_columns:
            if col[1] in ['prediction_type', 'generated_at']:
                print(f"  - {col[1]:20s} {col[2]:10s} DEFAULT: {col[4] if col[4] else 'None'}")

        print("\n" + "="*70)

    except Exception as e:
        print(f"\n✗ エラー: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
