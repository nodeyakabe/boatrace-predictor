"""
2026年2月データ自動補完スクリプト

現在実行中のデータ補完（2022, 2024, 2025）完了後に自動実行
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# マスターログの最新ファイルを取得
def get_latest_multi_year_log():
    log_files = list(LOG_DIR.glob("multi_year_completion_*.log"))
    if not log_files:
        return None
    return max(log_files, key=lambda f: f.stat().st_mtime)

def wait_for_completion():
    """現在実行中のmulti_year_completionの完了を待つ"""
    print("=" * 80)
    print("現在実行中のデータ補完の完了を待機中...")
    print("=" * 80)

    log_file = get_latest_multi_year_log()
    if not log_file:
        print("[INFO] 実行中のデータ補完が見つかりません")
        return True

    print(f"監視対象: {log_file}")

    last_size = 0
    stable_count = 0

    while True:
        current_size = log_file.stat().st_size

        # ログファイルが成長していない場合
        if current_size == last_size:
            stable_count += 1
            if stable_count >= 3:  # 30秒間変化なし
                # 最終レポートの確認
                with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                    if '最終レポート' in content and ('2025年度 データ補完完了' in content or '全体完了時刻' in content):
                        print("\n[OK] データ補完が完了しました")
                        return True
        else:
            stable_count = 0
            last_size = current_size

        # 進捗を表示
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 待機中... (ログサイズ: {current_size:,} bytes)", end='\r')
        time.sleep(10)

def run_feb_2026_completion():
    """2026年2月のデータ補完を実行"""
    script_path = PROJECT_ROOT / "scripts" / "data_collection" / "補完_統合版_決まり手_レース詳細.py"

    print("\n" + "=" * 80)
    print("2026年2月データ補完を開始します")
    print("=" * 80)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"対象期間: 2026-02-01 ～ 2026-02-12")
    print("=" * 80 + "\n")

    try:
        cmd = [
            sys.executable,
            str(script_path),
            '--start-date', '2026-02-01',
            '--end-date', '2026-02-12'
        ]

        print(f"実行コマンド: {' '.join(cmd)}\n")

        # リアルタイム出力
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1
        )

        for line in process.stdout:
            print(line, end='')

        process.wait()

        print("\n" + "=" * 80)
        if process.returncode == 0:
            print("✅ 2026年2月データ補完が完了しました")
        else:
            print(f"❌ 補完が失敗しました（終了コード: {process.returncode}）")
        print("=" * 80)

        return process.returncode == 0

    except Exception as e:
        print(f"\n[ERROR] 補完実行エラー: {e}")
        return False

def main():
    print("=" * 80)
    print("2026年2月データ自動補完スクリプト")
    print("=" * 80)
    print(f"実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80 + "\n")

    # Step 1: 現在のデータ補完完了を待つ
    if not wait_for_completion():
        print("[ERROR] タイムアウトまたはエラー")
        return 1

    # 少し待機（ファイルクローズ等）
    print("\n準備中...")
    time.sleep(5)

    # Step 2: 2026年2月のデータ補完を実行
    success = run_feb_2026_completion()

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
