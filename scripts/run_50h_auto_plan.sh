#!/bin/bash
# ============================================================
# 50時間自動実行プラン
#
# Phase 1: actual_course修正（batch_data_loader.py適用済み）
#          → 2024-2025 before予測再生成（~20h）
#          → バックテスト（2024+2025）
#          → ROIゲート（前回比-5pt以下なら自動停止）
#
# Phase 2: wave_height改善（wave_height_adjuster.py適用済み）
#          → 2024-2025 before予測再生成（~20h）
#          → バックテスト（2024+2025）
#          → 結果ログ
#
# 実行方法:
#   bash scripts/run_50h_auto_plan.sh 2>&1 | tee logs/auto_plan_50h.log
# ============================================================

set -e
PROJ="c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032"
cd "$PROJ"

LOG="logs/auto_plan_50h.log"
RESULT_JSON="data/auto_plan_results.json"
WORKERS=2

# v2.40.0ベースライン（ROI 101.3%）
BASELINE_ROI_2024=95.0   # 2024年単体の許容下限（ベースライン-5pt目安）
BASELINE_ROI_2025=95.0   # 2025年単体の許容下限

mkdir -p logs data

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

# ============================================================
# バックテスト実行・ROI抽出ヘルパー
# ============================================================
run_backtest_year() {
    local year=$1
    local json_out="data/bt_result_${year}.json"
    python scripts/backtest/standard_backtest_unique.py \
        --year "$year" --save-json "$json_out"
    echo "$json_out"
}

extract_roi() {
    local json_file=$1
    # JSON から roi を抽出（例: {"roi": 123.4, ...}）
    python -c "
import json, sys
with open('$json_file') as f:
    d = json.load(f)
# total または summary キー対応
roi = d.get('roi') or d.get('summary', {}).get('roi') or d.get('total', {}).get('roi') or 0
print(f'{float(roi):.1f}')
" 2>/dev/null || echo "0.0"
}

# ============================================================
# Phase 1 開始
# ============================================================
log "=========================================="
log "Phase 1 開始: actual_course修正 + 再生成"
log "=========================================="

# Gitコミット（Phase1コード変更を記録）
log "Git state を保存..."
git add src/database/batch_data_loader.py
git add src/analysis/wave_height_adjuster.py
git add src/analysis/beforeinfo_scorer.py
git add config/weather_rules.json
git diff --cached --stat | tee -a "$LOG"
git commit -m "feat: actual_course + wave_height改善（50h自動プラン Phase1/2コード変更）

- batch_data_loader.py: COALESCE(rd.actual_course, e.pit_number) を3箇所適用
- wave_height_adjuster.py: W-1(5-9cm会場別), W-2(15cm+ -8.0pt), W-3(venue_code引数追加)
- beforeinfo_scorer.py: venue_code を wave_height_adjuster に渡すよう修正
- weather_rules.json: rough threshold 6cm → 5cm

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" 2>&1 | tee -a "$LOG" || log "コミット済みまたはスキップ"

# Phase 1: 2024-2025年 before予測再生成
for year in 2024 2025; do
    log "--- Phase1: ${year}年 before予測再生成 開始 ---"
    python scripts/prediction/generate_before_fast_parallel.py \
        --year "$year" --workers "$WORKERS" --force 2>&1 | tee -a "$LOG"
    if [ ${PIPESTATUS[0]} -ne 0 ]; then
        log "ERROR: ${year}年再生成失敗。スクリプト停止。"
        exit 1
    fi
    log "--- Phase1: ${year}年 完了 ---"
done

# Phase 1: バックテスト
log "--- Phase1: バックテスト開始 ---"
PHASE1_ROI_2024=0
PHASE1_ROI_2025=0

for year in 2024 2025; do
    log "バックテスト ${year}年..."
    json_file=$(run_backtest_year "$year")
    roi=$(extract_roi "$json_file")
    log "  ${year}年 ROI: ${roi}%"
    if [ "$year" = "2024" ]; then
        PHASE1_ROI_2024=$roi
    else
        PHASE1_ROI_2025=$roi
    fi
