"""
is_ladies バックフィル v2（CSSクラス法）

旧版（backfill_is_ladies.py）はタイトルテキスト文字列マッチングで全件誤検知が発生したため廃止。
本スクリプトは月次スケジュールページのCSSクラスを使って女子戦を確実に検出する。

検出ロジック:
  is-gradeColorVenus → ヴィーナスシリーズ (is_ladies=1)
  is-gradeColorLady  → オールレディース  (is_ladies=1)
  ScheduleScraper.get_monthly_schedule_with_grades() を使用（既存実装を流用）

副産物:
  --update-gender を指定すると、女子戦に出場した選手の racers.gender='female' も更新する。
  （529名の欠損選手については fetch_racer_profiles.py で補完すること）

使い方:
  python scripts/data_collection/backfill_is_ladies_v2.py
  python scripts/data_collection/backfill_is_ladies_v2.py --dry-run
  python scripts/data_collection/backfill_is_ladies_v2.py --update-gender
  python scripts/data_collection/backfill_is_ladies_v2.py --start-year 2020 --end-year 2025
"""

import os
import sys
import sqlite3
import argparse
import time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')

from src.scraper.schedule_scraper import ScheduleScraper
from config.settings import GENDER_LADIES_THRESHOLD


def collect_ladies_venue_dates(start_year: int, end_year: int) -> set:
    """
    月次スケジュールのCSSクラスから女子戦の (venue_code, race_date) を収集。

    Returns:
        set of (venue_code: str, race_date: str YYYY-MM-DD)
    """
    scraper = ScheduleScraper(delay=0.5)
    ladies_venue_dates = set()

    current_year = datetime.now().year
    current_month = datetime.now().month

    total_months = 0
    total_ladies = 0

    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            if year == current_year and month > current_month:
                break
            if year == end_year + 1:
                break

            print(f'  スケジュール取得: {year}-{month:02d}', end='', flush=True)
            schedule = scraper.get_monthly_schedule_with_grades(year, month)
            time.sleep(0.3)  # 追加待機

            ladies_count = 0
            for (venue_code, date_str), (grade, is_ladies, is_rookie) in schedule.items():
                if is_ladies:
                    # date_str は YYYYMMDD → YYYY-MM-DD
                    date_formatted = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}'
                    ladies_venue_dates.add((venue_code, date_formatted))
                    ladies_count += 1

            total_months += 1
            total_ladies += ladies_count
            print(f' → 女子戦日程: {ladies_count}件 (累計{len(ladies_venue_dates)}件)', flush=True)

    scraper.close()
    print(f'\nスケジュール取得完了: {total_months}ヶ月 / 女子戦日程: {len(ladies_venue_dates)}件 (venue×date)')
    return ladies_venue_dates


def update_is_ladies(conn: sqlite3.Connection, ladies_venue_dates: set, dry_run: bool) -> tuple:
    """
    races.is_ladies を更新する。

    Returns:
        (updated_count, already_count)
    """
    total_updated = 0
    total_already = 0

    for venue_code, race_date in sorted(ladies_venue_dates):
        already = conn.execute(
            'SELECT COUNT(*) FROM races WHERE venue_code=? AND race_date=? AND is_ladies=1',
            (venue_code, race_date)
        ).fetchone()[0]
        total_already += already

        to_update = conn.execute(
            'SELECT COUNT(*) FROM races WHERE venue_code=? AND race_date=? AND is_ladies=0',
            (venue_code, race_date)
        ).fetchone()[0]

        if to_update > 0 and not dry_run:
            conn.execute(
                'UPDATE races SET is_ladies=1 WHERE venue_code=? AND race_date=? AND is_ladies=0',
                (venue_code, race_date)
            )
        total_updated += to_update

    if not dry_run:
        conn.commit()

    return total_updated, total_already


GENDER_THRESHOLD = GENDER_LADIES_THRESHOLD  # config/settings.py で一元管理

