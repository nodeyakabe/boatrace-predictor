# -*- coding: utf-8 -*-
"""単一の展示データ取得テスト"""
import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

import requests
from bs4 import BeautifulSoup
import threading

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

def fetch_exhibition_data(venue_code: str, race_date: str, race_number: int):
    """1レース分の展示データを取得（全艇分）"""
    session = get_session()
    date_str = race_date.replace('-', '')

    try:
        # 直前情報ページを取得
        url = "https://www.boatrace.jp/owpc/pc/race/beforeinfo"
        params = {
            "jcd": venue_code,
            "hd": date_str,
            "rno": race_number
        }

        print(f"リクエスト開始: {url}?jcd={venue_code}&hd={date_str}&rno={race_number}")
        response = session.get(url, params=params, timeout=15)
        print(f"レスポンス受信: {response.status_code}")
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # データ公開チェック
        error_msg = soup.find('p', class_='is-fs14')
        if error_msg and '情報はありません' in error_msg.get_text():
            print("データなし")
            return None

        # 展示タイムを取得
        exhibition_times = {}
        table = soup.find('table', class_='is-w748')
        if table:
            tbodies = table.find_all('tbody')
            print(f"tbody数: {len(tbodies)}")
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

        print(f"取得した展示タイム: {exhibition_times}")

        if not exhibition_times:
            return None

        # 全艇分のデータを作成
        data_list = []
        for pit_number in range(1, 7):
            data_list.append({
                'venue_code': venue_code,
                'race_date': race_date,
                'race_number': race_number,
                'pit_number': pit_number,
                'exhibition_time': exhibition_times.get(pit_number),
                'tilt': None,
                'st_time': None,
                'exhibition_course': None
            })

        return data_list

    except Exception as e:
        print(f"エラー: {type(e).__name__} - {e}")
        return None

print("="*80)
print("単一の展示データ取得テスト")
print("="*80)
print()

# 2020-01-27 桐生 1R（実在するレース）
result = fetch_exhibition_data('01', '2020-01-27', 1)

print()
print("結果:")
if result:
    for item in result:
        print(f"  枠{item['pit_number']}: {item['exhibition_time']}")
else:
    print("  データなし")
