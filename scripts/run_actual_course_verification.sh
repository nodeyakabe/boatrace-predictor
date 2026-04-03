#!/bin/bash
# actual_course 検証 自動化スクリプト
# -----------------------------------------------
# 【処理内容】
#   STEP 1: 現在進行中の再生成が完了するまで待機
#   STEP 2: B1バックテスト保存（wind_direction適用後・actual_course未適用）
#   STEP 3: batch_data_loader.py に actual_course パッチ適用
#   STEP 4: before 全年度再生成（2020-2025、4並列）
#   STEP 5: B2バックテスト保存（actual_course適用後）
#   STEP 6: B1 vs B2 比較レポート出力
#
# 【実行方法】
#   nohup bash scripts/run_actual_course_verification.sh > logs/actual_course_verification.log 2>&1 &
#   tail -f logs/actual_course_verification.log
#
# 【所要時間目安】
#   現在の再生成完了待ち: 不明（最大24時間）
#   B1バックテスト: ~30分
#   before 全年度再生成（4並列）: ~42時間（7時間/年 × 6年）
#   B2バックテスト: ~30分
#   合計（待ち除く）: ~43時間
# -----------------------------------------------

set -euo pipefail
cd "c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032"

WORKERS=4
BASELINE_B1="data/baselines/B1_wind_direction.json"
BASELINE_B2="data/baselines/B2_actual_course.json"
PATCH_TARGET="src/database/batch_data_loader.py"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# ================================================================
# STEP 1: 現在の再生成が完了するまで待機
# ================================================================
log "=== STEP 1: 現在の再生成完了待ち ==="
log "  generate_before_fast_parallel.py が終了するまで5分おきに確認します..."
log "  ※ 現在 2023年(Run A) と 2021年(Run B) が並列稼働中"

while true; do
    RUNNING=$(wmic process where "name='python.exe'" get commandline 2>/dev/null \
              | grep "generate_before_fast_parallel\|generate_advance_fast_parallel" \
              | wc -l 2>/dev/null || echo 0)
    RUNNING=$(echo "$RUNNING" | tr -d ' \r\n')
    if [ "$RUNNING" -eq 0 ] 2>/dev/null; then
        log "  現在の再生成プロセスが終了しました。次のステップに進みます。"
        break
    fi
    log "  再生成中（${RUNNING}プロセス）... 5分後に再確認"
    sleep 300
done

# ================================================================
# STEP 2: B1 バックテスト保存
# ================================================================
log ""
log "=== STEP 2: B1バックテスト（wind_direction済み・actual_course前）==="
mkdir -p data/baselines
python scripts/backtest/standard_backtest_unique.py --full --save-json "$BASELINE_B1"
log "  B1保存完了: $BASELINE_B1"

# ================================================================
# STEP 3: batch_data_loader.py に actual_course パッチ適用
# ================================================================
log ""
log "=== STEP 3: actual_course パッチ適用 ==="

python3 - <<'PYEOF'
import re, sys

path = "src/database/batch_data_loader.py"
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# --- パッチ1: pit_number → COALESCE(rd.actual_course, e.pit_number) ---
OLD_COL = "                e.pit_number as course,"
NEW_COL = "                COALESCE(rd.actual_course, e.pit_number) as course,"

if NEW_COL in content:
    print("[SKIP] パッチ1は既に適用済みです")
elif OLD_COL not in content:
    print("[ERROR] パッチ1: 対象文字列が見つかりません。手動確認が必要です。")
    sys.exit(1)
else:
    content = content.replace(OLD_COL, NEW_COL, 1)
    print("[OK] パッチ1適用: pit_number → COALESCE(rd.actual_course, e.pit_number)")

# --- パッチ2: GROUP BY に actual_course を反映 ---
OLD_GROUP = "            GROUP BY e.racer_number, e.pit_number"
NEW_GROUP = "            GROUP BY e.racer_number, COALESCE(rd.actual_course, e.pit_number)"

if NEW_GROUP in content:
    print("[SKIP] パッチ2は既に適用済みです")
elif OLD_GROUP not in content:
    print("[ERROR] パッチ2: GROUP BY 対象が見つかりません。手動確認が必要です。")
    sys.exit(1)
else:
    content = content.replace(OLD_GROUP, NEW_GROUP, 1)
    print("[OK] パッチ2適用: GROUP BY を更新")

# --- パッチ3: query_course ブロックに LEFT JOIN race_details を追加 ---
import re as _re
OLD_JOIN = "            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number\n            WHERE e.racer_number IN"
NEW_JOIN = "            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number\n            LEFT JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number\n            WHERE e.racer_number IN"

# query_course ブロック内だけで LEFT JOIN の有無を確認
_course_match = _re.search(r'query_course = f"""(.*?)"""', content, _re.DOTALL)
if _course_match and 'LEFT JOIN race_details rd' in _course_match.group(1):
    print("[SKIP] パッチ3は既に適用済みです（query_course ブロック内に LEFT JOIN を確認）")
elif OLD_JOIN not in content:
    print("[ERROR] パッチ3: JOIN対象が見つかりません。手動確認が必要です。")
    sys.exit(1)
else:
    count = content.count(OLD_JOIN)
    content = content.replace(OLD_JOIN, NEW_JOIN, 1)
    print(f"[OK] パッチ3適用: {count}箇所のうち1箇所（query_course）に LEFT JOIN race_details を追加")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("[完了] batch_data_loader.py へのパッチ適用が完了しました。")
PYEOF

if [ $? -ne 0 ]; then
    log "  [ERROR] パッチ適用に失敗しました。処理を中断します。"
    log "  手動で src/database/batch_data_loader.py を確認してください。"
    exit 1
fi

log "  パッチ適用完了"

# ================================================================
# STEP 4: before 全年度再生成（2020-2025）
# ================================================================
log ""
log "=== STEP 4: before 全年度再生成 開始（${WORKERS}並列）==="

for year in 2020 2021 2022 2023 2024 2025; do
    log "  --- ${year}年 開始: $(date) ---"
    python scripts/prediction/generate_before_fast_parallel.py \
        --year $year --workers $WORKERS --force
    if [ $? -ne 0 ]; then
        log "  [ERROR] ${year}年 再生成に失敗しました。処理を中断します。"
        exit 1
    fi
    log "  --- ${year}年 完了: $(date) ---"
done

log "  全年度再生成 完了"

# ================================================================
# STEP 5: B2 バックテスト保存
# ================================================================
log ""
log "=== STEP 5: B2バックテスト（actual_course適用後）==="
python scripts/backtest/standard_backtest_unique.py --full --save-json "$BASELINE_B2"
log "  B2保存完了: $BASELINE_B2"

# ================================================================
# STEP 6: 比較レポート出力
# ================================================================
log ""
log "=== STEP 6: B1 vs B2 比較レポート ==="
python scripts/maintenance/compare_baselines.py \
    --b1 "$BASELINE_B1" \
    --b2 "$BASELINE_B2" \
    --label1 "B1（wind_direction済み・actual_course前）" \
    --label2 "B2（actual_course適用後）"

log ""
log "=== 全工程完了: $(date) ==="
log "  B1: $BASELINE_B1"
log "  B2: $BASELINE_B2"
log "  レポート確認: python scripts/maintenance/compare_baselines.py --b1 $BASELINE_B1 --b2 $BASELINE_B2"
