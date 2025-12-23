"""
データベース初期化スクリプト
最初に1回だけ実行してデータベースとテーブルを作成する
"""

from src.database.models import Database
from config.settings import VENUES, DATABASE_PATH


def main():
    """データベースを初期化"""
    print("=" * 50)
    print("競艇予想システム - データベース初期化")
    print("=" * 50)

    # データベースインスタンス作成
    db = Database(DATABASE_PATH)

    # テーブル作成
    print("\n[1/2] テーブルを作成中...")
    db.create_tables()

    # 競艇場マスタデータ投入
    print("\n[2/2] 競艇場情報を登録中...")
    db.initialize_venues(VENUES)

    print("\n" + "=" * 50)
    print("データベース初期化が完了しました！")
    print(f"データベースパス: {DATABASE_PATH}")
    print("=" * 50)


if __name__ == "__main__":
    main()
