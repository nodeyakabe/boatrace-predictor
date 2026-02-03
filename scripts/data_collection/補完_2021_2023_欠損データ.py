# -*- coding: utf-8 -*-
"""2021年・2023年の欠損データ補完スクリプト（CSV方式）

背景:
- 2021年: 総レース55,728件のうち、オッズ17.0%、結果25.9%しかない（83%欠損）
- 2023年: 総レース55,980件のうち、オッズ16.2%、結果26.9%しかない（83%欠損）
- racesテーブルにはレース情報が登録済み、詳細データが未収集

このスクリプトの特徴:
1. CSV方式でDB負荷を回避
2. 月別に分割して実行（リカバリ容易）
3. 並列化で高速収集（12ワーカー推奨）
4. 50タスクごとに自動保存（障害耐性）

使用例:
    # 2021年全体を月別に収集
    python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --all-months

    # 特定月のみ収集
    python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 1

    # 2023年全体を月別に収集
    python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2023 --all-months

    # 並列数を指定
    python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 1 --workers 12
"""

import sys
import os
import csv
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
from calendar import monthrange

# Windows文字コード対策
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.scraper.race_scraper_v2 import RaceScraperV2
from src.scraper.result_scraper import ResultScraper
from src.scraper.odds_scraper import OddsScraper

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
        thread_local.odds_scraper = OddsScraper()
    return thread_local.race_scraper, thread_local.result_scraper, thread_local.odds_scraper


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


