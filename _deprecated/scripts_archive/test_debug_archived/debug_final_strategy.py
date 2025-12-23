# -*- coding: utf-8 -*-
"""最終運用戦略のデバッグ - 的中レースの詳細確認"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus

db_path = ROOT_DIR / "data" / "boatrace.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

evaluator = BetTargetEvaluator()

# 2025年1月のデータで確認
cursor.execute('''
    SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-01-31'
    ORDER BY r.race_date, r.venue_code, r.race_number
''')

races = cursor.fetchall()
hit_count = 0

print("的中レース詳細（最初の5件）")
print("=" * 100)

for race in races:
    if hit_count >= 5:
        break

    race_id = race['race_id']
    venue_code = int(race['venue_code']) if race['venue_code'] else 0

    # 1コース級別
    cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
    c1 = cursor.fetchone()
    c1_rank = c1['racer_rank'] if c1 else 'B1'

    # 予測
    cursor.execute('''
        SELECT pit_number, confidence
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'advance'
        ORDER BY rank_prediction
    ''', (race_id,))
    preds = cursor.fetchall()

    if len(preds) < 6:
        continue

    confidence = preds[0]['confidence']
    pred_combo = f"{preds[0]['pit_number']}-{preds[1]['pit_number']}-{preds[2]['pit_number']}"

    # オッズ
    cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?', (race_id, pred_combo))
    odds_row = cursor.fetchone()
    pred_odds = odds_row['odds'] if odds_row else 0

    # 判定
    result = evaluator.evaluate(
        confidence=confidence,
        c1_rank=c1_rank,
        old_combo=pred_combo,
        new_combo=pred_combo,
        old_odds=pred_odds,
        new_odds=pred_odds,
        has_beforeinfo=True,
        venue_code=venue_code
    )

    if result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
        continue

    # 実際の結果
    cursor.execute('''
        SELECT pit_number FROM results
        WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
        ORDER BY rank
    ''', (race_id,))
    results = cursor.fetchall()

    if len(results) < 3:
        continue

    actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

    # 実際のオッズ
    cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?', (race_id, actual_combo))
    actual_odds_row = cursor.fetchone()
    actual_odds = actual_odds_row['odds'] if actual_odds_row else 0

    if pred_combo == actual_combo:
        hit_count += 1
        payout = (result.bet_amount / 100) * actual_odds

        print(f"\n[的中{hit_count}] {race['race_date']} 会場{venue_code} R{race['race_number']}")
        print(f"  信頼度: {confidence}, 1コース: {c1_rank}")
        print(f"  予測: {pred_combo}, 予測オッズ: {pred_odds:.1f}倍")
        print(f"  実際: {actual_combo}, 実際オッズ: {actual_odds:.1f}倍")
        print(f"  賭け金: {result.bet_amount}円, 払戻: {payout:.0f}円")
        print(f"  ROI: {(payout/result.bet_amount*100):.1f}%")

conn.close()
print("\n" + "=" * 100)
