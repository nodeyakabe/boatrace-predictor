#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2025年データでの信頼度別ROI検証（高速版）
==========================================

検証項目:
1. 信頼度別的中率（A, B, C, D, E）
2. 信頼度別ROI
3. ベースライン vs オッズ校正の比較
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag
import sqlite3
from collections import defaultdict

DB_PATH = "data/boatrace_backup_20251212_145413.db"

def quick_2025_verification(num_races=50):
    """2025年データでの高速検証"""

    print("=" * 80)
    print("2025年データ 信頼度別ROI検証（高速版）")
    print("=" * 80)
    print(f"検証レース数: {num_races}")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 2025年のオッズデータがあるレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id FROM races r
        INNER JOIN results res ON res.race_id = r.id
        INNER JOIN trifecta_odds odds ON odds.race_id = r.id
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2025-04-01'
            AND res.is_invalid = 0
        ORDER BY r.id LIMIT ?
    ''', (num_races,))
    race_ids = [row[0] for row in cursor.fetchall()]

    if len(race_ids) == 0:
        print("[ERROR] 2025年のデータが見つかりません")
        conn.close()
        return

    print(f"[DATA] 取得レース数: {len(race_ids)}")
    print()

    # ========================================
    # ベースライン測定（機能無効）
    # ========================================
    print("[1/2] ベースライン測定（rank23_odds_calibration: False）")
    print("-" * 80)

    set_feature_flag('rank23_odds_calibration', False)
    predictor_baseline = RacePredictor(DB_PATH, use_cache=False)

    baseline_stats = {
        'total': defaultdict(int),
        'trifecta_hits': defaultdict(int),
        '1st_hits': defaultdict(int),
        'investment': defaultdict(int),
        'returns': defaultdict(float)
    }

    for i, race_id in enumerate(race_ids):
        if i % 10 == 0:
            print(f"  進捗: {i}/{len(race_ids)}", end="\r")

        try:
            predictions = predictor_baseline.predict_race(race_id, use_beforeinfo=True)
            if len(predictions) < 3:
                continue

            # 信頼度を取得（最上位艇の信頼度を使用）
            confidence = predictions[0].get('confidence', 'C')

            pred_1st = predictions[0]['pit_number']
            pred_combo = f"{predictions[0]['pit_number']}-{predictions[1]['pit_number']}-{predictions[2]['pit_number']}"

            # 実際の結果
            cursor.execute('''
                SELECT GROUP_CONCAT(pit_number, '-') as combo,
                       (SELECT pit_number FROM results WHERE race_id = ? AND rank = 1 AND is_invalid = 0) as first
                FROM (SELECT pit_number FROM results WHERE race_id = ? AND is_invalid = 0 AND rank <= 3 ORDER BY rank)
            ''', (race_id, race_id))
            row = cursor.fetchone()
            if not row or not row[0]:
                continue

            actual_combo = row[0]
            actual_1st = row[1]

            # 三連単オッズを取得
            cursor.execute('''
                SELECT odds FROM trifecta_odds
                WHERE race_id = ? AND combination = ?
            ''', (race_id, pred_combo))
            odds_row = cursor.fetchone()
            if not odds_row:
                continue
            odds = odds_row[0]

            # 統計を記録
            baseline_stats['total'][confidence] += 1
            baseline_stats['total']['ALL'] += 1
            baseline_stats['investment'][confidence] += 100  # 100円ベット
            baseline_stats['investment']['ALL'] += 100

            if pred_combo == actual_combo:
                baseline_stats['trifecta_hits'][confidence] += 1
                baseline_stats['trifecta_hits']['ALL'] += 1
                baseline_stats['returns'][confidence] += odds * 100
                baseline_stats['returns']['ALL'] += odds * 100

            if pred_1st == actual_1st:
                baseline_stats['1st_hits'][confidence] += 1
                baseline_stats['1st_hits']['ALL'] += 1

        except Exception as e:
            pass

    print(f"  完了: {len(race_ids)}/{len(race_ids)}")
    print()

    # ========================================
    # オッズ校正測定（機能有効）
    # ========================================
    print("[2/2] オッズ校正測定（rank23_odds_calibration: True）")
    print("-" * 80)

    set_feature_flag('rank23_odds_calibration', True)
    predictor_calibrated = RacePredictor(DB_PATH, use_cache=False)

    calibrated_stats = {
        'total': defaultdict(int),
        'trifecta_hits': defaultdict(int),
        '1st_hits': defaultdict(int),
        'investment': defaultdict(int),
        'returns': defaultdict(float)
    }

    for i, race_id in enumerate(race_ids):
        if i % 10 == 0:
            print(f"  進捗: {i}/{len(race_ids)}", end="\r")

        try:
            predictions = predictor_calibrated.predict_race(race_id, use_beforeinfo=True)
            if len(predictions) < 3:
                continue

            confidence = predictions[0].get('confidence', 'C')

            pred_1st = predictions[0]['pit_number']
            pred_combo = f"{predictions[0]['pit_number']}-{predictions[1]['pit_number']}-{predictions[2]['pit_number']}"

            cursor.execute('''
                SELECT GROUP_CONCAT(pit_number, '-') as combo,
                       (SELECT pit_number FROM results WHERE race_id = ? AND rank = 1 AND is_invalid = 0) as first
                FROM (SELECT pit_number FROM results WHERE race_id = ? AND is_invalid = 0 AND rank <= 3 ORDER BY rank)
            ''', (race_id, race_id))
            row = cursor.fetchone()
            if not row or not row[0]:
                continue

            actual_combo = row[0]
            actual_1st = row[1]

            cursor.execute('''
                SELECT odds FROM trifecta_odds
                WHERE race_id = ? AND combination = ?
            ''', (race_id, pred_combo))
            odds_row = cursor.fetchone()
            if not odds_row:
                continue
            odds = odds_row[0]

            calibrated_stats['total'][confidence] += 1
            calibrated_stats['total']['ALL'] += 1
            calibrated_stats['investment'][confidence] += 100
            calibrated_stats['investment']['ALL'] += 100

            if pred_combo == actual_combo:
                calibrated_stats['trifecta_hits'][confidence] += 1
                calibrated_stats['trifecta_hits']['ALL'] += 1
                calibrated_stats['returns'][confidence] += odds * 100
                calibrated_stats['returns']['ALL'] += odds * 100

            if pred_1st == actual_1st:
                calibrated_stats['1st_hits'][confidence] += 1
                calibrated_stats['1st_hits']['ALL'] += 1

        except Exception as e:
            pass

    print(f"  完了: {len(race_ids)}/{len(race_ids)}")
    print()

    # ========================================
    # 結果サマリー
    # ========================================
    print("=" * 80)
    print("信頼度別 結果サマリー")
    print("=" * 80)
    print()

    confidence_levels = ['A', 'B', 'C', 'D', 'E', 'ALL']

    for conf in confidence_levels:
        b_total = baseline_stats['total'][conf]
        c_total = calibrated_stats['total'][conf]

        if b_total == 0 and c_total == 0:
            continue

        print(f"【信頼度 {conf}】")
        print(f"  レース数: {b_total}")

        if b_total > 0:
            # ベースライン
            b_trifecta_rate = baseline_stats['trifecta_hits'][conf] / b_total * 100
            b_1st_rate = baseline_stats['1st_hits'][conf] / b_total * 100
            b_investment = baseline_stats['investment'][conf]
            b_returns = baseline_stats['returns'][conf]
            b_roi = (b_returns - b_investment) / b_investment * 100 if b_investment > 0 else 0

            print(f"  [ベースライン]")
            print(f"    三連単的中率: {b_trifecta_rate:.2f}% ({baseline_stats['trifecta_hits'][conf]}/{b_total})")
            print(f"    1着的中率:    {b_1st_rate:.2f}% ({baseline_stats['1st_hits'][conf]}/{b_total})")
            print(f"    ROI:          {b_roi:+.2f}% (投資{b_investment:,}円 / 払戻{b_returns:,.0f}円)")

        if c_total > 0:
            # オッズ校正
            c_trifecta_rate = calibrated_stats['trifecta_hits'][conf] / c_total * 100
            c_1st_rate = calibrated_stats['1st_hits'][conf] / c_total * 100
            c_investment = calibrated_stats['investment'][conf]
            c_returns = calibrated_stats['returns'][conf]
            c_roi = (c_returns - c_investment) / c_investment * 100 if c_investment > 0 else 0

            print(f"  [オッズ校正]")
            print(f"    三連単的中率: {c_trifecta_rate:.2f}% ({calibrated_stats['trifecta_hits'][conf]}/{c_total})")
            print(f"    1着的中率:    {c_1st_rate:.2f}% ({calibrated_stats['1st_hits'][conf]}/{c_total})")
            print(f"    ROI:          {c_roi:+.2f}% (投資{c_investment:,}円 / 払戻{c_returns:,.0f}円)")

        if b_total > 0 and c_total > 0:
            # 差分
            diff_trifecta = c_trifecta_rate - b_trifecta_rate
            diff_roi = c_roi - b_roi
            print(f"  [差分]")
            print(f"    三連単: {diff_trifecta:+.2f}pt")
            print(f"    ROI:    {diff_roi:+.2f}pt")

        print()

    print("=" * 80)

    conn.close()

    # 機能フラグを戻す
    set_feature_flag('rank23_odds_calibration', True)

if __name__ == "__main__":
    quick_2025_verification(50)
