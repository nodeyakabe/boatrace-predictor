# -*- coding: utf-8 -*-
"""状態フラグ調整のテスト

1レースで状態フラグの動作を確認
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor
from src.analysis.beforeinfo_flag_adjuster import BeforeInfoFlagAdjuster


def test_flag_adjuster():
    """状態フラグ調整のテスト"""
    db_path = ROOT_DIR / "data" / "boatrace.db"

    # 2025年の直前情報付きレースを1件取得
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date, r.race_number
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        AND rd.exhibition_time IS NOT NULL
        ORDER BY r.race_date, r.race_number
        LIMIT 1
    ''')
    race = cursor.fetchone()

    if not race:
        print("テスト対象レースが見つかりません")
        return

    race_id = race['id']
    race_date = race['race_date']
    race_number = race['race_number']

    print("=" * 80)
    print(f"テスト対象: {race_date} {race_number}R (race_id: {race_id})")
    print("=" * 80)
    print()

    # 状態フラグ調整を直接テスト
    adjuster = BeforeInfoFlagAdjuster(db_path)

    print("【各艇の状態フラグと調整係数】")
    print()

    for pit in range(1, 7):
        adjustment = adjuster.calculate_adjustment_factors(race_id, pit)

        print(f"{pit}号艇:")
        print(f"  スコア係数: {adjustment['score_multiplier']:.3f}")
        print(f"  信頼度係数: {adjustment['confidence_multiplier']:.3f}")
        print(f"  フラグ:")
        for flag_name, flag_value in adjustment['flags'].items():
            if flag_value:
                print(f"    - {flag_name}: {flag_value}")
        if adjustment['reasons']:
            print(f"  調整理由:")
            for reason in adjustment['reasons']:
                print(f"    - {reason}")
        print()

    # RacePredictorでの予測テスト
    print("=" * 80)
    print("【RacePredictorでの予測結果】")
    print("=" * 80)
    print()

    # BEFORE無効で予測
    from config.feature_flags import FEATURE_FLAGS
    original_flag = FEATURE_FLAGS['beforeinfo_flag_adjustment']
    FEATURE_FLAGS['beforeinfo_flag_adjustment'] = False

    predictor_without = RacePredictor(db_path, use_cache=False)
    predictions_without = predictor_without.predict_race(race_id)

    # BEFORE有効で予測
    FEATURE_FLAGS['beforeinfo_flag_adjustment'] = True

    predictor_with = RacePredictor(db_path, use_cache=False)
    predictions_with = predictor_with.predict_race(race_id)

    FEATURE_FLAGS['beforeinfo_flag_adjustment'] = original_flag

    # 比較表示
    print("状態フラグ無効:")
    for i, pred in enumerate(predictions_without[:6], 1):
        print(f"{i}位: {pred['pit_number']}号艇 (スコア: {pred['total_score']:.1f})")

    print()
    print("状態フラグ有効:")
    for i, pred in enumerate(predictions_with[:6], 1):
        pit = pred['pit_number']
        score = pred['total_score']
        mode = pred.get('integration_mode', 'unknown')
        reasons = pred.get('beforeinfo_reasons', [])

        reason_str = ', '.join(reasons) if reasons else 'なし'
        print(f"{i}位: {pit}号艇 (スコア: {score:.1f}, 調整: {reason_str})")

    print()

    # 順位変動を確認
    rank_without = {pred['pit_number']: i+1 for i, pred in enumerate(predictions_without)}
    rank_with = {pred['pit_number']: i+1 for i, pred in enumerate(predictions_with)}

    print("順位変動:")
    for pit in range(1, 7):
        before = rank_without[pit]
        after = rank_with[pit]
        if before != after:
            print(f"  {pit}号艇: {before}位 → {after}位")

    print()

    # 実際の結果を表示
    cursor.execute('''
        SELECT pit_number, rank
        FROM results
        WHERE race_id = ? AND is_invalid = 0
        ORDER BY rank
    ''', (race_id,))
    results = cursor.fetchall()

    print("実際の結果:")
    for result in results:
        pit = result['pit_number']
        rank = result['rank']
        print(f"  {rank}着: {pit}号艇")

    conn.close()

    print()
    print("=" * 80)


if __name__ == '__main__':
    test_flag_adjuster()
