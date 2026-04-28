# -*- coding: utf-8 -*-
"""
2018-2019年データ収集 Phase 2-4 順次実行スクリプト

Phase 2: 決まり手補完（kimarite欠落0件のためスキップ予定）
Phase 3: レース詳細補完（race_details 222件欠落）
Phase 4: オッズ収集（trifecta_odds 全26,328件未収集）
"""

import sys
import io
import os
import subprocess
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_FILE = PROJECT_ROOT / "data" / "csv" / "2018_2019_full" / "phase2_4_log.txt"


def log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + "\n")


def run_phase(name: str, cmd: list, timeout: int = 14400) -> bool:
    log(f"{'='*60}")
    log(f"開始: {name}")
    log(f"コマンド: {' '.join(cmd)}")
    log(f"{'='*60}")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            timeout=timeout,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        if result.returncode == 0:
            log(f"✅ {name} 完了")
            return True
        else:
            log(f"❌ {name} 失敗 (returncode={result.returncode})")
            return False
    except subprocess.TimeoutExpired:
        log(f"❌ {name} タイムアウト（{timeout//3600}時間超過）")
        return False
    except Exception as e:
        log(f"❌ {name} 例外: {e}")
        return False


def main():
    log("=" * 70)
    log("2018-2019年 Phase 2-4 順次実行開始")
    log("=" * 70)

    results = {}

    # Phase 2: 決まり手補完
    ok = run_phase(
        "Phase 2: 決まり手補完",
        [sys.executable,
         str(PROJECT_ROOT / "scripts" / "data_collection" / "補完_決まり手データ_改善版.py"),
         "--start-date", "2018-01-01",
         "--end-date", "2019-12-31"],
        timeout=7200,
    )
    results["Phase 2 決まり手補完"] = "✅ 完了" if ok else "❌ 失敗"
    if not ok:
        log("⚠️  Phase 2 失敗。Phase 3へ継続。")

    # Phase 3: レース詳細補完
    ok = run_phase(
        "Phase 3: レース詳細補完",
        [sys.executable,
         str(PROJECT_ROOT / "scripts" / "data_collection" / "補完_レース詳細データ_改善版v4.py"),
         "--start-date", "2018-01-01",
         "--end-date", "2019-12-31"],
        timeout=14400,  # 4時間
    )
    results["Phase 3 レース詳細補完"] = "✅ 完了" if ok else "❌ 失敗"
    if not ok:
        log("⚠️  Phase 3 失敗。Phase 4へ継続。")

    # Phase 4: オッズ収集
    ok = run_phase(
        "Phase 4: trifecta_odds収集",
        [sys.executable,
         str(PROJECT_ROOT / "scripts" / "data_collection" / "fetch_odds_parallel_safe.py"),
         "--start-date", "2018-01-01",
         "--end-date", "2019-12-31"],
        timeout=21600,  # 6時間
    )
    results["Phase 4 trifecta_odds収集"] = "✅ 完了" if ok else "❌ 失敗"

    # サマリー
    log("")
    log("=" * 70)
    log("Phase 2-4 実行完了サマリー")
    log("=" * 70)
    for phase, status in results.items():
        log(f"  {status}  {phase}")

    all_ok = all("✅" in v for v in results.values())
    if all_ok:
        log("")
        log("Phase 2-4 ALL_SUCCESS")  # ウォッチャーが検知する成功マーカー
        log("🎉 Phase 2-4 全完了！")
        log("次のステップ:")
        log("  Phase 5: python scripts/data_collection/fetch_2018_2019_beforeinfo.py")
    else:
        log("")
        log("⚠️  一部失敗。ログを確認して再実行してください。")
        log("Phase 2-4 FAILED")  # 失敗時はALL_SUCCESSを出力しない


if __name__ == '__main__':
    main()
