# -*- coding: utf-8 -*-
"""超簡略化オッズテスト"""
import sys
import sqlite3
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

db_path = str(ROOT_DIR / 'data' / 'boatrace_backup_20251212_145413.db')

# 結果をファイルに出力
output_file = ROOT_DIR / 'results' / 'odds_test_result.txt'

from src.analysis.race_predictor import RacePredictor
from src.analysis.scorers.odds_calibrator import OddsCalibrator
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus

def run():
    output = []
    output.append("=== Odds Integration Test ===")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT r.id as race_id, r.venue_code
        FROM races r
        INNER JOIN trifecta_odds o ON r.id = o.race_id
        INNER JOIN results res ON r.id = res.race_id
        WHERE r.race_date BETWEEN '2025-11-28' AND '2025-12-10'
        AND res.is_invalid = 0
        LIMIT 500
    ''')
    races = [dict(row) for row in cursor.fetchall()]
    output.append(f'Races: {len(races)}')

    predictor = RacePredictor(db_path)
    evaluator = BetTargetEvaluator()
    calibrator = OddsCalibrator(db_path, rank23_alpha=0.2)

    stats_base = {'n': 0, 'hit': 0, 'r2': 0, 'r3': 0, 'bet': 0, 'pay': 0}
    stats_cal = {'n': 0, 'hit': 0, 'r2': 0, 'r3': 0, 'bet': 0, 'pay': 0}

    for i, race in enumerate(races):
        race_id = race['race_id']
        try:
            preds = predictor.predict_race(race_id)
        except Exception as e:
            continue

        if not preds or len(preds) < 6:
            continue

        conf = preds[0].get('confidence', 'E')
        if conf in ['A', 'B']:
            continue

        top3 = [p['pit_number'] for p in preds[:3]]
        combo = f'{top3[0]}-{top3[1]}-{top3[2]}'

        preds_cal = calibrator.calibrate_rank23_predictions([p.copy() for p in preds], race_id, 0.2)
        top3_cal = [p['pit_number'] for p in preds_cal[:3]]
        combo_cal = f'{top3_cal[0]}-{top3_cal[1]}-{top3_cal[2]}'

        cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id=? AND combination=?', (race_id, combo))
        row = cursor.fetchone()
        if not row:
            continue
        odds = row['odds']

        # 購入条件のチェックをスキップして純粋な予測精度を測定
        # (BetTargetEvaluatorの条件は厳しいため、全レースで精度を測定)
        bet_amount = 100  # 固定100円

        cursor.execute('SELECT pit_number FROM results WHERE race_id=? AND is_invalid=0 AND rank IN ("1","2","3") ORDER BY rank', (race_id,))
        actual = [r['pit_number'] for r in cursor.fetchall()]
        if len(actual) < 3:
            continue
        actual_combo = f'{actual[0]}-{actual[1]}-{actual[2]}'

        # Baseline
        stats_base['n'] += 1
        stats_base['bet'] += bet_amount
        if top3[1] == actual[1]: stats_base['r2'] += 1
        if top3[2] == actual[2]: stats_base['r3'] += 1
        if combo == actual_combo:
            stats_base['hit'] += 1
            cursor.execute('SELECT amount FROM payouts WHERE race_id=? AND bet_type="trifecta" AND combination=?', (race_id, actual_combo))
            p = cursor.fetchone()
            if p: stats_base['pay'] += (bet_amount/100)*p['amount']

        # Calibrated
        stats_cal['n'] += 1
        stats_cal['bet'] += bet_amount
        if top3_cal[1] == actual[1]: stats_cal['r2'] += 1
        if top3_cal[2] == actual[2]: stats_cal['r3'] += 1
        if combo_cal == actual_combo:
            stats_cal['hit'] += 1
            cursor.execute('SELECT amount FROM payouts WHERE race_id=? AND bet_type="trifecta" AND combination=?', (race_id, actual_combo))
            p = cursor.fetchone()
            if p: stats_cal['pay'] += (bet_amount/100)*p['amount']

        if (i+1) % 10 == 0:
            output.append(f'Processed: {i+1}')

    conn.close()

    output.append("\n=== Results ===")
    for name, s in [('Baseline', stats_base), ('Alpha=0.2', stats_cal)]:
        if s['n'] == 0:
            continue
        roi = s['pay']/s['bet']*100 if s['bet'] > 0 else 0
        output.append(f"{name}: n={s['n']}, hit={s['hit']}, ROI={roi:.1f}%, "
                     f"R2={s['r2']/s['n']*100:.1f}%, R3={s['r3']/s['n']*100:.1f}%")

    # ファイルに保存
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output))

    # 画面にも出力
    for line in output:
        print(line)

if __name__ == "__main__":
    run()
