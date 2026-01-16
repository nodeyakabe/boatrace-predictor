"""決まり手データ補完 v3（タイムアウト対応版）"""
import os
import sqlite3
import requests
from bs4 import BeautifulSoup
import argparse
import time
import warnings
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# プロジェクトルート
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')

def get_kimarite(venue_code, race_date, race_number, retry=2):
    """決まり手を取得（リトライ付き）"""
    date_str = race_date.replace('-', '')
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_number}&jcd={int(venue_code):02d}&hd={date_str}"

    for attempt in range(retry):
        try:
            response = requests.get(url, timeout=30)  # 30秒タイムアウト
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'lxml')

            for table in soup.find_all('table'):
                thead = table.find('thead')
                if not thead:
                    continue

                headers = [th.get_text(strip=True) for th in thead.find_all('th')]

                if any('決まり手' in h for h in headers):
                    tbody = table.find('tbody')
                    if tbody:
                        td = tbody.find('td')
                        if td:
                            text = td.get_text(strip=True)
                            if text and len(text) > 0:
                                return text

        except requests.exceptions.Timeout:
            if attempt < retry - 1:
                time.sleep(5)  # タイムアウト後は5秒待機
                continue
            else:
                return None  # 最終試行でもタイムアウト

        except Exception:
            if attempt < retry - 1:
                time.sleep(2)
                continue
            else:
                return None

    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-date', required=True)
    parser.add_argument('--end-date', required=True)
    args = parser.parse_args()

    print("="*70)
    print("決まり手データ補完 v3（タイムアウト対応版）")
    print("="*70)
    print(f"期間: {args.start_date} ～ {args.end_date}")
    print(f"DB: {DB_PATH}")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("対象レース抽出中...")

    cursor.execute("""
        SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE res.kimarite IS NULL
          AND res.rank = '1'
          AND res.is_invalid = 0
          AND r.race_date BETWEEN ? AND ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, [args.start_date, args.end_date])

    races = cursor.fetchall()
    print(f"対象: {len(races)}件")

    if not races:
        print("補完対象なし")
        conn.close()
        return

    print("\\n処理開始...")
    print("-"*70)

    success = 0
    timeout_err = 0
    other_err = 0
    start_time = time.time()

    for i, (rid, vcode, rdate, rnum) in enumerate(races, 1):
        try:
            k = get_kimarite(vcode, rdate, rnum)
            if k:
                cursor.execute("UPDATE results SET kimarite = ? WHERE race_id = ? AND rank = '1'", (k, rid))
                conn.commit()
                success += 1
                status = f"OK: {k}"
            else:
                status = "TIMEOUT/ERROR"
                timeout_err += 1

            # 10件ごとに進捗表示
            if i % 10 == 0 or i == len(races):
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                remaining = (len(races) - i) / rate if rate > 0 else 0
                print(f"[{i}/{len(races)}] {status} ({success}成功, {timeout_err}失敗) - 残り約{remaining/60:.1f}分")
            elif success > 0 and success % 50 == 0:
                print(f"[{i}/{len(races)}] {status}")

        except Exception as e:
            other_err += 1
            if i % 10 == 0:
                print(f"[{i}/{len(races)}] ERROR: {type(e).__name__}")

    conn.close()

    elapsed_total = time.time() - start_time

    print()
    print("="*70)
    print("完了")
    print("="*70)
    print(f"対象レース: {len(races)}件")
    print(f"成功: {success}件 ({success/len(races)*100:.1f}%)")
    print(f"タイムアウト/失敗: {timeout_err}件")
    print(f"その他エラー: {other_err}件")
    print(f"処理時間: {elapsed_total/60:.1f}分")
    print(f"処理速度: {len(races)/elapsed_total:.2f}件/秒")
    print("="*70)

if __name__ == "__main__":
    main()
