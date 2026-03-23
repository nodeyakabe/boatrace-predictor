# -*- coding: utf-8 -*-
"""DBで entries が欠損しているレースの日付×会場のみをピンポイントでCSV収集

brute-force（全日付×全24会場）の代わりに、DBから欠損レースを特定して
必要な組み合わせのみアクセスする。

【brute-forceとの比較（2022年1-7月の場合）】
  brute-force: 5,088タスク（212日 × 24会場）→ 推定31時間
  このスクリプト: 841タスク（欠損のある日付×会場のみ）→ 推定5時間

使用例:
    python scripts/data_collection/fetch_missing_entries_csv.py \\
        --start 2022-01-01 --end 2022-07-31 \\
        --output data/csv/2022_entries_補完 --workers 8

実施後の手順（休日明け）:
    1. dry-run確認:
       python scripts/data_collection/import_races_csv.py \\
           --dir data/csv/2022_entries_補完 --dry-run
    2. DB投入:
       python scripts/data_collection/import_races_csv.py \\
           --dir data/csv/2022_entries_補完
    3. 後続処理（DATA_DEPENDENCY_CHAIN）:
       python scripts/data_collection/補完_決まり手データ_改善版.py
       python scripts/data_collection/補完_レース詳細データ_改善版v4.py
"""

import sys
import os
import argparse
import sqlite3
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

# fetch_to_csv_parallel_improved.py の関数を再利用
# （Windows文字コード設定はimport先のモジュールに任せる）
SCRIPTS_DATA_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DATA_DIR))
from fetch_to_csv_parallel_improved import fetch_venue_day_parallel, save_to_csv


def get_missing_venue_days(db_path: str, start_date: str, end_date: str) -> list:
    """DBからentries欠損レースの日付×会場ユニーク組み合わせを取得"""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        SELECT DISTINCT r.venue_code, r.race_date
        FROM races r
        LEFT JOIN entries e ON r.id = e.race_id
        WHERE r.race_date BETWEEN ? AND ?
          AND e.race_id IS NULL
        ORDER BY r.race_date, r.venue_code
    ''', (start_date, end_date))
    rows = c.fetchall()
    conn.close()
    return rows


def main():
    parser = argparse.ArgumentParser(
        description='DBで entries 欠損のある日付×会場のみピンポイントでCSV収集'
    )
    parser.add_argument('--start', required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--output', required=True, help='CSV出力ディレクトリ')
    parser.add_argument('--workers', type=int, default=8, help='並列数（デフォルト: 8）')
    parser.add_argument('--dry-run', action='store_true', help='タスク数確認のみ（取得しない）')
    args = parser.parse_args()

    db_path = str(ROOT_DIR / 'data' / 'boatrace.db')
    output_dir = ROOT_DIR / args.output

    print('=' * 70)
    print('entries欠損レース ピンポイントCSV収集')
    print('=' * 70)
    print(f'期間: {args.start} - {args.end}')
    print(f'出力先: {args.output}')
    print(f'並列数: {args.workers}スレッド')
    print()

    # 欠損日付×会場リストを取得
    missing = get_missing_venue_days(db_path, args.start, args.end)
    print(f'欠損タスク数: {len(missing)}件（日付×会場）')

    if not missing:
        print('欠損なし。処理不要。')
        return

    # brute-forceとの比較
    from datetime import datetime, timedelta
    start_dt = datetime.strptime(args.start, '%Y-%m-%d')
    end_dt = datetime.strptime(args.end, '%Y-%m-%d')
    total_days = (end_dt - start_dt).days + 1
    brute_force_tasks = total_days * 24
    reduction = (1 - len(missing) / brute_force_tasks) * 100
    print(f'brute-forceなら: {brute_force_tasks}タスク → {reduction:.0f}%削減')
    print(f'推定時間: 約{len(missing) * 30 / args.workers / 60:.0f}〜{len(missing) * 60 / args.workers / 60:.0f}分')
    print()

    if args.dry_run:
        print('[dry-run] タスク確認のみ。取得しません。')
        for vc, date in missing[:10]:
            print(f'  venue={vc} date={date}')
        if len(missing) > 10:
            print(f'  ... 他 {len(missing) - 10}件')
        return

    # 並列取得
    task_args = [(vc, date, None) for vc, date in missing]
    all_results = []
    completed = 0
    start_time = time.time()

    print('=== データ取得開始 ===')
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_venue_day_parallel, t): t for t in task_args}
        for future in as_completed(futures):
            completed += 1
            venue_code, race_date, count, races_data, incomplete = future.result()

            if count > 0:
                all_results.append({
                    'venue_code': venue_code,
                    'race_date': race_date.replace('-', ''),
                    'races_data': races_data
                })
                print(f'取得完了: 会場={venue_code}, 日付={race_date}, {count}レース')

            if completed % 50 == 0 or completed == len(task_args):
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = (len(task_args) - completed) / rate if rate > 0 else 0
                print(f'進捗: {completed}/{len(task_args)} ({completed/len(task_args)*100:.1f}%)'
                      f' - 取得レース: {len(all_results)} - 残り約{remaining/60:.1f}分')

    print(f'\n取得完了: {len(all_results)}レース分 → CSV書き出し中...')
    saved = save_to_csv(output_dir, all_results)
    print(f'CSV書き出し完了: {output_dir}')
    print()
    print('次のステップ（休日明け）:')
    print(f'  1. dry-run確認: python scripts/data_collection/import_races_csv.py --dir {args.output} --dry-run')
    print(f'  2. DB投入:      python scripts/data_collection/import_races_csv.py --dir {args.output}')
    print( '  3. kimarite補完: python scripts/data_collection/補完_決まり手データ_改善版.py')
    print( '  4. race_details補完: python scripts/data_collection/補完_レース詳細データ_改善版v4.py')


if __name__ == '__main__':
    main()
