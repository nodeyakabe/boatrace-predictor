# -*- coding: utf-8 -*-
"""過去データをCSVファイルに保存（DB負荷なし版）

並列化により高速取得し、CSVに出力することでDB負荷を回避:
- データ収集中はDBロックなし
- 他の作業と並行可能
- 失敗時のリカバリが容易

使用例:
    # 特定期間のデータをCSV出力
    python scripts/data_collection/fetch_to_csv_parallel.py --start 2020-01-01 --end 2020-12-31 --output data/csv/2020

    # 並列数を指定
    python scripts/data_collection/fetch_to_csv_parallel.py --start 2020-01-01 --end 2020-01-31 --workers 12 --output data/csv/2020_01
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
import json

# Windows文字コード対策
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.scraper.race_scraper_v2 import RaceScraperV2
from src.scraper.result_scraper import ResultScraper

# 全24競艇場コード
ALL_VENUES = [
    '01', '02', '03', '04', '05', '06', '07', '08', '09', '10',
    '11', '12', '13', '14', '15', '16', '17', '18', '19', '20',
    '21', '22', '23', '24'
]

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


def fetch_venue_day_parallel(args):
    """1会場1日分のデータを取得（並列用）"""
    venue_code, race_date, _ = args

    race_scraper, result_scraper = get_scrapers()

    race_date_yyyymmdd = race_date.replace('-', '')
    success_count = 0
    races_data = []

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

                # 結果取得
                result_data = result_scraper.get_race_result(venue_code, race_date_yyyymmdd, race_number)

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

    return venue_code, race_date, success_count, races_data


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
                        for result in result_data.get('results', []):
                            result_row = {
                                'venue_code': venue_code,
                                'race_date': race_date,
                                'race_number': race_data.get('race_number'),
                                'pit_number': result.get('pit_number'),
                                'rank': result.get('rank', ''),
                                'is_invalid': 1 if result.get('is_invalid') else 0,
                                'kimarite': result.get('kimarite', ''),
                            }
                            writer_results.writerow(result_row)

                        # 払戻金
                        for payout in result_data.get('payouts', []):
                            payout_row = {
                                'venue_code': venue_code,
                                'race_date': race_date,
                                'race_number': race_data.get('race_number'),
                                'bet_type': payout.get('bet_type', ''),
                                'combination': payout.get('combination', ''),
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
    parser = argparse.ArgumentParser(description='過去データをCSVに保存（並列化版）')
    parser.add_argument('--start', type=str, required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--output', type=str, required=True, help='出力ディレクトリ')
    parser.add_argument('--workers', type=int, default=12, help='並列数（デフォルト: 12）')
    args = parser.parse_args()

    output_dir = Path(args.output)
    dates = get_date_range(args.start, args.end)

    print("=" * 70)
    print("過去データCSV保存（並列化版）")
    print("=" * 70)
    print(f"期間: {args.start} - {args.end} ({len(dates)}日間)")
    print(f"出力先: {output_dir}")
    print(f"並列数: {args.workers}スレッド")
    print(f"予想時間: 約{len(dates) * 0.5 / 60:.1f}-{len(dates) * 1 / 60:.1f}時間")
    print()

    # 並列取得開始
    print("=== データ取得開始 ===")
    start_time = time.time()

    # 全タスクを作成（日付×会場）
    tasks = []
    for date in dates:
        for venue_code in ALL_VENUES:
            tasks.append((venue_code, date, None))

    print(f"総タスク数: {len(tasks)} (日付{len(dates)} × 会場{len(ALL_VENUES)})")
    print()

    all_results = []
    completed = 0
    total_races = 0
    saved_total = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_venue_day_parallel, task): task for task in tasks}

        for future in as_completed(futures):
            completed += 1
            venue_code, race_date, success_count, races_data = future.result()

            if success_count > 0:
                all_results.append({
                    'venue_code': venue_code,
                    'race_date': race_date,
                    'races_data': races_data
                })
                total_races += success_count

                # 50タスクごとにCSV保存（メモリ節約 & 途中保存）
                if len(all_results) >= 50:
                    saved = save_to_csv(output_dir, all_results)
                    saved_total += saved
                    all_results = []  # メモリ解放

            if completed % 50 == 0 or completed == len(tasks):
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = (len(tasks) - completed) / rate if rate > 0 else 0
                print(f"進捗: {completed}/{len(tasks)} ({completed/len(tasks)*100:.1f}%) - "
                      f"取得レース: {total_races} - 保存済: {saved_total} - 残り約{remaining/60:.1f}分")

    # 残りデータのCSV保存
    if all_results:
        print("\n=== 最終データ保存中 ===")
        saved = save_to_csv(output_dir, all_results)
        saved_total += saved

    saved = saved_total  # 合計を設定

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


if __name__ == '__main__':
    main()
