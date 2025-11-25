#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
race_details初期データ作成スクリプト（INSERT対応版）

race_detailsレコードが存在しないレースに対して、
BeforeInfoScraperで取得した展示タイム・チルト角度・部品交換情報を
INSERTで新規登録します。

実行方法:
  python 補完_race_details_INSERT対応.py 2025-11-17 2025-11-17
  python 補完_race_details_INSERT対応.py 2025-11-01 2025-11-30
"""
import sys
sys.path.append('src')

import sqlite3
from datetime import datetime
from scraper.beforeinfo_scraper import BeforeInfoScraper
from tqdm import tqdm
import time

def main():
    if len(sys.argv) < 3:
        print("使用方法: python 補完_race_details_INSERT対応.py [開始日] [終了日]")
        print("例: python 補完_race_details_INSERT対応.py 2025-11-17 2025-11-17")
        sys.exit(1)

    start_date_str = sys.argv[1]
    end_date_str = sys.argv[2]

    print("="*80)
    print("race_details初期データ作成（INSERT対応版）")
    print("="*80)
    print(f"対象期間: {start_date_str} ～ {end_date_str}")
    print()

    # DBから対象レースを取得
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # race_detailsが存在しないレースを取得
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

    scraper = BeforeInfoScraper(delay=0.5)
    success_count = 0
    partial_count = 0
    error_count = 0
    skip_count = 0

    for race_id, venue_code, race_date, race_number in tqdm(races, desc="race_details作成"):
        # 日付をYYYYMMDD形式に変換
        date_str = race_date.replace('-', '')

        try:
            # BeforeInfo取得
            beforeinfo = scraper.get_race_beforeinfo(venue_code, date_str, race_number)

            if not beforeinfo:
                skip_count += 1
                time.sleep(0.5)
                continue

            exhibition_times = beforeinfo.get('exhibition_times', {})
            tilt_angles = beforeinfo.get('tilt_angles', {})
            parts_replacements = beforeinfo.get('parts_replacements', {})

            # 6艇分のレコードをINSERT
            inserted = 0
            for pit_number in range(1, 7):
                ex_time = exhibition_times.get(pit_number)
                tilt = tilt_angles.get(pit_number)
                parts = parts_replacements.get(pit_number)

                # INSERT (最低限pit_numberは必須)
                cursor.execute("""
                    INSERT INTO race_details (
                        race_id, pit_number,
                        exhibition_time, tilt_angle, parts_replacement
                    ) VALUES (?, ?, ?, ?, ?)
                """, (race_id, pit_number, ex_time, tilt, parts))
                inserted += 1

            conn.commit()

            if inserted == 6:
                # データありで6艇分すべて登録
                if exhibition_times or tilt_angles or parts_replacements:
                    success_count += 1
                else:
                    # レコードは作ったがデータなし
                    partial_count += 1

            # レート制限対策
            time.sleep(0.5)

        except Exception as e:
            error_count += 1
            print(f"\n[エラー] race_id={race_id}, {venue_code}-{race_date}-R{race_number}: {e}")
            time.sleep(0.5)

    scraper.close()

    print("\n" + "="*80)
    print("作成完了")
    print("="*80)
    print(f"成功（データあり）: {success_count}レース")
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
    print(f"  展示タイムあり: {ex_count}件 ({ex_count/total_details*100:.1f}%)")
    print(f"  チルト角度あり: {tilt_count}件 ({tilt_count/total_details*100:.1f}%)")
    print(f"  部品交換あり: {parts_count}件 ({parts_count/total_details*100:.1f}%)")

    conn.close()
    print("\n" + "="*80)


if __name__ == "__main__":
    main()
