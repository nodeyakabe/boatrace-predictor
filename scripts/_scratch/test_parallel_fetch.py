# -*- coding: utf-8 -*-
"""並列展示データ取得テスト"""
import sys
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
from typing import List, Dict, Optional

ROOT_DIR = Path(__file__).parent
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

def fetch_exhibition_data(venue_code: str, race_date: str, race_number: int) -> Optional[List[Dict]]:
    """1レース分の展示データを取得"""
    session = get_session()
    date_str = race_date.replace('-', '')

    try:
        url = "https://www.boatrace.jp/owpc/pc/race/beforeinfo"
        params = {"jcd": venue_code, "hd": date_str, "rno": race_number}

        response = session.get(url, params=params, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        error_msg = soup.find('p', class_='is-fs14')
        if error_msg and '情報はありません' in error_msg.get_text():
            return None

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
                        pit_text = cols[0].get_text(strip=True)
                        try:
                            pit_number = int(pit_text)
                        except:
                            continue

                        time_text = cols[4].get_text(strip=True)
                        if time_text:
                            try:
                                time_value = float(time_text)
                                if 5.0 <= time_value <= 10.0:
                                    exhibition_times[pit_number] = time_value
                            except:
                                pass

        if not exhibition_times:
            return None

        data_list = []
        for pit_number in range(1, 7):
            data_list.append({
                'venue_code': venue_code,
                'race_date': race_date,
                'race_number': race_number,
                'pit_number': pit_number,
                'exhibition_time': exhibition_times.get(pit_number),
            })

        return data_list

    except:
        return None

def fetch_venue_day(args) -> Dict:
    """1会場1日分の展示データを取得"""
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

    return {
        'venue_code': venue_code,
        'race_date': race_date,
        'success': success_count,
        'failed': failed_count,
        'data': data
    }

print("="*80)
print("並列展示データ取得テスト")
print("="*80)
print()

# テスト用タスク（実在する開催）
tasks = [
    ('01', '2020-01-27'),  # 桐生
    ('20', '2020-01-27'),  # 若松
]

print(f"タスク数: {len(tasks)}")
print()

# 並列処理
print("ThreadPoolExecutor起動...")
sys.stdout.flush()

with ThreadPoolExecutor(max_workers=2) as executor:
    print("ThreadPoolExecutor起動成功")
    sys.stdout.flush()

    futures = {executor.submit(fetch_venue_day, task): task for task in tasks}
    print(f"タスク投入完了: {len(futures)}件")
    sys.stdout.flush()

    for i, future in enumerate(as_completed(futures), 1):
        print(f"[{i}/{len(tasks)}] 結果待機中...")
        sys.stdout.flush()

        result = future.result()
        print(f"[{i}/{len(tasks)}] 完了: {result['venue_code']} {result['race_date']} - 成功:{result['success']} 失敗:{result['failed']}")
        sys.stdout.flush()

print("\n完了")
