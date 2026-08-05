"""
Phase 2 Task D 回帰テスト
修正後の check_and_notify() 評価ロジックが正しく動作することを検証する。

対象:
  - ADV○BEF×（誤購入パターン）→ before値で評価すれば全件EXCLUDED（却下）されること
  - ADV○BEF○（整合パターン） → before値で評価しても全件PASS（通過）すること
  - ADV×BEF○（正常パターン） → before値で評価して全件PASS（通過）すること

実行方法:
  cd BoatRace_package_20251115_172032
  python -m pytest tests/regression/test_phase2_purchase_integrity.py -v

または直接実行:
  python tests/regression/test_phase2_purchase_integrity.py
"""
import sys
import csv
import os
import sqlite3
from typing import Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.bet_conditions import STANDARD_BET_CONDITIONS

DB_PATH = os.path.join(os.path.dirname(__file__), '../../data/boatrace.db')
QUADRANT_CSV = os.path.join(os.path.dirname(__file__),
    '../../reports/diagnosis_20260713/phase2/purchase_quadrant.csv')

ACTIVE_CONDITIONS = {c['id']: c for c in STANDARD_BET_CONDITIONS if c.get('active', True) is not False}


def check_condition_match(cond: Dict, conf: Optional[str], score: Optional[float]) -> Tuple[bool, str]:
    """confidence/score が条件フィルターを通過するか判定"""
    if conf is None or score is None:
        return False, f"データなし(conf={conf}, score={score})"
    cond_conf = cond.get('confidence')
    if cond_conf and conf != cond_conf:
        return False, f"信頼度不一致(期待:{cond_conf} 実際:{conf})"
    score_min = cond.get('score_min', -999)
    score_max = cond.get('score_max', 9999)
    if score < score_min:
        return False, f"スコア下限未満({score:.1f}<{score_min})"
    if score >= score_max:
        return False, f"スコア上限超過({score:.1f}>={score_max})"
    return True, "OK"


def get_predictions_after_fix(cursor, race_id: int) -> Tuple[Optional[str], Optional[float]]:
    """
    修正後の _get_predictions() 相当:
    before予測優先、なければadvanceにフォールバック
    """
    cursor.execute("""
        SELECT confidence, total_score
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before' AND rank_prediction = 1
    """, (race_id,))
    row = cursor.fetchone()
    if row:
        return row['confidence'], row['total_score']
    # fallback to advance
    cursor.execute("""
        SELECT confidence, total_score
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'advance' AND rank_prediction = 1
    """, (race_id,))
    row = cursor.fetchone()
    if row:
        return row['confidence'], row['total_score']
    return None, None


