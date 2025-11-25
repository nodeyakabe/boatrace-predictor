"""
データ保存プロセスのデバッグ
"""

import logging
from src.scraper.bulk_scraper import BulkScraper
from src.database.data_manager import DataManager

# ロギング設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def debug_save_process():
    """データ保存プロセスをデバッグ"""
    print("=" * 70)
    print("データ保存プロセスのデバッグ")
    print("=" * 70)

    scraper = BulkScraper()
    dm = DataManager()

    try:
        # 1レースだけ取得
        print("\n[1] データ取得中...")
        race_data = scraper.scraper.get_race_card("10", "20251113", 2)

        if race_data:
            print(f"\n[OK] データ取得成功")
            print(f"  venue_code: {race_data['venue_code']}")
            print(f"  race_date: {race_data['race_date']}")
            print(f"  race_number: {race_data['race_number']}")
            print(f"  entries数: {len(race_data.get('entries', []))}")

            # データ保存
            print("\n[2] データ保存中...")
            result = dm.save_race_data(race_data)

            if result:
                print("\n[OK] 保存成功")

                # 保存されたデータを確認
                print("\n[3] 保存データ確認中...")
                saved_data = dm.get_race_data(
                    race_data['venue_code'],
                    race_data['race_date'],
                    race_data['race_number']
                )

                if saved_data:
                    print(f"\n[OK] 保存データ確認成功")
                    print(f"  entries数: {len(saved_data.get('entries', []))}")

                    if saved_data.get('entries'):
                        print(f"  1号艇の選手名: {saved_data['entries'][0].get('racer_name')}")
                    else:
                        print("\n[ERROR] entriesが空です！")
                else:
                    print("\n[ERROR] 保存データが取得できませんでした")
            else:
                print("\n[ERROR] 保存失敗")
        else:
            print("\n[ERROR] データ取得失敗")

    except Exception as e:
        print(f"\n[ERROR] エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        scraper.close()


if __name__ == "__main__":
    debug_save_process()
