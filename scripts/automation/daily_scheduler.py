"""
メインスケジューラ（5ブロック構成）

常駐して以下のタスクを自動実行:
- 毎朝3:00 Aブロック（前日データ完全収集）
- 毎朝6:00 Cブロック（本日データ収集 + advance予測生成）
- 毎朝7:30 Dブロック（本日予想生成）
- 毎朝8:00 Eブロック（当日オッズ収集）
- 動的     各レース締切10分前通知

【ブロック詳細】
Aブロック: 結果→確定オッズ→直前情報→展示→直前予想（5タスク）
Cブロック: レースデータ→advance予測生成（2タスク）
Dブロック: 予想生成（1タスク）
Eブロック: 当日オッズ収集（1タスク、6:00は未公開のため8:00に分離）
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


class _TeeStream:
    """stdout/stderrをコンソールとファイルに同時出力するTeeラッパー"""
    def __init__(self, original, log_file):
        self._original = original
        self._log_file = log_file

    def write(self, data):
        try:
            self._original.write(data)
        except (UnicodeEncodeError, UnicodeDecodeError):
            # cp932等のエンコード非対応文字はASCII変換して出力
            try:
                self._original.write(data.encode('ascii', errors='replace').decode('ascii'))
            except Exception:
                pass
        except OSError:
            # コンソールハンドル無効時（[Errno 22]等）はログファイルのみに出力
            pass
        try:
            self._log_file.write(data)
            self._log_file.flush()
        except Exception:
            pass

    def flush(self):
        try:
            self._original.flush()
        except OSError:
            pass
        try:
            self._log_file.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._original, name)


def _setup_file_logging():
    """ログファイルへの出力設定"""
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")
    log_path = log_dir / f"scheduler_{today_str}.log"
    log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = _TeeStream(sys.__stdout__, log_file)
    sys.stderr = _TeeStream(sys.__stderr__, log_file)
    print(f"[INFO] ログファイル: {log_path}", flush=True)

from scripts.automation.monitor_race_timing import RaceMonitor
from scripts.automation.notify import send_discord_notification, send_error_notification
from scripts.automation.block_a_yesterday_data import BlockARunner
from scripts.automation.block_c_today_data import BlockCRunner
from scripts.automation.block_d_today_prediction import BlockDRunner
from scripts.automation.fetch_today_odds import fetch_todays_odds
from scripts.maintenance.run_racer_features_recompute import recompute_racer_features


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

    my_pid = os.getpid()

    # ① psutilで既存プロセスを直接確認（ロックファイルより確実・レース競合なし）
    # python.exe のみ対象（シェルラッパーのcmdlineに daily_scheduler.py が含まれる誤検知を防ぐ）
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        if proc.info['pid'] == my_pid:
            continue
        try:
            proc_name = (proc.info['name'] or '').lower()
            if 'python' not in proc_name:
                continue
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'daily_scheduler.py' in cmdline:
                print(f"[ERROR] daily_schedulerは既に起動しています (PID: {proc.info['pid']})")
                return False
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    lock_path = project_root / "data" / "daily_scheduler.lock"

    # 古いロックファイルがあれば、PIDが生存中か確認してから削除
    if lock_path.exists():
        try:
            with open(lock_path, 'r') as f:
                old_pid = int(f.read().strip())

            # PIDが実際に生存しているか確認
            if psutil.pid_exists(old_pid):
                try:
                    proc = psutil.Process(old_pid)
                    cmdline = ' '.join(proc.cmdline() or [])
                    if 'daily_scheduler.py' in cmdline:
                        print(f"[ERROR] ロックファイルのプロセスが起動中: PID {old_pid}")
                        return False
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass  # プロセス消滅済み → 削除してよい

            print(f"[INFO] 古いロックファイルを削除: PID {old_pid} (プロセス終了済み)")
        except Exception:
            pass
        lock_path.unlink(missing_ok=True)

    # ② 排他オープン（'x'フラグ）でアトミックに作成
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, 'x') as f:
            f.write(str(my_pid))
        lock_file = lock_path
        return True
    except FileExistsError:
        # 極めて稀なタイミングで別プロセスが同時作成した場合
        print(f"[ERROR] ロックファイル競合（別プロセスが同時起動）: {lock_path}")
        return False
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


def racer_features_job():
    """毎週月曜・木曜04:00: racer_features / racer_venue_features 週2回更新"""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] racer_features 更新開始（最大遅延3日）")
    try:
        success = recompute_racer_features()
        if success:
            print(f"[OK] racer_features 更新完了")
        else:
            send_error_notification("racer_features更新エラー", "週2回更新が失敗しました")
    except Exception as e:
        error_msg = f"racer_features更新エラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("racer_features更新エラー", error_msg)


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


def block_e_job():
    """Eブロック: 当日オッズ収集（08:00）

    6:00時点では公式サイトが当日オッズを未公開のため、
    発走1時間前（08:00）に収集することで取得成功率を最大化する。
    """
    today = datetime.now().strftime('%Y-%m-%d')
    start_time = datetime.now()

    print("\n" + "=" * 80)
    print(f"[{start_time.strftime('%Y-%m-%d %H:%M:%S')}] Eブロック開始: 当日オッズ収集")
    print(f"対象日: {today}")
    print("=" * 80 + "\n")

    print("[タスク 1/1] 本日のオッズ収集...")
    task_start = datetime.now()

    try:
        odds_count = fetch_todays_odds()
        elapsed = (datetime.now() - task_start).total_seconds()

        print(f"  取得: {odds_count}レース")
        print(f"  所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒")
        print(f"  [OK]\n")

        end_time = datetime.now()
        total = (end_time - start_time).total_seconds()
        print("=" * 80)
        print(f"[{end_time.strftime('%Y-%m-%d %H:%M:%S')}] Eブロック完了")
        print(f"  総所要時間: {int(total // 60)}分{int(total % 60)}秒")
        print("=" * 80 + "\n")

    except Exception as e:
        error_msg = f"Eブロック（オッズ収集）でエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("Eブロックエラー", error_msg)


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
    message = (
        f"🤖 **システム起動** {datetime.now().strftime('%m/%d %H:%M')}\n"
        f"A 03:00 → C 06:00 → E 08:00 → D 08:30"
    )
    send_discord_notification(message)


def shutdown_notification():
    """停止通知"""
    message = f"🛑 **システム停止** {datetime.now().strftime('%m/%d %H:%M')}"
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
    print("  - 毎朝 6:00 - Cブロック（本日データ収集 + advance予測生成）")
    print("  - 毎朝 8:00 - Eブロック（当日オッズ収集）")
    print("  - 毎朝 8:30 - Dブロック（予想生成・オッズあり状態で通知）")
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

    # ログファイルへの出力設定
    _setup_file_logging()

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

    # 毎朝8:00にEブロック（当日オッズ収集）- Dブロックより先に実行
    schedule.every().day.at("08:00").do(block_e_job)
    print("[OK] 毎朝 8:00 - Eブロック（当日オッズ収集）")

    # 毎朝8:30にDブロック（予想生成）- Eブロック完了後（~08:28）にオッズあり状態で通知
    schedule.every().day.at("08:30").do(block_d_job)
    print("[OK] 毎朝 8:30 - Dブロック（予想生成）")

    # 1分ごとにレース監視（20分前取得、10分前通知）
    schedule.every(1).minutes.do(race_monitor_job)
    print("[OK] 1分ごと - レース監視（直前情報20分前取得、通知10分前送信）")

    # 毎週月曜・木曜04:00にracer_features更新（Aブロック完了後）
    # 最大遅延6日→3日に短縮（直近5走のトレンド精度向上のため週2回）
    schedule.every().monday.at("04:00").do(racer_features_job)
    schedule.every().thursday.at("04:00").do(racer_features_job)
    print("[OK] 毎週月曜・木曜 4:00 - racer_features / racer_venue_features 週2回更新")

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
