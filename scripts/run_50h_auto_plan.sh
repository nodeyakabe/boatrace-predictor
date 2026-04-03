#!/bin/bash
# ============================================================
# 50時間自動実行プラン v4（再起動耐性版）
#
# Phase 1: actual_course修正のみ反映（wave_heightを一時旧版に戻す）
#          → 2024-2025 before予測再生成（~20h）
#          → バックテスト（2024+2025）
#          → ROIゲート（下限未満なら自動停止）
#
# Phase 2: wave_height改善を追加（git show HEAD で正確に現行版に戻す）
#          → 2024-2025 before予測再生成（~20h）
#          → バックテスト（2024+2025）
#          → 詳細ログ・JSON保存
#
# 再起動耐性:
#   - STATE_FILE に完了済み Phase を記録 → 再起動後に完了済みをスキップ
#   - Phase2復元は git show HEAD:file を使用（バックアップ破損に依存しない）
#   - 起動時に wave_height ファイルが旧版のまま残っていたら自動復元
#
# 実行方法:
#   bash scripts/run_50h_auto_plan.sh
#   ※ ログは logs/auto_plan_50h.log に自動書き込み（外部 tee 不要）
#   ※ 中断後の再開: そのまま再実行すれば完了済み Phase をスキップ
# ============================================================

set -eo pipefail

PROJ="c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032"
cd "$PROJ"

LOG="logs/auto_plan_50h.log"
WORKERS=2

# v2.40.0 ベースラインROI下限（この値を下回ったらPhase2スキップ）
# 2024ベースライン~100%（収支-520円）→ 下限90%（10pt余裕）
# 2025ベースライン~120% → 下限95%
BASELINE_ROI_2024=90.0
BASELINE_ROI_2025=95.0

# Phase1用: wave_height変更前のコミット（64c4298 = docsのみ変更）
PRE_WAVE_COMMIT="64c4298"

# wave_heightに関係する3ファイル
WAVE_FILES=(
    "src/analysis/wave_height_adjuster.py"
    "src/analysis/beforeinfo_scorer.py"
    "config/weather_rules.json"
)

# 進捗管理（再起動時のスキップ用）
STATE_FILE="data/_auto_plan_state.txt"
WAVE_FILES_SWAPPED=0

mkdir -p logs data

# ============================================================
# ユーティリティ
# ============================================================
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

elapsed_str() {
    local secs=$1
    printf "%dh %02dm %02ds" $((secs/3600)) $(( (secs%3600)/60 )) $((secs%60))
}

save_state() {
    echo "$1" > "$STATE_FILE"
    log "  [状態] $1 を保存"
}

load_state() {
    cat "$STATE_FILE" 2>/dev/null || echo "START"
}

# バックテストJSONから指標を取得
extract_metric() {
    local json_file=$1
    local key=$2
    python - <<EOF 2>/dev/null || echo "0"
import json
with open(r'$json_file', encoding='utf-8') as f:
    d = json.load(f)
v = d.get('total', {}).get('$key')
print(0 if v is None else v)
EOF
}

# バックテスト結果を1行ログ出力し、ROIをstdoutに返す
# >&2 で stderr に向けて stdout 汚染防止（roi=$(...) が ROI値のみキャプチャ）
log_backtest_detail() {
    local phase_label=$1 year=$2 json_file=$3
    local roi profit bets hits hit_rate
    roi=$(extract_metric "$json_file" roi)
    profit=$(extract_metric "$json_file" profit)
    bets=$(extract_metric "$json_file" bets)
    hits=$(extract_metric "$json_file" hits)
    hit_rate=$(extract_metric "$json_file" hit_rate)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')]   [${phase_label}/${year}年] ROI=${roi}% | 収支=${profit}円 | 件数=${bets} | 的中=${hits}(${hit_rate}%)" | tee -a "$LOG" >&2
    echo "$roi"
}

# wave_height ファイルをHEADの現行版に復元（git objectsを直接参照 → バックアップ破損の影響なし）
restore_wave_files_from_head() {
    log "  wave_heightファイルをHEAD(${PRE_WAVE_COMMIT}以降)から復元..."
    git show "HEAD:src/analysis/wave_height_adjuster.py" > src/analysis/wave_height_adjuster.py
    git show "HEAD:src/analysis/beforeinfo_scorer.py"    > src/analysis/beforeinfo_scorer.py
    git show "HEAD:config/weather_rules.json"            > config/weather_rules.json
    WAVE_FILES_SWAPPED=0
    grep -m1 "rough.*min" config/weather_rules.json | tee -a "$LOG" || true
}

