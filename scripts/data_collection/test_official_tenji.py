"""
BOAT RACE公式サイトからオリジナル展示データを取得するテストスクリプト

江戸川競艇場（03場）のオリジナル展示データ取得を試みる
"""
import sys
from pathlib import Path

# Windows環境での文字化け対策
if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import json

def test_official_site(venue_code, date_str, race_no, show_browser=False):
    """
    BOAT RACE公式サイトからオリジナル展示データを取得

    Args:
        venue_code: 場コード (例: "03")
        date_str: 日付 (YYYY-MM-DD形式)
        race_no: レース番号
        show_browser: ブラウザを表示するか
    """
    # Chrome設定
    chrome_options = Options()
    if not show_browser:
        chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')

    # ブラウザ起動
    driver_path = ChromeDriverManager().install()
    if 'THIRD_PARTY_NOTICES' in driver_path or not driver_path.endswith('.exe'):
        driver_dir = Path(driver_path).parent
        correct_path = driver_dir / 'chromedriver.exe'
        if not correct_path.exists():
            win32_dir = driver_dir / 'chromedriver-win32'
            if win32_dir.exists():
                correct_path = win32_dir / 'chromedriver.exe'
        if correct_path.exists():
            driver_path = str(correct_path)

    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # 日付を公式サイト形式に変換 (YYYYMMDD)
        hd = date_str.replace('-', '')

        # URL構築
        url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={race_no}&jcd={venue_code}&hd={hd}"

        print(f"アクセス: {url}")
        driver.get(url)

        # ページ読み込み待機
        time.sleep(3)

        # ページHTMLを取得
        page_source = driver.page_source

        # 「データがありません」チェック
        if 'データがありません' in page_source:
            print("❌ データがありません")
            return None

        print("✓ ページ読み込み成功")

        # オリジナル展示データを探す
        # 可能性のあるセレクタをリストアップ
        possible_selectors = [
            '.table1',  # テーブル
            '.is-fs12',  # フォントサイズ12のクラス
            'table',  # 普通のテーブル
            '.is-w495',  # 幅495のクラス
        ]

        print("\n【HTML構造調査】")
        for selector in possible_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                print(f"\n{selector}: {len(elements)}個")
                if elements:
                    # 最初の要素のテキストを取得
                    text = elements[0].text[:200] if elements[0].text else ''
                    print(f"  サンプル: {text}")
            except Exception as e:
                print(f"  エラー: {e}")

        # 展示タイム関連のテキストを検索
        print("\n【キーワード検索】")
        keywords = ['展示タイム', '一周タイム', '回り足', '直線タイム', 'チルト']
        for keyword in keywords:
            if keyword in page_source:
                print(f"✓ '{keyword}' 発見")
                # 周辺のHTML を抽出
                idx = page_source.find(keyword)
                context = page_source[max(0, idx-200):min(len(page_source), idx+200)]
                print(f"  コンテキスト: {context[:100]}...")
            else:
                print(f"❌ '{keyword}' なし")

        # tbody内のデータを探す
        print("\n【テーブルデータ抽出】")
        try:
            tbody_elements = driver.find_elements(By.TAG_NAME, 'tbody')
            print(f"tbody要素: {len(tbody_elements)}個")

            for i, tbody in enumerate(tbody_elements[:3]):  # 最初の3つ
                rows = tbody.find_elements(By.TAG_NAME, 'tr')
                print(f"\ntbody[{i}]: {len(rows)}行")
                for j, row in enumerate(rows[:2]):  # 最初の2行
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    cell_texts = [cell.text for cell in cells]
                    print(f"  行{j}: {cell_texts}")
        except Exception as e:
            print(f"エラー: {e}")

        # スクリーンショット保存
        screenshot_path = project_root / 'temp' / f'official_site_{venue_code}_{hd}_R{race_no}.png'
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(screenshot_path))
        print(f"\nスクリーンショット保存: {screenshot_path}")

        return {
            'url': url,
            'has_data': 'データがありません' not in page_source,
            'keywords_found': {kw: kw in page_source for kw in keywords},
        }

    finally:
        driver.quit()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='BOAT RACE公式サイトのオリジナル展示データ取得テスト')
    parser.add_argument('--venue', type=str, default='03', help='場コード（デフォルト: 03=江戸川）')
    parser.add_argument('--date', type=str, default='2026-01-15', help='日付（YYYY-MM-DD）')
    parser.add_argument('--race', type=int, default=1, help='レース番号')
    parser.add_argument('--show-browser', action='store_true', help='ブラウザを表示')
    args = parser.parse_args()

    print('=' * 80)
    print('BOAT RACE公式サイト オリジナル展示データ取得テスト')
    print('=' * 80)
    print(f'場: {args.venue}')
    print(f'日付: {args.date}')
    print(f'レース: {args.race}R')
    print('=' * 80)
    print()

    result = test_official_site(args.venue, args.date, args.race, args.show_browser)

    if result:
        print('\n' + '=' * 80)
        print('結果')
        print('=' * 80)
        print(json.dumps(result, indent=2, ensure_ascii=False))
