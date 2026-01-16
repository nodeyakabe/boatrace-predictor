"""
決まり手データ補完（シンプル版・デバッグ付き）
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import sqlite3
import requests
from bs4 import BeautifulSoup
import argparse

# プロジェクトルートを取得
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')

print("[INIT] スクリプト初期化完了")

def get_kimarite(venue_code, race_date, race_number):
    """決まり手を取得"""
    date_str = race_date.replace('-', '')
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_number}&jcd={int(venue_code):02d}&hd={date_str}"

    try:
        response = requests.get(url, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'lxml')

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
                        kimarite = td.get_text(strip=True)
                        if kimarite and kimarite not in ['', ' ']:
                            return kimarite

    except Exception as e:
        pass

    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-date', type=str, help='開始日')
    parser.add_argument('--end-date', type=str, help='終了日')
    args = parser.parse_args()

    print("="*80)
    print("決まり手データ補完（シンプル版）")
    print("="*80)

    print(f"[DEBUG] DB接続: {DB_PATH}")

    # DBからレース取得
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"[DEBUG] クエリ実行中...")

    query = """
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
          AND r.race_date BETWEEN ? AND ?
        ORDER BY r.race_date DESC, r.venue_code, r.race_number
    """

    cursor.execute(query, [args.start_date, args.end_date])
    races = cursor.fetchall()

    print(f"[DEBUG] クエリ完了: {len(races)}件")

    if len(races) == 0:
        print("補完対象なし")
        conn.close()
        return

    print(f"\\n補完対象: {len(races)}件")
    print("処理開始...")

    success = 0
    error = 0

    for i, (race_id, venue_code, race_date, race_number) in enumerate(races, 1):
        kimarite = get_kimarite(venue_code, race_date, race_number)

        if kimarite:
            cursor.execute("""
                UPDATE results
                SET kimarite = ?
                WHERE race_id = ? AND rank = '1'
            """, (kimarite, race_id))
            conn.commit()
            success += 1
        else:
            error += 1

        if i % 10 == 0:
            print(f"進捗: {i}/{len(races)} ({i/len(races)*100:.1f}%)")

    conn.close()

    print("\\n" + "="*80)
    print("完了")
    print("="*80)
    print(f"成功: {success}件")
    print(f"失敗: {error}件")
    print("="*80)

if __name__ == "__main__":
    print("[MAIN] main()開始")
    main()
    print("[MAIN] main()終了")
