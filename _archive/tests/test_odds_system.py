"""
オッズシステムの統合テスト
"""
import sys
import sqlite3
from datetime import datetime
from config.settings import DATABASE_PATH

def test_database_tables():
    """データベーステーブルの確認"""
    print("="*70)
    print("データベーステーブル確認")
    print("="*70)

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # テーブル存在確認
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('trifecta_odds', 'win_odds')")
        tables = [row[0] for row in cursor.fetchall()]

        if 'trifecta_odds' in tables:
            print("\n[OK] trifecta_odds テーブルが存在します")
            cursor.execute("PRAGMA table_info(trifecta_odds)")
            columns = cursor.fetchall()
            print("  カラム:")
            for col in columns:
                print(f"    - {col[1]} ({col[2]})")
        else:
            print("\n[NG] trifecta_odds テーブルが存在しません")

        if 'win_odds' in tables:
            print("\n[OK] win_odds テーブルが存在します")
            cursor.execute("PRAGMA table_info(win_odds)")
            columns = cursor.fetchall()
            print("  カラム:")
            for col in columns:
                print(f"    - {col[1]} ({col[2]})")
        else:
            print("\n[NG] win_odds テーブルが存在しません")

        # データ件数確認
        print("\n" + "="*70)
        print("データ件数")
        print("="*70)

        cursor.execute("SELECT COUNT(*) FROM trifecta_odds")
        trifecta_count = cursor.fetchone()[0]
        print(f"\n3連単オッズ: {trifecta_count}件")

        cursor.execute("SELECT COUNT(*) FROM win_odds")
        win_count = cursor.fetchone()[0]
        print(f"単勝オッズ: {win_count}件")

        # 最新のオッズデータを確認
        if trifecta_count > 0:
            print("\n" + "="*70)
            print("最新の3連単オッズ（サンプル）")
            print("="*70)

            cursor.execute("""
                SELECT t.combination, t.odds, t.fetched_at, r.venue_code, r.race_number, r.race_date
                FROM trifecta_odds t
                JOIN races r ON t.race_id = r.id
                ORDER BY t.fetched_at DESC
                LIMIT 5
            """)
            rows = cursor.fetchall()

            for row in rows:
                combo, odds, fetched_at, venue_code, race_number, race_date = row
                print(f"\n  {venue_code} {race_date} {race_number}R: {combo} = {odds}倍")
                print(f"    取得日時: {fetched_at}")

        if win_count > 0:
            print("\n" + "="*70)
            print("最新の単勝オッズ（サンプル）")
            print("="*70)

            cursor.execute("""
                SELECT w.pit_number, w.odds, w.fetched_at, r.venue_code, r.race_number, r.race_date
                FROM win_odds w
                JOIN races r ON w.race_id = r.id
                ORDER BY w.fetched_at DESC
                LIMIT 6
            """)
            rows = cursor.fetchall()

            current_race = None
            for row in rows:
                pit_number, odds, fetched_at, venue_code, race_number, race_date = row
                race_key = f"{venue_code} {race_date} {race_number}R"

                if current_race != race_key:
                    print(f"\n  {race_key}")
                    print(f"    取得日時: {fetched_at}")
                    current_race = race_key

                print(f"    {pit_number}号艇: {odds}倍")

        conn.close()
        print("\n[OK] データベース確認完了")
        return True

    except Exception as e:
        print(f"\n[NG] エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_module_imports():
    """モジュールインポートテスト"""
    print("\n" + "="*70)
    print("モジュールインポート確認")
    print("="*70)

    try:
        print("\n[1] OddsScraperインポート...")
        from src.scraper.odds_scraper import OddsScraper
        print("  [OK] OddsScraper")

        print("\n[2] AutoOddsFetcherインポート...")
        from src.scraper.auto_odds_fetcher import AutoOddsFetcher
        print("  [OK] AutoOddsFetcher")

        print("\n[3] UIコンポーネントインポート...")
        from ui.components.odds_fetcher_ui import render_odds_fetcher
        print("  [OK] render_odds_fetcher")

        print("\n[OK] 全モジュールのインポート成功")
        return True

    except Exception as e:
        print(f"\n[NG] インポートエラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_odds_fetcher_initialization():
    """AutoOddsFetcherの初期化テスト"""
    print("\n" + "="*70)
    print("AutoOddsFetcher初期化テスト")
    print("="*70)

    try:
        from src.scraper.auto_odds_fetcher import AutoOddsFetcher

        print("\n初期化中...")
        fetcher = AutoOddsFetcher(delay=0.5)
        print("[OK] AutoOddsFetcher初期化成功")

        print("\nクローズ中...")
        fetcher.close()
        print("[OK] クローズ成功")

        return True

    except Exception as e:
        print(f"\n[NG] エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_race_data_availability():
    """レースデータの確認"""
    print("\n" + "="*70)
    print("本日のレースデータ確認")
    print("="*70)

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        today = datetime.now().strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT COUNT(*)
            FROM races
            WHERE race_date = ?
        """, (today,))
        today_races = cursor.fetchone()[0]

        print(f"\n本日のレース数: {today_races}件")

        if today_races > 0:
            print("[OK] 本日のレースデータが存在します")

            # サンプル表示
            cursor.execute("""
                SELECT venue_code, race_number, race_time
                FROM races
                WHERE race_date = ?
                ORDER BY venue_code, race_number
                LIMIT 5
            """, (today,))
            rows = cursor.fetchall()

            print("\nサンプル（最初の5レース）:")
            for venue_code, race_number, race_time in rows:
                print(f"  {venue_code} {race_number}R {race_time or '時刻未設定'}")
        else:
            print("[INFO] 本日のレースデータがまだ取得されていません")
            print("       「今日の予想を準備」ボタンでレースデータを取得してください")

        conn.close()
        return True

    except Exception as e:
        print(f"\n[NG] エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "#"*70)
    print("# オッズシステム統合テスト")
    print("#"*70)

    results = []

    # テスト1: モジュールインポート
    results.append(("モジュールインポート", test_module_imports()))

    # テスト2: データベーステーブル
    results.append(("データベーステーブル", test_database_tables()))

    # テスト3: AutoOddsFetcher初期化
    results.append(("AutoOddsFetcher初期化", test_odds_fetcher_initialization()))

    # テスト4: レースデータ確認
    results.append(("レースデータ確認", test_race_data_availability()))

    # 結果サマリー
    print("\n" + "="*70)
    print("テスト結果サマリー")
    print("="*70)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test_name}")

    total_tests = len(results)
    passed_tests = sum(1 for _, result in results if result)

    print(f"\n合計: {passed_tests}/{total_tests} テスト成功")

    if passed_tests == total_tests:
        print("\n[SUCCESS] 全テスト成功！オッズ取得機能は正常に動作します。")
        print("\n次のステップ:")
        print("  1. Streamlit UI で「データ準備」タブを開く")
        print("  2. 「オッズ自動取得」を選択")
        print("  3. まず「今日の予想を準備」でレースデータを取得")
        print("  4. その後「本日のオッズを一括取得」でオッズを取得")
    else:
        print("\n[WARNING] 一部テストが失敗しました。")

    print("\n" + "#"*70)
