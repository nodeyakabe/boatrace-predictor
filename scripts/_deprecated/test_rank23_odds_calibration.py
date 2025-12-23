#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""2着・3着オッズ校正機能のテスト"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# 警告を抑制
import warnings
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

from src.analysis.scorers.odds_calibrator import OddsCalibrator
from src.analysis.race_predictor import RacePredictor
import sqlite3

DB_PATH = "data/boatrace_backup_20251212_145413.db"

def test_rank23_calibration():
    """2着・3着オッズ校正のテスト"""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # オッズデータがあるレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id FROM races r
        INNER JOIN results res ON res.race_id = r.id
        INNER JOIN trifecta_odds odds ON odds.race_id = r.id
        WHERE r.race_date >= '2024-01-01' AND r.race_date < '2024-01-10'
            AND res.is_invalid = 0
        ORDER BY r.id LIMIT 1
    ''')
    race_id = cursor.fetchone()[0]

    print(f"テストレースID: {race_id}")
    print("=" * 70)

    # 予測を取得
    predictor = RacePredictor(DB_PATH, use_cache=False)
    predictions = predictor.predict_race(race_id, use_beforeinfo=True)

    print("\n[BEFORE] オッズ校正前の予測:")
    print("-" * 70)
    for i, pred in enumerate(predictions[:3], 1):
        print(f"{i}位: 艇{pred['pit_number']} - スコア{pred['total_score']:.1f}")

    # 2着・3着オッズ校正を適用
    calibrator = OddsCalibrator(DB_PATH, alpha=0.5, temperature=4.0, rank23_alpha=0.3)
    calibrated_predictions = calibrator.calibrate_rank23_predictions(predictions, race_id, alpha=0.3)

    print("\n[AFTER] 2着・3着オッズ校正後:")
    print("-" * 70)
    for i, pred in enumerate(calibrated_predictions[:3], 1):
        if pred.get('rank23_calibrated'):
            market_prob = pred.get('market_second_prob', 0)
            ml_prob = pred.get('ml_second_prob', 0)
            integrated_prob = pred.get('integrated_second_prob', 0)
            adjustment = pred.get('rank23_adjustment', 1.0)

            print(f"{i}位: 艇{pred['pit_number']} - スコア{pred['total_score']:.1f}")
            if i > 1:  # 2着以降
                print(f"     市場2着確率: {market_prob:.3f}")
                print(f"     ML2着確率:   {ml_prob:.3f}")
                print(f"     統合確率:     {integrated_prob:.3f}")
                print(f"     調整係数:     {adjustment:.3f}x")
        else:
            print(f"{i}位: 艇{pred['pit_number']} - スコア{pred['total_score']:.1f} (校正なし)")

    # 実際の結果を取得
    cursor.execute('''
        SELECT pit_number, rank FROM results
        WHERE race_id = ? AND is_invalid = 0
        ORDER BY rank
    ''', (race_id,))
    actual_results = cursor.fetchall()

    print("\n[ACTUAL] 実際の結果:")
    print("-" * 70)
    for pit, rank in actual_results[:3]:
        print(f"{rank}着: 艇{pit}")

    # 最適3連単組み合わせを取得
    print("\n[OPTIMAL] 最適3連単組み合わせ（期待値順）:")
    print("-" * 70)
    optimal_combos = calibrator.get_optimal_trifecta_combinations(
        predictions, race_id, top_n=5
    )

    for i, combo_info in enumerate(optimal_combos, 1):
        print(f"{i}. {combo_info['combination']}: "
              f"EV={combo_info['ev']:.3f}, "
              f"オッズ={combo_info['odds']:.1f}, "
              f"統合確率={combo_info['prob']:.4f}")

    conn.close()

    print("\n" + "=" * 70)
    print("2着・3着オッズ校正機能のテスト完了")

if __name__ == "__main__":
    test_rank23_calibration()