done

log "Phase1 結果: 2024=${PHASE1_ROI_2024}%, 2025=${PHASE1_ROI_2025}%"

# ROIゲート判定
GATE_FAIL=0
python -c "
a=$PHASE1_ROI_2024; b=$PHASE1_ROI_2025; la=$BASELINE_ROI_2024; lb=$BASELINE_ROI_2025
if a < la or b < lb:
    print('FAIL')
else:
    print('PASS')
" 2>/dev/null | grep -q FAIL && GATE_FAIL=1

if [ $GATE_FAIL -eq 1 ]; then
    log "=========================================="
    log "ROIゲート 不合格: Phase1の結果がベースラインを5pt以上下回りました"
    log "  2024: ${PHASE1_ROI_2024}% (下限 ${BASELINE_ROI_2024}%)"
    log "  2025: ${PHASE1_ROI_2025}% (下限 ${BASELINE_ROI_2025}%)"
    log "Phase2 はスキップします。手動で確認してください。"
    log "=========================================="
    # JSON記録
    python -c "
import json
result = {
    'phase1': {'roi_2024': $PHASE1_ROI_2024, 'roi_2025': $PHASE1_ROI_2025},
    'gate': 'FAIL',
    'phase2': None
}
with open('$RESULT_JSON', 'w') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
"
    exit 0
fi

log "ROIゲート 合格: Phase2に進みます"

# ============================================================
# Phase 2 開始
# ============================================================
log "=========================================="
log "Phase 2 開始: wave_height改善 + 再生成"
log "=========================================="

# Phase 2: 2024-2025年 before予測再生成（wave_height変更反映）
for year in 2024 2025; do
    log "--- Phase2: ${year}年 before予測再生成 開始 ---"
    python scripts/prediction/generate_before_fast_parallel.py \
        --year "$year" --workers "$WORKERS" --force 2>&1 | tee -a "$LOG"
    if [ ${PIPESTATUS[0]} -ne 0 ]; then
        log "ERROR: ${year}年再生成失敗。スクリプト停止。"
        exit 1
    fi
    log "--- Phase2: ${year}年 完了 ---"
done

# Phase 2: バックテスト
log "--- Phase2: バックテスト開始 ---"
PHASE2_ROI_2024=0
PHASE2_ROI_2025=0

for year in 2024 2025; do
    log "バックテスト ${year}年..."
    json_file=$(run_backtest_year "$year")
    roi=$(extract_roi "$json_file")
    log "  ${year}年 ROI: ${roi}%"
    if [ "$year" = "2024" ]; then
        PHASE2_ROI_2024=$roi
    else
        PHASE2_ROI_2025=$roi
    fi
done

log "Phase2 結果: 2024=${PHASE2_ROI_2024}%, 2025=${PHASE2_ROI_2025}%"

# ============================================================
# 最終サマリー
# ============================================================
log "=========================================="
log "50時間自動プラン 完了サマリー"
log "=========================================="
log "Phase1 (actual_course): 2024=${PHASE1_ROI_2024}%, 2025=${PHASE1_ROI_2025}%"
log "Phase2 (wave_height):   2024=${PHASE2_ROI_2024}%, 2025=${PHASE2_ROI_2025}%"
log "=========================================="

# JSON記録
python -c "
import json
result = {
    'phase1': {'roi_2024': $PHASE1_ROI_2024, 'roi_2025': $PHASE1_ROI_2025},
    'gate': 'PASS',
    'phase2': {'roi_2024': $PHASE2_ROI_2024, 'roi_2025': $PHASE2_ROI_2025}
}
with open('$RESULT_JSON', 'w') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print('結果を $RESULT_JSON に保存しました')
" 2>&1 | tee -a "$LOG"

log "完了: $(date)"
