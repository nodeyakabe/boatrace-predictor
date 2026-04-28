"""
選手プロフィール一括取得スクリプト

データソース: https://www.boatrace.jp/owpc/pc/data/racersearch/profile?toban=XXXX
  - Selenium 不要（requests + BeautifulSoup）
  - 公式サイト（br-racers.jp サードパーティ依存なし）

対象: entries テーブルに存在する全 racer_number（2,131人）
出力: data/csv/racers/profiles.csv

再起動耐性:
  - 出力 CSV を起動時に読み込み、処理済みをスキップ
  - 途中停止後に再実行すれば続きから処理

性別:
  - races.is_ladies=1 のレースに出場した選手番号 → female
  - それ以外 → male（保守的）
  ※ backfill_is_ladies_v2.py で is_ladies を先に更新しておくこと

使い方:
  python scripts/data_collection/fetch_racer_profiles.py             # 全件
  python scripts/data_collection/fetch_racer_profiles.py --test 20  # テスト20件
  python scripts/data_collection/fetch_racer_profiles.py --workers 8
  python scripts/data_collection/fetch_racer_profiles.py --only-missing  # 欠損529人のみ
"""

import os
import sys
import csv
import time
import sqlite3
import argparse
import threading
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'csv', 'racers')
PROFILES_CSV = os.path.join(OUTPUT_DIR, 'profiles.csv')

PROFILE_URL = 'https://www.boatrace.jp/owpc/pc/data/racersearch/profile?toban={}'
DELAY = 0.5  # 1ワーカーあたりの間隔（秒）

FIELDNAMES = [
    'racer_number', 'name', 'name_kana', 'gender',
    'birth_date', 'height', 'weight', 'blood_type',
    'branch', 'hometown', 'registration_period', 'rank',
    'updated_at', 'fetch_status',
]

CSV_LOCK = threading.Lock()


def get_female_racer_numbers(conn: sqlite3.Connection) -> set:
    """races.is_ladies=1 のレースに出場した選手番号を取得（性別判定用）"""
    rows = conn.execute("""
        SELECT DISTINCT e.racer_number
        FROM entries e
        JOIN races r ON e.race_id = r.id
        WHERE r.is_ladies = 1
    """).fetchall()
    return {row[0] for row in rows}


def get_target_racer_numbers(conn: sqlite3.Connection, only_missing: bool) -> list:
    """取得対象の racer_number リストを返す"""
    if only_missing:
        rows = conn.execute("""
            SELECT DISTINCT e.racer_number
            FROM entries e
            LEFT JOIN racers r ON e.racer_number = r.racer_number
            WHERE r.racer_number IS NULL
            ORDER BY e.racer_number
        """).fetchall()
    else:
        rows = conn.execute(
            'SELECT DISTINCT racer_number FROM entries ORDER BY racer_number'
        ).fetchall()
    return [row[0] for row in rows]


def load_processed_numbers(csv_path: str) -> set:
    """処理済み racer_number を CSV から読み込む"""
    processed = set()
    if not os.path.exists(csv_path):
        return processed
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            num = row.get('racer_number', '').strip()
            if num:
                processed.add(num)
    return processed


def parse_profile(html: str, racer_number: str) -> dict:
    """公式プロフィールページの HTML をパースして選手情報を返す"""
    soup = BeautifulSoup(html, 'html.parser')
    data = {'racer_number': racer_number}

    # 選手名（.racer1_bodyName）
    name_elem = soup.select_one('.racer1_bodyName')
    if name_elem:
        data['name'] = name_elem.get_text(strip=True).replace('　', ' ')

    # カナ（.racer1_bodyKana）
    kana_elem = soup.select_one('.racer1_bodyKana')
    if kana_elem:
        data['name_kana'] = kana_elem.get_text(strip=True).replace('　', ' ')

    # プロフィール dl/dt/dd
    for dl in soup.find_all('dl'):
        dts = dl.find_all('dt')
        dds = dl.find_all('dd')
        for dt, dd in zip(dts, dds):
            label = dt.get_text(strip=True)
            value = dd.get_text(strip=True)
            if not value:
                continue
            _map_field(data, label, value)

    return data


def _map_field(data: dict, label: str, value: str):
    """ラベルと値を data dict にマッピング"""
    if '登録番号' in label:
        pass  # 既知
    elif '生年月日' in label:
        m = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', value)
        if m:
            data['birth_date'] = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    elif '身長' in label:
        m = re.search(r'(\d+(?:\.\d+)?)', value)
        if m:
            data['height'] = float(m.group(1))
    elif '体重' in label:
        m = re.search(r'(\d+(?:\.\d+)?)', value)
        if m:
            data['weight'] = float(m.group(1))
    elif '血液型' in label:
        data['blood_type'] = value
    elif '支部' in label:
        data['branch'] = value
    elif '出身地' in label:
        data['hometown'] = value
    elif '登録期' in label:
        m = re.search(r'(\d+)', value)
        if m:
            data['registration_period'] = int(m.group(1))
    elif '級別' in label:
        m = re.search(r'([AB][12])', value)
        if m:
            data['rank'] = m.group(1)


