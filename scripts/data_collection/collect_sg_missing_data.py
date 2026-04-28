# -*- coding: utf-8 -*-
"""
SG大会の欠損レースデータを補完収集するスクリプト

DBのSGグレードレースを分析し、6日間イベントとして欠損している日付を特定。
特定した (会場, 日付) の組み合わせだけをピンポイントで収集する。

使い方:
    # 対象一覧の確認のみ（ドライラン）
    python scripts/data_collection/collect_sg_missing_data.py --dry-run

    # 全年度を収集
    python scripts/data_collection/collect_sg_missing_data.py

    # 特定年のみ
    python scripts/data_collection/collect_sg_missing_data.py --start-year 2024 --end-year 2025

    # 収集後のインポート
    python scripts/data_collection/import_races_csv.py --dir data/csv/sg_missing
    python scripts/maintenance/backfill_race_grades.py
"""

import sys
import io
import os
import csv
import json
import sqlite3
import argparse
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

DB_PATH = ROOT_DIR / 'data' / 'boatrace.db'
OUTPUT_DIR = ROOT_DIR / 'data' / 'csv' / 'sg_missing'
PROGRESS_FILE = OUTPUT_DIR / 'progress.json'

thread_local = threading.local()


def get_scrapers():
    from src.scraper.race_scraper_v2 import RaceScraperV2
    from src.scraper.result_scraper import ResultScraper
    if not hasattr(thread_local, 'race_scraper'):
        thread_local.race_scraper = RaceScraperV2()
        thread_local.result_scraper = ResultScraper()
    return thread_local.race_scraper, thread_local.result_scraper


def find_missing_sg_pairs(conn, start_year: int, end_year: int) -> list:
    """
    DBのSGクラスターを分析して欠損 (venue, date) ペアを返す。
    6日間イベントとして [first_date-2, last_date+5] のウィンドウで欠損を探す。
    """
    cur = conn.cursor()

    # DBに存在するレース日付のセット
    cur.execute('SELECT venue_code, race_date FROM races GROUP BY venue_code, race_date')
    existing = {}
    for venue, date in cur.fetchall():
        existing.setdefault(venue, set()).add(date)

    # SG付きレース日を取得
    cur.execute('''
        SELECT venue_code, race_date FROM races
        WHERE race_grade = "SG"
        ORDER BY race_date, venue_code
    ''')
    rows = cur.fetchall()

    # クラスタリング（同会場で7日以内をひとつのイベントとみなす）
    clusters = []
    current = None
    for venue, date in rows:
        d = datetime.strptime(date, '%Y-%m-%d')
        yr = d.year
        if yr < start_year or yr > end_year:
            continue
        if current and current['venue'] == venue and (d - current['last']).days <= 7:
            current['dates'].append(date)
            current['last'] = d
        else:
            if current:
                clusters.append(current)
            current = {'venue': venue, 'dates': [date], 'last': d}
    if current:
        clusters.append(current)

    # 各クラスターの欠損日を特定
    missing_pairs = []  # (venue, date_str) のリスト
    for c in clusters:
        first = datetime.strptime(c['dates'][0], '%Y-%m-%d')
        last  = datetime.strptime(c['dates'][-1], '%Y-%m-%d')
        venue = c['venue']

        # 6日イベント想定ウィンドウ: first-2 〜 last+5（上限8日）
        window_start = first - timedelta(days=2)
        window_end   = last  + timedelta(days=5)
        if (window_end - window_start).days > 7:
            window_end = window_start + timedelta(days=7)

        d = window_start
        while d <= window_end:
            ds = d.strftime('%Y-%m-%d')
            if ds not in existing.get(venue, set()):
                missing_pairs.append((venue, ds))
            d += timedelta(days=1)

    # 重複排除・ソート
    missing_pairs = sorted(set(missing_pairs))
    return missing_pairs


def load_progress() -> set:
    """収集済み (venue, date) のセットを読み込む"""
    if PROGRESS_FILE.exists():
        data = json.loads(PROGRESS_FILE.read_text(encoding='utf-8'))
        return set(tuple(p) for p in data.get('done', []))
    return set()


def save_progress(done: set):
    """収集済み (venue, date) を保存"""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {'done': [list(p) for p in sorted(done)]}
    PROGRESS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def fetch_venue_day(venue_code: str, race_date: str) -> tuple:
    """1会場1日分を取得"""
    race_scraper, result_scraper = get_scrapers()
    date_yyyymmdd = race_date.replace('-', '')
    races_data = []

    for race_number in range(1, 13):
        data_found = False
        for retry in range(3):
            try:
                race_data = race_scraper.get_race_card(venue_code, date_yyyymmdd, race_number)
                if not race_data or not race_data.get('entries'):
                    break  # データなしは正常終了（リトライ不要）

                race_data['venue_code'] = venue_code
                race_data['race_date']   = date_yyyymmdd
                race_data['race_number'] = race_number

                result_data = result_scraper.get_race_result_complete(venue_code, date_yyyymmdd, race_number)
                races_data.append({'race': race_data, 'result': result_data})
                data_found = True
                time.sleep(0.1)
                break
            except Exception as e:
                if retry < 2:
                    time.sleep(2 ** retry)
                else:
                    print(f'  取得失敗: venue={venue_code} {race_date} R{race_number}: {e}')

        # R1 でデータなし（またはリトライ全失敗）→ 当日未開催扱いで打ち切り
        if race_number == 1 and not data_found:
            return venue_code, race_date, 0, []

    return venue_code, race_date, len(races_data), races_data


