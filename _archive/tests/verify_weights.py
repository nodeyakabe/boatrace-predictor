"""
実際に使用されている重みを確認
"""

from src.analysis.race_predictor import RacePredictor

race_id = 132764

predictor = RacePredictor(db_path='data/boatrace.db')
predictions = predictor.predict_race(race_id)

print("=" * 80)
print("使用されている重み確認")
print(f"race_id: {race_id}")
print("=" * 80)
print()

if predictions and len(predictions) > 0:
    sample = predictions[0]

    print("予測結果（1号艇）:")
    print(f"  pit_number: {sample.get('pit_number')}")
    print(f"  total_score: {sample.get('total_score', 0):.2f}")
    print(f"  pre_score: {sample.get('pre_score', 0):.2f}")
    print(f"  beforeinfo_score: {sample.get('beforeinfo_score', 0):.2f}")
    print(f"  pre_weight: {sample.get('pre_weight', 'N/A')}")
    print(f"  before_weight: {sample.get('before_weight', 'N/A')}")
    print()

    # 実際の重みを計算
    pre = sample.get('pre_score', 0)
    before = sample.get('beforeinfo_score', 0)
    total = sample.get('total_score', 0)
    pre_w = sample.get('pre_weight', None)
    before_w = sample.get('before_weight', None)

    if pre_w and before_w:
        print(f"使用されている重み: PRE {pre_w:.1%} / BEFORE {before_w:.1%}")

        expected = pre * pre_w + before * before_w
        print()
        print("検証:")
        print(f"  PRE_SCORE × {pre_w:.2f} = {pre * pre_w:.2f}")
        print(f"  BEFORE_SCORE × {before_w:.2f} = {before * before_w:.2f}")
        print(f"  期待値: {expected:.2f}")
        print(f"  実測値: {total:.2f}")
        print(f"  差分: {total - expected:.2f}")
    else:
        print("重み情報が予測結果に含まれていません")
        print()
        print("可能性:")
        print("  1. 予測結果に重み情報が追加されていない")
        print("  2. DynamicIntegratorが呼ばれていない")

    print()
    print("全艇の beforeinfo_score:")
    print("-" * 80)
    for pred in predictions:
        pit = pred['pit_number']
        before_score = pred.get('beforeinfo_score', 0)
        print(f"  {pit}号: {before_score:.2f}")

else:
    print("エラー: 予測結果を取得できませんでした")

print()
print("=" * 80)