def fetch_one(racer_number: str, session: requests.Session) -> dict:
    """1選手のプロフィールを取得してパース"""
    time.sleep(DELAY)  # ワーカー内でレート制御（並列数に依存しない固定待機）
    url = PROFILE_URL.format(racer_number)
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        data = parse_profile(resp.text, racer_number)
        # プロフィールなし（引退・存在しない選手）の検出
        if not data.get('name'):
            data['fetch_status'] = 'no_profile'
        else:
            data['fetch_status'] = 'ok'
        return data
    except requests.exceptions.HTTPError as e:
        return {'racer_number': racer_number, 'fetch_status': f'http_{e.response.status_code}'}
    except Exception as e:
        return {'racer_number': racer_number, 'fetch_status': f'error:{type(e).__name__}'}


def main():
    parser = argparse.ArgumentParser(description='選手プロフィール一括取得')
    parser.add_argument('--test', type=int, help='テスト件数（指定すると先頭N件のみ）')
    parser.add_argument('--workers', type=int, default=4, help='並列ワーカー数（デフォルト4）')
    parser.add_argument('--only-missing', action='store_true',
                        help='racers テーブルに存在しない選手のみ取得')
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    # 性別判定: is_ladies=1 レースに出場した選手 → female
    print('女性選手番号を取得中（races.is_ladies=1 ベース）...', end='', flush=True)
    female_numbers = get_female_racer_numbers(conn)
    print(f' {len(female_numbers)}人')

    if len(female_numbers) == 0:
        print('[警告] 女性選手番号が0人。先に backfill_is_ladies_v2.py を実行してください。')
        print('  性別は全員 male として仮設定します。')

    # 対象選手リスト
    all_targets = get_target_racer_numbers(conn, args.only_missing)
    conn.close()

    mode_label = '欠損選手のみ' if args.only_missing else '全選手'
    print(f'対象: {len(all_targets)}人 ({mode_label})')

    # 処理済みスキップ
    processed = load_processed_numbers(PROFILES_CSV)
    targets = [n for n in all_targets if n not in processed]

    if args.test:
        targets = targets[:args.test]

    print(f'処理済み: {len(processed)}人 / 今回処理: {len(targets)}人')

    if not targets:
        print('全員処理済みです。')
        return

    # CSV 書き込み（追記モード）
    write_header = not os.path.exists(PROFILES_CSV) or os.path.getsize(PROFILES_CSV) == 0

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    success_count = 0
    error_count = 0
    female_found = 0
    start_time = time.time()

    with open(PROFILES_CSV, 'a', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
        if write_header:
            writer.writeheader()

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(fetch_one, num, session): num
                for num in targets
            }

            for i, future in enumerate(as_completed(futures), 1):
                racer_number = futures[future]
                try:
                    data = future.result()
                except Exception as e:
                    data = {'racer_number': racer_number, 'fetch_status': f'exception:{e}'}

                # 性別設定
                is_female = racer_number in female_numbers
                data['gender'] = 'female' if is_female else 'male'
                data['updated_at'] = datetime.now().isoformat()

                with CSV_LOCK:
                    writer.writerow(data)
                    f.flush()

                status = data.get('fetch_status', '')
                if status == 'ok':
                    success_count += 1
                    if is_female:
                        female_found += 1
                    # 進捗表示
                    if i % 100 == 0 or is_female:
                        elapsed = time.time() - start_time
                        rate = i / elapsed if elapsed > 0 else 0
                        eta = (len(targets) - i) / rate if rate > 0 else 0
                        gender_mark = '♀' if is_female else '♂'
                        name = data.get('name', '?')
                        print(f'[{i}/{len(targets)}] {name} ({racer_number}) {gender_mark}'
                              f'  速度:{rate:.1f}件/秒  残:{eta/60:.1f}分')
                else:
                    error_count += 1
                    if error_count <= 10 or i % 200 == 0:
                        print(f'[{i}/{len(targets)}] NG {racer_number}: {status}')

                pass  # レート制御は fetch_one 内で実施

    session.close()

    elapsed_total = time.time() - start_time
    print(f'\n=== 完了 ===')
    print(f'成功: {success_count}人 / エラー: {error_count}人')
    print(f'女性選手: {female_found}人 (is_ladies レース出場者)')
    print(f'経過時間: {elapsed_total/60:.1f}分')
    print(f'CSV: {PROFILES_CSV}')
    print()
    print('次のステップ:')
    print('  python scripts/data_collection/import_racers_csv.py')


if __name__ == '__main__':
    main()
