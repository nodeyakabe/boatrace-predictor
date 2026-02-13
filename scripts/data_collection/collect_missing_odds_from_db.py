#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DBベースの欠損オッズ収集スクリプト

ScheduleScraperに依存せず、DB内の既存レースから欠損オッズを収集します。
"""
import sys
import io
import sqlite3
import argparse
import time
import csv
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

# Windows文字コード対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH
from src.scraper.odds_scraper import OddsScraper


def get_missing_odds_races(db_path: Path, year: int, month: int = None) -> List[Tuple[str, str, int]]:
    """
    オッズが欠けているレースのリストを取得

    Returns:
        List[(venue_code, race_date, race_number), ...]
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if month:
        date_pattern = f'{year}-{month:02d}-%'
    else:
        date_pattern = f'{year}-%'

    # オッズが欠けているレースを取得
    cursor.execute('''
        SELECT r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date LIKE ?
        AND NOT EXISTS (
            SELECT 1 FROM trifecta_odds t WHERE t.race_id = r.id
        )
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (date_pattern,))

    missing_races = cursor.fetchall()
    conn.close()

    return missing_races


def fetch_odds_for_race(args):
    """1レースのオッズを取得（並列処理用）"""
    venue_code, race_date, race_number = args

    scraper = OddsScraper()

    # YYYY-MM-DD → YYYYMMDD
    race_date_yyyymmdd = race_date.replace('-', '')

    try:
        odds_data = scraper.get_trifecta_odds(venue_code, race_date_yyyymmdd, race_number)

        if odds_data and len(odds_data) > 0:
            return {
                'success': True,
                'venue_code': venue_code,
                'race_date': race_date_yyyymmdd,
                'race_number': race_number,
                'odds': odds_data,
                'count': len(odds_data)
            }
        else:
            return {
                'success': False,
                'venue_code': venue_code,
                'race_date': race_date_yyyymmdd,
                'race_number': race_number,
                'reason': 'no_data'
            }
    except Exception as e:
        return {
            'success': False,
            'venue_code': venue_code,
            'race_date': race_date_yyyymmdd,
            'race_number': race_number,
            'reason': str(e)
        }
    finally:
        scraper.close()
        time.sleep(0.1)  # レート制限


def save_odds_to_csv(output_file: Path, all_odds_data: list):
    """オッズをCSVに保存"""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    header = ['venue_code', 'race_date', 'race_number', 'combination', 'odds']

    write_header = not output_file.exists()

    with open(output_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=header)

        if write_header:
            writer.writeheader()

        saved_count = 0
        for item in all_odds_data:
            if item['success']:
                for combination, odds_value in item['odds'].items():
                    writer.writerow({
                        'venue_code': item['venue_code'],
                        'race_date': item['race_date'],
                        'race_number': item['race_number'],
                        'combination': combination,
                        'odds': odds_value
                    })
                saved_count += 1

        return saved_count


def main():
    parser = argparse.ArgumentParser(description='DBベースの欠損オッズ収集')
    parser.add_argument('--year', type=int, required=True, help='対象年')
    parser.add_argument('--month', type=int, choices=range(1, 13), help='対象月（省略時は全月）')
    parser.add_argument('--workers', type=int, default=8, help='並列数（デフォルト: 8）')
    parser.add_argument('--output', type=str, help='CSV出力先（デフォルト: data/csv/missing_odds_YEAR_MONTH.csv）')
    parser.add_argument('--batch-size', type=int, default=100, help='バッチ保存サイズ（デフォルト: 100）')
    args = parser.parse_args()

    db_path = DATABASE_PATH

    # 出力ファイル
    if args.output:
        output_file = Path(args.output)
    else:
        if args.month:
            output_file = PROJECT_ROOT / 'data' / 'csv' / f'missing_odds_{args.year}_{args.month:02d}.csv'
        else:
            output_file = PROJECT_ROOT / 'data' / 'csv' / f'missing_odds_{args.year}.csv'

    print("=" * 80)
    print("DBベースの欠損オッズ収集")
    print("=" * 80)
    print(f"対象: {args.year}年{args.month}月" if args.month else f"対象: {args.year}年")
    print(f"出力先: {output_file}")
    print(f"並列数: {args.workers}スレッド")
    print()

    # 欠損レースを取得
    print("=== 欠損レース確認中 ===")
    missing_races = get_missing_odds_races(db_path, args.year, args.month)

    if not missing_races:
        print("✅ 欠損オッズはありません")
        return

    print(f"欠損レース数: {len(missing_races):,}件")
    print()

    # サンプル表示
    print("最初の5件:")
    for i, (venue, date, race_no) in enumerate(missing_races[:5], 1):
        print(f"  {i}. 会場{venue} {date} R{race_no}")
    print()

    # 収集開始
    print("=== オッズ収集開始 ===")
    start_time = time.time()

    success_count = 0
    failed_count = 0
    batch_data = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_odds_for_race, race): race for race in missing_races}

        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()

            if result['success']:
                success_count += 1
                batch_data.append(result)
                print(f"[{i}/{len(missing_races)}] ✅ {result['venue_code']} {result['race_date']} R{result['race_number']} - {result['count']}通り")
            else:
                failed_count += 1
                print(f"[{i}/{len(missing_races)}] ❌ {result['venue_code']} {result['race_date']} R{result['race_number']} - {result['reason']}")

            # バッチ保存
            if len(batch_data) >= args.batch_size:
                saved = save_odds_to_csv(output_file, batch_data)
                print(f"  💾 {saved}レース分のオッズをCSV保存")
                batch_data = []

            # 進捗表示
            if i % 100 == 0:
                elapsed = time.time() - start_time
                speed = i / elapsed * 60
                remaining = (len(missing_races) - i) / speed if speed > 0 else 0
                print(f"  進捗: {i}/{len(missing_races)} ({i/len(missing_races)*100:.1f}%) | 速度: {speed:.1f}件/分 | 残り: {remaining:.1f}分")

    # 最終バッチ保存
    if batch_data:
        saved = save_odds_to_csv(output_file, batch_data)
        print(f"  💾 {saved}レース分のオッズをCSV保存")

    elapsed_time = time.time() - start_time

    print()
    print("=" * 80)
    print("収集完了")
    print("=" * 80)
    print(f"対象レース数: {len(missing_races):,}")
    print(f"成功: {success_count:,}")
    print(f"失敗: {failed_count:,}")
    print(f"成功率: {success_count / len(missing_races) * 100:.1f}%")
    print(f"所要時間: {elapsed_time / 60:.1f}分")
    print(f"出力先: {output_file}")
    print("=" * 80)


if __name__ == '__main__':
    main()
