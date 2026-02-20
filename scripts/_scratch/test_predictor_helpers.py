#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
predictor_helpers.py の動作確認テスト
"""
import sys
import io

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    print("=" * 60)
    print("predictor_helpers.py 動作確認テスト")
    print("=" * 60)
    print()

    # 1. インポートテスト
    print("[1] インポートテスト")
    from src.prediction.predictor_helpers import (
        create_standard_predictor,
        create_backtest_predictor,
        create_accuracy_predictor,
        create_value_predictor,
        create_custom_predictor
    )
    print("   ✅ 全ヘルパー関数のインポート成功")
    print()

    # 2. 標準predictor生成テスト
    print("[2] 標準predictor生成テスト")
    predictor = create_standard_predictor()
    print(f"   ✅ create_standard_predictor() 成功")
    print(f"   - Type: {type(predictor).__name__}")
    print(f"   - use_cache: {predictor.use_cache}")
    print(f"   - db_path: {predictor.db_path}")
    print()

    # 3. バックテスト用predictor生成テスト
    print("[3] バックテスト用predictor生成テスト")
    backtest_predictor = create_backtest_predictor()
    print(f"   ✅ create_backtest_predictor() 成功")
    print(f"   - use_cache: {backtest_predictor.use_cache} (期待値: False)")
    print()

    # 4. カスタムpredictor生成テスト
    print("[4] カスタムpredictor生成テスト")
    custom_predictor = create_custom_predictor(use_cache=False, db_path="custom.db")
    print(f"   ✅ create_custom_predictor() 成功")
    print(f"   - use_cache: {custom_predictor.use_cache}")
    print(f"   - db_path: {custom_predictor.db_path}")
    print()

    print("=" * 60)
    print("✅ 全テスト成功")
    print("=" * 60)

except Exception as e:
    print(f"\n❌ エラー発生: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
