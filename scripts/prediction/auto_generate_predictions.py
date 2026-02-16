"""
予測生成自動連携スクリプト

before予想 → advance予想を自動で順次実行します。

使用方法:
    python scripts/prediction/auto_generate_predictions.py

特徴:
- before予想完了を待機
- 完了後、自動的にadvance予想を開始
- ロックファイルを自動削除
- エラー時も継続
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import subprocess
import time
from pathlib import Path
from datetime import datetime
import glob

PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
MASTER_LOG = LOG_DIR / f'auto_predictions_{timestamp}.log'

def log_print(message):
    """コンソールとログに出力"""
    print(message)
    with open(MASTER_LOG, 'a', encoding='utf-8') as f:
        f.write(message + '\n')

def remove_lock_files():
    """予測のロックファイルを削除"""
    lock_files = glob.glob(str(PROJECT_ROOT / 'data' / '.lock_prediction_*'))
    for f in lock_files:
        try:
            Path(f).unlink()
            log_print(f'  削除: {f}')
        except Exception as e:
            log_print(f'  削除失敗: {f} - {e}')
    return len(lock_files)

def run_prediction(prediction_type):
    """予測生成を実行"""
    log_print(f"\n{'='*80}")
    log_print(f"{prediction_type}予想生成 開始")
    log_print(f"{'='*80}")
    log_print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    start_time = time.time()

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / 'scripts' / 'prediction' / 'generate_predictions.py'),
        '--years', '2020,2021,2022,2023,2024,2025',
        '--type', prediction_type
    ]

    log_print(f"実行コマンド: {' '.join(cmd)}\n")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1
        )

        # リアルタイム出力
        for line in process.stdout:
            print(line, end='')
            with open(MASTER_LOG, 'a', encoding='utf-8') as f:
                f.write(line)

        process.wait()
        elapsed = time.time() - start_time

        log_print(f"\n{'='*80}")
        if process.returncode == 0:
            log_print(f"✅ {prediction_type}予想生成 完了")
            log_print(f"処理時間: {elapsed/3600:.2f}時間（{elapsed/60:.1f}分）")
            log_print(f"{'='*80}\n")
            return True
        else:
            log_print(f"❌ {prediction_type}予想生成 失敗（終了コード: {process.returncode}）")
            log_print(f"処理時間: {elapsed/3600:.2f}時間（{elapsed/60:.1f}分）")
            log_print(f"{'='*80}\n")
            return False

    except Exception as e:
        elapsed = time.time() - start_time
        log_print(f"\n{'='*80}")
        log_print(f"❌ {prediction_type}予想生成 エラー")
        log_print(f"エラー内容: {str(e)}")
        log_print(f"処理時間: {elapsed/3600:.2f}時間（{elapsed/60:.1f}分）")
        log_print(f"{'='*80}\n")
        return False

def main():
    log_print("="*80)
    log_print("予測生成自動連携スクリプト")
    log_print("="*80)
    log_print(f"実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"マスターログ: {MASTER_LOG}")
    log_print("="*80)

    overall_start = time.time()
    results = []

    # ロックファイル削除
    log_print("\n" + "="*80)
    log_print("ロックファイル削除")
    log_print("="*80)
    removed = remove_lock_files()
    log_print(f"削除したロックファイル数: {removed}")

    # before予想生成
    success_before = run_prediction('before')
    results.append(('before予想生成', success_before))

    if not success_before:
        log_print("[WARNING] before予想生成が失敗しましたが、advance予想を続行します")

    # 少し待機
    time.sleep(5)

    # 再度ロックファイル削除
    log_print("\n" + "="*80)
    log_print("ロックファイル再削除（advance予想前）")
    log_print("="*80)
    removed = remove_lock_files()
    log_print(f"削除したロックファイル数: {removed}")

    # advance予想生成
    success_advance = run_prediction('advance')
    results.append(('advance予想生成', success_advance))

    # 最終レポート
    overall_elapsed = time.time() - overall_start

    log_print("\n" + "="*80)
    log_print("最終レポート")
    log_print("="*80)
    log_print(f"全体完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"総処理時間: {overall_elapsed/3600:.2f}時間（{overall_elapsed/60:.1f}分）")

    log_print("\n" + "-"*80)
    log_print("結果")
    log_print("-"*80)

    success_count = sum(1 for _, success in results if success)
    failed_count = len(results) - success_count

    for task_name, success in results:
        status = "✅" if success else "❌"
        log_print(f"  {status} {task_name}")

    log_print("\n" + "-"*80)
    log_print("サマリー")
    log_print("-"*80)
    log_print(f"  総タスク数: {len(results)}")
    log_print(f"  成功: {success_count} ✅")
    log_print(f"  失敗: {failed_count} ❌")

    if success_count == len(results):
        log_print(f"\n🎉 すべてのタスクが正常に完了しました！")
    else:
        log_print(f"\n⚠️ 一部のタスクで問題が発生しました。")

    log_print("\n" + "="*80)
    log_print(f"マスターログ: {MASTER_LOG}")
    log_print("="*80)

    return 0 if failed_count == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
