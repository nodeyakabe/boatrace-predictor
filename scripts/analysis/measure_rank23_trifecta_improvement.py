#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""2着・3着オッズ校正による三連単的中率改善測定"""

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

def measure_trifecta_improvement(num_races=50):
    """三連単的中率の改善効果を測定"""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # オッズデータがあるレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id FROM races r
        INNER JOIN results res ON res.race_id = r.id
        INNER JOIN trifecta_odds odds ON odds.race_id = r.id
        WHERE r.race_date >= '2024-01-01' AND r.race_date < '2024-02-01'
            AND res.is_invalid = 0
        ORDER BY r.id LIMIT ?
    ''', (num_races,))
    race_ids = [row[0] for row in cursor.fetchall()]

    print(f"三連単的中率測定: {len(race_ids)}レース")
    print("=" * 70)

    predictor = RacePredictor(DB_PATH, use_cache=False)
    calibrator = OddsCalibrator(DB_PATH, alpha=0.5, temperature=4.0, rank23_alpha=0.3)

    # ベースライン（オッズ校正なし）
    print("\n[1/2] ベースライン測定（機械学習のみ）...")
    baseline_hits = 0
    baseline_total = 0

    for i, race_id in enumerate(race_ids):
        if i % 10 == 0:
            print(f"  進捗: {i}/{len(race_ids)}")

        try:
            # 予測
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)
            if len(predictions) < 3:
                continue

            # 予測トップ3
            pred_combo = f"{predictions[0]['pit_number']}-{predictions[1]['pit_number']}-{predictions[2]['pit_number']}"

            # 実際の結果
            cursor.execute('''
                SELECT GROUP_CONCAT(pit_number, '-') as actual_combo
                FROM (
                    SELECT pit_number FROM results
                    WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                    ORDER BY rank
                )
            ''', (race_id,))
            row = cursor.fetchone()
            if not row or not row[0]:
                continue

            actual_combo = row[0]
            baseline_total += 1

            if pred_combo == actual_combo:
                baseline_hits += 1

        except:
            pass

    baseline_rate = baseline_hits / baseline_total if baseline_total > 0 else 0
    print(f"  完了: {baseline_rate:.2%} ({baseline_hits}/{baseline_total})")

    # オッズ校正あり
    print("\n[2/2] オッズ校正測定（2着・3着統合）...")
    calibrated_hits = 0
    calibrated_total = 0

    for i, race_id in enumerate(race_ids):
        if i % 10 == 0:
            print(f"  進捗: {i}/{len(race_ids)}")

        try:
            # 予測
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)
            if len(predictions) < 3:
                continue

            # 2着・3着オッズ校正を適用
            calibrated_predictions = calibrator.calibrate_rank23_predictions(
                predictions, race_id, alpha=0.3
            )

            if len(calibrated_predictions) < 3:
                continue

            # 予測トップ3
            pred_combo = f"{calibrated_predictions[0]['pit_number']}-{calibrated_predictions[1]['pit_number']}-{calibrated_predictions[2]['pit_number']}"

            # 実際の結果
            cursor.execute('''
                SELECT GROUP_CONCAT(pit_number, '-') as actual_combo
                FROM (
                    SELECT pit_number FROM results
                    WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                    ORDER BY rank
                )
            ''', (race_id,))
            row = cursor.fetchone()
            if not row or not row[0]:
                continue

            actual_combo = row[0]
            calibrated_total += 1

            if pred_combo == actual_combo:
                calibrated_hits += 1

        except:
            pass

    calibrated_rate = calibrated_hits / calibrated_total if calibrated_total > 0 else 0
    diff = (calibrated_rate - baseline_rate) * 100

    print(f"  完了: {calibrated_rate:.2%} ({calibrated_hits}/{calibrated_total})")

    print()
    print("=" * 70)
    print("結果サマリー")
    print("=" * 70)
    print(f"サンプル数:             {baseline_total}レース")
    print(f"ベースライン（MLのみ）: {baseline_rate:.4%}")
    print(f"オッズ校正（統合）:     {calibrated_rate:.4%}")
    print(f"差分:                   {diff:+.2f}pt")
    print("=" * 70)

    if diff > 0.5:
        print("\n[GOOD] 改善効果あり！2着・3着オッズ統合は有効")
    elif diff > -0.5:
        print("\n[NEUTRAL] 効果微小")
    else:
        print("\n[WARN] 悪化")

    conn.close()

if __name__ == "__main__":
    measure_trifecta_improvement(50)
