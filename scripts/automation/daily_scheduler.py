"""
メインスケジューラ

常駐して以下のタスクを自動実行:
- 毎朝5:00 前日のレース結果収集
- 毎朝5:30 前日の確定オッズ取得（暫定オッズを上書き）
- 毎朝6:10 前日の直前情報収集
- 毎朝6:50 前日の直前予想生成
- 毎朝7:10 前日のオリジナル展示データ収集
- 毎朝7:40 本日のオッズ収集（暫定オッズ）
- 毎朝8:20 本日の予想生成
- 購入対象レースの締切10分前 直前情報取得・通知（動的スケジュール）

【2段階オッズ収集システム】
7:40に暫定オッズを取得して8:20に予測生成し、翌朝5:30に確定オッズで上書き。
これにより、当日の予測は生成しつつ、バックテストには正確なデータを使用できます。

【スケジュール間隔】
各処理間に20～40分の余裕を設定し、データ収集の完了を確実にします。
特に本日オッズ収集→予想生成は40分の余裕を確保。
"""

import os
import sys
import time
import signal
import schedule
import sqlite3
import psutil
from datetime import datetime, timedelta
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.generate_daily_predictions import generate_todays_predictions
from scripts.automation.monitor_race_timing import RaceMonitor
from scripts.automation.notify import send_discord_notification, send_error_notification
from scripts.automation.daily_tenji_collector import collect_previous_day_tenji
from scripts.automation.fetch_today_odds import fetch_todays_odds
from scripts.automation.fetch_yesterday_results import fetch_yesterday_results
from scripts.automation.fetch_yesterday_beforeinfo import fetch_yesterday_beforeinfo
from scripts.automation.generate_yesterday_before_predictions import generate_yesterday_before_predictions
from scripts.automation.fetch_yesterday_final_odds import fetch_yesterday_final_odds


# グローバル変数
running = True
monitor = None
lock_file = None


def acquire_lock():
    """
    ロックファイルを取得して二重起動を防止

    Returns:
        bool: ロック取得成功ならTrue、既に起動中ならFalse
    """
    global lock_file

    lock_path = project_root / "data" / "daily_scheduler.lock"

    # 既存のロックファイルをチェック
    if lock_path.exists():
        try:
            with open(lock_path, 'r') as f:
                old_pid = int(f.read().strip())

            # プロセスがまだ生きているか確認
            if psutil.pid_exists(old_pid):
                try:
                    proc = psutil.Process(old_pid)
                    # daily_scheduler.pyを実行しているか確認
                    cmdline = ' '.join(proc.cmdline())
                    if 'daily_scheduler.py' in cmdline:
                        print(f"[ERROR] daily_schedulerは既に起動しています (PID: {old_pid})")
                        print(f"[ERROR] 既存のプロセスを停止してから再実行してください")
                        return False
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # 古いロックファイルを削除
            print(f"[INFO] 古いロックファイルを削除: PID {old_pid} (プロセス終了済み)")
            lock_path.unlink()

        except (ValueError, FileNotFoundError):
            # ロックファイルが壊れている場合は削除
            lock_path.unlink(missing_ok=True)

    # 新しいロックファイルを作成
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, 'w') as f:
            f.write(str(os.getpid()))
        lock_file = lock_path
        return True
    except Exception as e:
        print(f"[ERROR] ロックファイル作成失敗: {e}")
        return False


def release_lock():
    """ロックファイルを解放"""
    global lock_file

    if lock_file and lock_file.exists():
        try:
            lock_file.unlink()
            print("[INFO] ロックファイルを解放しました")
        except Exception as e:
            print(f"[WARNING] ロックファイル削除失敗: {e}")


def signal_handler(signum, frame):
    """
    シグナルハンドラ（Ctrl+Cなどで終了）

    Args:
        signum: シグナル番号
        frame: フレーム
    """
    global running
    print("\n\n停止シグナルを受信しました。終了します...")
    running = False


