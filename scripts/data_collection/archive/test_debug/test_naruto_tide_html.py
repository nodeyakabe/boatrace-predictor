"""
鳴門競艇場の潮見表ページのHTML構造を確認
URL: https://www.n14.jp/modules/datafile/?page=index_tide_table
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import time

def analyze_naruto_tide_page():
    """鳴門競艇場の潮見表ページのHTML構造を分析"""

    chrome_options = Options()
    # headless=False でブラウザを表示して確認
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--log-level=3')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        url = "https://www.n14.jp/modules/datafile/?page=index_tide_table"
        print(f"アクセス中: {url}\n")

        driver.get(url)
        time.sleep(3)  # ページ読み込み待機

        # ページタイトル
        print("="*80)
        print(f"ページタイトル: {driver.title}")
        print("="*80)

        # すべてのテーブルを探す
        tables = driver.find_elements(By.TAG_NAME, "table")
        print(f"\nテーブル数: {len(tables)}個\n")

        for idx, table in enumerate(tables, 1):
            print(f"\n{'='*80}")
            print(f"テーブル {idx}")
            print('='*80)

            # テーブルのclass属性
            table_class = table.get_attribute("class")
            print(f"Class: {table_class}")

            # テーブルの最初の5行を表示
            rows = table.find_elements(By.TAG_NAME, "tr")
            print(f"行数: {len(rows)}")

            print("\n最初の5行のデータ:")
            for row_idx, row in enumerate(rows[:5], 1):
                cells = row.find_elements(By.TAG_NAME, "td")
                if not cells:
                    cells = row.find_elements(By.TAG_NAME, "th")

                cell_texts = [cell.text.strip() for cell in cells]
                print(f"  行{row_idx} ({len(cell_texts)}列): {cell_texts}")

            # テーブル内のテキストを一部表示
            table_text = table.text[:500]
            print(f"\nテーブルテキスト（最初の500文字）:")
            print(table_text)

        # divベースのレイアウトも確認
        print(f"\n{'='*80}")
        print("DIVベースのレイアウト確認")
        print('='*80)

        # 「潮」「干潮」「満潮」というキーワードを含む要素を探す
        elements = driver.find_elements(By.XPATH, "//*[contains(text(), '潮') or contains(text(), '干潮') or contains(text(), '満潮')]")
        print(f"\n「潮」関連の要素数: {len(elements)}個")

        for idx, elem in enumerate(elements[:10], 1):
            tag_name = elem.tag_name
            elem_class = elem.get_attribute("class")
            elem_text = elem.text[:100]
            print(f"\n要素{idx}:")
            print(f"  タグ: {tag_name}")
            print(f"  Class: {elem_class}")
            print(f"  テキスト: {elem_text}")

        # ページのHTML全体を保存（デバッグ用）
        html_content = driver.page_source
        output_file = "temp/naruto_tide_page.html"

        import os
        os.makedirs("temp", exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"\n{'='*80}")
        print(f"ページのHTML全体を保存: {output_file}")
        print('='*80)

    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()

    finally:
        input("\nEnterキーを押すとブラウザを閉じます...")
        driver.quit()

if __name__ == "__main__":
    analyze_naruto_tide_page()
