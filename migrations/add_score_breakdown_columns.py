"""
race_predictionsテーブルにスコア内訳カラムを追加
再予測機能を完全に運用可能にする
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from config.settings import DATABASE_PATH

def add_score_breakdown_columns():
    """race_predictionsテーブルにスコア内訳カラムを追加"""

    print("=" * 80)
    print("race_predictionsテーブル拡張")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 既存のカラムを確認
    cursor.execute("PRAGMA table_info(race_predictions)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    print("\n既存のカラム:")
    for col in sorted(existing_columns):
        print(f"  • {col}")

    # 追加するカラム
    new_columns = [
        ('course_score', 'REAL DEFAULT 0'),
        ('racer_score', 'REAL DEFAULT 0'),
        ('motor_score', 'REAL DEFAULT 0'),
        ('kimarite_score', 'REAL DEFAULT 0'),
        ('grade_score', 'REAL DEFAULT 0'),
    ]

    added_count = 0
    print("\n追加するカラム:")

    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            print(f"  • {col_name} ({col_type})")
            cursor.execute(f"ALTER TABLE race_predictions ADD COLUMN {col_name} {col_type}")
            added_count += 1
        else:
            print(f"  ✓ {col_name} (既に存在)")

    if added_count > 0:
        conn.commit()
        print(f"\n{added_count}個のカラムを追加しました")
    else:
        print("\n追加するカラムはありませんでした（既に最新）")

    conn.close()

    print("\n" + "=" * 80)
    print("テーブル拡張完了")
    print("=" * 80)


if __name__ == "__main__":
    add_score_breakdown_columns()
