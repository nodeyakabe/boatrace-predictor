# -*- coding: utf-8 -*-
"""
race_grade / is_ladies / is_rookie 完全バックフィル（gradesch ページ版）

gradesch?year=XXXX&hcd=XX を使うことで、各グレードの全イベント（開催期間全日）
を確実に取得できる。monthlyschedule 方式と異なり、単月SGイベントも全日分補完される。

対象 hcd:
  01: SG / PG1（G1）
  02: G1 / G2
  03: G3 / オールレディース
  04: ヴィーナスシリーズ
  05: ルーキーシリーズ
  （06: マスターズリーグ は DB スキーマに存在しないためスキップ）

必要リクエスト数: 9年 × 5hcd = 45リクエスト（約1分）

使い方:
    python scripts/maintenance/backfill_race_grades_v2.py
    python scripts/maintenance/backfill_race_grades_v2.py --start-year 2024 --end-year 2026
    python scripts/maintenance/backfill_race_grades_v2.py --dry-run
"""
import sys
import io
import re
import time
import sqlite3
import argparse
import requests
from pathlib import Path
from datetime import date, timedelta
from bs4 import BeautifulSoup

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'boatrace.db'

BASE_URL = 'https://www.boatrace.jp/owpc/pc/race/gradesch'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}


def classify_grade(classes: list[str]) -> tuple | None:
    """
    CSSクラスリストからグレード情報を返す。
    Returns (race_grade, is_ladies, is_rookie) or None
    """
    has = set(classes)
    if 'is-SGa' in has:
        return ('SG', 0, 0)
    if 'is-G1a' in has:
        return ('G1', 0, 0)
    if 'is-G1b' in has:
        return ('G1', 0, 0)
    if 'is-G2b' in has:
        return ('G2', 0, 0)
    if 'is-G3b' in has:
        if 'is-lady' in has:
            return ('オールレディース', 1, 0)
        return ('G3', 0, 0)
    if 'is-venus' in has:
        return ('ヴィーナスシリーズ', 1, 0)
    if any(c.startswith('is-rookie') for c in has):
        return ('ルーキーシリーズ', 0, 1)
    return None


def parse_date_range(date_text: str, year: int) -> tuple[date, date] | None:
    """
    "03/25-03/30" → (date(year, 3, 25), date(year, 3, 30))
    年をまたぐ場合（例: "12/27-01/01"）は終了日を翌年として処理する。
    """
    m = re.match(r'(\d{2}/\d{2})-(\d{2}/\d{2})', date_text.strip())
    if not m:
        return None
    sm, sd = map(int, m.group(1).split('/'))
    em, ed = map(int, m.group(2).split('/'))
    start = date(year, sm, sd)
    end_year = year + 1 if em < sm else year
    end = date(end_year, em, ed)
    return start, end


def fetch_gradesch(year: int, hcd: int, delay: float = 1.0, max_retries: int = 3) -> list[dict]:
    """
    gradesch ページを取得してイベント一覧を返す。
    Returns list of {start_date, end_date, venue_code, grade, is_ladies, is_rookie}
    """
    url = BASE_URL
    params = {'year': year, 'hcd': f'{hcd:02d}'}

    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            break
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f'  ❌ fetch error year={year} hcd={hcd}: {e}')
                return []

    soup = BeautifulSoup(r.text, 'html.parser')
    events = []

    for tbody in soup.find_all('tbody'):
        # 1つのtbodyに複数trがある場合（例: 8月にレディースチャンピオン+ボートレースメモリアル）を
        # すべて処理する。月セル（is-fs14）はrowspanで最初の行にのみ存在する。
        for tr in tbody.find_all('tr'):
            tds = tr.find_all('td')

            # 日付
            date_td = tr.find('td', class_='td_date')
            if not date_td:
                continue
            date_range = parse_date_range(date_td.get_text(strip=True), year)
            if not date_range:
                continue
            start_dt, end_dt = date_range

            # 会場コード（imgのsrcから）
            img = tr.find('img', src=re.compile(r'text_place1_'))
            if not img:
                continue
            vm = re.search(r'text_place1_(\d+)', img['src'])
            if not vm:
                continue
            venue_code = vm.group(1).zfill(2)

            # グレード（全tdのCSSクラスを収集）
            all_classes = []
            for td in tds:
                all_classes.extend(td.get('class') or [])
            grade_info = classify_grade(all_classes)
            if not grade_info:
                continue

            events.append({
                'start_date': start_dt,
                'end_date':   end_dt,
                'venue_code': venue_code,
                'grade':      grade_info[0],
                'is_ladies':  grade_info[1],
                'is_rookie':  grade_info[2],
            })

    time.sleep(delay)
    return events


