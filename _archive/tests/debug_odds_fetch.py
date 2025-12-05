#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
オッズ取得デバッグスクリプト
実際のHTML構造を確認
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

def debug_odds_page(venue_code: str, race_date: str, race_number: int):
    """オッズページのHTML構造をデバッグ"""
    url = f"https://www.boatrace.jp/owpc/pc/race/odds3t?rno={race_number}&jcd={venue_code.zfill(2)}&hd={race_date.replace('-', '')}"

    print("="*60)
    print(f"オッズページデバッグ: {venue_code}場 {race_number}R ({race_date})")
    print("="*60)
    print(f"URL: {url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='ja-JP'
            )
            page = context.new_page()

            # ページ読み込み
            page.goto(url, timeout=30000, wait_until='domcontentloaded')
            page.wait_for_timeout(5000)  # JS実行待ち

            title = page.title()
            html = page.content()

            print(f"\nページタイトル: {title}")
            print(f"HTML長さ: {len(html)}")

            # HTML解析
            soup = BeautifulSoup(html, 'html.parser')

            # テーブル数
            tables = soup.find_all('table')
            print(f"\nテーブル数: {len(tables)}")

            # 各テーブルの行数を確認
            for i, table in enumerate(tables):
                rows = table.find_all('tr')
                print(f"  テーブル{i}: {len(rows)}行")
                if len(rows) > 0:
                    first_row_cells = rows[0].find_all(['th', 'td'])
                    print(f"    1行目セル数: {len(first_row_cells)}")

            # エラーメッセージの確認
            error_div = soup.find('div', class_='is-error')
            if error_div:
                print(f"\n[ERROR] エラーメッセージ: {error_div.get_text(strip=True)}")

            # メッセージ確認
            messages = soup.find_all('p', class_='is-p1')
            if messages:
                print(f"\nメッセージ:")
                for msg in messages:
                    print(f"  - {msg.get_text(strip=True)}")

            # 画像確認
            no_data_img = soup.find('img', alt='データがありません')
            if no_data_img:
                print("\n[INFO] 「データがありません」画像が表示されています")

            # HTMLをファイルに保存
            output_file = f"debug_odds_{venue_code}_{race_date}_{race_number}.html"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"\nHTMLを保存: {output_file}")

            browser.close()

    except Exception as e:
        print(f"\n[ERROR] エラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 今日の日付
    today = datetime.now().strftime('%Y%m%d')
    print(f"本日: {today}\n")

    # 戸田競艇場 1R
    debug_odds_page('02', today, 1)

    print("\n" + "="*60)

    # 昨日の日付も試す
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
    print(f"\n昨日: {yesterday}\n")
    debug_odds_page('02', yesterday, 1)
