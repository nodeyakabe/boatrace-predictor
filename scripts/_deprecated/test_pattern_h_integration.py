#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
パターンH統合テスト

BetTargetEvaluatorとMultiBetGeneratorの統合が正しく動作するか確認
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus, MultiBetPattern

def test_pattern_h_integration():
    """パターンH統合テスト"""
    print("=" * 80)
    print("パターンH統合テスト")
    print("=" * 80)
    print()

    # 評価器初期化（パターンH有効）
    evaluator = BetTargetEvaluator(
        use_multi_bet=True,
        multi_bet_pattern=MultiBetPattern.PATTERN_H
    )
    print("[OK] BetTargetEvaluator初期化成功（パターンH）")

    # テストデータ
    race_data = {
        'venue_code': 7,
        'entries': [{'pit_number': 1, 'racer_rank': 'B1'}],
    }
    predictions = {
        'confidence': 'C',
        'old_prediction': [1, 2, 3],
        'new_prediction': [1, 2, 3],
        'full_prediction': [1, 2, 3, 4, 5, 6],
    }
    odds_dict = {
        "1-2-3": 35.0,
        "1-2-4": 42.0,
        "1-2-5": 55.0,
        "1-2-6": 68.0,
        "1-3-2": 38.0,
        "2-1-3": 40.0,
    }

    # 購入対象判定
    target = evaluator.evaluate_race(
        race_data=race_data,
        predictions=predictions,
        odds_data=odds_dict,
        has_beforeinfo=True
    )

    print()
    print("【評価結果】")
    print(f"  ステータス: {target.status.value}")
    print(f"  信頼度: {target.confidence}")
    print(f"  1コース級別: {target.c1_rank}")
    print(f"  期待ROI: {target.expected_roi}%")

    # 複数点買い情報確認
    if target.multi_bet_result:
        print()
        print("【複数点買い情報】")
        print(f"  パターン: {target.multi_bet_result.pattern.value}")
        print(f"  説明: {target.multi_bet_result.description}")
        print(f"  総投資額: {target.multi_bet_result.total_investment}円")
        print(f"  期待的中率: {target.multi_bet_result.expected_hit_rate}%")
        print(f"  期待ROI: {target.multi_bet_result.expected_roi}%")
        print()
        print("  買い目:")
        for i, bet in enumerate(target.multi_bet_result.bets, 1):
            print(f"    {i}. {bet.combination}: {bet.bet_amount}円（オッズ{bet.odds}倍）")

        # 検証
        assert len(target.multi_bet_result.bets) == 3, "パターンHは3点買いのはず"
        assert target.multi_bet_result.total_investment == 400, "総投資額は400円のはず"
        assert target.multi_bet_result.bets[0].bet_amount == 200, "1点目は200円のはず"
        assert target.multi_bet_result.bets[1].bet_amount == 100, "2点目は100円のはず"
        assert target.multi_bet_result.bets[2].bet_amount == 100, "3点目は100円のはず"

        print()
        print("[OK] 複数点買い情報検証成功")
    else:
        print()
        print("[NG] 複数点買い情報が生成されていません")
        return False

    # 1点買いモードのテスト
    print()
    print("=" * 80)
    print("1点買いモードテスト")
    print("=" * 80)
    print()

    evaluator_single = BetTargetEvaluator(use_multi_bet=False)
    target_single = evaluator_single.evaluate_race(
        race_data=race_data,
        predictions=predictions,
        odds_data=odds_dict,
        has_beforeinfo=True
    )

    print(f"  ステータス: {target_single.status.value}")
    print(f"  買い目: {target_single.combination}")
    print(f"  賭け金: {target_single.bet_amount}円")
    print(f"  複数点買い情報: {target_single.multi_bet_result}")

    assert target_single.multi_bet_result is None, "1点買いモードでは複数点買い情報はNoneのはず"
    print()
    print("[OK] 1点買いモード検証成功")

    print()
    print("=" * 80)
    print("[SUCCESS] 全テスト合格！")
    print("=" * 80)
    return True

if __name__ == '__main__':
    success = test_pattern_h_integration()
    sys.exit(0 if success else 1)
