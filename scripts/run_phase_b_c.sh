#!/bin/bash
# Phase B + C: before/advance全年度再生成 → バックテスト
# 2026-03-19 作成（run_longrun_tasks.sh から分離）
# Phase A完了後に自動呼び出しされる

set -e
cd "$(dirname "$0")/.."

LOG_DATE=$(date +%Y%m%d)
echo "================================================================"
echo "=== Phase B 開始: $(date) ==="
echo "================================================================"

# ================================================================
# Phase B-1: CSV生成（並列OK - DBに触れない）
# ================================================================

echo ""
echo "[Phase B-1] before CSV生成（workers=2）とadvance CSV生成（workers=1）を並列起動..."

(
  for YEAR in 2020 2021 2022 2023 2024 2025; do
    echo "[before] ${YEAR}年 CSV生成中..."
    python scripts/prediction/generate_before_fast_parallel.py \
        --year $YEAR --workers 2 --force --csv-only
    echo "[before] ${YEAR}年 CSV生成完了"
  done
) >> logs/before_regen_${LOG_DATE}.log 2>&1 &
BEFORE_PID=$!

(
  for YEAR in 2020 2021 2022 2023 2024 2025; do
    echo "[advance] ${YEAR}年 CSV生成中..."
    python scripts/prediction/generate_advance_fast_parallel.py \
        --year $YEAR --workers 1 --force --csv-only
    echo "[advance] ${YEAR}年 CSV生成完了"
  done
) >> logs/advance_regen_${LOG_DATE}.log 2>&1 &
ADVANCE_PID=$!

echo "  before PID: $BEFORE_PID  → logs/before_regen_${LOG_DATE}.log"
echo "  advance PID: $ADVANCE_PID → logs/advance_regen_${LOG_DATE}.log"
echo "  CSV生成完了まで待機中（約2〜3日）..."

wait $BEFORE_PID
echo "[OK] before CSV生成完了: $(date)"

wait $ADVANCE_PID
echo "[OK] advance CSV生成完了: $(date)"

# ================================================================
# Phase B-2: DB投入（シーケンシャル - DB競合回避）
# ================================================================

echo ""
echo "[Phase B-2] DB投入（シーケンシャル）..."

for YEAR in 2020 2021 2022 2023 2024 2025; do
    echo "[Phase B-2] before DB投入 ${YEAR}年..."
    python scripts/prediction/generate_before_fast_parallel.py \
        --year $YEAR --import-only
    echo "[Phase B-2] advance DB投入 ${YEAR}年..."
    python scripts/prediction/generate_advance_fast_parallel.py \
        --year $YEAR --import-only
done

echo ""
echo "================================================================"
echo "=== Phase B完了: $(date) ==="
echo "================================================================"

# ================================================================
# Phase C: バックテスト
# ================================================================

echo ""
echo "[Phase C] fast_backtest --full..."
python scripts/backtest/fast_backtest.py --full

echo ""
echo "================================================================"
echo "=== 全タスク完了: $(date) ==="
echo "================================================================"
