"""
決まり手データのCSV収集スクリプト（DB書き込みなし）

DB競合を避けるため、収集結果をCSVに出力する。
インポートは import_kimarite_csv.py で別途実施。

使用例:
  python scripts/data_collection/補完_決まり手データ_csv版.py --start-date 2020-01-01 --end-date 2020-12-31
  python scripts/data_collection/補完_決まり手データ_csv版.py --start-date 2022-01-01 --end-date 2022-12-31
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import argparse
import sqlite3
import csv
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
import warnings
warnings.filterwarnings("ignore")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')
CSV_DIR = os.path.join(PROJECT_ROOT, 'data', 'csv', 'kimarite')

thread_local = threading.local()

def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
        thread_local.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    return thread_local.session

def get_races_without_kimarite(start_date=None, end_date=None):
    """欠損レースをDBから取得（読み取りのみ）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "AND r.race_date BETWEEN ? AND ?"
        params = [start_date, end_date]
        print(f"期間フィルター: {start_date} ～ {end_date}")
    elif start_date:
        date_filter = "AND r.race_date >= ?"
        params = [start_date]
    elif end_date:
        date_filter = "AND r.race_date <= ?"
        params = [end_date]

    query = f"""
        SELECT DISTINCT
            r.id,
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE (res.kimarite IS NULL OR res.kimarite = '')
          AND res.rank = '1'
          AND res.is_invalid = 0
          {date_filter}
        ORDER BY r.race_date, r.venue_code, r.race_number
    """
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    print(f"欠損レース: {len(rows):,}件")
    return rows

def fetch_kimarite_fast(args, retry=3):
    """1レースの決まり手を取得"""
    race_id, venue_code, race_date, race_number = args
    date_str = race_date.replace('-', '')
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_number}&jcd={int(venue_code):02d}&hd={date_str}"

    for attempt in range(retry):
        try:
            session = get_session()
            response = session.get(url, timeout=10)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'lxml')

            kimarite = None
            for table in soup.find_all('table'):
                thead = table.find('thead')
                if not thead:
                    continue
                headers = [th.get_text(strip=True) for th in thead.find_all('th')]
                if '決まり手' in headers:
                    tbody = table.find('tbody')
                    if tbody:
                        td = tbody.find('td')
                        if td:
                            text = td.get_text(strip=True)
                            if text and text not in ['', ' ']:
                                kimarite = text
                                break

            if kimarite:
                return {
                    'race_id': race_id,
                    'venue_code': venue_code,
                    'race_date': race_date,
                    'race_number': race_number,
                    'kimarite': kimarite
                }
            else:
                if attempt < retry - 1:
                    time.sleep(1)
                    continue
                return None

        except Exception:
            if attempt < retry - 1:
                time.sleep(1)
                continue
            return None

    return None

def main():
    parser = argparse.ArgumentParser(description='決まり手データCSV収集（DB書き込みなし）')
    parser.add_argument('--start-date', type=str, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--output', type=str, help='出力CSVファイルパス（省略時は自動命名）')
    args = parser.parse_args()

    print("=" * 70)
    print("決まり手データ CSV収集スクリプト（DB書き込みなし）")
    print("=" * 70)

    # 出力ファイルパス決定
    os.makedirs(CSV_DIR, exist_ok=True)
    if args.output:
        csv_path = args.output
    else:
        start_tag = (args.start_date or 'all').replace('-', '')[:8]
        end_tag = (args.end_date or 'all').replace('-', '')[:8]
        csv_path = os.path.join(CSV_DIR, f"kimarite_{start_tag}_{end_tag}.csv")
    print(f"出力先: {csv_path}")

    # 欠損レース取得（DBから読み取りのみ）
    races = get_races_without_kimarite(
        start_date=args.start_date,
        end_date=args.end_date
    )
    if len(races) == 0:
        print("補完が必要なレースはありません。")
        return

    print(f"\n補完対象: {len(races):,}件")
    print("処理を開始します（DB書き込みなし）...")

    success_count = 0
    error_count = 0
    start_time = time.time()
    max_workers = 16

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['race_id', 'venue_code', 'race_date', 'race_number', 'kimarite'])

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_kimarite_fast, race): race for race in races}

            for i, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result()
                    if result:
                        writer.writerow([
                            result['race_id'],
                            result['venue_code'],
                            result['race_date'],
                            result['race_number'],
                            result['kimarite']
                        ])
                        f.flush()
                        success_count += 1
                    else:
                        error_count += 1
                except Exception:
                    error_count += 1

                if i % 200 == 0:
                    elapsed = time.time() - start_time
                    rate = i / elapsed
                    remaining = (len(races) - i) / rate if rate > 0 else 0
                    print(f"進捗: {i:,}/{len(races):,} ({i/len(races)*100:.1f}%) "
                          f"- {rate:.1f}件/秒 - 残り約{remaining/60:.1f}分 "
                          f"(成功:{success_count:,} 失敗:{error_count:,})")

    elapsed_total = time.time() - start_time
    print("\n" + "=" * 70)
    print("収集完了")
    print("=" * 70)
    print(f"対象: {len(races):,}件")
    print(f"成功: {success_count:,}件 ({success_count/len(races)*100:.1f}%)")
    print(f"失敗: {error_count:,}件")
    print(f"処理時間: {elapsed_total/60:.1f}分")
    print(f"出力ファイル: {csv_path}")
    print(f"\n次のステップ: python scripts/data_collection/import_kimarite_csv.py --csv {csv_path}")

if __name__ == "__main__":
    main()
