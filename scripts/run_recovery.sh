#!/bin/bash
# リカバリスクリプト: advance 2023-2025 再生成 + 全年度DB投入 + バックテスト
# 2026-03-22 作成（run_phase_b_c.sh が advance 2023 PermissionError でクラッシュした後の継続）
#
# 実行前の状態:
#   before CSV:  2020-2025 全完了（新コード・pairwise=True）
#   advance CSV: 2020-2022 完了 / 2023 90/365日（新コード） / 2024-2025 旧ファイル残存
#   DB投入: 未実行 / fast_backtest: 未実行

set -e
cd "$(dirname "$0")/.."

LOG="logs/recovery_$(date +%Y%m%d_%H%M%S).log"
mkdir -p logs
exec > >(tee -a "$LOG") 2>&1

echo "================================================================"
echo "=== リカバリ開始: $(date) ==="
echo "================================================================"

# ================================================================
# Phase B-1: advance CSV再生成（2023残り + 2024 + 2025）
# ================================================================

echo ""
echo "[Phase B-1a] advance 2023年 残り生成（--csv-only、--forceなし → 既存90日スキップ）..."
python scripts/prediction/generate_advance_fast_parallel.py \
    --year 2023 --workers 1 --csv-only
echo "[OK] advance 2023年 CSV完了"

echo ""
echo "[Phase B-1b] advance 2024年 生成（--force で旧ファイル上書き）..."
python scripts/prediction/generate_advance_fast_parallel.py \
    --year 2024 --workers 1 --force --csv-only
echo "[OK] advance 2024年 CSV完了"

echo ""
echo "[Phase B-1c] advance 2025年 生成（--force で旧ファイル上書き）..."
python scripts/prediction/generate_advance_fast_parallel.py \
    --year 2025 --workers 1 --force --csv-only
echo "[OK] advance 2025年 CSV完了"

echo ""
echo "================================================================"
echo "=== Phase B-1完了: $(date) ==="
echo "================================================================"

# ================================================================
# Phase B-2: DB投入（before + advance 全年度・シーケンシャル）
# ================================================================

echo ""
echo "[Phase B-2] DB投入 開始..."

for YEAR in 2020 2021 2022 2023 2024 2025; do
    echo ""
    echo "[Phase B-2] before ${YEAR}年 DB投入..."
    python scripts/prediction/generate_before_fast_parallel.py \
        --year $YEAR --import-only
    echo "[OK] before ${YEAR}年 完了"

    echo "[Phase B-2] advance ${YEAR}年 DB投入..."
    python scripts/prediction/generate_advance_fast_parallel.py \
        --year $YEAR --import-only
    echo "[OK] advance ${YEAR}年 完了"
done

echo ""
echo "================================================================"
echo "=== Phase B-2完了: $(date) ==="
echo "================================================================"

# ================================================================
# Phase C: import_features + fast_backtest
# ================================================================

echo ""
echo "[Phase C-1] prediction_features 更新..."
python scripts/prediction/import_features_from_predictions.py --full --force
echo "[OK] prediction_features 更新完了"

echo ""
echo "[Phase C-2] fast_backtest --full..."
python scripts/backtest/fast_backtest.py --full

echo ""
echo "================================================================"
echo "=== 全タスク完了: $(date) ==="
echo "================================================================"
