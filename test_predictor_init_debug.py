#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Predictor初期化デバッグテスト"""
import sys
import io
import time

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

print("[1/4] 開始", flush=True)

import os
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from scripts.safety_check import check_hierarchical_predictor
check_hierarchical_predictor()
print("[2/4] safety_check 完了", flush=True)

from src.prediction.predictor_helpers import create_standard_predictor
print("[3/4] import 完了", flush=True)

print("[4/4] Predictor初期化開始...", flush=True)
start = time.time()
predictor = create_standard_predictor()
elapsed = time.time() - start
print(f"✅ Predictor初期化完了 ({elapsed:.1f}秒)", flush=True)
