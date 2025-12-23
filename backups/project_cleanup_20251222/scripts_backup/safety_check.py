#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測データ生成前の安全チェック共通モジュール

全ての予測生成スクリプトから import して使用する
"""
import sys
import os

# パス設定
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.feature_flags import FEATURE_FLAGS


def check_hierarchical_predictor():
    """
    hierarchical_predictor が有効かチェック

    無効な場合は処理を強制停止する（D/Eのみの信頼度になるのを防ぐ）

    Returns:
        bool: True（有効）

    Raises:
        SystemExit: hierarchical_predictor が無効の場合
    """
    if not FEATURE_FLAGS.get('hierarchical_predictor', False):
        print("=" * 70)
        print("🔴 FATAL ERROR: hierarchical_predictor is OFF")
        print("=" * 70)
        print()
        print("このまま続行すると、信頼度が D/E のみになります。")
        print("A, B, C の信頼度が生成されません。")
        print()
        print("対処方法:")
        print("  1. config/feature_flags.py を開く")
        print("  2. 'hierarchical_predictor': True に設定")
        print("  3. スクリプトを再実行")
        print()
        print("=" * 70)
        sys.exit(1)

    print("✅ Safety check passed: hierarchical_predictor is ON")
    return True


def display_feature_flags():
    """現在の重要なフィーチャーフラグを表示"""
    print("\n現在のフィーチャーフラグ:")
    important_flags = [
        'hierarchical_predictor',
        'lightgbm_ranking',
        'pairwise_scoring',
        'confidence_based_switching',
        'kimarite_flow_prediction',
        'makuri_risk_adjustment',
        'ab_rank_special_betting',
    ]

    for flag in important_flags:
        value = FEATURE_FLAGS.get(flag, False)
        status = "✓" if value else "✗"
        print(f"  [{status}] {flag}: {value}")
    print()


def safety_check(display_flags: bool = True):
    """
    予測生成前の安全チェック統合関数

    Args:
        display_flags: フィーチャーフラグを表示するか（デフォルト: True）

    Returns:
        bool: True（全チェック通過）

    Raises:
        SystemExit: チェック失敗時
    """
    if display_flags:
        display_feature_flags()

    check_hierarchical_predictor()

    return True


if __name__ == '__main__':
    # テスト実行
    print("Safety Check Module Test")
    print("-" * 70)
    safety_check()
    print("All checks passed!")
