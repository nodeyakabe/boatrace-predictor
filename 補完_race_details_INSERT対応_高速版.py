#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
race_details初期データ作成スクリプト（INSERT対応・高速版）

並列処理で高速化:
- ThreadPoolExecutorで6スレッド並列実行
- delayを0.2秒に短縮
- バッチコミットで高速化

実行方法:
  python 補完_race_details_INSERT対応_高速版.py 2025-11-17 2025-11-17
"""
import sys
sys.path.append('src')

import sqlite3
from datetime import datetime
from scraper.beforeinfo_scraper import BeforeInfoScraper
from tqdm import tqdm
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import threading

# スレッドローカルストレージ
thread_local = threading.local()

def get_scraper():
    """スレッドごとのスクレイパーを取得"""
    if not hasattr(thread_local, "scraper"):
        thread_local.scraper = BeforeInfoScraper(delay=0.2)
    return thread_local.scraper

# グローバルカウンター
success_count = 0
partial_count = 0
error_count = 0
skip_count = 0
counter_lock = Lock()

def process_race(race_info):
    """1レースを処理"""
    global success_count, partial_count, error_count, skip_count

    race_id, venue_code, race_date, race_number = race_info
    date_str = race_date.replace('-', '')

    try:
        scraper = get_scraper()
        beforeinfo = scraper.get_race_beforeinfo(venue_code, date_str, race_number)

        if not beforeinfo:
            with counter_lock:
                skip_count += 1
            return None

        exhibition_times = beforeinfo.get('exhibition_times', {})
        tilt_angles = beforeinfo.get('tilt_angles', {})
        parts_replacements = beforeinfo.get('parts_replacements', {})

        # 6艇分のデータを準備
        details = []
        for pit_number in range(1, 7):
            ex_time = exhibition_times.get(pit_number)
            tilt = tilt_angles.get(pit_number)
            parts = parts_replacements.get(pit_number)

            details.append((race_id, pit_number, ex_time, tilt, parts))

        # カウント更新
        with counter_lock:
            if exhibition_times or tilt_angles or parts_replacements:
                success_count += 1
            else:
                partial_count += 1

        return details

    except Exception as e:
        with counter_lock:
            error_count += 1
        return None

def main():
    global success_count, partial_count, error_count, skip_count

    if len(sys.argv) < 3:
        print("使用方法: python 補完_race_details_INSERT対応_高速版.py [開始日] [終了日]")
        print("例: python 補完_race_details_INSERT対応_高速版.py 2025-11-17 2025-11-17")
        sys.exit(1)

    start_date_str = sys.argv[1]
    end_date_str = sys.argv[2]

    print("="*80)
    print("race_details初期データ作成（INSERT対応・高速版）")
    print("="*80)
    print(f"対象期間: {start_date_str} ～ {end_date_str}")
    print(f"並列スレッド数: 6")
    print()

    # DBから対象レースを取得
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date BETWEEN ? AND ?
        AND NOT EXISTS (
            SELECT 1 FROM race_details rd
            WHERE rd.race_id = r.id
        )
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, (start_date_str, end_date_str))

    races = cursor.fetchall()

    print(f"race_detailsが未登録のレース数: {len(races)}件\n")

    if len(races) == 0:
        print("対象レースがありません")
        conn.close()
        sys.exit(0)

    print(f"{len(races)}件のrace_detailsレコードを作成します...\n")

    # 並列処理
    start_time = time.time()
    all_details = []

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(process_race, race): race for race in races}

        for future in tqdm(as_completed(futures), total=len(races), desc="race_details作成"):
            result = future.result()
            if result:
                all_details.extend(result)

    # 一括INSERT（重複時はスキップ）
    print("\nデータベースに保存中...")
    cursor.executemany("""
        INSERT OR IGNORE INTO race_details (
            race_id, pit_number,
            exhibition_time, tilt_angle, parts_replacement
        ) VALUES (?, ?, ?, ?, ?)
    """, all_details)

    conn.commit()

    elapsed = time.time() - start_time

    print("\n" + "="*80)
    print("作成完了")
    print("="*80)
    print(f"処理時間: {elapsed:.1f}秒 ({elapsed/60:.1f}分)")
    print(f"平均速度: {elapsed/len(races):.2f}秒/レース")
    print(f"\n成功（データあり）: {success_count}レース")
    print(f"レコード作成のみ: {partial_count}レース")
    print(f"スキップ: {skip_count}レース")
    print(f"エラー: {error_count}レース")

    # 確認
    cursor.execute("""
        SELECT COUNT(*) FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date BETWEEN ? AND ?
    """, (start_date_str, end_date_str))
    total_details = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            COUNT(CASE WHEN exhibition_time IS NOT NULL THEN 1 END) as ex_count,
            COUNT(CASE WHEN tilt_angle IS NOT NULL THEN 1 END) as tilt_count,
            COUNT(CASE WHEN parts_replacement IS NOT NULL THEN 1 END) as parts_count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date BETWEEN ? AND ?
    """, (start_date_str, end_date_str))
    ex_count, tilt_count, parts_count = cursor.fetchone()

    print(f"\n【登録データ確認】")
    print(f"  race_detailsレコード: {total_details}件")
    if total_details > 0:
        print(f"  展示タイムあり: {ex_count}件 ({ex_count/total_details*100:.1f}%)")
        print(f"  チルト角度あり: {tilt_count}件 ({tilt_count/total_details*100:.1f}%)")
        print(f"  部品交換あり: {parts_count}件 ({parts_count/total_details*100:.1f}%)")

    conn.close()
    print("\n" + "="*80)


if __name__ == "__main__":
    main()
