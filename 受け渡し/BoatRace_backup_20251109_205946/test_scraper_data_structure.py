"""
スクレイパーのデータ構造確認
"""
from src.scraper.result_scraper_improved_v3 import ImprovedResultScraperV3
import json

scraper = ImprovedResultScraperV3()

# テストデータ: 2024-04-03の会場01の1Rを取得
venue_code = '01'
race_date = '2024-04-03'
race_number = 1

print(f"取得中: 会場{venue_code} {race_date} {race_number}R")
print("="*80)

result = scraper.get_race_result_complete(venue_code, race_date, race_number)

if result:
    print("データ構造:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
else:
    print("データなし")

scraper.close()
