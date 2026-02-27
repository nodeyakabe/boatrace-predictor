# -*- coding: utf-8 -*-
"""展示データをCSVに収集（exhibition_time、tilt、ST補完用）

BeforeInfoScraperを使用して2020年以降の展示データを収集し、CSV形式で保存。
後でバルクインポートすることでDB負荷を回避。

使用例:
    # 2020年1月の展示データを収集
    python scripts/data_collection/fetch_exhibition_data_to_csv.py \
        --start 2020-01-01 --end 2020-01-31 \
        --output data/csv/exhibition_data/2020_01 \
        --workers 8

特徴:
- DBアクセスなし、CSVのみに保存
- 並列処理で高速収集（8ワーカー推奨）
- 50レースごとに自動保存
- BeforeInfoScraperで2020年まで遡及可能
"""

import sys
import os
import csv
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
from typing import List, Dict, Optional

# Windows文字コード対策（ThreadPoolExecutorと競合するためコメントアウト）
# if sys.platform == 'win32':
#     import io
#     sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
#     sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

import requests
from bs4 import BeautifulSoup

# スレッドローカルストレージ
thread_local = threading.local()

def get_session():
    """スレッドローカルなHTTPセッションを取得"""
    if not hasattr(thread_local, 'session'):
        thread_local.session = requests.Session()
        thread_local.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
    return thread_local.session


def get_date_range(start_date: str, end_date: str) -> List[str]:
    """日付範囲をリストで返す"""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    return dates


