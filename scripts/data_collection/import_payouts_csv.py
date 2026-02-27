"""
払戻金 CSV を DB に投入するスクリプト（Phase 2）

補完_払戻金データ.py（Phase 1）で生成した CSV を DB に UPSERT 投入する。
毎日収集と時間帯が被っても競合しない（WAL モードを前提）。

【使用例】
  # ドライランで件数確認のみ
  python scripts/data_collection/import_payouts_csv.py --dir data/payouts_csv --dry-run

  # 全 CSV を投入
  python scripts/data_collection/import_payouts_csv.py --dir data/payouts_csv

  # 特定年度のみ
  python scripts/data_collection/import_payouts_csv.py --dir data/payouts_csv/2023

  # 単一ファイル
  python scripts/data_collection/import_payouts_csv.py data/payouts_csv/2023/2023-06-01.csv

【UPSERT 方式】
  INSERT INTO payouts(race_id, bet_type, combination, amount, popularity)
  ON CONFLICT(race_id, bet_type, combination) DO UPDATE SET
    amount=excluded.amount, popularity=excluded.popularity
  → 既存行の id・created_at を保持したまま上書き
"""
import sys
import os
import io
import csv
import argparse
import sqlite3
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)


DB_PATH = "data/boatrace.db"
BATCH_SIZE = 500  # UPSERT バッチサイズ


def collect_csv_files(paths: list) -> list:
    """ファイル or ディレクトリから CSV を収集"""
    result = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix == '.csv':
            result.append(path)
        elif path.is_dir():
            result.extend(sorted(path.rglob('*.csv')))
        else:
            print(f"[!] スキップ（対象外）: {p}")
    return sorted(set(result))


def count_csv_rows(csv_path: Path) -> int:
    """CSV の行数（ヘッダー除く）"""
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            return sum(1 for _ in csv.DictReader(f))
    except Exception:
        return -1


def upsert_payouts_batch(conn, rows: list) -> tuple:
    """
    payouts を UPSERT する
    rows: [{'race_id':..., 'bet_type':..., 'combination':..., 'amount':..., 'popularity':...}, ...]
    Returns: (inserted, updated, errors)
    """
    sql = """
        INSERT INTO payouts(race_id, bet_type, combination, amount, popularity)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(race_id, bet_type, combination) DO UPDATE SET
            amount     = excluded.amount,
            popularity = excluded.popularity
    """
    inserted = 0
    errors = 0
    cur = conn.cursor()

    for row in rows:
        try:
            race_id    = int(row['race_id'])
            bet_type   = row['bet_type']
            combination = row['combination']
            amount     = int(row['amount']) if row.get('amount') not in (None, '', 'None') else None
            popularity = int(row['popularity']) if row.get('popularity') not in (None, '', 'None') else None

            if amount is None:
                errors += 1
                continue

            cur.execute(sql, (race_id, bet_type, combination, amount, popularity))
            inserted += 1

        except (ValueError, TypeError) as e:
            errors += 1

    return inserted, errors


def import_csv_file(conn, csv_path: Path, dry_run: bool) -> dict:
    """1ファイルを読み込んで DB 投入"""
    rows = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        return {'file': csv_path.name, 'rows': 0, 'inserted': 0, 'errors': 1, 'error_msg': str(e)}

    if not rows:
        return {'file': csv_path.name, 'rows': 0, 'inserted': 0, 'errors': 0}

    if dry_run:
        return {'file': csv_path.name, 'rows': len(rows), 'inserted': 0, 'errors': 0, 'dry_run': True}

    total_inserted = 0
    total_errors = 0

    # バッチ単位で UPSERT
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        inserted, errors = upsert_payouts_batch(conn, batch)
        total_inserted += inserted
        total_errors += errors

    conn.commit()

    return {
        'file': csv_path.name,
        'rows': len(rows),
        'inserted': total_inserted,
        'errors': total_errors,
    }


def main():
    parser = argparse.ArgumentParser(
        description='払戻金 CSV を DB に投入（Phase 2）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('files', nargs='*', metavar='CSV_FILE',
                        help='投入する CSV ファイル（複数指定可）')
    parser.add_argument('--dir', action='append', metavar='CSV_DIR', dest='dirs',
                        help='投入する CSV ディレクトリ（複数指定可、再帰的に *.csv を収集）')
    parser.add_argument('--dry-run', action='store_true',
                        help='DB 投入せず件数確認のみ')
    args = parser.parse_args()

    all_paths = list(args.files or []) + list(args.dirs or [])
    if not all_paths:
        parser.print_help()
        sys.exit(1)

    csv_files = collect_csv_files(all_paths)
    if not csv_files:
        print("対象 CSV ファイルが見つかりません。")
        sys.exit(1)

    print("="*80)
    print(f"払戻金 CSV → DB 投入 Phase 2")
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}対象ファイル: {len(csv_files)}個")
    print("="*80)

    # 総行数の事前確認
    total_rows_estimate = sum(count_csv_rows(f) for f in csv_files)
    print(f"総行数（概算）: {total_rows_estimate:,}行")
    if args.dry_run:
        print("\n[DRY-RUN] DB 投入はしません。件数確認のみ。")

    conn = None
    if not args.dry_run:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

    total_inserted = 0
    total_errors = 0
    processed_files = 0

    import time
    start_time = time.time()

    for i, csv_path in enumerate(csv_files, 1):
        result = import_csv_file(conn, csv_path, args.dry_run)
        processed_files += 1
        total_inserted += result.get('inserted', 0)
        total_errors += result.get('errors', 0)

        if result.get('error_msg'):
            print(f"[{i}/{len(csv_files)}] ERROR {result['file']}: {result['error_msg']}")
        elif args.dry_run:
            print(f"[{i}/{len(csv_files)}] {result['file']}: {result['rows']}行")
        else:
            print(f"[{i}/{len(csv_files)}] {result['file']}: {result['rows']}行 投入={result['inserted']} エラー={result['errors']}")

        # 進捗表示（50ファイルごと）
        if i % 50 == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed
            remaining = (len(csv_files) - i) / rate if rate > 0 else 0
            print(f"\n  進捗: {i}/{len(csv_files)}ファイル - {rate:.1f}ファイル/秒 - 残り約{remaining/60:.1f}分\n")

    if conn:
        conn.close()

    elapsed_total = time.time() - start_time

    print("\n" + "="*80)
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Phase 2 完了")
    print("="*80)
    print(f"処理ファイル数:  {processed_files}")
    print(f"総行数（概算）:  {total_rows_estimate:,}")
    if not args.dry_run:
        print(f"DB 投入成功:    {total_inserted:,}")
        print(f"DB 投入エラー:  {total_errors:,}")
    print(f"処理時間:        {elapsed_total/60:.1f}分")
    print("="*80)


if __name__ == "__main__":
    main()
