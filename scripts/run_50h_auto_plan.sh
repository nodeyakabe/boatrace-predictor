#!/bin/bash
# ============================================================
# 50時間自動実行プラン v3
#
# Phase 1: actual_course修正のみ反映（wave_highを一時旧版に戻す）
#          → 2024-2025 before予測再生成（~20h）
#          → バックテスト（2024+2025）
#          → ROIゲート（2024/2025どちらかが下限未満なら自動停止）
#
# Phase 2: wave_height改善を追加（旧版を現行版に戻す）
#          → 2024-2025 before予測再生成（~20h）
#          → バックテスト（2024+2025）
#          → 詳細ログ・JSON保存
#
# 前提:
#   以下4ファイルがコミット済みであること（git log で 3e00ff6 以降）
#   - src/database/batch_data_loader.py    ← actual_course修正
#   - src/analysis/wave_height_adjuster.py ← wave_height改善 (Phase2)
#   - src/analysis/beforeinfo_scorer.py    ← venue_code対応 (Phase2)
#   - config/weather_rules.json            ← rough threshold 5cm (Phase2)
#
# 実行方法:
#   bash scripts/run_50h_auto_plan.sh
#   ※ スクリプト内で logs/auto_plan_50h.log に自動書き込み済み（外部 tee 不要）
# ============================================================

set -eo pipefail

PROJ="c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032"
cd "$PROJ"

LOG="logs/auto_plan_50h.log"
WORKERS=2

# v2.40.0 ベースラインROI下限（この値を下回ったらPhase2スキップ）
# 2024ベースラインは~100%（収支-520円）のため下限を90%に設定（5pt余裕だと厳しすぎる）
# 2025ベースラインは~120%のため下限を95%に設定
BASELINE_ROI_2024=90.0
BASELINE_ROI_2025=95.0

# Phase1用: wave_height変更前のコミットハッシュ
PRE_WAVE_COMMIT="64c4298"

# wave_heightに関係する3ファイル（Phase1では旧版に差し替える）
WAVE_FILES=(
    "src/analysis/wave_height_adjuster.py"
    "src/analysis/beforeinfo_scorer.py"
    "config/weather_rules.json"
)

BACKUP_DIR="data/_phase1_wave_backup"
WAVE_FILES_SWAPPED=0

mkdir -p logs data "$BACKUP_DIR"

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

# バックテストJSONから指標を取得（encoding='utf-8' 必須）
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

# バックテスト結果を1行でログ出力し、ROIを stdout に返す
# 重要: log() は tee で stdout にも出力するため >&2 で stderr に向ける
#       これにより roi=$(log_backtest_detail ...) が ROI値のみをキャプチャできる
log_backtest_detail() {
    local phase_label=$1
    local year=$2
    local json_file=$3
    local roi profit bets hits hit_rate
    roi=$(extract_metric "$json_file" roi)
    profit=$(extract_metric "$json_file" profit)
    bets=$(extract_metric "$json_file" bets)
    hits=$(extract_metric "$json_file" hits)
    hit_rate=$(extract_metric "$json_file" hit_rate)
    # >&2: ログ出力を stderr に向けて stdout 汚染を防ぐ
    echo "[$(date '+%Y-%m-%d %H:%M:%S')]   [${phase_label}/${year}年] ROI=${roi}% | 収支=${profit}円 | 件数=${bets} | 的中=${hits}(${hit_rate}%)" | tee -a "$LOG" >&2
    echo "$roi"  # stdout には ROI 値のみ
}

# ============================================================
# クリーンアップ: スクリプト終了時に wave_height ファイルを復元
# ============================================================
cleanup() {
    local exit_code=$?
    if [ $WAVE_FILES_SWAPPED -eq 1 ]; then
        log "[cleanup] wave_heightファイルを現行版に復元中..."
        for f in "${WAVE_FILES[@]}"; do
            local basename
            basename=$(basename "$f")
            if [ -f "$BACKUP_DIR/$basename" ]; then
                cp "$BACKUP_DIR/$basename" "$f"
                log "  復元: $f"
            fi
        done
        WAVE_FILES_SWAPPED=0
        log "[cleanup] 復元完了"
    fi
    if [ $exit_code -ne 0 ]; then
        log "[ERROR] スクリプトがエラーで終了しました (exit_code=$exit_code)"
    fi
}
trap cleanup EXIT

