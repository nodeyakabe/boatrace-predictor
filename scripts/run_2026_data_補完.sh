#!/bin/bash
# 2026年データ補完スクリプト
# 2026-03-23 作成
#
# 前提:
#   - DB復元完了済み（boatrace_backup_pairwise_test.db → boatrace.db）
#   - Phase A完了済み（beforeinfo 01-03/18・odds 01-03/18・統計指標）
#   - entries/results CSV: 1月・2月は存在（未投入）、3月は未収集
#   - odds: 03-19〜03-22分が不足
#
# 実行方法:
#   cd c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032
#   bash scripts/run_2026_data_補完.sh

set -e
cd "$(dirname "$0")/.."

LOG="logs/data_補完_2026_$(date +%Y%m%d_%H%M%S).log"
mkdir -p logs
exec > >(tee -a "$LOG") 2>&1

echo "================================================================"
echo "=== 2026年データ補完開始: $(date) ==="
echo "================================================================"

# ================================================================
# STEP 1: 2026年3月分 entries/results CSV収集
# ================================================================

echo ""
echo "[STEP 1] 2026-03 entries/results CSV収集..."
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
    --start 2026-03-01 --end 2026-03-22 \
    --output data/csv/2026_03_補完 --workers 8
echo "[OK] 2026-03 CSV収集完了"

# ================================================================
# STEP 2: entries/results DB投入（1月・2月・3月）
# ================================================================

echo ""
echo "[STEP 2-1] 2026-01 DB投入..."
python scripts/data_collection/import_races_csv.py --dir data/csv/2026_01_補完
echo "[OK] 2026-01 完了"

echo ""
echo "[STEP 2-2] 2026-02 DB投入..."
python scripts/data_collection/import_races_csv.py --dir data/csv/2026_02_補完
echo "[OK] 2026-02 完了"

echo ""
echo "[STEP 2-3] 2026-03 DB投入..."
python scripts/data_collection/import_races_csv.py --dir data/csv/2026_03_補完
echo "[OK] 2026-03 完了"

# ================================================================
# STEP 3: 後続処理（entries/results追加後の必須チェーン）
# ================================================================

echo ""
echo "[STEP 3-1] kimarite補完..."
python scripts/data_collection/補完_決まり手データ_改善版.py \
    --start-date 2026-01-01 --end-date 2026-03-22
echo "[OK] kimarite補完完了"

echo ""
echo "[STEP 3-2] race_details補完..."
python scripts/data_collection/補完_レース詳細データ_改善版v4.py \
    --start-date 2026-01-01 --end-date 2026-03-22
echo "[OK] race_details補完完了"

echo ""
echo "[STEP 3-3] trifecta_odds補完（2026-03-19〜03-22）..."
# fetch_odds_parallel_safe.py はDB直接保存（CSV経由ではない）
python scripts/data_collection/fetch_odds_parallel_safe.py \
    --start-date 2026-03-19 --end-date 2026-03-22 --workers 8
echo "[OK] odds補完完了"

echo ""
echo "[STEP 3-4] 統計指標再生成（2026年全体）..."
python scripts/data_collection/build_indicator_stats.py \
    --start 2026-01-01 --end 2026-03-22
echo "[OK] 統計指標再生成完了"

# ================================================================
# STEP 4: beforeinfo補完（03-19〜03-22分）
# ================================================================

echo ""
echo "[STEP 4] beforeinfo補完（2026-03-19〜03-22）..."
# stdin を /dev/null にリダイレクトして対話プロンプト (y/N) を回避
python scripts/data_collection/collect_beforeinfo_to_csv_parallel.py \
    --start 2026-03-19 --end 2026-03-22 \
    --output data/csv/beforeinfo/2026_03_post --workers 8 < /dev/null
python scripts/data_collection/import_beforeinfo_csv_to_db.py \
    --input data/csv/beforeinfo/2026_03_post
echo "[OK] beforeinfo補完完了"

echo ""
echo "================================================================"
echo "=== 全タスク完了: $(date) ==="
echo "================================================================"
echo ""
echo "次のアクション（手動）:"
echo "  - before予測再生成（2026年・任意）:"
echo "    python scripts/prediction/fast_prediction_generator.py --date 2026-03-23 --type before"