def save_to_csv(output_dir: Path, venue_code: str, race_date: str, races_data: list):
    """fetch_to_csv_parallel_improved.py と同一フォーマットでCSV追記"""
    output_dir.mkdir(parents=True, exist_ok=True)

    races_csv     = output_dir / 'races.csv'
    entries_csv   = output_dir / 'entries.csv'
    conditions_csv= output_dir / 'race_conditions.csv'
    details_csv   = output_dir / 'race_details.csv'
    results_csv   = output_dir / 'results.csv'
    payouts_csv   = output_dir / 'payouts.csv'

    races_header     = ['venue_code','race_date','race_number','race_time','race_grade',
                        'race_distance','is_nighter','is_ladies','is_rookie','is_shinnyuu_kotei']
    entries_header   = ['venue_code','race_date','race_number','pit_number','racer_number',
                        'racer_name','racer_rank','racer_home','racer_age','racer_weight',
                        'motor_number','boat_number','win_rate','second_rate','third_rate',
                        'f_count','l_count','avg_st','local_win_rate','local_second_rate',
                        'local_third_rate','motor_second_rate','motor_third_rate',
                        'boat_second_rate','boat_third_rate']
    conditions_header= ['venue_code','race_date','race_number','weather','wind_direction',
                        'wind_speed','wave_height','temperature','water_temperature']
    details_header   = ['venue_code','race_date','race_number','pit_number','exhibition_time',
                        'tilt_angle','parts_replacement','actual_course','st_time']
    results_header   = ['venue_code','race_date','race_number','pit_number','rank',
                        'is_invalid','kimarite']
    payouts_header   = ['venue_code','race_date','race_number','bet_type','combination',
                        'amount','popularity']

    def open_csv(path, header):
        write_header = not path.exists()
        f = open(path, 'a', newline='', encoding='utf-8')
        w = csv.DictWriter(f, fieldnames=header)
        if write_header:
            w.writeheader()
        return f, w

    f_races, w_races         = open_csv(races_csv,      races_header)
    f_entries, w_entries     = open_csv(entries_csv,    entries_header)
    f_cond, w_cond           = open_csv(conditions_csv, conditions_header)
    f_det, w_det             = open_csv(details_csv,    details_header)
    f_res, w_res             = open_csv(results_csv,    results_header)
    f_pay, w_pay             = open_csv(payouts_csv,    payouts_header)

    try:
        for item in races_data:
            rd = item['race']
            result = item['result']
            rnum = rd.get('race_number')
            rdate_str = race_date.replace('-', '')  # YYYYMMDD（既存CSV形式に統一）

            w_races.writerow({
                'venue_code': venue_code, 'race_date': rdate_str,
                'race_number': rnum,
                'race_time': rd.get('race_time', ''),
                'race_grade': rd.get('race_grade', ''),
                'race_distance': rd.get('race_distance', 1800),
                'is_nighter': 1 if rd.get('is_nighter') else 0,
                'is_ladies': 1 if rd.get('is_ladies') else 0,
                'is_rookie': 1 if rd.get('is_rookie') else 0,
                'is_shinnyuu_kotei': 1 if rd.get('is_shinnyuu_kotei') else 0,
            })

            for e in rd.get('entries', []):
                w_entries.writerow({
                    'venue_code': venue_code, 'race_date': rdate_str, 'race_number': rnum,
                    'pit_number': e.get('pit_number'), 'racer_number': e.get('racer_number',''),
                    'racer_name': e.get('racer_name',''), 'racer_rank': e.get('racer_rank',''),
                    'racer_home': e.get('racer_home',''), 'racer_age': e.get('racer_age'),
                    'racer_weight': e.get('racer_weight'), 'motor_number': e.get('motor_number'),
                    'boat_number': e.get('boat_number'), 'win_rate': e.get('win_rate'),
                    'second_rate': e.get('second_rate'), 'third_rate': e.get('third_rate'),
                    'f_count': e.get('f_count'), 'l_count': e.get('l_count'),
                    'avg_st': e.get('avg_st'), 'local_win_rate': e.get('local_win_rate'),
                    'local_second_rate': e.get('local_second_rate'),
                    'local_third_rate': e.get('local_third_rate'),
                    'motor_second_rate': e.get('motor_second_rate'),
                    'motor_third_rate': e.get('motor_third_rate'),
                    'boat_second_rate': e.get('boat_second_rate'),
                    'boat_third_rate': e.get('boat_third_rate'),
                })

            if result and result.get('weather_data'):
                wd = result['weather_data']
                w_cond.writerow({
                    'venue_code': venue_code, 'race_date': rdate_str, 'race_number': rnum,
                    'weather': wd.get('weather_condition',''),
                    'wind_direction': wd.get('wind_direction',''),
                    'wind_speed': wd.get('wind_speed'),
                    'wave_height': wd.get('wave_height'),
                    'temperature': wd.get('temperature'),
                    'water_temperature': wd.get('water_temperature'),
                })

            if result:
                actual_courses = result.get('actual_courses', {})
                st_times = result.get('st_times', {})
                for pit in range(1, 7):
                    ac = actual_courses.get(pit)
                    st = st_times.get(pit)
                    if ac is not None or st is not None:
                        w_det.writerow({
                            'venue_code': venue_code, 'race_date': rdate_str,
                            'race_number': rnum, 'pit_number': pit,
                            'exhibition_time': None, 'tilt_angle': None,
                            'parts_replacement': '', 'actual_course': ac, 'st_time': st,
                        })

                kimarite = result.get('kimarite') or result.get('winning_technique')
                for r in result.get('results', []):
                    w_res.writerow({
                        'venue_code': venue_code, 'race_date': rdate_str,
                        'race_number': rnum, 'pit_number': r.get('pit_number'),
                        'rank': r.get('rank',''), 'is_invalid': 1 if r.get('is_invalid') else 0,
                        'kimarite': kimarite if r.get('rank') == 1 else '',
                    })

                for bet_key, payout_list in result.get('payouts', {}).items():
                    for payout in payout_list:
                        combo = payout.get('combination') or str(payout.get('pit_number',''))
                        w_pay.writerow({
                            'venue_code': venue_code, 'race_date': rdate_str,
                            'race_number': rnum, 'bet_type': bet_key,
                            'combination': combo,
                            'amount': payout.get('amount'),
                            'popularity': payout.get('popularity'),
                        })
    finally:
        for f in [f_races, f_entries, f_cond, f_det, f_res, f_pay]:
            f.close()


