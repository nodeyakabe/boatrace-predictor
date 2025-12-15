#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2024年の不足データ（展示タイム・払戻金）を収集
"""
import sys
import os

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ['PYTHONUNBUFFERED'] = '1'

import time
import sqlite3
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from src.scraper.result_scraper import ResultScraper


def get_races_missing_exhibition(db_path):
    """展示タイムが欠けている2024年レースを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
        AND NOT EXISTS (
            SELECT 1 FROM race_details rd
            WHERE rd.race_id = r.id AND rd.exhibition_time IS NOT NULL
        )
        ORDER BY r.race_date, r.venue_code, r.race_number
    """)
    races = cursor.fetchall()
    conn.close()
    return races


def get_races_missing_payouts(db_path):
    """払戻金が欠けている2024年レースを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
        AND NOT EXISTS (SELECT 1 FROM payouts p WHERE p.race_id = r.id)
        ORDER BY r.race_date, r.venue_code, r.race_number
    """)
    races = cursor.fetchall()
    conn.close()
    return races


def collect_exhibition(args):
    """展示タイムを収集"""
    race_id, venue_code, race_date, race_number, db_path = args

    scraper = BeforeInfoScraper(delay=0.3)

    try:
        date_str = race_date.replace('-', '')
        beforeinfo = scraper.get_race_beforeinfo(
            venue_code=f"{int(venue_code):02d}",
            date_str=date_str,
            race_number=race_number
        )

        if beforeinfo and beforeinfo.get('is_published'):
            conn = sqlite3.connect(db_path, timeout=30.0)
            cursor = conn.cursor()

            exhibition_times = beforeinfo.get('exhibition_times', {})
            tilt_angles = beforeinfo.get('tilt_angles', {})
            st_times = beforeinfo.get('start_timings', {})

            for pit in range(1, 7):
                cursor.execute('''
                    UPDATE race_details
                    SET exhibition_time = COALESCE(?, exhibition_time),
                        tilt_angle = COALESCE(?, tilt_angle),
                        st_time = COALESCE(?, st_time)
                    WHERE race_id = ? AND pit_number = ?
                ''', (
                    exhibition_times.get(pit),
                    tilt_angles.get(pit),
                    st_times.get(pit),
                    race_id, pit
                ))

            conn.commit()
            conn.close()
            return True
    except:
        pass
    return False


def collect_payout(args):
    """払戻金を収集"""
    race_id, venue_code, race_date, race_number, db_path = args

    scraper = ResultScraper()

    try:
        date_str = race_date.replace('-', '')
        result = scraper.get_race_result_complete(
            venue_code=f"{int(venue_code):02d}",
            race_date=date_str,
            race_number=race_number
        )

        if result and result.get('payouts'):
            conn = sqlite3.connect(db_path, timeout=30.0)
            cursor = conn.cursor()

            payouts = result.get('payouts', {})
            trifecta = payouts.get('trifecta', [])

            for payout_data in trifecta:
                combination = payout_data.get('combination', '')
                amount = payout_data.get('amount', 0)

                if combination and amount:
                    cursor.execute('''
                        INSERT OR REPLACE INTO payouts (race_id, bet_type, combination, amount)
                        VALUES (?, 'trifecta', ?, ?)
                    ''', (race_id, combination, amount))

            # 結果も保存
            results = result.get('results', [])
            for res in results:
                pit = res.get('pit_number')
                rank = res.get('rank')
                if pit and rank:
                    rank_str = str(rank) if isinstance(rank, int) else rank
                    cursor.execute('''
                        INSERT OR REPLACE INTO results (race_id, pit_number, rank, is_invalid)
                        VALUES (?, ?, ?, 0)
                    ''', (race_id, pit, rank_str))

            conn.commit()
            conn.close()
            return True
    except:
        pass
    return False


def main():
    print("=" * 70)
    print("2024年 不足データ収集")
    print("=" * 70)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    db_path = str(PROJECT_ROOT / "data" / "boatrace.db")

    # 不足データを取得
    races_exh = get_races_missing_exhibition(db_path)
    races_pay = get_races_missing_payouts(db_path)

    print(f"展示タイム不足: {len(races_exh):,}件")
    print(f"払戻金不足: {len(races_pay):,}件")
    print()

    # 確認
    try:
        if sys.stdin.isatty():
            response = input("収集を開始しますか？ (y/N): ")
            if response.lower() != 'y':
                print("キャンセルしました")
                return
    except (EOFError, OSError):
        print("（バックグラウンド実行: 自動開始）")

    print()
    start_time = time.time()

    # === 展示タイム収集 ===
    if races_exh:
        print(f"[1/2] 展示タイム収集中...")
        tasks = [(r[0], r[1], r[2], r[3], db_path) for r in races_exh]
        exh_success = 0

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(collect_exhibition, t): t for t in tasks}
            for idx, future in enumerate(as_completed(futures), 1):
                if future.result():
                    exh_success += 1
                if idx % 100 == 0:
                    print(f"  進捗: {idx}/{len(tasks)} (成功: {exh_success})")

        print(f"  完了: {exh_success}/{len(races_exh)}件")

    # === 払戻金収集 ===
    if races_pay:
        print(f"[2/2] 払戻金収集中...")
        tasks = [(r[0], r[1], r[2], r[3], db_path) for r in races_pay]
        pay_success = 0

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(collect_payout, t): t for t in tasks}
            for idx, future in enumerate(as_completed(futures), 1):
                if future.result():
                    pay_success += 1
                if idx % 100 == 0:
                    print(f"  進捗: {idx}/{len(tasks)} (成功: {pay_success})")

        print(f"  完了: {pay_success}/{len(races_pay)}件")

    elapsed = time.time() - start_time
    print()
    print("=" * 70)
    print(f"収集完了 (所要時間: {elapsed/60:.1f}分)")
    print("=" * 70)


if __name__ == "__main__":
    main()
