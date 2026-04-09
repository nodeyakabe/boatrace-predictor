"""
本日のレースデータ収集モジュール

毎朝実行し、本日のレース基本情報を収集
開催スケジュールを事前取得して開催場のみを対象にすることで高速化
"""

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def fetch_todays_races(headless: bool = True) -> int:
    """
    本日のレースデータを収集

    Args:
        headless: ヘッドレスモードで実行するか（注：このパラメータは現在未使用）

    Returns:
        int: 収集したレース数
    """
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"\n{'='*60}")
    print(f"本日のレースデータ収集: {today}")
    print(f"{'='*60}\n")

    # 開催スケジュールを事前取得（リトライ付き）
    venue_codes = None
    for retry in range(2):  # 最大2回試行
        try:
            from src.scraper.schedule_scraper import ScheduleScraper
            import time

            scraper = ScheduleScraper()
            today_schedule = scraper.get_today_schedule()
            scraper.close()

            if not today_schedule:
                if retry == 0:
                    print("[WARNING] 開催スケジュールが空です。5秒後にリトライします...")
                    time.sleep(5)
                    continue
                else:
                    print("[WARNING] 開催スケジュール取得失敗（2回目も空）")
                    print("全競艇場を対象に収集を試みます\n")
                    venue_codes = None
                    break

            venue_count = len(today_schedule)
            venue_codes = sorted(today_schedule.keys())
            print(f"本日の開催: {venue_count}場")
            print(f"開催場: {', '.join(venue_codes)}\n")
            break  # 成功したのでループを抜ける

        except Exception as e:
            if retry == 0:
                print(f"[WARNING] 開催スケジュール取得エラー: {e}")
                print("5秒後にリトライします...")
                import time
                time.sleep(5)
            else:
                print(f"[WARNING] 開催スケジュール取得エラー（2回目）: {e}")
                print("全競艇場を対象に収集を試みます\n")
                venue_codes = None

    try:
        # 開催場のみを対象に並列収集
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from src.scraper.race_scraper_v2 import RaceScraperV2
        from src.database.fast_data_manager import FastDataManager
        import time
        import threading

        # スレッドローカルストレージ
        thread_local = threading.local()

        def get_scrapers():
            """スレッドローカルなスクレイパーを取得"""
            if not hasattr(thread_local, 'race_scraper'):
                thread_local.race_scraper = RaceScraperV2()
            return thread_local.race_scraper

        def fetch_venue_races(venue_code):
            """1会場の全レースを取得"""
            race_scraper = get_scrapers()
            today_yyyymmdd = datetime.now().strftime('%Y%m%d')
            races_data = []

            for race_number in range(1, 13):
                try:
                    race_data = race_scraper.get_race_card(venue_code, today_yyyymmdd, race_number)
                    if not race_data or not race_data.get('entries'):
                        break

                    race_data['venue_code'] = venue_code
                    race_data['race_date'] = today_yyyymmdd
                    race_data['race_number'] = race_number

                    # 結果収集は前日分のみAブロック(fetch_yesterday_results.py)が担当
                    # 当日は未終了レースのため結果取得は不要
                    races_data.append({
                        'race': race_data,
                        'result': None
                    })

                    time.sleep(0.1)

                except Exception as e:
                    # エラーは握りつぶすが、デバッグ用にログ出力
                    if race_number <= 3:  # 序盤3レースのみログ出力（ログ爆発防止）
                        print(f"  [DEBUG] {venue_code}場{race_number}R取得失敗: {type(e).__name__}")

            return venue_code, races_data

        # 並列収集（開催場のみ）
        all_races_data = []
        total_races = 0

        target_venues = venue_codes if venue_codes else [f'{i:02d}' for i in range(1, 25)]

        print(f"データ収集開始: {len(target_venues)}場を並列処理\n")

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(fetch_venue_races, venue_code) for venue_code in target_venues]

            for future in as_completed(futures):
                try:
                    venue_code, races_data = future.result()
                    if races_data:
                        all_races_data.append({
                            'venue_code': venue_code,
                            'race_date': datetime.now().strftime('%Y-%m-%d'),
                            'races_data': races_data
                        })
                        total_races += len(races_data)
                        print(f"  {venue_code}場: {len(races_data)}レース取得")
                except Exception as e:
                    # 会場全体の取得失敗時はログ出力
                    print(f"  [WARNING] 会場取得失敗: {type(e).__name__}: {str(e)[:50]}")

        # データ保存
        if all_races_data:
            print(f"\nデータベース保存中...")
            db_path = project_root / 'data' / 'boatrace.db'
            data_manager = FastDataManager(str(db_path))
            saved_count = 0

            try:
                data_manager.begin_batch()

                for item in all_races_data:
                    venue_code = item['venue_code']
                    for race_item in item['races_data']:
                        try:
                            race_data = race_item['race']
                            result_data = race_item['result']

                            race_id = data_manager.save_race_data_fast(race_data)

                            if race_id:
                                saved_count += 1

                        except Exception as e:
                            # 個別レース保存失敗時はログ出力（最初の数件のみ）
                            if saved_count < 3:
                                print(f"  [DEBUG] {venue_code}場 レース保存失敗: {type(e).__name__}")

                data_manager.commit_batch()
                print(f"  保存完了: {saved_count}レース\n")

            except Exception as e:
                print(f"  [ERROR] 保存エラー: {e}")
                try:
                    data_manager.rollback_batch()
                except:
                    pass
                raise

            finally:
                try:
                    data_manager.close()
                except:
                    pass

        print(f"\n{'='*60}")
        print(f"収集完了: {total_races}レース")
        print(f"{'='*60}\n")

        return total_races

    except Exception as e:
        print(f"\n[ERROR] レースデータ収集中にエラー: {e}")
        import traceback
        traceback.print_exc()
        return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='本日のレースデータ収集')
    parser.add_argument(
        '--headless',
        action='store_true',
        default=True,
        help='ヘッドレスモードで実行（デフォルト: True）'
    )

    args = parser.parse_args()

    race_count = fetch_todays_races(headless=args.headless)

    if race_count > 0:
        print(f"\n[SUCCESS] {race_count}レースのデータを収集しました")
        sys.exit(0)
    else:
        print("\n[WARNING] レースデータを収集できませんでした（レース休止日の可能性）")
        sys.exit(0)  # レース休止日は正常終了
