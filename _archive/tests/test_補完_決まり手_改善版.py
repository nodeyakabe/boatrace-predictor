"""決まり手補完改善版のテスト（10レースのみ）"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
import requests
from bs4 import BeautifulSoup
import threading

# セッションプール
thread_local = threading.local()

def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
        thread_local.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    return thread_local.session

def get_test_races():
    """テスト用に10件のレースを取得"""
    conn = sqlite3.connect("data/boatrace.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT
            r.id,
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE res.kimarite IS NULL
          AND res.rank = '1'
          AND res.is_invalid = 0
        ORDER BY r.race_date DESC, r.venue_code, r.race_number
        LIMIT 10
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def fetch_kimarite(args):
    race_id, venue_code, race_date, race_number = args
    date_str = race_date.replace('-', '')
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_number}&jcd={int(venue_code):02d}&hd={date_str}"

    try:
        session = get_session()
        response = session.get(url, timeout=10)
        response.raise_for_status()
        response.encoding = response.apparent_encoding

        soup = BeautifulSoup(response.text, 'lxml')

        # 決まり手テーブルを探す
        kimarite = None
        tables = soup.find_all('table')

        for table in tables:
            thead = table.find('thead')
            if not thead:
                continue

            headers = [th.get_text(strip=True) for th in thead.find_all('th')]

            if '決まり手' in headers:
                tbody = table.find('tbody')
                if tbody:
                    td = tbody.find('td')
                    if td:
                        kimarite_text = td.get_text(strip=True)
                        if kimarite_text and kimarite_text not in ['', ' ']:
                            kimarite = kimarite_text
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
            return None

    except Exception as e:
        print(f"エラー: {venue_code} {race_date} R{race_number} - {e}")
        return None

print("=" * 80)
print("決まり手補完改善版テスト（10レース）")
print("=" * 80)

races = get_test_races()
print(f"\nテスト対象: {len(races)}件\n")

success = 0
failure = 0

for i, race in enumerate(races, 1):
    result = fetch_kimarite(race)
    if result:
        success += 1
        print(f"[{i}/{len(races)}] ✓ {int(result['venue_code']):02d} {result['race_date']} R{result['race_number']:2d} - {result['kimarite']}")
    else:
        failure += 1
        print(f"[{i}/{len(races)}] ✗ {int(race[1]):02d} {race[2]} R{race[3]:2d} - 取得失敗")

print("\n" + "=" * 80)
print(f"成功: {success}件, 失敗: {failure}件")
print("=" * 80)