def apply_events(conn: sqlite3.Connection, events: list[dict], dry_run: bool) -> dict:
    """DB に対してイベントの全日程を UPDATE する"""
    cur = conn.cursor()
    updated = 0
    checked = 0

    for ev in events:
        d = ev['start_date']
        while d <= ev['end_date']:
            date_iso = d.isoformat()
            cur.execute(
                'SELECT COUNT(*) FROM races WHERE venue_code=? AND race_date=?',
                (ev['venue_code'], date_iso)
            )
            cnt = cur.fetchone()[0]
            checked += 1

            if cnt > 0 and not dry_run:
                cur.execute(
                    'UPDATE races SET race_grade=?, is_ladies=?, is_rookie=? WHERE venue_code=? AND race_date=?',
                    (ev['grade'], ev['is_ladies'], ev['is_rookie'], ev['venue_code'], date_iso)
                )
                updated += cur.rowcount
            elif cnt > 0:
                updated += cnt  # dry-run では件数のみ

            d += timedelta(days=1)

    if not dry_run:
        conn.commit()

    return {'updated': updated, 'checked': checked}


def main():
    parser = argparse.ArgumentParser(description='race_grade 完全バックフィル（gradesch 版）')
    parser.add_argument('--start-year', type=int, default=2018)
    parser.add_argument('--end-year',   type=int, default=2026)
    parser.add_argument('--dry-run',    action='store_true')
    parser.add_argument('--delay',      type=float, default=1.0)
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f'[ERROR] DB が見つかりません: {DB_PATH}')
        sys.exit(1)

    HCD_LIST = [1, 2, 3, 4, 5]  # 6=マスターズリーグ はスキップ
    HCD_NAME = {1: 'SG/PG1', 2: 'G1/G2', 3: 'G3/レディース', 4: 'ヴィーナス', 5: 'ルーキー'}

    mode = '[DRY RUN]' if args.dry_run else '[実行]'
    print(f'=== race_grade 完全バックフィル（gradesch版）{mode} ===')
    print(f'対象期間: {args.start_year}〜{args.end_year}年  delay={args.delay}s')
    print()

    conn = sqlite3.connect(str(DB_PATH))
    total_updated = 0
    total_events  = 0

    try:
        for year in range(args.start_year, args.end_year + 1):
            print(f'--- {year}年 ---')
            for hcd in HCD_LIST:
                print(f'  hcd={hcd:02d} ({HCD_NAME[hcd]}) ... ', end='', flush=True)
                events = fetch_gradesch(year, hcd, delay=args.delay)

                if not events:
                    print('0件')
                    continue

                result = apply_events(conn, events, args.dry_run)
                print(f'{len(events)}イベント  レース更新={result["updated"]}件')
                total_events  += len(events)
                total_updated += result['updated']

    finally:
        conn.close()

    print()
    print(f'=== 完了 ===')
    print(f'総イベント数: {total_events}')
    print(f'総更新レース: {total_updated}件')
    if args.dry_run:
        print('（DRY RUN のため実際には変更なし）')
        return

    # 補完後の分布確認
    conn2 = sqlite3.connect(str(DB_PATH))
    cur2 = conn2.cursor()
    print()
    print('=== 補完後の race_grade 分布 ===')
    cur2.execute("SELECT race_grade, COUNT(*) FROM races GROUP BY race_grade ORDER BY COUNT(*) DESC")
    for row in cur2.fetchall():
        print(f'  {row[0] or "NULL"}: {row[1]}件')
    conn2.close()


if __name__ == '__main__':
    main()
