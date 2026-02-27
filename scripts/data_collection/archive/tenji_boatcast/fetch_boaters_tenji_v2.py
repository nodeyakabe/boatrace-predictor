"""
Boaters オリジナル展示データ収集スクリプト (Playwright版)

正しいURL: https://boaters-boatrace.com/race/{venue}/{date}/{race}R/last-minute?last-minute-content=original-tenji

使い方:
    # 本日のデータを収集
    python scripts/data_collection/fetch_boaters_tenji.py

    # 特定日のデータを収集
    python scripts/data_collection/fetch_boaters_tenji.py --date 2026-01-15

    # 特定場のデータを収集
    python scripts/data_collection/fetch_boaters_tenji.py --venue 01

    # 単一レースをテスト
    python scripts/data_collection/fetch_boaters_tenji.py --venue 01 --date 2026-01-15 --race 1
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


# 会場コードのマッピング
VENUE_CODE_TO_NAME = {
    '01': 'kiryu',      # 桐生
    '02': 'toda',       # 戸田
    '03': 'edogawa',    # 江戸川
    '04': 'heiwajima',  # 平和島
    '05': 'tamagawa',   # 多摩川
    '06': 'hamanako',   # 浜名湖
    '07': 'gamagori',   # 蒲郡
    '08': 'tokoname',   # 常滑
    '09': 'tsu',        # 津
    '10': 'mikuni',     # 三国
    '11': 'biwako',     # びわこ
    '12': 'suminoe',    # 住之江
    '13': 'amagasaki',  # 尼崎
    '14': 'naruto',     # 鳴門
    '15': 'marugame',   # 丸亀
    '16': 'kojima',     # 児島
    '17': 'miyajima',   # 宮島
    '18': 'tokuyama',   # 徳山
    '19': 'shimonoseki',# 下関
    '20': 'wakamatsu',  # 若松
    '21': 'ashiya',     # 芦屋
    '22': 'fukuoka',    # 福岡
    '23': 'karatsu',    # 唐津
    '24': 'omura',      # 大村
}


async def fetch_tenji_data(page, venue_code, target_date, race_no, retry_count=2):
    """
    指定された場・日付・レース番号のオリジナル展示データを取得

    Args:
        page: Playwrightのページオブジェクト
        venue_code: 場コード (1-24、文字列 "01"～"24")
        target_date: 対象日付 (YYYY-MM-DD)
        race_no: レース番号 (1-12)
        retry_count: リトライ回数

    Returns:
        dict: 展示データ（選手情報、展示タイム等）
    """
    # 会場名に変換
    venue_name = VENUE_CODE_TO_NAME.get(f"{int(venue_code):02d}")
    if not venue_name:
        print(f"  ✗ 不正な会場コード: {venue_code}")
        return None

    # URLを構築
    url = f'https://boaters-boatrace.com/race/{venue_name}/{target_date}/{race_no}R/last-minute?last-minute-content=original-tenji'

    for attempt in range(retry_count):
        try:
            if attempt > 0:
                print(f"  [{venue_code}] {target_date} {race_no}R - リトライ {attempt}/{retry_count-1}")
            else:
                print(f"  [{venue_code}] {target_date} {race_no}R - アクセス中...")
                print(f"    URL: {url}")

            # ページにアクセス
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(5)  # データ読み込み待機（さらに長く）

            # データを抽出
            print(f"    → データ抽出中...")

            tenji_data = await page.evaluate(r'''() => {
                const result = {
                    racers: {},
                    found: false
                };

                // Chakra UIのスタック要素を探す（Boatersサイト用）
                const allDivs = Array.from(document.querySelectorAll('div'));

                // "オリジナル展示"を含むdivを探す
                const tenjiContainer = allDivs.find(div =>
                    div.textContent.includes('オリジナル展示')
                );

                if (tenjiContainer) {
                    // テキストをスペースで分割してパース
                    const text = tenjiContainer.textContent;

                    // 数値パターン（XX.XX形式）を抽出
                    const timeMatches = text.match(/\d+\.\d{2}/g);

                    // 枠番パターン（1～6）を抽出
                    const wakuMatches = text.match(/[1-6][^\d]/g);

                    if (timeMatches && timeMatches.length >= 12) {
                        // 6艇 × 3タイム（半周、回り足、直線展示）= 18個のタイム
                        // ただし、最初の6個が重要（半周 + 回り足 + 直線展示）
                        for (let waku = 1; waku <= 6; waku++) {
                            const baseIdx = (waku - 1) * 3;
                            if (baseIdx + 2 < timeMatches.length) {
                                result.racers[waku] = {
                                    waku: waku,
                                    hanshu: parseFloat(timeMatches[baseIdx]),
                                    mawariashi: parseFloat(timeMatches[baseIdx + 1]),
                                    chokusen: parseFloat(timeMatches[baseIdx + 2]),
                                    raw_text: text.substring(text.indexOf(String(waku)), 200)
                                };
                                result.found = true;
                            }
                        }
                    }
                }

                // ページテキストも取得（デバッグ用）
                result.page_text = document.body.textContent.substring(0, 500);

                return result;
            }''')

            if tenji_data['found'] and len(tenji_data['racers']) > 0:
                print(f"    ✓ データ取得成功: {len(tenji_data['racers'])}名")
                return {
                    'venue_code': int(venue_code),
                    'venue_name': venue_name,
                    'date': target_date,
                    'race_no': race_no,
                    'racers': tenji_data['racers'],
                    'url': url
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

    parser = argparse.ArgumentParser(description='Boaters オリジナル展示データ収集')
    parser.add_argument('--date', type=str, help='対象日付 (YYYY-MM-DD)', default=None)
    parser.add_argument('--venue', type=str, help='場コード (01-24)', default=None)
    parser.add_argument('--race', type=int, help='レース番号 (1-12、指定時は単一レースのみ取得)', default=None)
    parser.add_argument('--headless', action='store_true', help='ヘッドレスモードで実行', default=True)
    parser.add_argument('--show-browser', action='store_true', help='ブラウザを表示（デバッグ用）')
    args = parser.parse_args()

    # デフォルトは本日
    target_date = args.date if args.date else datetime.now().strftime('%Y-%m-%d')

    # デフォルトは全場
    if args.venue:
        venues = [f"{int(args.venue):02d}"]
    else:
        venues = [f"{i:02d}" for i in range(1, 25)]

    # レース範囲
    if args.race:
        race_range = [args.race]
    else:
        race_range = list(range(1, 13))

    # ヘッドレスモード設定
    headless = args.headless and not args.show_browser

    print(f"{'='*80}")
    print(f"Boaters オリジナル展示データ収集")
    print(f"対象日付: {target_date}")
    print(f"対象場: {venues if len(venues) <= 5 else f'{len(venues)}場'}")
    print(f"対象レース: {race_range if len(race_range) <= 3 else f'{len(race_range)}レース'}")
    print(f"ブラウザ表示: {'ON' if not headless else 'OFF'}")
    print(f"{'='*80}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()

        all_results = []

        for venue in venues:
            print(f"\n場コード {venue} ({VENUE_CODE_TO_NAME.get(venue, '不明')}) の処理開始")

            for race_no in race_range:
                result = await fetch_tenji_data(page, venue, target_date, race_no)
                if result:
                    all_results.append(result)

                await asyncio.sleep(0.5)  # レート制限対策

        # 結果を保存
        output_dir = project_root / 'data' / 'tenji' / 'boaters'
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
