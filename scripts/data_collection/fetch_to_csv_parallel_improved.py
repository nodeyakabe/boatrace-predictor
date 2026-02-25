# -*- coding: utf-8 -*-
"""過去データをCSVファイルに保存（改善版・開催スケジュール対応）

改善点:
1. 開催スケジュールを事前取得し、実際に開催している会場のみアクセス
2. 過去レースで「結果が不完全」の場合はエラーとして扱う
3. 無駄なアクセスを削減し、高速化

使用例:
    # 特定期間のデータをCSV出力
    python scripts/data_collection/fetch_to_csv_parallel_improved.py --start 2026-01-04 --end 2026-01-14 --output data/csv/2026_01

    # 並列数を指定
    python scripts/data_collection/fetch_to_csv_parallel_improved.py --start 2020-01-01 --end 2020-01-31 --workers 12 --output data/csv/2020_01
"""

import sys
import os
import csv
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading

# Windows文字コード対策
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.scraper.race_scraper_v2 import RaceScraperV2
from src.scraper.result_scraper import ResultScraper
from src.scraper.schedule_scraper import ScheduleScraper

# スレッドローカルストレージ
thread_local = threading.local()

def get_scrapers():
    """スレッドローカルなスクレイパーを取得"""
    if not hasattr(thread_local, 'race_scraper'):
        thread_local.race_scraper = RaceScraperV2()
        thread_local.result_scraper = ResultScraper()
    return thread_local.race_scraper, thread_local.result_scraper


def get_date_range(start_date: str, end_date: str):
    """日付範囲をリストで返す"""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    return dates


def get_schedule_for_period(start_date: str, end_date: str):
    """
    期間内の開催スケジュールを取得

    Returns:
        dict: {
            '20260104': ['01', '02', '03', ...],  # その日に開催している会場リスト
            '20260105': ['01', '04', '05', ...],
            ...
        }
    """
    scraper = ScheduleScraper()
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')

    print("\n=== 開催スケジュール取得中 ===")
    venue_schedule = scraper.get_schedule_for_period(start_dt, end_dt)
    scraper.close()

    # 日付ごとのスケジュールに変換
    date_schedule = {}
    for venue_code, dates in venue_schedule.items():
        for date_str in dates:
            if date_str not in date_schedule:
                date_schedule[date_str] = []
            date_schedule[date_str].append(venue_code)

    # 各日付の会場リストをソート
    for date_str in date_schedule:
        date_schedule[date_str].sort()

    # 統計表示
    total_venue_days = sum(len(venues) for venues in date_schedule.values())
    days_count = len(date_schedule)
    avg_venues = total_venue_days / days_count if days_count > 0 else 0

    print(f"  期間: {start_date} ～ {end_date}")
    print(f"  開催日数: {days_count}日")
    print(f"  総会場日数: {total_venue_days} (平均 {avg_venues:.1f}会場/日)")
    print()

    return date_schedule


def fetch_venue_day_parallel(args):
    """1会場1日分のデータを取得（並列用）"""
    venue_code, race_date, _ = args

    race_scraper, result_scraper = get_scrapers()

    race_date_yyyymmdd = race_date.replace('-', '')
    success_count = 0
    races_data = []
    incomplete_results = []

    for race_number in range(1, 13):
        max_retries = 3
        for retry in range(max_retries):
            try:
                # 出走表取得
                race_data = race_scraper.get_race_card(venue_code, race_date_yyyymmdd, race_number)
                if not race_data or not race_data.get('entries'):
                    break  # データなしは正常終了

                race_data['venue_code'] = venue_code
                race_data['race_date'] = race_date_yyyymmdd
                race_data['race_number'] = race_number

                # 結果取得（payouts含む完全版）
                result_data = result_scraper.get_race_result_complete(venue_code, race_date_yyyymmdd, race_number)

                # 過去レースで結果が不完全な場合は警告
                if result_data and result_data.get('results'):
                    result_count = len(result_data['results'])
                    if result_count < 6:
                        incomplete_results.append(
                            f"{venue_code} {race_date_yyyymmdd} R{race_number} (取得: {result_count}/6艇)"
                        )

                races_data.append({
                    'race': race_data,
                    'result': result_data
                })
                success_count += 1

                time.sleep(0.1)  # レート制限
                break  # 成功したらリトライループを抜ける

            except Exception as e:
                if retry < max_retries - 1:
                    time.sleep(2 ** retry)  # 指数バックオフ

    return venue_code, race_date, success_count, races_data, incomplete_results


