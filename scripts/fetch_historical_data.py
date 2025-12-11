# -*- coding: utf-8 -*-
"""過去データ一括取得スクリプト

過去の特定期間のレースデータを取得し、DBに保存・予測を生成するスクリプト。
データ欠損時に手動で実行することを想定。

使用例:
    # 特定期間のデータ取得（データ取得+結果取得+オッズ取得+予測生成）
    python scripts/fetch_historical_data.py --start 2025-12-02 --end 2025-12-04

    # 予測生成なし
    python scripts/fetch_historical_data.py --start 2025-12-02 --end 2025-12-04 --no-predict

    # ドライラン（実際には取得しない）
    python scripts/fetch_historical_data.py --start 2025-12-02 --end 2025-12-04 --dry-run

    # 特定会場のみ
    python scripts/fetch_historical_data.py --start 2025-12-02 --end 2025-12-04 --venues 01,07,21

    # 不足データの確認のみ
    python scripts/fetch_historical_data.py --start 2025-12-01 --end 2025-12-11 --check-only
"""

import sys
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.scraper.race_scraper_v2 import RaceScraperV2
from src.scraper.result_scraper import ResultScraper
from src.database.fast_data_manager import FastDataManager

# 全24競艇場コード
ALL_VENUES = [
    '01', '02', '03', '04', '05', '06', '07', '08', '09', '10',
    '11', '12', '13', '14', '15', '16', '17', '18', '19', '20',
    '21', '22', '23', '24'
]

VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川',
    '06': '浜名湖', '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国',
    '11': 'びわこ', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀',
    '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}


def get_date_range(start_date: str, end_date: str):
    """日付範囲をリストで返す"""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    return dates


