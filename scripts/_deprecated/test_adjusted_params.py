#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""パラメータ調整版の効果測定"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# 警告を抑制
import warnings
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag
import sqlite3

DB_PATH = "data/boatrace_backup_20251212_145413.db"

def test_adjusted_parameters():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 50レースでテスト
    cursor.execute('''
        SELECT DISTINCT r.id FROM races r
        INNER JOIN results res ON res.race_id = r.id
        INNER JOIN trifecta_odds odds ON odds.race_id = r.id
        WHERE r.race_date >= '2024-01-01' AND r.race_date < '2024-01-25'
            AND res.is_invalid = 0 AND res.rank = 1
        ORDER BY r.id LIMIT 50
    ''')
    race_ids = [row[0] for row in cursor.fetchall()]

    print('パラメータ調整版の検証: 50レース')
    print('新パラメータ: α=0.5, T=4.0, 補正0.7-1.6倍')
    print('=' * 60)

    # ベースライン
    print('\n[1/2] ベースライン測定...')
    predictor = RacePredictor(DB_PATH, use_cache=False)
    b_ok, b_tot = 0, 0
    for rid in race_ids:
        try:
            preds = predictor.predict_race(rid, use_beforeinfo=True)
            if not preds:
                continue
            cursor.execute('SELECT pit_number FROM results WHERE race_id=? AND rank=1 AND is_invalid=0', (rid,))
            r = cursor.fetchone()
            if r:
                b_tot += 1
                if preds[0]['pit_number'] == r[0]:
                    b_ok += 1
        except:
            pass

    b_acc = b_ok / b_tot if b_tot else 0
    print(f'  完了: {b_acc:.2%} ({b_ok}/{b_tot})')

    # オッズ校正（新パラメータ）
    print('\n[2/2] オッズ校正測定（α=0.5, T=4.0）...')
    set_feature_flag('odds_calibration', True)
    cp = RacePredictor(DB_PATH, use_cache=False)
    t_ok, t_tot = 0, 0
    for rid in race_ids:
        try:
            preds = cp.predict_race(rid, use_beforeinfo=True)
            if not preds:
                continue
            cursor.execute('SELECT pit_number FROM results WHERE race_id=? AND rank=1 AND is_invalid=0', (rid,))
            r = cursor.fetchone()
            if r:
                t_tot += 1
                if preds[0]['pit_number'] == r[0]:
                    t_ok += 1
        except:
            pass

    t_acc = t_ok / t_tot if t_tot else 0
    diff = (t_acc - b_acc) * 100

    print(f'  完了: {t_acc:.2%} ({t_ok}/{t_tot})')
    print()
    print('=' * 60)
    print(f'ベースライン: {b_acc:.4%}')
    print(f'オッズ校正:   {t_acc:.4%}')
    print(f'差分:         {diff:+.2f}pt')
    print('=' * 60)

    if diff > 0.5:
        print('\n[GOOD] 改善効果あり → 200レースで本格検証')
    elif diff > -0.5:
        print('\n[NEUTRAL] 効果微小 → 2着・3着適用を検討')
    else:
        print('\n[WARN] 悪化 → 設定見直し')

    conn.close()
    set_feature_flag('odds_calibration', False)

if __name__ == "__main__":
    test_adjusted_parameters()
