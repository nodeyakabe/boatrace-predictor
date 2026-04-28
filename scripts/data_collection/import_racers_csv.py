"""
選手プロフィール CSV → racers テーブル 投入スクリプト

入力: data/csv/racers/profiles.csv（fetch_racer_profiles.py の出力）
処理: ON CONFLICT(racer_number) DO UPDATE SET ... でUPSERT

性別判定（優先順）:
  1. ladies_master.csv（ladies-info.jp 公式リスト・現役女性選手278人）→ 最優先
  2. is_ladies=1 レースに GENDER_THRESHOLD 回以上出場 → フォールバック
  3. 上記いずれにも該当しない → male

使い方:
  python scripts/data_collection/import_racers_csv.py
  python scripts/data_collection/import_racers_csv.py --dry-run  # 件数確認のみ
  python scripts/data_collection/import_racers_csv.py --csv data/csv/racers/profiles.csv
"""

import os
import sys
import csv
import sqlite3
import argparse
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import GENDER_LADIES_THRESHOLD

DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')
DEFAULT_CSV = os.path.join(PROJECT_ROOT, 'data', 'csv', 'racers', 'profiles.csv')
LADIES_MASTER_CSV = os.path.join(PROJECT_ROOT, 'data', 'csv', 'racers', 'ladies_master.csv')

GENDER_THRESHOLD = GENDER_LADIES_THRESHOLD  # config/settings.py で一元管理


def safe_float(v):
    try:
        return float(v) if v not in (None, '', 'None') else None
    except (ValueError, TypeError):
        return None


def safe_int(v):
    try:
        return int(v) if v not in (None, '', 'None') else None
    except (ValueError, TypeError):
        return None


def safe_str(v):
    return v if v not in (None, '', 'None') else None


