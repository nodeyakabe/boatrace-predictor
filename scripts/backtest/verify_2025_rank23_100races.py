#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2025年データでのrank23_odds_calibration検証（100レース）
========================================================

検証日: 2025-12-18
目的: 2025年データでの効果確認
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

DB_PATH = "data/boatrace_backup_20251212_145413.db"

def verify_2025_data(num_races=100):
    """2025年データでの検証"""

    print("=" * 80)
    print("2025年データ rank23_odds_calibration検証")
    print("=" * 80)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"検証レース数: {num_races}")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 2025年オッズデータがあるレースを取得
    cursor.execute('''
        SELECT DISTINCT r.id FROM races r
        INNER JOIN results res ON res.race_id = r.id
        INNER JOIN trifecta_odds odds ON odds.race_id = r.id
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2025-12-31'
            AND res.is_invalid = 0
        ORDER BY r.id LIMIT ?
    ''', (num_races,))
    race_ids = [row[0] for row in cursor.fetchall()]

    print(f"[DATA] 取得レース数: {len(race_ids)}")
    print()

    # ========================================
    # ベースライン測定（機能無効）
    # ========================================
    print("[1/2] ベースライン測定（機能無効）")
    print("-" * 80)

    set_feature_flag('rank23_odds_calibration', False)
    predictor_baseline = RacePredictor(DB_PATH, use_cache=False)

    baseline_trifecta_hits = 0
    baseline_trifecta_total = 0
    baseline_1st_hits = 0
    baseline_1st_total = 0

    for i, race_id in enumerate(race_ids):
        if i % 25 == 0:
            print(f"  進捗: {i}/{len(race_ids)}", end="\r")

        try:
            predictions = predictor_baseline.predict_race(race_id, use_beforeinfo=True)
            if len(predictions) < 3:
                continue

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

            baseline_trifecta_total += 1
            if pred_combo == row[0]:
                baseline_trifecta_hits += 1

            baseline_1st_total += 1
            if pred_1st == row[1]:
                baseline_1st_hits += 1

        except:
            pass

    baseline_trifecta_rate = baseline_trifecta_hits / baseline_trifecta_total if baseline_trifecta_total > 0 else 0
    baseline_1st_rate = baseline_1st_hits / baseline_1st_total if baseline_1st_total > 0 else 0

    print(f"  完了: {len(race_ids)}/{len(race_ids)}")
    print(f"  三連単的中率: {baseline_trifecta_rate:.4%} ({baseline_trifecta_hits}/{baseline_trifecta_total})")
    print(f"  1着的中率:    {baseline_1st_rate:.4%} ({baseline_1st_hits}/{baseline_1st_total})")
    print()

    # ========================================
    # 本番測定（機能有効）
    # ========================================
    print("[2/2] 本番測定（機能有効）")
    print("-" * 80)

    set_feature_flag('rank23_odds_calibration', True)
    predictor_production = RacePredictor(DB_PATH, use_cache=False)

    production_trifecta_hits = 0
    production_trifecta_total = 0
    production_1st_hits = 0
    production_1st_total = 0

    for i, race_id in enumerate(race_ids):
        if i % 25 == 0:
            print(f"  進捗: {i}/{len(race_ids)}", end="\r")

        try:
            predictions = predictor_production.predict_race(race_id, use_beforeinfo=True)
            if len(predictions) < 3:
                continue

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

            production_trifecta_total += 1
            if pred_combo == row[0]:
                production_trifecta_hits += 1

            production_1st_total += 1
            if pred_1st == row[1]:
                production_1st_hits += 1

        except:
            pass

    production_trifecta_rate = production_trifecta_hits / production_trifecta_total if production_trifecta_total > 0 else 0
    production_1st_rate = production_1st_hits / production_1st_total if production_1st_total > 0 else 0

    print(f"  完了: {len(race_ids)}/{len(race_ids)}")
    print(f"  三連単的中率: {production_trifecta_rate:.4%} ({production_trifecta_hits}/{production_trifecta_total})")
    print(f"  1着的中率:    {production_1st_rate:.4%} ({production_1st_hits}/{production_1st_total})")
    print()

    # ========================================
    # 結果サマリー
    # ========================================
    diff_trifecta = (production_trifecta_rate - baseline_trifecta_rate) * 100
    diff_1st = (production_1st_rate - baseline_1st_rate) * 100

    print("=" * 80)
    print("2025年検証結果サマリー")
    print("=" * 80)
    print(f"検証レース数:           {baseline_trifecta_total}")
    print()
    print("[三連単的中率]")
    print(f"  ベースライン:         {baseline_trifecta_rate:.4%}")
    print(f"  本番（機能有効）:     {production_trifecta_rate:.4%}")
    print(f"  差分:                 {diff_trifecta:+.2f}pt")
    print()
    print("[1着的中率（参考）]")
    print(f"  ベースライン:         {baseline_1st_rate:.4%}")
    print(f"  本番（機能有効）:     {production_1st_rate:.4%}")
    print(f"  差分:                 {diff_1st:+.2f}pt")
    print("=" * 80)
    print()

    # 2024年結果との比較
    print("【参考】2024年データでの検証結果")
    print("  三連単的中率: 12.24% → 14.29% (+2.04pt)")
    print()
    print("【今回】2025年データでの検証結果")
    print(f"  三連単的中率: {baseline_trifecta_rate:.2%} → {production_trifecta_rate:.2%} ({diff_trifecta:+.2f}pt)")
    print()

    # 判定
    if diff_trifecta > 1.5:
        status = "[EXCELLENT] 2025年でも効果あり"
        action = "→ 機能を継続使用"
    elif diff_trifecta > 0.5:
        status = "[GOOD] 改善効果あり"
        action = "→ 継続モニタリング"
    elif diff_trifecta > -0.5:
        status = "[NEUTRAL] 効果微小"
        action = "→ パラメータ調整を検討"
    else:
        status = "[NG] 2025年では効果なし"
        action = "→ 原因調査が必要"

    print(f"判定: {status}")
    print(f"推奨アクション: {action}")
    print()
    print("=" * 80)

    conn.close()

    # 最終的に機能を有効に戻す
    set_feature_flag('rank23_odds_calibration', True)

if __name__ == "__main__":
    verify_2025_data(100)
