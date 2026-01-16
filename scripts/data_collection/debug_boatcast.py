"""
BOATCAST デバッグ用スクリプト
実際の画面を表示してHTML構造を確認
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

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


async def debug():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)  # ゆっくり実行
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()

        venue_code = 1
        url = f'https://race.boatcast.jp/replay?jo={venue_code:02d}&md=T'

        print(f"ページにアクセス: {url}")
        await page.goto(url, wait_until='domcontentloaded')
        await asyncio.sleep(5)

        print("\n1. 日付選択ボタンを探します...")
        # 日付ボタンを探して表示
        date_info = await page.evaluate('''() => {
            const today = new Date();
            const dateStr = today.getFullYear() + '/' +
                          String(today.getMonth() + 1).padStart(2, '0') + '/' +
                          String(today.getDate()).padStart(2, '0');

            const allElements = Array.from(document.querySelectorAll('*'));
            const dateElements = allElements.filter(el =>
                el.textContent && el.textContent.includes(dateStr)
            );

            return dateElements.slice(0, 5).map(el => ({
                tag: el.tagName,
                text: el.textContent.substring(0, 100),
                class: el.className
            }));
        }''')

        print(f"日付要素候補: {len(date_info)}個")
        for i, info in enumerate(date_info, 1):
            print(f"  [{i}] {info['tag']}: {info['text']}")

        print("\n2. レース番号ボタンを探します...")
        race_info = await page.evaluate('''() => {
            const allElements = Array.from(document.querySelectorAll('*'));
            const raceElements = allElements.filter(el => {
                const text = el.textContent.trim();
                return text.match(/^\\d{1,2}R$/) || (text.length <= 2 && text.match(/^\\d{1,2}$/));
            });

            return raceElements.slice(0, 20).map(el => ({
                tag: el.tagName,
                text: el.textContent.trim(),
                class: el.className,
                clickable: el.click !== undefined
            }));
        }''')

        print(f"レース番号候補: {len(race_info)}個")
        for i, info in enumerate(race_info, 1):
            print(f"  [{i}] {info['tag']}: '{info['text']}' (class: {info['class'][:40]})")

        print("\n3. オリジナル展示データタブを探します...")
        tab_info = await page.evaluate('''() => {
            const allElements = Array.from(document.querySelectorAll('*'));
            const tabElements = allElements.filter(el =>
                el.textContent && el.textContent.includes('オリジナル展示')
            );

            return tabElements.map(el => ({
                tag: el.tagName,
                text: el.textContent.substring(0, 50),
                class: el.className
            }));
        }''')

        print(f"タブ要素候補: {len(tab_info)}個")
        for i, info in enumerate(tab_info, 1):
            print(f"  [{i}] {info['tag']}: {info['text']} (class: {info['class'][:40]})")

        print("\n\n手動で以下の操作を行ってください:")
        print("1. 日付を選択")
        print("2. レース番号を選択")
        print("3. オリジナル展示データタブをクリック")
        print("\n操作完了後、Enterキーを押してください...")

        input()  # ユーザー操作待ち

        print("\n4. データテーブルを探します...")
        table_info = await page.evaluate('''() => {
            const results = {
                tables: [],
                tenji_elements: [],
                number_elements: []
            };

            // テーブル要素
            const tables = Array.from(document.querySelectorAll('table, tbody'));
            results.tables = tables.slice(0, 3).map(t => ({
                tag: t.tagName,
                rows: t.querySelectorAll('tr').length,
                cells: t.querySelectorAll('td').length
            }));

            // 展示関連のクラス名を持つ要素
            const tenjiEls = Array.from(document.querySelectorAll('[class*="tenji"], [class*="exhibition"]'));
            results.tenji_elements = tenjiEls.slice(0, 10).map(el => ({
                tag: el.tagName,
                class: el.className,
                text: el.textContent.substring(0, 50)
            }));

            // 数値データ（展示タイム等）を含む要素
            const numberPattern = /\\d+\\.\\d{2}/;
            const allEls = Array.from(document.querySelectorAll('*'));
            const numberEls = allEls.filter(el => {
                const text = el.textContent.trim();
                return numberPattern.test(text) && text.length < 20;
            });
            results.number_elements = numberEls.slice(0, 10).map(el => ({
                tag: el.tagName,
                class: el.className,
                text: el.textContent.trim()
            }));

            return results;
        }''')

        print(f"\nテーブル: {len(table_info['tables'])}個")
        for i, t in enumerate(table_info['tables'], 1):
            print(f"  [{i}] {t['tag']}: {t['rows']}行, {t['cells']}セル")

        print(f"\n展示関連要素: {len(table_info['tenji_elements'])}個")
        for i, el in enumerate(table_info['tenji_elements'], 1):
            print(f"  [{i}] {el['tag']}: {el['text']} (class: {el['class'][:40]})")

        print(f"\n数値要素: {len(table_info['number_elements'])}個")
        for i, el in enumerate(table_info['number_elements'], 1):
            print(f"  [{i}] {el['tag']}: '{el['text']}' (class: {el['class'][:40]})")

        # HTMLを保存
        html = await page.content()
        output_file = project_root / 'temp' / 'investigation' / 'boatcast_debug.html'
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"\nHTML保存: {output_file}")

        print("\n\nブラウザを閉じるにはEnterキーを押してください...")
        input()

        await browser.close()


if __name__ == '__main__':
    asyncio.run(debug())
