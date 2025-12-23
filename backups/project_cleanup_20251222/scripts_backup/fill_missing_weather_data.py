"""
過去データの天候情報補完スクリプト

race_conditionsテーブルで天候データ（weather, wind_direction）が欠落している
過去レースの天候情報を、直前情報ページから再取得して補完する。

対象期間: 2025年1月1日 ～ 2025年11月27日
"""
import os
import sys
import sqlite3
import time
from datetime import datetime, timedelta
import concurrent.futures

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.scraper.beforeinfo_scraper import BeforeInfoScraper


def get_races_without_weather(db_path: str, start_date: str, end_date: str):
    """
    天候データが欠落しているレースを取得

    Args:
        db_path: データベースパス
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）

    Returns:
        レース情報のリスト
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND (rc.weather IS NULL OR rc.weather = '')
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, (start_date, end_date))

    races = []
    for row in cursor.fetchall():
        race_date_str = row[2].replace('-', '')  # YYYY-MM-DD → YYYYMMDD
        races.append({
            'race_id': row[0],
            'venue_code': row[1],
            'race_date': race_date_str,
            'race_number': row[3]
        })

    conn.close()
    return races


def fetch_and_update_weather(race_info, db_path):
    """
    1レースの天候データを取得してDBを更新

    Args:
        race_info: レース情報辞書
        db_path: データベースパス

    Returns:
        成功したかどうか
    """
    try:
        scraper = BeforeInfoScraper(delay=0.5)
        beforeinfo = scraper.get_race_beforeinfo(
            race_info['venue_code'],
            race_info['race_date'],
            race_info['race_number']
        )

        if beforeinfo and beforeinfo.get('is_published'):
            weather = beforeinfo.get('weather', {})
            weather_code = weather.get('weather_code')
            wind_dir_code = weather.get('wind_dir_code')

            # コードをテキストに変換
            weather_text = scraper._weather_code_to_text(weather_code) if weather_code else None
            wind_dir_text = scraper._wind_dir_code_to_text(wind_dir_code) if wind_dir_code else None

            # DBを更新（天候・風向のみ更新）
            if weather_text or wind_dir_text:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE race_conditions
                    SET weather = COALESCE(?, weather),
                        wind_direction = COALESCE(?, wind_direction)
                    WHERE race_id = ?
                """, (weather_text, wind_dir_text, race_info['race_id']))

                conn.commit()
                conn.close()

                scraper.close()
                return True

        scraper.close()
        return False

    except Exception as e:
        print(f"エラー (race_id={race_info['race_id']}): {e}")
        return False


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    # 対象期間（天候データが欠落している期間）
    start_date = '2025-01-01'
    end_date = '2025-11-27'

    print("=" * 80)
    print("過去データ天候情報補完スクリプト")
    print("=" * 80)
    print(f"対象期間: {start_date} ～ {end_date}")
    print()

    # 天候データが欠落しているレースを取得
    print("天候データが欠落しているレースを検索中...")
    races = get_races_without_weather(db_path, start_date, end_date)
    print(f"対象レース: {len(races)}件")
    print()

    if not races:
        print("補完対象のレースがありません。")
        return

    # ユーザー確認
    print(f"WARNING: {len(races)}件のレースの天候データを補完します。")
    print(f"推定時間: 約{len(races) * 0.5 / 60:.1f}分（0.5秒/レース × {len(races)}件）")
    response = input("続行しますか？ (yes/no): ")

    if response.lower() != 'yes':
        print("キャンセルしました。")
        return

    print()
    print("=" * 80)
    print("天候データ補完開始")
    print("=" * 80)

    success_count = 0
    failed_count = 0
    start_time = time.time()

    # 並列処理（8スレッド）
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_and_update_weather, race, db_path): race for race in races}

        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            if future.result():
                success_count += 1
            else:
                failed_count += 1

            # 進捗表示（10件ごと）
            if i % 10 == 0 or i == len(races):
                elapsed = time.time() - start_time
                rate = i / elapsed
                remaining = (len(races) - i) / rate if rate > 0 else 0
                print(f"[{i}/{len(races)}] 成功: {success_count}, 失敗: {failed_count} "
                      f"(処理速度: {rate:.1f}件/秒, 残り時間: {remaining/60:.1f}分)")

    elapsed_time = time.time() - start_time

    print()
    print("=" * 80)
    print("補完完了")
    print("=" * 80)
    print(f"成功: {success_count}件")
    print(f"失敗: {failed_count}件")
    print(f"処理時間: {elapsed_time/60:.1f}分")
    print()

    # 補完後の統計を表示
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN rc.weather IS NOT NULL AND rc.weather != '' THEN 1 END) as has_weather
        FROM race_conditions rc
        JOIN races r ON rc.race_id = r.id
        WHERE r.race_date >= ? AND r.race_date <= ?
    """, (start_date, end_date))

    row = cursor.fetchone()
    print(f"【補完後の統計（{start_date} ～ {end_date}）】")
    print(f"  総レコード数: {row[0]:,}件")
    print(f"  天候データあり: {row[1]:,}件 ({row[1]/row[0]*100:.1f}%)")

    conn.close()


if __name__ == "__main__":
    main()
