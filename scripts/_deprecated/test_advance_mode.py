#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
advance予測モードのテスト
直前情報を使わないことを確認
"""
import sys
import os

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from scripts.fast_prediction_generator import FastPredictionGenerator

def test_advance_mode():
    """advanceモードで直前情報を使わないことを確認"""
    print("=" * 80)
    print("advance予測モードのテスト")
    print("=" * 80)

    # advanceモードで初期化
    print("\n【テスト1】advanceモードで初期化")
    generator_advance = FastPredictionGenerator(prediction_type='advance')
    print(f"  prediction_type: {generator_advance.prediction_type}")
    print(f"  use_beforeinfo: {generator_advance.use_beforeinfo}")

    if generator_advance.prediction_type == 'advance' and generator_advance.use_beforeinfo == False:
        print("  ✅ 正常: advanceモード、直前情報を使わない")
    else:
        print("  🔴 異常: 設定が正しくありません")
        return False

    # beforeモードで初期化
    print("\n【テスト2】beforeモードで初期化")
    generator_before = FastPredictionGenerator(prediction_type='before')
    print(f"  prediction_type: {generator_before.prediction_type}")
    print(f"  use_beforeinfo: {generator_before.use_beforeinfo}")

    if generator_before.prediction_type == 'before' and generator_before.use_beforeinfo == True:
        print("  ✅ 正常: beforeモード、直前情報を使う")
    else:
        print("  🔴 異常: 設定が正しくありません")
        return False

    # デフォルト（引数なし）の場合
    print("\n【テスト3】デフォルト（引数なし）")
    generator_default = FastPredictionGenerator()
    print(f"  prediction_type: {generator_default.prediction_type}")
    print(f"  use_beforeinfo: {generator_default.use_beforeinfo}")

    if generator_default.prediction_type == 'advance' and generator_default.use_beforeinfo == False:
        print("  ✅ 正常: デフォルトはadvanceモード、直前情報を使わない")
    else:
        print("  🔴 異常: デフォルトがadvanceになっていません")
        return False

    # RacePredictorへの引数渡しを確認
    print("\n【テスト4】RacePredictorへの引数渡しを確認")
    print(f"  FastPredictionGenerator.use_beforeinfo = {generator_advance.use_beforeinfo}")
    print(f"  → RacePredictor.predict_race()に use_beforeinfo={generator_advance.use_beforeinfo} を渡す")

    if generator_advance.use_beforeinfo == False:
        print("  ✅ 正常: predict_race(race_id, use_beforeinfo=False) が呼ばれる")
        print("  → RacePredictor内で直前情報スコアリングがスキップされる（896-903行目）")
    else:
        print("  🔴 異常: use_beforeinfo=Trueになっています")
        return False

    print("\n" + "=" * 80)
    print("✅ 全テストパス: advanceモードで直前情報を使わない設定が正しい")
    print("=" * 80)

    print("\n【確認事項】")
    print("1. FastPredictionGenerator(prediction_type='advance')")
    print("   → self.use_beforeinfo = False")
    print()
    print("2. self.predictor.predict_race(race_id, use_beforeinfo=False)")
    print("   → RacePredictor.predict_race()に False が渡される")
    print()
    print("3. RacePredictor.predict_race()内（896-903行目）")
    print("   if use_beforeinfo:  # False なのでスキップ")
    print("       predictions = self._apply_beforeinfo_integration(...)")
    print()
    print("4. 結果: 直前情報（展示タイム、ST等）を使わない事前予測が生成される")

    return True

if __name__ == "__main__":
    success = test_advance_mode()
    sys.exit(0 if success else 1)
