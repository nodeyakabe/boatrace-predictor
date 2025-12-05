"""
RDMDB潮位データ収集改善版のテスト
2023年1月と2022年12月の2ヶ月分をテスト
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.append('src')

import sqlite3
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException
import time
import os
import zipfile
from scraper.rdmdb_tide_parser import RDMDBTideParser

print("="*80)
print("RDMDB潮位データ収集改善版テスト")
print("="*80)

# テスト対象: 2022年12月（30s_形式）と2023年1月（01m_形式）
TEST_YEAR_MONTHS = [
    (2022, 12),
    (2023, 1)
]

# テスト地点: Hiroshima のみ
TEST_STATION = 'Hiroshima'

print(f"\nテスト対象:")
print(f"  期間: {', '.join([f'{y}年{m}月' for y, m in TEST_YEAR_MONTHS])}")
print(f"  地点: {TEST_STATION}")

# ダウンロードディレクトリ
download_dir = os.path.join(os.getcwd(), "rdmdb_tide_data_test")
os.makedirs(download_dir, exist_ok=True)

# DBに接続（テスト用）
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# Chrome設定
chrome_options = Options()
chrome_options.add_experimental_option('prefs', {
    "download.default_directory": download_dir,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
})

print("\nChromeドライバーを起動中...")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

def find_checkbox_for_station(driver, station_name, year):
    """観測地点のチェックボックスを複数のIDフォーマットで探す"""
    # 調査の結果、全期間で30s_形式を使用していることが判明
    id_formats = [
        f"data_kind_30s_{station_name}_JP",
        f"data_kind_{station_name}",
    ]

    for checkbox_id in id_formats:
        try:
            checkbox = driver.find_element(By.ID, checkbox_id)
            print(f"  ✓ チェックボックス発見: {checkbox_id}")
            return checkbox
        except NoSuchElementException:
            print(f"  - チェックボックス未発見: {checkbox_id}")
            continue

    return None

def find_extracted_csv(download_dir, station_name):
    """解凍されたCSVファイルを探す"""
    # .zipでないファイルを全て取得（ディレクトリは除外）
    files = [f for f in os.listdir(download_dir)
             if not f.endswith('.zip') and os.path.isfile(os.path.join(download_dir, f))]

    if files:
        files_with_time = [(f, os.path.getmtime(os.path.join(download_dir, f))) for f in files]
        files_with_time.sort(key=lambda x: x[1], reverse=True)

        # 最新ファイルを返す（拡張子の有無に関わらず）
        latest_file = files_with_time[0][0]
        return os.path.join(download_dir, latest_file)

    return None

# 統計情報
stats = {
    'downloaded': 0,
    'parsed': 0,
    'inserted': 0,
    'errors': 0
}

try:
    for year, month in TEST_YEAR_MONTHS:
        print(f"\n{'='*80}")
        print(f"テスト: {year}年{month}月 {TEST_STATION}")
        print(f"{'='*80}")

        try:
            # 検索ページに移動
            print("  1. 検索ページに移動中...")
            driver.get("https://near-goos1.jodc.go.jp/vpage/index.html")
            time.sleep(2)

            submit_button = driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
            submit_button.click()
            time.sleep(2)

            # 年月を選択
            print(f"  2. {year}年{month}月を選択中...")
            year_select = Select(driver.find_element(By.NAME, "year"))
            year_select.select_by_value(str(year))
            time.sleep(0.5)

            month_radios = driver.find_elements(By.NAME, "month")
            for radio in month_radios:
                if radio.get_attribute("value") == str(month):
                    driver.execute_script("arguments[0].click();", radio)
                    break
            time.sleep(0.5)

            # 観測地点を選択
            print(f"  3. {TEST_STATION}チェックボックスを探索中...")
            checkbox = find_checkbox_for_station(driver, TEST_STATION, year)

            if checkbox is None:
                print(f"  ✗ チェックボックスが見つかりません")
                stats['errors'] += 1
                continue

            driver.execute_script("arguments[0].click();", checkbox)
            time.sleep(0.5)

            # ダウンロードボタンをクリック
            print("  4. ダウンロードボタンをクリック中...")
            forms = driver.find_elements(By.TAG_NAME, "form")
            for form in forms:
                action = form.get_attribute('action')
                if 'download_yearmonth.cgi' in action:
                    buttons = form.find_elements(By.CSS_SELECTOR, "input[type='submit']")
                    if buttons:
                        driver.execute_script("arguments[0].click();", buttons[0])
                        break

            # ダウンロード完了を待つ
            print("  5. ダウンロード完了待機中...")
            time.sleep(8)

            # ZIPファイルを探す
            downloaded_files = [f for f in os.listdir(download_dir) if f.endswith('.zip')]

            if downloaded_files:
                zip_path = os.path.join(download_dir, downloaded_files[-1])
                print(f"  ✓ ZIPファイルダウンロード成功: {downloaded_files[-1]}")
                stats['downloaded'] += 1

                # ZIPを解凍
                print("  6. ZIP解凍中...")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(download_dir)

                # 解凍されたファイルを探す
                data_file = find_extracted_csv(download_dir, TEST_STATION)

                if data_file:
                    print(f"  ✓ 解凍ファイル発見: {os.path.basename(data_file)}")

                    # データをパース
                    print("  7. データパース中...")
                    tide_data = RDMDBTideParser.parse_file(data_file, year, month)

                    if tide_data and len(tide_data) > 0:
                        stats['parsed'] += 1
                        print(f"  ✓ パース成功: {len(tide_data)}レコード")

                        # 最初の3レコードを表示
                        print("\n  サンプルデータ（最初の3レコード）:")
                        for i, data in enumerate(tide_data[:3], 1):
                            print(f"    [{i}] {data['datetime']} - 潮位: {data['sea_level_cm']}cm")

                        # DBに保存
                        print("\n  8. DB保存中...")
                        inserted = 0
                        for data in tide_data:
                            try:
                                cursor.execute("""
                                    INSERT OR IGNORE INTO rdmdb_tide
                                    (station_name, observation_datetime, sea_level_cm,
                                     air_pressure_hpa, temperature_c, sea_level_smoothed_cm)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (TEST_STATION, data['datetime'], data['sea_level_cm'],
                                      data['air_pressure_hpa'], data['temperature_c'],
                                      data['sea_level_smoothed_cm']))

                                if cursor.rowcount > 0:
                                    inserted += 1
                            except Exception as e:
                                pass

                        conn.commit()
                        stats['inserted'] += inserted
                        print(f"  ✓ DB保存成功: {inserted}レコード挿入")

                        # ファイルを削除
                        os.remove(data_file)
                        os.remove(zip_path)
                    else:
                        print(f"  ✗ パース失敗: データ数 0")
                        stats['errors'] += 1
                else:
                    print(f"  ✗ 解凍ファイルが見つかりません")
                    stats['errors'] += 1
            else:
                print(f"  ✗ ZIPファイルがダウンロードされませんでした")
                stats['errors'] += 1

        except Exception as e:
            print(f"  ✗ エラー: {e}")
            import traceback
            traceback.print_exc()
            stats['errors'] += 1

finally:
    driver.quit()
    conn.close()

# 最終集計
print("\n" + "="*80)
print("テスト結果")
print("="*80)
print(f"テスト対象: {len(TEST_YEAR_MONTHS)}ファイル")
print(f"ダウンロード成功: {stats['downloaded']}件")
print(f"パース成功: {stats['parsed']}件")
print(f"DB挿入レコード数: {stats['inserted']:,}件")
print(f"エラー: {stats['errors']}件")

if stats['parsed'] == len(TEST_YEAR_MONTHS):
    print("\n✓ 全テストパス!")
elif stats['parsed'] > 0:
    print(f"\n△ 一部成功 ({stats['parsed']}/{len(TEST_YEAR_MONTHS)})")
else:
    print("\n✗ 全テスト失敗")

print("="*80)
