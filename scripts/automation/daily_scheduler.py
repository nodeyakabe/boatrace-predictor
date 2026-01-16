"""
メインスケジューラ

常駐して以下のタスクを自動実行:
- 毎朝7:00 本日の予想生成
- 5分ごと レース監視（直前情報取得・通知）
"""

import os
import sys
import time
import signal
import schedule
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.generate_daily_predictions import generate_todays_predictions
from scripts.automation.monitor_race_timing import RaceMonitor
from scripts.automation.notify import send_discord_notification, send_error_notification


# グローバル変数
running = True
monitor = None


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
        else:
            print("[ERROR] 朝の予想生成失敗")

    except Exception as e:
        error_msg = f"朝の予想生成中にエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("スケジューラエラー", error_msg)


def race_monitoring_job():
    """レース監視ジョブ（5分ごと）"""
    global monitor

    if monitor is None:
        db_path = project_root / "data" / "boatrace.db"

        if not db_path.exists():
            print(f"WARNING️ データベースが見つかりません: {db_path}")
            return

        monitor = RaceMonitor(str(db_path))

    try:
        stats = monitor.monitor_once()

        # 何かアクションがあった場合のみログ出力
        if stats['direct_info_fetched'] > 0 or stats['notifications_sent'] > 0:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n[{timestamp}] レース監視実行:")
            print(f"  対象レース: {stats['total_races']}")
            print(f"  直前情報取得: {stats['direct_info_fetched']}")
            print(f"  通知送信: {stats['notifications_sent']}")

            if stats['errors'] > 0:
                print(f"  WARNING️ エラー: {stats['errors']}")

    except Exception as e:
        error_msg = f"レース監視中にエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("レース監視エラー", error_msg)


def startup_notification():
    """起動通知"""
    message = f"""🤖 **ボートレース自動化システム起動**

起動時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**スケジュール:**
- 毎朝 8:30 - 予想生成
- 5分ごと - レース監視

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
    print("  - 毎朝 8:30 - 予想生成")
    print("  - 5分ごと - レース監視")
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

    # 毎朝8:30に予想生成
    schedule.every().day.at("08:30").do(morning_prediction_job)
    print("[OK] 毎朝 8:30 - 予想生成")

    # 5分ごとにレース監視
    schedule.every(5).minutes.do(race_monitoring_job)
    print("[OK] 5分ごと - レース監視")

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

    # メイン実行
    main()
