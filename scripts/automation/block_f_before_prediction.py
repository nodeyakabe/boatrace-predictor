"""
Fブロック: 当日直前情報一括収集 + before予測生成

実行時刻: 毎朝10:30
目的:
  GAP1（monitor_race_timing）のReadTimeoutで直前情報が取得できなかったレースを
  一括で補完し、before予測を当日中に生成することで、
  D_ST_CONTRAST等のbefore予測依存条件を当日のmonitor.pyが評価できるようにする。

タスク:
  1. 本日の全レース直前情報を一括収集（fetch_today_beforeinfo相当）
  2. 本日のbefore予測生成（fast_prediction_generator --type before）
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.notify import send_discord_notification, send_error_notification
from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from src.scraper.schedule_scraper import ScheduleScraper
import sqlite3


def _get_race_id(conn: sqlite3.Connection, venue_code: str, race_date: str, race_number: int):
    """venue_code, race_date, race_numberからrace_idを取得"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM races WHERE venue_code = ? AND race_date = ? AND race_number = ?",
        (venue_code, race_date, race_number)
    )
    result = cursor.fetchone()
    return result[0] if result else None


def collect_today_beforeinfo(today_date: str, today_yyyymmdd: str) -> dict:
    """本日の全レース直前情報を一括収集してDBに保存"""
    print("\n[タスク 1/2] 本日の直前情報一括収集...")
    task_start = datetime.now()

    scraper = BeforeInfoScraper()
    db_path = project_root / 'data' / 'boatrace.db'

    # 開催会場リストを取得
    try:
        schedule_scraper = ScheduleScraper()
        today_schedule = schedule_scraper.get_today_schedule()
        schedule_scraper.close()
        venues = sorted(today_schedule.keys()) if today_schedule else None
    except Exception as e:
        print(f"  ⚠️ スケジュール取得エラー: {e} → フォールバック（全24会場）")
        venues = None

    if not venues:
        venues = [f'{i:02d}' for i in range(1, 25)]

    print(f"  対象会場: {len(venues)}会場 ({', '.join(venues)})")

    total_success = 0
    total_skip = 0
    total_errors = 0

    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        for venue_code in venues:
            for race_number in range(1, 13):
                try:
                    result = scraper.get_race_beforeinfo(venue_code, today_yyyymmdd, race_number)

                    if result and result.get('is_published'):
                        race_id = _get_race_id(conn, venue_code, today_date, race_number)
                        if race_id:
                            success = scraper.save_to_db(race_id, result)
                            if success:
                                total_success += 1
                            else:
                                total_errors += 1
                                print(f"  {venue_code}場 {race_number}R: DB保存失敗")
                        else:
                            total_skip += 1
                    else:
                        total_skip += 1

                    time.sleep(0.3)

                except Exception as e:
                    total_errors += 1
                    print(f"  {venue_code}場 {race_number}R: エラー ({type(e).__name__}: {e})")

            time.sleep(0.5)
    finally:
        conn.close()
        scraper.close()

    elapsed = (datetime.now() - task_start).total_seconds()
    print(f"  収集完了: 成功={total_success}, スキップ={total_skip}, エラー={total_errors}")
    print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒")
    print("  [OK]\n")

    return {'success': total_success, 'skip': total_skip, 'errors': total_errors}


def generate_today_before_predictions(today_date: str) -> dict:
    """本日のbefore予測を生成（既存はスキップ）"""
    print("[タスク 2/2] 本日のbefore予測生成...")
    task_start = datetime.now()

    try:
        from scripts.prediction.fast_prediction_generator import FastPredictionGenerator

        generator = FastPredictionGenerator(prediction_type='before')
        results = generator.generate_all_predictions(today_date, skip_existing=True)

        elapsed = (datetime.now() - task_start).total_seconds()
        print(f"  生成: {results.get('generated', 0)}件 / エラー: {results.get('errors', 0)}件")
        print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒")
        print("  [OK]\n")
        return results

    except Exception as e:
        elapsed = (datetime.now() - task_start).total_seconds()
        print(f"  [ERROR] before予測生成エラー: {e}")
        print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒\n")
        raise


class BlockFRunner:
    """Fブロック実行クラス"""

    def run_all(self) -> bool:
        start_time = datetime.now()
        today_date = start_time.strftime('%Y-%m-%d')
        today_yyyymmdd = start_time.strftime('%Y%m%d')

        print("\n" + "=" * 80)
        print(f"[{start_time.strftime('%Y-%m-%d %H:%M:%S')}] Fブロック開始: 直前情報収集 + before予測生成")
        print(f"対象日: {today_date}")
        print("=" * 80 + "\n")

        success = True

        # タスク1: 直前情報一括収集
        try:
            collect_result = collect_today_beforeinfo(today_date, today_yyyymmdd)
        except Exception as e:
            error_msg = f"Fブロック（直前情報収集）でエラー: {e}"
            print(f"[ERROR] {error_msg}")
            send_error_notification("Fブロックエラー", error_msg, severity='warning')
            success = False

        # タスク2: before予測生成（直前情報収集が失敗しても試みる）
        try:
            pred_result = generate_today_before_predictions(today_date)
            pred_count = pred_result.get('generated', 0)
        except Exception as e:
            error_msg = f"Fブロック（before予測生成）でエラー: {e}"
            print(f"[ERROR] {error_msg}")
            send_error_notification("Fブロックエラー", error_msg, severity='critical')
            success = False
            pred_count = 0

        end_time = datetime.now()
        total_elapsed = (end_time - start_time).total_seconds()

        print("=" * 80)
        print(f"[{end_time.strftime('%Y-%m-%d %H:%M:%S')}] Fブロック完了")
        print(f"  ステータス: {'成功' if success else '一部エラー'}")
        print(f"  総所要時間: {int(total_elapsed // 60)}分{int(total_elapsed % 60)}秒")
        print("=" * 80 + "\n")

        # Discord通知（before予測生成件数）
        if pred_count > 0:
            msg = (
                f"📊 **Fブロック完了** {end_time.strftime('%m/%d %H:%M')}\n"
                f"before予測: {pred_count}件生成"
            )
            send_discord_notification(msg, channel='log')

        return success


def main():
    runner = BlockFRunner()
    success = runner.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
