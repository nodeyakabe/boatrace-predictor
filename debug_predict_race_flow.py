"""
predict_race メソッドの実行フローをトレース

before_scoreが0になる原因を特定する
"""

import sqlite3
from src.analysis.race_predictor import RacePredictor
import json

race_id = 132764

print("=" * 80)
print("predict_race 実行フローのデバッグ")
print(f"race_id: {race_id}")
print("=" * 80)
print()

# RacePredictorのインスタンス作成
predictor = RacePredictor(db_path='data/boatrace.db')

# 予測実行前の状態確認
print("【1】 RacePredictor インスタンス情報:")
print(f"  beforeinfo_scorer: {predictor.beforeinfo_scorer}")
print(f"  dynamic_integrator: {predictor.dynamic_integrator}")
print(f"  entry_prediction_model: {predictor.entry_prediction_model}")
print()

# feature_flagsの状態確認
from config.feature_flags import is_feature_enabled, FEATURE_FLAGS
print("【2】 feature_flags の状態:")
print(f"  dynamic_integration: {is_feature_enabled('dynamic_integration')}")
print(f"  entry_prediction_model: {is_feature_enabled('entry_prediction_model')}")
print()

# 予測実行
print("【3】 予測実行中...")
predictions = predictor.predict_race(race_id)
print(f"  予測結果: {len(predictions)}艇")
print()

# 予測結果の詳細確認
print("【4】 予測結果の詳細:")
for i, pred in enumerate(predictions[:3], 1):
    print(f"\n{i}位予測: {pred['pit_number']}号")
    print(f"  total_score: {pred.get('total_score', 'なし')}")
    print(f"  pre_score: {pred.get('pre_score', 'なし')}")
    print(f"  beforeinfo_score: {pred.get('beforeinfo_score', 'なし')}")
    print(f"  beforeinfo_confidence: {pred.get('beforeinfo_confidence', 'なし')}")
    print(f"  beforeinfo_completeness: {pred.get('beforeinfo_completeness', 'なし')}")

    # 統合モード情報
    if 'integration_mode' in pred:
        print(f"  integration_mode: {pred['integration_mode']}")
        print(f"  pre_weight: {pred.get('pre_weight', 'なし')}")
        print(f"  before_weight: {pred.get('before_weight', 'なし')}")

    # beforeinfo_detail
    if 'beforeinfo_detail' in pred:
        print(f"  beforeinfo_detail: {pred['beforeinfo_detail']}")

print()
print("=" * 80)

# BeforeInfoScorerを直接呼び出して比較
print("【5】 BeforeInfoScorer 直接呼び出しとの比較:")
print()

for pit in [1, 4, 5]:  # 1位、2位、5号（最高before_score）を確認
    bi_result = predictor.beforeinfo_scorer.calculate_beforeinfo_score(
        race_id=race_id,
        pit_number=pit
    )

    # predict_race結果から該当艇を探す
    pred_result = next((p for p in predictions if p['pit_number'] == pit), None)

    print(f"{pit}号:")
    print(f"  BeforeInfoScorer直接: total_score={bi_result['total_score']:.2f}, confidence={bi_result['confidence']:.3f}")
    if pred_result:
        print(f"  predict_race結果: beforeinfo_score={pred_result.get('beforeinfo_score', 'なし')}")
        print(f"  一致: {abs(bi_result['total_score'] - pred_result.get('beforeinfo_score', -999)) < 0.1}")
    else:
        print(f"  predict_race結果: 艇が見つからない")
    print()

print("=" * 80)

# RacePredictorのmodeを確認
print("【6】 RacePredictor のモード設定:")
print(f"  mode: {predictor.mode}")
print(f"  custom_weights: {predictor.custom_weights}")
print()

# dynamic_integrator が None でないか確認
print("【7】 dynamic_integrator の状態:")
if predictor.dynamic_integrator:
    print(f"  インスタンス: {type(predictor.dynamic_integrator).__name__}")
else:
    print(f"  インスタンス: None （問題！）")
print()

print("=" * 80)
print("デバッグ完了")
print("=" * 80)
