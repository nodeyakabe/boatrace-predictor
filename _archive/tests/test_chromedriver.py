"""ChromeDriverのテスト"""
import sys
sys.path.append('src')

from scraper.original_tenji_browser import OriginalTenjiBrowserScraper

print("="*70)
print("ChromeDriver初期化テスト")
print("="*70)

try:
    print("\nスクレイパー初期化中...")
    scraper = OriginalTenjiBrowserScraper(headless=True)
    print("[OK] ChromeDriver初期化成功!")

    print("\nテストページにアクセス中...")
    scraper.driver.get("https://www.google.com")
    print(f"[OK] ページタイトル: {scraper.driver.title}")

    scraper.close()
    print("\n[OK] すべてのテスト成功!")

except Exception as e:
    print(f"\n[ERROR] エラー発生:")
    print(f"{e}")
    import traceback
    traceback.print_exc()
