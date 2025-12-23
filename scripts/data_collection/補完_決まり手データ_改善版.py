"""
決まり手データの補完スクリプト（改善版 - 期間フィルター対応）

改善点:
1. ThreadPoolExecutor使用（HTTP I/Oに最適）
2. ResultScraperを使わず直接HTTPリクエスト
3. セッション再利用で高速化
4. バッチDB更新でロック競合を回避
5. リトライ機能追加
6. 期間フィルター対応（--start-date, --end-date）
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import argparse
import sqlite3
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading

# スレッドローカルセッション
thread_local = threading.local()

def get_session():
    """スレッドローカルなセッションを取得"""
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
        thread_local.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    return thread_local.session

def get_races_without_kimarite(db_path="data/boatrace.db", start_date=None, end_date=None):
    """
    決まり手が欠損しているレースを取得

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

    # 結果データはあるが、決まり手がNULLのレースを抽出
    query = f"""
        SELECT DISTINCT
            r.id,
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE res.kimarite IS NULL
          AND res.rank = '1'
          AND res.is_invalid = 0
          {date_filter}
        ORDER BY r.race_date DESC, r.venue_code, r.race_number
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    print(f"決まり手が欠損しているレース: {len(rows)}件")
    return rows

def fetch_kimarite_fast(args, retry=3):
    """
    1レースの決まり手を高速取得（決まり手のみ）

    Args:
        args: (race_id, venue_code, race_date, race_number)
        retry: リトライ回数

    Returns:
        dict: {'race_id': id, 'kimarite': '逃げ', 'winning_technique': 1}
    """
    race_id, venue_code, race_date, race_number = args

    # race_dateをYYYYMMDD形式に変換
    date_str = race_date.replace('-', '')

    # URLを構築
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_number}&jcd={int(venue_code):02d}&hd={date_str}"

    for attempt in range(retry):
        try:
            session = get_session()
            response = session.get(url, timeout=10)
            response.raise_for_status()

            # エンコーディングを明示的に設定
            response.encoding = response.apparent_encoding

            # BeautifulSoupでパース
            soup = BeautifulSoup(response.text, 'lxml')

            # 決まり手テーブルを探す
            kimarite = None
            tables = soup.find_all('table')

            for table in tables:
                # theadからヘッダーをチェック
                thead = table.find('thead')
                if not thead:
                    continue

                headers = [th.get_text(strip=True) for th in thead.find_all('th')]

                if '決まり手' in headers:
                    tbody = table.find('tbody')
                    if tbody:
                        td = tbody.find('td')
                        if td:
                            kimarite_text = td.get_text(strip=True)
                            if kimarite_text and kimarite_text not in ['', ' ']:
                                kimarite = kimarite_text
                                break

            if kimarite:
                # 数値コードに変換
                kimarite_map = {
                    '逃げ': 1,
                    '差し': 2,
                    'まくり': 3,
                    'まくり差し': 4,
                    '抜き': 5,
                    '恵まれ': 6
                }
                winning_technique = kimarite_map.get(kimarite)

                return {
                    'race_id': race_id,
                    'kimarite': kimarite,
                    'winning_technique': winning_technique,
                    'venue_code': venue_code,
                    'race_date': race_date,
                    'race_number': race_number
                }
            else:
                # リトライ
                if attempt < retry - 1:
                    time.sleep(1)
                    continue
                else:
                    return None

        except Exception as e:
            # リトライ
            if attempt < retry - 1:
                time.sleep(1)
                continue
            else:
                return None

    return None

def update_kimarite_batch(conn, results):
    """
    決まり手をバッチ更新

    Args:
        conn: データベース接続
        results: 結果のリスト
    """
    cursor = conn.cursor()

    # バッチ更新
    for result in results:
        cursor.execute("""
            UPDATE results
            SET kimarite = ?, winning_technique = ?
            WHERE race_id = ? AND rank = '1'
        """, (result['kimarite'], result['winning_technique'], result['race_id']))

    conn.commit()

def main():
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='決まり手データ補完（期間指定対応）')
    parser.add_argument('--start-date', type=str, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='終了日 (YYYY-MM-DD)')
    args = parser.parse_args()

    print("="*80)
    print("決まり手データ補完スクリプト（改善版 - 期間フィルター対応）")
    print("="*80)

    # 1. 決まり手が欠損しているレースを取得
    races = get_races_without_kimarite(
        start_date=args.start_date,
        end_date=args.end_date
    )

    if len(races) == 0:
        print("\n補完が必要なレースはありません。")
        return

    print(f"\n補完対象: {len(races)}件")
    print("\n処理を開始します...")
    print("※改善版: ThreadPoolExecutor、セッション再利用、リトライ機能搭載")

    # 2. 並列で決まり手を取得
    results = []
    success_count = 0
    error_count = 0

    start_time = time.time()

    # ThreadPoolExecutorで並列処理（I/O bound）
    max_workers = 16  # スレッド数

    batch = []
    batch_size = 100  # 100件ごとにDB書き込み

    conn = sqlite3.connect("data/boatrace.db")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_kimarite_fast, race): race for race in races}

        for i, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()

                if result:
                    batch.append(result)
                    success_count += 1

                    # バッチ書き込み
                    if len(batch) >= batch_size:
                        update_kimarite_batch(conn, batch)
                        print(f"[{i}/{len(races)}] 保存完了: {len(batch)}件 ({success_count}/{len(races)}件)")
                        batch = []

                    # 進捗表示（100件ごと）
                    if i % 100 == 0:
                        elapsed = time.time() - start_time
                        rate = i / elapsed
                        remaining = (len(races) - i) / rate if rate > 0 else 0
                        print(f"進捗: {i}/{len(races)} ({i/len(races)*100:.1f}%) - {rate:.1f}件/秒 - 残り約{remaining/60:.1f}分")
                else:
                    error_count += 1

            except Exception as e:
                error_count += 1

    # 残りのバッチを書き込み
    if batch:
        update_kimarite_batch(conn, batch)
        print(f"最終バッチ保存完了: {len(batch)}件")

    conn.close()

    # 3. 最終集計
    elapsed_total = time.time() - start_time

    print("\n" + "="*80)
    print("最終集計")
    print("="*80)
    print(f"対象レース数: {len(races)}")
    print(f"取得成功: {success_count}件")
    print(f"取得失敗: {error_count}件")
    print(f"成功率: {success_count/len(races)*100:.1f}%")
    print(f"処理時間: {elapsed_total/60:.1f}分")
    print(f"処理速度: {len(races)/elapsed_total:.1f}件/秒")
    print("="*80)

if __name__ == "__main__":
    main()
