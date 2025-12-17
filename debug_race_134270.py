#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
race_id=134270の詳細デバッグ
"""
import sys
import os
import traceback

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from scripts.fast_prediction_generator import FastPredictionGenerator

print("="*80)
print("race_id=134270 詳細デバッグ")
print("="*80)

gen = FastPredictionGenerator('advance')

# データロード
if gen.predictor.batch_loader:
    print("\n日次データロード中...")
    gen.predictor.batch_loader.load_daily_data('2024-01-01')
    print("データロード完了")

try:
    predictions = gen.predictor.predict_race(134270, use_beforeinfo=False)
    print(f"\n✅ 成功: {len(predictions)}件の予測")
except Exception as e:
    print(f"\n❌ エラー発生!")
    print(f"エラー型: {type(e).__name__}")
    print(f"エラーメッセージ: {e}")
    print("\n完全なスタックトレース:")
    print("="*80)
    traceback.print_exc()
    print("="*80)