def check_missing_data(db_path: Path, year: int, month: int = None):
    """
    欠損データを確認

    Returns:
        dict: {
            'total_races': 総レース数,
            'missing_entries': エントリー欠損レース数,
            'missing_results': 結果欠損レース数,
            'missing_odds': オッズ欠損レース数,
            'missing_payouts': 払戻欠損レース数
        }
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 対象期間
    if month:
        date_pattern = f'{year}-{month:02d}%'
        period_str = f'{year}年{month}月'
    else:
        date_pattern = f'{year}%'
        period_str = f'{year}年全体'

    # 総レース数
    cursor.execute('SELECT COUNT(*) FROM races WHERE race_date LIKE ?', (date_pattern,))
    total_races = cursor.fetchone()[0]

    # エントリー欠損
    cursor.execute('''
        SELECT COUNT(*)
        FROM races r
        LEFT JOIN entries e ON r.id = e.race_id
        WHERE r.race_date LIKE ? AND e.race_id IS NULL
    ''', (date_pattern,))
    missing_entries = cursor.fetchone()[0]

    # 結果欠損
    cursor.execute('''
        SELECT COUNT(*)
        FROM races r
        LEFT JOIN results res ON r.id = res.race_id
        WHERE r.race_date LIKE ? AND res.race_id IS NULL
    ''', (date_pattern,))
    missing_results = cursor.fetchone()[0]

    # オッズ欠損
    cursor.execute('''
        SELECT COUNT(*)
        FROM races r
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
        WHERE r.race_date LIKE ? AND t.race_id IS NULL
    ''', (date_pattern,))
    missing_odds = cursor.fetchone()[0]

    # 払戻欠損
    cursor.execute('''
        SELECT COUNT(*)
        FROM races r
        LEFT JOIN payouts p ON r.id = p.race_id
        WHERE r.race_date LIKE ? AND p.race_id IS NULL
    ''', (date_pattern,))
    missing_payouts = cursor.fetchone()[0]

    conn.close()

    return {
        'period': period_str,
        'total_races': total_races,
        'missing_entries': missing_entries,
        'missing_results': missing_results,
        'missing_odds': missing_odds,
        'missing_payouts': missing_payouts
    }


def fetch_venue_day_parallel(args):
    """1会場1日分のデータを取得（並列用）"""
    venue_code, race_date, _ = args

    race_scraper, result_scraper, odds_scraper = get_scrapers()

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

                # 結果取得
                result_data = result_scraper.get_race_result(venue_code, race_date_yyyymmdd, race_number)

                # 過去レースで結果が不完全な場合は警告
                if result_data and result_data.get('results'):
                    result_count = len(result_data['results'])
                    if result_count < 6:
                        incomplete_results.append(
                            f"{venue_code} {race_date_yyyymmdd} R{race_number} (取得: {result_count}/6艇)"
                        )

                # オッズ取得
                odds_data = None
                try:
                    odds_data = odds_scraper.get_trifecta_odds(venue_code, race_date_yyyymmdd, race_number)
                except Exception as e:
                    # オッズが取得できない場合もあるのでスキップ
                    pass

                races_data.append({
                    'race': race_data,
                    'result': result_data,
                    'odds': odds_data
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
    - trifecta_odds.csv: 3連単オッズ
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # CSVファイルパス
    races_csv = output_dir / 'races.csv'
    entries_csv = output_dir / 'entries.csv'
    conditions_csv = output_dir / 'race_conditions.csv'
    details_csv = output_dir / 'race_details.csv'
    results_csv = output_dir / 'results.csv'
    payouts_csv = output_dir / 'payouts.csv'
    odds_csv = output_dir / 'trifecta_odds.csv'

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
    odds_header = ['venue_code', 'race_date', 'race_number', 'combination', 'odds']

    # ファイルが存在しない場合のみヘッダーを書き込む
    write_headers = {
        races_csv: not races_csv.exists(),
        entries_csv: not entries_csv.exists(),
        conditions_csv: not conditions_csv.exists(),
        details_csv: not details_csv.exists(),
        results_csv: not results_csv.exists(),
        payouts_csv: not payouts_csv.exists(),
        odds_csv: not odds_csv.exists(),
    }

    # CSVファイルを開く（追記モード）
    with open(races_csv, 'a', newline='', encoding='utf-8') as f_races, \
         open(entries_csv, 'a', newline='', encoding='utf-8') as f_entries, \
         open(conditions_csv, 'a', newline='', encoding='utf-8') as f_conditions, \
         open(details_csv, 'a', newline='', encoding='utf-8') as f_details, \
         open(results_csv, 'a', newline='', encoding='utf-8') as f_results, \
         open(payouts_csv, 'a', newline='', encoding='utf-8') as f_payouts, \
         open(odds_csv, 'a', newline='', encoding='utf-8') as f_odds:

        writer_races = csv.DictWriter(f_races, fieldnames=races_header)
        writer_entries = csv.DictWriter(f_entries, fieldnames=entries_header)
        writer_conditions = csv.DictWriter(f_conditions, fieldnames=conditions_header)
        writer_details = csv.DictWriter(f_details, fieldnames=details_header)
        writer_results = csv.DictWriter(f_results, fieldnames=results_header)
        writer_payouts = csv.DictWriter(f_payouts, fieldnames=payouts_header)
        writer_odds = csv.DictWriter(f_odds, fieldnames=odds_header)

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
        if write_headers[odds_csv]:
            writer_odds.writeheader()

        saved_count = 0

        for item in all_races_data:
            venue_code = item['venue_code']
            race_date = item['race_date']
            races_data = item['races_data']

            for race_item in races_data:
                try:
                    race_data = race_item['race']
                    result_data = race_item['result']
                    odds_data = race_item.get('odds')

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

                    # オッズデータ
                    if odds_data and odds_data.get('odds'):
                        for combination, odds_value in odds_data['odds'].items():
                            odds_row = {
                                'venue_code': venue_code,
                                'race_date': race_date,
                                'race_number': race_data.get('race_number'),
                                'combination': combination,
                                'odds': odds_value,
                            }
                            writer_odds.writerow(odds_row)

                    saved_count += 1

                except Exception as e:
                    print(f"CSV保存エラー: {e}")
                    import traceback
                    traceback.print_exc()

    return saved_count


def main():
    parser = argparse.ArgumentParser(description='2021年・2023年欠損データ補完（CSV方式）')
    parser.add_argument('--year', type=int, required=True, choices=[2021, 2023], help='対象年（2021 or 2023）')
    parser.add_argument('--month', type=int, choices=range(1, 13), help='対象月（1-12）省略時は確認のみ')
    parser.add_argument('--all-months', action='store_true', help='全月を順次実行')
    parser.add_argument('--workers', type=int, default=12, help='並列数（デフォルト: 12）')
    parser.add_argument('--output-base', type=str, default='data/csv/補完', help='CSV出力ベースディレクトリ')
    args = parser.parse_args()

    db_path = ROOT_DIR / 'data' / 'boatrace.db'

    print("=" * 80)
    print(f"{args.year}年欠損データ補完スクリプト（CSV方式）")
    print("=" * 80)
    print()

    # 欠損データ確認
    print(f"=== {args.year}年のデータ状況確認 ===")
    year_stats = check_missing_data(db_path, args.year)
    print(f"  総レース数: {year_stats['total_races']:,}")
    print(f"  エントリー欠損: {year_stats['missing_entries']:,} ({year_stats['missing_entries']/year_stats['total_races']*100:.1f}%)")
    print(f"  結果欠損: {year_stats['missing_results']:,} ({year_stats['missing_results']/year_stats['total_races']*100:.1f}%)")
    print(f"  オッズ欠損: {year_stats['missing_odds']:,} ({year_stats['missing_odds']/year_stats['total_races']*100:.1f}%)")
    print(f"  払戻欠損: {year_stats['missing_payouts']:,} ({year_stats['missing_payouts']/year_stats['total_races']*100:.1f}%)")
    print()

    # 月別確認
    print("=== 月別欠損状況 ===")
    for month in range(1, 13):
        month_stats = check_missing_data(db_path, args.year, month)
        if month_stats['total_races'] > 0:
            print(f"{month:2d}月: 総{month_stats['total_races']:4d}レース | "
                  f"エントリー欠{month_stats['missing_entries']:4d} | "
                  f"結果欠{month_stats['missing_results']:4d} | "
                  f"オッズ欠{month_stats['missing_odds']:4d}")
    print()

    if not args.month and not args.all_months:
        print("特定月を収集する場合: --month N を指定")
        print("全月を収集する場合: --all-months を指定")
        return

    # 実行対象月の決定
    target_months = []
    if args.all_months:
        target_months = list(range(1, 13))
    elif args.month:
        target_months = [args.month]

    # 月別に収集
    for month in target_months:
        # 月の最終日を取得
        last_day = monthrange(args.year, month)[1]
        start_date = f'{args.year}-{month:02d}-01'
        end_date = f'{args.year}-{month:02d}-{last_day:02d}'

        output_dir = Path(args.output_base) / str(args.year) / f'{month:02d}'

        print("=" * 80)
        print(f"{args.year}年{month}月のデータ収集")
        print("=" * 80)
        print(f"期間: {start_date} - {end_date}")
        print(f"出力先: {output_dir}")
        print(f"並列数: {args.workers}スレッド")
        print()

        dates = get_date_range(start_date, end_date)

        # タスク作成
        tasks = []
        for date in dates:
            for venue_code in ALL_VENUES:
                tasks.append((venue_code, date, db_path))

        print(f"総タスク数: {len(tasks)} ({len(dates)}日 × {len(ALL_VENUES)}会場)")
        print(f"予想時間: 約{len(dates) * 0.5 / 60:.1f}-{len(dates) * 1 / 60:.1f}時間")
        print()

        # 並列取得開始
        print("=== データ取得開始 ===")
        start_time = time.time()

        all_results = []
        completed = 0
        total_races = 0
        all_incomplete_results = []
        batch_size = 50

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

                # 50タスクごとに自動保存
                if len(all_results) >= batch_size:
                    save_to_csv(output_dir, all_results)
                    all_results = []  # メモリ解放

                # 進捗表示
                if completed % 50 == 0 or completed == len(tasks):
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (len(tasks) - completed) / rate if rate > 0 else 0
                    print(f"進捗: {completed}/{len(tasks)} ({completed/len(tasks)*100:.1f}%) - "
                          f"取得レース: {total_races} - 残り約{remaining/60:.1f}分")

        # 残りのデータを保存
        if all_results:
            print("\n=== 最終CSV保存中 ===")
            save_to_csv(output_dir, all_results)

        elapsed = time.time() - start_time

        print()
        print("=" * 80)
        print(f"{args.year}年{month}月 収集完了")
        print("=" * 80)
        print(f"取得レース数: {total_races}")
        print(f"所要時間: {elapsed/60:.1f}分")
        print(f"速度: {len(dates) / (elapsed/60):.1f}日/分")
        print(f"出力先: {output_dir.absolute()}")
        print()

        # 不完全な結果の警告
        if all_incomplete_results:
            print("⚠️ 警告: 不完全な結果が検出されました")
            print(f"該当レース数: {len(all_incomplete_results)}")
            print("\n最初の10件:")
            for i, msg in enumerate(all_incomplete_results[:10], 1):
                print(f"  {i}. {msg}")
            if len(all_incomplete_results) > 10:
                print(f"  ... 他{len(all_incomplete_results) - 10}件")
            print()

    # 全完了メッセージ
    print("=" * 80)
    print("全ての月の収集が完了しました")
    print("=" * 80)
    print("\n次のステップ:")
    print(f"1. データ投入: python scripts/maintenance/投入_2021_2023_補完データ.py --year {args.year}")
    print()


if __name__ == '__main__':
    main()