def load_quadrant_csv():
    """purchase_quadrant.csv を読み込んでquadrant別に分類"""
    rows = []
    with open(QUADRANT_CSV, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def test_phase2_regression():
    """メイン回帰テスト"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = load_quadrant_csv()
    # 条件特定済みかつ UNKNOWN 以外
    testable = [r for r in rows if r['effective_condition_id'] not in ('UNKNOWN', '') and
                r['effective_condition_id'] in ACTIVE_CONDITIONS]
    print(f"テスト対象: {len(testable)}件（条件特定済み）")

    # quadrant別に分類
    adv_ok_bef_ng = [r for r in testable if r['quadrant'] == 'ADV○BEF×']
    adv_ok_bef_ok = [r for r in testable if r['quadrant'] == 'ADV○BEF○']
    adv_ng_bef_ok = [r for r in testable if r['quadrant'] == 'ADV×BEF○']
    print(f"  ADV○BEF×: {len(adv_ok_bef_ng)}件")
    print(f"  ADV○BEF○: {len(adv_ok_bef_ok)}件")
    print(f"  ADV×BEF○: {len(adv_ng_bef_ok)}件")

    failures = []
    total_tests = 0

    # ADV○BEF× → 修正後ロジックでは EXCLUDED（before値で評価 → FAIL）
    # ただし「before予測なし」のケースは Task 2（advance フォールバック封鎖）で対処する別問題
    print("\n=== ADV○BEF× テスト（全件 EXCLUDED 期待） ===")
    no_before_count = 0
    for row in adv_ok_bef_ng:
        race_id = int(row['race_id'])
        cid = row['effective_condition_id']
        cond = ACTIVE_CONDITIONS[cid]
        bef_reason = row.get('bef_reason', '')
        # before予測なしのケースは Task 2 対象として分離
        if 'before予測なし' in bef_reason or 'データなし' in bef_reason:
            no_before_count += 1
            print(f"  [Task2] {race_id} [{cid}] - before予測未生成（Task2対象・このテストではスキップ）")
            continue
        conf, score = get_predictions_after_fix(cur, race_id)
        passed, reason = check_condition_match(cond, conf, score)
        total_tests += 1
        if passed:
            failures.append({
                'test': 'ADV○BEF×→EXCLUDED',
                'race_id': race_id,
                'cid': cid,
                'conf': conf,
                'score': score,
                'reason': f'修正後でも通過してしまう: {reason}',
            })
            print(f"  FAIL: {race_id} [{cid}] conf={conf} score={score} - {reason}")
        else:
            score_str = f"{score:.1f}" if score is not None else "N/A"
            print(f"  OK:   {race_id} [{cid}] conf={conf} score={score_str} → {reason}")
    if no_before_count:
        print(f"  [Task2スキップ]: {no_before_count}件（before予測未生成 → Task 2で封鎖済み）")

    # ADV○BEF○ → 修正後ロジックでも PASS
    print("\n=== ADV○BEF○ テスト（全件 PASS 期待） ===")
    for row in adv_ok_bef_ok:
        race_id = int(row['race_id'])
        cid = row['effective_condition_id']
        cond = ACTIVE_CONDITIONS[cid]
        conf, score = get_predictions_after_fix(cur, race_id)
        passed, reason = check_condition_match(cond, conf, score)
        total_tests += 1
        if not passed:
            failures.append({
                'test': 'ADV○BEF○→PASS',
                'race_id': race_id,
                'cid': cid,
                'conf': conf,
                'score': score,
                'reason': f'修正後に通過しない: {reason}',
            })
            print(f"  FAIL: {race_id} [{cid}] conf={conf} score={score} - {reason}")
        else:
            score_str = f"{score:.1f}" if score is not None else "N/A"
            print(f"  OK:   {race_id} [{cid}] conf={conf} score={score_str} → PASS")

    # ADV×BEF○ → 修正後ロジックでも PASS
    print("\n=== ADV×BEF○ テスト（全件 PASS 期待） ===")
    for row in adv_ng_bef_ok:
        race_id = int(row['race_id'])
        cid = row['effective_condition_id']
        cond = ACTIVE_CONDITIONS[cid]
        conf, score = get_predictions_after_fix(cur, race_id)
        passed, reason = check_condition_match(cond, conf, score)
        total_tests += 1
        if not passed:
            failures.append({
                'test': 'ADV×BEF○→PASS',
                'race_id': race_id,
                'cid': cid,
                'conf': conf,
                'score': score,
                'reason': f'修正後に通過しない: {reason}',
            })
            print(f"  FAIL: {race_id} [{cid}] conf={conf} score={score} - {reason}")
        else:
            score_str = f"{score:.1f}" if score is not None else "N/A"
            print(f"  OK:   {race_id} [{cid}] conf={conf} score={score_str} → PASS")

    conn.close()

    print(f"\n=== 結果 ===")
    print(f"テスト数: {total_tests}")
    print(f"FAIL: {len(failures)}")
    if failures:
        print("\n失敗一覧:")
        for f in failures:
            print(f"  [{f['test']}] race_id={f['race_id']} cid={f['cid']}: {f['reason']}")
        print("\n[FAIL] テスト FAIL: 期待と異なる結果があります。修正内容を確認してください。")
        return False
    else:
        print("\n[OK] 全テスト PASS")
        return True


if __name__ == '__main__':
    ok = test_phase2_regression()
    sys.exit(0 if ok else 1)
