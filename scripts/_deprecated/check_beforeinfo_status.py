#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
直前情報（beforeinfo）収集状況確認スクリプト

昨夜実行したデータ収集の結果を詳細に把握する
"""
import sys
import os
import io
import sqlite3
from datetime import datetime
from pathlib import Path

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def main():
    print("=" * 70)
    print("直前情報（beforeinfo）収集状況確認")
    print("=" * 70)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 1. race_detailsの直前情報（exhibition_time）
    print("【1】race_details テーブルの直前情報")
    print("-" * 70)

    cursor.execute("""
        SELECT
            COUNT(*) as total_entries,
            SUM(CASE WHEN exhibition_time IS NOT NULL THEN 1 ELSE 0 END) as has_exhibition_time,
            SUM(CASE WHEN st_time IS NOT NULL THEN 1 ELSE 0 END) as has_st_time,
            SUM(CASE WHEN chikusen_time IS NOT NULL THEN 1 ELSE 0 END) as has_chikusen_time,
            SUM(CASE WHEN isshu_time IS NOT NULL THEN 1 ELSE 0 END) as has_isshu_time,
            SUM(CASE WHEN mawariashi_time IS NOT NULL THEN 1 ELSE 0 END) as has_mawariashi_time,
            SUM(CASE WHEN tilt_angle IS NOT NULL THEN 1 ELSE 0 END) as has_tilt_angle
        FROM race_details
    """)

    row = cursor.fetchone()
    total = row[0]
    ex_time = row[1]
    st_time = row[2]
    chikusen = row[3]
    isshu = row[4]
    mawariashi = row[5]
    tilt = row[6]

    print(f"  総エントリ数: {total:,}件")
    print(f"  exhibition_time 有: {ex_time:,}件 ({ex_time/total*100:.1f}%)")
    print(f"  st_time 有: {st_time:,}件 ({st_time/total*100:.1f}%)")
    print(f"  chikusen_time 有: {chikusen:,}件 ({chikusen/total*100:.1f}%)")
    print(f"  isshu_time 有: {isshu:,}件 ({isshu/total*100:.1f}%)")
    print(f"  mawariashi_time 有: {mawariashi:,}件 ({mawariashi/total*100:.1f}%)")
    print(f"  tilt_angle 有: {tilt:,}件 ({tilt/total*100:.1f}%)")
    print("")

    # 2. exhibition_dataテーブル
    print("【2】exhibition_data テーブル（専用直前情報）")
    print("-" * 70)

    cursor.execute("SELECT COUNT(*) FROM exhibition_data")
    ex_data_count = cursor.fetchone()[0]
    print(f"  総レコード数: {ex_data_count:,}件")

    if ex_data_count > 0:
        cursor.execute("""
            SELECT
                MIN(race_id) as min_race_id,
                MAX(race_id) as max_race_id
            FROM exhibition_data
        """)
        row = cursor.fetchone()
        print(f"  race_id範囲: {row[0]} ~ {row[1]}")
    print("")

    # 3. weatherテーブル
    print("【3】weather テーブル（天候情報）")
    print("-" * 70)

    cursor.execute("SELECT COUNT(*) FROM weather")
    weather_count = cursor.fetchone()[0]
    print(f"  総レコード数: {weather_count:,}件")

    cursor.execute("""
        SELECT
            MIN(weather_date) as min_date,
            MAX(weather_date) as max_date
        FROM weather
    """)
    row = cursor.fetchone()
    print(f"  日付範囲: {row[0]} ~ {row[1]}")
    print("")

    # 4. 年度別のbefore予測と直前情報の対応状況
    print("【4】年度別 before予測と直前情報の対応状況")
    print("-" * 70)

    for year in [2020, 2021, 2022, 2023, 2024]:
        cursor.execute(f"""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date >= '{year}-01-01'
              AND r.race_date <= '{year}-12-31'
              AND rp.prediction_type = 'before'
        """)
        before_count = cursor.fetchone()[0]

        cursor.execute(f"""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= '{year}-01-01'
              AND r.race_date <= '{year}-12-31'
              AND rp.prediction_type = 'before'
              AND rd.exhibition_time IS NOT NULL
        """)
        with_exhibition = cursor.fetchone()[0]

        cursor.execute(f"""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= '{year}-01-01'
              AND r.race_date <= '{year}-12-31'
              AND rp.prediction_type = 'before'
              AND rd.st_time IS NOT NULL
        """)
        with_st_time = cursor.fetchone()[0]

        print(f"{year}年:")
        print(f"  before予測総数: {before_count:,}件")
        print(f"  展示タイム有: {with_exhibition:,}件 ({with_exhibition/before_count*100 if before_count > 0 else 0:.1f}%)")
        print(f"  STタイム有: {with_st_time:,}件 ({with_st_time/before_count*100 if before_count > 0 else 0:.1f}%)")
        print("")

    # 5. 直前情報の欠損パターン分析
    print("【5】直前情報の欠損パターン分析（2024年）")
    print("-" * 70)

    cursor.execute("""
        SELECT
            CASE
                WHEN rd.exhibition_time IS NOT NULL AND rd.st_time IS NOT NULL THEN '両方あり'
                WHEN rd.exhibition_time IS NOT NULL AND rd.st_time IS NULL THEN '展示タイムのみ'
                WHEN rd.exhibition_time IS NULL AND rd.st_time IS NOT NULL THEN 'STのみ'
                ELSE '両方なし'
            END as pattern,
            COUNT(*) as count
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2024-12-31'
        GROUP BY pattern
        ORDER BY count DESC
    """)

    for pattern, count in cursor.fetchall():
        print(f"  {pattern}: {count:,}件")
    print("")

    # 6. 最近収集された直前情報（最新5レース）
    print("【6】最近収集された直前情報（最新5レース）")
    print("-" * 70)

    cursor.execute("""
        SELECT
            r.race_date,
            r.venue_code,
            r.race_number,
            COUNT(DISTINCT rd.id) as entry_count,
            SUM(CASE WHEN rd.exhibition_time IS NOT NULL THEN 1 ELSE 0 END) as ex_time_count,
            SUM(CASE WHEN rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as st_count
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2024-01-01'
        GROUP BY r.id
        ORDER BY r.race_date DESC, r.venue_code DESC, r.race_number DESC
        LIMIT 5
    """)

    for race_date, venue, race_num, entries, ex_count, st_count in cursor.fetchall():
        venue_str = f"{int(venue):02d}" if venue else "??"
        race_num_str = f"{int(race_num):02d}" if race_num else "??"
        print(f"  {race_date} {venue_str}場 {race_num_str}R: "
              f"エントリ{entries}件 展示{ex_count}件 ST{st_count}件")
    print("")

    # 7. 昨夜の収集ジョブ確認
    print("【7】昨夜の収集ジョブ確認")
    print("-" * 70)

    job_file = Path(PROJECT_ROOT) / 'temp' / 'jobs' / 'tenji_collection.json'
    if job_file.exists():
        import json
        with open(job_file, 'r', encoding='utf-8') as f:
            job_data = json.load(f)

        print(f"  ジョブファイル: {job_file}")
        print(f"  最終更新: {datetime.fromtimestamp(job_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  ステータス: {job_data.get('status', 'unknown')}")
        print(f"  進捗: {job_data.get('processed', 0)}/{job_data.get('total', 0)}")
        if 'last_error' in job_data and job_data['last_error']:
            print(f"  最終エラー: {job_data['last_error']}")
    else:
        print("  ジョブファイルが見つかりません")
    print("")

    conn.close()

    print("=" * 70)
    print("確認完了")
    print("=" * 70)


if __name__ == '__main__':
    main()
