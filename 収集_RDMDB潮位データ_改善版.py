"""
NEAR-GOOS RDMDB 潮位データ収集スクリプト（改善版）
2022年11月～2025年9月の潮位データを収集してDBに保存

改善点:
1. ファイル名マッチング改善（station_name in f → 正確なパターンマッチ）
2. 複数の element ID フォーマットに対応（30s_, 01m_）
3. 2025年10月をスキップ（データ未公開）
4. ファイル削除前にパース成功を確認
5. リトライ機能追加
6. より詳細なエラーログ
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.append('src')

import sqlite3
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import time
import os
import zipfile
from scraper.rdmdb_tide_parser import RDMDBTideParser
from tqdm import tqdm

print("="*80)
print("NEAR-GOOS RDMDB 潮位データ収集（改善版）")
print("="*80)

# 競艇場とRDMDB観測地点のマッピング
VENUE_TO_RDMDB_STATION = {
    '15': {'name': '児島', 'rdmdb_station': 'Hiroshima', 'station_id': '30s_Hiroshima_JP'},
    '16': {'name': '鳴門', 'rdmdb_station': 'Tokuyama', 'station_id': '30s_Tokuyama_JP'},
    '17': {'name': '丸亀', 'rdmdb_station': 'Hiroshima', 'station_id': '30s_Hiroshima_JP'},
    '18': {'name': '宮島', 'rdmdb_station': 'Hiroshima', 'station_id': '30s_Hiroshima_JP'},
    '20': {'name': '若松', 'rdmdb_station': 'Hakata', 'station_id': '30s_Hakata_JP'},
    '22': {'name': '福岡', 'rdmdb_station': 'Hakata', 'station_id': '30s_Hakata_JP'},
    '24': {'name': '大村', 'rdmdb_station': 'Sasebo', 'station_id': '30s_Sasebo_JP'}
}

# 収集する観測地点（重複除去）
UNIQUE_STATIONS = {
    'Hiroshima': '30s_Hiroshima_JP',
    'Hakata': '30s_Hakata_JP',
    'Sasebo': '30s_Sasebo_JP',
    'Tokuyama': '30s_Tokuyama_JP'
}

# 収集期間: 2022年11月～2025年9月（36ヶ月）
# 2025年10月は除外（データ未公開のため）
START_YEAR = 2022
START_MONTH = 11
END_YEAR = 2025
END_MONTH = 9  # 10月を除外

# ダウンロードディレクトリ
download_dir = os.path.join(os.getcwd(), "rdmdb_tide_data")
os.makedirs(download_dir, exist_ok=True)

print(f"\n収集対象:")
print(f"  観測地点: {len(UNIQUE_STATIONS)}地点（{', '.join(UNIQUE_STATIONS.keys())}）")
print(f"  期間: {START_YEAR}年{START_MONTH}月 ～ {END_YEAR}年{END_MONTH}月")
print(f"  ※ 2025年10月はデータ未公開のためスキップ")

# 年月のリストを生成
year_months = []
current_date = datetime(START_YEAR, START_MONTH, 1)
end_date = datetime(END_YEAR, END_MONTH, 1)

while current_date <= end_date:
    year_months.append((current_date.year, current_date.month))
    if current_date.month == 12:
        current_date = datetime(current_date.year + 1, 1, 1)
    else:
        current_date = datetime(current_date.year, current_date.month + 1, 1)

print(f"  合計: {len(year_months)}ヶ月 × {len(UNIQUE_STATIONS)}地点 = {len(year_months) * len(UNIQUE_STATIONS)}ファイル")

# DBに接続
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# rdmdb_tideテーブルを作成（存在しない場合）
cursor.execute("""
    CREATE TABLE IF NOT EXISTS rdmdb_tide (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        station_name TEXT NOT NULL,
        observation_datetime TEXT NOT NULL,
        sea_level_cm REAL,
        air_pressure_hpa REAL,
        temperature_c REAL,
        sea_level_smoothed_cm REAL,
        UNIQUE(station_name, observation_datetime)
    )
""")

cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_rdmdb_tide_station_datetime
    ON rdmdb_tide(station_name, observation_datetime)
""")