def morning_prediction_job():
    """朝の予想生成ジョブ"""
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 朝の予想生成開始")
    print("=" * 60)

    try:
        success = generate_todays_predictions()

        if success:
            print("[OK] 朝の予想生成完了")

            # 予想生成後、レース通知スケジュールを設定
            print("\n購入対象レースの通知スケジュール設定中...")
            scheduled_count = schedule_race_notifications()

            if scheduled_count > 0:
                print(f"[OK] {scheduled_count}レースの通知を予約")
            else:
                print("[INFO] 予約する通知なし")

        else:
            print("[ERROR] 朝の予想生成失敗")

    except Exception as e:
        error_msg = f"朝の予想生成中にエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("スケジューラエラー", error_msg)


def tenji_collection_job():
    """前日のオリジナル展示データ収集ジョブ（毎朝8:00）"""
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 前日オリジナル展示データ収集開始")
    print("=" * 60)

    try:
        race_count = collect_previous_day_tenji(headless=True, update_existing=True)

        if race_count > 0:
            print(f"[OK] 前日オリジナル展示データ収集完了: {race_count}レース")
        else:
            print("[WARNING] 前日オリジナル展示データ収集: データなし")

    except Exception as e:
        error_msg = f"オリジナル展示データ収集中にエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("展示データ収集エラー", error_msg)


def odds_collection_job():
    """本日のオッズ収集ジョブ（毎朝8:15）"""
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 本日のオッズ収集開始")
    print("=" * 60)

    try:
        race_count = fetch_todays_odds(headless=True)

        if race_count > 0:
            print(f"[OK] オッズ収集完了: {race_count}レース")
        else:
            print("[WARNING] オッズ収集: データなし")

    except Exception as e:
        error_msg = f"オッズ収集中にエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("オッズ収集エラー", error_msg)


def results_collection_job():
    """前日のレース結果収集ジョブ（毎朝7:00）"""
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 前日レース結果収集開始")
    print("=" * 60)

    try:
        race_count = fetch_yesterday_results(headless=True)

        if race_count > 0:
            print(f"[OK] 前日レース結果収集完了: {race_count}レース")
        else:
            print("[INFO] 前日レース結果: 全て取得済み")

    except Exception as e:
        error_msg = f"前日レース結果収集中にエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("結果収集エラー", error_msg)


def beforeinfo_collection_job():
    """前日の直前情報収集ジョブ（毎朝7:30）"""
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 前日直前情報収集開始")
    print("=" * 60)

    try:
        race_count = fetch_yesterday_beforeinfo(headless=True)

        if race_count > 0:
            print(f"[OK] 前日直前情報収集完了: {race_count}レース")
        else:
            print("[WARNING] 前日直前情報収集: データなし")

    except Exception as e:
        error_msg = f"前日直前情報収集中にエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("直前情報収集エラー", error_msg)


def yesterday_before_prediction_job():
    """前日の直前予想生成ジョブ（毎朝7:45）"""
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 前日直前予想生成開始")
    print("=" * 60)

    try:
        race_count = generate_yesterday_before_predictions(force=False)

        if race_count > 0:
            print(f"[OK] 前日直前予想生成完了: {race_count}レース")
        else:
            print("[WARNING] 前日直前予想生成: データなし")

    except Exception as e:
        error_msg = f"前日直前予想生成中にエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("直前予想生成エラー", error_msg)


def final_odds_collection_job():
    """前日の確定オッズ取得ジョブ（毎朝7:05）"""
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 前日確定オッズ取得開始")
    print("=" * 60)

    try:
        race_count = fetch_yesterday_final_odds(headless=True)

        if race_count > 0:
            print(f"[OK] 前日確定オッズ取得完了: {race_count}レース")
        else:
            print("[INFO] 前日確定オッズ: データなし")

    except Exception as e:
        error_msg = f"前日確定オッズ取得中にエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("確定オッズ取得エラー", error_msg)


