"""決まり手データ補完 v2"""
import os
import sqlite3
import requests
from bs4 import BeautifulSoup
import argparse

# プロジェクトルート
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')

print("[INIT] Start")

def get_kimarite(venue_code, race_date, race_number):
    """決まり手を取得"""
    date_str = race_date.replace('-', '')
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_number}&jcd={int(venue_code):02d}&hd={date_str}"

    try:
        response = requests.get(url, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'lxml')

        for table in soup.find_all('table'):
            thead = table.find('thead')
            if not thead:
                continue

            headers = [th.get_text(strip=True) for th in thead.find_all('th')]

            # 決まり手ヘッダーを探す（日本語で）
            if any('決まり手' in h for h in headers):
                tbody = table.find('tbody')
                if tbody:
                    td = tbody.find('td')
                    if td:
                        text = td.get_text(strip=True)
                        if text and len(text) > 0:
                            return text
    except Exception as e:
        pass

    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-date', required=True)
    parser.add_argument('--end-date', required=True)
    args = parser.parse_args()

    print("="*60)
    print("Kimarite Fetch")
    print("="*60)
    print(f"DB: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Querying...")

    cursor.execute("""
        SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE res.kimarite IS NULL
          AND res.rank = '1'
          AND res.is_invalid = 0
          AND r.race_date BETWEEN ? AND ?
        LIMIT 100
    """, [args.start_date, args.end_date])

    races = cursor.fetchall()
    print(f"Found: {len(races)} races")

    if not races:
        print("No data")
        return

    success = 0
    for i, (rid, vcode, rdate, rnum) in enumerate(races, 1):
        k = get_kimarite(vcode, rdate, rnum)
        if k:
            cursor.execute("UPDATE results SET kimarite = ? WHERE race_id = ? AND rank = '1'", (k, rid))
            conn.commit()
            success += 1
            print(f"[{i}/{len(races)}] OK: {k}")
        else:
            print(f"[{i}/{len(races)}] FAIL")

    conn.close()
    print(f"\\nDone: {success}/{len(races)}")

if __name__ == "__main__":
    main()
