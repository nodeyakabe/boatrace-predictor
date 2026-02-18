#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""generate_predictions.pyの最小再現テスト"""
import sys
import os
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

print("[1/6] パス設定完了", flush=True)

from config.feature_flags import FEATURE_FLAGS
print("[2/6] FEATURE_FLAGS インポート完了", flush=True)

from scripts.safety_check import check_hierarchical_predictor
check_hierarchical_predictor()
print("[3/6] safety_check 完了", flush=True)

from src.prediction.predictor_helpers import create_standard_predictor
print("[4/6] predictor_helpers インポート完了", flush=True)

print("[5/6] Predictor初期化開始...", flush=True)
import time
start = time.time()
predictor = create_standard_predictor()
elapsed = time.time() - start
print(f"[5/6] Predictor初期化完了 ({elapsed:.1f}秒)", flush=True)

print("[6/6] main()関数の処理開始...", flush=True)

# generate_predictions.pyのmain()の処理を模倣
from datetime import datetime
import argparse

parser = argparse.ArgumentParser(description='テスト')
parser.add_argument('--years', type=str, default='2020')
parser.add_argument('--type', type=str, default='before')
parser.add_argument('--dry-run', action='store_true')
parser.add_argument('--dry-run-size', type=int, default=1)

# コマンドライン引数を模倣
sys.argv = ['test_generate_minimal.py', '--years', '2020', '--type', 'before', '--dry-run', '--dry-run-size', '1']
args = parser.parse_args()

print("="*70, flush=True)
print("予測データ統合生成スクリプト", flush=True)
print(f"モード: DRY RUN", flush=True)
print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
print("="*70, flush=True)

# フィーチャーフラグ確認
print("\n現在のフィーチャーフラグ:", flush=True)
important_flags = ['hierarchical_predictor', 'lightgbm_ranking', 'pairwise_scoring']
for flag in important_flags:
    value = FEATURE_FLAGS.get(flag, False)
    status = "✓" if value else "✗"
    print(f"  [{status}] {flag}: {value}", flush=True)

print("\n✅ ここまで到達（ハングしていない）", flush=True)