# ============================================================
# クリーンアップ: 異常終了時にwave_heightファイルをHEADから復元
# ============================================================
cleanup() {
    local exit_code=$?
    if [ $WAVE_FILES_SWAPPED -eq 1 ]; then
        log "[cleanup] wave_heightファイルをHEADから自動復元..."
        git show "HEAD:src/analysis/wave_height_adjuster.py" > src/analysis/wave_height_adjuster.py 2>/dev/null || true
        git show "HEAD:src/analysis/beforeinfo_scorer.py"    > src/analysis/beforeinfo_scorer.py    2>/dev/null || true
        git show "HEAD:config/weather_rules.json"            > config/weather_rules.json            2>/dev/null || true
        WAVE_FILES_SWAPPED=0
        log "[cleanup] 復元完了"
    fi
    if [ $exit_code -ne 0 ]; then
        log "[ERROR] スクリプトがエラーで終了しました (exit_code=$exit_code)"
    fi
}
trap cleanup EXIT

# ============================================================
# 開始ログ・事前チェック
# ============================================================
SCRIPT_START=$(date +%s)
log "=========================================="
log "50時間自動実行プラン 開始 (v4 再起動耐性版)"
log "  日時      : $(date)"
log "  Python    : $(python --version 2>&1)"
log "  Git branch: $(git branch --show-current 2>/dev/null || echo unknown)"
log "  Git HEAD  : $(git rev-parse --short HEAD 2>/dev/null)"
log "  Workers   : $WORKERS"
log "  ROI下限   : 2024=${BASELINE_ROI_2024}%, 2025=${BASELINE_ROI_2025}%"
log "  STATE_FILE: $STATE_FILE"
log "=========================================="

# ディスク空き容量チェック
FREE_GB=$(python -c "import shutil; s=shutil.disk_usage('.'); print(f'{s.free/1024**3:.1f}')" 2>/dev/null || echo "0")
log "ディスク空き: ${FREE_GB}GB"
python -c "
f=float('$FREE_GB')
if f < 5.0:
    print('  WARNING: 5GB未満。再生成中にディスクフルになる可能性があります')
" 2>/dev/null | tee -a "$LOG" || true

# 前提ファイル確認
for f in src/database/batch_data_loader.py "${WAVE_FILES[@]}"; do
    [ -f "$f" ] || { log "ERROR: ファイルが見つかりません: $f"; exit 1; }
done

# ── 再起動対策: wave_height ファイルが旧版のまま残っていたら自動復元 ──
HEAD_ROUGH=$(git show "HEAD:config/weather_rules.json" 2>/dev/null | grep -m1 '"rough"' | grep -o '"min": [0-9]*' | grep -o '[0-9]*' || echo "0")
CUR_ROUGH=$(grep -m1 '"rough"' config/weather_rules.json | grep -o '"min": [0-9]*' | grep -o '[0-9]*' || echo "0")
if [ "$CUR_ROUGH" != "$HEAD_ROUGH" ]; then
    log "⚠ wave_heightファイルが旧版のまま残っています（前回の異常終了の可能性）"
    log "  HEAD (期待値) rough.min=${HEAD_ROUGH}  現在値=${CUR_ROUGH}"
    restore_wave_files_from_head
    log "  自動復元完了"
fi

# 前回の状態を確認
CURRENT_STATE=$(load_state)
log "前回の状態: ${CURRENT_STATE}"

# ============================================================
# Phase 1
# ============================================================
if [ "$CURRENT_STATE" = "PHASE1_DONE" ] || [ "$CURRENT_STATE" = "PHASE2_DONE" ]; then
    log ""
    log "--- Phase1: 完了済みのためスキップ（$STATE_FILE を参照） ---"
    PHASE1_ROI_2024=$(extract_metric "data/bt_result_phase1_2024.json" roi)
    PHASE1_ROI_2025=$(extract_metric "data/bt_result_phase1_2025.json" roi)
    log "  Phase1 ROI（保存済み）: 2024=${PHASE1_ROI_2024}%, 2025=${PHASE1_ROI_2025}%"
    PHASE1_START=$SCRIPT_START
    PHASE1_END=$SCRIPT_START