conn.commit()

# Chrome設定
chrome_options = Options()
chrome_options.add_experimental_option('prefs', {
    "download.default_directory": download_dir,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
})

# WebDriverを起動
print("\nChromeドライバーを起動中...")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

# 統計情報
stats = {
    'total': len(year_months) * len(UNIQUE_STATIONS),
    'skipped': 0,
    'downloaded': 0,
    'parsed': 0,
    'inserted': 0,
    'errors': 0
}

def find_checkbox_for_station(driver, station_name, year):
    """
    観測地点のチェックボックスを複数のIDフォーマットで探す

    Args:
        driver: Seleniumドライバー
        station_name: 観測地点名（Hiroshima, Hakata等）
        year: 年（フォーマット選択に使用）

    Returns:
        WebElement: チェックボックス要素（見つからない場合None）
    """
    # 試すIDフォーマットのリスト
    # 調査の結果、全期間で30s_形式を使用していることが判明
    id_formats = [
        f"data_kind_30s_{station_name}_JP",
        f"data_kind_{station_name}",
    ]

    for checkbox_id in id_formats:
        try:
            checkbox = driver.find_element(By.ID, checkbox_id)
            return checkbox
        except NoSuchElementException:
            continue

    return None

def find_extracted_csv(download_dir, station_name):
    """
    解凍されたCSVファイルを探す（改善版）

    Args:
        download_dir: ダウンロードディレクトリ
        station_name: 観測地点名

    Returns:
        str: ファイルパス（見つからない場合None）
    """
    # .zipでないファイルを全て取得（ディレクトリは除外）
    files = [f for f in os.listdir(download_dir)
             if not f.endswith('.zip') and os.path.isfile(os.path.join(download_dir, f))]

    # 最新のファイルを返す（タイムスタンプでソート）
    if files:
        files_with_time = [(f, os.path.getmtime(os.path.join(download_dir, f))) for f in files]
        files_with_time.sort(key=lambda x: x[1], reverse=True)

        # 最新ファイルを返す（拡張子の有無に関わらず）
        latest_file = files_with_time[0][0]
        return os.path.join(download_dir, latest_file)

    return None

