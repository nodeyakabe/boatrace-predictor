"""
BeforeInfoScorerの動作確認
"""

from src.analysis.beforeinfo_scorer import BeforeInfoScorer
import json

scorer = BeforeInfoScorer(db_path='data/boatrace.db')

race_id = 132764
pit_number = 1

print("=" * 80)
print(f"BeforeInfoScorer テスト")
print(f"race_id: {race_id}, pit_number: {pit_number}")
print("=" * 80)
print()

# 直前情報スコアを計算
result = scorer.calculate_beforeinfo_score(race_id, pit_number)

print("計算結果:")
print(json.dumps(result, indent=2, ensure_ascii=False))
print()

# 他の艇も確認
print("=" * 80)
print("全艇のbefore_scoreを確認:")
print("=" * 80)
for pit in range(1, 7):
    result = scorer.calculate_beforeinfo_score(race_id, pit)
    print(f"{pit}号: total_score={result['total_score']:.2f}, confidence={result['confidence']:.2f}, data_completeness={result['data_completeness']:.2f}")

print()
print("=" * 80)