def schedule_race_notifications():
    """本日の購入対象レースの通知スケジュールを設定"""
    global monitor

    db_path = project_root / "data" / "boatrace.db"
    if not db_path.exists():
        print(f"WARNING: データベースが見つかりません: {db_path}")
        return 0

    if monitor is None:
        monitor = RaceMonitor(str(db_path))

    try:
        # 本日の購入対象レースを取得
        target_races = monitor.get_todays_target_races()

        if not target_races:
            print("[INFO] 本日の購入対象レースなし")
            return 0

        scheduled_count = 0
        for race in target_races:
            # 締切10分前の時刻を計算
            race_time_str = race['race_time']  # "HH:MM:SS"
            race_datetime = datetime.strptime(f"{race['race_date']} {race_time_str}", '%Y-%m-%d %H:%M:%S')
            notification_time = race_datetime - timedelta(minutes=10)

            # 過去の時刻はスキップ
            if notification_time < datetime.now():
                continue

            # 通知時刻を "HH:MM" 形式に変換
            time_str = notification_time.strftime('%H:%M')

            # スケジュールに登録
            def create_notification_job(race_id, venue_code, race_number):
                def job():
                    race_monitoring_job_for_race(race_id, venue_code, race_number)
                return job

            schedule.every().day.at(time_str).do(
                create_notification_job(race['race_id'], race['venue_code'], race['race_number'])
            )

            scheduled_count += 1
            print(f"  [{venue_code:02d}場 {race_number:2d}R] 通知予約: {time_str}")

        print(f"[OK] {scheduled_count}レースの通知をスケジュール登録")
        return scheduled_count

    except Exception as e:
        print(f"[ERROR] レース通知スケジュール設定エラー: {e}")
        return 0


def race_monitoring_job_for_race(race_id, venue_code, race_number):
    """特定レースの直前情報取得・通知"""
    global monitor

    if monitor is None:
        db_path = project_root / "data" / "boatrace.db"
        monitor = RaceMonitor(str(db_path))

    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n[{timestamp}] レース通知実行: {venue_code:02d}場 {race_number:2d}R")

        # 直前情報取得
        stats = monitor.monitor_once()

        print(f"  直前情報取得: {stats['direct_info_fetched']}")
        print(f"  通知送信: {stats['notifications_sent']}")

        if stats['errors'] > 0:
            print(f"  WARNING: エラー: {stats['errors']}")

    except Exception as e:
        error_msg = f"レース通知中にエラー ({venue_code:02d}場 {race_number:2d}R): {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("レース通知エラー", error_msg)


def startup_notification():
    """起動通知"""
    message = f"""🤖 **ボートレース自動化システム起動**

起動時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**スケジュール:**
- 毎朝 7:00 - 前日レース結果収集
- 毎朝 7:30 - 前日直前情報収集
- 毎朝 7:45 - 前日直前予想生成
- 毎朝 8:00 - 前日オリジナル展示データ収集
- 毎朝 8:15 - 本日のオッズ収集
- 毎朝 8:30 - 予想生成 + レース通知スケジュール登録
- 各レース締切10分前 - 直前情報取得・通知（動的スケジュール）

システムは正常稼働中です。
"""
    send_discord_notification(message)


def shutdown_notification():
    """停止通知"""
    message = f"""🛑 **ボートレース自動化システム停止**

停止時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

システムを再起動する場合:
```
python scripts/automation/daily_scheduler.py
```
"""
    send_discord_notification(message)


