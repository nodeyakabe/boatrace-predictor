"""
払戻金データ補完スクリプト（CSV方式 Phase 1）

【役割】
  払戻金が欠損しているレースをスクレイピングして CSV に保存する。
  DB には一切触れない。毎日のデータ収集との競合ゼロ。

【Phase 2（DB投入）は別スクリプト】
  python scripts/data_collection/import_payouts_csv.py --dir data/payouts_csv

【出力先】
  data/payouts_csv/YYYY/YYYY-MM-DD.csv  （1日1ファイル）

【使用例】
  # 全期間を CSV 書き出し
  python scripts/data_collection/補完_払戻金データ.py --start-date 2020-01-01 --end-date 2026-02-25

  # 特定期間のみ
  python scripts/data_collection/補完_払戻金データ.py --start-date 2023-01-01 --end-date 2023-12-31

  # 既存 CSV を上書き（再取得）
  python scripts/data_collection/補完_払戻金データ.py --start-date 2023-01-01 --end-date 2023-01-31 --overwrite

【最適化（2026-02-25）】
  - ThreadPoolExecutor + max_workers=24（HTTP I/O 並列）
  - threading.local() でスクレイパー再利用（セッション再利用）
  - DB に触れないので毎日収集と競合しない
  - 中断再開対応: 既存 CSV がある日付はスキップ（--overwrite で上書き）
"""
import sys
import io
import os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

import argparse
import sqlite3
import csv
import threading
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.scraper.result_scraper import ResultScraper
import time

# スレッドローカルストレージ（スクレイパー再利用）
thread_local = threading.local()

CSV_OUTPUT_DIR = Path("data/payouts_csv")
CSV_COLUMNS = ["race_id", "venue_code", "race_date", "race_number",
               "bet_type", "combination", "amount", "popularity"]


def get_scraper():
    """スレッドローカルなスクレイパーを取得（セッション再利用）"""
    if not hasattr(thread_local, 'scraper'):
        thread_local.scraper = ResultScraper()
    return thread_local.scraper


def get_races_without_payouts(db_path="data/boatrace.db", start_date=None, end_date=None):
    """
    払戻金データが欠損しているレースを取得
    Returns: [(race_id, venue_code, race_date, race_number), ...]
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    date_filter = ""
    params = []

    if start_date and end_date:
        date_filter = "AND r.race_date BETWEEN ? AND ?"
        params = [start_date, end_date]
        print(f"期間フィルター: {start_date} ～ {end_date}")
    elif start_date:
        date_filter = "AND r.race_date >= ?"
        params = [start_date]
        print(f"期間フィルター: {start_date} 以降")
    elif end_date:
        date_filter = "AND r.race_date <= ?"
        params = [end_date]
        print(f"期間フィルター: {end_date} まで")
    else:
        print("期間フィルターなし（全期間対象）")

    query = f"""
        SELECT
            r.id,
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE NOT EXISTS (SELECT 1 FROM payouts p WHERE p.race_id = r.id)
          AND res.is_invalid = 0
          AND r.race_date < date('now')
          {date_filter}
        GROUP BY r.id
        ORDER BY r.race_date ASC, r.venue_code, r.race_number
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    print(f"払戻金データが欠損しているレース: {len(rows)}件")
    return rows


def get_dates_with_existing_csv(output_dir: Path) -> set:
    """既存 CSV がある日付セットを返す"""
    dates = set()
    for csv_file in output_dir.rglob("*.csv"):
        dates.add(csv_file.stem)  # YYYY-MM-DD
    return dates


def fetch_payout(args):
    """1レースの払戻金データを取得（スクレイパー再利用版）"""
    race_id, venue_code, race_date, race_number = args
    date_str = race_date.replace('-', '')

    scraper = get_scraper()

    try:
        data = scraper.get_payouts_and_kimarite(venue_code, date_str, race_number)

        if data and data.get('payouts'):
            return {
                'race_id': race_id,
                'venue_code': venue_code,
                'race_date': race_date,
                'race_number': race_number,
                'payouts': data['payouts']
            }
        return None

    except Exception as e:
        print(f"取得エラー: {venue_code} {race_date} R{race_number} - {e}")
        # 壊れたセッションをリセット
        try:
            thread_local.scraper.close()
        except Exception:
            pass
        if hasattr(thread_local, 'scraper'):
            del thread_local.scraper
        return None


