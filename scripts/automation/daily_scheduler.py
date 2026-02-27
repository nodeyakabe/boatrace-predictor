"""
メインスケジューラ（4ブロック構成 v2）

常駐して以下のタスクを自動実行:
- 毎朝5:00 Aブロック（前日データ完全収集）
- 毎朝7:00 Cブロック（本日データ収集）
- 毎朝8:00 Dブロック（本日予想生成）
- 動的     各レース締切10分前通知

【4ブロック構成のメリット】
- 依存タスクを1スクリプトで順次実行（待機時間ゼロ）
- エラーハンドリングが容易
- ログが追いやすい
- 手動再実行が簡単

【ブロック詳細】
Aブロック: 結果→確定オッズ→直前情報→展示→直前予想（5タスク）
Cブロック: レースデータ→オッズ（2タスク）
Dブロック: 予想生成→通知スケジュール登録（2タスク）
"""

import os
import sys
import time
import signal
import schedule
import psutil
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.monitor_race_timing import RaceMonitor
from scripts.automation.notify import send_discord_notification, send_error_notification
from scripts.automation.block_a_yesterday_data import BlockARunner
from scripts.automation.block_c_today_data import BlockCRunner
from scripts.automation.block_d_today_prediction import BlockDRunner


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


def block_a_job():
    """Aブロック: 前日データ完全収集 + 日次リセット"""
    global monitor

    # 日次リセット: 翌日に向けて状態をクリア
    if monitor is not None:
        monitor.notified_races.clear()
        monitor.fetched_direct_info.clear()
        monitor.fetched_odds_races.clear()
        monitor._bet_target_cache.clear()
        monitor._cache_date = None
        print("[INFO] 日次リセット完了（通知済み・直前情報・オッズ取得済みセットをクリア）")

    try:
        runner = BlockARunner()
        success = runner.run_all()

        if not success:
            print("[WARNING] Aブロックでエラーが発生しましたが続行します")

    except Exception as e:
        error_msg = f"Aブロック実行中にエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("Aブロックエラー", error_msg)


def block_c_job():
    """Cブロック: 本日データ収集"""
    try:
        runner = BlockCRunner()
        success = runner.run_all()

        if not success:
            print("[WARNING] Cブロックでエラーが発生しましたが続行します")

    except Exception as e:
        error_msg = f"Cブロック実行中にエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("Cブロックエラー", error_msg)


def block_d_job():
    """Dブロック: 本日予想生成"""
    try:
        # Dブロック実行
        runner = BlockDRunner()
        success = runner.run_all()

        if not success:
            print("[WARNING] Dブロックでエラーが発生しました")

    except Exception as e:
        error_msg = f"Dブロック実行中にエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("Dブロックエラー", error_msg)


# 古いジョブ関数は削除（4ブロック構成に統合）


def race_monitor_job():
    """
    定期レース監視ジョブ（1分ごと）

    購入対象レースを監視し:
    - 締切20分前: 直前情報取得 + 再評価
    - 締切10分前: 購入通知送信
    """
    global monitor

    db_path = project_root / "data" / "boatrace.db"
    if not db_path.exists():
        return

    if monitor is None:
        monitor = RaceMonitor(str(db_path))

    try:
        # 監視サイクル実行（購入対象レースの20分前取得、10分前通知をチェック）
        stats = monitor.monitor_once()

        # エラーがあれば表示（通常は出力なし）
        if stats.get('errors', 0) > 0:
            print(f"[WARNING] レース監視でエラー: {stats['errors']}件")

    except Exception as e:
        # エラーログのみ（通常の監視サイクルなので通知は送らない）
        print(f"[ERROR] レース監視エラー: {e}")



def startup_notification():
    """起動通知"""
    message = f"""🤖 **ボートレース自動化システム起動（v3.0 - 常駐監視版）**

起動時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**スケジュール:**
- 03:00 - Aブロック（前日データ完全収集 + 日次リセット）
- 06:00 - Cブロック（本日データ収集）
- 07:30 - Dブロック（予想生成）
- 1分ごと - レース監視（オッズ30-50分前再取得、直前情報20分前取得、通知10分前送信）

**ブロック詳細:**
Aブロック: 結果→確定オッズ→直前情報→展示→直前予想 + 日次リセット
Cブロック: レースデータ→オッズ
Dブロック: 予想生成
レース監視: CANDIDATE→オッズ再取得→TARGET昇格→直前情報取得→通知

システムは正常稼働中です。
"""
    send_discord_notification(message)


def shutdown_notification():
    """停止通知"""
    message = f"""🛑 **ボートレース自動化システム停止（v2）**

停止時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

システムを再起動する場合:
```
python scripts/automation/daily_scheduler.py
```

手動でブロック実行する場合:
```
python scripts/automation/block_a_yesterday_data.py
python scripts/automation/block_c_today_data.py
python scripts/automation/block_d_today_prediction.py
```
"""
    send_discord_notification(message)


def print_status():
    """ステータス表示"""
    global monitor

    print("\n" + "=" * 60)
    print("ボートレース自動化システム（v3.0 - 常駐監視版）")
    print("=" * 60)
    print(f"起動時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nスケジュール:")
    print("  - 毎朝 3:00 - Aブロック（前日データ完全収集 + 日次リセット）")
    print("  - 毎朝 6:00 - Cブロック（本日データ収集）")
    print("  - 毎朝 7:30 - Dブロック（予想生成）")
    print("  - 1分ごと - レース監視（オッズ再取得→直前情報→通知）")
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

    # スケジュール設定（4ブロック構成）
    print("スケジュール設定中...")

    # 毎朝3:00にAブロック（前日データ完全収集）- 1時間前倒し
    schedule.every().day.at("03:00").do(block_a_job)
    print("[OK] 毎朝 3:00 - Aブロック（前日データ完全収集）[1時間前倒し]")

    # 毎朝6:00にCブロック（本日データ収集）- 30分前倒し
    schedule.every().day.at("06:00").do(block_c_job)
    print("[OK] 毎朝 6:00 - Cブロック（本日データ収集）[30分前倒し]")

    # 毎朝7:30にDブロック（予想生成）
    schedule.every().day.at("07:30").do(block_d_job)
    print("[OK] 毎朝 7:30 - Dブロック（予想生成）")

    # 1分ごとにレース監視（20分前取得、10分前通知）
    schedule.every(1).minutes.do(race_monitor_job)
    print("[OK] 1分ごと - レース監視（直前情報20分前取得、通知10分前送信）")

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
