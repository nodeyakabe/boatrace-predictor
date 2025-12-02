"""
未来のレース情報（出走表）を取得
リアルタイム予想用
"""
import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import sys
import io
from datetime import datetime, timedelta

# Windows環境でのUTF-8出力対応
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DATABASE_PATH = "data/boatrace.db"
BASE_URL = "https://www.boatrace.jp"

def get_upcoming_race_dates(days_ahead=7):
    """今日から指定日数先までの日付リストを取得"""
    dates = []
    for i in range(days_ahead):
        date = datetime.now() + timedelta(days=i)
        dates.append(date.strftime('%Y%m%d'))
    return dates

def fetch_race_schedule(date_str):
    """指定日のレース開催情報を取得"""
    url = f"{BASE_URL}/owpc/pc/race/index?hd={date_str}"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # 開催場を抽出（新しいHTML構造に対応）
        # jcd=パラメータを持つリンクから会場コードを抽出
        venues = set()

        # raceindex?jcd=XX のパターンを探す
        race_links = soup.find_all('a', href=True)
        for link in race_links:
            href = link.get('href', '')
            if 'raceindex?jcd=' in href and f'hd={date_str}' in href:
                # jcd=XX を抽出
                import re
                match = re.search(r'jcd=(\d+)', href)
                if match:
                    jcd = match.group(1).zfill(2)
                    venues.add(jcd)

        return sorted(list(venues))

    except Exception as e:
        print(f"  ⚠️ レース開催情報取得エラー ({date_str}): {e}")
        return []

def fetch_race_list(date_str, venue_code):
    """指定日・会場のレース一覧を取得"""
    url = f"{BASE_URL}/owpc/pc/race/racelist?rno=1&jcd={venue_code}&hd={date_str}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # レース番号を抽出（1R～12Rが基本）
        race_numbers = []
        for i in range(1, 13):
            # レースが存在するか確認
            race_link = soup.find('a', href=lambda x: x and f'rno={i}' in x)
            if race_link:
                race_numbers.append(i)

        return race_numbers

    except Exception as e:
        print(f"  ⚠️ レース一覧取得エラー ({venue_code}/{date_str}): {e}")
        return []

def fetch_race_beforeinfo(date_str, venue_code, race_number):
    """出走表情報を取得"""
    url = f"{BASE_URL}/owpc/pc/race/beforeinfo?rno={race_number}&jcd={venue_code}&hd={date_str}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # レース基本情報
        race_title = soup.select_one('.heading2_title')
        race_time = soup.select_one('.table1 .is-fs12')

        race_info = {
            'date': date_str,
            'venue_code': venue_code,
            'race_number': race_number,
            'title': race_title.text.strip() if race_title else '',
            'time': race_time.text.strip() if race_time else ''
        }

        # 出走表
        entries = []
        tbody = soup.select_one('.is-w495 tbody')

        if tbody:
            rows = tbody.select('tr')
            for row in rows:
                waku = row.select_one('.is-fs14')
                name_elem = row.select_one('.is-fs18')

                if waku and name_elem:
                    pit_number = waku.text.strip()
                    racer_name = name_elem.text.strip().replace('\n', '').replace(' ', '')

                    # 登録番号を取得
                    racer_link = name_elem.find('a')
                    racer_number = None
                    if racer_link and 'toban' in racer_link.get('href', ''):
                        racer_number = racer_link['href'].split('toban=')[1].split('&')[0]

                    entry = {
                        'pit_number': pit_number,
                        'racer_number': racer_number,
                        'racer_name': racer_name
                    }
                    entries.append(entry)

        return race_info, entries

    except Exception as e:
        print(f"  ⚠️ 出走表取得エラー ({venue_code}/{date_str}/R{race_number}): {e}")
        return None, []

def save_upcoming_race(conn, race_info, entries):
    """未来のレース情報をDBに保存"""
    cursor = conn.cursor()

    # 日付をYYYY-MM-DD形式に変換
    race_date = f"{race_info['date'][:4]}-{race_info['date'][4:6]}-{race_info['date'][6:]}"

    # レース情報を保存（既存の場合は更新）
    cursor.execute("""
        INSERT OR REPLACE INTO races
        (venue_code, race_date, race_number, race_time, race_title)
        VALUES (?, ?, ?, ?, ?)
    """, (
        race_info['venue_code'],
        race_date,
        race_info['race_number'],
        race_info['time'],
        race_info['title']
    ))

    race_id = cursor.lastrowid

    # 既存のrace_idを取得（INSERT OR REPLACEの場合）
    if race_id == 0:
        cursor.execute("""
            SELECT id FROM races
            WHERE venue_code = ? AND race_date = ? AND race_number = ?
        """, (race_info['venue_code'], race_date, race_info['race_number']))
        result = cursor.fetchone()
        if result:
            race_id = result[0]

    # 出走表を保存
    for entry in entries:
        if entry['racer_number']:
            cursor.execute("""
                INSERT OR REPLACE INTO entries
                (race_id, pit_number, racer_number, racer_name)
                VALUES (?, ?, ?, ?)
            """, (
                race_id,
                entry['pit_number'],
                entry['racer_number'],
                entry['racer_name']
            ))

    conn.commit()
    return race_id

def fetch_upcoming_races(days_ahead=3):
    """今日から指定日数先までのレース情報を取得"""
    print("=" * 80)
    print(f"未来のレース情報取得（今日から{days_ahead}日先まで）")
    print("=" * 80)
    print()

    conn = sqlite3.connect(DATABASE_PATH)

    dates = get_upcoming_race_dates(days_ahead)
    total_races = 0

    for date_str in dates:
        formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        print(f"📅 {formatted_date}")

        venues = fetch_race_schedule(date_str)

        if not venues:
            print(f"  ℹ️ 開催なし")
            print()
            continue

        print(f"  開催場: {', '.join(venues)}")

        for venue_code in venues:
            race_numbers = fetch_race_list(date_str, venue_code)

            if not race_numbers:
                continue

            for race_number in race_numbers:
                race_info, entries = fetch_race_beforeinfo(date_str, venue_code, race_number)

                if race_info and entries:
                    race_id = save_upcoming_race(conn, race_info, entries)
                    total_races += 1
                    print(f"  ✅ 場{venue_code} R{race_number:2d} {race_info['time']} ({len(entries)}艇)")

                time.sleep(0.5)  # レート制限対策

        print()

    conn.close()

    print("=" * 80)
    print(f"📊 取得完了: {total_races}レース")
    print("=" * 80)

if __name__ == "__main__":
    # デフォルトで今日から3日先まで取得
    import argparse
    parser = argparse.ArgumentParser(description='未来のレース情報を取得')
    parser.add_argument('--days', type=int, default=3, help='何日先まで取得するか（デフォルト: 3日）')
    args = parser.parse_args()

    fetch_upcoming_races(days_ahead=args.days)
