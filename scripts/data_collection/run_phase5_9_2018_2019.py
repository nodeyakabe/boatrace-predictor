# -*- coding: utf-8 -*-
"""
2018-2019年データ収集 Phase 5-9 順次実行スクリプト

Phase 5: beforeinfo収集（exhibition_time, tilt_angle等）
Phase 6: 統計指標再生成（player_escape_stats / stadium_attack_stats, 2018-2025）
Phase 7: advance予測生成（2018年・2019年）
Phase 8: before予測生成（2018年・2019年）
Phase 9: 8年間バックテスト（2018-2025）

【再起動耐性】
各フェーズ完了時にマーカーファイルを作成。
PC再起動後に再実行しても完了済みフェーズはスキップされる。
マーカーディレクトリ: data/csv/2018_2019_full/markers/
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
LOG_FILE = PROJECT_ROOT / "data" / "csv" / "2018_2019_full" / "phase5_9_log.txt"
MARKER_DIR = PROJECT_ROOT / "data" / "csv" / "2018_2019_full" / "markers"


def log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + "\n")


def phase_done(name: str) -> bool:
    return (MARKER_DIR / f"{name}.done").exists()


def mark_phase_done(name: str):
    MARKER_DIR.mkdir(parents=True, exist_ok=True)
    (MARKER_DIR / f"{name}.done").write_text(datetime.now().isoformat(), encoding='utf-8')


def run_phase(name: str, cmd: list, timeout: int = 14400) -> bool:
    log(f"{'='*60}")
    log(f"開始: {name}")
    log(f"コマンド: {' '.join(str(c) for c in cmd)}")
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
    log("2018-2019年 Phase 5-9 順次実行開始")
    log("=" * 70)

    results = {}

    # Phase 5: beforeinfo収集
    phase_key = "phase5"
    if phase_done(phase_key):
        log("Phase 5: beforeinfo収集 — スキップ（完了済み）")
        results["Phase 5 beforeinfo収集"] = "✅ 完了（スキップ）"
    else:
        ok = run_phase(
            "Phase 5: beforeinfo収集（展示タイム・チルト等）",
            [sys.executable,
             str(PROJECT_ROOT / "scripts" / "data_collection" / "fetch_2018_2019_beforeinfo.py")],
            timeout=86400,  # 24時間
        )
        results["Phase 5 beforeinfo収集"] = "✅ 完了" if ok else "❌ 失敗"
        if ok:
            mark_phase_done(phase_key)
        else:
            log("⚠️  Phase 5 失敗。Phase 6へ継続。")

    # Phase 6: 統計指標再生成（2018-2025対応）
    phase_key = "phase6"
    if phase_done(phase_key):
        log("Phase 6: 統計指標再生成 — スキップ（完了済み）")
        results["Phase 6 統計指標再生成"] = "✅ 完了（スキップ）"
    else:
        ok = run_phase(
            "Phase 6: 統計指標再生成（2018-2025）",
            [sys.executable,
             str(PROJECT_ROOT / "scripts" / "data_collection" / "build_indicator_stats.py"),
             "--yearly"],
            timeout=7200,
        )
        results["Phase 6 統計指標再生成"] = "✅ 完了" if ok else "❌ 失敗"
        if ok:
            mark_phase_done(phase_key)
        else:
            log("⚠️  Phase 6 失敗。Phase 7へ継続。")

    # Phase 7: advance予測生成（2018・2019年）
    for year in [2018, 2019]:
        phase_key = f"phase7_{year}"
        if phase_done(phase_key):
            log(f"Phase 7 advance予測({year}) — スキップ（完了済み）")
            results[f"Phase 7 advance予測({year})"] = "✅ 完了（スキップ）"
        else:
            ok = run_phase(
                f"Phase 7: advance予測生成（{year}年）",
                [sys.executable,
                 str(PROJECT_ROOT / "scripts" / "prediction" / "generate_advance_fast.py"),
                 "--year", str(year)],
                timeout=14400,
            )
            results[f"Phase 7 advance予測({year})"] = "✅ 完了" if ok else "❌ 失敗"
            if ok:
                mark_phase_done(phase_key)
            else:
                log(f"⚠️  Phase 7 ({year}) 失敗。継続。")

    # Phase 8: before予測生成（2018・2019年）
    for year in [2018, 2019]:
        phase_key = f"phase8_{year}"
        if phase_done(phase_key):
            log(f"Phase 8 before予測({year}) — スキップ（完了済み）")
            results[f"Phase 8 before予測({year})"] = "✅ 完了（スキップ）"
        else:
            ok = run_phase(
                f"Phase 8: before予測生成（{year}年）",
                [sys.executable,
                 str(PROJECT_ROOT / "scripts" / "prediction" / "generate_before_fast.py"),
                 "--year", str(year)],
                timeout=86400,  # 24時間（1年分の生成に十分な時間）
            )
            results[f"Phase 8 before予測({year})"] = "✅ 完了" if ok else "❌ 失敗"
            if ok:
                mark_phase_done(phase_key)
            else:
                log(f"⚠️  Phase 8 ({year}) 失敗。継続。")

    # Phase 9: 8年間バックテスト（2018-2025）
    phase_key = "phase9"
    if phase_done(phase_key):
        log("Phase 9: バックテスト — スキップ（完了済み）")
        results["Phase 9 8年間バックテスト"] = "✅ 完了（スキップ）"
    else:
        ok = run_phase(
            "Phase 9: 8年間バックテスト（2018-2025）",
            [sys.executable,
             str(PROJECT_ROOT / "scripts" / "backtest" / "standard_backtest_unique.py"),
             "--full"],
            timeout=3600,
        )
        results["Phase 9 8年間バックテスト"] = "✅ 完了" if ok else "❌ 失敗"
        if ok:
            mark_phase_done(phase_key)

    # 最終サマリー
    log("")
    log("=" * 70)
    log("Phase 5-9 実行完了サマリー")
    log("=" * 70)
    for phase, status in results.items():
        log(f"  {status}  {phase}")

    all_ok = all("✅" in v for v in results.values())
    if all_ok:
        log("")
        log("Phase 5-9 ALL_SUCCESS")  # ウォッチャー用マーカー
        log("🎉 Phase 5-9 全完了！2018-2019年データ収集パイプライン完了。")
        log("バックテスト結果を docs/HANDOVER.md に反映してください。")
    else:
        failed = [k for k, v in results.items() if "❌" in v]
        log("")
        log(f"⚠️  {len(failed)}フェーズ失敗: {failed}")
        log("再実行すると完了済みフェーズはスキップされます:")
        log("  python scripts/data_collection/run_phase5_9_2018_2019.py")


if __name__ == '__main__':
    main()
