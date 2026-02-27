"""
Boatersサイトのデバッグ用スクリプト
実際のHTMLを保存して構造を確認
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


async def debug():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        page = await browser.new_page()

        url = 'https://boaters-boatrace.com/race/kiryu/2026-01-15/1R/last-minute?last-minute-content=original-tenji'

        print(f"アクセス: {url}")
        await page.goto(url, wait_until='networkidle', timeout=30000)
        print("ページ読み込み完了")

        # 10秒待機
        print("\n10秒待機します...")
        await asyncio.sleep(10)

        # HTMLを保存
        html = await page.content()
        output_file = project_root / 'temp' / 'boaters_debug.html'
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"\nHTML保存完了: {output_file}")
        print(f"ファイルサイズ: {len(html):,} 文字")

        # データ要素を探す
        print("\n## データ要素の探索 ##\n")

        # テーブルを探す
        tables_info = await page.evaluate('''() => {
            const tables = Array.from(document.querySelectorAll('table, tbody'));
            return tables.slice(0, 5).map(t => ({
                tag: t.tagName,
                rows: t.querySelectorAll('tr').length,
                cells: t.querySelectorAll('td').length,
                classes: t.className
            }));
        }''')

        print(f"テーブル: {len(tables_info)}個")
        for i, t in enumerate(tables_info, 1):
            print(f"  [{i}] {t['tag']}: {t['rows']}行, {t['cells']}セル (class: {t['classes'][:50]})")

        # "オリジナル"や"展示"を含む要素
        tenji_info = await page.evaluate('''() => {
            const allEls = Array.from(document.querySelectorAll('*'));
            const tenjiEls = allEls.filter(el => {
                const text = el.textContent || '';
                return text.includes('オリジナル') || text.includes('展示') ||
                       text.includes('チルト') || text.includes('回り足');
            });
            return tenjiEls.slice(0, 10).map(el => ({
                tag: el.tagName,
                text: el.textContent.substring(0, 100),
                class: el.className
            }));
        }''')

        print(f"\nオリジナル/展示関連要素: {len(tenji_info)}個")
        for i, el in enumerate(tenji_info, 1):
            print(f"  [{i}] {el['tag']}: {el['text'][:50]} (class: {el['class'][:40]})")

        print("\n\nブラウザを30秒後に閉じます...")
        await asyncio.sleep(30)

        await browser.close()


if __name__ == '__main__':
    asyncio.run(debug())
