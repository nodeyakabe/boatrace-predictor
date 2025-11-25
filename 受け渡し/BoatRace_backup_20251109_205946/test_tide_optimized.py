"""
潮位データ取得のテスト（最適化版）
レース開催日のみをダウンロード
"""

import sqlite3
from datetime import datetime
from fetch_tide_for_races_only import OptimizedTideDataFetcher
from link_tide_to_races import TideRaceLinker


def test_optimized_tide_fetch():
    """最適化版の潮位データ取得テスト"""

    print("="*80)
    print("潮位データ取得テスト（最適化版）")
    print("="*80)
    print(f"テスト日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # テストケース: 2015年11月（福岡・大村）
    test_start = "2015-11-01"
    test_end = "2015-11-30"

    print(f"\n【テスト概要】")
    print(f"  期間: {test_start} ～ {test_end}")
    print(f"  会場: 福岡(22), 大村(24)")
    print(f"  方式: レース開催日のみをダウンロード（最適化版）")

    # レース開催日を確認
    db_path = "data/boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            venue_code,
            COUNT(DISTINCT race_date) as race_days,
            COUNT(*) as total_races
        FROM races
        WHERE race_date BETWEEN ? AND ?
          AND venue_code IN ('22', '24')
        GROUP BY venue_code
    """, (test_start, test_end))

    venue_stats = cursor.fetchall()

    print(f"\nレース開催状況:")
    total_race_days = 0
    total_races = 0
    for venue, days, races in venue_stats:
        venue_name = "福岡" if venue == "22" else "大村"
        print(f"  {venue_name}({venue}): {days}日間, {races}レース")
        total_race_days += days
        total_races += races

    print(f"  合計: {total_race_days}日, {total_races}レース")

    # 推定データ量
    records_per_day = 2880  # 30秒値
    estimated_records = total_race_days * records_per_day
    print(f"\n推定インポートレコード数: 約{estimated_records:,}件")
    print(f"  ({total_race_days}日 × {records_per_day}レコード/日)")

    # インポート前の状態
    cursor.execute("""
        SELECT COUNT(*)
        FROM rdmdb_tide
        WHERE DATE(observation_datetime) BETWEEN ? AND ?
          AND station_name IN ('Hakata', 'Sasebo')
    """, (test_start, test_end))
    before_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        LEFT JOIN race_tide_data rtd ON r.id = rtd.race_id
        WHERE r.race_date BETWEEN ? AND ?
          AND r.venue_code IN ('22', '24')
          AND rtd.race_id IS NULL
    """, (test_start, test_end))
    missing_races = cursor.fetchone()[0]

    conn.close()

    print(f"\nインポート前の状態:")
    print(f"  rdmdb_tideレコード数: {before_count:,}")
    print(f"  潮位未紐付けレース: {missing_races:,}/{total_races}")

    # ステップ1: 最適化版でダウンロード・インポート
    print("\n" + "="*80)
    print("【ステップ1】 最適化版データ取得")
    print("="*80)

    try:
        fetcher = OptimizedTideDataFetcher(
            db_path=db_path,
            download_dir="rdmdb_test_optimized",
            delay=1.0
        )

        fetcher.fetch_optimized(
            start_date=test_start,
            end_date=test_end
        )

        # インポート後の状態
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM rdmdb_tide
            WHERE DATE(observation_datetime) BETWEEN ? AND ?
              AND station_name IN ('Hakata', 'Sasebo')
        """, (test_start, test_end))
        after_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT
                station_name,
                COUNT(*) as count,
                MIN(observation_datetime) as min_dt,
                MAX(observation_datetime) as max_dt
            FROM rdmdb_tide
            WHERE DATE(observation_datetime) BETWEEN ? AND ?
              AND station_name IN ('Hakata', 'Sasebo')
            GROUP BY station_name
        """, (test_start, test_end))
        station_data = cursor.fetchall()

        conn.close()

        print(f"\nインポート結果:")
        print(f"  インポート前: {before_count:,} レコード")
        print(f"  インポート後: {after_count:,} レコード")
        print(f"  新規インポート: {after_count - before_count:,} レコード")

        if station_data:
            print(f"\n観測点別データ:")
            print(f"  {'観測点':15s} {'レコード数':>12s} {'期間':30s}")
            print("  " + "-"*60)
            for station, count, min_dt, max_dt in station_data:
                period = f"{min_dt[:10]} ～ {max_dt[:10]}"
                print(f"  {station:15s} {count:12,} {period:30s}")

        # 実際と推定の比較
        actual_records = after_count - before_count
        efficiency = (actual_records / estimated_records * 100) if estimated_records > 0 else 0
        print(f"\nデータ効率:")
        print(f"  推定: {estimated_records:,} レコード")
        print(f"  実際: {actual_records:,} レコード")
        print(f"  効率: {efficiency:.1f}%")

        if actual_records == 0:
            print("\n[WARN] 新規データがインポートされていません")
            print("       すでにデータが存在するか、ダウンロードに失敗した可能性があります")

    except Exception as e:
        print(f"\n[ERROR] データ取得失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ステップ2: レースへの紐付け
    print("\n" + "="*80)
    print("【ステップ2】 レースへの紐付け")
    print("="*80)

    try:
        linker = TideRaceLinker(db_path=db_path)
        linker.link_races(
            start_date=test_start,
            end_date=test_end,
            venue_codes=['22', '24']
        )

        # 紐付け結果確認
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            INNER JOIN race_tide_data rtd ON r.id = rtd.race_id
            WHERE r.race_date BETWEEN ? AND ?
              AND r.venue_code IN ('22', '24')
        """, (test_start, test_end))
        linked_races = cursor.fetchone()[0]

        # サンプル表示
        cursor.execute("""
            SELECT
                r.venue_code,
                r.race_date,
                r.race_number,
                rtd.sea_level_cm
            FROM races r
            INNER JOIN race_tide_data rtd ON r.id = rtd.race_id
            WHERE r.race_date BETWEEN ? AND ?
              AND r.venue_code IN ('22', '24')
            ORDER BY r.race_date, r.venue_code, r.race_number
            LIMIT 10
        """, (test_start, test_end))
        samples = cursor.fetchall()

        conn.close()

        print(f"\n紐付け結果:")
        print(f"  総レース数: {total_races}")
        if total_races > 0:
            print(f"  紐付け成功: {linked_races} ({linked_races/total_races*100:.1f}%)")
            print(f"  紐付け失敗: {total_races - linked_races}")
        else:
            print(f"  [WARN] 対象レースが0件です")

        if samples:
            print(f"\nサンプルデータ（先頭10件）:")
            print(f"  {'会場':4s} {'日付':12s} {'R':3s} {'潮位(cm)':>10s}")
            print("  " + "-"*35)
            for venue, date, race_num, sea_level in samples:
                venue_name = "福岡" if venue == "22" else "大村"
                print(f"  {venue_name:4s} {date:12s} {race_num:3d} {sea_level:10d}")

    except Exception as e:
        print(f"\n[ERROR] 紐付け失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 総合評価
    print("\n" + "="*80)
    print("テスト結果")
    print("="*80)

    success = True

    if after_count > before_count:
        print("[PASS] ステップ1: データ取得成功")
        print(f"       {after_count - before_count:,} レコードをインポート")
    else:
        print("[WARN] ステップ1: 新規データなし（すでに存在する可能性）")

    if linked_races > 0:
        print("[PASS] ステップ2: 紐付け成功")
        print(f"       {linked_races}/{total_races} レースに紐付け")
    else:
        print("[FAIL] ステップ2: 紐付け失敗")
        success = False

    print("="*80)

    if success or linked_races == total_races:
        print("\n[OK] テストに合格しました！")
        print("\n最適化版の本格実行コマンド:")
        print("  python fetch_tide_for_races_only.py --start 2015-01-01 --end 2021-12-31")
        print("\n利点:")
        print("  - データ量: 全日の約1/5～1/7（約5-8GB）")
        print("  - 実行時間: 大幅短縮（レース開催日のみ処理）")
        print("  - ディスク容量: 大幅節約")
    else:
        print("\n[WARN] 一部のテストが失敗しました")

    print("="*80)

    return success


if __name__ == '__main__':
    try:
        success = test_optimized_tide_fetch()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nテストが中断されました")
        exit(1)
    except Exception as e:
        print(f"\n\n致命的エラー: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
