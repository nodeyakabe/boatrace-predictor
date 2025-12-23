"""
高速版オッズ取得スクリプト

最適化内容:
- 並列処理（ThreadPoolExecutor）
- 最小限の遅延
- バッチDB書き込み
- リトライを1回に削減
"""
import os
import sys
import sqlite3
import argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
import warnings

warnings.filterwarnings('ignore')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import requests
from bs4 import BeautifulSoup


class FastOddsScraper:
    """高速オッズ取得（並列処理対応）"""

    def __init__(self, delay: float = 0.2):
        self.base_url = "https://www.boatrace.jp/owpc/pc/race/odds3t"
        self.delay = delay
        self.local = threading.local()

    def _get_session(self):
        """スレッドローカルセッション"""
        if not hasattr(self.local, 'session'):
            self.local.session = requests.Session()
            self.local.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                'Accept': 'text/html',
            })
        return self.local.session

    def get_trifecta_odds(self, venue_code, race_date, race_number):
        """3連単オッズを取得"""
        params = {
            'rno': race_number,
            'jcd': venue_code.zfill(2),
            'hd': race_date.replace('-', '')
        }

        try:
            time.sleep(self.delay)
            session = self._get_session()
            response = session.get(self.base_url, params=params, timeout=30)

            if response.status_code != 200:
                return None

            response.encoding = 'utf-8'
            return self._parse_odds(response.text)

        except Exception:
            return None

    def _parse_odds(self, html):
        """高速パース"""
        soup = BeautifulSoup(html, 'lxml')
        odds_data = {}

        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            if len(rows) < 20:
                continue

            second_boats = [2, 3, 4, 5, 6]
            row_idx = 1

            for second_boat in second_boats:
                for sub_row in range(4):
                    if row_idx >= len(rows):
                        break

                    row = rows[row_idx]
                    cells = row.find_all('td')
                    row_idx += 1

                    if len(cells) >= 18:
                        for first_boat in range(1, 7):
                            base_idx = (first_boat - 1) * 3
                            try:
                                cell_second = int(cells[base_idx].text.strip())
                                third_boat = int(cells[base_idx + 1].text.strip())
                                odds_text = cells[base_idx + 2].text.strip().replace(',', '')
                                if odds_text and odds_text != '-':
                                    odds_value = float(odds_text)
                                    if 1.0 <= odds_value <= 99999.0:
                                        if len(set([first_boat, cell_second, third_boat])) == 3:
                                            odds_data[f"{first_boat}-{cell_second}-{third_boat}"] = odds_value
                            except (ValueError, IndexError):
                                continue

                    elif len(cells) >= 12:
                        for first_boat in range(1, 7):
                            if first_boat == second_boat:
                                continue
                            base_idx = (first_boat - 1) * 2
                            try:
                                third_boat = int(cells[base_idx].text.strip())
                                odds_text = cells[base_idx + 1].text.strip().replace(',', '')
                                if odds_text and odds_text != '-':
                                    odds_value = float(odds_text)
                                    if 1.0 <= odds_value <= 99999.0:
                                        if len(set([first_boat, second_boat, third_boat])) == 3:
                                            odds_data[f"{first_boat}-{second_boat}-{third_boat}"] = odds_value
                            except (ValueError, IndexError):
                                continue

            if len(odds_data) >= 60:
                break

        return odds_data if odds_data else None


def get_races_to_fetch(db_path, start_date, end_date):
    """未取得レースを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date BETWEEN ? AND ?
          AND NOT EXISTS (
              SELECT 1 FROM trifecta_odds t WHERE t.race_id = r.id
          )
        ORDER BY r.race_date, r.venue_code, r.race_number
    """
    cursor.execute(query, (start_date, end_date))
    races = cursor.fetchall()
    conn.close()
    return races


def process_race(race_info, scraper):
    """1レース処理"""
    race_id, venue_code, race_date, race_number = race_info
    date_str = race_date.replace('-', '')
    odds = scraper.get_trifecta_odds(venue_code, date_str, race_number)

    if odds:
        return (race_id, odds)
    return None


def save_batch_to_db(db_path, batch_data):
    """バッチ保存"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for race_id, odds_data in batch_data:
        for combination, odds_value in odds_data.items():
            cursor.execute("""
                INSERT OR REPLACE INTO trifecta_odds (race_id, combination, odds, fetched_at)
                VALUES (?, ?, ?, datetime('now'))
            """, (race_id, combination, odds_value))

    conn.commit()
    conn.close()
    return len(batch_data)


def main():
    parser = argparse.ArgumentParser(description='高速オッズ取得')
    parser.add_argument('--db', default='data/boatrace.db')
    parser.add_argument('--start-date', default='2025-01-01')
    parser.add_argument('--end-date', default='2025-10-31')
    parser.add_argument('--workers', type=int, default=20)
    parser.add_argument('--delay', type=float, default=0.1)
    parser.add_argument('--batch-size', type=int, default=50)

    args = parser.parse_args()

    db_path = os.path.join(PROJECT_ROOT, args.db)
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}")
        return

    print("=" * 60)
    print("高速オッズ取得（並列処理版）")
    print(f"期間: {args.start_date} ～ {args.end_date}")
    print(f"並列数: {args.workers}, 遅延: {args.delay}秒")
    print("=" * 60)

    races = get_races_to_fetch(db_path, args.start_date, args.end_date)
    total = len(races)
    print(f"対象レース数: {total}")

    if total == 0:
        print("取得対象なし")
        return

    scraper = FastOddsScraper(delay=args.delay)

    success_count = 0
    error_count = 0
    batch_data = []

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_race, race, scraper): race for race in races}

        for i, future in enumerate(as_completed(futures)):
            result = future.result()

            if result:
                batch_data.append(result)
                success_count += 1

                # バッチ保存
                if len(batch_data) >= args.batch_size:
                    save_batch_to_db(db_path, batch_data)
                    batch_data = []
            else:
                error_count += 1

            # 進捗表示
            if (i + 1) % 100 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                remaining = (total - i - 1) / rate if rate > 0 else 0
                print(f"進捗: {i + 1}/{total} ({(i+1)/total*100:.1f}%) "
                      f"- 成功: {success_count}, エラー: {error_count} "
                      f"- 速度: {rate:.1f}件/秒 - 残り: {remaining/60:.1f}分")

    # 残りを保存
    if batch_data:
        save_batch_to_db(db_path, batch_data)

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("完了")
    print(f"  成功: {success_count}レース")
    print(f"  エラー: {error_count}レース")
    print(f"  処理時間: {elapsed/60:.1f}分")
    print(f"  平均速度: {total/elapsed:.2f}件/秒")
    print("=" * 60)


if __name__ == '__main__':
    main()
