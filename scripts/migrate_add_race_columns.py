"""
データベースマイグレーション: racesテーブルに新カラムを追加

追加カラム:
- grade: グレード（SG/G1/G2/G3/一般）
- is_nighter: ナイターレースか
- is_ladies: 女子戦か
- is_rookie: 新人戦か
- is_shinnyuu_kotei: 進入固定レースか
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
    print("racesテーブルに新カラムを追加")
    print("=" * 60)

    # データベースパス
    db_path = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')

    if not os.path.exists(db_path):
        print(f"エラー: データベースが見つかりません: {db_path}")
        return

    print(f"データベース: {db_path}")

    # マイグレーション実行
    db = Database(db_path)
    added_columns = db.migrate_add_race_columns()

    if added_columns:
        print(f"\n追加されたカラム: {', '.join(added_columns)}")
    else:
        print("\nすべてのカラムは既に存在しています")

    print("\n" + "=" * 60)
    print("マイグレーション完了")
    print("=" * 60)


if __name__ == '__main__':
    main()
