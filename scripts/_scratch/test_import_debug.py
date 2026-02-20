#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""インポートテスト"""
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

print("[1/8] 開始")

import os
print("[2/8] os インポート完了")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, PROJECT_ROOT)
print("[3/8] パス設定完了")

from config.settings import DATABASE_PATH
print("[4/8] DATABASE_PATH インポート完了")

from config.feature_flags import FEATURE_FLAGS
print("[5/8] FEATURE_FLAGS インポート完了")

from scripts.safety_check import check_hierarchical_predictor
print("[6/8] safety_check インポート完了")

check_hierarchical_predictor()
print("[7/8] safety_check 実行完了")

from src.prediction.predictor_helpers import create_standard_predictor
print("[8/8] create_standard_predictor インポート完了")

print("\n全てのインポート成功!")
