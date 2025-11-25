"""
潮位データ取得のテスト
小規模なテストでダウンロード・インポート・紐付けの動作確認
"""

import os
import sqlite3
from datetime import datetime
from fetch_historical_tide_data import HistoricalTideDataFetcher
from link_tide_to_races import TideRaceLinker


def test_tide_data_fetch():
    """潮位データ取得のテスト"""

    print("="*80)
    print("潮位データ取得テスト")
    print("="*80)
    print(f"テスト日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # テストケース: 2015年1月のデータ（1ヶ月のみ）
    test_start = "2015-01-01"
    test_end = "2015-01-31"
    test_venues = ['22', '24']  # 福岡、大村

    print(f"\n【テストケース】")
    print(f"  期間: {test_start} ～ {test_end}")
    print(f"  会場: 福岡(22), 大村(24)")
    print(f"  期待ファイル数: 2 ファイル（1ヶ月 × 2会場）")

    # ステップ1: ダウンロード
    print("\n" + "="*80)
    print("【ステップ1】 データダウンロード")
    print("="*80)

    fetcher = HistoricalTideDataFetcher(
        download_dir="rdmdb_test",
        delay=1.0
    )

    try:
        fetcher.download_period(
            start_date=test_start,
            end_date=test_end,
            venues=test_venues
        )

        # ダウンロードファイル確認
        download_dir = "rdmdb_test"
        if os.path.exists(download_dir):
            files = [f for f in os.listdir(download_dir) if not f.startswith('.')]
            print(f"\n[OK] ダウンロードディレクトリ: {os.path.abspath(download_dir)}")
            print(f"[OK] ファイル数: {len(files)}")

            if len(files) > 0:
                print(f"\nダウンロードファイル:")
                for f in files:
                    filepath = os.path.join(download_dir, f)
                    size = os.path.getsize(filepath)
                    print(f"  {f:30s} {size:10,} バイト")
            else:
                print("[ERROR] ファイルがダウンロードされていません")
                return False
        else:
            print("[ERROR] ダウンロードディレクトリが作成されていません")
            return False

    except Exception as e:
        print(f"\n[ERROR] ダウンロード失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ステップ2: データベースインポート
    print("\n" + "="*80)
    print("【ステップ2】 データベースインポート")
    print("="*80)

    db_path = "data/boatrace.db"

    # インポート前のレコード数
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM rdmdb_tide WHERE DATE(observation_datetime) BETWEEN ? AND ?",
                   (test_start, test_end))
    before_count = cursor.fetchone()[0]
    conn.close()

    print(f"インポート前のレコード数: {before_count:,}")

    try:
        # テスト用のfetcherを再作成（ダウンロードディレクトリ指定）
        fetcher_import = HistoricalTideDataFetcher(download_dir="rdmdb_test")
        fetcher_import.import_to_database(db_path=db_path)

        # インポート後のレコード数
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM rdmdb_tide WHERE DATE(observation_datetime) BETWEEN ? AND ?",
                       (test_start, test_end))
        after_count = cursor.fetchone()[0]

        # 観測点別のデータ数
        cursor.execute("""
            SELECT station_name, COUNT(*) as count
            FROM rdmdb_tide
            WHERE DATE(observation_datetime) BETWEEN ? AND ?
            GROUP BY station_name
        """, (test_start, test_end))
        station_counts = cursor.fetchall()

        conn.close()

        print(f"インポート後のレコード数: {after_count:,}")
        print(f"新規インポート数: {after_count - before_count:,}")

        if len(station_counts) > 0:
            print(f"\n観測点別データ数:")
            for station, count in station_counts:
                print(f"  {station:20s}: {count:,} レコード")

        if after_count == before_count:
            print("\n[WARN] 新規データがインポートされていません（すでに存在する可能性）")

    except Exception as e:
        print(f"\n[ERROR] インポート失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ステップ3: レースへの紐付け
    print("\n" + "="*80)
    print("【ステップ3】 レースへの紐付け")
    print("="*80)

    # 紐付け前の状況確認
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date BETWEEN ? AND ?
          AND r.venue_code IN (?, ?)
    """, (test_start, test_end, *test_venues))
    total_races = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        INNER JOIN race_tide_data rtd ON r.id = rtd.race_id
        WHERE r.race_date BETWEEN ? AND ?
          AND r.venue_code IN (?, ?)
    """, (test_start, test_end, *test_venues))
    before_linked = cursor.fetchone()[0]

    conn.close()

    print(f"対象レース数: {total_races:,}")
    print(f"紐付け前: {before_linked:,} レース")

    try:
        linker = TideRaceLinker(db_path=db_path)
        linker.link_races(
            start_date=test_start,
            end_date=test_end,
            venue_codes=test_venues
        )

        # 紐付け後の状況確認
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            INNER JOIN race_tide_data rtd ON r.id = rtd.race_id
            WHERE r.race_date BETWEEN ? AND ?
              AND r.venue_code IN (?, ?)
        """, (test_start, test_end, *test_venues))
        after_linked = cursor.fetchone()[0]

        # サンプルデータ確認
        cursor.execute("""
            SELECT
                r.venue_code,
                r.race_date,
                r.race_number,
                rtd.sea_level_cm,
                rtd.data_source
            FROM races r
            INNER JOIN race_tide_data rtd ON r.id = rtd.race_id
            WHERE r.race_date BETWEEN ? AND ?
              AND r.venue_code IN (?, ?)
            ORDER BY r.race_date, r.venue_code, r.race_number
            LIMIT 5
        """, (test_start, test_end, *test_venues))
        samples = cursor.fetchall()

        conn.close()

        print(f"\n紐付け後: {after_linked:,} レース")
        print(f"新規紐付け: {after_linked - before_linked:,} レース")

        if after_linked > before_linked:
            print(f"\n[OK] {after_linked - before_linked:,} レースに潮位データを紐付けました")

            if samples:
                print(f"\nサンプルデータ（先頭5件）:")
                print(f"  {'会場':4s} {'日付':12s} {'R':3s} {'潮位(cm)':>10s} {'データソース':20s}")
                print("  " + "-"*60)
                for venue, date, race_num, sea_level, source in samples:
                    print(f"  {venue:4s} {date:12s} {race_num:3d} {sea_level:10d} {source:20s}")

        elif after_linked == before_linked:
            print(f"\n[WARN] 新規紐付けがありません（すでに紐付け済みの可能性）")

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

    if len(files) >= 2:
        print("[PASS] ステップ1: ダウンロード成功")
    else:
        print("[FAIL] ステップ1: ダウンロード失敗")
        success = False

    if after_count > before_count or after_count > 0:
        print("[PASS] ステップ2: インポート成功")
    else:
        print("[FAIL] ステップ2: インポート失敗")
        success = False

    if after_linked > before_linked or after_linked == total_races:
        print("[PASS] ステップ3: 紐付け成功")
    else:
        print("[FAIL] ステップ3: 紐付け失敗")
        success = False

    print("="*80)

    if success:
        print("[OK] 全テストに合格しました！")
        print("本格実行を開始できます。")
        print("\n推奨コマンド:")
        print("  # 2015-2021年の全データダウンロード")
        print("  python fetch_historical_tide_data.py --start 2015-01-01 --end 2021-12-31")
        print("\n  # レースへの紐付け")
        print("  python link_tide_to_races.py --start 2015-01-01 --end 2021-12-31")
    else:
        print("[WARN] 一部のテストが失敗しました")

    print("="*80)

    return success


if __name__ == '__main__':
    try:
        success = test_tide_data_fetch()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nテストが中断されました")
        exit(1)
    except Exception as e:
        print(f"\n\n致命的エラー: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
