"""
気象庁潮位表（潮汐表）データ取得のテスト
2015年11月の福岡・大村のデータで動作確認
"""

import sqlite3
import os
from datetime import datetime
from fetch_tide_suisan import TideSuisanFetcher


def test_tide_suisan_fetch():
    """潮位表データ取得のテスト"""

    print("="*80)
    print("気象庁潮位表データ取得テスト")
    print("="*80)
    print(f"テスト日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # テストケース: 2015年11月（福岡・大村）
    test_start = "2015-11-01"
    test_end = "2015-11-30"
    test_venues = ['22', '24']  # 福岡、大村

    print(f"\n[テスト概要]")
    print(f"  期間: {test_start} ~ {test_end}")
    print(f"  会場: 福岡(22), 大村(24)")
    print(f"  データソース: 気象庁潮位表（満潮・干潮）")

    # データベース確認
    db_path = "data/boatrace.db"

    if not os.path.exists(db_path):
        print(f"\n[ERROR] データベースが見つかりません: {db_path}")
        return False

    # インポート前の状態
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM tide
        WHERE tide_date BETWEEN ? AND ?
          AND venue_code IN ('22', '24')
    """, (test_start, test_end))
    before_count = cursor.fetchone()[0]

    conn.close()

    print(f"\nインポート前の状態:")
    print(f"  tideテーブルのレコード数: {before_count:,}")

    # ステップ1: データ取得
    print("\n" + "="*80)
    print("[ステップ1] 潮位表データ取得")
    print("="*80)

    try:
        fetcher = TideSuisanFetcher(
            db_path=db_path,
            delay=1.0  # テストなので短めに
        )

        fetcher.fetch_and_save(
            start_date=test_start,
            end_date=test_end,
            venues=test_venues
        )

    except Exception as e:
        print(f"\n[ERROR] データ取得失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

    # インポート後の状態確認
    print("\n" + "="*80)
    print("[ステップ2] データ検証")
    print("="*80)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 総レコード数
    cursor.execute("""
        SELECT COUNT(*)
        FROM tide
        WHERE tide_date BETWEEN ? AND ?
          AND venue_code IN ('22', '24')
    """, (test_start, test_end))
    after_count = cursor.fetchone()[0]

    # 会場別・潮汐種別の統計
    cursor.execute("""
        SELECT
            venue_code,
            tide_type,
            COUNT(*) as count
        FROM tide
        WHERE tide_date BETWEEN ? AND ?
          AND venue_code IN ('22', '24')
        GROUP BY venue_code, tide_type
        ORDER BY venue_code, tide_type
    """, (test_start, test_end))
    stats = cursor.fetchall()

    # サンプルデータ表示
    cursor.execute("""
        SELECT
            venue_code,
            tide_date,
            tide_time,
            tide_type,
            tide_level
        FROM tide
        WHERE tide_date BETWEEN ? AND ?
          AND venue_code IN ('22', '24')
        ORDER BY venue_code, tide_date, tide_time
        LIMIT 20
    """, (test_start, test_end))
    samples = cursor.fetchall()

    conn.close()

    # 結果表示
    print(f"\nインポート結果:")
    print(f"  インポート前: {before_count:,} レコード")
    print(f"  インポート後: {after_count:,} レコード")
    print(f"  新規インポート: {after_count - before_count:,} レコード")

    if stats:
        print(f"\n会場別・潮汐種別の統計:")
        print(f"  {'会場':4s} {'種別':6s} {'レコード数':>12s}")
        print("  " + "-"*30)
        for venue, tide_type, count in stats:
            venue_name = "福岡" if venue == "22" else "大村"
            print(f"  {venue_name:4s} {tide_type:6s} {count:12,}")

    if samples:
        print(f"\nサンプルデータ（先頭20件）:")
        print(f"  {'会場':4s} {'日付':12s} {'時刻':6s} {'種別':6s} {'潮位(cm)':>10s}")
        print("  " + "-"*50)
        for venue, date, time, tide_type, level in samples[:10]:
            venue_name = "福岡" if venue == "22" else "大村"
            print(f"  {venue_name:4s} {date:12s} {time:6s} {tide_type:6s} {level:10d}")

        if len(samples) > 10:
            print(f"  ... (残り{len(samples)-10}件)")

    # データの妥当性チェック
    print("\n" + "="*80)
    print("[ステップ3] データ妥当性チェック")
    print("="*80)

    success = True

    # チェック1: データが取得できたか
    if after_count > before_count:
        print("[PASS] 新規データが取得できました")
        print(f"       {after_count - before_count:,} レコード")
    else:
        print("[WARN] 新規データがありません（すでに存在する可能性）")

    # チェック2: 満潮・干潮の両方があるか
    tide_types = set(stat[1] for stat in stats)
    if '満潮' in tide_types and '干潮' in tide_types:
        print("[PASS] 満潮・干潮の両方のデータがあります")
    else:
        print("[ERROR] 満潮・干潮のデータが不完全です")
        print(f"        取得できた種別: {tide_types}")
        success = False

    # チェック3: データ量が妥当か（1ヶ月 × 2会場 = 約240レコード想定）
    expected_min = 200  # 1ヶ月 × 2会場 × 4回/日 × 30日 = 240（多少の欠測を考慮）
    expected_max = 300
    actual = after_count - before_count

    if expected_min <= actual <= expected_max:
        print(f"[PASS] データ量が妥当です（{actual:,} レコード）")
        print(f"       想定範囲: {expected_min:,} ~ {expected_max:,}")
    elif actual < expected_min:
        print(f"[WARN] データ量が少ない可能性があります（{actual:,} レコード）")
        print(f"       想定範囲: {expected_min:,} ~ {expected_max:,}")
    else:
        print(f"[INFO] データ量が想定より多いです（{actual:,} レコード）")

    # チェック4: 潮位の値が妥当な範囲か
    if samples:
        tide_levels = [level for _, _, _, _, level in samples]
        min_level = min(tide_levels)
        max_level = max(tide_levels)

        if 0 <= min_level <= 500 and 0 <= max_level <= 500:
            print(f"[PASS] 潮位の値が妥当です（{min_level}cm ~ {max_level}cm）")
        else:
            print(f"[ERROR] 潮位の値が異常です（{min_level}cm ~ {max_level}cm）")
            success = False

    # 総合評価
    print("\n" + "="*80)
    print("テスト結果")
    print("="*80)

    if success and after_count > before_count:
        print("[OK] テストに合格しました！")
        print("\n次のステップ:")
        print("  1. 本格実行:")
        print("     python fetch_tide_suisan.py --start 2015-11-01 --end 2021-12-31")
        print("")
        print("  2. レースへの紐付け:")
        print("     python link_tide_to_races.py --start 2015-11-01 --end 2021-12-31")
        print("")
        print("利点:")
        print("  - データ量: 約5MB（RDMDBの約1/1000）")
        print("  - 実行時間: 約10-20分（RDMDB版の約1/10）")
        print("  - 過去データ: 2015年以前も取得可能")
    else:
        print("[ERROR] テストが失敗しました")
        success = False

    print("="*80)

    return success


if __name__ == '__main__':
    try:
        success = test_tide_suisan_fetch()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nテストが中断されました")
        exit(1)
    except Exception as e:
        print(f"\n\n致命的エラー: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