def main():
    parser = argparse.ArgumentParser(description='SG欠損レースデータ補完収集')
    parser.add_argument('--start-year', type=int, default=2018)
    parser.add_argument('--end-year',   type=int, default=2025)
    parser.add_argument('--workers',    type=int, default=4, help='並列数（デフォルト: 4）')
    parser.add_argument('--dry-run',    action='store_true')
    parser.add_argument('--delay',      type=float, default=0.5, help='会場間待機秒数')
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    try:
        missing = find_missing_sg_pairs(conn, args.start_year, args.end_year)
    finally:
        conn.close()

    print(f'=== SG欠損データ補完収集 ===')
    print(f'対象期間: {args.start_year}〜{args.end_year}年')
    print(f'欠損 (会場, 日付) ペア数: {len(missing)}件')
    print()

    if args.dry_run:
        print('[DRY RUN] 対象一覧:')
        by_year = {}
        for venue, date in missing:
            yr = date[:4]
            by_year.setdefault(yr, []).append((venue, date))
        for yr in sorted(by_year):
            print(f'  {yr}年: {len(by_year[yr])}件')
            for v, d in sorted(by_year[yr])[:5]:
                print(f'    venue={v} {d}')
            if len(by_year[yr]) > 5:
                print(f'    ... (+{len(by_year[yr])-5}件)')
        print()
        print('実際に収集するには --dry-run を外して実行してください')
        return

    # 収集済みをスキップ
    done = load_progress()
    targets = [(v, d) for v, d in missing if (v, d) not in done]
    print(f'収集済みスキップ: {len(missing) - len(targets)}件')
    print(f'今回収集対象: {len(targets)}件')
    print(f'出力先: {OUTPUT_DIR}')
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total_fetched = 0
    total_no_race = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_venue_day, v, d): (v, d) for v, d in targets}
        completed = 0
        for future in as_completed(futures):
            venue, date, count, races_data = future.result()
            completed += 1
            key = (venue, date)

            if count > 0:
                save_to_csv(OUTPUT_DIR, venue, date, races_data)
                total_fetched += count
                print(f'  [{completed}/{len(targets)}] venue={venue} {date}: {count}レース取得')
            else:
                total_no_race += 1
                print(f'  [{completed}/{len(targets)}] venue={venue} {date}: 開催なし（スキップ）')

            done.add(key)
            if completed % 10 == 0:
                save_progress(done)
            time.sleep(args.delay)

    save_progress(done)

    print()
    print(f'=== 完了 ===')
    print(f'取得レース数: {total_fetched}件')
    print(f'開催なし日数: {total_no_race}件')
    print()
    print('次のステップ:')
    print(f'  1. python scripts/data_collection/import_races_csv.py --dir {OUTPUT_DIR}')
    print(f'  2. python scripts/maintenance/backfill_race_grades.py')
    print(f'  3. python scripts/data_collection/補完_決まり手データ_改善版.py')
    print(f'  4. python scripts/data_collection/補完_レース詳細データ_改善版v4.py')
    print(f'  5. python scripts/data_collection/fetch_odds_parallel_safe.py  # trifecta_odds')


if __name__ == '__main__':
    main()
