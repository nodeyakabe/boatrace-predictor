"""
データベースインデックス最適化
クエリパフォーマンス向上のための複合インデックス追加
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from config.settings import DATABASE_PATH


def optimize_database_indexes():
    """データベースインデックスを最適化"""

    print("=" * 80)
    print("データベースインデックス最適化")
    print("=" * 80)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 既存のインデックスを確認
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type = 'index'
        ORDER BY name
    """)

    existing_indexes = {row[0] for row in cursor.fetchall()}

    print("既存のインデックス:")
    for idx in sorted(existing_indexes):
        if not idx.startswith('sqlite_'):  # システムインデックスを除外
            print(f"  • {idx}")
    print()

    # 追加するインデックス定義
    new_indexes = [
        # レース検索用（日付・会場・レース番号）
        ("idx_races_date_venue_race", "CREATE INDEX IF NOT EXISTS idx_races_date_venue_race ON races(race_date, venue_code, race_number)"),

        # 選手検索用
        ("idx_entries_racer", "CREATE INDEX IF NOT EXISTS idx_entries_racer ON entries(racer_number)"),
        ("idx_entries_race_pit", "CREATE INDEX IF NOT EXISTS idx_entries_race_pit ON entries(race_id, pit_number)"),

        # 結果検索用
        ("idx_results_race_pit", "CREATE INDEX IF NOT EXISTS idx_results_race_pit ON results(race_id, pit_number)"),
        ("idx_results_race_rank", "CREATE INDEX IF NOT EXISTS idx_results_race_rank ON results(race_id, rank)"),

        # レース詳細検索用
        ("idx_race_details_race_pit", "CREATE INDEX IF NOT EXISTS idx_race_details_race_pit ON race_details(race_id, pit_number)"),
        ("idx_race_details_actual_course", "CREATE INDEX IF NOT EXISTS idx_race_details_actual_course ON race_details(actual_course)"),

        # 予測検索用
        ("idx_race_predictions_race", "CREATE INDEX IF NOT EXISTS idx_race_predictions_race ON race_predictions(race_id)"),
        ("idx_race_predictions_confidence", "CREATE INDEX IF NOT EXISTS idx_race_predictions_confidence ON race_predictions(confidence)"),

        # 履歴検索用
        ("idx_prediction_history_race_type", "CREATE INDEX IF NOT EXISTS idx_prediction_history_race_type ON prediction_history(race_id, prediction_type)"),

        # 展示データ検索用
        ("idx_exhibition_data_race", "CREATE INDEX IF NOT EXISTS idx_exhibition_data_race ON exhibition_data(race_id)"),

        # レース条件検索用
        ("idx_race_conditions_race", "CREATE INDEX IF NOT EXISTS idx_race_conditions_race ON race_conditions(race_id)"),

        # 進入コース検索用
        ("idx_actual_courses_race", "CREATE INDEX IF NOT EXISTS idx_actual_courses_race ON actual_courses(race_id)"),
    ]

    added_count = 0
    skipped_count = 0

    print("追加するインデックス:")
    print("-" * 80)

    for idx_name, create_sql in new_indexes:
        if idx_name not in existing_indexes:
            print(f"  ✓ {idx_name}")
            cursor.execute(create_sql)
            added_count += 1
        else:
            print(f"  - {idx_name} (既に存在)")
            skipped_count += 1

    print()

    if added_count > 0:
        conn.commit()
        print(f"{added_count}個のインデックスを追加しました")
    else:
        print("追加するインデックスはありませんでした")

    print(f"スキップ: {skipped_count}個")
    print()

    # VACUUM と ANALYZE を実行
    print("=" * 80)
    print("データベース最適化を実行中...")
    print("=" * 80)
    print()

    print("1. ANALYZE を実行（統計情報を更新）...")
    cursor.execute("ANALYZE")
    print("   完了")
    print()

    print("2. VACUUM を実行（データベースを最適化）...")
    print("   ※ この処理には時間がかかる場合があります")
    # VACUUMはトランザクション外で実行
    conn.commit()
    conn.close()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("VACUUM")
    conn.close()
    print("   完了")
    print()

    # データベースサイズを確認
    db_size = os.path.getsize(DATABASE_PATH) / (1024 * 1024)  # MB
    print(f"データベースサイズ: {db_size:.2f} MB")
    print()

    print("=" * 80)
    print("データベース最適化完了")
    print("=" * 80)


if __name__ == "__main__":
    optimize_database_indexes()
