#!/bin/bash
# 2026年データ補完 + 予測再生成スクリプト（1〜3月）
# 月別分割・途中停止後は再実行で再開可能（各月のCSVが存在すればfetch_to_csvをスキップ）
#
# 実行順序:
#   Step 1a  : 1月 entries/results 収集 → DB投入
#   Step 1b  : 2月 entries/results 収集 → DB投入
#   Step 1c  : 3月 entries/results 収集 → DB投入
#   Step 1.5 : kimarite 補完
#   Step 1.6 : race_details 補完
#   Step 1.7 : trifecta_odds 収集
#   Step 2   : exhibition_data 収集 → DB投入
#   Step 2.5 : 統計指標再生成
#   Step 3   : advance 予測再生成
#   Step 4   : before 予測再生成

set -e

cd "$(dirname "$0")/.."

echo "=============================="
echo "2026年データ補完 + 予測再生成"
echo "=============================="

# ===== 月別fetch+import関数 =====
fetch_and_import_month() {
    local label=$1
    local start=$2
    local end=$3
    local output=$4

    echo ""
    echo "[${label}] entries/results CSV収集 (${start} 〜 ${end}) ※brute-force"

    if [ -f "${output}/races.csv" ]; then
        echo "[${label}] スキップ: ${output}/races.csv が既に存在します"
    else
        python scripts/data_collection/fetch_to_csv_parallel_improved.py \
            --start ${start} --end ${end} \
            --output ${output} \
            --workers 2 \
            --brute-force
    fi

    echo "[${label}] DB投入"
    python scripts/data_collection/import_races_csv.py \
        --dir ${output}

    echo "[${label}] 完了"
}

# ===== Step 1a: 1月 =====
fetch_and_import_month "Step 1a: 1月" "2026-01-01" "2026-01-31" "data/csv/2026_01_bf"

# ===== Step 1b: 2月 =====
fetch_and_import_month "Step 1b: 2月" "2026-02-01" "2026-02-28" "data/csv/2026_02_bf"

# ===== Step 1c: 3月 =====
fetch_and_import_month "Step 1c: 3月" "2026-03-01" "2026-03-31" "data/csv/2026_03_bf"

# ===== Step 1.5: kimarite補完 =====
echo ""
echo "[Step 1.5] kimarite補完"
python scripts/data_collection/補完_決まり手データ_改善版.py
echo "[Step 1.5] 完了"

# ===== Step 1.6: race_details補完 =====
echo ""
echo "[Step 1.6] race_details補完"
python scripts/data_collection/補完_レース詳細データ_改善版v4.py
echo "[Step 1.6] 完了"

# ===== Step 1.7: trifecta_odds収集 =====
echo ""
echo "[Step 1.7] trifecta_odds収集 (2026-01-01 〜 2026-03-31)"
python scripts/data_collection/fetch_odds_parallel_safe.py \
    --start-date 2026-01-01 --end-date 2026-03-31 \
    --workers 2
echo "[Step 1.7] 完了"

# ===== Step 2: exhibition_data補完 =====
echo ""
echo "[Step 2] exhibition_data CSV収集 (2026-01-01 〜 2026-03-31)"
echo y | python scripts/data_collection/collect_beforeinfo_to_csv_parallel.py \
    --start 2026-01-01 --end 2026-03-31 \
    --output data/csv/beforeinfo/2026_補完 \
    --workers 2

echo "[Step 2] DB投入"
python scripts/data_collection/import_beforeinfo_csv_to_db.py \
    --input data/csv/beforeinfo/2026_補完
echo "[Step 2] 完了"

# ===== Step 2.5: 統計指標再生成 =====
echo ""
echo "[Step 2.5] 統計指標再生成（全期間累積）"
python scripts/data_collection/build_indicator_stats.py
echo "[Step 2.5] 完了"

# ===== Step 3: advance予測再生成 =====
echo ""
echo "[Step 3] advance予測再生成 (2026年)"
python scripts/prediction/generate_advance_fast.py --year 2026
echo "[Step 3] 完了"

# ===== Step 4: before予測再生成 =====
echo ""
echo "[Step 4] before予測再生成 (2026年)"
python scripts/prediction/generate_before_fast.py --year 2026
echo "[Step 4] 完了"

echo ""
echo "=============================="
echo "2026年データ補完 + 予測再生成 全ステップ完了"
echo "=============================="
