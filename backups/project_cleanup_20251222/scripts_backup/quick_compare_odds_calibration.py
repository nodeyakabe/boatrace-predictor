#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
rank23_odds_calibration 高速検証（2025年データ）
================================================

高速化のポイント:
1. RacePredictorを1回だけ初期化
2. feature_flagを動的に切り替え
3. 三連単的中率を測定
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings
warnings.filterwarnings('ignore')

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag
import sqlite3

DB_PATH = "data/boatrace_backup_20251212_145413.db"

def quick_test(num_races=100):
    """2025年データでのrank23検証"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 2025年レース取得
    cursor.execute('''
        SELECT DISTINCT r.id FROM races r
        INNER JOIN results res ON res.race_id = r.id
        INNER JOIN trifecta_odds odds ON odds.race_id = r.id
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2025-12-31'
            AND res.is_invalid = 0
        ORDER BY r.id LIMIT ?
    ''', (num_races,))
    race_ids = [row[0] for row in cursor.fetchall()]

    print(f"2025年データ rank23検証: {len(race_ids)}レース")
    print("=" * 80)

    # Predictor初期化（1回のみ！）
    print("\n[INIT] RacePredictor初期化中...")
    predictor = RacePredictor(DB_PATH, use_cache=False)
    print("[INIT] 完了\n")

    # ========================================
    # ベースライン測定（機能無効）
    # ========================================
    print("[1/2] ベースライン測定（rank23_odds_calibration: False）")
    print("-" * 80)
    set_feature_flag('rank23_odds_calibration', False)

    b_trifecta_ok, b_trifecta_tot = 0, 0
    b_1st_ok, b_1st_tot = 0, 0

    for i, rid in enumerate(race_ids):
        if i % 20 == 0:
            print(f"  進捗: {i}/{len(race_ids)}", flush=True)
        try:
            preds = predictor.predict_race(rid, use_beforeinfo=True)
            if len(preds) < 3:
                continue

            pred_combo = f"{preds[0]['pit_number']}-{preds[1]['pit_number']}-{preds[2]['pit_number']}"
            pred_1st = preds[0]['pit_number']

            cursor.execute('''
                SELECT GROUP_CONCAT(pit_number, '-') as combo,
                       (SELECT pit_number FROM results WHERE race_id = ? AND rank = 1 AND is_invalid = 0) as first
                FROM (SELECT pit_number FROM results WHERE race_id = ? AND is_invalid = 0 AND rank <= 3 ORDER BY rank)
            ''', (rid, rid))
            r = cursor.fetchone()
            if not r or not r[0]:
                continue

            b_trifecta_tot += 1
            if pred_combo == r[0]:
                b_trifecta_ok += 1

            b_1st_tot += 1
            if pred_1st == r[1]:
                b_1st_ok += 1
        except:
            pass

    b_trifecta_rate = b_trifecta_ok / b_trifecta_tot if b_trifecta_tot > 0 else 0
    b_1st_rate = b_1st_ok / b_1st_tot if b_1st_tot > 0 else 0
    print(f"  完了: {len(race_ids)}/{len(race_ids)}")
    print(f"  三連単: {b_trifecta_rate:.4%} ({b_trifecta_ok}/{b_trifecta_tot})")
    print(f"  1着:    {b_1st_rate:.4%} ({b_1st_ok}/{b_1st_tot})")
    print()

    # ========================================
    # オッズ校正測定（機能有効）
    # ========================================
    print("[2/2] オッズ校正測定（rank23_odds_calibration: True）")
    print("-" * 80)
    set_feature_flag('rank23_odds_calibration', True)

    c_trifecta_ok, c_trifecta_tot = 0, 0
    c_1st_ok, c_1st_tot = 0, 0

    for i, rid in enumerate(race_ids):
        if i % 20 == 0:
            print(f"  進捗: {i}/{len(race_ids)}", flush=True)
        try:
            preds = predictor.predict_race(rid, use_beforeinfo=True)
            if len(preds) < 3:
                continue

            pred_combo = f"{preds[0]['pit_number']}-{preds[1]['pit_number']}-{preds[2]['pit_number']}"
            pred_1st = preds[0]['pit_number']

            cursor.execute('''
                SELECT GROUP_CONCAT(pit_number, '-') as combo,
                       (SELECT pit_number FROM results WHERE race_id = ? AND rank = 1 AND is_invalid = 0) as first
                FROM (SELECT pit_number FROM results WHERE race_id = ? AND is_invalid = 0 AND rank <= 3 ORDER BY rank)
            ''', (rid, rid))
            r = cursor.fetchone()
            if not r or not r[0]:
                continue

            c_trifecta_tot += 1
            if pred_combo == r[0]:
                c_trifecta_ok += 1

            c_1st_tot += 1
            if pred_1st == r[1]:
                c_1st_ok += 1
        except:
            pass

    c_trifecta_rate = c_trifecta_ok / c_trifecta_tot if c_trifecta_tot > 0 else 0
    c_1st_rate = c_1st_ok / c_1st_tot if c_1st_tot > 0 else 0
    print(f"  完了: {len(race_ids)}/{len(race_ids)}")
    print(f"  三連単: {c_trifecta_rate:.4%} ({c_trifecta_ok}/{c_trifecta_tot})")
    print(f"  1着:    {c_1st_rate:.4%} ({c_1st_ok}/{c_1st_tot})")
    print()

    # ========================================
    # 結果サマリー
    # ========================================
    diff_trifecta = (c_trifecta_rate - b_trifecta_rate) * 100
    diff_1st = (c_1st_rate - b_1st_rate) * 100

    print("=" * 80)
    print("2025年検証結果サマリー")
    print("=" * 80)
    print(f"検証レース数:           {b_trifecta_tot}")
    print()
    print("[三連単的中率]")
    print(f"  ベースライン:         {b_trifecta_rate:.4%}")
    print(f"  オッズ校正:           {c_trifecta_rate:.4%}")
    print(f"  差分:                 {diff_trifecta:+.2f}pt")
    print()
    print("[1着的中率（参考）]")
    print(f"  ベースライン:         {b_1st_rate:.4%}")
    print(f"  オッズ校正:           {c_1st_rate:.4%}")
    print(f"  差分:                 {diff_1st:+.2f}pt")
    print("=" * 80)
    print()

    # 2024年結果との比較
    print("【参考】2024年データでの検証結果")
    print("  三連単的中率: 12.24% → 14.29% (+2.04pt)")
    print()
    print("【今回】2025年データでの検証結果")
    print(f"  三連単的中率: {b_trifecta_rate:.2%} → {c_trifecta_rate:.2%} ({diff_trifecta:+.2f}pt)")
    print()

    # 判定
    if diff_trifecta > 1.5:
        status = "[EXCELLENT]"
        action = "機能継続使用"
    elif diff_trifecta > 0.5:
        status = "[GOOD]"
        action = "継続モニタリング"
    elif diff_trifecta > -0.5:
        status = "[NEUTRAL]"
        action = "パラメータ調整検討"
    else:
        status = "[NG]"
        action = "機能無効化を推奨"

    print(f"判定: {status} {diff_trifecta:+.2f}pt")
    print(f"推奨: {action}")
    print("=" * 80)

    conn.close()
    set_feature_flag('rank23_odds_calibration', True)

if __name__ == "__main__":
    import sys
    num_races = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    quick_test(num_races)
