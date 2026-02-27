"""
DB最適化 Phase 1 実行スクリプト

races.grade と results.winning_technique カラムを削除する。
SQLiteはALTER TABLE DROP COLUMN非対応のため、テーブル再作成で実施。
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


def execute_phase1_1_remove_grade_column():
    """Phase 1-1: races.grade カラムの削除"""
    print("\n" + "=" * 80)
    print("【Phase 1-1: races.grade カラムの削除】")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Step 0: VIEW を一時削除
        print("\nStep 0: VIEW を一時削除中...")
        cursor.execute("DROP VIEW IF EXISTS race_details_extended")
        cursor.execute("DROP VIEW IF EXISTS racer_performance_summary")
        cursor.execute("DROP VIEW IF EXISTS venue_statistics_view")
        print("  VIEW 削除完了")

        # Step 1: データマージ (race_grade が NULL/空 の場合、grade から値をコピー)
        print("\nStep 1: データマージ中...")
        cursor.execute("""
            UPDATE races
            SET race_grade = grade
            WHERE (race_grade IS NULL OR race_grade = '')
              AND grade IS NOT NULL AND grade != ''
        """)
        merged_count = cursor.rowcount
        print(f"  マージ完了: {merged_count:,}件")

        # Step 2: 検証
        print("\nStep 2: データ検証中...")
        cursor.execute("""
            SELECT COUNT(*) FROM races
            WHERE race_grade IS NOT NULL AND race_grade != ''
        """)
        with_race_grade = cursor.fetchone()[0]
        print(f"  race_grade にデータあり: {with_race_grade:,}件")

        # Step 3: 新テーブル作成 (grade カラムを除外)
        print("\nStep 3: 新テーブル作成中...")
        cursor.execute("""
            CREATE TABLE new_races (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_code TEXT NOT NULL,
                race_date TEXT NOT NULL,
                race_number INTEGER NOT NULL,
                race_time TEXT,
                race_grade TEXT,
                race_distance INTEGER,
                race_status TEXT DEFAULT 'scheduled',
                is_nighter INTEGER DEFAULT 0,
                is_ladies INTEGER DEFAULT 0,
                is_rookie INTEGER DEFAULT 0,
                is_shinnyuu_kotei INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(venue_code, race_date, race_number)
            )
        """)
        print("  新テーブル作成完了")

        # Step 4: データコピー
        print("\nStep 4: データコピー中...")
        cursor.execute("""
            INSERT INTO new_races (
                id, venue_code, race_date, race_number, race_time,
                race_grade, race_distance, race_status,
                is_nighter, is_ladies, is_rookie, is_shinnyuu_kotei, created_at
            )
            SELECT
                id, venue_code, race_date, race_number, race_time,
                race_grade, race_distance, race_status,
                is_nighter, is_ladies, is_rookie, is_shinnyuu_kotei, created_at
            FROM races
        """)
        copied_count = cursor.rowcount
        print(f"  データコピー完了: {copied_count:,}件")

        # Step 5: 旧テーブル削除
        print("\nStep 5: 旧テーブル削除中...")
        cursor.execute("DROP TABLE races")
        print("  旧テーブル削除完了")

        # Step 6: リネーム
        print("\nStep 6: テーブルリネーム中...")
        cursor.execute("ALTER TABLE new_races RENAME TO races")
        print("  リネーム完了")

        # Step 7: インデックス再作成
        print("\nStep 7: インデックス再作成中...")

        # UNIQUEインデックスは自動作成されるのでスキップ

        # 個別インデックス
        cursor.execute("CREATE INDEX idx_races_venue_date ON races(venue_code, race_date)")
        cursor.execute("CREATE INDEX idx_races_date ON races(race_date)")
        cursor.execute("CREATE INDEX idx_races_venue_date_number ON races(venue_code, race_date, race_number)")

        print("  インデックス再作成完了")

        # Step 8: VIEW を再作成 (r.grade → r.race_grade に修正)
        print("\nStep 8: VIEW を再作成中...")

        # race_details_extended (grade → race_grade に修正)
        cursor.execute("""
            CREATE VIEW race_details_extended AS
            SELECT
                rd.id as detail_id,
                rd.race_id,
                rd.pit_number,
                rd.exhibition_time,
                rd.tilt_angle,
                rd.parts_replacement,
                rd.actual_course,
                rd.st_time,
                res.rank,
                res.kimarite,
                res.is_invalid,
                res.trifecta_odds,
                r.race_date,
                r.venue_code,
                r.race_number,
                r.title,
                r.race_grade,
                e.racer_number,
                e.racer_name,
                e.motor_number,
                e.boat_number
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            LEFT JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
        """)

        # racer_performance_summary (変更なし)
        cursor.execute("""
            CREATE VIEW racer_performance_summary AS
            SELECT
                e.racer_number,
                e.racer_name,
                COUNT(DISTINCT r.id) as total_races,
                SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 2 THEN 1 ELSE 0 END) as top2,
                SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as top3,
                AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as win_rate,
                AVG(CASE WHEN CAST(res.rank AS INTEGER) <= 2 THEN 1.0 ELSE 0.0 END) as place_rate_2,
                AVG(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1.0 ELSE 0.0 END) as place_rate_3,
                AVG(rd.st_time) as avg_st_time,
                MIN(r.race_date) as first_race_date,
                MAX(r.race_date) as last_race_date
            FROM entries e
            JOIN races r ON e.race_id = r.id
            LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE res.rank IS NOT NULL
            GROUP BY e.racer_number, e.racer_name
        """)

        # venue_statistics_view (変更なし)
        cursor.execute("""
            CREATE VIEW venue_statistics_view AS
            SELECT
                r.venue_code,
                COUNT(DISTINCT r.id) as total_races,
                AVG(CASE WHEN rd.actual_course = 1 AND res.rank = '1' THEN 1.0 ELSE 0.0 END) as course1_win_rate,
                AVG(CASE WHEN rd.actual_course IN (1, 2, 3) AND res.rank = '1' THEN 1.0 ELSE 0.0 END) as inside_win_rate,
                AVG(res.trifecta_odds) as avg_trifecta_odds,
                AVG(CASE WHEN res.trifecta_odds >= 10000 THEN 1.0 ELSE 0.0 END) as high_payout_rate,
                (
                    SELECT res2.kimarite
                    FROM results res2
                    JOIN races r2 ON res2.race_id = r2.id
                    WHERE r2.venue_code = r.venue_code
                      AND res2.rank = '1'
                      AND res2.kimarite IS NOT NULL
                    GROUP BY res2.kimarite
                    ORDER BY COUNT(*) DESC
                    LIMIT 1
                ) as most_common_kimarite,
                MIN(r.race_date) as first_race_date,
                MAX(r.race_date) as last_race_date
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE res.rank = '1'
            GROUP BY r.venue_code
        """)

        print("  VIEW 再作成完了")

        # コミット
        conn.commit()
        print("\n[SUCCESS] Phase 1-1 完了: races.grade カラムを削除しました")

        return True

    except Exception as e:
        print(f"\n[ERROR] エラー発生: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


def execute_phase1_2_remove_winning_technique():
    """Phase 1-2: results.winning_technique カラムの削除"""
    print("\n\n" + "=" * 80)
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
    print("DB最適化 Phase 1 実行")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    print("\n[重要] 実行前にバックアップが作成されていることを確認してください")
    print("バックアップファイル: data/boatrace_backup_YYYYMMDD_HHMMSS.db")

    response = input("\n実行しますか？ (yes/no): ")

    if response.lower() != 'yes':
        print("キャンセルしました")
        return

    # Phase 1-1 実行
    success1 = execute_phase1_1_remove_grade_column()

    if not success1:
        print("\n[ERROR] Phase 1-1 が失敗しました。処理を中断します。")
        return

    # Phase 1-2 実行
    success2 = execute_phase1_2_remove_winning_technique()

    if not success2:
        print("\n[ERROR] Phase 1-2 が失敗しました。")
        print("[INFO] Phase 1-1 は完了していますが、Phase 1-2 は未完了です。")
        return

    # 検証
    verify_schema_changes()

    print("\n" + "=" * 80)
    print("[SUCCESS] Phase 1 完了")
    print("=" * 80)
    print("\n次のステップ:")
    print("1. コード修正:")
    print("   - src/database/data_manager.py:214 の grade 参照を削除")
    print("   - src/database/data_manager.py:568,573 の winning_technique 参照を削除")
    print("2. 動作確認:")
    print("   - 予測処理のテスト実行")
    print("   - UIからのデータ表示確認")


if __name__ == "__main__":
    main()
