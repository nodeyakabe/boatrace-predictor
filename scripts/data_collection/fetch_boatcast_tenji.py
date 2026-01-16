"""
BOATCAST オリジナル展示データ収集スクリプト

使い方:
    # 本日のデータを収集
    python scripts/data_collection/fetch_boatcast_tenji.py

    # 特定日のデータを収集
    python scripts/data_collection/fetch_boatcast_tenji.py --date 2026-01-15

    # 特定場のデータを収集
    python scripts/data_collection/fetch_boatcast_tenji.py --venue 01
"""

import asyncio
import json
import argparse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import re

# Windows環境での文字化け対策
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


async def fetch_tenji_data(page, venue_code, target_date, race_no, retry_count=3):
    """
    指定された場・日付・レース番号のオリジナル展示データを取得

    Args:
        page: Playwrightのページオブジェクト
        venue_code: 場コード (1-24)
        target_date: 対象日付 (YYYY-MM-DD)
        race_no: レース番号 (1-12)
        retry_count: リトライ回数

    Returns:
        dict: 展示データ（選手情報、展示タイム等）
    """

    url = f'https://race.boatcast.jp/replay?jo={venue_code:02d}&md=T'

    for attempt in range(retry_count):
        try:
            if attempt > 0:
                print(f"  [{venue_code:02d}] {target_date} {race_no}R - リトライ {attempt}/{retry_count-1}")
            else:
                print(f"  [{venue_code:02d}] {target_date} {race_no}R - アクセス中...")

            # ページにアクセス（初回のみ）
            if attempt == 0:
                await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(3)

            # 日付を選択
            date_selected = await page.evaluate(f'''(targetDate) => {{
                // 日付要素を探してクリック
                const dateElements = Array.from(document.querySelectorAll('*'));
                const targetElement = dateElements.find(el => {{
                    const text = el.textContent;
                    return text && text.includes(targetDate.replace(/-/g, '/'));
                }});

                if (targetElement && targetElement.click) {{
                    targetElement.click();
                    return true;
                }}
                return false;
            }}''', target_date.replace('-', '/'))

            if date_selected:
                if attempt == 0:
                    print(f"    ✓ 日付選択: {target_date}")
                await asyncio.sleep(5)  # 長めに待機
            else:
                if attempt == 0:
                    print(f"    - 日付が見つかりません: {target_date}")
                continue

            # レース番号を選択
            race_selected = await page.evaluate(f'''(raceNo) => {{
                // レース番号ボタンを探してクリック（より正確なセレクタ）
                const buttons = Array.from(document.querySelectorAll('button, a, div[role="button"], span[role="button"]'));
                const raceButton = buttons.find(el => {{
                    const text = el.textContent.trim();
                    // "1R", "2R"などの形式、または数字のみ
                    return text === raceNo + 'R' || text === String(raceNo);
                }});

                if (raceButton && raceButton.click) {{
                    raceButton.click();
                    return true;
                }}
                return false;
            }}''', race_no)

            if race_selected:
                if attempt == 0:
                    print(f"    ✓ レース選択: {race_no}R")
                await asyncio.sleep(8)  # データ読み込み待機をさらに長く
            else:
                if attempt == 0:
                    print(f"    - レースが見つかりません: {race_no}R")
                continue

            # 「オリジナル展示データ」タブをクリック
            # より柔軟な検索
            tab_clicked = await page.evaluate('''() => {
                // ボタンやタブ要素を探す
                const candidates = Array.from(document.querySelectorAll('button, a, div, span, li'));

                // より柔軟なマッチング
                const tab = candidates.find(el => {
                    const text = el.textContent || '';
                    return text.includes('オリジナル展示') ||
                           (text.includes('オリジナル') && text.includes('展示')) ||
                           text === 'オリジナル展示データ';
                });

                if (tab && tab.click) {
                    tab.click();
                    return true;
                }
                return false;
            }''')

            if tab_clicked:
                if attempt == 0:
                    print(f"    ✓ オリジナル展示データタブをクリック")
                await asyncio.sleep(6)  # タブ切り替え待機をさらに長く
            else:
                if attempt == 0:
                    print(f"    - オリジナル展示データタブが見つかりません")

            # データを抽出
            print(f"    → データ抽出中...")

            tenji_data = await page.evaluate('''() => {
                const racers = [];

                // テーブル行を探す（柔軟な検索）
                const rows = Array.from(document.querySelectorAll('tr, [class*="row"], [class*="racer"]'));

                rows.forEach(row => {
                    // 各セルのテキストを取得
                    const cells = Array.from(row.querySelectorAll('td, [class*="cell"], div'));
                    const cellTexts = cells.map(c => c.textContent.trim()).filter(t => t);

                    // 展示タイムっぽい数値（X.XX形式）があるか確認
                    const hasTime = cellTexts.some(text => /\\d+\\.\\d{2}/.test(text));

                    // 登録番号っぽい数値（4桁）があるか確認
                    const hasRegNo = cellTexts.some(text => /\\/\\d{4}/.test(text));

                    if (hasTime && hasRegNo && cellTexts.length >= 5) {
                        racers.push({
                            raw_cells: cellTexts,
                            html: row.innerHTML.substring(0, 500)
                        });
                    }
                });

                return {
                    racers: racers,
                    page_text: document.body.textContent.substring(0, 1000)
                };
            }''')

            if tenji_data['racers'] and len(tenji_data['racers']) > 0:
                print(f"    ✓ データ取得成功: {len(tenji_data['racers'])}名")
                return {
                    'venue_code': venue_code,
                    'date': target_date,
                    'race_no': race_no,
                    'racers': tenji_data['racers'],
                    'raw_page_text': tenji_data['page_text']
                }
            else:
                # リトライする
                if attempt < retry_count - 1:
                    print(f"    - データが見つかりません。リトライします...")
                    await asyncio.sleep(2)
                    continue
                else:
                    print(f"    - データが取得できませんでした（最終試行）")
                    print(f"    デバッグ: {tenji_data['page_text'][:200]}")
                    return None

        except PlaywrightTimeout:
            if attempt < retry_count - 1:
                print(f"    - タイムアウト。リトライします...")
                await asyncio.sleep(2)
                continue
            else:
                print(f"    ✗ タイムアウト（最終試行）")
                return None
        except Exception as e:
            if attempt < retry_count - 1:
                print(f"    - エラー: {e}。リトライします...")
                await asyncio.sleep(2)
                continue
            else:
                print(f"    ✗ エラー（最終試行）: {e}")
                return None

    return None


