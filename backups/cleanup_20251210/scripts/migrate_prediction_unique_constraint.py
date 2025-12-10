"""
race_predictionsテーブルのUNIQUE制約を修正

変更内容:
- 旧: UNIQUE(race_id, pit_number)
- 新: UNIQUE(race_id, pit_number, prediction_type)

これにより、事前予想(advance)と直前予想(before)を両方保持できるようになります。
"""

import sqlite3
import os
from datetime import datetime

def migrate_prediction_table(db_path: str = "data/boatrace.db"):
    """race_predictionsテーブルのUNIQUE制約を修正"""

    if not os.path.exists(db_path):
        print(f"[ERROR] データベースが見つかりません: {db_path}")
        return False

    print(f"[DB] データベース: {db_path}")
    print("[WARN] race_predictionsテーブルのUNIQUE制約を修正します")
    print("   旧: UNIQUE(race_id, pit_number)")
    print("   新: UNIQUE(race_id, pit_number, prediction_type)")
    print()

    # バックアップファイル名
    backup_path = db_path.replace('.db', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')

    try:
        # バックアップ作成
        print(f"[BACKUP] バックアップ作成中: {backup_path}")
        import shutil
        shutil.copy2(db_path, backup_path)
        print("[OK] バックアップ完了")
        print()

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 既存データ件数を確認
        cursor.execute("SELECT COUNT(*) FROM race_predictions")
        total_count = cursor.fetchone()[0]
        print(f"[DATA] 既存データ: {total_count}件")

        # prediction_type別の件数
        cursor.execute("""
            SELECT prediction_type, COUNT(*)
            FROM race_predictions
            GROUP BY prediction_type
        """)
        for ptype, count in cursor.fetchall():
            print(f"   - {ptype}: {count}件")
        print()

        # Step 0: 依存するビューを削除
        print("[STEP 0] 依存するビューを削除中...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='view'")
        views = [row[0] for row in cursor.fetchall()]
        for view_name in views:
            cursor.execute(f"DROP VIEW IF EXISTS {view_name}")
            print(f"   - {view_name} を削除")
        print("[OK] ビュー削除完了")
        print()

        # Step 1: 一時テーブルを作成（新しいUNIQUE制約付き）
        print("[STEP 1] 新しいスキーマで一時テーブルを作成中...")
        cursor.execute("""
            CREATE TABLE race_predictions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                pit_number INTEGER NOT NULL,
                rank_prediction INTEGER NOT NULL,
                total_score REAL NOT NULL,
                confidence TEXT,
                racer_name TEXT,
                racer_number TEXT,
                applied_rules TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                course_score REAL,
                racer_score REAL,
                motor_score REAL,
                kimarite_score REAL,
                grade_score REAL,
                prediction_type TEXT DEFAULT 'advance',
                generated_at TIMESTAMP,
                UNIQUE(race_id, pit_number, prediction_type),
                FOREIGN KEY (race_id) REFERENCES races(id)
            )
        """)
        print("[OK] 一時テーブル作成完了")
        print()

        # Step 2: データをコピー
        print("[STEP 2] データを一時テーブルにコピー中...")
        cursor.execute("""
            INSERT INTO race_predictions_new
            SELECT * FROM race_predictions
        """)
        copied_count = cursor.rowcount
        print(f"[OK] {copied_count}件のデータをコピー完了")
        print()

        # Step 3: 旧テーブルを削除
        print("[STEP 3] 旧テーブルを削除中...")
        cursor.execute("DROP TABLE race_predictions")
        print("[OK] 旧テーブル削除完了")
        print()

        # Step 4: 一時テーブルをリネーム
        print("[STEP 4] 一時テーブルをrace_predictionsにリネーム中...")
        cursor.execute("ALTER TABLE race_predictions_new RENAME TO race_predictions")
        print("[OK] リネーム完了")
        print()

        # Step 5: データ確認
        print("[STEP 5] マイグレーション結果を確認中...")
        cursor.execute("SELECT COUNT(*) FROM race_predictions")
        final_count = cursor.fetchone()[0]

        if final_count == total_count:
            print(f"[OK] データ件数一致: {final_count}件")
        else:
            print(f"[WARN] データ件数が変わりました: {total_count}件 -> {final_count}件")

        # 新しいスキーマを確認
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='race_predictions'")
        new_schema = cursor.fetchone()[0]

        if "UNIQUE(race_id, pit_number, prediction_type)" in new_schema:
            print("[OK] UNIQUE制約が正しく更新されました")
        else:
            print("[WARN] UNIQUE制約の確認に失敗しました")
            print(new_schema)

        conn.commit()
        conn.close()

        # Step 6: ビューを再作成
        print()
        print("[STEP 6] ビューを再作成中...")
        try:
            from src.database.views import initialize_views
            initialize_views(db_path)
            print("[OK] ビュー再作成完了")
        except Exception as e:
            print(f"[WARN] ビュー再作成に失敗: {e}")
            print("   (後で手動で `python -c \"from src.database.views import initialize_views; initialize_views('data/boatrace.db')\"` を実行してください)")

        print()
        print("=" * 60)
        print("[SUCCESS] マイグレーション完了！")
        print("=" * 60)
        print()
        print("[INFO] 変更内容:")
        print("   - 事前予想(advance)と直前予想(before)を両方保持できます")
        print("   - 直前予想を更新しても事前予想は削除されません")
        print()
        print(f"[BACKUP] バックアップファイル: {backup_path}")
        print("   (問題があれば、このファイルから復元できます)")

        return True

    except Exception as e:
        print(f"[ERROR] マイグレーションエラー: {e}")
        print()
        print(f"[BACKUP] バックアップから復元してください: {backup_path}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys

    db_path = "data/boatrace.db"
    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    print()
    print("=" * 60)
    print("race_predictions UNIQUE制約マイグレーション")
    print("=" * 60)
    print()

    success = migrate_prediction_table(db_path)

    if success:
        sys.exit(0)
    else:
        sys.exit(1)
