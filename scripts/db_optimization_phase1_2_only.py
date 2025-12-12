"""
DB最適化 Phase 1-2 のみ実行

results.winning_technique カラムを削除する（Phase 1-1は完了済み）
"""

import sqlite3
import sys
import io
from pathlib import Path
from datetime import datetime

# 標準出力をUTF-8に設定
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

DB_PATH = project_root / 'data' / 'boatrace.db'


def execute_phase1_2_remove_winning_technique():
    """Phase 1-2: results.winning_technique カラムの削除"""
    print("\n" + "=" * 80)
    print("【Phase 1-2: results.winning_technique カラムの削除】")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Step 1: データ検証
        print("\nStep 1: データ検証中...")
        cursor.execute("""
            SELECT COUNT(*) FROM results
            WHERE rank = '1' AND kimarite IS NOT NULL AND kimarite != ''
        """)
        with_kimarite = cursor.fetchone()[0]
        print(f"  kimarite にデータあり (1着のみ): {with_kimarite:,}件")

        # Step 2: 新テーブル作成 (winning_technique カラムを除外)
        print("\nStep 2: 新テーブル作成中...")
        cursor.execute("""
            CREATE TABLE new_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                pit_number INTEGER NOT NULL,
                rank TEXT,
                is_invalid INTEGER DEFAULT 0,
                trifecta_odds REAL,
                kimarite TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (race_id) REFERENCES races(id),
                UNIQUE(race_id, pit_number)
            )
        """)
        print("  新テーブル作成完了")

        # Step 3: データコピー
        print("\nStep 3: データコピー中...")
        cursor.execute("""
            INSERT INTO new_results (
                id, race_id, pit_number, rank,
                is_invalid, trifecta_odds, kimarite, created_at
            )
            SELECT
                id, race_id, pit_number, rank,
                is_invalid, trifecta_odds, kimarite, created_at
            FROM results
        """)
        copied_count = cursor.rowcount
        print(f"  データコピー完了: {copied_count:,}件")

        # Step 4: 旧テーブル削除
        print("\nStep 4: 旧テーブル削除中...")
        cursor.execute("DROP TABLE results")
        print("  旧テーブル削除完了")

        # Step 5: リネーム
        print("\nStep 5: テーブルリネーム中...")
        cursor.execute("ALTER TABLE new_results RENAME TO results")
        print("  リネーム完了")

        # Step 6: インデックス再作成
        print("\nStep 6: インデックス再作成中...")

        # 個別インデックス
        cursor.execute("CREATE INDEX idx_results_race_id ON results(race_id)")
        cursor.execute("CREATE INDEX idx_results_rank ON results(rank)")

        print("  インデックス再作成完了")

        # コミット
        conn.commit()
        print("\n[SUCCESS] Phase 1-2 完了: results.winning_technique カラムを削除しました")

        return True

    except Exception as e:
        print(f"\n[ERROR] エラー発生: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


def verify_schema_changes():
    """スキーマ変更の検証"""
    print("\n\n" + "=" * 80)
    print("【スキーマ変更の検証】")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # races テーブルのスキーマ確認
    print("\n[races テーブル]")
    cursor.execute("PRAGMA table_info(races)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col[1]} ({col[2]})")

    # results テーブルのスキーマ確認
    print("\n[results テーブル]")
    cursor.execute("PRAGMA table_info(results)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col[1]} ({col[2]})")

    # データ件数確認
    print("\n[データ件数]")
    cursor.execute("SELECT COUNT(*) FROM races")
    race_count = cursor.fetchone()[0]
    print(f"  races: {race_count:,}件")

    cursor.execute("SELECT COUNT(*) FROM results")
    result_count = cursor.fetchone()[0]
    print(f"  results: {result_count:,}件")

    conn.close()


def main():
    """メイン処理"""
    print("=" * 80)
    print("DB最適化 Phase 1-2 実行")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    print("\n[INFO] Phase 1-1 (races.grade削除) は完了済みです")
    print("[INFO] Phase 1-2 (results.winning_technique削除) のみ実行します")

    response = input("\n実行しますか？ (yes/no): ")

    if response.lower() != 'yes':
        print("キャンセルしました")
        return

    # Phase 1-2 実行
    success = execute_phase1_2_remove_winning_technique()

    if not success:
        print("\n[ERROR] Phase 1-2 が失敗しました。")
        return

    # 検証
    verify_schema_changes()

    print("\n" + "=" * 80)
    print("[SUCCESS] Phase 1 完全完了")
    print("=" * 80)
    print("\n次のステップ:")
    print("1. コード修正:")
    print("   - src/database/data_manager.py:568,573 の winning_technique 参照を削除")
    print("2. 動作確認:")
    print("   - 予測処理のテスト実行")
    print("   - UIからのデータ表示確認")


if __name__ == "__main__":
    main()
