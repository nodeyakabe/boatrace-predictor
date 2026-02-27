# -*- coding: utf-8 -*-
"""過去データ一括取得スクリプト（並列化版）

並列化により10-15倍高速化:
- 会場単位で並列取得（8-12スレッド）
- 1日あたり約30秒-1分（従来: 5-7分）

使用例:
    # 特定期間のデータ取得
    python scripts/data_collection/fetch_historical_data_parallel.py --start 2022-08-01 --end 2022-12-31

    # 並列数を指定
    python scripts/data_collection/fetch_historical_data_parallel.py --start 2020-01-01 --end 2020-12-31 --workers 12
"""

import sys
import os
import sqlite3
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


def get_schedule_for_period(start_date: str, end_date: str):
    """
    期間内の開催スケジュールを取得

    Returns:
        dict: {
            '20260104': ['01', '02', '03', ...],  # その日に開催している会場リスト
            '20260105': ['01', '04', '05', ...],
            ...
        }
        または None (失敗時のフォールバック用)
    """
    try:
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

    except Exception as e:
        print(f"⚠️ 開催スケジュール取得エラー: {e}")
        print("   → フォールバックモードで全会場を対象とします")
        return None  # フォールバック用


def check_existing_data(db_path: Path, race_date: str):
    """指定日の既存データを確認"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM races WHERE race_date = ?', (race_date,))
    race_count = cursor.fetchone()[0]

    cursor.execute('''
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        INNER JOIN results res ON r.id = res.race_id
        WHERE r.race_date = ?
    ''', (race_date,))
    result_count = cursor.fetchone()[0]

    conn.close()
    return race_count, result_count


def fetch_venue_day_parallel(args):
    """1会場1日分のデータを取得（並列用）"""
    venue_code, race_date, db_path = args

    race_scraper, result_scraper = get_scrapers()

    race_date_yyyymmdd = race_date.replace('-', '')
    success_count = 0
    races_data = []
    incomplete_results = []  # 不完全結果の追跡

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

                # 結果取得（payouts/actual_courses/st_times/kimarite含む完全版）
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

                time.sleep(0.1)  # レート制限（並列なので短め）
                break  # 成功したらリトライループを抜ける

            except Exception as e:
                if retry < max_retries - 1:
                    time.sleep(2 ** retry)  # 指数バックオフ: 1秒, 2秒, 4秒
                # 最終リトライでも失敗したらパス

    return venue_code, race_date, success_count, races_data, incomplete_results


def save_races_batch(db_path: Path, all_races_data: list):
    """取得したレースデータを一括保存"""
    from src.database.fast_data_manager import FastDataManager

    data_manager = FastDataManager(str(db_path))
    saved_count = 0

    try:
        # トランザクション開始（重要：これがないとコミットされない）
        data_manager.begin_batch()

        for item in all_races_data:
            venue_code = item['venue_code']
            race_date = item['race_date']
            races_data = item['races_data']

            for race_item in races_data:
                try:
                    race_data = race_item['race']
                    result_data = race_item['result']

                    race_id = data_manager.save_race_data_fast(race_data)

                    if race_id and result_data:
                        result_data['venue_code'] = venue_code
                        result_data['race_date'] = race_date.replace('-', '')
                        result_data['race_number'] = race_data['race_number']
                        data_manager.save_race_result_fast(result_data)

                        # payouts保存（get_race_result_complete()で取得済み）
                        if result_data.get('payouts'):
                            data_manager.save_payouts_batch(race_id, result_data['payouts'])

                        # actual_course/st_time保存（キーはint型）
                        actual_courses = result_data.get('actual_courses', {})
                        st_times = result_data.get('st_times', {})
                        if actual_courses:
                            data_manager.upsert_actual_courses_batch(race_id, actual_courses, st_times)

                        # kimarite保存（races.kimariteカラム）
                        if result_data.get('kimarite'):
                            data_manager.update_kimarite(race_id, result_data['kimarite'])

                        saved_count += 1

                except Exception as e:
                    print(f"レース保存エラー [{race_date} venue={venue_code}]: {e}")

        # トランザクションコミット
        data_manager.commit_batch()

    except Exception as e:
        print(f"バッチ保存エラー: {e}")
        try:
            data_manager.rollback_batch()
        except:
            pass
        raise

    finally:
        # リソース解放
        try:
            data_manager.close()
        except:
            pass

    return saved_count


def main():
    parser = argparse.ArgumentParser(description='過去データ一括取得（並列化版）')
    parser.add_argument('--start', type=str, required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--workers', type=int, default=10, help='並列数（デフォルト: 10）')
    parser.add_argument('--skip-existing', action='store_true', help='既存データがある日はスキップ')
    parser.add_argument('--check-only', action='store_true', help='不足データの確認のみ')
    args = parser.parse_args()

    db_path = ROOT_DIR / 'data' / 'boatrace.db'
    dates = get_date_range(args.start, args.end)

    print("=" * 70)
    print("過去データ一括取得（並列化版）")
    print("=" * 70)
    print(f"期間: {args.start} - {args.end} ({len(dates)}日間)")
    print(f"並列数: {args.workers}スレッド")
    print(f"予想時間: 約{len(dates) * 0.5 / 60:.1f}-{len(dates) * 1 / 60:.1f}時間")
    print()

    # 既存データ確認
    print("=== 既存データ確認 ===")
    missing_dates = []
    for date in dates:
        race_count, result_count = check_existing_data(db_path, date)
        if race_count == 0:
            missing_dates.append(date)
            print(f"  {date}: データなし [要取得]")
        elif result_count < race_count:
            missing_dates.append(date)
            print(f"  {date}: {race_count}レース, 結果{result_count}件 [結果不足]")
        elif args.skip_existing:
            pass  # スキップ
        else:
            missing_dates.append(date)  # 再取得対象

    print(f"\n取得対象: {len(missing_dates)}日")

    if args.check_only:
        return

    if not missing_dates:
        print("取得対象データがありません。")
        return

    # 並列取得開始
    print("\n=== データ取得開始 ===")
    start_time = time.time()

    # 開催スケジュール取得（改善版）
    date_schedule = get_schedule_for_period(args.start, args.end)

    # タスク作成
    tasks = []
    if date_schedule:
        # スケジュール取得成功: 開催日のみ
        for date in missing_dates:
            date_yyyymmdd = date.replace('-', '')
            venue_codes = date_schedule.get(date_yyyymmdd, [])
            for venue_code in venue_codes:
                tasks.append((venue_code, date, db_path))

        total_possible_tasks = len(missing_dates) * len(ALL_VENUES)
        reduction_rate = (1 - len(tasks) / total_possible_tasks) * 100 if total_possible_tasks > 0 else 0

        print(f"総タスク数: {len(tasks)} (開催日のみ)")
        print(f"  従来方式: {total_possible_tasks}タスク (全日×全会場)")
        print(f"  改善版: {len(tasks)}タスク (開催日のみ)")
        print(f"  削減率: {reduction_rate:.1f}%")
    else:
        # フォールバック: 全会場対象（従来方式）
        print("⚠️ 開催スケジュール取得失敗 → 従来方式（全会場）で実行")
        for date in missing_dates:
            for venue_code in ALL_VENUES:
                tasks.append((venue_code, date, db_path))
        print(f"総タスク数: {len(tasks)} (日付{len(missing_dates)} × 会場{len(ALL_VENUES)})")

    print()

    all_results = []
    all_incomplete_results = []  # 不完全結果の追跡
    completed = 0
    total_races = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_venue_day_parallel, task): task for task in tasks}

        for future in as_completed(futures):
            completed += 1
            venue_code, race_date, success_count, races_data, incomplete_results = future.result()

            if success_count > 0:
                all_results.append({
                    'venue_code': venue_code,
                    'race_date': race_date,
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

    # 一括保存
    print("\n=== データ保存中 ===")
    saved = save_races_batch(db_path, all_results)

    elapsed = time.time() - start_time

    print()
    print("=" * 70)
    print("処理完了")
    print("=" * 70)
    print(f"取得レース数: {total_races}")
    print(f"保存レース数: {saved}")
    print(f"所要時間: {elapsed/60:.1f}分")
    print(f"速度: {len(missing_dates) / (elapsed/60):.1f}日/分")

    # 最終確認
    print("\n=== 最終データ確認 ===")
    for date in missing_dates[:5]:  # 最初の5日分だけ表示
        race_count, result_count = check_existing_data(db_path, date)
        status = "[OK]" if result_count > 0 else "[NG]"
        print(f"  {date}: {race_count}レース, 結果{result_count}件 {status}")
    if len(missing_dates) > 5:
        print(f"  ... 他{len(missing_dates)-5}日")

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
