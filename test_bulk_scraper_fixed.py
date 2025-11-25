"""
BulkScraperのcp932エンコーディング修正テスト
2025-11-13のレースデータを取得してエラーが出ないか確認
"""

from src.scraper.bulk_scraper import BulkScraper
from src.database.data_manager import DataManager
from datetime import datetime

def test_bulk_scraper():
    """
    BulkScraperのテスト
    2025-11-13の1会場を取得して、エンコーディングエラーが出ないか確認
    """
    print("=" * 70)
    print("BulkScraper cp932修正テスト")
    print("=" * 70)

    # テスト対象の日付と会場
    test_date = "20251113"
    test_venue = "10"  # 若松
    test_races = 12  # 全12レース

    print(f"\nテスト日付: {test_date}")
    print(f"テスト会場: {test_venue} (若松)")
    print(f"取得レース数: {test_races}R\n")

    # BulkScraperを初期化
    scraper = BulkScraper()

    try:
        # レースデータを取得
        print("レースデータ取得開始...\n")
        races = scraper.fetch_all_races(test_venue, test_date, test_races)

        print("\n" + "=" * 70)
        print(f"取得結果: {len(races)}件のレースデータを取得")
        print("=" * 70)

        if len(races) > 0:
            print("\n[OK] データ取得成功！")
            print(f"サンプルデータ（1R目）:")
            print(f"  レース番号: {races[0]['race_number']}")
            print(f"  選手数: {len(races[0]['entries'])}名")
            print(f"  レース時刻: {races[0]['race_time']}")

            # DBに保存してみる
            print("\n" + "=" * 70)
            print("データベースへの保存テスト")
            print("=" * 70)

            dm = DataManager()
            success_count = 0
            error_count = 0

            for race in races:
                try:
                    if dm.save_race_data(race):
                        success_count += 1
                        print(f"[OK] {race['race_number']}R 保存成功")
                    else:
                        error_count += 1
                        print(f"[NG] {race['race_number']}R 保存失敗")
                except Exception as e:
                    error_count += 1
                    print(f"[ERROR] {race['race_number']}R エラー: {e}")

            print("\n" + "=" * 70)
            print("保存結果")
            print("=" * 70)
            print(f"成功: {success_count}件")
            print(f"失敗: {error_count}件")

            return True
        else:
            print("\n[NG] データが取得できませんでした")
            return False

    except Exception as e:
        print(f"\n[ERROR] テスト失敗: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        scraper.close()


if __name__ == "__main__":
    result = test_bulk_scraper()

    if result:
        print("\n" + "=" * 70)
        print("[OK] cp932エンコーディング問題は修正されました！")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("[NG] 問題が残っています")
        print("=" * 70)