def save_results_to_csv(results_by_date: dict, output_dir: Path, overwrite: bool):
    """
    日付ごとに CSV 保存
    results_by_date: {race_date: [result_dict, ...]}
    """
    saved_files = 0
    saved_rows = 0

    for race_date in sorted(results_by_date.keys()):
        year = race_date[:4]
        dir_path = output_dir / year
        dir_path.mkdir(parents=True, exist_ok=True)
        csv_path = dir_path / f"{race_date}.csv"

        if csv_path.exists() and not overwrite:
            # 既存ファイルに追記（同日の複数バッチ対応）
            mode = 'a'
            write_header = False
        else:
            mode = 'w'
            write_header = True

        with open(csv_path, mode, newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            if write_header:
                writer.writeheader()

            for result in results_by_date[race_date]:
                for bet_type, payout_list in result['payouts'].items():
                    if not isinstance(payout_list, list):
                        continue
                    for payout in payout_list:
                        combination_val = (
                            payout.get('combination') or
                            str(payout.get('pit_number', ''))
                        )
                        row = {
                            'race_id': result['race_id'],
                            'venue_code': result['venue_code'],
                            'race_date': race_date,
                            'race_number': result['race_number'],
                            'bet_type': bet_type,
                            'combination': combination_val,
                            'amount': payout.get('amount', ''),
                            'popularity': payout.get('popularity', ''),
                        }
                        writer.writerow(row)
                        saved_rows += 1

        saved_files += 1

    return saved_files, saved_rows


def main():
    parser = argparse.ArgumentParser(
        description='払戻金補完 Phase 1: スクレイピング → CSV保存（DB触れない）'
    )
    parser.add_argument('--start-date', type=str, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--workers', type=int, default=24, help='並列スレッド数（デフォルト: 24）')
    parser.add_argument('--overwrite', action='store_true',
                        help='既存 CSV を上書き（デフォルト: 既存日付はスキップ）')
    args = parser.parse_args()

    print("="*80)
    print("払戻金データ補完 Phase 1（CSV方式）")
    print("DB には一切触れません。毎日収集との競合ゼロ。")
    print("="*80)
    print(f"並列スレッド数: {args.workers}")
    print(f"出力先: {CSV_OUTPUT_DIR}/YYYY/YYYY-MM-DD.csv")
    print(f"既存CSVの扱い: {'上書き' if args.overwrite else 'スキップ（中断再開対応）'}")

    # 既存 CSV がある日付を取得（スキップ用）
    existing_dates = get_dates_with_existing_csv(CSV_OUTPUT_DIR) if not args.overwrite else set()
    if existing_dates and not args.overwrite:
        print(f"既存 CSV: {len(existing_dates)}日分（スキップ対象）")

    # 欠損レース取得
    all_races = get_races_without_payouts(
        start_date=args.start_date,
        end_date=args.end_date
    )

    if len(all_races) == 0:
        print("\n補完が必要なレースはありません。")
        return

    # 既存 CSV がある日付のレースをスキップ
    if existing_dates and not args.overwrite:
        races = [r for r in all_races if r[2] not in existing_dates]
        skipped = len(all_races) - len(races)
        if skipped > 0:
            print(f"既存 CSV によりスキップ: {skipped}件")
    else:
        races = all_races

    if len(races) == 0:
        print("\n全対象レースは既に CSV 保存済みです。")
        print(f"再取得する場合は --overwrite オプションを使用してください。")
        return

    print(f"\n処理対象: {len(races)}件")
    print("\n処理を開始します...")

    max_workers = min(args.workers, len(races))
    start_time = time.time()
    success_count = 0
    error_count = 0

    # 取得結果を日付ごとに蓄積
    results_by_date = defaultdict(list)
    FLUSH_INTERVAL = 500  # 500件ごとに CSV に flush

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_payout, race): race for race in races}

        for i, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()

                if result and result.get('payouts'):
                    results_by_date[result['race_date']].append(result)
                    success_count += 1

                    # 3連単の払戻金を表示
                    trifecta = result['payouts'].get('trifecta', [])
                    if trifecta and isinstance(trifecta, list):
                        top = trifecta[0]
                        print(f"[{i}/{len(races)}] {result['venue_code']} {result['race_date']} R{result['race_number']:2d} - 3連単: {top.get('payout', 'N/A')}円")
                    else:
                        print(f"[{i}/{len(races)}] {result['venue_code']} {result['race_date']} R{result['race_number']:2d} - 取得成功")
                else:
                    error_count += 1

                # 進捗 + 定期 CSV flush（500件ごと）
                if i % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = i / elapsed
                    remaining = (len(races) - i) / rate if rate > 0 else 0
                    print(f"\n進捗: {i}/{len(races)} ({i/len(races)*100:.1f}%) - {rate:.1f}件/秒 - 残り約{remaining/60:.1f}分")

                if i % FLUSH_INTERVAL == 0 and results_by_date:
                    files, rows = save_results_to_csv(results_by_date, CSV_OUTPUT_DIR, args.overwrite)
                    print(f"[CSV flush] {files}ファイル / {rows}行 保存")
                    results_by_date.clear()

            except Exception as e:
                error_count += 1
                print(f"[{i}/{len(races)}] エラー: {e}")

    # 残りを CSV 保存
    if results_by_date:
        files, rows = save_results_to_csv(results_by_date, CSV_OUTPUT_DIR, args.overwrite)
        print(f"\n最終 CSV 保存: {files}ファイル / {rows}行")
        results_by_date.clear()

    elapsed_total = time.time() - start_time

    print("\n" + "="*80)
    print("Phase 1 完了")
    print("="*80)
    print(f"対象レース数: {len(races)}")
    print(f"取得成功:     {success_count}件")
    print(f"取得失敗:     {error_count}件")
    print(f"処理時間:     {elapsed_total/60:.1f}分")
    print(f"処理速度:     {len(races)/elapsed_total:.1f}件/秒")
    print(f"\n出力先: {CSV_OUTPUT_DIR}/")
    print("\n【次のステップ（Phase 2: DB投入）】")
    print(f"  python scripts/data_collection/import_payouts_csv.py --dir {CSV_OUTPUT_DIR} --dry-run")
    print(f"  python scripts/data_collection/import_payouts_csv.py --dir {CSV_OUTPUT_DIR}")
    print("="*80)


if __name__ == "__main__":
    main()
