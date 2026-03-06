#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全タスク完了後の予測再生成パイプライン（2026-02-27作成）
================================================================================

【実行フロー】
  STEP 0: 実行中プロセスの完了待機
    - PID 6772:  2025年 actual_course補完
    - PID 13016: 2024年 advance予測CSV生成
    - PID 5444:  2024年 beforeinfo CSV収集

  STEP 1: 2024年 beforeinfo CSV → DB投入 (exhibition_time)

  STEP 2: 2024年 advance予測再生成 (actual_course 96.4% 反映)
  STEP 3: 2024年 before予測再生成  (exhibition_time 補完後)

  STEP 4: 2020年 advance予測再生成 (actual_course 82%→98.9% 反映)
  STEP 5: 2020年 before予測再生成

  STEP 6: 標準テスト実行 (6年間 standard_backtest_unique.py --full)

【確認方法（2日後）】
  - ログ:         logs/pipeline_YYYYMMDD_HHMMSS.log
  - advance CSV:  data/predictions_csv/advance/{2020,2024}/
  - before  CSV:  data/predictions_csv/before/{2020,2024}/
  - 標準テスト結果: ログの末尾
================================================================================
"""

import subprocess
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# ログ設定
# ──────────────────────────────────────────────────────────────────────────────
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────────────────────────────

def is_process_running(pid: int) -> bool:
    """PIDのプロセスが実行中か確認（Windows wmic使用）"""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", f"processid={pid}", "get", "processid"],
            capture_output=True, text=True, timeout=15,
        )
        return str(pid) in result.stdout
    except Exception:
        return False  # 確認できない場合は完了とみなす


def wait_for_process(pid: int, name: str, check_interval: int = 120) -> None:
    """プロセスが終了するまで待機"""
    if not is_process_running(pid):
        logger.info(f"  [{name}] PID {pid} は既に完了済み (スキップ)")
        return
    logger.info(f"  [{name}] PID {pid} の完了を待機中... (確認間隔: {check_interval}秒)")
    while is_process_running(pid):
        time.sleep(check_interval)
    logger.info(f"  [{name}] ✅ 完了")


def run_step(step_num: int, name: str, cmd: list, allow_fail: bool = False) -> bool:
    """
    ステップを実行してログに記録する。
    allow_fail=True の場合、失敗してもパイプラインを継続する。
    """
    sep = "=" * 60
    logger.info("")
    logger.info(sep)
    logger.info(f"STEP {step_num}: {name}")
    logger.info(f"コマンド: {' '.join(cmd)}")
    logger.info(sep)
    start = datetime.now()

    result = subprocess.run(cmd)

    elapsed = int((datetime.now() - start).total_seconds())
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    elapsed_str = f"{h}時間{m}分{s}秒" if h else f"{m}分{s}秒"

    if result.returncode == 0:
        logger.info(f"✅ STEP {step_num} 完了 (所要: {elapsed_str})")
        return True
    else:
        msg = f"❌ STEP {step_num} 失敗 (returncode={result.returncode}, 所要: {elapsed_str})"
        if allow_fail:
            logger.warning(msg + " → 続行します")
        else:
            logger.error(msg)
        return False


# ──────────────────────────────────────────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────────────────────────────────────────

def main():
    pipeline_start = datetime.now()
    logger.info("")
    logger.info("=" * 60)
    logger.info("予測再生成パイプライン 開始")
    logger.info(f"開始時刻: {pipeline_start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"ログ:     {log_file}")
    logger.info("=" * 60)

    # ────────────────────────────────────────────────────────────────────
    # STEP 0: 実行中プロセスの完了待機
    # ────────────────────────────────────────────────────────────────────
    logger.info("")
    logger.info("STEP 0: 実行中プロセスの完了待機")
    logger.info("-" * 40)

    waiting = {
        6772:  "2025年 actual_course補完",
        13016: "2024年 advance予測CSV生成",
        5444:  "2024年 beforeinfo CSV収集",
    }
    for pid, name in waiting.items():
        wait_for_process(pid, name, check_interval=120)

    logger.info("全待機プロセス 完了 ✅")

    # ────────────────────────────────────────────────────────────────────
    # STEP 1: beforeinfo CSV → DB投入（2024年 exhibition_time）
    # ────────────────────────────────────────────────────────────────────
    run_step(
        1, "2024年 beforeinfo(exhibition_time) CSV → DB投入",
        ["python", "scripts/data_collection/import_beforeinfo_csv_to_db.py",
         "--input", "data/csv/beforeinfo/2024"],
        allow_fail=True,
    )

    # ────────────────────────────────────────────────────────────────────
    # STEP 2: 2024年 advance予測再生成
    # （actual_course 96.4% 反映済みデータで再生成）
    # ────────────────────────────────────────────────────────────────────
    run_step(
        2, "2024年 advance予測再生成 (CSV+DB)",
        ["python", "scripts/prediction/generate_advance_fast.py", "--year", "2024"],
    )

    # ────────────────────────────────────────────────────────────────────
    # STEP 3: 2024年 before予測再生成
    # （exhibition_time DB投入後に実行）
    # ────────────────────────────────────────────────────────────────────
    run_step(
        3, "2024年 before予測再生成 (CSV+DB)",
        ["python", "scripts/prediction/generate_before_fast.py", "--year", "2024"],
    )

    # ────────────────────────────────────────────────────────────────────
    # STEP 4: 2020年 advance予測再生成
    # （actual_course 82%→98.9% 反映）
    # ────────────────────────────────────────────────────────────────────
    run_step(
        4, "2020年 advance予測再生成 (CSV+DB)",
        ["python", "scripts/prediction/generate_advance_fast.py", "--year", "2020"],
    )

    # ────────────────────────────────────────────────────────────────────
    # STEP 5: 2020年 before予測再生成
    # ────────────────────────────────────────────────────────────────────
    run_step(
        5, "2020年 before予測再生成 (CSV+DB)",
        ["python", "scripts/prediction/generate_before_fast.py", "--year", "2020"],
    )

    # ────────────────────────────────────────────────────────────────────
    # STEP 6: 標準テスト（6年間 2020-2025）
    # ────────────────────────────────────────────────────────────────────
    run_step(
        6, "標準テスト 6年間 (standard_backtest_unique.py --full)",
        ["python", "scripts/backtest/standard_backtest_unique.py", "--full"],
    )

    # ────────────────────────────────────────────────────────────────────
    # 完了レポート
    # ────────────────────────────────────────────────────────────────────
    elapsed_total = int((datetime.now() - pipeline_start).total_seconds())
    h = elapsed_total // 3600
    m = (elapsed_total % 3600) // 60
    s = elapsed_total % 60

    logger.info("")
    logger.info("=" * 60)
    logger.info("全パイプライン 完了!")
    logger.info(f"総所要時間: {h}時間{m}分{s}秒")
    logger.info(f"ログ:       {log_file}")
    logger.info("")
    logger.info("【確認項目（2日後）】")
    logger.info("  advance CSV: data/predictions_csv/advance/2020/")
    logger.info("  advance CSV: data/predictions_csv/advance/2024/")
    logger.info("  before  CSV: data/predictions_csv/before/2020/")
    logger.info("  before  CSV: data/predictions_csv/before/2024/")
    logger.info("  標準テスト: ログの末尾を確認")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
