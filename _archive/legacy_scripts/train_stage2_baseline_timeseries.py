"""
Stage2モデル学習スクリプト（ベースライン時系列分割版）

実験#006: 実験#005との公平な比較のため、ベースライン特徴量のみで時系列分割
- 学習期間: 2024-04-01 〜 2024-05-31（2ヶ月）
- テスト期間: 2024-06-01 〜 2024-06-30（1ヶ月）
- 特徴量: 30個（会場・級別特徴量なし）
- 目的: 実験#005との差分が会場・級別特徴量の純粋な効果
"""

import sys
sys.path.append('.')

from src.ml.dataset_builder import DatasetBuilder
from src.ml.model_trainer import ModelTrainer
from sklearn.metrics import roc_auc_score, log_loss
from datetime import datetime
import pandas as pd
import numpy as np

print("=" * 70)
print("Stage2モデル学習 - ベースライン時系列分割版（実験#006）")
print("=" * 70)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# データセット構築（学習用）
print("\n[Step 1] 学習データセット構築（2024-04-01〜2024-05-31）")
builder = DatasetBuilder(db_path="data/boatrace.db")
df_train_raw = builder.build_training_dataset(
    start_date="2024-04-01",
    end_date="2024-05-31",
    venue_codes=None
)
print(f"  生データ: {len(df_train_raw):,}件")

df_train_raw = df_train_raw[df_train_raw['result_rank'].notna()].copy()
print(f"  結果あり: {len(df_train_raw):,}件")

# データセット構築（テスト用）
print("\n[Step 2] テストデータセット構築（2024-06-01〜2024-06-30）")
df_test_raw = builder.build_training_dataset(
    start_date="2024-06-01",
    end_date="2024-06-30",
    venue_codes=None
)
print(f"  生データ: {len(df_test_raw):,}件")

df_test_raw = df_test_raw[df_test_raw['result_rank'].notna()].copy()
print(f"  結果あり: {len(df_test_raw):,}件")

# 目的変数作成
df_train_raw['is_win'] = (df_train_raw['result_rank'].astype(str) == '1').astype(int)
df_test_raw['is_win'] = (df_test_raw['result_rank'].astype(str) == '1').astype(int)

print(f"  学習データ正例: {df_train_raw['is_win'].sum():,}件")
print(f"  テストデータ正例: {df_test_raw['is_win'].sum():,}件")

# ベースライン特徴量追加関数（会場・級別特徴量なし）
def add_baseline_features(df):
    """ベースライン特徴量のみを追加（会場・級別特徴量を除外）"""
    df = df.copy()

    # 枠番ダミー
    for i in range(1, 7):
        df[f'pit_number_{i}'] = (df['pit_number'] == i).astype(int)

    # コース別ダミー
    if 'actual_course' in df.columns:
        for i in range(1, 7):
            df[f'actual_course_{i}'] = (df['actual_course'] == i).astype(int)
        df['pit_course_diff'] = df['pit_number'] - df['actual_course']

    # 選手成績特徴量
    # (racer_win_rate, racer_place_rate, racer_avg_st などは既にDatasetBuilderで追加済み)

    return df

# 学習データに特徴量追加
print("\n[Step 3] 学習データに特徴量追加（ベースラインのみ）")
df_train = add_baseline_features(df_train_raw)
print(f"  特徴量追加後: {len(df_train.columns)}カラム")

# テストデータに特徴量追加
print("\n[Step 4] テストデータに特徴量追加（ベースラインのみ）")
df_test = add_baseline_features(df_test_raw)
print(f"  特徴量追加後: {len(df_test.columns)}カラム")

# 共通の特徴量カラムを抽出（数値型のみ）
train_numeric_cols = df_train.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
test_numeric_cols = df_test.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'is_place_2', 'is_place_3', 'result_rank']

# 学習とテストで共通の特徴量のみ使用
common_features = set(train_numeric_cols) & set(test_numeric_cols)
feature_cols = [col for col in common_features if col not in exclude_cols]
feature_cols = sorted(feature_cols)  # 順序を固定

print(f"\n[Step 5] 特徴量抽出")
print(f"  共通特徴量数: {len(feature_cols)}個")
print(f"  特徴量一覧（最初の30個）:")
for i, col in enumerate(feature_cols[:30]):
    print(f"    {i+1:2d}. {col}")

# 欠損値処理
X_train = df_train[feature_cols].copy()
X_test = df_test[feature_cols].copy()

for col in X_train.columns:
    if X_train[col].isna().any():
        mean_val = X_train[col].mean()
        X_train.loc[:, col] = X_train[col].fillna(mean_val)
        X_test.loc[:, col] = X_test[col].fillna(mean_val)  # 学習データの平均で補完

y_train = df_train['is_win']
y_test = df_test['is_win']

