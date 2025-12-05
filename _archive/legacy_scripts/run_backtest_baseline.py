"""
Stage2ベースラインモデルのバックテスト

学習済みモデルを使って2024-04-01〜2024-06-30のレースを予測し、
ROIを算出する
"""

import sys
sys.path.append('.')

from src.ml.dataset_builder import DatasetBuilder
from src.ml.model_trainer import ModelTrainer
from sklearn.metrics import roc_auc_score, log_loss, accuracy_score
from datetime import datetime
import pandas as pd
import numpy as np

print("=" * 70)
print("Stage2ベースラインモデル バックテスト")
print("=" * 70)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# データセット構築（学習時と同じ期間）
print("\n[Step 1] テストデータ構築（2024-04-01〜2024-06-30）")
builder = DatasetBuilder(db_path="data/boatrace.db")
df_raw = builder.build_training_dataset(start_date="2024-04-01", end_date="2024-06-30", venue_codes=None)
print(f"  生データ: {len(df_raw):,}件")

# 結果がないデータを除外
df_raw = df_raw[df_raw['result_rank'].notna()].copy()
print(f"  結果あり: {len(df_raw):,}件")

# 目的変数作成
df_raw['is_win'] = (df_raw['result_rank'].astype(str) == '1').astype(int)

# 派生特徴量追加（学習時と同じ処理）
print("\n[Step 2] 派生特徴量追加")
df = df_raw.copy()

# 枠番ダミー
for i in range(1, 7):
    df[f'pit_number_{i}'] = (df['pit_number'] == i).astype(int)

# コース別ダミー
if 'actual_course' in df.columns:
    for i in range(1, 7):
        df[f'actual_course_{i}'] = (df['actual_course'] == i).astype(int)
    df['pit_course_diff'] = df['pit_number'] - df['actual_course']

# 特徴量とラベル分離
numeric_cols = df.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'is_place_2', 'is_place_3', 'result_rank']
feature_cols = [col for col in numeric_cols if col not in exclude_cols]

X = df[feature_cols].fillna(df[feature_cols].mean())
y = df['is_win']

print(f"  特徴量数: {len(feature_cols)}個")
print(f"  X shape: {X.shape}")

# モデルロード
print("\n[Step 3] モデルロード")
trainer = ModelTrainer(model_dir="models")
trainer.load_model("stage2_baseline_3months.json")
print("  [OK] モデルロード完了")

# 予測
print("\n[Step 4] 予測実行")
y_pred_proba = trainer.predict(X)
y_pred = (y_pred_proba > 0.5).astype(int)

# 評価メトリクス
print("\n[Step 5] 評価メトリクス")
auc = roc_auc_score(y, y_pred_proba)
logloss = log_loss(y, y_pred_proba)
accuracy = accuracy_score(y, y_pred)

print(f"  AUC: {auc:.4f}")
print(f"  Log Loss: {logloss:.4f}")
print(f"  Accuracy: {accuracy:.4f}")

# レース単位での予測精度
print("\n[Step 6] レース単位での予測精度")
df['pred_proba'] = y_pred_proba

# レース単位で最高確率の艇を予想
race_predictions = df.groupby('race_id').apply(
    lambda x: x.loc[x['pred_proba'].idxmax()]
).reset_index(drop=True)

# 的中率計算
race_hit_count = (race_predictions['is_win'] == 1).sum()
total_races = len(race_predictions)
hit_rate = race_hit_count / total_races

print(f"  総レース数: {total_races:,}レース")
print(f"  的中数: {race_hit_count:,}レース")
print(f"  的中率: {hit_rate*100:.2f}%")

# 確率帯別の的中率
print("\n[Step 7] 確率帯別の的中率")
race_predictions['proba_bucket'] = pd.cut(
    race_predictions['pred_proba'],
    bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
    labels=['0.0-0.2', '0.2-0.4', '0.4-0.6', '0.6-0.8', '0.8-1.0']
)

for bucket in race_predictions['proba_bucket'].cat.categories:
    bucket_data = race_predictions[race_predictions['proba_bucket'] == bucket]
    if len(bucket_data) > 0:
        bucket_hit_rate = (bucket_data['is_win'] == 1).mean()
        print(f"  {bucket}: {len(bucket_data):4d}レース, 的中率 {bucket_hit_rate*100:.2f}%")

# ROI計算（簡易版：すべて100円賭けたと仮定）
print("\n[Step 8] ROI計算（単勝のみ、仮想）")
# ※ 実際のオッズデータがないため、ここでは概算
# 平均的な単勝オッズは約7倍と仮定
assumed_avg_odds = 7.0
total_bet = total_races * 100
total_return = race_hit_count * 100 * assumed_avg_odds
roi = (total_return / total_bet) * 100

print(f"  総投資額: {total_bet:,}円")
print(f"  総払戻額: {total_return:,.0f}円（仮定オッズ={assumed_avg_odds}倍）")
print(f"  ROI: {roi:.2f}%")
print(f"  ※ 実際のオッズデータがないため、平均オッズ{assumed_avg_odds}倍で概算")

print(f"\n完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
