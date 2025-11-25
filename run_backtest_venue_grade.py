"""
バックテストスクリプト（会場・級別特徴量版）

実験#004モデルのバックテスト
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
print("バックテスト - 会場・級別特徴量版")
print("=" * 70)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# データセット構築
print("\n[Step 1] データセット構築")
builder = DatasetBuilder(db_path="data/boatrace.db")
df_raw = builder.build_training_dataset(
    start_date="2024-04-01",
    end_date="2024-06-30",
    venue_codes=None
)
print(f"  生データ: {len(df_raw):,}件")

df_raw = df_raw[df_raw['result_rank'].notna()].copy()
print(f"  結果あり: {len(df_raw):,}件")

# 目的変数作成
df_raw['is_win'] = (df_raw['result_rank'].astype(str) == '1').astype(int)

# 基本派生特徴量追加
print("\n[Step 2] 特徴量追加")
df = df_raw.copy()

# 枠番ダミー
for i in range(1, 7):
    df[f'pit_number_{i}'] = (df['pit_number'] == i).astype(int)

# コース別ダミー
if 'actual_course' in df.columns:
    for i in range(1, 7):
        df[f'actual_course_{i}'] = (df['actual_course'] == i).astype(int)
    df['pit_course_diff'] = df['pit_number'] - df['actual_course']

# 会場特性特徴量
VENUE_PIT1_WIN_RATE = {
    '01': 55.6, '02': 46.3, '03': 50.0, '04': 41.7, '05': 60.0,
    '06': 62.0, '07': 62.0, '08': 61.1, '09': 72.5, '10': 61.1,
    '11': 66.7, '12': 68.3, '13': 61.9, '14': 49.2, '15': 59.7,
    '16': 61.7, '17': 65.7, '18': 66.7, '19': 56.7, '20': 55.2,
    '21': 61.1, '22': 59.3, '23': 51.9, '24': 75.9
}

VENUE_PIT2_WIN_RATE = {
    '01': 8.3, '02': 15.7, '03': 15.5, '04': 22.6, '05': 14.2,
    '06': 11.1, '07': 10.2, '08': 13.2, '09': 6.7, '10': 15.7,
    '11': 4.8, '12': 8.3, '13': 8.3, '14': 16.7, '15': 9.7,
    '16': 10.0, '17': 10.2, '18': 16.7, '19': 16.7, '20': 19.8,
    '21': 12.0, '22': 19.4, '23': 17.6, '24': 11.1
}

df['venue_pit1_win_rate'] = df['venue_code'].map(VENUE_PIT1_WIN_RATE)
df['venue_pit2_win_rate'] = df['venue_code'].map(VENUE_PIT2_WIN_RATE)
df['venue_inner_bias'] = df['venue_pit1_win_rate'] / (df['venue_pit1_win_rate'] + df['venue_pit2_win_rate'] + 0.001)

def categorize_venue(rate):
    if pd.isna(rate):
        return 'unknown'
    if rate >= 70:
        return 'super_inner'
    elif rate >= 60:
        return 'inner'
    elif rate >= 50:
        return 'balanced'
    else:
        return 'outer'

df['venue_category'] = df['venue_pit1_win_rate'].apply(categorize_venue)
df = pd.get_dummies(df, columns=['venue_category'], prefix='venue_cat')

# 級別特徴量
GRADE_WIN_RATE = {'A1': 25.5, 'A2': 23.5, 'B1': 11.7, 'B2': 5.3}
GRADE_RANK = {'A1': 1, 'A2': 2, 'B1': 3, 'B2': 4}

df['grade_win_rate'] = df['racer_rank'].map(GRADE_WIN_RATE)
df['grade_rank'] = df['racer_rank'].map(GRADE_RANK)
df['is_a_class'] = df['racer_rank'].isin(['A1', 'A2']).astype(int)

# 交互作用項
if 'pit_number_1' in df.columns and 'venue_inner_bias' in df.columns:
    df['pit1_venue_inner'] = df['pit_number_1'] * df['venue_inner_bias']

if 'grade_win_rate' in df.columns and 'venue_inner_bias' in df.columns:
    df['grade_venue_inner'] = df['grade_win_rate'] * df['venue_inner_bias']

if 'pit_number_1' in df.columns and 'is_a_class' in df.columns:
    df['pit1_grade_a'] = df['pit_number_1'] * df['is_a_class']

if 'venue_pit1_win_rate' in df.columns and 'actual_course_1' in df.columns:
    df['venue_course1'] = df['venue_pit1_win_rate'] * df['actual_course_1']

# 特徴量抽出
numeric_cols = df.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'is_place_2', 'is_place_3', 'result_rank']
feature_cols = [col for col in numeric_cols if col not in exclude_cols]

X = df[feature_cols].copy()
for col in X.columns:
    if X[col].isna().any():
        X.loc[:, col] = X[col].fillna(X[col].mean())

y = df['is_win']

print(f"  特徴量数: {len(feature_cols)}個")
print(f"  データ数: {len(X):,}件")

# モデルロード
print("\n[Step 3] モデルロード")
trainer = ModelTrainer(model_dir="models")
trainer.load_model("stage2_with_venue_grade_3months.json")
print("  モデルロード完了")

# 予測
print("\n[Step 4] 予測実行")
y_pred_proba = trainer.predict(X)
y_pred_binary = (y_pred_proba >= 0.5).astype(int)

# 評価
print("\n[Step 5] 総合評価")
auc = roc_auc_score(y, y_pred_proba)
logloss = log_loss(y, y_pred_proba)
accuracy = accuracy_score(y, y_pred_binary)

print(f"  AUC: {auc:.4f}")
print(f"  Log Loss: {logloss:.4f}")
print(f"  Accuracy: {accuracy:.2%}")

# 確率帯別分析
print("\n[Step 6] 確率帯別的中率")
print("-" * 60)
print(f"{'確率帯':<15} {'件数':<10} {'的中数':<10} {'的中率':<10} {'期待値':<10}")
print("-" * 60)

prob_bins = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
for i in range(len(prob_bins) - 1):
    lower = prob_bins[i]
    upper = prob_bins[i + 1]

    mask = (y_pred_proba >= lower) & (y_pred_proba < upper)
    count = mask.sum()

    if count > 0:
        wins = y[mask].sum()
        hit_rate = wins / count
        expected = y_pred_proba[mask].mean()

        print(f"{lower:.1f}-{upper:.1f}      {count:<10} {int(wins):<10} {hit_rate:>7.2%}    {expected:>7.2%}")

# 高確率帯（0.8以上）の詳細分析
print("\n[Step 7] 高確率帯（0.8以上）の分析")
high_conf_mask = y_pred_proba >= 0.8
high_conf_count = high_conf_mask.sum()
high_conf_wins = y[high_conf_mask].sum()
high_conf_hit_rate = high_conf_wins / high_conf_count if high_conf_count > 0 else 0

print(f"  対象レース数: {high_conf_count:,}件")
print(f"  的中数: {int(high_conf_wins):,}件")
print(f"  的中率: {high_conf_hit_rate:.2%}")
print(f"  平均予測確率: {y_pred_proba[high_conf_mask].mean():.2%}")

# 仮想ROI計算（オッズ=1.5と仮定）
if high_conf_count > 0:
    virtual_odds = 1.5
    virtual_return = high_conf_wins * virtual_odds
    virtual_investment = high_conf_count
    virtual_roi = (virtual_return / virtual_investment) * 100

    print(f"\n  仮想投資戦略（オッズ={virtual_odds}と仮定）:")
    print(f"    投資額: {virtual_investment:,}円")
    print(f"    回収額: {virtual_return:,.0f}円")
    print(f"    ROI: {virtual_roi:.2f}%")

# ベースライン比較
print("\n[Step 8] ベースライン比較")
print("-" * 60)
baseline_auc = 0.8551
print(f"  ベースラインAUC:      {baseline_auc:.4f}")
print(f"  会場・級別版AUC:       {auc:.4f}")
print(f"  差分:                 {auc - baseline_auc:+.4f} ({(auc - baseline_auc) / baseline_auc * 100:+.2f}%)")

print(f"\n完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
