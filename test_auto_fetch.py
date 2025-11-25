"""
過去データ自動取得のテスト
最終保存日から1日分のみ取得して動作確認
"""
from datetime import datetime, timedelta
from src.scraper.safe_historical_scraper import SafeHistoricalScraper
import sqlite3

# データベースパス
DB_PATH = "data/boatrace.db"

def get_last_saved_date():
    """最終保存日を取得"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT MAX(race_date) FROM races")
        result = cursor.fetchone()
        conn.close()

        if result and result[0]:
            last_date = datetime.strptime(result[0], '%Y-%m-%d')
            return last_date
        else:
            return None
    except Exception as e:
        print(f"エラー: {e}")
        return None

def main():
    print("=" * 80)
    print("過去データ自動取得テスト")
    print("=" * 80)

    # 最終保存日を確認
    last_saved = get_last_saved_date()

    if last_saved:
        print(f"[OK] 最終保存日: {last_saved.strftime('%Y-%m-%d')}")
        start_date = last_saved + timedelta(days=1)
    else:
        print("[INFO] データがありません。2024-11-13から取得します。")
        start_date = datetime(2024, 11, 13)

    # テスト用に1日分のみ取得
    end_date = start_date

    print(f"[INFO] 取得期間: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    print(f"[INFO] 対象: 全24会場")
    print("=" * 80)
    print()

    # SafeHistoricalScraperで取得
    scraper = SafeHistoricalScraper(safe_mode=True)

    try:
        success_days, failed_days = scraper.fetch_historical_data(
            start_date=start_date,
            end_date=end_date,
            venues=None  # 全会場
        )

        print()
        print("=" * 80)
        print("[OK] テスト完了！")
        print(f"成功: {success_days}日 / 失敗: {failed_days}日")
        print("=" * 80)

    except Exception as e:
        print(f"[ERROR] エラー: {e}")
        import traceback
        traceback.print_exc()

    finally:
        scraper.close()

if __name__ == '__main__':
    main()
