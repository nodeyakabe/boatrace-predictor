"""
女性レーサーマスターリスト取得スクリプト

ladies-info.jp の公式 JSON API から現役女性レーサー全員を取得し、
data/csv/racers/ladies_master.csv に保存する。

API: https://www.ladies-info.jp/api-racers/api?q=&kyu=&birthplace=&shibu=&ki=&page=N
  total: 278人, max_page: 18（16件/ページ）

取得フィールド:
  racer_number, name, name_kana, registration_period, branch, rank

使い方:
  python scripts/data_collection/fetch_ladies_master.py
  python scripts/data_collection/fetch_ladies_master.py --out data/csv/racers/ladies_master.csv
"""

import os
import sys
import csv
import time
import argparse
import requests
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

DEFAULT_OUT = os.path.join(PROJECT_ROOT, 'data', 'csv', 'racers', 'ladies_master.csv')
API_BASE = 'https://www.ladies-info.jp/api-racers/api'


def fetch_all_pages(delay: float = 0.5) -> list[dict]:
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; BoatRaceAnalyzer/1.0)'})

    # ページ1 でtotalとmax_pageを確認
    r = session.get(API_BASE, params={'q': '', 'kyu': '', 'birthplace': '', 'shibu': '', 'ki': '', 'page': 1}, timeout=15)
    r.raise_for_status()
    data = r.json()
    total = data['total']
    max_page = data['max_page']
    print(f'API 確認: 総数={total}人, ページ数={max_page}')

    all_racers = list(data['racers'])
    print(f'  page 1/{max_page}: {len(data["racers"])}件取得')

    for page in range(2, max_page + 1):
        time.sleep(delay)
        r = session.get(API_BASE, params={'q': '', 'kyu': '', 'birthplace': '', 'shibu': '', 'ki': '', 'page': page}, timeout=15)
        r.raise_for_status()
        data = r.json()
        all_racers.extend(data['racers'])
        print(f'  page {page}/{max_page}: {len(data["racers"])}件取得 (累計 {len(all_racers)}件)')

    print(f'取得完了: 合計 {len(all_racers)}件 (API reported total: {total})')
    return all_racers


def save_csv(racers: list[dict], out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fieldnames = ['racer_number', 'name', 'name_kana', 'registration_period', 'branch', 'rank', 'fetched_at']
    now_str = datetime.now().isoformat()

    with open(out_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in racers:
            writer.writerow({
                'racer_number': r.get('no', ''),
                'name': r.get('name', ''),
                'name_kana': r.get('kana', ''),
                'registration_period': r.get('ki', '') or None,
                'branch': r.get('shibu', '') or None,
                'rank': r.get('kyu', '') or None,
                'fetched_at': now_str,
            })

    print(f'CSV 保存: {out_path} ({len(racers)}件)')


def main():
    parser = argparse.ArgumentParser(description='女性レーサーマスターリスト取得')
    parser.add_argument('--out', default=DEFAULT_OUT, help=f'出力CSVパス (デフォルト: {DEFAULT_OUT})')
    parser.add_argument('--delay', type=float, default=0.5, help='ページ間ディレイ秒 (デフォルト: 0.5)')
    args = parser.parse_args()

    print(f'女性レーサーマスターリスト取得開始')
    print(f'出力先: {args.out}')
    print()

    racers = fetch_all_pages(delay=args.delay)
    save_csv(racers, args.out)

    print()
    print('=== 完了 ===')
    print(f'取得件数: {len(racers)}人')
    print()
    print('次のステップ:')
    print('  python scripts/data_collection/import_racers_csv.py  # ladies_master.csv を自動参照してgenderを更新')


if __name__ == '__main__':
    main()
