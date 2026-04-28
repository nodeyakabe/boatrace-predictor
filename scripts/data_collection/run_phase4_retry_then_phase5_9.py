# -*- coding: utf-8 -*-
"""
Phase 4 再実行 + Phase 5-9 自動継続スクリプト

【背景】
Phase 4（trifecta_odds）が6時間タイムアウトで失敗。
22,100/26,328件（83.9%）は収集済み。
fetch_odds_parallel_safe.py はDB上の既収集レースを自動スキップするため、
再実行すると残り16.1%（約4,228件）のみ収集する。
完了後、run_phase5_9_2018_2019.py を自動実行する。
"""

import sys
import io
import subprocess
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_FILE = PROJECT_ROOT / "data" / "csv" / "2018_2019_full" / "phase4_retry_log.txt"
PHASE24_LOG = PROJECT_ROOT / "data" / "csv" / "2018_2019_full" / "phase2_4_log.txt"


def log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + "\n")


def append_phase24_log(msg: str):
    """Phase 2-4ログにも記録（ウォッチャーが検知できるように）"""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    with open(PHASE24_LOG, 'a', encoding='utf-8') as f:
        f.write(line + "\n")


def main():
    log("=" * 70)
    log("Phase 4 再実行（残り約16%）→ Phase 5-9 自動継続")
    log("=" * 70)

    # Phase 4 再実行（タイムアウト12時間）
    log("開始: Phase 4 trifecta_odds収集（再実行・既収集スキップあり）")
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "data_collection" / "fetch_odds_parallel_safe.py"),
        "--start-date", "2018-01-01",
        "--end-date", "2019-12-31",
    ]
    log(f"コマンド: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            timeout=43200,  # 12時間
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        phase4_ok = result.returncode == 0
    except subprocess.TimeoutExpired:
        log("❌ Phase 4 タイムアウト（12時間超過）")
        phase4_ok = False
    except Exception as e:
        log(f"❌ Phase 4 例外: {e}")
        phase4_ok = False

    if not phase4_ok:
        log("❌ Phase 4 失敗。処理を中止します。")
        log("  残り件数を確認して再実行してください:")
        log("  python scripts/data_collection/run_phase4_retry_then_phase5_9.py")
        return

    log("✅ Phase 4 完了")

    # phase2_4_log にも成功マーカーを追記（ウォッチャーが残っている場合のため）
    append_phase24_log("Phase 2-4 ALL_SUCCESS")
    log("Phase 2-4 ALL_SUCCESS マーカーをログに追記しました")

    # Phase 5-9 起動
    log("=" * 70)
    log("Phase 5-9 を起動します")
    log("=" * 70)

    phase59_script = PROJECT_ROOT / "scripts" / "data_collection" / "run_phase5_9_2018_2019.py"
    result = subprocess.run(
        [sys.executable, str(phase59_script)],
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode == 0:
        log("✅ Phase 5-9 全完了")
    else:
        log(f"❌ Phase 5-9 失敗。再実行:")
        log("  python scripts/data_collection/run_phase5_9_2018_2019.py")


if __name__ == '__main__':
    main()
