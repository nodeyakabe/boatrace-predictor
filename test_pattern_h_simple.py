#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""パターンH判定ロジックの簡易テスト"""

# テストケース: 手動で構築したレースデータ
from src.betting.evaluator_helpers import create_standard_evaluator

# Evaluator作成
evaluator = create_standard_evaluator()

# テストレースデータ（仮想）
race_data = {
    'id': 'test001',
    'venue_code': '07',  # 蒲郡（B×50-100の会場）
    'race_number': 10,
    'race_date': '2024-06-01',
    'race_time': '15:00',
    'wind_speed': 2.0,
    'entries': [
        {'pit_number': 1, 'racer_number': '1001', 'racer_rank': 'A1', 'motor_second_rate': 45.0, 'second_rate': 50.0},
        {'pit_number': 2, 'racer_number': '1002', 'racer_rank': 'A1', 'motor_second_rate': 40.0, 'second_rate': 48.0},
        {'pit_number': 3, 'racer_number': '1003', 'racer_rank': 'A2', 'motor_second_rate': 38.0, 'second_rate': 45.0},
        {'pit_number': 4, 'racer_number': '1004', 'racer_rank': 'B1', 'motor_second_rate': 35.0, 'second_rate': 42.0},
        {'pit_number': 5, 'racer_number': '1005', 'racer_rank': 'B1', 'motor_second_rate': 33.0, 'second_rate': 40.0},
        {'pit_number': 6, 'racer_number': '1006', 'racer_rank': 'B2', 'motor_second_rate': 30.0, 'second_rate': 38.0},
    ]
}

# 予測データ
predictions = {
    'confidence': 'B',
    'old_prediction': [3, 1, 2, 4, 5, 6],  # 3-1-2-4-5-6
    'new_prediction': [3, 1, 2, 4, 5, 6]
}

# オッズデータ（パターンH用に3点）
odds_data = {
    '3-1-2': 55.0,  # 1-2-3: 範囲内（50-100）
    '3-1-4': 70.0,  # 1-2-4: 範囲内
    '3-1-5': 40.0,  # 1-2-5: 範囲外（50未満）
}

print("=" * 80)
print("パターンH判定ロジック簡易テスト")
print("=" * 80)
print()
print(f"レース: 蒲郡 R10")
print(f"信頼度: {predictions['confidence']}")
print(f"予測順位: {predictions['old_prediction']}")
print(f"オッズ:")
print(f"  3-1-2: {odds_data.get('3-1-2', 'なし')}倍")
print(f"  3-1-4: {odds_data.get('3-1-4', 'なし')}倍")
print(f"  3-1-5: {odds_data.get('3-1-5', 'なし')}倍")
print()

# BetTargetEvaluator評価
try:
    bet_target = evaluator.evaluate_race(
        race_data=race_data,
        predictions=predictions,
        odds_data=odds_data,
        has_beforeinfo=True
    )

    print("[評価結果]")
    print(f"  判定: {bet_target.status.value}")
    print(f"  買い目: {bet_target.combination}")
    print(f"  オッズ: {bet_target.odds}倍")
    print(f"  理由: {bet_target.reason}")
    print(f"  パターンH: {bet_target.use_pattern_h}")
    print()

    if bet_target.use_pattern_h:
        print("[期待動作]")
        print("  [OK] パターンH=Trueで、3点（3-1-2, 3-1-4, 3-1-5）をチェック")
        print("  [OK] 3-1-2（55倍）と3-1-4（70倍）が範囲内（50-100倍）")
        print("  [OK] 最もオッズが高い3-1-4（70倍）を選択")
        print()

        if bet_target.combination == '3-1-4' and bet_target.odds == 70.0:
            print("[SUCCESS] テスト成功: パターンH判定ロジックが正しく動作しています")
        else:
            print("[FAIL] テスト失敗: 期待する買い目（3-1-4）とオッズ（70倍）が一致しません")
            print(f"  実際: 買い目={bet_target.combination}, オッズ={bet_target.odds}")
    else:
        print("[FAIL] テスト失敗: パターンHが適用されていません（use_pattern_h=False）")

except Exception as e:
    print(f"[ERROR] エラー発生: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)
