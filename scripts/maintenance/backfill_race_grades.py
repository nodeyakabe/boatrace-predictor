# -*- coding: utf-8 -*-
"""
既存 races テーブルへ race_grade / is_ladies / is_rookie を一括補完

アプローチ:
  月間スケジュールページ（monthlyschedule）を年月単位で取得し、
  SG/G1/G2/G3/Venus/Rookie/Lady の開催情報を (venue_code, date) → grade に変換。
  各レースの個別ページにはアクセスしない（月96リクエストで完了）。

実行例:
    # ドライラン（件数確認のみ）
    python scripts/maintenance/backfill_race_grades.py --dry-run

    # 2018-2025年を全補完（デフォルト）
    python scripts/maintenance/backfill_race_grades.py

    # 特定年のみ
    python scripts/maintenance/backfill_race_grades.py --start-year 2024 --end-year 2025
"""
import sys
import io
import sqlite3
import argparse
import time
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / 'data' / 'boatrace.db'


def fmt_date(date_str: str) -> str:
    """YYYYMMDD → YYYY-MM-DD"""
    s = str(date_str).strip()
    if len(s) == 8 and '-' not in s:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def backfill_month(conn: sqlite3.Connection, scraper, year: int, month: int,
                   dry_run: bool) -> dict:
    """1か月分を補完"""
    grade_map = scraper.get_monthly_schedule_with_grades(year, month)

    if not grade_map:
        return {'skipped': 0, 'updated': 0}

    cur = conn.cursor()
    updated = 0
    skipped = 0

    for (venue_code, date_yyyymmdd), (grade, is_ladies, is_rookie) in grade_map.items():
        date_iso = fmt_date(date_yyyymmdd)

        # 対象レースが DB に存在するか確認
        cur.execute("""
            SELECT COUNT(*) FROM races
            WHERE venue_code = ? AND race_date = ?
        """, (venue_code, date_iso))
        count = cur.fetchone()[0]

        if count == 0:
            skipped += 1
            continue

        if dry_run:
            updated += count
            continue

        cur.execute("""
            UPDATE races
            SET race_grade = ?,
                is_ladies  = ?,
                is_rookie  = ?
            WHERE venue_code = ? AND race_date = ?
        """, (grade, is_ladies, is_rookie, venue_code, date_iso))
        updated += cur.rowcount

    if not dry_run:
        conn.commit()

    return {'skipped': skipped, 'updated': updated}


def main():
    parser = argparse.ArgumentParser(description='race_grade / is_ladies / is_rookie 一括補完')
    parser.add_argument('--start-year', type=int, default=2018, help='開始年（デフォルト: 2018）')
    parser.add_argument('--end-year',   type=int, default=2026, help='終了年（デフォルト: 2026）')
    parser.add_argument('--dry-run', action='store_true', help='確認のみ（DBを変更しない）')
    parser.add_argument('--delay', type=float, default=1.0, help='リクエスト間隔（秒）')
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f'[ERROR] DBが見つかりません: {DB_PATH}')
        sys.exit(1)

    from src.scraper.schedule_scraper import ScheduleScraper
    scraper = ScheduleScraper(delay=args.delay)

    mode = '[DRY RUN]' if args.dry_run else '[実行]'
    now_year  = datetime.now().year
    now_month = datetime.now().month

    print(f'=== race_grade 一括補完 {mode} ===')
    print(f'対象期間: {args.start_year}年 〜 {args.end_year}年')
    print(f'DB: {DB_PATH}')
    print()

    conn = sqlite3.connect(str(DB_PATH))
    total_updated = 0
    total_skipped = 0

    try:
        for year in range(args.start_year, args.end_year + 1):
            for month in range(1, 13):
                # 未来月はスキップ
                if year > now_year or (year == now_year and month > now_month):
                    break

                print(f'  {year}年{month:02d}月 ... ', end='', flush=True)
                result = backfill_month(conn, scraper, year, month, args.dry_run)
                print(f"更新={result['updated']}件 / DB不存在スキップ={result['skipped']}件")
                total_updated += result['updated']
                total_skipped += result['skipped']

                time.sleep(args.delay)

    finally:
        conn.close()
        scraper.close()

    print()
    print(f'=== 完了 ===')
    print(f'総更新件数: {total_updated}件')
    print(f'DBスキップ: {total_skipped}件（スケジュール上にあるがDBに未収録）')
    if args.dry_run:
        print('（DRY RUNのため実際には変更なし）')

    # 補完後の集計を表示
    if not args.dry_run:
        conn2 = sqlite3.connect(str(DB_PATH))
        cur2 = conn2.cursor()
        print()
        print('=== 補完後のrace_grade分布 ===')
        cur2.execute("SELECT race_grade, COUNT(*) FROM races GROUP BY race_grade ORDER BY COUNT(*) DESC")
        for row in cur2.fetchall():
            print(f'  {row[0]}: {row[1]}件')
        print()
        print('=== is_ladies / is_rookie ===')
        cur2.execute("SELECT is_ladies, is_rookie, COUNT(*) FROM races GROUP BY is_ladies, is_rookie")
        for row in cur2.fetchall():
            print(f'  is_ladies={row[0]}, is_rookie={row[1]}: {row[2]}件')
        conn2.close()


if __name__ == '__main__':
    main()