else
    log ""
    log "=========================================="
    log "Phase 1 開始: actual_course修正のみ測定"
    log "  （wave_heightは ${PRE_WAVE_COMMIT} の旧版を一時使用）"
    log "=========================================="
    PHASE1_START=$(date +%s)

    # wave_height ファイルを旧版に差し替え
    log "wave_heightファイルを旧版(${PRE_WAVE_COMMIT})に差し替え..."
    git show "${PRE_WAVE_COMMIT}:src/analysis/wave_height_adjuster.py" > src/analysis/wave_height_adjuster.py
    git show "${PRE_WAVE_COMMIT}:src/analysis/beforeinfo_scorer.py"    > src/analysis/beforeinfo_scorer.py
    git show "${PRE_WAVE_COMMIT}:config/weather_rules.json"            > config/weather_rules.json
    WAVE_FILES_SWAPPED=1
    grep -m1 "rough.*min" config/weather_rules.json | tee -a "$LOG" || true

    # Phase1 before予測再生成
    for year in 2024 2025; do
        log ""
        log "--- Phase1: ${year}年 before予測再生成 開始 ($(date)) ---"
        REGEN_START=$(date +%s)
        python scripts/prediction/generate_before_fast_parallel.py \
            --year "$year" --workers "$WORKERS" --force 2>&1 | tee -a "$LOG"
        REGEN_END=$(date +%s)
        log "--- Phase1: ${year}年 完了 ($(elapsed_str $((REGEN_END - REGEN_START)))) ---"
    done

    # Phase1 バックテスト
    log ""
    log "--- Phase1: バックテスト開始 ($(date)) ---"
    BT1_START=$(date +%s)
    PHASE1_ROI_2024=0
    PHASE1_ROI_2025=0

    for year in 2024 2025; do
        json_file="data/bt_result_phase1_${year}.json"
        python scripts/backtest/standard_backtest_unique.py \
            --year "$year" --save-json "$json_file" 2>&1 | tee -a "$LOG"
        roi=$(log_backtest_detail "Phase1" "$year" "$json_file")
        if [ "$year" = "2024" ]; then PHASE1_ROI_2024=$roi; else PHASE1_ROI_2025=$roi; fi
    done
    BT1_END=$(date +%s)
    log "--- Phase1バックテスト完了 ($(elapsed_str $((BT1_END - BT1_START)))) ---"

    # wave_height を HEAD の現行版に戻す（git show HEAD = 常に正確）
    log ""
    log "wave_heightファイルをHEAD現行版に復元..."
    restore_wave_files_from_head

    PHASE1_END=$(date +%s)
    log ""
    log "--- Phase1 完了サマリー ($(elapsed_str $((PHASE1_END - PHASE1_START)))) ---"
    log "  2024: ROI=${PHASE1_ROI_2024}%  (下限 ${BASELINE_ROI_2024}%)"
    log "  2025: ROI=${PHASE1_ROI_2025}%  (下限 ${BASELINE_ROI_2025}%)"

    save_state "PHASE1_DONE"
fi

# ============================================================
# ROI ゲート判定
# ============================================================
log ""
GATE_RESULT=$(python - <<EOF 2>/dev/null || echo "FAIL"
a = float($PHASE1_ROI_2024)
b = float($PHASE1_ROI_2025)
la = float($BASELINE_ROI_2024)
lb = float($BASELINE_ROI_2025)
print('FAIL' if a < la or b < lb else 'PASS')
EOF
)

log "ROIゲート判定: ${GATE_RESULT}"

if [ "$GATE_RESULT" = "FAIL" ]; then
    log "=========================================="
    log "ROIゲート 不合格: Phase2をスキップします"
    log "  2024: ${PHASE1_ROI_2024}%  (下限 ${BASELINE_ROI_2024}%)"
    log "  2025: ${PHASE1_ROI_2025}%  (下限 ${BASELINE_ROI_2025}%)"
    log "  ▶ actual_course修正がマイナス効果の可能性。手動確認してください。"
    log "=========================================="
    python - <<EOF 2>&1 | tee -a "$LOG"
