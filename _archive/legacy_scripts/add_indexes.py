"""
SQLインデックス追加スクリプト
改善点_1118.md ⑧ SQLインデックス不足の対応
"""

import sqlite3
import time
from pathlib import Path

def add_indexes(db_path="data/boatrace.db"):
    """データベースにインデックスを追加"""

    if not Path(db_path).exists():
        print(f"エラー: データベースファイルが見つかりません: {db_path}")
        return False

    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    # 追加するインデックスのリスト
    indexes = [
        # races テーブル - 日付・会場・レース番号の複合インデックス
        (
            "idx_races_date_venue_number",
            "races",
            "CREATE INDEX IF NOT EXISTS idx_races_date_venue_number ON races(race_date, venue_code, race_number)"
        ),
        # races テーブル - 日付のみのインデックス（日付範囲検索用）
        (
            "idx_races_date",
            "races",
            "CREATE INDEX IF NOT EXISTS idx_races_date ON races(race_date)"
        ),
        # race_details テーブル - race_id と pit_number
        (
            "idx_race_details_race_pit",
            "race_details",
            "CREATE INDEX IF NOT EXISTS idx_race_details_race_pit ON race_details(race_id, pit_number)"
        ),
        # entries テーブル - racer_number（選手検索用）
        (
            "idx_entries_racer_number",
            "entries",
            "CREATE INDEX IF NOT EXISTS idx_entries_racer_number ON entries(racer_number)"
        ),
        # entries テーブル - race_id（レース別エントリー取得用）
        (
            "idx_entries_race_id",
            "entries",
            "CREATE INDEX IF NOT EXISTS idx_entries_race_id ON entries(race_id)"
        ),
        # results テーブル - race_id
        (
            "idx_results_race_id",
            "results",
            "CREATE INDEX IF NOT EXISTS idx_results_race_id ON results(race_id)"
        ),
        # weather テーブル - venue_code と weather_date
        (
            "idx_weather_venue_date",
            "weather",
            "CREATE INDEX IF NOT EXISTS idx_weather_venue_date ON weather(venue_code, weather_date)"
        ),
        # tide テーブル - venue_code と tide_date
        (
            "idx_tide_venue_date",
            "tide",
            "CREATE INDEX IF NOT EXISTS idx_tide_venue_date ON tide(venue_code, tide_date)"
        ),
    ]

    print("=" * 50)
    print("SQLインデックス追加開始")
    print("=" * 50)

    # 既存インデックスを確認
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    existing_indexes = {row[0] for row in cursor.fetchall()}
    print(f"\n既存インデックス数: {len(existing_indexes)}")

    added_count = 0
    skipped_count = 0

    for idx_name, table_name, sql in indexes:
        if idx_name in existing_indexes:
            print(f"  [スキップ] {idx_name} (既に存在)")
            skipped_count += 1
            continue

        print(f"  [追加中] {idx_name} on {table_name}...", end=" ")
        start_time = time.time()

        try:
            cursor.execute(sql)
            elapsed = time.time() - start_time
            print(f"完了 ({elapsed:.2f}秒)")
            added_count += 1
        except Exception as e:
            print(f"エラー: {e}")

    conn.commit()

    # ANALYZE実行（クエリオプティマイザ用の統計情報更新）
    print("\n統計情報を更新中 (ANALYZE)...", end=" ")
    start_time = time.time()
    cursor.execute("ANALYZE")
    elapsed = time.time() - start_time
    print(f"完了 ({elapsed:.2f}秒)")

    conn.close()

    print("\n" + "=" * 50)
    print(f"結果: {added_count}個追加, {skipped_count}個スキップ")
    print("=" * 50)

    return True


def show_indexes(db_path="data/boatrace.db"):
    """現在のインデックス一覧を表示"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, tbl_name, sql
        FROM sqlite_master
        WHERE type='index' AND sql IS NOT NULL
        ORDER BY tbl_name, name
    """)

    indexes = cursor.fetchall()
    conn.close()

    print("\n現在のインデックス一覧:")
    print("-" * 60)

    current_table = None
    for name, table, sql in indexes:
        if table != current_table:
            print(f"\n[{table}]")
            current_table = table
        print(f"  - {name}")

    print(f"\n合計: {len(indexes)}個のインデックス")


if __name__ == "__main__":
    import sys

    db_path = "data/boatrace.db"

    if len(sys.argv) > 1:
        if sys.argv[1] == "--show":
            show_indexes(db_path)
        else:
            db_path = sys.argv[1]
            add_indexes(db_path)
    else:
        add_indexes(db_path)
        show_indexes(db_path)