def load_ladies_master(master_path: str) -> set:
    """
    ladies-info.jp から取得した公式女性レーサーリスト（fetch_ladies_master.py の出力）を読み込む。
    ファイルが存在しない場合は空セットを返す（フォールバックへ委譲）。
    """
    if not os.path.exists(master_path):
        print(f'[警告] ladies_master.csv が見つかりません: {master_path}')
        print('  fetch_ladies_master.py を実行してください。フォールバック（50回閾値）を使用します。')
        return set()

    numbers = set()
    with open(master_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            num = row.get('racer_number', '').strip()
            if num:
                numbers.add(num)
    return numbers


def get_threshold_female_numbers(conn: sqlite3.Connection) -> set:
    """
    is_ladies=1 レースに GENDER_THRESHOLD 回以上出場した選手番号を返す（フォールバック）。
    ladies_master.csv が存在する場合は補完用途のみ。
    """
    rows = conn.execute(f"""
        SELECT e.racer_number
        FROM entries e JOIN races r ON e.race_id = r.id
        WHERE r.is_ladies = 1
        GROUP BY e.racer_number
        HAVING COUNT(*) >= {GENDER_THRESHOLD}
    """).fetchall()
    return {row[0] for row in rows}


def import_csv(csv_path: str, db_path: str, dry_run: bool):
    if not os.path.exists(csv_path):
        print(f'エラー: CSV が見つかりません: {csv_path}')
        return

    rows = []
    error_rows = 0
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            num = row.get('racer_number', '').strip()
            status = row.get('fetch_status', '')
            if not num:
                continue
            if status == 'no_profile' or (status not in ('ok', '') and not status.startswith('ok')):
                error_rows += 1
                continue
            rows.append(row)

    print(f'CSV 読み込み: {len(rows)}件 (エラー行スキップ: {error_rows}件)')

    if dry_run:
        print('[DRY-RUN] DB更新をスキップ。件数のみ表示。')
        return

    conn = sqlite3.connect(db_path)

    # is_ladies バックフィル完了の安全確認
    ladies_race_count = conn.execute('SELECT COUNT(*) FROM races WHERE is_ladies=1').fetchone()[0]
    if ladies_race_count < 7000:
        print(f'[警告] is_ladies=1 のレース数が少なすぎます（{ladies_race_count}件 < 7000件）。')
        print('  backfill_is_ladies_v2.py が完了しているか確認してください。')
        conn.close()
        return

    before_count = conn.execute('SELECT COUNT(*) FROM racers').fetchone()[0]
    print(f'投入前 racers 件数: {before_count}人')
    print(f'is_ladies=1 レース数: {ladies_race_count}件 (安全確認OK)')

    # 性別マスターの構築（優先順）
    ladies_master = load_ladies_master(LADIES_MASTER_CSV)
    threshold_females = get_threshold_female_numbers(conn)
    # 両方の和集合を正式な female セットとする
    all_female_numbers = ladies_master | threshold_females
    print(f'性別マスター: ladies_master={len(ladies_master)}人 / 閾値{GENDER_THRESHOLD}回={len(threshold_females)}人 / 合計={len(all_female_numbers)}人')

    upserted = 0
    now_str = datetime.now().isoformat()

    for row in rows:
        racer_number = row.get('racer_number', '').strip()
        name = safe_str(row.get('name'))
        name_kana = safe_str(row.get('name_kana'))
        # ladies_master（公式）または閾値判定で female、それ以外は male
        gender = 'female' if racer_number in all_female_numbers else 'male'
        birth_date = safe_str(row.get('birth_date'))
        height = safe_float(row.get('height'))
        weight = safe_float(row.get('weight'))
        blood_type = safe_str(row.get('blood_type'))
        branch = safe_str(row.get('branch'))
        hometown = safe_str(row.get('hometown'))
        registration_period = safe_int(row.get('registration_period'))
        rank = safe_str(row.get('rank'))
        updated_at = safe_str(row.get('updated_at')) or now_str

        conn.execute("""
            INSERT INTO racers (
                racer_number, name, name_kana, gender, birth_date,
                height, weight, blood_type, branch, hometown,
                registration_period, rank, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(racer_number) DO UPDATE SET
                name             = COALESCE(excluded.name, racers.name),
                name_kana        = COALESCE(excluded.name_kana, racers.name_kana),
                gender           = excluded.gender,
                birth_date       = COALESCE(excluded.birth_date, racers.birth_date),
                height           = COALESCE(excluded.height, racers.height),
                weight           = COALESCE(excluded.weight, racers.weight),
                blood_type       = COALESCE(excluded.blood_type, racers.blood_type),
                branch           = COALESCE(excluded.branch, racers.branch),
                hometown         = COALESCE(excluded.hometown, racers.hometown),
                registration_period = COALESCE(excluded.registration_period, racers.registration_period),
                rank             = COALESCE(excluded.rank, racers.rank),
                updated_at       = excluded.updated_at
        """, (
            racer_number, name, name_kana, gender, birth_date,
            height, weight, blood_type, branch, hometown,
            registration_period, rank, updated_at
        ))
        upserted += 1

        if upserted % 500 == 0:
            conn.commit()
            print(f'  {upserted}/{len(rows)}件 投入中...')

    conn.commit()

    after_count = conn.execute('SELECT COUNT(*) FROM racers').fetchone()[0]
    female_count = conn.execute("SELECT COUNT(*) FROM racers WHERE gender='female'").fetchone()[0]
    male_count = conn.execute("SELECT COUNT(*) FROM racers WHERE gender='male'").fetchone()[0]
    null_count = conn.execute("SELECT COUNT(*) FROM racers WHERE gender IS NULL").fetchone()[0]

    conn.close()

    print(f'\n=== 完了 ===')
    print(f'UPSERT: {upserted}件')
    print(f'投入後 racers 件数: {after_count}人 (増加: +{after_count - before_count}人)')
    print(f'  female: {female_count}人')
    print(f'  male:   {male_count}人')
    print(f'  NULL:   {null_count}人')


def main():
    parser = argparse.ArgumentParser(description='選手プロフィール CSV → DB 投入')
    parser.add_argument('--csv', default=DEFAULT_CSV, help=f'入力CSVパス (デフォルト: {DEFAULT_CSV})')
    parser.add_argument('--dry-run', action='store_true', help='DB更新せず件数のみ表示')
    args = parser.parse_args()

    import_csv(args.csv, DB_PATH, args.dry_run)


if __name__ == '__main__':
    main()
