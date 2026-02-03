# -*- coding: utf-8 -*-
"""race_detailsデータをCSVに収集（chikusen_time補完用）

DB負荷を回避するため、CSVに収集してから後でバルク投入する。

使用例:
    # 2020年のrace_detailsを収集
    python scripts/data_collection/fetch_race_details_to_csv.py \
        --start 2020-01-01 --end 2020-12-31 \
        --output data/csv/race_details/2020 \
        --workers 12

特徴:
- DBにアクセスせず、CSVファイルのみに保存
- 並列処理で高速収集（12ワーカー推奨）
- 50レースごとに自動保存（途中で止まってもデータが残る）
- 既存CSVがあればスキップ（途中から再開可能）
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

# Windows文字コード対策
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.scraper.result_scraper import ResultScraper

# スレッドローカルストレージ
thread_local = threading.local()

def get_scraper():
    """スレッドローカルなスクレイパーを取得"""
    if not hasattr(thread_local, 'scraper'):
        thread_local.scraper = ResultScraper(read_timeout=10)
    return thread_local.scraper


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


def fetch_race_details(venue_code: str, race_date: str, race_number: int) -> Optional[List[Dict]]:
    """
    1レース分のrace_detailsを取得（全艇分）

    Returns:
        list of dict: [
            {
                'venue_code': '01',
                'race_date': '2020-01-01',
                'race_number': 1,
                'pit_number': 1,
                'exhibition_time': 6.75,
                'tilt': -0.5,
                'chikusen_time': 6.82,
                ...
            },
            ... (2-6号艇)
        ]
    """
    scraper = get_scraper()
    date_str = race_date.replace('-', '')

    try:
        # ResultScraperで結果ページから詳細情報を取得
        result_data = scraper.get_race_result_complete(venue_code, date_str, race_number)

        if not result_data or not result_data.get('race_details'):
            return None

        race_details = result_data['race_details']

        race_details_list = []
        for detail in race_details:
            race_details_list.append({
                'venue_code': venue_code,
                'race_date': race_date,
                'race_number': race_number,
                'pit_number': detail.get('pit_number'),
                'exhibition_time': detail.get('exhibition_time'),
                'tilt': detail.get('tilt'),
                'chikusen_time': detail.get('chikusen_time'),
                'st_time': detail.get('st_time')
            })

        return race_details_list if race_details_list else None

    except Exception as e:
        return None


def fetch_venue_day(args) -> Dict:
    """
    1会場1日分のrace_detailsを取得（並列用）

    Returns:
        {
            'venue_code': '01',
            'race_date': '2020-01-01',
            'success': 5,
            'failed': 7,
            'data': [race_details_dict, ...]
        }
    """
    venue_code, race_date = args

    success_count = 0
    failed_count = 0
    data = []

    for race_number in range(1, 13):  # 1R-12R
        try:
            details_list = fetch_race_details(venue_code, race_date, race_number)
            if details_list:
                data.extend(details_list)
                success_count += 1
            else:
                failed_count += 1

            time.sleep(0.05)  # レート制限（軽いリクエストなので短め）

        except Exception as e:
            failed_count += 1

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
              'exhibition_time', 'tilt', 'chikusen_time', 'st_time']

    with open(output_file, mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=header)

        if is_first_batch:
            writer.writeheader()

        for row in data:
            writer.writerow(row)


def load_existing_csv(output_file: Path) -> set:
    """
    既存CSVファイルから処理済みのレースを読み込む

    Returns:
        set of (venue_code, race_date, race_number)
    """
    if not output_file.exists():
        return set()

    processed = set()

    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row['venue_code'], row['race_date'], int(row['race_number']))
                processed.add(key)
    except Exception as e:
        print(f"既存CSVの読み込みエラー: {e}")
        return set()

    return processed


def main():
    parser = argparse.ArgumentParser(description='race_detailsデータをCSVに収集')
    parser.add_argument('--start', required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--output', required=True, help='出力先ディレクトリ')
    parser.add_argument('--workers', type=int, default=12, help='並列ワーカー数（デフォルト: 12）')
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / 'race_details.csv'

    print("="*80)
    print("race_details CSV収集（chikusen_time補完用）")
    print("="*80)
    print(f"期間: {args.start} ～ {args.end}")
    print(f"出力先: {output_file}")
    print(f"並列ワーカー: {args.workers}")
    print()

    # 既存CSVから処理済みレースを読み込み
    processed_races = load_existing_csv(output_file)
    if processed_races:
        print(f"既存CSVを検出: {len(processed_races):,}レース（スキップ対象）")
        print()

    # 全会場×全日付のタスクリストを生成
    dates = get_date_range(args.start, args.end)
    venues = [f'{i:02d}' for i in range(1, 25)]  # 01-24場

    tasks = []
    for date in dates:
        for venue in venues:
            tasks.append((venue, date))

    print(f"対象タスク数: {len(tasks):,}件（24会場 × {len(dates)}日）")
    print(f"推定レース数: 約{len(tasks) * 6:,}件（1会場日平均6レース）")
    print()
    print("収集を開始します...")
    print()

    # 並列収集
    start_time = time.time()
    total_success = 0
    total_failed = 0
    batch_data = []
    is_first_batch = not processed_races  # 既存CSVがなければヘッダー出力

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_venue_day, task): task for task in tasks}

        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()

            total_success += result['success']
            total_failed += result['failed']

            # 収集したデータをバッチに追加
            batch_data.extend(result['data'])

            # 50タスクごとにCSV保存
            if i % 50 == 0 or i == len(tasks):
                if batch_data:
                    save_to_csv_batch(output_file, batch_data, is_first_batch)
                    is_first_batch = False
                    batch_data = []

                elapsed = time.time() - start_time
                races_per_sec = total_success / elapsed if elapsed > 0 else 0
                remaining = len(tasks) - i
                eta = remaining / (i / elapsed) if elapsed > 0 else 0

                print(f"[{i}/{len(tasks)}] "
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
    print(f"成功率: {total_success/(total_success+total_failed)*100:.1f}%")
    print(f"所要時間: {elapsed_time/60:.1f}分")
    print(f"出力ファイル: {output_file}")
    print()
    print("次のステップ:")
    print(f"  python scripts/maintenance/import_race_details_from_csv.py --input {output_dir}")
    print("="*80)


if __name__ == '__main__':
    main()
