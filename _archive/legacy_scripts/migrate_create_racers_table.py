"""
データベースマイグレーション: racersテーブルを作成

選手マスタテーブルの作成
"""

import os
import sys

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.database.models import Database


def main():
    """マイグレーション実行"""
    print("=" * 60)
    print("データベースマイグレーション")
    print("racersテーブルを作成")
    print("=" * 60)

    # データベースパス
    db_path = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')

    if not os.path.exists(db_path):
        print(f"エラー: データベースが見つかりません: {db_path}")
        return

    print(f"データベース: {db_path}")

    # マイグレーション実行
    db = Database(db_path)
    conn = db.connect()
    cursor = conn.cursor()

    # racersテーブルが既に存在するかチェック
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='racers'")
    if cursor.fetchone():
        print("\nracersテーブルは既に存在しています")
    else:
        # racersテーブルを作成
        cursor.execute("""
            CREATE TABLE racers (
                racer_number TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                name_kana TEXT,
                gender TEXT,
                birth_date DATE,
                height REAL,
                weight REAL,
                blood_type TEXT,
                branch TEXT,
                hometown TEXT,
                registration_period INTEGER,
                rank TEXT,
                win_rate REAL,
                second_rate REAL,
                third_rate REAL,
                ability_index REAL,
                average_st REAL,
                wins INTEGER,
                updated_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print("\nracersテーブルを作成しました")

    db.close()

    print("\n" + "=" * 60)
    print("マイグレーション完了")
    print("=" * 60)


if __name__ == '__main__':
    main()