def print_status():
    """ステータス表示"""
    global monitor

    print("\n" + "=" * 60)
    print("ボートレース自動化システム")
    print("=" * 60)
    print(f"起動時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nスケジュール:")
    print("  - 毎朝 7:00 - 前日レース結果収集")
    print("  - 毎朝 7:30 - 前日直前情報収集")
    print("  - 毎朝 7:45 - 前日直前予想生成")
    print("  - 毎朝 8:00 - 前日オリジナル展示データ収集")
    print("  - 毎朝 8:15 - 本日のオッズ収集")
    print("  - 毎朝 8:30 - 予想生成 + レース通知スケジュール登録")
    print("  - 各レース締切10分前 - 直前情報取得・通知（動的）")
    print("\n操作:")
    print("  - Ctrl+C で停止")
    print("=" * 60 + "\n")

    # 次回実行時刻を表示
    next_run = schedule.next_run()
    if next_run:
        print(f"次回ジョブ実行: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        print()


def main():
    """メイン処理"""
    global running

    # ロックファイルを取得（二重起動チェック）
    if not acquire_lock():
        print("\n[ERROR] 既に起動中のため終了します")
        return 1

    # シグナルハンドラ設定（Ctrl+Cで終了）
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # ステータス表示
    print_status()

    # 起動通知
    print("起動通知を送信中...")
    startup_notification()
    print("[OK] 起動通知送信完了\n")

    # スケジュール設定
    print("スケジュール設定中...")

    # 毎朝5:00に前日のレース結果収集
    schedule.every().day.at("05:00").do(results_collection_job)
    print("[OK] 毎朝 5:00 - 前日レース結果収集")

    # 毎朝5:30に前日の確定オッズ取得（暫定オッズを上書き）
    schedule.every().day.at("05:30").do(final_odds_collection_job)
    print("[OK] 毎朝 5:30 - 前日確定オッズ取得")

    # 毎朝6:10に前日の直前情報収集
    schedule.every().day.at("06:10").do(beforeinfo_collection_job)
    print("[OK] 毎朝 6:10 - 前日直前情報収集")

    # 毎朝6:50に前日の直前予想生成
    schedule.every().day.at("06:50").do(yesterday_before_prediction_job)
    print("[OK] 毎朝 6:50 - 前日直前予想生成")

    # 毎朝7:10に前日のオリジナル展示データ収集
    schedule.every().day.at("07:10").do(tenji_collection_job)
    print("[OK] 毎朝 7:10 - 前日オリジナル展示データ収集")

    # 毎朝7:40に本日のオッズ収集
    schedule.every().day.at("07:40").do(odds_collection_job)
    print("[OK] 毎朝 7:40 - 本日のオッズ収集")

    # 毎朝8:20に予想生成 + レース通知スケジュール登録
    schedule.every().day.at("08:20").do(morning_prediction_job)
    print("[OK] 毎朝 8:20 - 予想生成 + レース通知スケジュール登録")

    print("\nシステム稼働開始...\n")

    # メインループ
    try:
        while running:
            schedule.run_pending()
            time.sleep(30)  # 30秒ごとにチェック

    except Exception as e:
        error_msg = f"スケジューラメインループでエラー: {str(e)}"
        print(f"\n[ERROR] {error_msg}")
        send_error_notification("スケジューラ致命的エラー", error_msg)

    finally:
        # ロックファイルを解放
        release_lock()

        # 停止通知
        print("\n停止通知を送信中...")
        shutdown_notification()
        print("[OK] 停止通知送信完了")

        print("\nシステム停止完了")


if __name__ == "__main__":
    # 必要なパッケージのインポートチェック
    try:
        import schedule
    except ImportError:
        print("[ERROR] エラー: schedule パッケージがインストールされていません")
        print("\n以下のコマンドでインストールしてください:")
        print("  pip install schedule")
        sys.exit(1)

    try:
        import requests
    except ImportError:
        print("[ERROR] エラー: requests パッケージがインストールされていません")
        print("\n以下のコマンドでインストールしてください:")
        print("  pip install requests")
        sys.exit(1)

    try:
        from dotenv import load_dotenv
    except ImportError:
        print("[ERROR] エラー: python-dotenv パッケージがインストールされていません")
        print("\n以下のコマンドでインストールしてください:")
        print("  pip install python-dotenv")
        sys.exit(1)

    try:
        import psutil
    except ImportError:
        print("[ERROR] エラー: psutil パッケージがインストールされていません")
        print("\n以下のコマンドでインストールしてください:")
        print("  pip install psutil")
        sys.exit(1)

    # メイン実行
    sys.exit(main())