def fetch_exhibition_data(venue_code: str, race_date: str, race_number: int) -> Optional[List[Dict]]:
    """
    1レース分の展示データを取得（全艇分）

    Returns:
        list of dict: [
            {
                'venue_code': '01',
                'race_date': '2020-01-01',
                'race_number': 1,
                'pit_number': 1,
                'exhibition_time': 6.75,
                'tilt': -0.5,
                'st_time': 0.15,
                'exhibition_course': 1
            },
            ... (2-6号艇)
        ]
    """
    session = get_session()
    date_str = race_date.replace('-', '')

    try:
        # 直前情報ページを取得（シンプルなHTTPリクエスト）
        url = "https://www.boatrace.jp/owpc/pc/race/beforeinfo"
        params = {
            "jcd": venue_code,
            "hd": date_str,
            "rno": race_number
        }

        response = session.get(url, params=params, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # データ公開チェック
        error_msg = soup.find('p', class_='is-fs14')
        if error_msg and '情報はありません' in error_msg.get_text():
            return None

        # 展示タイムを取得
        exhibition_times = {}
        table = soup.find('table', class_='is-w748')
        if table:
            tbodies = table.find_all('tbody')
            for tbody in tbodies:
                rows = tbody.find_all('tr', recursive=False)
                if rows:
                    first_row = rows[0]
                    cols = first_row.find_all(['td', 'th'], recursive=False)
                    if len(cols) >= 5:
                        # 枠番
                        pit_text = cols[0].get_text(strip=True)
                        try:
                            pit_number = int(pit_text)
                        except:
                            continue

                        # 展示タイム（Col 4）
                        time_text = cols[4].get_text(strip=True)
                        if time_text:
                            try:
                                time_value = float(time_text)
                                if 5.0 <= time_value <= 10.0:
                                    exhibition_times[pit_number] = time_value
                            except:
                                pass

        # データがない場合はNone
        if not exhibition_times:
            return None

        # 全艇分のデータを作成（シンプル版：exhibition_timeのみ）
        data_list = []
        for pit_number in range(1, 7):
            data_list.append({
                'venue_code': venue_code,
                'race_date': race_date,
                'race_number': race_number,
                'pit_number': pit_number,
                'exhibition_time': exhibition_times.get(pit_number),
                'tilt': None,  # 後で拡張可能
                'st_time': None,  # 後で拡張可能
                'exhibition_course': None  # 後で拡張可能
            })

        return data_list

    except requests.exceptions.Timeout:
        return None
    except Exception as e:
        return None


def fetch_venue_day(args) -> Dict:
    """
    1会場1日分の展示データを取得（並列用）

    Returns:
        {
            'venue_code': '01',
            'race_date': '2020-01-01',
            'success': 5,
            'failed': 7,
            'data': [exhibition_dict, ...]
        }
    """
    venue_code, race_date = args

    success_count = 0
    failed_count = 0
    data = []

    for race_number in range(1, 13):  # 1R-12R
        try:
            details_list = fetch_exhibition_data(venue_code, race_date, race_number)
            if details_list:
                data.extend(details_list)
                success_count += 1
            else:
                failed_count += 1

            time.sleep(0.05)  # レート制限

        except Exception as e:
            failed_count += 1
            # エラーでも続行

    return {
        'venue_code': venue_code,
        'race_date': race_date,
        'success': success_count,
        'failed': failed_count,
        'data': data
    }


def save_to_csv_batch(output_file: Path, data: List[Dict], is_first_batch: bool = False):
    """バッチデータをCSVに追記保存"""
    mode = 'w' if is_first_batch else 'a'

    header = ['venue_code', 'race_date', 'race_number', 'pit_number',
              'exhibition_time', 'tilt', 'st_time', 'exhibition_course']

    with open(output_file, mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=header)

        if is_first_batch:
            writer.writeheader()

        for row in data:
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description='展示データをCSVに収集')
    parser.add_argument('--start', required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--output', required=True, help='出力先ディレクトリ')
    parser.add_argument('--workers', type=int, default=8, help='並列ワーカー数（デフォルト: 8）')
    parser.add_argument('--db', default='data/boatrace.db', help='DBファイルパス')
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / 'exhibition_data.csv'

    print("="*80)
    print("展示データ CSV収集（BeforeInfoScraper使用）")
    print("="*80)
    print(f"期間: {args.start} ～ {args.end}")
    print(f"出力先: {output_file}")
    print(f"並列ワーカー: {args.workers}")
    print()

    # DBから実際の開催スケジュールを取得
    import sqlite3
    conn = sqlite3.connect(args.db, check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT venue_code, race_date
        FROM races
        WHERE race_date BETWEEN ? AND ?
        ORDER BY race_date, venue_code
    """, (args.start, args.end))

    tasks = cursor.fetchall()
    conn.close()

    # タスク準備（スレッディング問題回避）
    print("タスク準備中...")
    task_list = list(tasks)
    task_count = len(task_list)

    print(f"対象タスク数: {task_count:,}件（実開催のみ）")
    print(f"推定レース数: 約{task_count * 6:,}件（1会場日平均6レース）")
    print()
    print("収集を開始します...")
    print()

    # 並列収集
    start_time = time.time()
    total_success = 0
    total_failed = 0
    batch_data = []
    is_first_batch = True

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_venue_day, task): task for task in task_list}

        for i, future in enumerate(as_completed(futures), 1):
            try:
                # 各タスクに最大120秒のタイムアウト
                result = future.result(timeout=120)

                total_success += result['success']
                total_failed += result['failed']

                # 収集したデータをバッチに追加
                batch_data.extend(result['data'])

            except Exception as e:
                # タイムアウトまたはエラーの場合はスキップ
                task_info = futures[future]
                print(f"  タスク失敗: {task_info[0]} {task_info[1]} - {type(e).__name__}")
                total_failed += 12  # 最大12レース分を失敗扱い

            # 50タスクごとにCSV保存
            if i % 50 == 0 or i == task_count:
                if batch_data:
                    save_to_csv_batch(output_file, batch_data, is_first_batch)
                    is_first_batch = False
                    batch_data = []

                elapsed = time.time() - start_time
                races_per_sec = total_success / elapsed if elapsed > 0 else 0
                remaining = task_count - i
                eta = remaining / (i / elapsed) if elapsed > 0 else 0

                print(f"[{i}/{task_count}] "
                      f"成功: {total_success:,} / 失敗: {total_failed:,} / "
                      f"速度: {races_per_sec:.1f}レース/秒 / "
                      f"残り: {eta/60:.1f}分")

    elapsed_time = time.time() - start_time

    print()
    print("="*80)
    print("収集完了")
    print("="*80)
    print(f"成功: {total_success:,}レース")
    print(f"失敗: {total_failed:,}レース")
    if total_success + total_failed > 0:
        print(f"成功率: {total_success/(total_success+total_failed)*100:.1f}%")
    print(f"所要時間: {elapsed_time/60:.1f}分")
    print(f"出力ファイル: {output_file}")
    print()
    print("次のステップ:")
    print(f"  python scripts/maintenance/import_exhibition_data_from_csv.py --input {output_dir}")
    print("="*80)


if __name__ == '__main__':
    main()
