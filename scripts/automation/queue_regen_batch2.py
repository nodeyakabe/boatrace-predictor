#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2スケール混在問題 修正バッチ2 自動キュー実行スクリプト（2026-03-02更新版）
==========================================================
【目的】
  2025 before --force 完了を検知 → 残る全対象年度を順次・並行実行

【背景】
  2025-12-22 に max_confidence 制限がコメントアウトされ、
  2022〜2026 の一部予測が旧コード（A率40-52%）で生成された。
  現行コードで全件再生成することで信頼度分布を正規化する。

【再生成対象一覧（全件）】
  旧コード A率   → 正常 A率   優先度
  2022 advance  39.6% → ~19%  実行中（別プロセス）
  2025 before   51.3% → ~19%  実行中（別プロセス＝本スクリプトの待機対象）
  2022 before    6.7% → ~17%  BATCH 2a
  2023 advance  52.8% → ~20%  BATCH 2b  ←並行
  2024 advance  51.8% → ~15%  BATCH 3
  2026 before   46.4% → ~19%  BATCH 3b  ←並行（上位AIで追加発見）
  2024 before   20.1% → ~10%  BATCH 4
  2023 before   20.5% → ~20%  BATCH 4b  ←並行（正常に近いが統一）

  ★ 2025 advance / 2020・2021 全タイプ: 新コード生成のみ → 対象外

【実行順序】
  WAIT:    2025 before --force  (既実行中)
  BATCH 2: 2022 before + 2023 advance  (並行)
  BATCH 3: 2024 advance + 2026 before  (並行)
  BATCH 4: 2024 before + 2023 before   (並行)
  FINAL:   standard_backtest_unique.py --full

【2024 advance のA率=2.5%（新コード）について】
  _calculate_confidence が補正前スコアで判定するため、2024年データ特性で
  C率が高くなる設計上の問題（別途要検討）。--force 再生成でも2.5%付近に
  なる可能性があるが、少なくとも旧コードの51.8%は解消される。
