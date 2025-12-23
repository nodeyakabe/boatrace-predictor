#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
データ収集の失敗原因を特定
"""
import sys
import os
import sqlite3
import traceback

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from src.scraper.result_scraper import ResultScraper

# 失敗しているレースを1件取得
conn = sqlite3.connect('data/boatrace.db')
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
    LIMIT 1
""")

race = cursor.fetchone()
conn.close()

if not race:
    print("不足データなし")
    sys.exit(0)

race_id, venue_code, race_date, race_number = race

print("="*80)
print(f"テスト対象レース")
print(f"  race_id: {race_id}")
print(f"  venue_code: {venue_code}")
print(f"  race_date: {race_date}")
print(f"  race_number: {race_number}")
print("="*80)

# 展示タイム取得を試行
print("\n【展示タイム取得テスト】")
scraper = BeforeInfoScraper(delay=0.3)

try:
    date_str = race_date.replace('-', '')
    venue_str = f"{int(venue_code):02d}"

    print(f"URL生成パラメータ: venue={venue_str}, date={date_str}, race={race_number}")

    beforeinfo = scraper.get_race_beforeinfo(
        venue_code=venue_str,
        date_str=date_str,
        race_number=race_number
    )

    print(f"\n取得結果:")
    print(f"  データ取得: {'成功' if beforeinfo else '失敗'}")

    if beforeinfo:
        print(f"  is_published: {beforeinfo.get('is_published')}")
        print(f"  exhibition_times: {len(beforeinfo.get('exhibition_times', {}))}件")
        print(f"  tilt_angles: {len(beforeinfo.get('tilt_angles', {}))}件")
        print(f"  start_timings: {len(beforeinfo.get('start_timings', {}))}件")
        print(f"\n  詳細:")
        for key, value in beforeinfo.items():
            if isinstance(value, dict) and len(value) <= 6:
                print(f"    {key}: {value}")
    else:
        print("  beforeinfo is None または 空")

except Exception as e:
    print(f"\n❌ エラー発生:")
    print(f"  型: {type(e).__name__}")
    print(f"  メッセージ: {e}")
    print("\nスタックトレース:")
    traceback.print_exc()

# 払戻金取得も試行
print("\n" + "="*80)
print("【払戻金取得テスト】")

cursor = conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT r.id, r.venue_code, r.race_date, r.race_number
    FROM races r
    WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
    AND NOT EXISTS (SELECT 1 FROM payouts p WHERE p.race_id = r.id)
    ORDER BY r.race_date, r.venue_code, r.race_number
    LIMIT 1
""")

race2 = cursor.fetchone()
conn.close()

if race2:
    race_id2, venue_code2, race_date2, race_number2 = race2

    print(f"テスト対象: {race_date2} {venue_code2}場 {race_number2}R")

    scraper2 = ResultScraper()

    try:
        date_str2 = race_date2.replace('-', '')
        venue_str2 = f"{int(venue_code2):02d}"

        result = scraper2.get_race_result_complete(
            venue_code=venue_str2,
            race_date=date_str2,
            race_number=race_number2
        )

        print(f"\n取得結果:")
        print(f"  データ取得: {'成功' if result else '失敗'}")

        if result:
            print(f"  payouts: {len(result.get('payouts', {}))}件")
            print(f"  results: {len(result.get('results', []))}件")
        else:
            print("  result is None または 空")

    except Exception as e:
        print(f"\n❌ エラー発生:")
        print(f"  型: {type(e).__name__}")
        print(f"  メッセージ: {e}")
        print("\nスタックトレース:")
        traceback.print_exc()
else:
    print("払戻金不足データなし")