def check_existing_data(db_path: Path, race_date: str):
    """指定日の既存データを確認"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT COUNT(*) FROM races WHERE race_date = ?
    ''', (race_date,))
    race_count = cursor.fetchone()[0]

    cursor.execute('''
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        INNER JOIN results res ON r.id = res.race_id
        WHERE r.race_date = ?
    ''', (race_date,))
    result_count = cursor.fetchone()[0]

    cursor.execute('''
        SELECT COUNT(DISTINCT rp.race_id)
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date = ? AND rp.prediction_type = 'advance'
    ''', (race_date,))
    pred_count = cursor.fetchone()[0]

    conn.close()
    return race_count, result_count, pred_count


def fetch_single_race(race_scraper: RaceScraperV2, result_scraper: ResultScraper,
                       data_manager: FastDataManager,
                       venue_code: str, race_date: str, race_number: int):
    """単一レースのデータを取得して保存"""
    try:
        # YYYYMMDD形式に変換
        race_date_yyyymmdd = race_date.replace('-', '')

        # 出走表取得
        race_data = race_scraper.get_race_card(venue_code, race_date_yyyymmdd, race_number)
        if not race_data or not race_data.get('entries'):
            return None, "出走表取得失敗"

        # レースデータにメタ情報追加（YYYYMMDD形式で渡す）
        race_data['venue_code'] = venue_code
        race_data['race_date'] = race_date_yyyymmdd
        race_data['race_number'] = race_number

        # DB保存（FastDataManagerの正しいメソッド名を使用）
        race_id = data_manager.save_race_data_fast(race_data)

        # レース結果取得（ResultScraperを使用）
        result_data = result_scraper.get_race_result(venue_code, race_date_yyyymmdd, race_number)

        if race_id and result_data:
            # 結果データにメタ情報を追加
            result_data['venue_code'] = venue_code
            result_data['race_date'] = race_date_yyyymmdd
            result_data['race_number'] = race_number
            data_manager.save_race_result_fast(result_data)

        # 変更をコミット
        data_manager.commit_batch()

        return race_id, None
    except Exception as e:
        return None, str(e)


def fetch_venue_day(race_scraper: RaceScraperV2, result_scraper: ResultScraper,
                    data_manager: FastDataManager,
                    venue_code: str, race_date: str, dry_run: bool = False):
    """1会場1日分のデータを取得"""
    venue_name = VENUE_NAMES.get(venue_code, venue_code)
    success_count = 0
    errors = []

    for race_number in range(1, 13):
        if dry_run:
            continue

        race_id, error = fetch_single_race(race_scraper, result_scraper, data_manager,
                                            venue_code, race_date, race_number)
        if race_id:
            success_count += 1
        elif error:
            errors.append(f"R{race_number}: {error[:50]}")
        time.sleep(0.3)  # レート制限

    return venue_code, success_count, errors


def generate_predictions(db_path: Path, race_date: str):
    """指定日のレースに対して予測を生成"""
    try:
        from src.prediction.predictor import Predictor

        predictor = Predictor(str(db_path))

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, venue_code, race_number FROM races
            WHERE race_date = ?
            ORDER BY venue_code, race_number
        ''', (race_date,))
        races = cursor.fetchall()
        conn.close()

        success_count = 0
        for race_id, venue_code, race_number in races:
            try:
                predictor.predict_race(race_id, prediction_type='advance')
                success_count += 1
            except Exception as e:
                pass  # 予測エラーは無視

        return success_count
    except Exception as e:
        print(f"  [予測エラー]: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description='過去データ一括取得')
    parser.add_argument('--start', type=str, required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--venues', type=str, help='会場コード（カンマ区切り、省略時は全会場）')
    parser.add_argument('--no-predict', action='store_true', help='予測生成をスキップ')
    parser.add_argument('--dry-run', action='store_true', help='実際には取得しない')
    parser.add_argument('--workers', type=int, default=4, help='並列数（デフォルト: 4）')
    parser.add_argument('--skip-existing', action='store_true', help='既存データがある日はスキップ')
    parser.add_argument('--check-only', action='store_true', help='不足データの確認のみ')
    args = parser.parse_args()

    db_path = ROOT_DIR / 'data' / 'boatrace.db'

    # 対象会場
    if args.venues:
        venues = args.venues.split(',')
    else:
        venues = ALL_VENUES

    # 対象日付
    dates = get_date_range(args.start, args.end)

    print("=" * 70)
    print("過去データ一括取得")
    print("=" * 70)
    print(f"期間: {args.start} ～ {args.end} ({len(dates)}日間)")
    print(f"会場: {len(venues)}会場")
    if not args.check_only:
        print(f"並列数: {args.workers}")
        print(f"予測生成: {'OFF' if args.no_predict else 'ON'}")
        print(f"ドライラン: {'ON' if args.dry_run else 'OFF'}")
    print()

    # 既存データ確認
    print("=== 既存データ確認 ===")
    missing_dates = []
    for date in dates:
        race_count, result_count, pred_count = check_existing_data(db_path, date)
        status = ""
        needs_fetch = False
        if race_count == 0:
            status = "[要取得]"
            needs_fetch = True
        elif result_count < race_count:
            status = f"[結果不足: {result_count}/{race_count}]"
            needs_fetch = True
        elif pred_count == 0:
            status = "[予測なし]"
        else:
            status = "[完了]"
        print(f"  {date}: {race_count}レース, 結果{result_count}件, 予測{pred_count}件 {status}")

        if needs_fetch:
            missing_dates.append(date)
    print()

    if args.check_only:
        print(f"不足データのある日: {len(missing_dates)}日")
        if missing_dates:
            print("  " + ", ".join(missing_dates))
        return

    if args.dry_run:
        print("[DRY-RUN] 実際のデータ取得はスキップします")
        return

    # スクレイパーとデータマネージャー初期化
    print("スクレイパー初期化中...")
    race_scraper = RaceScraperV2()
    result_scraper = ResultScraper()
    data_manager = FastDataManager(str(db_path))
    print("初期化完了")
    print()

    # 日付ごとに処理
    for date in dates:
        race_count, result_count, _ = check_existing_data(db_path, date)
        if args.skip_existing and race_count > 0 and result_count == race_count:
            print(f"\n[SKIP] {date}: 既存データあり ({race_count}レース)")
            continue

        print(f"\n{'='*50}")
        print(f"{date} のデータ取得")
        print(f"{'='*50}")

        # 会場を処理（シンプルに順次処理）
        total_success = 0
        for venue_code in venues:
            venue_name = VENUE_NAMES.get(venue_code, venue_code)
            venue_code, success, errors = fetch_venue_day(
                race_scraper, result_scraper, data_manager, venue_code, date, args.dry_run
            )
            if success > 0:
                print(f"  {venue_name}({venue_code}): {success}レース取得")
                total_success += success
            elif errors:
                # 非開催日のエラーは無視
                pass

        print(f"  → 合計: {total_success}レース取得")

        # 予測生成
        if not args.no_predict and total_success > 0:
            print(f"  → 予測生成中...")
            pred_count = generate_predictions(db_path, date)
            print(f"  → {pred_count}件の予測生成完了")

    print()
    print("=" * 70)
    print("処理完了")
    print("=" * 70)

    # 最終確認
    print("\n=== 最終データ確認 ===")
    for date in dates:
        race_count, result_count, pred_count = check_existing_data(db_path, date)
        status = ""
        if race_count == 0:
            status = "[データなし]"
        elif pred_count == 0:
            status = "[予測なし]"
        else:
            status = "[OK]"
        print(f"  {date}: {race_count}レース, 結果{result_count}件, 予測{pred_count}件 {status}")


if __name__ == '__main__':
    main()