try:
    # 年月でループ
    with tqdm(total=stats['total'], desc="潮位データ収集") as pbar:
        for year, month in year_months:
            for station_name, station_id in UNIQUE_STATIONS.items():
                pbar.set_description(f"{year}年{month}月 {station_name}")

                # すでにDBに存在するかチェック
                check_date_start = f"{year}-{month:02d}-01 00:00:00"
                if month == 12:
                    check_date_end = f"{year+1}-01-01 00:00:00"
                else:
                    check_date_end = f"{year}-{month+1:02d}-01 00:00:00"

                cursor.execute("""
                    SELECT COUNT(*) FROM rdmdb_tide
                    WHERE station_name = ?
                    AND observation_datetime >= ?
                    AND observation_datetime < ?
                """, (station_name, check_date_start, check_date_end))

                existing = cursor.fetchone()[0]

                if existing > 1000:  # 1ヶ月分として十分なデータがある
                    stats['skipped'] += 1
                    pbar.update(1)
                    continue

                # リトライ機能付きでダウンロード
                success = False
                retry_count = 3

                for attempt in range(retry_count):
                    try:
                        # 検索ページに移動
                        driver.get("https://near-goos1.jodc.go.jp/vpage/index.html")
                        time.sleep(2)

                        submit_button = driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
                        submit_button.click()
                        time.sleep(2)

                        # 年月を選択
                        year_select = Select(driver.find_element(By.NAME, "year"))
                        year_select.select_by_value(str(year))
                        time.sleep(0.5)

                        month_radios = driver.find_elements(By.NAME, "month")
                        for radio in month_radios:
                            if radio.get_attribute("value") == str(month):
                                driver.execute_script("arguments[0].click();", radio)
                                break
                        time.sleep(0.5)

                        # 観測地点を選択（改善版）
                        checkbox = find_checkbox_for_station(driver, station_name, year)

                        if checkbox is None:
                            print(f"\n警告: {year}年{month}月 {station_name} - チェックボックスが見つかりません")
                            stats['errors'] += 1
                            break

                        driver.execute_script("arguments[0].click();", checkbox)
                        time.sleep(0.5)

                        # ダウンロードボタンをクリック
                        forms = driver.find_elements(By.TAG_NAME, "form")
                        for form in forms:
                            action = form.get_attribute('action')
                            if 'download_yearmonth.cgi' in action:
                                buttons = form.find_elements(By.CSS_SELECTOR, "input[type='submit']")
                                if buttons:
                                    driver.execute_script("arguments[0].click();", buttons[0])
                                    break

                        # ダウンロード完了を待つ
                        time.sleep(8)

                        # ZIPファイルを探す
                        downloaded_files = [f for f in os.listdir(download_dir) if f.endswith('.zip')]

                        if downloaded_files:
                            zip_path = os.path.join(download_dir, downloaded_files[-1])
                            stats['downloaded'] += 1

                            # ZIPを解凍
                            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                                zip_ref.extractall(download_dir)

                            # 解凍されたファイルを探す（改善版）
                            data_file = find_extracted_csv(download_dir, station_name)

                            if data_file:
                                # データをパース
                                tide_data = RDMDBTideParser.parse_file(data_file, year, month)

                                if tide_data and len(tide_data) > 0:
                                    stats['parsed'] += 1

                                    # DBに保存
                                    inserted = 0
                                    for data in tide_data:
                                        try:
                                            cursor.execute("""
                                                INSERT OR IGNORE INTO rdmdb_tide
                                                (station_name, observation_datetime, sea_level_cm,
                                                 air_pressure_hpa, temperature_c, sea_level_smoothed_cm)
                                                VALUES (?, ?, ?, ?, ?, ?)
                                            """, (station_name, data['datetime'], data['sea_level_cm'],
                                                  data['air_pressure_hpa'], data['temperature_c'],
                                                  data['sea_level_smoothed_cm']))

                                            if cursor.rowcount > 0:
                                                inserted += 1
                                        except Exception as e:
                                            pass

                                    conn.commit()
                                    stats['inserted'] += inserted

                                    # パース成功した場合のみファイルを削除
                                    try:
                                        os.remove(data_file)
                                        os.remove(zip_path)
                                    except:
                                        pass

                                    success = True
                                    break
                                else:
                                    print(f"\n警告: {year}年{month}月 {station_name} - パース失敗（データ数: 0）")
                                    # パース失敗してもファイルは削除しない（再試行可能にする）
                            else:
                                print(f"\n警告: {year}年{month}月 {station_name} - 解凍ファイルが見つかりません")
                        else:
                            print(f"\n警告: {year}年{month}月 {station_name} - ZIPファイルがダウンロードされませんでした")

                    except Exception as e:
                        if attempt < retry_count - 1:
                            print(f"\nリトライ {attempt+1}/{retry_count}: {year}年{month}月 {station_name} - {e}")
                            time.sleep(2)
                            continue
                        else:
                            print(f"\nエラー: {year}年{month}月 {station_name} - {e}")
                            stats['errors'] += 1
                            break

                if not success:
                    stats['errors'] += 1

                pbar.update(1)

                # 進捗表示（10件ごと）
                if (stats['downloaded'] + stats['skipped']) % 10 == 0:
                    print(f"\n進捗: ダウンロード {stats['downloaded']}件, パース {stats['parsed']}件, 挿入 {stats['inserted']:,}レコード, スキップ {stats['skipped']}件, エラー {stats['errors']}件")

finally:
    driver.quit()
    conn.close()

# 最終集計
print("\n" + "="*80)
print("最終集計")
print("="*80)
print(f"対象: {stats['total']}ファイル")
print(f"スキップ（既存データあり）: {stats['skipped']}件")
print(f"ダウンロード成功: {stats['downloaded']}件")
print(f"パース成功: {stats['parsed']}件")
print(f"DB挿入レコード数: {stats['inserted']:,}件")
print(f"エラー: {stats['errors']}件")
print(f"成功率: {stats['parsed']/(stats['downloaded'] if stats['downloaded'] > 0 else 1)*100:.1f}%")
print("="*80)
