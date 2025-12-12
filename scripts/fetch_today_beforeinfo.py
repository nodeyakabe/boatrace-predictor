"""
今日の直前情報取得スクリプト
"""

from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from datetime import datetime
import sqlite3
import time
import os

def get_race_id(venue_code: str, race_date: str, race_number: int, db_path: str = None) -> int:
    """
    venue_code, race_date, race_numberからrace_idを取得

    Args:
        venue_code: 会場コード（例: "03"）
        race_date: レース日付 YYYY-MM-DD形式
        race_number: レース番号（1-12）
        db_path: データベースパス

    Returns:
        int: race_id（見つからない場合はNone）
    """
    if db_path is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        db_path = os.path.join(project_root, 'data/boatrace.db')

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id FROM races
            WHERE venue_code = ? AND race_date = ? AND race_number = ?
        """, (venue_code, race_date, race_number))

        result = cursor.fetchone()
        conn.close()

        return result[0] if result else None

    except Exception as e:
        print(f"race_id取得エラー: {e}")
        return None


def main():
    """今日の直前情報を取得してDBに保存"""

    scraper = BeforeInfoScraper()
    today_date = datetime.now().strftime('%Y-%m-%d')  # YYYY-MM-DD形式
    today_yyyymmdd = datetime.now().strftime('%Y%m%d')  # YYYYMMDD形式

    # 今日開催されている会場リスト
    venues = ['03', '05', '06', '07', '10', '13', '14', '15', '17', '19', '21']

    total_success = 0
    total_skip = 0
    total_errors = 0

    print('='*60)
    print(f'直前情報取得開始: {today_date}')
    print('='*60)

    for venue_code in venues:
        print(f'\n会場 {venue_code}:')

        for race_number in range(1, 13):
            try:
                # 直前情報を取得
                result = scraper.get_race_beforeinfo(
                    venue_code,
                    today_yyyymmdd,
                    race_number
                )

                if result and result.get('is_published'):
                    # race_idを取得
                    race_id = get_race_id(venue_code, today_date, race_number)

                    if race_id:
                        # DBに保存
                        success = scraper.save_to_db(race_id, result)
                        if success:
                            total_success += 1
                            print(f'  {race_number}R: OK (race_id={race_id})')
                        else:
                            total_errors += 1
                            print(f'  {race_number}R: DB保存失敗')
                    else:
                        total_skip += 1
                        print(f'  {race_number}R: race_id取得失敗（レース未登録）')
                else:
                    total_skip += 1
                    print(f'  {race_number}R: 未公開')

                # レート制限対策
                time.sleep(0.5)

            except Exception as e:
                total_errors += 1
                print(f'  {race_number}R: エラー ({type(e).__name__}: {e})')

        # 会場間の待機時間
        time.sleep(1)

    print('')
    print('='*60)
    print(f'完了: 成功={total_success}, スキップ={total_skip}, エラー={total_errors}')
    print('='*60)

    scraper.close()


if __name__ == "__main__":
    main()