def update_gender_from_ladies_races(conn: sqlite3.Connection, dry_run: bool) -> int:
    """
    races.is_ladies=1 のレースに {GENDER_THRESHOLD} 回以上出場した選手を female に更新。

    閾値を設ける理由:
      - entries テーブルに誤ったracer_number が混入しているケースがある（峰竜太26件等）
      - 50回以上出場 → 本物の女性選手と判断できる
      - 50回未満の少数出場 → データエラーの可能性が高い

    Returns:
        更新件数
    """
    # Step1: 全女性ラベルをリセット
    now_str = datetime.now().isoformat()
    if not dry_run:
        conn.execute("UPDATE racers SET gender='male', updated_at=? WHERE gender='female'", (now_str,))

    # Step2: 閾値以上出場の選手を female に設定
    rows = conn.execute(f"""
        SELECT e.racer_number, COUNT(*) as cnt
        FROM entries e
        JOIN races r ON e.race_id = r.id
        WHERE r.is_ladies = 1
        GROUP BY e.racer_number
        HAVING cnt >= {GENDER_THRESHOLD}
    """).fetchall()
    female_numbers = [row[0] for row in rows]

    print(f'女子戦 {GENDER_THRESHOLD}回以上出場: {len(female_numbers)}人')

    if not female_numbers or dry_run:
        return len(female_numbers)

    updated = 0
    for num in female_numbers:
        result = conn.execute(
            "UPDATE racers SET gender='female', updated_at=? WHERE racer_number=? AND gender != 'female'",
            (now_str, num)
        )
        updated += result.rowcount

    conn.commit()
    return updated


def main():
    parser = argparse.ArgumentParser(description='is_ladies バックフィル v2（CSSクラス法）')
    parser.add_argument('--start-year', type=int, default=2020)
    parser.add_argument('--end-year', type=int, default=2025)
    parser.add_argument('--dry-run', action='store_true', help='DBを変更せず件数のみ表示')
    parser.add_argument('--update-gender', action='store_true',
                        help='女子戦出場選手の racers.gender=female も更新する'
                             '（閾値ベースのみ・ladies_master.csv 非参照。'
                             '正確な gender 更新は import_racers_csv.py を使うこと）')
    args = parser.parse_args()

    mode = '[DRY-RUN]' if args.dry_run else '[本番]'
    print(f'{mode} is_ladies バックフィル v2 開始: {args.start_year}-{args.end_year}年')
    print('検出方法: 月次スケジュールページの CSS クラス (is-gradeColorVenus / is-gradeColorLady)')
    print()

    # Phase 1: スケジュールCSSクラスから女子戦日程を収集
    print('=== Phase 1: 女子戦日程収集 ===')
    ladies_venue_dates = collect_ladies_venue_dates(args.start_year, args.end_year)

    if not ladies_venue_dates:
        print('女子戦日程が0件。スケジュールAPIの問題の可能性あり。')
        return

    # Phase 2: races.is_ladies 更新
    print('\n=== Phase 2: races.is_ladies 更新 ===')
    conn = sqlite3.connect(DB_PATH)

    # 現状確認
    before_count = conn.execute('SELECT COUNT(*) FROM races WHERE is_ladies=1').fetchone()[0]
    print(f'更新前 is_ladies=1: {before_count}件')

    updated, already = update_is_ladies(conn, ladies_venue_dates, args.dry_run)
    print(f'新規更新: {updated}件')
    print(f'既に is_ladies=1: {already}件')

    after_count = conn.execute('SELECT COUNT(*) FROM races WHERE is_ladies=1').fetchone()[0]
    print(f'更新後 is_ladies=1: {after_count}件')

    # Phase 3: racers.gender 更新（オプション）
    if args.update_gender:
        print('\n=== Phase 3: racers.gender 更新 ===')
        gender_updated = update_gender_from_ladies_races(conn, args.dry_run)
        if args.dry_run:
            print(f'[DRY-RUN] 女子戦出場: {gender_updated}人（変更なし）')
        else:
            print(f'racers.gender=female 更新: {gender_updated}件')

        # 更新後の確認
        female_count = conn.execute("SELECT COUNT(*) FROM racers WHERE gender='female'").fetchone()[0]
        print(f'更新後 racers.gender=female: {female_count}人')

    conn.close()

    # サマリー
    print('\n=== 完了 ===')
    print(f'検出した女子戦日程: {len(ladies_venue_dates)}件 (venue×date)')
    print(f'races.is_ladies 更新: {updated}件')
    if args.update_gender:
        print(f'racers.gender=female 更新: {gender_updated}件')
    print()
    if not args.dry_run:
        print('次のステップ:')
        print('  python scripts/data_collection/fetch_racer_profiles.py  # 欠損選手プロフィール補完')
        print('  python scripts/data_collection/import_racers_csv.py      # CSV → DB 投入')


if __name__ == '__main__':
    main()