print(f"\n[Step 6] データセット準備完了")
print(f"  X_train shape: {X_train.shape}")
print(f"  X_test shape: {X_test.shape}")
print(f"  y_train 正例: {y_train.sum():,}件 ({y_train.mean()*100:.2f}%)")
print(f"  y_test 正例: {y_test.sum():,}件 ({y_test.mean()*100:.2f}%)")

# モデル学習
print(f"\n[Step 7] XGBoost学習開始")
trainer = ModelTrainer(model_dir="models")
trainer.train(X_train, y_train, X_test, y_test)

# モデル保存
print(f"\n[Step 8] モデル保存")
model_path = trainer.save_model("stage2_baseline_timeseries.json")
print(f"  保存先: {model_path}")

# 評価
print(f"\n[Step 9] モデル評価（テストデータ: 2024-06）")
y_pred = trainer.predict(X_test)
auc = roc_auc_score(y_test, y_pred)
logloss = log_loss(y_test, y_pred)

print(f"  AUC: {auc:.4f}")
print(f"  Log Loss: {logloss:.4f}")

# 確率帯別分析
print("\n[Step 10] 確率帯別的中率")
print("-" * 60)
print(f"{'確率帯':<15} {'件数':<10} {'的中数':<10} {'的中率':<10}")
print("-" * 60)

prob_bins = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
for i in range(len(prob_bins) - 1):
    lower = prob_bins[i]
    upper = prob_bins[i + 1]

    mask = (y_pred >= lower) & (y_pred < upper)
    count = mask.sum()

    if count > 0:
        wins = y_test[mask].sum()
        hit_rate = wins / count
        print(f"{lower:.1f}-{upper:.1f}      {count:<10} {int(wins):<10} {hit_rate:>7.2%}")

# 高確率帯分析
high_conf_mask = y_pred >= 0.8
high_conf_count = high_conf_mask.sum()
high_conf_wins = y_test[high_conf_mask].sum()
high_conf_hit_rate = high_conf_wins / high_conf_count if high_conf_count > 0 else 0

print(f"\n[Step 11] 高確率帯（0.8以上）分析")
print(f"  対象レース数: {high_conf_count:,}件")
print(f"  的中数: {int(high_conf_wins):,}件")
print(f"  的中率: {high_conf_hit_rate:.2%}")

# 超高確率帯分析
very_high_conf_mask = y_pred >= 0.9
very_high_conf_count = very_high_conf_mask.sum()
very_high_conf_wins = y_test[very_high_conf_mask].sum()
very_high_conf_hit_rate = very_high_conf_wins / very_high_conf_count if very_high_conf_count > 0 else 0

print(f"\n[Step 12] 超高確率帯（0.9以上）分析")
print(f"  対象レース数: {very_high_conf_count:,}件")
print(f"  的中数: {int(very_high_conf_wins):,}件")
print(f"  的中率: {very_high_conf_hit_rate:.2%}")

# 実験比較
print("\n[Step 13] 実験比較")
print("=" * 70)
print("実験#005（会場・級別あり）vs 実験#006（ベースラインのみ）")
print("-" * 70)

# 実験#005の結果（前回実験から）
exp005_auc = 0.8322
exp005_hit_rate_08 = 66.85  # 0.8以上の的中率
exp005_hit_rate_09 = 73.09  # 0.9以上の的中率

print(f"{'指標':<25} {'実験#005':<15} {'実験#006':<15} {'差分':<15}")
print("-" * 70)
print(f"{'AUC':<25} {exp005_auc:<15.4f} {auc:<15.4f} {auc - exp005_auc:+.4f}")
print(f"{'的中率（0.8+）':<25} {exp005_hit_rate_08:<14.2f}% {high_conf_hit_rate*100:<14.2f}% {high_conf_hit_rate*100 - exp005_hit_rate_08:+.2f}pt")
print(f"{'的中率（0.9+）':<25} {exp005_hit_rate_09:<14.2f}% {very_high_conf_hit_rate*100:<14.2f}% {very_high_conf_hit_rate*100 - exp005_hit_rate_09:+.2f}pt")

# 結論
print("\n[Step 14] 結論")
print("=" * 70)

auc_diff = auc - exp005_auc

if auc_diff < -0.01:
    print(f"[OK] 会場・級別特徴量が明確に有効（AUC {abs(auc_diff):.4f}の向上）")
    print(f"     -> 実験#005（AUC {exp005_auc:.4f}）を推奨モデルとする")
elif auc_diff > 0.01:
    print(f"[WARNING] 会場・級別特徴量がノイズになっている可能性（AUC {auc_diff:.4f}の低下）")
    print(f"          -> 実験#006（AUC {auc:.4f}）を推奨モデルとする")
else:
    print(f"[INFO] 会場・級別特徴量の効果は限定的（AUC差 {auc_diff:.4f}）")
    print(f"       -> データ量減少の影響が大きい可能性")
    print(f"       -> 学習期間を延長（2023年データ追加）を推奨")

print("\n" + "=" * 70)
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
