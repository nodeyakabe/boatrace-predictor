"""
レース詳細データ補完スクリプト（軽量版 - ST time & actual_course のみ）

改善点:
1. 決まり手スクリプトと同じアプローチ（直接HTTP、必要部分のみパース）
2. ST time と actual_course のみ取得（その他のデータは取得しない）
3. ThreadPoolExecutor: 16ワーカー（決まり手と同様）
4. セッション再利用で高速化
5. バッチDB更新でロック競合を回避
6. 期間フィルター対応（--start-date, --end-date）

期待効果:
- v4（1.6件/秒）→ 軽量版（2.5件/秒）
- 38,694件の処理時間: 6.7時間 → 4.3時間
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

def get_races_missing_details(db_path="data/boatrace.db", start_date=None, end_date=None):
    """
    ST timeまたはactual_courseが欠損しているレースを取得

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

    # ST timeまたはactual_courseがNULLのレースを抽出
    query = f"""
        SELECT DISTINCT
            r.id,
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        WHERE EXISTS (
            SELECT 1 FROM race_details rd
            WHERE rd.race_id = r.id
            AND (rd.st_time IS NULL OR rd.actual_course IS NULL)
        )
        {date_filter}
        ORDER BY r.race_date DESC, r.venue_code, r.race_number
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    print(f"ST time/actual_courseが欠損しているレース: {len(rows)}件")
    return rows

def fetch_race_details_light(args, retry=3):
    """
    1レースのST timeとactual_courseのみを高速取得

    Args:
        args: (race_id, venue_code, race_date, race_number)
        retry: リトライ回数

    Returns:
        dict: {
            'race_id': id,
            'st_times': {1: 0.15, 2: 0.12, ...},
            'actual_courses': {1: 1, 2: 2, 3: 3, ...}
        } or None
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

            # レース存在確認
            title = soup.find('title')
            if title and 'エラー' in title.text:
                return None

            st_times = {}
            actual_courses = {}

            # スタート情報テーブルを探す（actual_courseとst_timeを同時取得）
            tables = soup.find_all('table')

            for table in tables:
                table_text = table.get_text()

                # 「スタート情報」を含むテーブルを探す
                if 'スタート情報' in table_text:
                    tbody = table.find('tbody')

                    if tbody:
                        rows = tbody.find_all('tr', recursive=False)

                        # 6行（6コース）あることを確認
                        if len(rows) == 6:
                            # 各行 = 各コース
                            for course, row in enumerate(rows, start=1):
                                # 枠番を取得
                                number_elem = row.find(class_='table1_boatImage1Number')

                                if number_elem:
                                    pit_text = number_elem.get_text(strip=True)
                                    try:
                                        pit_number = int(pit_text)
                                        if 1 <= pit_number <= 6:
                                            # actual_courseを記録
                                            actual_courses[pit_number] = course
                                    except ValueError:
                                        pass

                                # ST timeを取得（同じ行内）
                                time_elem = row.find(class_='table1_boatImage1TimeInner')
                                if time_elem and number_elem:
                                    time_text = time_elem.get_text(strip=True)

                                    # ".17" → "0.17"
                                    if time_text.startswith('.'):
                                        time_text = '0' + time_text

                                    try:
                                        st_time = float(time_text)
                                        st_times[pit_number] = st_time
                                    except ValueError:
                                        pass

                            # 6艇分取得できたら終了
                            if len(actual_courses) == 6:
                                break

            # データが取得できた場合のみ返す
            if st_times or actual_courses:
                return {
                    'race_id': race_id,
                    'st_times': st_times,
                    'actual_courses': actual_courses,
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

def update_race_details_batch(conn, results):
    """
    レース詳細をバッチ更新

    Args:
        conn: データベース接続
        results: 結果のリスト
    """
    cursor = conn.cursor()

    # 各レースのデータを更新
    for result in results:
        race_id = result['race_id']
        st_times = result.get('st_times', {})
        actual_courses = result.get('actual_courses', {})

        # 各艇のデータを更新
        for pit_number in range(1, 7):
            st_time = st_times.get(pit_number)
            actual_course = actual_courses.get(pit_number)

            if st_time is not None or actual_course is not None:
                # 更新フィールドを構築
                update_fields = []
                update_values = []

                if st_time is not None:
                    update_fields.append('st_time = ?')
                    update_values.append(st_time)

                if actual_course is not None:
                    update_fields.append('actual_course = ?')
                    update_values.append(actual_course)

                if update_fields:
                    update_values.extend([race_id, pit_number])
                    cursor.execute(f"""
                        UPDATE race_details
                        SET {', '.join(update_fields)}
                        WHERE race_id = ? AND pit_number = ?
                    """, update_values)

    conn.commit()

def main():
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='レース詳細データ補完（軽量版 - ST/course のみ）')
    parser.add_argument('--start-date', type=str, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='終了日 (YYYY-MM-DD)')
    args = parser.parse_args()

    print("="*80)
    print("レース詳細データ補完スクリプト（軽量版 - ST time & actual_course のみ）")
    print("="*80)

    # 1. ST time/actual_courseが欠損しているレースを取得
    races = get_races_missing_details(
        start_date=args.start_date,
        end_date=args.end_date
    )

    if len(races) == 0:
        print("\n補完が必要なレースはありません。")
        return

    print(f"\n補完対象: {len(races):,}件")
    print("\n処理を開始します...")
    print("※軽量版: ThreadPoolExecutor、セッション再利用、必要データのみ取得")

    # 2. 並列でレース詳細を取得
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
        futures = {executor.submit(fetch_race_details_light, race): race for race in races}

        for i, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()

                if result:
                    batch.append(result)
                    success_count += 1

                    # バッチ書き込み
                    if len(batch) >= batch_size:
                        update_race_details_batch(conn, batch)
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
        update_race_details_batch(conn, batch)
        print(f"最終バッチ保存完了: {len(batch)}件")

    conn.close()

    # 3. 最終集計
    elapsed_total = time.time() - start_time

    print("\n" + "="*80)
    print("最終集計")
    print("="*80)
    print(f"対象レース数: {len(races):,}")
    print(f"取得成功: {success_count:,}件")
    print(f"取得失敗: {error_count:,}件")
    if len(races) > 0:
        print(f"成功率: {success_count/len(races)*100:.1f}%")
    print(f"処理時間: {elapsed_total/60:.1f}分")
    if elapsed_total > 0:
        print(f"処理速度: {len(races)/elapsed_total:.1f}件/秒")
    print("="*80)

if __name__ == "__main__":
    main()
