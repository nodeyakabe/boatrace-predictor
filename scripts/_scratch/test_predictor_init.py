#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Predictor初期化テスト"""
import sys
import io
import time
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

print(f"[{datetime.now().strftime('%H:%M:%S')}] テスト開始")
print("[1/5] パス設定...")
import os
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

print("[2/5] 設定インポート...")
from config.settings import DATABASE_PATH

print("[3/5] feature_flags インポート...")
from config.feature_flags import FEATURE_FLAGS
print(f"  pairwise_scoring: {FEATURE_FLAGS.get('pairwise_scoring', False)}")

print("[4/5] create_standard_predictor インポート...")
start = time.time()
from src.prediction.predictor_helpers import create_standard_predictor
print(f"  インポート完了 ({time.time()-start:.1f}秒)")

print("[5/5] Predictor初期化...")
start = time.time()
predictor = create_standard_predictor()
elapsed = time.time() - start
print(f"  初期化完了 ({elapsed:.1f}秒)")

print(f"\n✅ テスト成功（総時間: {time.time()-start:.1f}秒）")
