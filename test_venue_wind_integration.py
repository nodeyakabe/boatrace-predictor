#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
風速・会場フィルター統合テスト

BetTargetEvaluatorに風速・会場除外ロジックが正しく統合されているか確認
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus, MultiBetPattern

def test_venue_wind_filter_integration():
    """風速・会場フィルター統合テスト"""
    print("=" * 80)
    print("風速・会場フィルター統合テスト")
    print("=" * 80)
    print()

    # 評価器初期化（パターンH + 風速・会場フィルター有効）
    evaluator = BetTargetEvaluator(
        use_multi_bet=True,
        multi_bet_pattern=MultiBetPattern.PATTERN_H,
        enable_venue_wind_filter=True
    )
    print("[OK] BetTargetEvaluator初期化成功（パターンH + 風速・会場フィルター）")
    print()

    # テストケース1: 超強風（6m+）× 信頼度D → 除外
    print("【テスト1】超強風（6m）× 信頼度D → 除外されるべき")
    race_data_1 = {
        'venue_code': 7,  # 蒲郡
        'wind_speed': 6.5,  # 超強風
        'entries': [{'pit_number': 1, 'racer_rank': 'B1'}],
    }
    predictions_1 = {
        'confidence': 'D',
        'old_prediction': [1, 2, 3],
        'new_prediction': [1, 2, 3],
        'full_prediction': [1, 2, 3, 4, 5, 6],
    }
    odds_dict_1 = {
        "1-2-3": 35.0,
        "1-2-4": 42.0,
        "1-2-5": 55.0,
    }

    target_1 = evaluator.evaluate_race(
        race_data=race_data_1,
        predictions=predictions_1,
        odds_data=odds_dict_1,
        has_beforeinfo=True
    )

    print(f"  ステータス: {target_1.status.value}")
    print(f"  理由: {target_1.reason}")
    assert target_1.status == BetStatus.EXCLUDED, "超強風×信頼度Dは除外されるべき"
    assert "風速・会場除外" in target_1.reason, "除外理由に「風速・会場除外」が含まれるべき"
    print("[OK] 超強風×信頼度Dは正しく除外された")
    print()

    # テストケース2: 不安定会場（宮島）× 強風（4m+）× 信頼度C → 除外
    print("【テスト2】不安定会場（宮島）× 強風（4m）× 信頼度C → 除外されるべき")
    race_data_2 = {
        'venue_code': 17,  # 宮島（最も不安定、std=10.71）
        'wind_speed': 4.5,  # 強風
        'entries': [{'pit_number': 1, 'racer_rank': 'A1'}],
    }
    predictions_2 = {
        'confidence': 'C',
        'old_prediction': [1, 2, 3],
        'new_prediction': [1, 2, 3],
        'full_prediction': [1, 2, 3, 4, 5, 6],
    }
    odds_dict_2 = {
        "1-2-3": 32.0,
        "1-2-4": 40.0,
        "1-2-5": 50.0,
    }

    target_2 = evaluator.evaluate_race(
        race_data=race_data_2,
        predictions=predictions_2,
        odds_data=odds_dict_2,
        has_beforeinfo=True
    )

    print(f"  ステータス: {target_2.status.value}")
    print(f"  理由: {target_2.reason}")
    assert target_2.status == BetStatus.EXCLUDED, "不安定会場×強風×信頼度Cは除外されるべき"
    print("[OK] 不安定会場×強風×信頼度Cは正しく除外された")
    print()

    # テストケース3: 通常条件（蒲郡、風速3m、信頼度C） → 購入対象
    print("【テスト3】通常条件（蒲郡、風速3m、信頼度C） → 購入対象となるべき")
    race_data_3 = {
        'venue_code': 7,  # 蒲郡
        'wind_speed': 3.0,  # 通常
        'entries': [{'pit_number': 1, 'racer_rank': 'B1'}],
    }
    predictions_3 = {
        'confidence': 'C',
        'old_prediction': [1, 2, 3],
        'new_prediction': [1, 2, 3],
        'full_prediction': [1, 2, 3, 4, 5, 6],
    }
    odds_dict_3 = {
        "1-2-3": 35.0,
        "1-2-4": 42.0,
        "1-2-5": 55.0,
    }

    target_3 = evaluator.evaluate_race(
        race_data=race_data_3,
        predictions=predictions_3,
        odds_data=odds_dict_3,
        has_beforeinfo=True
    )

    print(f"  ステータス: {target_3.status.value}")
    print(f"  信頼度: {target_3.confidence}")
    print(f"  1コース級別: {target_3.c1_rank}")

    if target_3.multi_bet_result:
        print(f"  複数点買い: {len(target_3.multi_bet_result.bets)}点")
        print(f"  総投資額: {target_3.multi_bet_result.total_investment}円")

    assert target_3.status in [BetStatus.TARGET_CONFIRMED, BetStatus.TARGET_ADVANCE], "通常条件は購入対象となるべき"
    assert target_3.multi_bet_result is not None, "パターンHが生成されているべき"
    print("[OK] 通常条件は正しく購入対象となった")
    print()

    # テストケース4: フィルター無効化テスト
    print("【テスト4】フィルター無効化 → 超強風でも購入対象となる")
    evaluator_no_filter = BetTargetEvaluator(
        use_multi_bet=True,
        multi_bet_pattern=MultiBetPattern.PATTERN_H,
        enable_venue_wind_filter=False  # フィルター無効
    )

    target_4 = evaluator_no_filter.evaluate_race(
        race_data=race_data_1,  # 超強風のデータを再利用
        predictions=predictions_1,
        odds_data=odds_dict_1,
        has_beforeinfo=True
    )

    print(f"  ステータス: {target_4.status.value}")
    assert target_4.status != BetStatus.EXCLUDED or "風速・会場除外" not in target_4.reason, \
        "フィルター無効時は風速・会場による除外がないべき"
    print("[OK] フィルター無効化が正しく機能している")
    print()

    print("=" * 80)
    print("[SUCCESS] 全テスト合格！")
    print("=" * 80)
    return True

if __name__ == '__main__':
    success = test_venue_wind_filter_integration()
    sys.exit(0 if success else 1)