import json
result = {
    'status': 'gate_fail',
    'completed_at': '$(date)',
    'config': {'workers': $WORKERS, 'pre_wave_commit': '$PRE_WAVE_COMMIT',
               'baseline_roi_2024': $BASELINE_ROI_2024, 'baseline_roi_2025': $BASELINE_ROI_2025},
    'phase1': {'label': 'actual_course修正のみ',
               'roi_2024': $PHASE1_ROI_2024, 'roi_2025': $PHASE1_ROI_2025},
    'gate': 'FAIL', 'phase2': None,
}
with open('data/auto_plan_results.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print('結果を data/auto_plan_results.json に保存しました')
EOF
    save_state "GATE_FAIL"
    exit 0
fi

log "ROIゲート 合格: Phase2に進みます"

# ============================================================
# Phase 2
# ============================================================
if [ "$CURRENT_STATE" = "PHASE2_DONE" ]; then
    log "--- Phase2: 完了済みのためスキップ ---"
    PHASE2_ROI_2024=$(extract_metric "data/bt_result_phase2_2024.json" roi)
    PHASE2_ROI_2025=$(extract_metric "data/bt_result_phase2_2025.json" roi)
    PHASE2_START=$SCRIPT_START
    PHASE2_END=$SCRIPT_START
else
    log ""
    log "=========================================="
    log "Phase 2 開始: actual_course + wave_height 改善"
    log "=========================================="
    PHASE2_START=$(date +%s)

    # Phase2 before予測再生成
    for year in 2024 2025; do
        log ""
        log "--- Phase2: ${year}年 before予測再生成 開始 ($(date)) ---"
        REGEN_START=$(date +%s)
        python scripts/prediction/generate_before_fast_parallel.py \
            --year "$year" --workers "$WORKERS" --force 2>&1 | tee -a "$LOG"
        REGEN_END=$(date +%s)
        log "--- Phase2: ${year}年 完了 ($(elapsed_str $((REGEN_END - REGEN_START)))) ---"
    done

    # Phase2 バックテスト
    log ""
    log "--- Phase2: バックテスト開始 ($(date)) ---"
    BT2_START=$(date +%s)
    PHASE2_ROI_2024=0
    PHASE2_ROI_2025=0

    for year in 2024 2025; do
        json_file="data/bt_result_phase2_${year}.json"
        python scripts/backtest/standard_backtest_unique.py \
            --year "$year" --save-json "$json_file" 2>&1 | tee -a "$LOG"
        roi=$(log_backtest_detail "Phase2" "$year" "$json_file")
        if [ "$year" = "2024" ]; then PHASE2_ROI_2024=$roi; else PHASE2_ROI_2025=$roi; fi
    done
    BT2_END=$(date +%s)
    log "--- Phase2バックテスト完了 ($(elapsed_str $((BT2_END - BT2_START)))) ---"

    PHASE2_END=$(date +%s)
    save_state "PHASE2_DONE"
fi

SCRIPT_END=$(date +%s)

# ============================================================
# 最終サマリー
# ============================================================
WAVE_DELTA_2024=$(python -c "print(f'{$PHASE2_ROI_2024 - $PHASE1_ROI_2024:+.1f}')" 2>/dev/null || echo "?")
WAVE_DELTA_2025=$(python -c "print(f'{$PHASE2_ROI_2025 - $PHASE1_ROI_2025:+.1f}')" 2>/dev/null || echo "?")

log ""
log "=========================================="
log "50時間自動プラン 完了"
log "  完了日時  : $(date)"
log "  総所要時間: $(elapsed_str $((SCRIPT_END - SCRIPT_START)))"
log ""
log "  Phase1 actual_course修正のみ"
log "    2024: ROI=${PHASE1_ROI_2024}%"
log "    2025: ROI=${PHASE1_ROI_2025}%"
log ""
log "  Phase2 actual_course + wave_height改善"
log "    2024: ROI=${PHASE2_ROI_2024}%"
log "    2025: ROI=${PHASE2_ROI_2025}%"
log ""
log "  ▶ wave_height限界効果 (Phase2 - Phase1)"
log "    2024: ${WAVE_DELTA_2024}pt"
log "    2025: ${WAVE_DELTA_2025}pt"
log ""
log "  詳細JSON   : data/auto_plan_results.json"
log "  バックテスト: data/bt_result_phase{1,2}_{2024,2025}.json"
log "  全ログ     : ${LOG}"
log "=========================================="

# 詳細JSON保存（条件別成績含む）
python - <<EOF 2>&1 | tee -a "$LOG"
import json, os

def load_bt(phase, year):
    path = f'data/bt_result_{phase}_{year}.json'
    if not os.path.exists(path):
        return {'error': f'{path} not found'}
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    return {'total': d.get('total', {}), 'conditions': d.get('conditions', [])}

def safe_delta(ph2_yr, ph1_yr):
    try:
        r2 = load_bt('phase2', ph2_yr).get('total', {}).get('roi') or 0
        r1 = load_bt('phase1', ph1_yr).get('total', {}).get('roi') or 0
        return round(float(r2) - float(r1), 1)
    except Exception:
        return None

result = {
    'status': 'completed',
    'completed_at': '$(date)',
    'elapsed_total': '$(elapsed_str $((SCRIPT_END - SCRIPT_START)))',
    'config': {
        'workers': $WORKERS,
        'pre_wave_commit': '$PRE_WAVE_COMMIT',
        'git_head': '$(git rev-parse HEAD 2>/dev/null || echo unknown)',
        'baseline_roi_2024': $BASELINE_ROI_2024,
        'baseline_roi_2025': $BASELINE_ROI_2025,
    },
    'phase1': {
        'label': 'actual_course修正のみ（wave_heightは旧版）',
        '2024': load_bt('phase1', '2024'),
        '2025': load_bt('phase1', '2025'),
    },
    'gate': 'PASS',
    'phase2': {
        'label': 'actual_course + wave_height改善（現行版）',
        '2024': load_bt('phase2', '2024'),
        '2025': load_bt('phase2', '2025'),
        'wave_delta_2024': safe_delta('2024', '2024'),
        'wave_delta_2025': safe_delta('2025', '2025'),
    },
}
with open('data/auto_plan_results.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print('  結果を data/auto_plan_results.json に保存しました')
EOF

log "完了"
