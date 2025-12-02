"""既存データでスクレイパーをテスト"""
import time
from src.scraper.bulk_scraper import BulkScraper

scraper = BulkScraper()
start = time.time()

result = scraper.fetch_multiple_venues(['01'], '20251128', 12)

scraper.close()

elapsed = time.time() - start
race_count = len(result.get('01', []))

print(f'\n所要時間: {elapsed:.1f}秒')
print(f'取得レース数: {race_count}')
