#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
単一レースの予測テスト
"""
import sys
import os

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from scripts.fast_prediction_generator import FastPredictionGenerator

# advance予測を生成
gen = FastPredictionGenerator('advance')

print("2024-01-01の予測を1日分テスト実行")
print("="*70)

result = gen.generate_all_predictions('2024-01-01', skip_existing=False)

print("\n"+"="*70)
print("結果:")
print(f"  総レース数: {result.get('total_races', 0)}")
print(f"  生成成功: {result.get('generated', 0)}")
print(f"  エラー: {result.get('errors', 0)}")
print(f"  スキップ: {result.get('skipped', 0)}")
print(f"  処理時間: {result.get('total_time', 0):.1f}秒")
print("="*70)
