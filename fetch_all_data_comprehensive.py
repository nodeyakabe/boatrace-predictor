#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
包括的データ取得スクリプト
最終保存日から現在日までの全データ種類を取得

取得データ:
1. レース結果（公式）
2. 展示タイム（公式）
3. STタイム・進入コース（公式）
4. オリジナル展示データ（公式・Selenium）
5. 天気データ（OpenWeatherMap API）
6. 潮位データ（気象庁・Selenium）
7. 払戻金（公式）
8. 決まり手（公式）

使用方法:
  # デフォルト: DBの最終保存日から当日まで
  python fetch_all_data_comprehensive.py

  # 日付範囲を明示的に指定
  python fetch_all_data_comprehensive.py --start 2025-11-01 --end 2025-11-12

  # テストモード（DB保存なし）
  python fetch_all_data_comprehensive.py --test --limit 10

  # 並列数を変更
  python fetch_all_data_comprehensive.py --workers 5
"""

import argparse
import sys
import os
import time
import sqlite3
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from multiprocessing import Manager
from threading import Thread
import queue

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.data_manager import DataManager
from src.scraper.result_scraper_improved_v4 import ImprovedResultScraperV4
from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from src.scraper.race_scraper_v2 import RaceScraperV2
from src.scraper.schedule_scraper import ScheduleScraper
from src.scraper.original_tenji_browser import OriginalTenjiBrowserScraper
from src.scraper.tide_browser_scraper import TideBrowserScraper

# データベースパス
DB_PATH = 'data/boatrace.db'

# 会場コード
VENUE_CODES = [f"{i:02d}" for i in range(1, 25)]


def get_last_saved_date():
    """
    データベースから最終保存日を取得

    Returns:
        str: 最終保存日（YYYY-MM-DD形式）
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT MAX(race_date) FROM races')
        result = cursor.fetchone()
        conn.close()

        if result and result[0]:
            return result[0]
        else:
            # データがない場合は1週間前から
            return (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    except Exception as e:
        print(f"[警告] 最終保存日取得エラー: {e}")
        return (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')


def fetch_single_race_comprehensive(args):
    """
    1レースの全データを包括的に取得

    Args:
        args: (venue_code, date_str, race_number)

    Returns:
        dict: 取得したデータ全て
    """
    venue_code, date_str, race_number = args

    result = {
        'venue_code': venue_code,
        'date_str': date_str,
        'race_number': race_number,
        'success': False,
        'error': None,
        'data': {}
    }

    try:
        # スクレイパー初期化
        race_scraper = RaceScraperV2()
        result_scraper = ImprovedResultScraperV4()
        beforeinfo_scraper = BeforeInfoScraper(delay=0.3)

        # 並列でデータ取得
        def fetch_race_card():
            return race_scraper.get_race_card(venue_code, date_str, race_number)

        def fetch_beforeinfo():
            return beforeinfo_scraper.get_race_beforeinfo(venue_code, date_str, race_number)

        def fetch_result():
            return result_scraper.get_race_result_complete(venue_code, date_str, race_number)

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_race = executor.submit(fetch_race_card)
            future_before = executor.submit(fetch_beforeinfo)
            future_result = executor.submit(fetch_result)

            race_data = future_race.result()
            beforeinfo = future_before.result()
            complete_result = future_result.result()

        # クリーンアップ
        race_scraper.close()
        result_scraper.close()
        beforeinfo_scraper.close()

        # 出走表が空の場合はスキップ
        if not race_data or len(race_data.get('entries', [])) == 0:
            result['error'] = 'No race card'
            return result

        result['data']['race_card'] = race_data
        result['data']['beforeinfo'] = beforeinfo
        result['data']['result'] = complete_result
        result['success'] = True

    except Exception as e:
        result['error'] = str(e)

    return result


def fetch_original_tenji_for_date(target_date, test_mode=False):
    """
    指定日の全レースのオリジナル展示データを取得

    Args:
        target_date: 対象日（YYYY-MM-DD形式）
        test_mode: テストモードかどうか

    Returns:
        dict: {(venue_code, race_number): tenji_data}
    """
    results = {}
    scraper = None

    try:
        scraper = OriginalTenjiBrowserScraper(headless=True)

        for venue_code in VENUE_CODES:
            for race_num in range(1, 13):
                try:
                    data = scraper.get_original_tenji(venue_code, target_date, race_num)
                    if data and len(data) > 0:
                        results[(venue_code, race_num)] = data
                        print(f"  [オリジナル展示] {venue_code} {race_num}R: {len(data)}艇")
                except Exception:
                    # エラーは無視（データがない場合が多い）
                    pass

                time.sleep(0.3)

    finally:
        if scraper:
            scraper.close()

    return results


def fetch_tide_for_date(target_date):
    """
    指定日の潮位データを取得（海水場のみ）

    Args:
        target_date: 対象日（YYYY-MM-DD形式）

    Returns:
        dict: {venue_code: tide_data}
    """
    results = {}
    scraper = None

    # 海水場のみ
    sea_venues = ['15', '16', '17', '18', '20', '22', '24']

    try:
        scraper = TideBrowserScraper(headless=True)

        for venue_code in sea_venues:
            try:
                tide_data = scraper.get_tide_data(venue_code, target_date)
                if tide_data:
                    results[venue_code] = tide_data
                    print(f"  [潮位] {venue_code}: {len(tide_data)}件")
            except Exception as e:
                print(f"  [潮位エラー] {venue_code}: {e}")

            time.sleep(2.0)

    finally:
        if scraper:
            scraper.close()

    return results


def save_comprehensive_data(data, original_tenji_dict, tide_dict, db, test_mode=False):
    """
    包括的データをDBに保存

    Args:
        data: レースデータ
        original_tenji_dict: オリジナル展示データ辞書
        tide_dict: 潮位データ辞書
        db: DataManager インスタンス
        test_mode: テストモードかどうか

    Returns:
        bool: 保存成功ならTrue
    """
    if test_mode:
        return True

    venue_code = data['venue_code']
    date_str = data['date_str']
    race_number = data['race_number']
    content = data['data']

    try:
        # 1. 出走表保存
        race_data = content.get('race_card')
        if race_data:
            db.save_race_data(race_data)

        # レースID取得
        race_date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        race_record = db.get_race_data(venue_code, race_date_formatted, race_number)

        if not race_record:
            print(f"[ERROR] Race ID not found: {venue_code} {date_str} {race_number}R")
            return False

        race_id = race_record['id']

        # 2. 事前情報保存（展示タイム・チルト角・部品交換）
        beforeinfo = content.get('beforeinfo')
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

        # 3. オリジナル展示データ保存
        key = (venue_code, race_number)
        if key in original_tenji_dict:
            tenji_data = original_tenji_dict[key]
            # race_detailsテーブルを更新
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            for boat_num, tenji in tenji_data.items():
                cursor.execute('''
                    UPDATE race_details
                    SET chikusen_time = ?, isshu_time = ?, mawariashi_time = ?
                    WHERE race_id = ? AND pit_number = ?
                ''', (
                    tenji.get('chikusen_time'),
                    tenji.get('isshu_time'),
                    tenji.get('mawariashi_time'),
                    race_id,
                    boat_num
                ))

            conn.commit()
            conn.close()

        # 4. 結果保存（STタイム・進入コース・決まり手・払戻）
        complete_result = content.get('result')
        if complete_result and not complete_result.get('is_invalid'):
            # 決まり手を数値コードに変換
            kimarite_text = complete_result.get('kimarite')
            winning_technique = None
            if kimarite_text:
                kimarite_map = {
                    '逃げ': 1, '差し': 2, 'まくり': 3,
                    'まくり差し': 4, '抜き': 5, '恵まれ': 6
                }
                winning_technique = kimarite_map.get(kimarite_text)

            # 結果データ保存
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

            # ログ出力
            st_count = len(st_times)
            flying = [p for p, s in st_status.items() if s == 'flying']
            late = [p for p, s in st_status.items() if s == 'late']

            log_msg = f"[OK] {venue_code} {date_str} {race_number:2d}R (ST: {st_count}/6"
            if flying:
                log_msg += f", F:{flying}"
            if late:
                log_msg += f", L:{late}"
            log_msg += ")"
            print(log_msg)

            # 天気データ
            weather_data = complete_result.get('weather_data')
            if weather_data:
                race_date_obj = datetime.strptime(date_str, '%Y%m%d')
                db.save_weather_data(
                    venue_code=venue_code,
                    weather_date=race_date_obj.strftime('%Y-%m-%d'),
                    weather_data=weather_data
                )

            # 払戻金
            payouts = complete_result.get('payouts', {})
            if payouts:
                db.save_payouts(race_id, payouts)

        # 5. 潮位データ保存
        if venue_code in tide_dict:
            tide_data = tide_dict[venue_code]
            # rdmdb_tideテーブルに保存
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            for tide in tide_data:
                cursor.execute('''
                    INSERT OR REPLACE INTO rdmdb_tide
                    (venue_code, tide_date, tide_time, tide_type, tide_level)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    venue_code,
                    race_date_formatted,
                    tide['time'],
                    tide['type'],
                    tide['level']
                ))

            conn.commit()
            conn.close()

        return True

    except Exception as e:
        print(f"[ERROR] Save failed: {venue_code} {date_str} {race_number}R - {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='包括的データ取得スクリプト')
    parser.add_argument('--start', help='開始日 (YYYY-MM-DD)。未指定の場合はDB最終保存日')
    parser.add_argument('--end', help='終了日 (YYYY-MM-DD)。未指定の場合は当日')
    parser.add_argument('--workers', type=int, default=3, help='並列ワーカー数 (default: 3)')
    parser.add_argument('--test', action='store_true', help='テストモード（DB保存なし）')
    parser.add_argument('--limit', type=int, help='取得上限レース数（テスト用）')
    parser.add_argument('--skip-original-tenji', action='store_true', help='オリジナル展示データをスキップ')
    parser.add_argument('--skip-tide', action='store_true', help='潮位データをスキップ')

    args = parser.parse_args()

    # 日付範囲の決定
    if args.start:
        start_date = datetime.strptime(args.start, '%Y-%m-%d')
    else:
        # DBから最終保存日を取得
        last_date_str = get_last_saved_date()
        start_date = datetime.strptime(last_date_str, '%Y-%m-%d') + timedelta(days=1)

    if args.end:
        end_date = datetime.strptime(args.end, '%Y-%m-%d')
    else:
        end_date = datetime.now()

    print("="*80)
    print("包括的データ取得スクリプト")
    print("="*80)
    print(f"期間: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
    print(f"並列ワーカー数: {args.workers}")
    print(f"モード: {'テスト（DB保存なし）' if args.test else '本番（DB保存あり）'}")
    if args.limit:
        print(f"取得上限: {args.limit}レース")
    print()
    print("取得データ:")
    print("  - レース結果（公式）")
    print("  - 展示タイム・チルト角・部品交換（公式）")
    print("  - STタイム・進入コース（公式）")
    if not args.skip_original_tenji:
        print("  - オリジナル展示データ（公式・Selenium）")
    if not args.skip_tide:
        print("  - 潮位データ（気象庁・Selenium）")
    print("  - 天気データ（公式）")
    print("  - 払戻金（公式）")
    print("  - 決まり手（公式）")
    print("="*80)
    print()

    # 開催スケジュール取得
    print("[1] 開催スケジュール取得中...")
    schedule_scraper = ScheduleScraper()
    schedule = schedule_scraper.get_schedule_for_period(start_date, end_date)
    schedule_scraper.close()

    # タスクリスト作成
    tasks = []
    for venue_code, dates in schedule.items():
        for date_str in dates:
            for race_number in range(1, 13):
                tasks.append((venue_code, date_str, race_number))

    if args.limit:
        tasks = tasks[:args.limit]

    total_days = sum(len(dates) for dates in schedule.values())
    print(f"  開催日数: {total_days}日")
    print(f"  総タスク数: {len(tasks)}レース")
    print()

    if len(tasks) == 0:
        print("取得するデータがありません。")
        return

    start_time = time.time()
    db = DataManager()

    # 統計情報
    stats = {
        'fetched': 0,
        'saved': 0,
        'errors': 0,
        'original_tenji_dates': 0,
        'tide_dates': 0
    }

    # 日付ごとに処理（オリジナル展示・潮位データは日単位）
    processed_dates = set()
    original_tenji_all = {}
    tide_all = {}

    # [2] レースデータ取得（並列）
    print("[2] レースデータ取得開始...")
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_single_race_comprehensive, task): task for task in tasks}

        completed = 0
        for future in as_completed(futures):
            task = futures[future]
            venue_code, date_str, race_number = task

            try:
                result = future.result()
                completed += 1

                if result['success']:
                    # 日付ごとのデータ取得（初回のみ）
                    date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

                    if date_formatted not in processed_dates:
                        processed_dates.add(date_formatted)

                        # オリジナル展示データ取得
                        if not args.skip_original_tenji:
                            print(f"\n[3] オリジナル展示データ取得: {date_formatted}")
                            tenji_data = fetch_original_tenji_for_date(date_formatted, args.test)
                            original_tenji_all.update(tenji_data)
                            stats['original_tenji_dates'] += 1

                        # 潮位データ取得
                        if not args.skip_tide:
                            print(f"\n[4] 潮位データ取得: {date_formatted}")
                            tide_data = fetch_tide_for_date(date_formatted)
                            tide_all.update(tide_data)
                            stats['tide_dates'] += 1

                        print()

                    # DB保存
                    if save_comprehensive_data(result, original_tenji_all, tide_all, db, args.test):
                        stats['saved'] += 1
                    else:
                        stats['errors'] += 1

                    stats['fetched'] += 1
                else:
                    error_msg = result.get('error', 'Unknown')
                    if 'No race card' not in error_msg:
                        print(f"[SKIP] {venue_code} {date_str} {race_number:2d}R - {error_msg}")
                    stats['errors'] += 1

                # 進捗表示
                if completed % 20 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (len(tasks) - completed) / rate if rate > 0 else 0
                    print(f"\n[Progress] {completed}/{len(tasks)} ({completed/len(tasks)*100:.1f}%) - {rate:.1f}件/秒 - 残り約{remaining/60:.0f}分")
                    print(f"  取得: {stats['fetched']}件, 保存: {stats['saved']}件, エラー: {stats['errors']}件\n")

            except Exception as e:
                print(f"[ERROR] {venue_code} {date_str} {race_number:2d}R - {e}")
                completed += 1
                stats['errors'] += 1

    elapsed = time.time() - start_time

    # 結果サマリー
    print("\n" + "="*80)
    print("処理完了")
    print("="*80)
    print(f"総タスク数: {len(tasks)}レース")
    print(f"取得成功: {stats['fetched']}レース")
    print(f"保存成功: {stats['saved']}レース")
    print(f"エラー: {stats['errors']}件")
    if not args.skip_original_tenji:
        print(f"オリジナル展示: {stats['original_tenji_dates']}日分")
    if not args.skip_tide:
        print(f"潮位データ: {stats['tide_dates']}日分")
    print(f"処理時間: {elapsed/60:.1f}分")
    if len(tasks) > 0:
        print(f"成功率: {stats['saved']/len(tasks)*100:.1f}%")
    print("="*80)


if __name__ == '__main__':
    main()
