"""
並列データ取得スクリプト - 改善版V3
STタイムに決まり手が混入するバグを修正

使用方法:
  python fetch_improved_v3.py --fill-missing --workers 5 --limit 100
  python fetch_improved_v3.py --start 2015-01-01 --end 2015-01-31 --workers 3
"""

import argparse
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
import sqlite3

from src.database.data_manager import DataManager
from src.scraper.result_scraper_improved_v3 import ImprovedResultScraperV3
from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from src.scraper.race_scraper_v2 import RaceScraperV2
from src.scraper.schedule_scraper import ScheduleScraper


def get_missing_data_tasks(db_path="data/boatrace.db", limit=None):
    """欠損データを検出"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT DISTINCT
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE rd.race_id IS NULL
           OR rd.exhibition_time IS NULL
           OR rd.st_time IS NULL
           OR rd.actual_course IS NULL
        ORDER BY r.race_date DESC, r.venue_code, r.race_number
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    rows = cursor.fetchall()

    tasks = []
    for venue_code, race_date, race_number in rows:
        date_str = race_date.replace('-', '')
        tasks.append((venue_code, date_str, race_number))

    conn.close()
    return tasks


def fetch_single_race(args):
    """1レースのデータを取得"""
    venue_code, date_str, race_number = args

    result = {
        'venue_code': venue_code,
        'date_str': date_str,
        'race_number': race_number,
        'success': False,
        'error': None,
        'data': None
    }

    try:
        # スクレイパー初期化
        race_scraper = RaceScraperV2()
        result_scraper = ImprovedResultScraperV3()
        beforeinfo_scraper = BeforeInfoScraper(delay=0.3)

        # データ取得
        race_data = race_scraper.get_race_card(venue_code, date_str, race_number)
        beforeinfo = beforeinfo_scraper.get_race_beforeinfo(venue_code, date_str, race_number)
        complete_result = result_scraper.get_race_result_complete(venue_code, date_str, race_number)

        # クリーンアップ
        race_scraper.close()
        result_scraper.close()
        beforeinfo_scraper.close()

        if not race_data or len(race_data.get('entries', [])) == 0:
            result['error'] = 'Empty race card'
            return result

        result['data'] = {
            'race_data': race_data,
            'beforeinfo': beforeinfo,
            'complete_result': complete_result
        }
        result['success'] = True

    except Exception as e:
        result['error'] = str(e)

    return result


def save_race_data(data, db):
    """1レースのデータをDBに保存"""
    venue_code = data['venue_code']
    date_str = data['date_str']
    race_number = data['race_number']
    content = data['data']

    try:
        # 出走表保存
        race_data = content['race_data']
        if race_data:
            db.save_race_data(race_data)

        # レースID取得
        race_date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        race_record = db.get_race_data(venue_code, race_date_formatted, race_number)

        if not race_record:
            print(f"[ERROR] Race ID not found: {venue_code} {date_str} {race_number}R")
            return False

        race_id = race_record['id']

        # 事前情報保存
        beforeinfo = content['beforeinfo']
        if beforeinfo:
            detail_updates = []
            for pit in range(1, 7):
                pit_detail = {'pit_number': pit}

                if pit in beforeinfo.get('exhibition_times', {}):
                    pit_detail['exhibition_time'] = beforeinfo['exhibition_times'][pit]
                if pit in beforeinfo.get('tilt_angles', {}):
                    pit_detail['tilt_angle'] = beforeinfo['tilt_angles'][pit]
                if pit in beforeinfo.get('parts_replacements', {}):
                    pit_detail['parts_replacement'] = beforeinfo['parts_replacements'][pit]

                if len(pit_detail) > 1:
                    detail_updates.append(pit_detail)

            if detail_updates:
                db.save_race_details(race_id, detail_updates)

        # 結果保存
        complete_result = content['complete_result']
        if complete_result and not complete_result.get('is_invalid'):
            # 決まり手
            kimarite_text = complete_result.get('kimarite')
            winning_technique = None
            if kimarite_text:
                kimarite_map = {
                    '逃げ': 1, '差し': 2, 'まくり': 3,
                    'まくり差し': 4, '抜き': 5, '恵まれ': 6
                }
                winning_technique = kimarite_map.get(kimarite_text)

            # 結果データ
            result_data_for_save = {
                'venue_code': venue_code,
                'race_date': date_str,
                'race_number': race_number,
                'results': complete_result.get('results', []),
                'trifecta_odds': complete_result.get('trifecta_odds'),
                'is_invalid': complete_result.get('is_invalid', False),
                'winning_technique': winning_technique,
                'kimarite': kimarite_text
            }
            db.save_race_result(result_data_for_save)

            # STタイムと進入コース
            actual_courses = complete_result.get('actual_courses', {})
            st_times = complete_result.get('st_times', {})
            st_status = complete_result.get('st_status', {})

            if actual_courses or st_times:
                detail_updates = []
                for pit in range(1, 7):
                    pit_detail = {'pit_number': pit}

                    if pit in actual_courses:
                        pit_detail['actual_course'] = actual_courses[pit]
                    if pit in st_times:
                        pit_detail['st_time'] = st_times[pit]

                    if len(pit_detail) > 1:
                        detail_updates.append(pit_detail)

                if detail_updates:
                    db.save_race_details(race_id, detail_updates)

            # F/Lログ
            flying = [p for p, s in st_status.items() if s == 'flying']
            late = [p for p, s in st_status.items() if s == 'late']

            st_count = len(st_times)
            log_msg = f"[OK] {venue_code} {date_str} {race_number:2d}R (ST: {st_count}/6)"

            if flying:
                log_msg += f" [F:{flying}]"
            if late:
                log_msg += f" [L:{late}]"

            print(log_msg)

            # 天気
            weather_data = complete_result.get('weather_data')
            if weather_data:
                race_date_obj = datetime.strptime(date_str, '%Y%m%d')
                db.save_weather_data(
                    venue_code=venue_code,
                    weather_date=race_date_obj.strftime('%Y-%m-%d'),
                    weather_data=weather_data
                )

            # 払戻
            payouts = complete_result.get('payouts', {})
            if payouts:
                db.save_payouts(race_id, payouts)

        return True

    except Exception as e:
        print(f"[ERROR] Save failed: {venue_code} {date_str} {race_number}R - {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Boat race data parallel fetch - V3')
    parser.add_argument('--start', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', help='End date (YYYY-MM-DD)')
    parser.add_argument('--workers', type=int, default=3, help='Number of workers (default: 3)')
    parser.add_argument('--fill-missing', action='store_true', help='Fill missing data mode')
    parser.add_argument('--limit', type=int, help='Limit number of tasks')

    args = parser.parse_args()

    if args.fill_missing:
        print("="*80)
        print(f"Improved V3 - Fill Missing Data Mode")
        print("="*80)
        print(f"Workers: {args.workers}")
        print("="*80)

        print("\nDetecting missing data...")
        tasks = get_missing_data_tasks(limit=args.limit)
        print(f"  Missing data: {len(tasks)} tasks")

        if len(tasks) == 0:
            print("\nNo missing data!")
            return

    else:
        if not args.start or not args.end:
            print("Error: --start and --end required")
            return

        start_date = datetime.strptime(args.start, '%Y-%m-%d')
        end_date = datetime.strptime(args.end, '%Y-%m-%d')

        print("="*80)
        print(f"Improved V3 - New Data Fetch Mode")
        print("="*80)
        print(f"Period: {args.start} - {args.end}")
        print(f"Workers: {args.workers}")
        print("="*80)

        print("\nFetching schedule...")
        schedule_scraper = ScheduleScraper()
        schedule = schedule_scraper.get_schedule_for_period(start_date, end_date)
        schedule_scraper.close()

        tasks = []
        for venue_code, dates in schedule.items():
            for date_str in dates:
                for race_number in range(1, 13):
                    tasks.append((venue_code, date_str, race_number))

        if args.limit:
            tasks = tasks[:args.limit]

        print(f"  Total tasks: {len(tasks)}")

    start_time = time.time()
    db = DataManager()

    # 並列処理
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_single_race, task): task for task in tasks}

        completed = 0
        saved = 0
        errors = 0

        for future in as_completed(futures):
            task = futures[future]

            try:
                result = future.result()
                completed += 1

                if result['success']:
                    if save_race_data(result, db):
                        saved += 1
                    else:
                        errors += 1
                else:
                    if result['error'] and 'Empty race card' not in result['error']:
                        print(f"[SKIP] {result['venue_code']} {result['date_str']} {result['race_number']}R - {result['error']}")
                    errors += 1

                if completed % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed
                    remaining = (len(tasks) - completed) / rate if rate > 0 else 0
                    print(f"\n[Progress] {completed}/{len(tasks)} ({completed/len(tasks)*100:.1f}%) - ETA {remaining/60:.0f}min")
                    print(f"  Saved: {saved}, Errors: {errors}\n")

            except Exception as e:
                print(f"[ERROR] {task} - {e}")
                completed += 1
                errors += 1

    elapsed = time.time() - start_time

    print("\n" + "="*80)
    print("Complete")
    print("="*80)
    print(f"Total tasks: {len(tasks)}")
    print(f"Saved: {saved}")
    print(f"Errors: {errors}")
    print(f"Time: {elapsed/60:.1f}min")
    if len(tasks) > 0:
        print(f"Success rate: {saved/len(tasks)*100:.1f}%")
    print("="*80)


if __name__ == '__main__':
    main()
