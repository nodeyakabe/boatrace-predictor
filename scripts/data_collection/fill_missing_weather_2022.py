# -*- coding: utf-8 -*-
"""
2022年天候データ補完スクリプト
==============================

2022年1-3月のweatherテーブルに大量の欠損があるため、
過去のレースデータから天候情報を補完する。

問題:
    - 2022年1-3月のweatherテーブルデータが欠損（約80%）
    - これにより直前情報分析に偏りが発生

対象:
    - weatherテーブル（会場×日付単位の天候データ）

使用例:
    python scripts/data_collection/fill_missing_weather_2022.py --check
    python scripts/data_collection/fill_missing_weather_2022.py --fill
"""

import sqlite3
import sys
import io
import os
import argparse
from datetime import datetime, timedelta

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川', '06': '浜名湖',
    '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国', '11': '琵琶湖', '12': '住之江',
    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島', '17': '宮島', '18': '徳山',
    '19': '下関', '20': '若松', '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}


def check_missing_weather(cursor):
    """欠損状況を確認"""
    print("=" * 70)
    print("天候データ欠損状況チェック")
    print("=" * 70)

    # 年度別・月別の欠損状況
    query = '''
    SELECT
        substr(r.race_date, 1, 7) as year_month,
        COUNT(DISTINCT r.venue_code || r.race_date) as total_venue_dates,
        COUNT(DISTINCT CASE WHEN w.id IS NOT NULL THEN r.venue_code || r.race_date END) as with_weather
    FROM races r
    LEFT JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
    WHERE r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
    GROUP BY year_month
    ORDER BY year_month
    '''
    cursor.execute(query)

    print("\n=== 年月別 天候データカバー率 ===")
    print(f"{'年月':>10} | {'総会場日数':>10} | {'天候あり':>10} | {'カバー率':>10}")
    print("-" * 50)

    problem_months = []
    for row in cursor.fetchall():
        year_month, total, with_w = row
        with_w = with_w or 0
        pct = with_w / total * 100 if total > 0 else 0
        missing = total - with_w

        if pct < 50:
            marker = " *** 問題 ***"
            problem_months.append((year_month, total, with_w, missing))
        elif pct < 90:
            marker = " *"
        else:
            marker = ""

        print(f"{year_month:>10} | {total:>10} | {with_w:>10} | {pct:>9.1f}%{marker}")

    if problem_months:
        print("\n=== 問題のある月（カバー率50%未満）===")
        for ym, total, with_w, missing in problem_months:
            print(f"  {ym}: 欠損 {missing}件 / {total}件")

    return problem_months


def find_weather_sources(cursor, year_month):
    """
    欠損している天候データの補完元を探す

    race_conditionsテーブルに天候情報があれば活用
    注: weatherカラム（天候種別）がNULLでも、wind_speed等があれば補完対象とする
    """
    query = '''
    SELECT
        r.venue_code,
        r.race_date,
        rc.weather,
        rc.wind_direction,
        rc.wind_speed,
        rc.water_temperature,
        rc.wave_height
    FROM races r
    JOIN race_conditions rc ON r.id = rc.race_id
    LEFT JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
    WHERE substr(r.race_date, 1, 7) = ?
    AND w.id IS NULL
    AND (rc.wind_speed IS NOT NULL OR rc.weather IS NOT NULL)
    GROUP BY r.venue_code, r.race_date
    ORDER BY r.venue_code, r.race_date
    '''
    cursor.execute(query, (year_month,))
    return cursor.fetchall()


def insert_weather_data(cursor, venue_code, weather_date, weather, wind_direction, wind_speed, water_temp, wave_height):
    """weatherテーブルにデータを挿入"""
    # 既存チェック
    cursor.execute('''
        SELECT id FROM weather WHERE venue_code = ? AND weather_date = ?
    ''', (venue_code, weather_date))

    if cursor.fetchone():
        return False  # 既存

    cursor.execute('''
        INSERT INTO weather (venue_code, weather_date, weather_condition, wind_direction, wind_speed, water_temperature, wave_height, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (venue_code, weather_date, weather, wind_direction, wind_speed, water_temp, wave_height, datetime.now().isoformat()))

    return True


def fill_missing_weather(cursor, conn, target_months=None):
    """欠損データを補完"""
    print("\n" + "=" * 70)
    print("天候データ補完処理")
    print("=" * 70)

    if target_months is None:
        # 問題のある月を自動検出
        problem_months = check_missing_weather(cursor)
        if not problem_months:
            print("\n補完対象の月がありません。")
            return

        target_months = [pm[0] for pm in problem_months]

    total_inserted = 0
    for year_month in target_months:
        sources = find_weather_sources(cursor, year_month)

        if not sources:
            print(f"\n{year_month}: race_conditionsに補完元データなし")
            continue

        print(f"\n{year_month}: {len(sources)}件の補完候補を発見")

        inserted = 0
        for row in sources:
            venue_code, weather_date, weather, wind_dir, wind_speed, water_temp, wave_height = row
            if insert_weather_data(cursor, venue_code, weather_date, weather, wind_dir, wind_speed, water_temp, wave_height):
                inserted += 1

        conn.commit()
        print(f"  → {inserted}件を挿入")
        total_inserted += inserted

    print(f"\n合計 {total_inserted}件を補完しました。")


def main():
    parser = argparse.ArgumentParser(description='2022年天候データ補完')
    parser.add_argument('--check', action='store_true', help='欠損状況をチェックのみ')
    parser.add_argument('--fill', action='store_true', help='欠損データを補完')
    args = parser.parse_args()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    if args.check:
        check_missing_weather(cursor)
    elif args.fill:
        fill_missing_weather(cursor, conn)
    else:
        # デフォルトはチェックのみ
        check_missing_weather(cursor)
        print("\n補完を実行するには --fill オプションを指定してください。")

    conn.close()


if __name__ == "__main__":
    main()
