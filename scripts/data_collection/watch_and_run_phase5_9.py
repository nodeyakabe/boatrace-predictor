# -*- coding: utf-8 -*-
"""
Phase 4完了を監視してPhase 5-9を自動起動するウォッチャー

phase2_4_log.txt に「Phase 2-4 ALL_SUCCESS」が書き込まれたら
run_phase5_9_2018_2019.py を自動実行する。

【成功時のみ起動】
Phase 2-4が失敗した場合（FAILED）はPhase 5-9を起動しない。

【再起動耐性】
- PC再起動後に再実行すると、Phase 2-4完了ログを検知して即座にPhase 5-9を開始
- Phase 5-9がすでに完了済みの場合はその旨を表示して終了
"""

import sys
import io
import time
import subprocess
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
PHASE24_LOG = PROJECT_ROOT / "data" / "csv" / "2018_2019_full" / "phase2_4_log.txt"
PHASE59_LOG = PROJECT_ROOT / "data" / "csv" / "2018_2019_full" / "phase5_9_log.txt"
PHASE59_SCRIPT = PROJECT_ROOT / "scripts" / "data_collection" / "run_phase5_9_2018_2019.py"

SUCCESS_MARKER = "Phase 2-4 ALL_SUCCESS"   # Phase 2-4成功時のみ出力
FAILED_MARKER = "Phase 2-4 FAILED"         # Phase 2-4失敗時のみ出力
PHASE59_DONE_MARKER = "Phase 5-9 ALL_SUCCESS"

POLL_INTERVAL = 120  # 2分ごとにチェック


def ts():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def read_log(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return ""


def phase24_succeeded() -> bool:
    return SUCCESS_MARKER in read_log(PHASE24_LOG)


def phase24_failed() -> bool:
    return FAILED_MARKER in read_log(PHASE24_LOG)


def phase24_finished() -> bool:
    return phase24_succeeded() or phase24_failed()


def phase59_already_done() -> bool:
    return PHASE59_DONE_MARKER in read_log(PHASE59_LOG)


def main():
    print(f"[{ts()}] ウォッチャー起動: Phase 4完了を監視中...")
    print(f"[{ts()}] 監視対象: {PHASE24_LOG}")
    print(f"[{ts()}] チェック間隔: {POLL_INTERVAL}秒")
    print(f"[{ts()}] 検知マーカー: '{SUCCESS_MARKER}'（成功時のみ起動）")

    # Phase 5-9がすでに完了している場合は終了
    if phase59_already_done():
        print(f"[{ts()}] Phase 5-9 はすでに完了済み。ウォッチャー終了。")
        return

    # Phase 2-4完了待機
    if phase24_finished():
        print(f"[{ts()}] Phase 2-4はすでに終了済み。ログを確認します。")
    else:
        print(f"[{ts()}] Phase 4完了待機中...")
        while not phase24_finished():
            time.sleep(POLL_INTERVAL)
            print(f"[{ts()}] 待機中... (Phase 4実行中)")

    # 成功/失敗の判定
    if phase24_failed():
        print(f"[{ts()}] ❌ Phase 2-4 が失敗しました。Phase 5-9 は起動しません。")
        print(f"[{ts()}] ログを確認して手動で対応してください: {PHASE24_LOG}")
        return

    if not phase24_succeeded():
        print(f"[{ts()}] ⚠️  成功マーカーが見つかりません。Phase 5-9 は起動しません。")
        print(f"[{ts()}] ログ確認: {PHASE24_LOG}")
        return

    print(f"[{ts()}] ✅ Phase 2-4 成功を確認！Phase 5-9 を起動します。")
    print(f"[{ts()}] スクリプト: {PHASE59_SCRIPT}")

    result = subprocess.run(
        [sys.executable, str(PHASE59_SCRIPT)],
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode == 0:
        print(f"[{ts()}] ✅ Phase 5-9 全完了")
    else:
        print(f"[{ts()}] ❌ Phase 5-9 失敗 (returncode={result.returncode})")
        print(f"[{ts()}] 再実行: python scripts/data_collection/run_phase5_9_2018_2019.py")


if __name__ == '__main__':
    main()
