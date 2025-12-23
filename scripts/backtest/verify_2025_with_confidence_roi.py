#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2025年データでのrank23_odds_calibration検証
信頼度別・収支・的中率の詳細分析
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
from datetime import datetime
from collections import defaultdict

DB_PATH = "data/boatrace_backup_20251212_145413.db"

def verify_2025_data():
    """2025年データでの詳細検証"""

    print("=" * 80)
    print("2025年データ検証: rank23_odds_calibration機能")
    print("=" * 80)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 2025年のオッズデータがあるレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date FROM races r
        INNER JOIN results res ON res.race_id = r.id
        INNER JOIN trifecta_odds odds ON odds.race_id = r.id
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2025-12-31'
            AND res.is_invalid = 0
        ORDER BY r.id
        LIMIT 150
    ''')
    race_data = cursor.fetchall()
    race_ids = [row[0] for row in race_data]

    if len(race_ids) == 0:
        print("[WARNING] 2025年のデータが見つかりません。")
        print("2024年データで代替検証を実施します。")
        cursor.execute('''
            SELECT DISTINCT r.id, r.race_date FROM races r
            INNER JOIN results res ON res.race_id = r.id
            INNER JOIN trifecta_odds odds ON odds.race_id = r.id
            WHERE r.race_date >= '2024-11-01' AND r.race_date < '2024-12-31'
                AND res.is_invalid = 0
            ORDER BY r.id
            LIMIT 150
        ''')
        race_data = cursor.fetchall()
        race_ids = [row[0] for row in race_data]

    print(f"[DATA] 取得レース数: {len(race_ids)}")
    print(f"[DATA] 期間: {race_data[0][1]} ～ {race_data[-1][1]}")
    print()

    # ========================================
    # ベースライン測定（機能無効）
    # ========================================
    print("[1/2] ベースライン測定（機能無効）")
    print("-" * 80)

    set_feature_flag('rank23_odds_calibration', False)
    predictor_baseline = RacePredictor(DB_PATH, use_cache=False)

    baseline_stats = {
        'total': defaultdict(int),
        'trifecta_hits': defaultdict(int),
        '1st_hits': defaultdict(int),
        'roi': defaultdict(float),
        'investment': defaultdict(int)
    }

    for i, race_id in enumerate(race_ids):
        if i % 30 == 0:
            print(f"  進捗: {i}/{len(race_ids)}", end="\r")

        try:
            predictions = predictor_baseline.predict_race(race_id, use_beforeinfo=True)
            if len(predictions) < 3:
                continue

            # 信頼度取得
            confidence = predictions[0]['confidence']
            pred_1st = predictions[0]['pit_number']
            pred_combo = f"{predictions[0]['pit_number']}-{predictions[1]['pit_number']}-{predictions[2]['pit_number']}"

            # 実際の結果とオッズを取得
            cursor.execute('''
                SELECT
                    (SELECT GROUP_CONCAT(pit_number, '-')
                     FROM (SELECT pit_number FROM results WHERE race_id = ? AND is_invalid = 0 AND rank <= 3 ORDER BY rank)) as combo,
                    (SELECT pit_number FROM results WHERE race_id = ? AND rank = 1 AND is_invalid = 0) as first,
                    (SELECT odds FROM trifecta_odds WHERE race_id = ? AND first = ? AND second = ? AND third = ? LIMIT 1) as odds
            ''', (race_id, race_id, race_id,
                  predictions[0]['pit_number'],
                  predictions[1]['pit_number'],
                  predictions[2]['pit_number']))
            row = cursor.fetchone()
            if not row or not row[0]:
                continue

            actual_combo = row[0]
            actual_1st = row[1]
            trifecta_odds = row[2] if row[2] else 0

            # 統計更新
            baseline_stats['total'][confidence] += 1
            baseline_stats['total']['ALL'] += 1
            baseline_stats['investment'][confidence] += 100  # 100円購入と仮定
            baseline_stats['investment']['ALL'] += 100

            # 三連単的中判定
            if pred_combo == actual_combo:
                baseline_stats['trifecta_hits'][confidence] += 1
                baseline_stats['trifecta_hits']['ALL'] += 1
                payout = trifecta_odds * 100 if trifecta_odds > 0 else 0
                baseline_stats['roi'][confidence] += payout
                baseline_stats['roi']['ALL'] += payout

            # 1着的中判定
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
    print("[2/2] オッズ校正測定（機能有効）")
    print("-" * 80)

    set_feature_flag('rank23_odds_calibration', True)
    predictor_calibrated = RacePredictor(DB_PATH, use_cache=False)

    calibrated_stats = {
        'total': defaultdict(int),
        'trifecta_hits': defaultdict(int),
        '1st_hits': defaultdict(int),
        'roi': defaultdict(float),
        'investment': defaultdict(int)
    }

    for i, race_id in enumerate(race_ids):
        if i % 30 == 0:
            print(f"  進捗: {i}/{len(race_ids)}", end="\r")

        try:
            predictions = predictor_calibrated.predict_race(race_id, use_beforeinfo=True)
            if len(predictions) < 3:
                continue

            # 信頼度取得
            confidence = predictions[0]['confidence']
            pred_1st = predictions[0]['pit_number']
            pred_combo = f"{predictions[0]['pit_number']}-{predictions[1]['pit_number']}-{predictions[2]['pit_number']}"

            # 実際の結果とオッズを取得
            cursor.execute('''
                SELECT
                    (SELECT GROUP_CONCAT(pit_number, '-')
                     FROM (SELECT pit_number FROM results WHERE race_id = ? AND is_invalid = 0 AND rank <= 3 ORDER BY rank)) as combo,
                    (SELECT pit_number FROM results WHERE race_id = ? AND rank = 1 AND is_invalid = 0) as first,
                    (SELECT odds FROM trifecta_odds WHERE race_id = ? AND first = ? AND second = ? AND third = ? LIMIT 1) as odds
            ''', (race_id, race_id, race_id,
                  predictions[0]['pit_number'],
                  predictions[1]['pit_number'],
                  predictions[2]['pit_number']))
            row = cursor.fetchone()
            if not row or not row[0]:
                continue

            actual_combo = row[0]
            actual_1st = row[1]
            trifecta_odds = row[2] if row[2] else 0

            # 統計更新
            calibrated_stats['total'][confidence] += 1
            calibrated_stats['total']['ALL'] += 1
            calibrated_stats['investment'][confidence] += 100
            calibrated_stats['investment']['ALL'] += 100

            # 三連単的中判定
            if pred_combo == actual_combo:
                calibrated_stats['trifecta_hits'][confidence] += 1
                calibrated_stats['trifecta_hits']['ALL'] += 1
                payout = trifecta_odds * 100 if trifecta_odds > 0 else 0
                calibrated_stats['roi'][confidence] += payout
                calibrated_stats['roi']['ALL'] += payout

            # 1着的中判定
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
    print("検証結果サマリー")
    print("=" * 80)
    print()

    # 信頼度リスト
    confidences = ['A', 'B', 'C', 'D', 'E', 'ALL']

    # 三連単的中率
    print("[1] 三連単的中率（信頼度別）")
    print("-" * 80)
    print(f"{'信頼度':<8} {'レース数':<10} {'ベースライン':<15} {'オッズ校正':<15} {'差分':<10}")
    print("-" * 80)

    for conf in confidences:
        if baseline_stats['total'][conf] == 0:
            continue

        b_rate = baseline_stats['trifecta_hits'][conf] / baseline_stats['total'][conf]
        c_rate = calibrated_stats['trifecta_hits'][conf] / calibrated_stats['total'][conf]
        diff = (c_rate - b_rate) * 100

        print(f"{conf:<8} {baseline_stats['total'][conf]:<10} "
              f"{b_rate:>6.2%} ({baseline_stats['trifecta_hits'][conf]:>3}) "
              f"{c_rate:>6.2%} ({calibrated_stats['trifecta_hits'][conf]:>3}) "
              f"{diff:>+6.2f}pt")

    print()

    # 1着的中率
    print("[2] 1着的中率（信頼度別・参考）")
    print("-" * 80)
    print(f"{'信頼度':<8} {'ベースライン':<15} {'オッズ校正':<15} {'差分':<10}")
    print("-" * 80)

    for conf in confidences:
        if baseline_stats['total'][conf] == 0:
            continue

        b_rate = baseline_stats['1st_hits'][conf] / baseline_stats['total'][conf]
        c_rate = calibrated_stats['1st_hits'][conf] / calibrated_stats['total'][conf]
        diff = (c_rate - b_rate) * 100

        print(f"{conf:<8} {b_rate:>6.2%} ({baseline_stats['1st_hits'][conf]:>3}) "
              f"{c_rate:>6.2%} ({calibrated_stats['1st_hits'][conf]:>3}) "
              f"{diff:>+6.2f}pt")

    print()

    # 収支（ROI）
    print("[3] 収支・ROI（信頼度別）")
    print("-" * 80)
    print(f"{'信頼度':<8} {'投資額':<10} {'ベースライン':<20} {'オッズ校正':<20} {'改善額':<10}")
    print("-" * 80)

    for conf in confidences:
        if baseline_stats['total'][conf] == 0:
            continue

        investment = baseline_stats['investment'][conf]
        b_return = baseline_stats['roi'][conf]
        c_return = calibrated_stats['roi'][conf]
        b_roi = (b_return - investment) / investment * 100 if investment > 0 else 0
        c_roi = (c_return - investment) / investment * 100 if investment > 0 else 0
        improvement = c_return - b_return

        print(f"{conf:<8} ¥{investment:<9,} "
              f"{b_roi:>+6.1f}% (¥{b_return:>7,.0f}) "
              f"{c_roi:>+6.1f}% (¥{c_return:>7,.0f}) "
              f"¥{improvement:>+8,.0f}")

    print()
    print("=" * 80)

    # 総合判定
    all_b_rate = baseline_stats['trifecta_hits']['ALL'] / baseline_stats['total']['ALL']
    all_c_rate = calibrated_stats['trifecta_hits']['ALL'] / calibrated_stats['total']['ALL']
    all_diff = (all_c_rate - all_b_rate) * 100

    all_investment = baseline_stats['investment']['ALL']
    all_b_roi = (baseline_stats['roi']['ALL'] - all_investment) / all_investment * 100
    all_c_roi = (calibrated_stats['roi']['ALL'] - all_investment) / all_investment * 100
    roi_improvement = all_c_roi - all_b_roi

    print()
    print("[総合判定]")
    print(f"  三連単的中率: {all_b_rate:.2%} → {all_c_rate:.2%} ({all_diff:+.2f}pt)")
    print(f"  ROI:          {all_b_roi:+.1f}% → {all_c_roi:+.1f}% ({roi_improvement:+.1f}pt)")
    print()

    if all_diff > 1.0 and roi_improvement > 0:
        print("  [EXCELLENT] 的中率・ROI共に大幅改善")
    elif all_diff > 0.5 or roi_improvement > 5:
        print("  [GOOD] 改善効果あり")
    elif all_diff > -0.5 and roi_improvement > -5:
        print("  [NEUTRAL] 効果微小")
    else:
        print("  [NG] 悪化")

    print("=" * 80)

    conn.close()

if __name__ == "__main__":
    verify_2025_data()
