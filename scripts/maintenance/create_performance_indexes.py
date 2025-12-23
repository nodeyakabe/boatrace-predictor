"""
パフォーマンス最適化用のインデックスを作成

頻繁にアクセスされるテーブルのカラムにインデックスを追加して、
クエリ速度を劇的に向上させる。
"""

import sqlite3
import sys

def create_indexes(db_path="data/boatrace.db"):
    """パフォーマンス最適化用のインデックスを作成"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("パフォーマンス最適化用インデックスの作成")
    print("=" * 80)

    # インデックス定義
    indexes = [
        # ========================================
        # races テーブル
        # ========================================
        (
            "idx_races_date",
            "CREATE INDEX IF NOT EXISTS idx_races_date ON races(race_date)"
        ),
        (
            "idx_races_venue_date",
            "CREATE INDEX IF NOT EXISTS idx_races_venue_date ON races(venue_code, race_date)"
        ),
        (
            "idx_races_venue_date_number",
            "CREATE INDEX IF NOT EXISTS idx_races_venue_date_number ON races(venue_code, race_date, race_number)"
        ),

        # ========================================
        # results テーブル
        # ========================================
        (
            "idx_results_race_pit",
            "CREATE INDEX IF NOT EXISTS idx_results_race_pit ON results(race_id, pit_number)"
        ),
        (
            "idx_results_race_id",
            "CREATE INDEX IF NOT EXISTS idx_results_race_id ON results(race_id)"
        ),
        (
            "idx_results_rank",
            "CREATE INDEX IF NOT EXISTS idx_results_rank ON results(rank)"
        ),
        (
            "idx_results_invalid",
            "CREATE INDEX IF NOT EXISTS idx_results_invalid ON results(is_invalid)"
        ),

        # ========================================
        # entries テーブル
        # ========================================
        (
            "idx_entries_race_id",
            "CREATE INDEX IF NOT EXISTS idx_entries_race_id ON entries(race_id)"
        ),
        (
            "idx_entries_race_pit",
            "CREATE INDEX IF NOT EXISTS idx_entries_race_pit ON entries(race_id, pit_number)"
        ),
        (
            "idx_entries_racer_number",
            "CREATE INDEX IF NOT EXISTS idx_entries_racer_number ON entries(racer_number)"
        ),
        (
            "idx_entries_motor_number",
            "CREATE INDEX IF NOT EXISTS idx_entries_motor_number ON entries(motor_number)"
        ),
        (
            "idx_entries_boat_number",
            "CREATE INDEX IF NOT EXISTS idx_entries_boat_number ON entries(boat_number)"
        ),

        # ========================================
        # race_details テーブル
        # ========================================
        (
            "idx_race_details_race_id",
            "CREATE INDEX IF NOT EXISTS idx_race_details_race_id ON race_details(race_id)"
        ),
        (
            "idx_race_details_race_pit",
            "CREATE INDEX IF NOT EXISTS idx_race_details_race_pit ON race_details(race_id, pit_number)"
        ),
        (
            "idx_race_details_st_time",
            "CREATE INDEX IF NOT EXISTS idx_race_details_st_time ON race_details(st_time)"
        ),
        (
            "idx_race_details_exhibition_course",
            "CREATE INDEX IF NOT EXISTS idx_race_details_exhibition_course ON race_details(exhibition_course)"
        ),
        (
            "idx_race_details_actual_course",
            "CREATE INDEX IF NOT EXISTS idx_race_details_actual_course ON race_details(actual_course)"
        ),

        # ========================================
        # weather テーブル
        # ========================================
        (
            "idx_weather_race_id",
            "CREATE INDEX IF NOT EXISTS idx_weather_race_id ON weather(race_id)"
        ),

        # ========================================
        # 複合インデックス（JOIN最適化）
        # ========================================
        (
            "idx_results_race_invalid_rank",
            "CREATE INDEX IF NOT EXISTS idx_results_race_invalid_rank ON results(race_id, is_invalid, rank)"
        ),
        (
            "idx_entries_racer_race",
            "CREATE INDEX IF NOT EXISTS idx_entries_racer_race ON entries(racer_number, race_id)"
        ),
    ]

    # インデックス作成
    created_count = 0
    for name, sql in indexes:
        try:
            print(f"作成中: {name}...", end=" ")
            cursor.execute(sql)
            print("OK")
            created_count += 1
        except sqlite3.Error as e:
            print(f"エラー: {e}")

    # コミット
    conn.commit()

    print("=" * 80)
    print(f"完了: {created_count}/{len(indexes)} 個のインデックスを作成")
    print("=" * 80)

    # ANALYZE実行（統計情報更新）
    print("\nデータベース統計情報を更新中...")
    cursor.execute("ANALYZE")
    conn.commit()
    print("OK 統計情報更新完了")

    conn.close()

    return created_count

if __name__ == "__main__":
    db_path = "data/boatrace.db" if len(sys.argv) <= 1 else sys.argv[1]
    created = create_indexes(db_path)

    if created > 0:
        print("\n[OK] インデックス作成が完了しました。")
        print("   クエリパフォーマンスが大幅に向上するはずです。")
    else:
        print("\n[注意] 新しいインデックスは作成されませんでした。")