async def main():
    """メイン処理"""

    parser = argparse.ArgumentParser(description='BOATCAST オリジナル展示データ収集')
    parser.add_argument('--date', type=str, help='対象日付 (YYYY-MM-DD)', default=None)
    parser.add_argument('--venue', type=str, help='場コード (01-24)', default=None)
    parser.add_argument('--headless', action='store_true', help='ヘッドレスモードで実行')
    args = parser.parse_args()

    # デフォルトは本日
    target_date = args.date if args.date else datetime.now().strftime('%Y-%m-%d')

    # デフォルトは全場
    venues = [int(args.venue)] if args.venue else list(range(1, 25))

    print(f"{'='*80}")
    print(f"BOATCAST オリジナル展示データ収集")
    print(f"対象日付: {target_date}")
    print(f"対象場: {venues if len(venues) <= 5 else f'{len(venues)}場'}")
    print(f"{'='*80}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()

        all_results = []

        for venue in venues:
            print(f"\n場コード {venue:02d} の処理開始")

            # 各レース（1-12R）を試行
            for race_no in range(1, 13):
                result = await fetch_tenji_data(page, venue, target_date, race_no)
                if result:
                    all_results.append(result)

                await asyncio.sleep(1)  # レート制限対策

        # 結果を保存
        output_dir = project_root / 'data' / 'tenji' / 'boatcast'
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f'tenji_{target_date.replace("-", "")}.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)

        print(f"\n{'='*80}")
        print(f"収集完了: {len(all_results)}レース")
        print(f"保存先: {output_file}")
        print(f"{'='*80}")

        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
