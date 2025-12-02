"""
払戻金データの補完スクリプト（期間フィルター対応）

結果データは存在するが、払戻金データが取得できていないレースの
払戻金データを取得してDBに保存する
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import argparse
import sqlite3
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from src.scraper.result_scraper import ResultScraper
from src.database.data_manager import DataManager
import time

def get_races_without_payouts(db_path="data/boatrace.db", start_date=None, end_date=None):
    """
    払戻金データが欠損しているレースを取得

    Args:
        db_path: データベースパス
        start_date: 開始日 (YYYY-MM-DD)
        end_date: 終了日 (YYYY-MM-DD)

    Returns:
        list: [(race_id, venue_code, race_date, race_number), ...]
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 期間フィルター条件を構築
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

    # 結果データは存在するが、払戻金データがないレースを抽出
    query = f"""
        SELECT
            r.id,
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE r.id NOT IN (SELECT DISTINCT race_id FROM payouts)
          AND res.is_invalid = 0
          AND r.race_date < date('now')
          {date_filter}
        GROUP BY r.id
        ORDER BY r.race_date DESC, r.venue_code, r.race_number
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    print(f"払戻金データが欠損しているレース: {len(rows)}件")
    return rows

def fetch_payout(args):
    """
    1レースの払戻金データを取得

    Args:
        args: (race_id, venue_code, race_date, race_number)

    Returns:
        dict: 払戻金データ
    """
    race_id, venue_code, race_date, race_number = args

    # race_dateをYYYYMMDD形式に変換
    date_str = race_date.replace('-', '')

    scraper = ResultScraper()

    try:
        # 払戻金と決まり手を取得
        data = scraper.get_payouts_and_kimarite(venue_code, date_str, race_number)

        if data and data.get('payouts'):
            scraper.close()
            return {
                'race_id': race_id,
                'venue_code': venue_code,
                'race_date': race_date,
                'race_number': race_number,
                'payouts': data['payouts']
            }
        else:
            scraper.close()
            return None

    except Exception as e:
        print(f"取得エラー: {venue_code} {race_date} R{race_number} - {e}")
        scraper.close()
        return None

def save_payout_data(db, data):
    """
    払戻金データをデータベースに保存

    Args:
        db: DataManagerインスタンス
        data: 払戻金データ
    """
    race_id = data['race_id']
    payouts = data['payouts']

    try:
        db.save_payouts(race_id, payouts)
        return True

    except Exception as e:
        print(f"保存エラー: {data['venue_code']} {data['race_date']} R{data['race_number']} - {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='払戻金データ補完（期間指定対応）')
    parser.add_argument('--start-date', type=str, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='終了日 (YYYY-MM-DD)')
    args = parser.parse_args()

    print("="*80)
    print("払戻金データ補完スクリプト（期間フィルター対応）")
    print("="*80)

    # 1. 払戻金データが欠損しているレースを取得
    races = get_races_without_payouts(
        start_date=args.start_date,
        end_date=args.end_date
    )

    if len(races) == 0:
        print("\n補完が必要なレースはありません。")
        return

    print(f"\n補完対象: {len(races)}件")
    print("\n処理を開始します...")

    # 2. 並列で払戻金データを取得
    results = []
    success_count = 0
    error_count = 0

    start_time = time.time()

    # ProcessPoolExecutorで並列処理
    max_workers = min(8, len(races))

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_payout, race): race for race in races}

        for i, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()

                if result and result.get('payouts'):
                    results.append(result)
                    success_count += 1

                    # 3連単の払戻金を表示
                    trifecta = result['payouts'].get('trifecta', [])
                    if trifecta:
                        top_payout = trifecta[0] if isinstance(trifecta, list) else trifecta
                        print(f"[{i}/{len(races)}] 取得成功: {result['venue_code']} {result['race_date']} R{result['race_number']:2d} - 3連単: {top_payout.get('payout', 'N/A')}円")
                    else:
                        print(f"[{i}/{len(races)}] 取得成功: {result['venue_code']} {result['race_date']} R{result['race_number']:2d}")
                else:
                    error_count += 1
                    race = futures[future]
                    print(f"[{i}/{len(races)}] 取得失敗: {race[1]} {race[2]} R{race[3]}")

                # 進捗表示
                if i % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = i / elapsed
                    remaining = (len(races) - i) / rate if rate > 0 else 0
                    print(f"\n進捗: {i}/{len(races)} ({i/len(races)*100:.1f}%) - {rate:.1f}件/秒 - 残り約{remaining/60:.1f}分\n")

            except Exception as e:
                error_count += 1
                print(f"[{i}/{len(races)}] エラー: {e}")

    # 3. データベースに一括保存
    print("\n" + "="*80)
    print("データベースに保存中...")
    print("="*80)

    db = DataManager()
    saved_count = 0
    save_errors = 0

    for result in results:
        try:
            if save_payout_data(db, result):
                saved_count += 1

                if saved_count % 100 == 0:
                    print(f"保存済み: {saved_count}/{len(results)}")
            else:
                save_errors += 1

        except Exception as e:
            save_errors += 1
            print(f"保存エラー: {result['venue_code']} {result['race_date']} R{result['race_number']} - {e}")

    # 4. 最終集計
    elapsed_total = time.time() - start_time

    print("\n" + "="*80)
    print("最終集計")
    print("="*80)
    print(f"対象レース数: {len(races)}")
    print(f"取得成功: {success_count}件")
    print(f"取得失敗: {error_count}件")
    print(f"DB保存成功: {saved_count}件")
    print(f"DB保存失敗: {save_errors}件")
    print(f"処理時間: {elapsed_total/60:.1f}分")
    print(f"処理速度: {len(races)/elapsed_total:.1f}件/秒")
    print("="*80)

if __name__ == "__main__":
    main()