# ============================================================
# 開始ログ（環境情報）
# ============================================================
SCRIPT_START=$(date +%s)
log "=========================================="
log "50時間自動実行プラン 開始"
log "  日時      : $(date)"
log "  Python    : $(python --version 2>&1)"
log "  Git branch: $(git branch --show-current 2>/dev/null || echo unknown)"
log "  Git HEAD  : $(git rev-parse --short HEAD 2>/dev/null)"
log "  Workers   : $WORKERS"
log "  ROI下限   : 2024=${BASELINE_ROI_2024}%, 2025=${BASELINE_ROI_2025}%"
log "  旧wave_height参照コミット: ${PRE_WAVE_COMMIT}"
log "=========================================="

# ============================================================
# 事前チェック
# ============================================================

# ディスク空き容量チェック（5GB未満なら警告）
log "ディスク空き容量チェック..."
FREE_GB=$(python -c "
import shutil
s = shutil.disk_usage('.')
print(f'{s.free / 1024**3:.1f}')
" 2>/dev/null || echo "0")
log "  空き容量: ${FREE_GB}GB"
python -c "
f = float('$FREE_GB')
if f < 5.0:
    print('WARNING: 空き容量が5GB未満です。再生成中にディスクフルになる可能性があります。')
" 2>/dev/null | tee -a "$LOG" || true

# Windows スリープ警告
log "  ⚠ Windowsスリープ設定: 電源オプションで「スリープしない」を確認してください"
log "    （設定方法: 設定 > 電源とバッテリー > スリープ → なし）"

# 前提確認: 4ファイルが存在するか
log "前提ファイル確認..."
for f in src/database/batch_data_loader.py "${WAVE_FILES[@]}"; do
    if [ ! -f "$f" ]; then
        log "ERROR: ファイルが見つかりません: $f"
        exit 1
    fi
    log "  OK: $f"
done

# ============================================================
# Phase 1: wave_height を旧版に差し替えて再生成
# ============================================================
log ""
log "=========================================="
log "Phase 1 開始: actual_course修正のみ測定"
log "  （wave_heightは ${PRE_WAVE_COMMIT} の旧版を一時使用）"
log "=========================================="

PHASE1_START=$(date +%s)

# 現行の wave_height ファイルをバックアップ
log "現行 wave_height ファイルをバックアップ: $BACKUP_DIR/"
for f in "${WAVE_FILES[@]}"; do
    cp "$f" "$BACKUP_DIR/"
    log "  保存: $f → $BACKUP_DIR/$(basename "$f")"
done

# 旧版を取得して差し替え
log "旧版 wave_height ファイルを ${PRE_WAVE_COMMIT} から復元..."
git show "${PRE_WAVE_COMMIT}:src/analysis/wave_height_adjuster.py" \
    > src/analysis/wave_height_adjuster.py
git show "${PRE_WAVE_COMMIT}:src/analysis/beforeinfo_scorer.py" \
    > src/analysis/beforeinfo_scorer.py
git show "${PRE_WAVE_COMMIT}:config/weather_rules.json" \
    > config/weather_rules.json
WAVE_FILES_SWAPPED=1

# 差し替え確認
log "差し替え後の確認:"
grep -m1 "rough.*min" config/weather_rules.json | tee -a "$LOG" || true
grep -m1 "def calculate_wave_height_adjustment" src/analysis/wave_height_adjuster.py | tee -a "$LOG" || true

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

# wave_height ファイルを現行版に戻す（Phase2用）
log ""
log "wave_heightファイルを現行版に復元..."
for f in "${WAVE_FILES[@]}"; do
    cp "$BACKUP_DIR/$(basename "$f")" "$f"
    log "  復元: $f"
done
WAVE_FILES_SWAPPED=0

# 復元確認
log "復元後の確認:"
grep -m1 "rough.*min" config/weather_rules.json | tee -a "$LOG" || true

PHASE1_END=$(date +%s)
log ""
log "--- Phase1 完了サマリー ($(elapsed_str $((PHASE1_END - PHASE1_START)))) ---"
log "  2024: ROI=${PHASE1_ROI_2024}%  (下限 ${BASELINE_ROI_2024}%)"
log "  2025: ROI=${PHASE1_ROI_2025}%  (下限 ${BASELINE_ROI_2025}%)"

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
    log "  2024: ${PHASE1_ROI_2024}% < 下限 ${BASELINE_ROI_2024}% ?"
    log "  2025: ${PHASE1_ROI_2025}% < 下限 ${BASELINE_ROI_2025}% ?"
    log "  ▶ actual_course修正がマイナス効果の可能性。手動確認してください。"
    log "=========================================="

    python - <<EOF 2>&1 | tee -a "$LOG"
import json
result = {
    'status': 'gate_fail',
    'completed_at': '$(date)',
    'config': {
        'workers': $WORKERS,
        'pre_wave_commit': '$PRE_WAVE_COMMIT',
        'baseline_roi_2024': $BASELINE_ROI_2024,
        'baseline_roi_2025': $BASELINE_ROI_2025,
    },
    'phase1': {
        'label': 'actual_course修正のみ',
        'roi_2024': $PHASE1_ROI_2024,
        'roi_2025': $PHASE1_ROI_2025,
    },
    'gate': 'FAIL',
    'phase2': None,
}
with open('data/auto_plan_results.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print('結果を data/auto_plan_results.json に保存しました')
EOF
    exit 0
fi

log "ROIゲート 合格: Phase2に進みます"

# ============================================================
# Phase 2: 現行版 wave_height で再生成
# ============================================================
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
SCRIPT_END=$(date +%s)

# ============================================================
# 最終サマリー
# ============================================================
log ""
log "=========================================="
log "50時間自動プラン 完了"
log "  完了日時  : $(date)"
log "  総所要時間: $(elapsed_str $((SCRIPT_END - SCRIPT_START)))"
log ""
log "  Phase1 actual_course修正のみ ($(elapsed_str $((PHASE1_END - PHASE1_START))))"
log "    2024: ROI=${PHASE1_ROI_2024}%"
log "    2025: ROI=${PHASE1_ROI_2025}%"
log ""
log "  Phase2 actual_course + wave_height改善 ($(elapsed_str $((PHASE2_END - PHASE2_START))))"
log "    2024: ROI=${PHASE2_ROI_2024}%"
log "    2025: ROI=${PHASE2_ROI_2025}%"
log ""

# wave_height 限界効果を計算（Python で小数演算）
WAVE_DELTA_2024=$(python -c "print(f'{$PHASE2_ROI_2024 - $PHASE1_ROI_2024:+.1f}')" 2>/dev/null || echo "?")
WAVE_DELTA_2025=$(python -c "print(f'{$PHASE2_ROI_2025 - $PHASE1_ROI_2025:+.1f}')" 2>/dev/null || echo "?")
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
    return {
        'total': d.get('total', {}),
        'conditions': d.get('conditions', []),
    }

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
        'elapsed': '$(elapsed_str $((PHASE1_END - PHASE1_START)))',
        '2024': load_bt('phase1', '2024'),
        '2025': load_bt('phase1', '2025'),
    },
    'gate': 'PASS',
    'phase2': {
        'label': 'actual_course + wave_height改善（現行版）',
        'elapsed': '$(elapsed_str $((PHASE2_END - PHASE2_START)))',
        '2024': load_bt('phase2', '2024'),
        '2025': load_bt('phase2', '2025'),
    },
}

# wave_delta をPythonで計算（shell変数の"?"混入を防ぐ）
def safe_delta(phase2_year, phase1_year):
    try:
        r2 = load_bt('phase2', phase2_year).get('total', {}).get('roi') or 0
        r1 = load_bt('phase1', phase1_year).get('total', {}).get('roi') or 0
        return round(float(r2) - float(r1), 1)
    except Exception:
        return None

result['phase2']['wave_delta_2024'] = safe_delta('2024', '2024')
result['phase2']['wave_delta_2025'] = safe_delta('2025', '2025')
with open('data/auto_plan_results.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print('  結果を data/auto_plan_results.json に保存しました')
EOF

log "完了"
