"""
is_ladies / is_rookie バックフィルスクリプト

【問題の背景】
- race_scraper_v2.py が is_ladies を未実装だったため、全398,748レースが is_ladies=0
- is_rookie は race_grade='ルーキーシリーズ' から確実に推定可能（こちらは先に修正済み）

【このスクリプトのアプローチ】
1. 月次スケジュールページ（72ヶ月分）から女子戦イベントの開始日を取得
2. 開催期間（連続した日付）を races テーブルから推定
3. 対象レースの is_ladies を一括更新

【限界】
- スケジュールAPIが過去データ（特に2020-2022年）で不完全な場合、一部見落とす可能性あり
- その場合は Option B（venue-date ごとにレースページ1枚取得）で補完が必要

使い方:
  python scripts/data_collection/backfill_is_ladies.py --start-year 2020 --end-year 2025
  python scripts/data_collection/backfill_is_ladies.py --start-year 2020 --end-year 2025 --dry-run
"""

import os
import sys
import time
import argparse
import sqlite3
import re
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')

LADIES_PATTERNS = ['女子', 'レディース', 'LADIES', 'オールレディース', 'ヴィーナスシリーズ', 'クイーンズ', 'QUEEN']
SCHEDULE_URL = 'https://www.boatrace.jp/owpc/pc/race/monthlyschedule'
DELAY = 0.5


def fetch_monthly_schedule(year: int, month: int, session: requests.Session) -> Dict[str, List[Tuple[str, str]]]:
    """
    月次スケジュールページから (venue_code, start_date, event_title) を取得

    Returns:
        {venue_code: [(start_date_yyyymmdd, event_title), ...]}
    """
    params = {'ym': f'{year}{month:02d}'}
    try:
        resp = session.get(SCHEDULE_URL, params=params, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        result: Dict[str, List[Tuple[str, str]]] = {}

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if 'jcd=' not in href or 'hd=' not in href:
                continue
            jcd_m = re.search(r'jcd=(\d+)', href)
            hd_m = re.search(r'hd=(\d{8})', href)
            if not jcd_m or not hd_m:
                continue
            venue_code = jcd_m.group(1).zfill(2)
            start_date = hd_m.group(1)
            title = link.get_text(strip=True)

            if venue_code not in result:
                result[venue_code] = []
            result[venue_code].append((start_date, title))

        return result
    except Exception as e:
        print(f'  スケジュール取得エラー ({year}-{month:02d}): {e}')
        return {}


def is_ladies_event(title: str) -> bool:
    return any(p in title for p in LADIES_PATTERNS)


def find_event_dates_in_db(conn: sqlite3.Connection, venue_code: str, end_date_str: str) -> List[str]:
    """
    DBから venue の end_date（スケジュールのhd=最終日）に対応するイベント全日程を取得

    スケジュールページの hd は最終日。最終日から最大7日前の連続日程を取得する。
    """
    end_dt = datetime.strptime(end_date_str, '%Y%m%d')
    # 最大7日前から最終日まで候補を生成
    candidate_dates = []
    for i in range(7, -1, -1):  # 7日前〜0日前（最終日）
        d = end_dt - timedelta(days=i)
        candidate_dates.append(d.strftime('%Y-%m-%d'))

    cur = conn.cursor()
    placeholders = ','.join(['?'] * len(candidate_dates))
    cur.execute(
        f'SELECT DISTINCT race_date FROM races WHERE venue_code=? AND race_date IN ({placeholders}) ORDER BY race_date',
        [venue_code] + candidate_dates
    )
    found = [row[0] for row in cur.fetchall()]

    if not found:
        return []

    # 最終日から遡って連続する日付を取得（後ろから前に連続チェック）
    result = []
    for i in range(len(found) - 1, -1, -1):
        if not result:
            result.insert(0, found[i])
        else:
            curr_dt = datetime.strptime(found[i], '%Y-%m-%d')
            next_dt = datetime.strptime(result[0], '%Y-%m-%d')
            if (next_dt - curr_dt).days == 1:
                result.insert(0, found[i])
            else:
                break  # ギャップがあれば別イベント（前方打ち切り）
    return result


def update_is_ladies(conn: sqlite3.Connection, venue_code: str, race_dates: List[str], dry_run: bool) -> int:
    """指定 venue/dates の全レースを is_ladies=1 に更新"""
    if not race_dates:
        return 0
    cur = conn.cursor()
    placeholders = ','.join(['?'] * len(race_dates))
    cur.execute(
        f'SELECT COUNT(*) FROM races WHERE venue_code=? AND race_date IN ({placeholders}) AND is_ladies=0',
        [venue_code] + race_dates
    )
    count = cur.fetchone()[0]
    if count > 0 and not dry_run:
        cur.execute(
            f'UPDATE races SET is_ladies=1 WHERE venue_code=? AND race_date IN ({placeholders})',
            [venue_code] + race_dates
        )
        conn.commit()
    return count


def main():
    parser = argparse.ArgumentParser(description='is_ladies バックフィル')
    parser.add_argument('--start-year', type=int, default=2020)
    parser.add_argument('--end-year', type=int, default=2025)
    parser.add_argument('--dry-run', action='store_true', help='DBを変更せず件数のみ表示')
    args = parser.parse_args()

    mode = '[DRY-RUN]' if args.dry_run else '[本番]'
    print(f'{mode} is_ladies バックフィル開始: {args.start_year}-{args.end_year}年')

    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

    conn = sqlite3.connect(DB_PATH)

    total_events = 0
    total_updated = 0
    ladies_events_found = []

    for year in range(args.start_year, args.end_year + 1):
        for month in range(1, 13):
            if year == args.end_year and month > datetime.now().month:
                break

            print(f'  スケジュール取得: {year}-{month:02d}', end='', flush=True)
            schedule = fetch_monthly_schedule(year, month, session)
            time.sleep(DELAY)

            month_ladies = 0
            for venue_code, events in schedule.items():
                for start_date, title in events:
                    if not is_ladies_event(title):
                        continue

                    # 連続日程をDBから推定
                    race_dates = find_event_dates_in_db(conn, venue_code, start_date)
                    if not race_dates:
                        continue

                    updated = update_is_ladies(conn, venue_code, race_dates, args.dry_run)
                    if updated > 0:
                        ladies_events_found.append({
                            'venue': venue_code,
                            'start': start_date,
                            'dates': race_dates,
                            'title': title,
                            'races': updated
                        })
                        total_events += 1
                        total_updated += updated
                        month_ladies += 1

            print(f' → 女子戦イベント: {month_ladies}件', flush=True)

    conn.close()

    print(f'\n=== 完了 ===')
    print(f'女子戦イベント数: {total_events}件')
    print(f'更新レース数: {total_updated}件')
    if ladies_events_found:
        print('\n女子戦イベント一覧（最新20件）:')
        for ev in ladies_events_found[-20:]:
            print(f'  venue={ev["venue"]} {ev["start"]} ({len(ev["dates"])}日間) {ev["title"][:40]} → {ev["races"]}レース')


if __name__ == '__main__':
    main()
