"""
シンプルなテスト: BOATCASTページのHTMLを取得して保存
"""

import asyncio
from playwright.async_api import async_playwright
import sys
from pathlib import Path

# Windows環境での文字化け対策
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

project_root = Path(__file__).resolve().parents[2]


async def main():
    async with async_playwright() as p:
        print("ブラウザを起動中...")
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        url = 'https://race.boatcast.jp/replay?jo=01&md=T'
        print(f"アクセス: {url}")

        await page.goto(url)
        print("ページ読み込み完了")

        # 20秒待機（手動操作用）
        print("\n20秒待機します。この間に手動で以下の操作を行ってください：")
        print("1. 日付を選択")
        print("2. レース番号を選択（例：3R）")
        print("3. 'オリジナル展示データ'タブをクリック")
        print("\n20秒後に自動的にHTMLを保存します...")

        await asyncio.sleep(20)

        # HTMLを保存
        html = await page.content()
        output_file = project_root / 'temp' / 'simple_test.html'
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"\nHTML保存完了: {output_file}")
        print(f"ファイルサイズ: {len(html):,} 文字")

        # データが含まれているか確認
        if 'B1' in html or 'A1' in html or 'A2' in html:
            print("✓ 級別データが見つかりました")
        else:
            print("✗ 級別データが見つかりません")

        if '登録番号' in html or '/4' in html or '/5' in html:
            print("✓ 登録番号らしきデータが見つかりました")
        else:
            print("✗ 登録番号が見つかりません")

        print("\nブラウザを10秒後に閉じます...")
        await asyncio.sleep(10)

        await browser.close()
        print("完了")


if __name__ == '__main__':
    asyncio.run(main())
