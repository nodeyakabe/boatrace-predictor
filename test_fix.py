#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修正後の動作テスト - 2024-01-01の1日分
"""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from scripts.fast_prediction_generator import FastPredictionGenerator

gen = FastPredictionGenerator('advance')

print("="*70)
print("2024-01-01 Prediction Test")
print("="*70)

result = gen.generate_all_predictions('2024-01-01', skip_existing=False)

print("\n" + "="*70)
print("Result:")
print(f"  Total races: {result.get('total_races', 0)}")
print(f"  Generated: {result.get('generated', 0)}")
print(f"  Errors: {result.get('errors', 0)}")
print(f"  Skipped: {result.get('skipped', 0)}")
print(f"  Time: {result.get('total_time', 0):.1f}s")
print("="*70)
