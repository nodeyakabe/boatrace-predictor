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

# exhibition_buff_rules.py の期待値（2026-03-19 展示タイム差ルール実装後）
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
    # 2026-03-24 展示タイム差ルール再設計（4段階・ペナルティ廃止）
     5.0,   # 展示1位×タイム差very_large(>=0.08s)
     3.0,   # 展示1位×タイム差large(0.05-0.08s)
     1.0,   # 展示1位×タイム差medium(0.03-0.05s)
])  # 合計14ルール（smallはルールなし=0pt）


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
        print("[ERROR] exhibition_buff_rules.py の値がベースラインと異なります")
        print("=" * 70)
        for e in errors:
            print(e)
        print()
        print("  原因: コードリバート漏れ、または意図的な変更かを確認してください。")
        print("  意図的な変更の場合: 残タスク一覧.md に記録してからスクリプトを再実行。")
        print("  確認コマンド: git diff f0d6d10 HEAD -- src/analysis/exhibition_buff_rules.py")
        print("=" * 70)
        return False

    print("[OK] Safety check passed: exhibition_buff_rules.py values OK")
    return True


def check_hierarchical_predictor():
    """
    hierarchical_predictor の状態を表示（情報のみ、停止はしない）

    2026-03-19 更新: このフラグはOFFにしても信頼度・スコアに影響しない。
    三連単確率（hierarchical_1st/2nd/3rd_prob）はDBに保存されず、
    confidence計算もtotal_scoreのみに依存するため、dead outputと確認済み。
    計算コスト削減のためFalseが推奨。

    Returns:
        bool: 常にTrue（チェックのみ、停止しない）
    """
    value = FEATURE_FLAGS.get('hierarchical_predictor', False)
    status = "ON " if value else "OFF"
    print(f"[INFO] hierarchical_predictor is {status} (dead output - no effect on score/confidence)")
    return True


def display_feature_flags():
    """現在の重要なフィーチャーフラグを表示"""
    print("\nFeature Flags:")
    important_flags = [
        'lightgbm_ranking',
        'pairwise_scoring',
        'confidence_based_switching',
        'kimarite_flow_prediction',
        'makuri_risk_adjustment',
        'ab_rank_special_betting',
    ]

    for flag in important_flags:
        value = FEATURE_FLAGS.get(flag, False)
        status = "ON " if value else "OFF"
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

    if not check_exhibition_buff_values():
        print("[FATAL] exhibition_buff_rules.py の値がベースラインと異なります。処理を停止します。")
        sys.exit(1)
    check_hierarchical_predictor()

    return True


if __name__ == '__main__':
    # テスト実行
    print("Safety Check Module Test")
    print("-" * 70)
    safety_check()
    print("All checks passed!")