def save_to_csv(output_dir: Path, all_races_data: list):
    """取得したデータをCSVファイルに保存

    保存形式:
    - races.csv: レース基本情報
    - entries.csv: 出走表
    - race_conditions.csv: レース条件（天候等）
    - race_details.csv: 展示情報
    - results.csv: レース結果
    - payouts.csv: 払戻金
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # CSVファイルパス
    races_csv = output_dir / 'races.csv'
    entries_csv = output_dir / 'entries.csv'
    conditions_csv = output_dir / 'race_conditions.csv'
    details_csv = output_dir / 'race_details.csv'
    results_csv = output_dir / 'results.csv'
    payouts_csv = output_dir / 'payouts.csv'

    # ヘッダー定義
    races_header = ['venue_code', 'race_date', 'race_number', 'race_time', 'race_grade',
                    'race_distance', 'is_nighter', 'is_ladies', 'is_rookie', 'is_shinnyuu_kotei']
    entries_header = ['venue_code', 'race_date', 'race_number', 'pit_number', 'racer_number',
                      'racer_name', 'racer_rank', 'racer_home', 'racer_age', 'racer_weight',
                      'motor_number', 'boat_number', 'win_rate', 'second_rate', 'third_rate',
                      'f_count', 'l_count', 'avg_st', 'local_win_rate', 'local_second_rate',
                      'local_third_rate', 'motor_second_rate', 'motor_third_rate',
                      'boat_second_rate', 'boat_third_rate']
    conditions_header = ['venue_code', 'race_date', 'race_number', 'weather', 'wind_direction',
                         'wind_speed', 'wave_height', 'temperature', 'water_temperature']
    details_header = ['venue_code', 'race_date', 'race_number', 'pit_number', 'exhibition_time',
                      'tilt_angle', 'parts_replacement', 'actual_course', 'st_time']
    results_header = ['venue_code', 'race_date', 'race_number', 'pit_number', 'rank',
                      'is_invalid', 'kimarite']
    payouts_header = ['venue_code', 'race_date', 'race_number', 'bet_type', 'combination',
                      'amount', 'popularity']

    # ファイルが存在しない場合のみヘッダーを書き込む
    write_headers = {
        races_csv: not races_csv.exists(),
        entries_csv: not entries_csv.exists(),
        conditions_csv: not conditions_csv.exists(),
        details_csv: not details_csv.exists(),
        results_csv: not results_csv.exists(),
        payouts_csv: not payouts_csv.exists(),
    }

    # CSVファイルを開く（追記モード）
    with open(races_csv, 'a', newline='', encoding='utf-8') as f_races, \
         open(entries_csv, 'a', newline='', encoding='utf-8') as f_entries, \
         open(conditions_csv, 'a', newline='', encoding='utf-8') as f_conditions, \
         open(details_csv, 'a', newline='', encoding='utf-8') as f_details, \
         open(results_csv, 'a', newline='', encoding='utf-8') as f_results, \
         open(payouts_csv, 'a', newline='', encoding='utf-8') as f_payouts:

        writer_races = csv.DictWriter(f_races, fieldnames=races_header)
        writer_entries = csv.DictWriter(f_entries, fieldnames=entries_header)
        writer_conditions = csv.DictWriter(f_conditions, fieldnames=conditions_header)
        writer_details = csv.DictWriter(f_details, fieldnames=details_header)
        writer_results = csv.DictWriter(f_results, fieldnames=results_header)
        writer_payouts = csv.DictWriter(f_payouts, fieldnames=payouts_header)

        # ヘッダー書き込み
        if write_headers[races_csv]:
            writer_races.writeheader()
        if write_headers[entries_csv]:
            writer_entries.writeheader()
        if write_headers[conditions_csv]:
            writer_conditions.writeheader()
        if write_headers[details_csv]:
            writer_details.writeheader()
        if write_headers[results_csv]:
            writer_results.writeheader()
        if write_headers[payouts_csv]:
            writer_payouts.writeheader()

        saved_count = 0

        for item in all_races_data:
            venue_code = item['venue_code']
            race_date = item['race_date']
            races_data = item['races_data']

            for race_item in races_data:
                try:
                    race_data = race_item['race']
                    result_data = race_item['result']

                    # レース基本情報
                    race_row = {
                        'venue_code': venue_code,
                        'race_date': race_date,
                        'race_number': race_data.get('race_number'),
                        'race_time': race_data.get('race_time', ''),
                        'race_grade': race_data.get('race_grade', ''),
                        'race_distance': race_data.get('race_distance', 1800),
                        'is_nighter': 1 if race_data.get('is_nighter') else 0,
                        'is_ladies': 1 if race_data.get('is_ladies') else 0,
                        'is_rookie': 1 if race_data.get('is_rookie') else 0,
                        'is_shinnyuu_kotei': 1 if race_data.get('is_shinnyuu_kotei') else 0,
                    }
                    writer_races.writerow(race_row)

                    # 出走表
                    for entry in race_data.get('entries', []):
                        entry_row = {
                            'venue_code': venue_code,
                            'race_date': race_date,
                            'race_number': race_data.get('race_number'),
                            'pit_number': entry.get('pit_number'),
                            'racer_number': entry.get('racer_number', ''),
                            'racer_name': entry.get('racer_name', ''),
                            'racer_rank': entry.get('racer_rank', ''),
                            'racer_home': entry.get('racer_home', ''),
                            'racer_age': entry.get('racer_age'),
                            'racer_weight': entry.get('racer_weight'),
                            'motor_number': entry.get('motor_number'),
                            'boat_number': entry.get('boat_number'),
                            'win_rate': entry.get('win_rate'),
                            'second_rate': entry.get('second_rate'),
                            'third_rate': entry.get('third_rate'),
                            'f_count': entry.get('f_count'),
                            'l_count': entry.get('l_count'),
                            'avg_st': entry.get('avg_st'),
                            'local_win_rate': entry.get('local_win_rate'),
                            'local_second_rate': entry.get('local_second_rate'),
                            'local_third_rate': entry.get('local_third_rate'),
                            'motor_second_rate': entry.get('motor_second_rate'),
                            'motor_third_rate': entry.get('motor_third_rate'),
                            'boat_second_rate': entry.get('boat_second_rate'),
                            'boat_third_rate': entry.get('boat_third_rate'),
                        }
                        writer_entries.writerow(entry_row)

                    # レース条件
                    if race_data.get('weather'):
                        condition_row = {
                            'venue_code': venue_code,
                            'race_date': race_date,
                            'race_number': race_data.get('race_number'),
                            'weather': race_data.get('weather', ''),
                            'wind_direction': race_data.get('wind_direction', ''),
                            'wind_speed': race_data.get('wind_speed'),
                            'wave_height': race_data.get('wave_height'),
                            'temperature': race_data.get('temperature'),
                            'water_temperature': race_data.get('water_temperature'),
                        }
                        writer_conditions.writerow(condition_row)

                    # 展示情報
                    for entry in race_data.get('entries', []):
                        if entry.get('exhibition_time') or entry.get('actual_course'):
                            detail_row = {
                                'venue_code': venue_code,
                                'race_date': race_date,
                                'race_number': race_data.get('race_number'),
                                'pit_number': entry.get('pit_number'),
                                'exhibition_time': entry.get('exhibition_time'),
                                'tilt_angle': entry.get('tilt_angle'),
                                'parts_replacement': entry.get('parts_replacement', ''),
                                'actual_course': entry.get('actual_course'),
                                'st_time': entry.get('st_time'),
                            }
                            writer_details.writerow(detail_row)

                    # 結果データ
                    if result_data:
                        # kimariteはレース単位でkimariteキーに格納されている
                        winning_technique = result_data.get('kimarite') or result_data.get('winning_technique')
                        for result in result_data.get('results', []):
                            rank = result.get('rank', '')
                            result_row = {
                                'venue_code': venue_code,
                                'race_date': race_date,
                                'race_number': race_data.get('race_number'),
                                'pit_number': result.get('pit_number'),
                                'rank': rank,
                                'is_invalid': 1 if result.get('is_invalid') else 0,
                                'kimarite': winning_technique if rank == 1 else '',
                            }
                            writer_results.writerow(result_row)

                        # 払戻金（get_race_result_completeはdict形式: {bet_key: [list]}）
                        for bet_key, payout_list in result_data.get('payouts', {}).items():
                            for payout in payout_list:
                                # win/placeはpit_number、それ以外はcombinationを使用
                                combination_val = payout.get('combination') or str(payout.get('pit_number', ''))
                                payout_row = {
                                    'venue_code': venue_code,
                                    'race_date': race_date,
                                    'race_number': race_data.get('race_number'),
                                    'bet_type': bet_key,
                                    'combination': combination_val,
                                    'amount': payout.get('amount'),
                                    'popularity': payout.get('popularity'),
                                }
                                writer_payouts.writerow(payout_row)

                    saved_count += 1

                except Exception as e:
                    print(f"CSV保存エラー: {e}")
                    import traceback
                    traceback.print_exc()

    return saved_count


def main():
    parser = argparse.ArgumentParser(description='過去データをCSVに保存（改善版）')
    parser.add_argument('--start', type=str, required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--output', type=str, required=True, help='出力ディレクトリ')
    parser.add_argument('--workers', type=int, default=12, help='並列数（デフォルト: 12）')
    parser.add_argument('--brute-force', action='store_true',
                        help='全24会場×全日付をブルートフォースで試行（スケジュールAPI不完全な過去期間向け）')
    args = parser.parse_args()

    output_dir = Path(args.output)
    dates = get_date_range(args.start, args.end)

    print("=" * 70)
    print("過去データCSV保存（改善版・開催スケジュール対応）")
    print("=" * 70)
    print(f"期間: {args.start} - {args.end} ({len(dates)}日間)")
    print(f"出力先: {output_dir}")
    print(f"並列数: {args.workers}スレッド")
    if args.brute_force:
        print(f"モード: ブルートフォース（全24会場×全日付）")
    print()

    # スケジュール取得 or ブルートフォース
    if args.brute_force:
        # スケジュールAPIに依存せず全24会場×全日付を試行
        all_venues = [f"{i:02d}" for i in range(1, 25)]
        date_schedule = {}
        for d in dates:
            d_key = d.replace('-', '')
            date_schedule[d_key] = all_venues
        total_venue_days = len(dates) * 24
        print(f"=== ブルートフォースモード ===")
        print(f"  期間: {args.start} ～ {args.end}")
        print(f"  全会場日数: {total_venue_days} ({len(dates)}日 × 24会場)")
        print(f"  ※スケジュールAPIをスキップ。開催なしの会場はスキップされます")
        print()
    else:
        date_schedule = get_schedule_for_period(args.start, args.end)

    # タスク作成（開催している会場のみ）
    tasks = []
    for date_str, venue_codes in date_schedule.items():
        date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        for venue_code in venue_codes:
            tasks.append((venue_code, date_formatted, None))

    total_venue_days = len(tasks)
    total_possible_tasks = len(dates) * 24
    reduction_rate = (1 - total_venue_days / total_possible_tasks) * 100 if total_possible_tasks > 0 else 0

    print("=== タスク最適化 ===")
    print(f"  従来方式: {total_possible_tasks}タスク (全日×全会場)")
    print(f"  改善版: {total_venue_days}タスク (開催日のみ)")
    print(f"  削減率: {reduction_rate:.1f}%")
    print(f"  予想時間: 約{total_venue_days * 0.02 / 60:.1f}-{total_venue_days * 0.04 / 60:.1f}時間")
    print()

    # 並列取得開始
    print("=== データ取得開始 ===")
    start_time = time.time()

    all_results = []
    completed = 0
    total_races = 0
    all_incomplete_results = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_venue_day_parallel, task): task for task in tasks}

        for future in as_completed(futures):
            completed += 1
            venue_code, race_date, success_count, races_data, incomplete_results = future.result()

            if success_count > 0:
                all_results.append({
                    'venue_code': venue_code,
                    'race_date': race_date.replace('-', ''),
                    'races_data': races_data
                })
                total_races += success_count

            # 不完全な結果を記録
            all_incomplete_results.extend(incomplete_results)

            if completed % 50 == 0 or completed == len(tasks):
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = (len(tasks) - completed) / rate if rate > 0 else 0
                print(f"進捗: {completed}/{len(tasks)} ({completed/len(tasks)*100:.1f}%) - "
                      f"取得レース: {total_races} - 残り約{remaining/60:.1f}分")

    # CSV保存
    print("\n=== CSV保存中 ===")
    saved = save_to_csv(output_dir, all_results)

    elapsed = time.time() - start_time

    print()
    print("=" * 70)
    print("処理完了")
    print("=" * 70)
    print(f"取得レース数: {total_races}")
    print(f"保存レース数: {saved}")
    print(f"所要時間: {elapsed/60:.1f}分")
    print(f"速度: {len(dates) / (elapsed/60):.1f}日/分")
    print(f"\n出力先: {output_dir.absolute()}")

    # 不完全な結果の警告
    if all_incomplete_results:
        print("\n" + "=" * 70)
        print("⚠️ 警告: 不完全な結果が検出されました")
        print("=" * 70)
        print(f"該当レース数: {len(all_incomplete_results)}")
        print("\n最初の10件:")
        for i, msg in enumerate(all_incomplete_results[:10], 1):
            print(f"  {i}. {msg}")
        if len(all_incomplete_results) > 10:
            print(f"  ... 他{len(all_incomplete_results) - 10}件")
        print("\n過去のレースで結果が6艇未満の場合、データ取得に問題がある可能性があります。")


if __name__ == '__main__':
    main()
