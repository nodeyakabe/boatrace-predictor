#!/bin/bash
# 長期放置タスク一括実行スクリプト
# 2026-03-19 作成
# 実行順: 2026年補完 → before/advance全年度再生成（並列）→ バックテスト

set -e
cd "$(dirname "$0")/.."

LOG="logs/longrun_$(date +%Y%m%d_%H%M%S).log"
mkdir -p logs

exec > >(tee -a "$LOG") 2>&1

echo "================================================================"
echo "=== 長期タスク開始: $(date) ==="
echo "================================================================"

# ================================================================
# Phase A: 2026年データ補完
# ================================================================

echo ""
echo "[Phase A-1] 2026-02 beforeinfo収集..."
python scripts/data_collection/collect_beforeinfo_to_csv_parallel.py \
    --start 2026-02-01 --end 2026-02-28 \
    --output data/csv/beforeinfo/2026_02 --workers 12
echo "[OK] 2026-02 beforeinfo収集完了"

echo ""
echo "[Phase A-2] 2026-03 beforeinfo収集..."
python scripts/data_collection/collect_beforeinfo_to_csv_parallel.py \
    --start 2026-03-01 --end 2026-03-18 \
    --output data/csv/beforeinfo/2026_03 --workers 12
echo "[OK] 2026-03 beforeinfo収集完了"

echo ""
echo "[Phase A-3] beforeinfo DB投入 (2026-01)..."
python scripts/data_collection/import_beforeinfo_csv_to_db.py \
    --input data/csv/beforeinfo/2026_01
echo "[OK] 2026-01 beforeinfo投入完了"

echo ""
echo "[Phase A-4] beforeinfo DB投入 (2026-02)..."
python scripts/data_collection/import_beforeinfo_csv_to_db.py \
    --input data/csv/beforeinfo/2026_02
echo "[OK] 2026-02 beforeinfo投入完了"

echo ""
echo "[Phase A-5] beforeinfo DB投入 (2026-03)..."
python scripts/data_collection/import_beforeinfo_csv_to_db.py \
    --input data/csv/beforeinfo/2026_03
echo "[OK] 2026-03 beforeinfo投入完了"

echo ""
echo "[Phase A-6] odds収集 2026-01〜03-18 (直接DB)..."
python scripts/data_collection/fetch_odds_parallel_safe.py \
    --start-date 2026-01-01 --end-date 2026-03-18 --workers 8
echo "[OK] odds収集完了"

echo ""
echo "[Phase A-7] 統計指標再生成 (2026年)..."
python scripts/data_collection/build_indicator_stats.py \
    --start 2026-01-01 --end 2026-03-18
echo "[OK] 統計指標再生成完了"

echo ""
echo "================================================================"
echo "=== Phase A完了: $(date) ==="
echo "================================================================"

# ================================================================
# Phase B + C: 別スクリプトに委譲（DB競合回避のため分離）
# ================================================================

echo ""
echo "[Phase B+C] run_phase_b_c.sh を起動..."
bash scripts/run_phase_b_c.sh
