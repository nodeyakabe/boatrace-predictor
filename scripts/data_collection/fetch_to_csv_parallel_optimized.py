# -*- coding: utf-8 -*-
"""過去データをCSVファイルに保存（最適化版・DB負荷なし）

最適化版の高速化 + CSV出力の安全性:
- 10-15倍高速化（会場単位で並列取得）
- 1日あたり約30秒-1分（従来: 5-7分）
- 50タスクごとにCSV保存（途中で止まってもデータ保護）
- DBロックなし（他の作業と並行可能）

使用例:
    # 特定期間のデータをCSV出力
    python scripts/data_collection/fetch_to_csv_parallel_optimized.py \
      --start 2020-09-01 --end 2021-12-31 \
      --output data/csv/2020_09_to_2021_12 \
      --workers 12

予想時間:
    - 1ヶ月（30日）: 約15-30分
    - 1年（365日）: 約3-6時間
    - 16ヶ月（487日）: 約4-8時間
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

# 全24競艇場コード
ALL_VENUES = [
    '01', '02', '03', '04', '05', '06', '07', '08', '09', '10',
    '11', '12', '13', '14', '15', '16', '17', '18', '19', '20',
    '21', '22', '23', '24'
]

VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川',
    '06': '浜名湖', '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国',
    '11': 'びわこ', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀',
    '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}

# スレッドローカルストレージ（各スレッドでスクレイパーを保持）
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

                time.sleep(0.1)  # レート制限（並列なので短め）
                break  # 成功したらリトライループを抜ける

            except Exception as e:
                if retry < max_retries - 1:
                    time.sleep(2 ** retry)  # 指数バックオフ: 1秒, 2秒, 4秒
                # 最終リトライでも失敗したらパス

    return venue_code, race_date, success_count, races_data


def save_to_csv(output_dir: Path, all_races_data: list):
    """レースデータをCSVに保存（50タスクごとに呼ばれる）"""
    output_dir.mkdir(parents=True, exist_ok=True)

    # CSVファイルパス
    csv_files = {
        'races': output_dir / 'races.csv',
        'entries': output_dir / 'entries.csv',
        'results': output_dir / 'results.csv',
        'race_conditions': output_dir / 'race_conditions.csv',
        'race_details': output_dir / 'race_details.csv',
        'payouts': output_dir / 'payouts.csv'
    }

    # ファイルが存在しない場合はヘッダーを書き込む
    file_exists = {k: v.exists() for k, v in csv_files.items()}

    saved_count = 0

    # 各CSVファイルを追記モードで開く
    with open(csv_files['races'], 'a', newline='', encoding='utf-8') as f_races, \
         open(csv_files['entries'], 'a', newline='', encoding='utf-8') as f_entries, \
         open(csv_files['results'], 'a', newline='', encoding='utf-8') as f_results, \
         open(csv_files['race_conditions'], 'a', newline='', encoding='utf-8') as f_conditions, \
         open(csv_files['race_details'], 'a', newline='', encoding='utf-8') as f_details, \
         open(csv_files['payouts'], 'a', newline='', encoding='utf-8') as f_payouts:

        writer_races = csv.writer(f_races)
        writer_entries = csv.writer(f_entries)
        writer_results = csv.writer(f_results)
        writer_conditions = csv.writer(f_conditions)
        writer_details = csv.writer(f_details)
        writer_payouts = csv.writer(f_payouts)

        # ヘッダー書き込み（初回のみ）
        if not file_exists['races']:
            writer_races.writerow(['venue_code', 'race_date', 'race_number', 'race_time', 'race_grade',
                                  'race_distance', 'is_nighter', 'is_ladies', 'is_rookie', 'is_shinnyuu_kotei'])

        if not file_exists['entries']:
            writer_entries.writerow(['venue_code', 'race_date', 'race_number', 'pit_number', 'racer_number',
                                    'racer_name', 'racer_rank', 'racer_home', 'racer_age', 'racer_weight',
                                    'motor_number', 'boat_number', 'win_rate', 'second_rate', 'third_rate',
                                    'f_count', 'l_count', 'avg_st', 'local_win_rate', 'local_second_rate',
                                    'local_third_rate', 'motor_second_rate', 'motor_third_rate',
                                    'boat_second_rate', 'boat_third_rate'])

        if not file_exists['results']:
            writer_results.writerow(['venue_code', 'race_date', 'race_number', 'pit_number', 'rank',
                                    'is_invalid', 'kimarite'])

        if not file_exists['race_conditions']:
            writer_conditions.writerow(['venue_code', 'race_date', 'race_number', 'weather', 'wind_direction',
                                       'wind_speed', 'wave_height', 'water_temp', 'air_temp'])

        if not file_exists['race_details']:
            writer_details.writerow(['venue_code', 'race_date', 'race_number', 'pit_number', 'exhibition_time',
                                    'tilt_angle'])

        if not file_exists['payouts']:
            writer_payouts.writerow(['venue_code', 'race_date', 'race_number', 'bet_type', 'combination', 'payout'])

        # データ書き込み
        for item in all_races_data:
            venue_code = item['venue_code']
            race_date = item['race_date']
            races_data = item['races_data']

            for race_item in races_data:
                race_data = race_item['race']
                result_data = race_item['result']

                # レース基本情報
                writer_races.writerow([
                    venue_code,
                    race_data['race_date'],
                    race_data['race_number'],
                    race_data.get('race_time', ''),
                    race_data.get('race_grade', ''),
                    race_data.get('race_distance', 0),
                    1 if race_data.get('is_nighter') else 0,
                    1 if race_data.get('is_ladies') else 0,
                    1 if race_data.get('is_rookie') else 0,
                    1 if race_data.get('is_shinnyuu_kotei') else 0
                ])

                # 出走表
                for entry in race_data.get('entries', []):
                    writer_entries.writerow([
                        venue_code,
                        race_data['race_date'],
                        race_data['race_number'],
                        entry.get('pit_number', 0),
                        entry.get('racer_number', 0),
                        entry.get('racer_name', ''),
                        entry.get('racer_rank', ''),
                        entry.get('racer_home', ''),
                        entry.get('racer_age', 0),
                        entry.get('racer_weight', 0.0),
                        entry.get('motor_number', 0),
                        entry.get('boat_number', 0),
                        entry.get('win_rate', 0.0),
                        entry.get('second_rate', 0.0),
                        entry.get('third_rate', 0.0),
                        entry.get('f_count', 0),
                        entry.get('l_count', 0),
                        entry.get('avg_st', 0.0),
                        entry.get('local_win_rate', 0.0),
                        entry.get('local_second_rate', 0.0),
                        entry.get('local_third_rate', 0.0),
                        entry.get('motor_second_rate', 0.0),
                        entry.get('motor_third_rate', 0.0),
                        entry.get('boat_second_rate', 0.0),
                        entry.get('boat_third_rate', 0.0)
                    ])

                # 結果
                if result_data:
                    for pit_result in result_data.get('results', []):
                        writer_results.writerow([
                            venue_code,
                            race_data['race_date'],
                            race_data['race_number'],
                            pit_result.get('pit_number', 0),
                            pit_result.get('rank', 0),
                            1 if pit_result.get('is_invalid') else 0,
                            pit_result.get('kimarite', '')
                        ])

                    # レース条件
                    conditions = result_data.get('conditions', {})
                    if conditions:
                        writer_conditions.writerow([
                            venue_code,
                            race_data['race_date'],
                            race_data['race_number'],
                            conditions.get('weather', ''),
                            conditions.get('wind_direction', ''),
                            conditions.get('wind_speed', 0.0),
                            conditions.get('wave_height', 0),
                            conditions.get('water_temp', 0.0),
                            conditions.get('air_temp', 0.0)
                        ])

                    # 展示情報
                    for detail in result_data.get('details', []):
                        writer_details.writerow([
                            venue_code,
                            race_data['race_date'],
                            race_data['race_number'],
                            detail.get('pit_number', 0),
                            detail.get('exhibition_time', 0.0),
                            detail.get('tilt_angle', 0.0)
                        ])

                    # 払戻金
                    for payout in result_data.get('payouts', []):
                        writer_payouts.writerow([
                            venue_code,
                            race_data['race_date'],
                            race_data['race_number'],
                            payout.get('bet_type', ''),
                            payout.get('combination', ''),
                            payout.get('payout', 0)
                        ])

                    saved_count += 1

    return saved_count


def main():
    parser = argparse.ArgumentParser(description='過去データCSV保存（最適化版・DB負荷なし）')
    parser.add_argument('--start', type=str, required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--output', type=str, required=True, help='CSV出力ディレクトリ')
    parser.add_argument('--workers', type=int, default=10, help='並列数（デフォルト: 10）')
    args = parser.parse_args()

    output_dir = Path(args.output)
    dates = get_date_range(args.start, args.end)

    print("=" * 70)
    print("過去データCSV保存（最適化版・DB負荷なし）")
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

    elapsed = time.time() - start_time

    print()
    print("=" * 70)
    print("処理完了")
    print("=" * 70)
    print(f"取得レース数: {total_races}")
    print(f"保存レース数: {saved_total}")
    print(f"所要時間: {elapsed/60:.1f}分")
    print(f"速度: {len(dates) / (elapsed/60):.1f}日/分")
    print(f"\nCSVファイル: {output_dir}")


if __name__ == '__main__':
    main()