"""

import subprocess
import sys
import time
import logging
import os
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ─────────────────────────────────────────────────────
# ログ設定
# ─────────────────────────────────────────────────────
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"regen_batch2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WATCH_LOG = PROJECT_ROOT / "logs" / "regen_2025bef_20260302_110226.log"


def wait_for_log_completion(log_path: Path, check_keywords=None, check_interval=120) -> bool:
    """ログファイルの完了を待機する。

    完了の判定条件:
    1. ログファイルの末尾にキーワードが含まれる
    2. または 120秒間ファイルサイズが変化しない（3回連続）
    """
    if check_keywords is None:
        check_keywords = ["Phase 2完了", "Phase 2 完了", "全件完了", "DB投入完了"]

    logger.info(f"監視対象ログ: {log_path}")
    last_size = -1
    stable_count = 0
    stable_threshold = 3

    while True:
        if not log_path.exists():
            logger.info(f"  ログファイル未存在、{check_interval}秒後に再確認...")
            time.sleep(check_interval)
            continue

        current_size = log_path.stat().st_size

        try:
            tail = log_path.read_text(encoding='utf-8', errors='replace')[-3000:]
            for kw in check_keywords:
                if kw in tail:
                    logger.info(f"  ✅ 完了キーワード検出: '{kw}'")
                    return True
        except Exception:
            pass

        if current_size == last_size and current_size > 1000:
            stable_count += 1
            logger.info(f"  ファイルサイズ安定 {stable_count}/{stable_threshold} ({current_size:,} bytes)")
            if stable_count >= stable_threshold:
                logger.info("  ✅ ファイルサイズ3回連続変化なし → 完了と判断")
                return True
        else:
            stable_count = 0
            logger.info(f"  処理中... サイズ={current_size:,} bytes")

        last_size = current_size
        time.sleep(check_interval)


def run_regen(year: int, pred_type: str, log_suffix: str) -> subprocess.Popen:
    """--force 再生成を非同期で起動"""
    script_map = {
        'advance': 'scripts/prediction/generate_advance_fast.py',
        'before':  'scripts/prediction/generate_before_fast.py',
    }
    script = script_map[pred_type]
    out_log = PROJECT_ROOT / "logs" / f"regen_{year}{pred_type[:3]}_{log_suffix}.log"
    logger.info(f"  起動: {year} {pred_type} --force  → {out_log.name}")

    with open(out_log, 'w', encoding='utf-8') as f:
        proc = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / script), '--year', str(year), '--force'],
            stdout=f, stderr=f,
            cwd=str(PROJECT_ROOT),
        )
    logger.info(f"  PID {proc.pid}")
    return proc


def wait_for_procs(procs: list, names: list, check_interval=120):
    """複数プロセスの完了を待機"""
    remaining = list(zip(procs, names))
    while remaining:
        still_running = []
        for proc, name in remaining:
            if proc.poll() is None:
                still_running.append((proc, name))
            else:
                rc = proc.returncode
                status = "✅" if rc == 0 else "❌"
                logger.info(f"  {status} {name} 完了 (returncode={rc})")
        remaining = still_running
        if remaining:
            logger.info(f"  待機中: {[n for _, n in remaining]}")
            time.sleep(check_interval)


def run_step(step_num: int, name: str, cmd: list) -> bool:
    logger.info(f"\n{'='*60}")
    logger.info(f"STEP {step_num}: {name}")
    logger.info(f"コマンド: {' '.join(str(c) for c in cmd)}")
    logger.info('='*60)
    start = datetime.now()
    result = subprocess.run([str(c) for c in cmd], cwd=str(PROJECT_ROOT))
    elapsed = int((datetime.now() - start).total_seconds())
    h, m, s = elapsed//3600, (elapsed%3600)//60, elapsed%60
    elapsed_str = f"{h}時間{m}分{s}秒" if h else f"{m}分{s}秒"
    if result.returncode == 0:
        logger.info(f"✅ STEP {step_num} 完了 (所要: {elapsed_str})")
        return True
    else:
        logger.error(f"❌ STEP {step_num} 失敗 (returncode={result.returncode})")
        return False


def main():
    start_time = datetime.now()
    logger.info("="*60)
    logger.info("2スケール混在修正 バッチ2 キュー実行スクリプト")
    logger.info(f"開始: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"ログ: {log_file}")
    logger.info("")
    logger.info("実行予定:")
    logger.info("  WAIT    → 2025 before --force 完了待ち")
    logger.info("  BATCH 2 → 2022 before + 2023 advance（並行）")
    logger.info("  BATCH 3 → 2024 advance + 2026 before（並行）")
    logger.info("  BATCH 4 → 2024 before + 2023 before（並行）")
    logger.info("  FINAL   → 標準テスト 6年間")
    logger.info("="*60)

    suffix = datetime.now().strftime('%Y%m%d_%H%M%S')

    # ─────────────────────────────────────────────────────
    # WAIT: 2025 before --force の完了を待機
    # ─────────────────────────────────────────────────────
    logger.info("\n[WAIT] 2025 before --force の完了を待機中...")
    logger.info(f"  監視ログ: {WATCH_LOG}")
    wait_for_log_completion(WATCH_LOG, check_interval=120)
    logger.info("✅ 2025 before --force 完了を確認\n")

    # ─────────────────────────────────────────────────────
    # BATCH 2: 2022 before + 2023 advance を並行実行
    # ─────────────────────────────────────────────────────
    logger.info("[BATCH 2] 2022 before + 2023 advance を並行実行...")
    proc_2022bef = run_regen(2022, 'before',  suffix)
    proc_2023adv = run_regen(2023, 'advance', suffix)
    wait_for_procs(
        [proc_2022bef, proc_2023adv],
        ['2022 before --force', '2023 advance --force'],
        check_interval=120,
    )
    logger.info("✅ BATCH 2 完了\n")

    # ─────────────────────────────────────────────────────
    # BATCH 3: 2024 advance + 2026 before を並行実行
    # ─────────────────────────────────────────────────────
    logger.info("[BATCH 3] 2024 advance + 2026 before を並行実行...")
    proc_2024adv = run_regen(2024, 'advance', suffix)
    proc_2026bef = run_regen(2026, 'before',  suffix)
    wait_for_procs(
        [proc_2024adv, proc_2026bef],
        ['2024 advance --force', '2026 before --force'],
        check_interval=120,
    )
    logger.info("✅ BATCH 3 完了\n")

    # ─────────────────────────────────────────────────────
    # BATCH 4: 2024 before + 2023 before を並行実行
    # ─────────────────────────────────────────────────────
    logger.info("[BATCH 4] 2024 before + 2023 before を並行実行...")
    proc_2024bef = run_regen(2024, 'before',  suffix)
    proc_2023bef = run_regen(2023, 'before',  suffix)
    wait_for_procs(
        [proc_2024bef, proc_2023bef],
        ['2024 before --force', '2023 before --force'],
        check_interval=120,
    )
    logger.info("✅ BATCH 4 完了\n")

    # ─────────────────────────────────────────────────────
    # FINAL: 標準テスト（全年度）
    # ─────────────────────────────────────────────────────
    run_step(
        99, "全年度 標準テスト (standard_backtest_unique.py --full)",
        [sys.executable, str(PROJECT_ROOT / 'scripts/backtest/standard_backtest_unique.py'), '--full'],
    )

    elapsed_total = int((datetime.now() - start_time).total_seconds())
    h, m, s = elapsed_total//3600, (elapsed_total%3600)//60, elapsed_total%60
    logger.info("\n" + "="*60)
    logger.info("全バッチ完了!")
    logger.info(f"総所要時間: {h}時間{m}分{s}秒")
    logger.info(f"ログ: {log_file}")
    logger.info("="*60)


if __name__ == "__main__":
    main()
