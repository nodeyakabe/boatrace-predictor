"""
racer_featuresの欠落期間（2024-04-01〜04-13）を補充
"""

import sys
sys.path.append('.')

from src.features.precompute_features import FeaturePrecomputer

print("=" * 70)
print("racer_features 欠落期間補充")
print("=" * 70)

precomputer = FeaturePrecomputer()

# 欠落期間のみ計算
start_date = "2024-04-01"
end_date = "2024-04-13"

print(f"\n補充期間: {start_date} 〜 {end_date}")
precomputer.compute_racer_features(start_date, end_date, batch_size=500)

print("\n=" * 70)
print("補充完了")
print("=" * 70)
