# -*- coding: utf-8 -*-
"""BetTargetEvaluatorのテスト"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator

evaluator = BetTargetEvaluator()

# テストケース: 信頼度D × イン強会場 × B1級 × オッズ15.8倍
result = evaluator.evaluate(
    confidence='D',
    c1_rank='B1',
    old_combo='1-6-5',
    new_combo='1-6-5',
    old_odds=15.8,
    new_odds=15.8,
    has_beforeinfo=True,
    venue_code=18  # 徳山
)

print("=" * 70)
print("テスト: 信頼度D × イン強会場(徳山) × B1級 × オッズ15.8倍")
print("=" * 70)
print(f"判定: {result.status.value}")
print(f"理由: {result.reason}")
print(f"賭け金: {result.bet_amount}円")
print(f"期待ROI: {result.expected_roi}%")
print()

# テストケース2: オッズ範囲外（8.1倍）
result2 = evaluator.evaluate(
    confidence='D',
    c1_rank='B1',
    old_combo='1-4-2',
    new_combo='1-4-2',
    old_odds=8.1,
    new_odds=8.1,
    has_beforeinfo=True,
    venue_code=19  # 下関
)

print("=" * 70)
print("テスト: 信頼度D × イン強会場(下関) × B1級 × オッズ8.1倍")
print("=" * 70)
print(f"判定: {result2.status.value}")
print(f"理由: {result2.reason}")
print()

# テストケース3: イン強会場でない場合
result3 = evaluator.evaluate(
    confidence='D',
    c1_rank='B1',
    old_combo='1-6-5',
    new_combo='1-6-5',
    old_odds=15.8,
    new_odds=15.8,
    has_beforeinfo=True,
    venue_code=1  # 桐生（イン強会場でない）
)

print("=" * 70)
print("テスト: 信頼度D × 非イン強会場(桐生) × B1級 × オッズ15.8倍")
print("=" * 70)
print(f"判定: {result3.status.value}")
print(f"理由: {result3.reason}")
print()
