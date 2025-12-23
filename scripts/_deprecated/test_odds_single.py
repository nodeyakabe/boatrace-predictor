"""
単一レースのオッズ取得テスト
"""
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.scraper.odds_scraper import OddsScraper
import sqlite3

# 2020年1月7日桐生1Rのオッズを取得
scraper = OddsScraper(delay=1.0, max_retries=3)

print("=" * 60)
print("オッズ取得テスト: 2020-01-07 桐生 1R")
print("=" * 60)

odds_data = scraper.get_trifecta_odds(
    venue_code='01',
    race_date='20200107',
    race_number=1
)

if odds_data:
    print(f"\n取得成功: {len(odds_data)}組み合わせ")
    # 最初の10組だけ表示
    count = 0
    for combo, odds in sorted(odds_data.items()):
        print(f"  {combo}: {odds}倍")
        count += 1
        if count >= 10:
            print(f"  ... (残り{len(odds_data)-10}組)")
            break

    # DBに保存してみる
    print("\nDBへの保存テスト...")
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # race_idを取得
    cursor.execute("""
        SELECT id FROM races
        WHERE venue_code='01' AND race_date='2020-01-07' AND race_number=1
    """)
    result = cursor.fetchone()

    if result:
        race_id = result[0]
        print(f"  race_id: {race_id}")

        # オッズを保存
        for combination, odds_value in odds_data.items():
            cursor.execute("""
                INSERT OR REPLACE INTO trifecta_odds (race_id, combination, odds, fetched_at)
                VALUES (?, ?, ?, datetime('now'))
            """, (race_id, combination, odds_value))

        conn.commit()
        print(f"  保存完了: {len(odds_data)}件")
    else:
        print("  エラー: レースIDが見つかりません")

    conn.close()
else:
    print("\n取得失敗")

print("=" * 60)
