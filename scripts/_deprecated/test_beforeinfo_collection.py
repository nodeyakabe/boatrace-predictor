#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
直前情報収集のテスト（1日分のみ）
"""
import sys
import os

# 最初に文字コード設定
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ['PYTHONUNBUFFERED'] = '1'

import sqlite3
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.scraper.beforeinfo_scraper import BeforeInfoScraper

def test_single_race():
    """1レース分の直前情報を取得してテスト"""
    print("=" * 80)
    print("直前情報収集テスト（2020-01-01の1レース）")
    print("=" * 80)
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"

    # 2020-01-01の最初のレースを取得
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date = '2020-01-01'
        ORDER BY r.venue_code, r.race_number
        LIMIT 1
    """)

    race = cursor.fetchone()
    conn.close()

    if not race:
        print("テスト対象レースが見つかりません")
        return False

    race_id, venue_code, race_date, race_number = race

    print(f"テスト対象: {race_date} 会場{int(venue_code):02d} R{race_number}")
    print(f"race_id: {race_id}")
    print()

    # 直前情報取得
    scraper = BeforeInfoScraper(delay=1.0)

    try:
        date_str = race_date.replace('-', '')

        print("直前情報を取得中...")
        beforeinfo = scraper.get_race_beforeinfo(
            venue_code=f"{int(venue_code):02d}",
            date_str=date_str,
            race_number=race_number
        )

        if beforeinfo and beforeinfo.get('is_published'):
            print("OK: データ取得成功")
            print()
            print("取得データ:")
            print(f"  展示タイム: {len(beforeinfo.get('exhibition_times', {}))}件")
            print(f"  チルト角度: {len(beforeinfo.get('tilt_angles', {}))}件")
            print(f"  部品交換: {len(beforeinfo.get('parts_replacements', {}))}件")
            print(f"  ST: {len(beforeinfo.get('start_timings', {}))}件")
            print(f"  進入コース: {len(beforeinfo.get('exhibition_courses', {}))}件")
            print(f"  気象データ: {beforeinfo.get('weather')}")
            print()
            return True
        else:
            print("NG: データ未公開または取得失敗")
            return False

    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_single_race()

    print()
    print("=" * 80)
    if success:
        print("テスト成功 - 直前情報収集スクリプトは正常に動作します")
    else:
        print("テスト失敗 - スクリプトに問題があります")
    print("=" * 80)

    sys.exit(0 if success else 1)
