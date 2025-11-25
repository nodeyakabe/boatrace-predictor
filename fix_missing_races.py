"""
欠損レースを再取得してデータベースに保存
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.race_scraper_v2 import RaceScraperV2
from src.database.data_manager import DataManager

def main():
    print("=" * 60)
    print("欠損レース修復")
    print("=" * 60)

    scraper = RaceScraperV2()
    data_manager = DataManager()

    # 欠損レース
    missing_races = [
        ("19", "20251119", 10),  # 下関 10R
        ("22", "20251119", 6),   # 福岡 6R
    ]

    success_count = 0
    for venue_code, race_date, race_number in missing_races:
        print(f"\n会場{venue_code} {race_number}R を取得中...")

        try:
            race_data = scraper.get_race_card(venue_code, race_date, race_number)

            if race_data and race_data.get('entries'):
                # データベースに保存
                if data_manager.save_race_data(race_data):
                    print(f"  ✅ 保存成功: {len(race_data['entries'])}選手")
                    success_count += 1
                else:
                    print(f"  ❌ 保存失敗")
            else:
                print(f"  ❌ データ取得失敗")

        except Exception as e:
            print(f"  ❌ エラー: {e}")

    scraper.close()

    print("\n" + "=" * 60)
    print(f"結果: {success_count}/{len(missing_races)} レース修復完了")
    print("=" * 60)

    # 確認
    import sqlite3
    from config.settings import DATABASE_PATH

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM races WHERE race_date = '2025-11-19'
    """)
    total = cursor.fetchone()[0]

    print(f"\n本日のレース数: {total}件")
    conn.close()


if __name__ == "__main__":
    main()
