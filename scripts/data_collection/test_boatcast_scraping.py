"""
BOATCAST オリジナル展示データのスクレイピングテスト

使い方:
    python scripts/data_collection/test_boatcast_scraping.py
"""

import asyncio
import json
from playwright.async_api import async_playwright
import sys
import os
from pathlib import Path
from datetime import datetime

# Windows環境での文字化け対策
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


async def test_scraping():
    """BOATCASTサイトからオリジナル展示データをスクレイピング"""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()

        # テスト用URL（桐生、展示モード）
        venue_code = 1
        url = f'https://race.boatcast.jp/replay?jo={venue_code:02d}&md=T'

        print(f"{'='*80}")
        print(f"BOATCAST オリジナル展示データ スクレイピングテスト")
        print(f"URL: {url}")
        print(f"{'='*80}\n")

        try:
            # ページにアクセス
            print("[1] ページにアクセス中...")
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(5)  # データ読み込み待機

            print("✓ ページ読み込み完了\n")

            # 日付とレース選択UIの状態を確認
            print("[2] 利用可能なレース日程を確認...")

            # 日付リストを取得
            dates = await page.evaluate('''() => {
                const dateElements = document.querySelectorAll('[class*="date"], [class*="day"]');
                const results = [];
                dateElements.forEach(el => {
                    const text = el.textContent.trim();
                    if (text.match(/\\d{4}.*\\d{1,2}.*\\d{1,2}/)) {
                        results.push({
                            text: text,
                            class: el.className
                        });
                    }
                });
                return results.slice(0, 10);
            }''')

            if dates:
                print("   検出された日付:")
                for i, date in enumerate(dates[:5], 1):
                    print(f"   [{i}] {date['text']}")
            else:
                print("   日付要素が見つかりません")

            # 「オリジナル展示データ」タブをクリック
            print("\n[3] 「オリジナル展示データ」タブをクリック...")

            # タブを探してクリック
            tab_clicked = await page.evaluate('''() => {
                const tabs = Array.from(document.querySelectorAll('*'));
                const targetTab = tabs.find(el =>
                    el.textContent && el.textContent.includes('オリジナル展示データ')
                );
                if (targetTab) {
                    targetTab.click();
                    return true;
                }
                return false;
            }''')

            if tab_clicked:
                print("✓ タブをクリックしました")
                await asyncio.sleep(3)  # データ表示待機
            else:
                print("✗ タブが見つかりません（既に表示されている可能性）")

            # テーブルデータを取得
            print("\n[4] オリジナル展示データを取得...")

            tenji_data = await page.evaluate('''() => {
                const results = [];

                // テーブル行を探す
                const rows = document.querySelectorAll('tr, [class*="row"], [class*="racer"], [class*="player"]');

                rows.forEach((row, idx) => {
                    const cells = row.querySelectorAll('td, [class*="cell"], [class*="data"]');
                    if (cells.length > 0) {
                        const rowData = {
                            index: idx,
                            cells: []
                        };

                        cells.forEach(cell => {
                            const text = cell.textContent.trim();
                            if (text && text.length > 0 && text.length < 100) {
                                rowData.cells.push({
                                    text: text,
                                    class: cell.className
                                });
                            }
                        });

                        if (rowData.cells.length > 0) {
                            results.push(rowData);
                        }
                    }
                });

                return results.slice(0, 10);
            }''')

            if tenji_data:
                print(f"   検出されたデータ行: {len(tenji_data)}件\n")
                for i, row in enumerate(tenji_data[:6], 1):
                    print(f"   行{i}:")
                    for j, cell in enumerate(row['cells'][:10], 1):
                        print(f"     [{j}] {cell['text']}")
            else:
                print("   データが見つかりません")

            # より詳細な要素解析
            print("\n[5] HTML構造の詳細解析...")

            structure = await page.evaluate('''() => {
                // オリジナル展示データを含む要素を探す
                const allElements = Array.from(document.querySelectorAll('*'));
                const tenjiElements = allElements.filter(el =>
                    el.textContent && (
                        el.textContent.includes('オリジナル展示') ||
                        el.textContent.includes('展示タイム') ||
                        el.textContent.includes('半周ラップ') ||
                        el.textContent.includes('まわり足')
                    )
                );

                const structure = {
                    tenji_containers: [],
                    data_rows: []
                };

                // コンテナ要素の特定
                tenjiElements.slice(0, 5).forEach(el => {
                    structure.tenji_containers.push({
                        tag: el.tagName,
                        class: el.className,
                        id: el.id,
                        text_sample: el.textContent.substring(0, 100)
                    });
                });

                // 数値データを含む要素を探す
                const numberPattern = /\\d+\\.\\d{2}/;  // 6.94 のような展示タイム
                allElements.forEach(el => {
                    const text = el.textContent.trim();
                    if (numberPattern.test(text) && text.length < 20) {
                        structure.data_rows.push({
                            tag: el.tagName,
                            class: el.className,
                            text: text,
                            parent_class: el.parentElement ? el.parentElement.className : ''
                        });
                    }
                });

                return {
                    containers: structure.tenji_containers,
                    number_elements: structure.data_rows.slice(0, 20)
                };
            }''')

            print("   オリジナル展示コンテナ:")
            for i, container in enumerate(structure['containers'][:3], 1):
                print(f"   [{i}] {container['tag']} (class: {container['class'][:50]})")
                print(f"       Text: {container['text_sample'][:80]}")

            print("\n   数値データ要素:")
            for i, elem in enumerate(structure['number_elements'][:10], 1):
                print(f"   [{i}] {elem['tag']}: {elem['text']} (class: {elem['class'][:40]})")

            # スクリーンショットを保存
            output_dir = project_root / 'temp' / 'investigation'
            output_dir.mkdir(parents=True, exist_ok=True)

            screenshot_path = output_dir / 'boatcast_tenji_test.png'
            await page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"\n[6] スクリーンショット保存: {screenshot_path}")

            # HTMLを保存
            html_content = await page.content()
            html_path = output_dir / 'boatcast_tenji_test.html'
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"[7] HTML保存: {html_path}")

            # 結果をJSONで保存
            result = {
                'url': url,
                'dates': dates,
                'tenji_data': tenji_data,
                'structure': structure
            }

            json_path = output_dir / 'boatcast_scraping_test.json'
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"[8] テスト結果保存: {json_path}")

            print(f"\n{'='*80}")
            print("テスト完了")
            print(f"{'='*80}")

            print("\nブラウザを15秒後に閉じます...")
            await asyncio.sleep(15)

        except Exception as e:
            print(f"✗ エラー: {e}")
            import traceback
            traceback.print_exc()

        await browser.close()


if __name__ == '__main__':
    asyncio.run(test_scraping())
