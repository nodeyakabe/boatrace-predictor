#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2着・3着オッズ校正の大規模検証（200レース）
===========================================

検証日: 2025-12-18
目的: rank23_odds_calibration機能の本番投入判断
期待効果: 三連単的中率 +2.0pt
"""

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
from config.feature_flags import set_feature_flag
import sqlite3
from datetime import datetime

DB_PATH = "data/boatrace_backup_20251212_145413.db"

def large_scale_verification(num_races=200):
    """大規模検証"""

    print("=" * 80)
    print("2着・3着オッズ校正 大規模検証")
    print("=" * 80)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"検証レース数: {num_races}")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # オッズデータがあるレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id FROM races r
        INNER JOIN results res ON res.race_id = r.id
        INNER JOIN trifecta_odds odds ON odds.race_id = r.id
        WHERE r.race_date >= '2024-01-01' AND r.race_date < '2024-03-01'
            AND res.is_invalid = 0
        ORDER BY r.id LIMIT ?
    ''', (num_races,))
    race_ids = [row[0] for row in cursor.fetchall()]

    print(f"[DATA] 取得レース数: {len(race_ids)}")
    print()

    predictor = RacePredictor(DB_PATH, use_cache=False)
    calibrator = OddsCalibrator(DB_PATH, alpha=0.5, temperature=4.0, rank23_alpha=0.3)

    # ========================================
    # ベースライン測定（機械学習のみ）
    # ========================================
    print("[1/2] ベースライン測定（機械学習のみ）")
    print("-" * 80)

    baseline_hits = 0
    baseline_total = 0
    baseline_1st_hits = 0  # 1着的中数
    baseline_1st_total = 0

    for i, race_id in enumerate(race_ids):
        if i % 50 == 0:
            print(f"  進捗: {i}/{len(race_ids)} ({i/len(race_ids)*100:.1f}%)")

        try:
            # 予測
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)
            if len(predictions) < 3:
                continue

            # 予測トップ3
            pred_1st = predictions[0]['pit_number']
            pred_combo = f"{predictions[0]['pit_number']}-{predictions[1]['pit_number']}-{predictions[2]['pit_number']}"

            # 実際の結果
            cursor.execute('''
                SELECT GROUP_CONCAT(pit_number, '-') as actual_combo,
                       (SELECT pit_number FROM results WHERE race_id = ? AND rank = 1 AND is_invalid = 0) as actual_1st
                FROM (
                    SELECT pit_number FROM results
                    WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                    ORDER BY rank
                )
            ''', (race_id, race_id))
            row = cursor.fetchone()
            if not row or not row[0]:
                continue

            actual_combo = row[0]
            actual_1st = row[1]

            # 三連単
            baseline_total += 1
            if pred_combo == actual_combo:
                baseline_hits += 1

            # 1着のみ
            baseline_1st_total += 1
            if pred_1st == actual_1st:
                baseline_1st_hits += 1

        except Exception as e:
            pass

    baseline_rate = baseline_hits / baseline_total if baseline_total > 0 else 0
    baseline_1st_rate = baseline_1st_hits / baseline_1st_total if baseline_1st_total > 0 else 0

    print(f"  完了: {len(race_ids)}/{len(race_ids)}")
    print(f"  三連単的中率: {baseline_rate:.4%} ({baseline_hits}/{baseline_total})")
    print(f"  1着的中率:    {baseline_1st_rate:.4%} ({baseline_1st_hits}/{baseline_1st_total})")
    print()

    # ========================================
    # オッズ校正適用（2着・3着統合）
    # ========================================
    print("[2/2] オッズ校正測定（2着・3着統合）")
    print("-" * 80)

    calibrated_hits = 0
    calibrated_total = 0
    calibrated_1st_hits = 0  # 1着的中数（変化なしのはず）
    calibrated_1st_total = 0

    for i, race_id in enumerate(race_ids):
        if i % 50 == 0:
            print(f"  進捗: {i}/{len(race_ids)} ({i/len(race_ids)*100:.1f}%)")

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
            pred_1st = calibrated_predictions[0]['pit_number']
            pred_combo = f"{calibrated_predictions[0]['pit_number']}-{calibrated_predictions[1]['pit_number']}-{calibrated_predictions[2]['pit_number']}"

            # 実際の結果
            cursor.execute('''
                SELECT GROUP_CONCAT(pit_number, '-') as actual_combo,
                       (SELECT pit_number FROM results WHERE race_id = ? AND rank = 1 AND is_invalid = 0) as actual_1st
                FROM (
                    SELECT pit_number FROM results
                    WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                    ORDER BY rank
                )
            ''', (race_id, race_id))
            row = cursor.fetchone()
            if not row or not row[0]:
                continue

            actual_combo = row[0]
            actual_1st = row[1]

            # 三連単
            calibrated_total += 1
            if pred_combo == actual_combo:
                calibrated_hits += 1

            # 1着のみ
            calibrated_1st_total += 1
            if pred_1st == actual_1st:
                calibrated_1st_hits += 1

        except Exception as e:
            pass

    calibrated_rate = calibrated_hits / calibrated_total if calibrated_total > 0 else 0
    calibrated_1st_rate = calibrated_1st_hits / calibrated_1st_total if calibrated_1st_total > 0 else 0

    print(f"  完了: {len(race_ids)}/{len(race_ids)}")
    print(f"  三連単的中率: {calibrated_rate:.4%} ({calibrated_hits}/{calibrated_total})")
    print(f"  1着的中率:    {calibrated_1st_rate:.4%} ({calibrated_1st_hits}/{calibrated_1st_total})")
    print()

    # ========================================
    # 結果サマリー
    # ========================================
    diff_trifecta = (calibrated_rate - baseline_rate) * 100
    diff_1st = (calibrated_1st_rate - baseline_1st_rate) * 100

    print("=" * 80)
    print("結果サマリー")
    print("=" * 80)
    print(f"検証レース数:           {baseline_total}")
    print()
    print("[三連単的中率]")
    print(f"  ベースライン（ML）:   {baseline_rate:.4%}")
    print(f"  オッズ統合:           {calibrated_rate:.4%}")
    print(f"  差分:                 {diff_trifecta:+.2f}pt")
    print()
    print("[1着的中率（参考）]")
    print(f"  ベースライン:         {baseline_1st_rate:.4%}")
    print(f"  オッズ統合:           {calibrated_1st_rate:.4%}")
    print(f"  差分:                 {diff_1st:+.2f}pt （変化なしが期待値）")
    print("=" * 80)
    print()

    # 判定
    if diff_trifecta > 1.5:
        status = "[EXCELLENT] 大幅改善（+1.5pt以上）"
        action = "→ 機能フラグを有効化して本番投入を推奨"
    elif diff_trifecta > 0.5:
        status = "[GOOD] 改善効果あり（+0.5pt以上）"
        action = "→ 500レースでの追加検証後、本番投入を検討"
    elif diff_trifecta > -0.5:
        status = "[NEUTRAL] 効果微小（±0.5pt以内）"
        action = "→ パラメータ調整を検討"
    else:
        status = "[NG] 悪化"
        action = "→ 実装見直しが必要"

    print(f"判定: {status}")
    print(f"推奨アクション: {action}")
    print()
    print("=" * 80)

    conn.close()

if __name__ == "__main__":
    large_scale_verification(200)
