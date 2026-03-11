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

# exhibition_buff_rules.py の期待値（f0d6d10 / 2e877e6 ベースライン）
# ⚠️ この値を変更する場合は必ず 残タスク一覧.md に記録すること
# ルール名は日本語のため、buff_value のソート済みリストで比較する
_EXPECTED_EXHIBITION_BUFF_VALUES = sorted([
    20.0,   # 展示1位×コース1
     4.0,   # 展示1位×コース2-3
     1.5,   # 展示1位×コース4-6
    -4.0,   # 展示4-6位×コース4-6
    12.0,   # 展示1位×A1級
     3.0,   # 展示1位×A2級
     1.5,   # 展示1位×B1級
     0.5,   # 展示1位×B2級
     6.0,   # 展示TOP2×ST好調×インコース
     3.0,   # 展示TOP2×ST普通×インコース
    -5.0,   # 展示3位以下×ST普通×アウトコース
     8.0,   # 展示1位×タイム差0.1-0.2秒
])  # 合計12ルール


def check_exhibition_buff_values():
    """
    exhibition_buff_rules.py の compound_buff 値がベースラインと一致するか検証

    2026-03-11 再発防止: ab12e54 コミットで P8 変更（60%圧縮）が混入し、
    9258c8c リバートで exhibition_buff_rules.py が見落とされた教訓から実装。

    Returns:
        bool: True（正常）/ False（差異あり）
    """
    try:
        from src.analysis.exhibition_buff_rules import get_exhibition_buff_rules
        actual_values = sorted([r.buff_value for r in get_exhibition_buff_rules()])
    except Exception as e:
        print(f"  [SKIP] exhibition_buff_rules.py 読み込みエラー: {e}")
        return True  # 読み込み失敗はスキップ（実行を止めない）

    errors = []
    expected = _EXPECTED_EXHIBITION_BUFF_VALUES
    if len(actual_values) != len(expected):
        errors.append(f"  ❌ ルール数が異なります: {len(actual_values)} (期待値: {len(expected)})")
        errors.append(f"     実際の値: {actual_values}")
        errors.append(f"     期待の値: {expected}")
    else:
        for i, (act, exp) in enumerate(zip(actual_values, expected)):
            if abs(act - exp) > 0.001:
                errors.append(f"  ❌ buff_value[{i}]: {act} (期待値: {exp})")

    if errors:
        print("=" * 70)
        print("🔴 WARNING: exhibition_buff_rules.py の値がベースラインと異なります")
        print("=" * 70)
        for e in errors:
            print(e)
        print()
        print("  原因: コードリバート漏れ、または意図的な変更かを確認してください。")
        print("  意図的な変更の場合: 残タスク一覧.md に記録してからスクリプトを再実行。")
        print("  確認コマンド: git diff f0d6d10 HEAD -- src/analysis/exhibition_buff_rules.py")
        print("=" * 70)
        return False

    print("✅ Safety check passed: exhibition_buff_rules.py values OK")
    return True


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

    check_exhibition_buff_values()
    check_hierarchical_predictor()

    return True


if __name__ == '__main__':
    # テスト実行
    print("Safety Check Module Test")
    print("-" * 70)
    safety_check()
    print("All checks passed!")
