"""
SHAP値分析スクリプト

特徴量の寄与度を可視化し、過学習の原因を特定
"""

import sys
sys.path.append('.')

from src.ml.dataset_builder import DatasetBuilder
from src.ml.model_trainer import ModelTrainer
import pandas as pd
import numpy as np
from datetime import datetime

print("=" * 70)
print("SHAP値分析 - 特徴量寄与度の可視化")
print("=" * 70)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

try:
    import shap
    print("  SHAP library loaded successfully")
except ImportError:
    print("\n[ERROR] SHAP library not found")
    print("  Install with: pip install shap")
    sys.exit(1)

# データセット構築（テスト期間）
print("\n[Step 1] テストデータセット構築（2024-06-01〜2024-06-30）")
builder = DatasetBuilder(db_path="data/boatrace.db")
df_test_raw = builder.build_training_dataset(
    start_date="2024-06-01",
    end_date="2024-06-30",
    venue_codes=None
)
print(f"  生データ: {len(df_test_raw):,}件")

df_test_raw = df_test_raw[df_test_raw['result_rank'].notna()].copy()
df_test_raw['is_win'] = (df_test_raw['result_rank'].astype(str) == '1').astype(int)
print(f"  結果あり: {len(df_test_raw):,}件")

# 学習データから会場・級別統計を取得（データ漏洩対策）
print("\n[Step 2] 学習データから統計を取得")
df_train_raw = builder.build_training_dataset(
    start_date="2024-04-01",
    end_date="2024-05-31",
    venue_codes=None
)
df_train_raw = df_train_raw[df_train_raw['result_rank'].notna()].copy()
df_train_raw['is_win'] = (df_train_raw['result_rank'].astype(str) == '1').astype(int)

# 会場別勝率計算
venue_stats = df_train_raw.groupby('venue_code').apply(
    lambda g: pd.Series({
        'pit1_win_rate': (
            g[g['pit_number'] == 1]['is_win'].sum() /
            max((g['pit_number'] == 1).sum(), 1) * 100
        ),
        'pit2_win_rate': (
            g[g['pit_number'] == 2]['is_win'].sum() /
            max((g['pit_number'] == 2).sum(), 1) * 100
        )
    })
).reset_index()

VENUE_PIT1_WIN_RATE = dict(zip(venue_stats['venue_code'], venue_stats['pit1_win_rate']))
VENUE_PIT2_WIN_RATE = dict(zip(venue_stats['venue_code'], venue_stats['pit2_win_rate']))

# 級別勝率計算
grade_stats = df_train_raw.groupby('racer_rank')['is_win'].agg(['sum', 'count'])
grade_stats['win_rate'] = grade_stats['sum'] / grade_stats['count'] * 100
GRADE_WIN_RATE = grade_stats['win_rate'].to_dict()
GRADE_RANK = {'A1': 1, 'A2': 2, 'B1': 3, 'B2': 4}

# 特徴量追加
print("\n[Step 3] テストデータに特徴量追加")
df_test = df_test_raw.copy()

# 枠番ダミー
for i in range(1, 7):
    df_test[f'pit_number_{i}'] = (df_test['pit_number'] == i).astype(int)

# コース別ダミー
if 'actual_course' in df_test.columns:
    for i in range(1, 7):
        df_test[f'actual_course_{i}'] = (df_test['actual_course'] == i).astype(int)
    df_test['pit_course_diff'] = df_test['pit_number'] - df_test['actual_course']

# 会場特性
df_test['venue_pit1_win_rate'] = df_test['venue_code'].map(VENUE_PIT1_WIN_RATE)
df_test['venue_pit2_win_rate'] = df_test['venue_code'].map(VENUE_PIT2_WIN_RATE)
df_test['venue_inner_bias'] = df_test['venue_pit1_win_rate'] / (
    df_test['venue_pit1_win_rate'] + df_test['venue_pit2_win_rate'] + 0.001
)

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

df_test['venue_category'] = df_test['venue_pit1_win_rate'].apply(categorize_venue)
df_test = pd.get_dummies(df_test, columns=['venue_category'], prefix='venue_cat')

# 級別特徴量
df_test['grade_win_rate'] = df_test['racer_rank'].map(GRADE_WIN_RATE)
df_test['grade_rank'] = df_test['racer_rank'].map(GRADE_RANK)
df_test['is_a_class'] = df_test['racer_rank'].isin(['A1', 'A2']).astype(int)

# 交互作用項
if 'pit_number_1' in df_test.columns and 'venue_inner_bias' in df_test.columns:
    df_test['pit1_venue_inner'] = df_test['pit_number_1'] * df_test['venue_inner_bias']

if 'grade_win_rate' in df_test.columns and 'venue_inner_bias' in df_test.columns:
    df_test['grade_venue_inner'] = df_test['grade_win_rate'] * df_test['venue_inner_bias']

if 'pit_number_1' in df_test.columns and 'is_a_class' in df_test.columns:
    df_test['pit1_grade_a'] = df_test['pit_number_1'] * df_test['is_a_class']

if 'venue_pit1_win_rate' in df_test.columns and 'actual_course_1' in df_test.columns:
    df_test['venue_course1'] = df_test['venue_pit1_win_rate'] * df_test['actual_course_1']

# 特徴量抽出
numeric_cols = df_test.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'is_place_2', 'is_place_3', 'result_rank']
feature_cols = [col for col in numeric_cols if col not in exclude_cols]
feature_cols = sorted(feature_cols)

X_test = df_test[feature_cols].copy()
for col in X_test.columns:
    if X_test[col].isna().any():
        X_test.loc[:, col] = X_test[col].fillna(X_test[col].mean())

y_test = df_test['is_win']

print(f"  特徴量数: {len(feature_cols)}個")
print(f"  データ数: {len(X_test):,}件")

# モデルロード
print("\n[Step 4] モデルロード")
trainer = ModelTrainer(model_dir="models")
trainer.load_model("stage2_venue_grade_timeseries.json")
print("  モデルロード完了")

# SHAP値計算（サンプル100件で高速化）
print("\n[Step 5] SHAP値計算（サンプル100件）")
print("  計算中...")

# サンプリング
sample_size = min(100, len(X_test))
X_sample = X_test.sample(n=sample_size, random_state=42)

# TreeExplainerを使用
explainer = shap.TreeExplainer(trainer.model)
shap_values = explainer.shap_values(X_sample)

print(f"  完了: SHAP values shape = {shap_values.shape}")

# SHAP値の統計
print("\n[Step 6] SHAP値統計")

# 特徴量ごとの平均絶対SHAP値
mean_abs_shap = np.abs(shap_values).mean(axis=0)
feature_importance_shap = pd.DataFrame({
    'feature': X_sample.columns,
    'mean_abs_shap': mean_abs_shap
}).sort_values('mean_abs_shap', ascending=False)

print("\n特徴量重要度（平均絶対SHAP値）Top 20:")
print("-" * 60)
print(f"{'順位':<4} {'特徴量':<40} {'平均|SHAP|':<12}")
print("-" * 60)

for i, row in feature_importance_shap.head(20).iterrows():
    feat_type = ""
    if any(x in row['feature'] for x in ['venue', 'grade', 'is_a_class']):
        feat_type = " [会場/級別]"
    elif any(x in row['feature'] for x in ['pit1_venue', 'grade_venue', 'pit1_grade', 'venue_course']):
        feat_type = " [交互作用]"

    print(f"{feature_importance_shap.index.get_loc(i)+1:2d}.  {row['feature']:40s} {row['mean_abs_shap']:10.4f}{feat_type}")

# 会場・級別系特徴量の寄与度
print("\n\n[Step 7] 会場・級別系特徴量の寄与度分析")

venue_grade_features = [f for f in feature_cols if any(x in f for x in ['venue', 'grade', 'is_a_class'])]
venue_grade_shap = feature_importance_shap[feature_importance_shap['feature'].isin(venue_grade_features)]

total_shap = feature_importance_shap['mean_abs_shap'].sum()
venue_grade_total = venue_grade_shap['mean_abs_shap'].sum()
venue_grade_ratio = venue_grade_total / total_shap * 100

print(f"\n会場・級別系特徴量数: {len(venue_grade_features)}個")
print(f"全特徴量数: {len(feature_cols)}個")
print(f"会場・級別系の寄与度割合: {venue_grade_ratio:.2f}%")

print("\n会場・級別系特徴量の寄与度:")
print("-" * 60)
for i, row in venue_grade_shap.head(10).iterrows():
    ratio = row['mean_abs_shap'] / total_shap * 100
    print(f"  {row['feature']:40s} {row['mean_abs_shap']:8.4f} ({ratio:5.2f}%)")

# 高確率予測の事例分析
print("\n\n[Step 8] 高確率予測（0.9以上）の特徴量寄与")

y_pred = trainer.predict(X_test)
high_conf_idx = X_test.index[y_pred >= 0.9][:5]  # 上位5件

if len(high_conf_idx) > 0:
    print(f"\n高確率予測事例（{len(high_conf_idx)}件）:")
    print("-" * 80)

    for idx in high_conf_idx:
        pred_prob = y_pred[X_test.index == idx].iloc[0]
        actual = y_test[idx]

        # 該当レースのSHAP値を取得（サンプル内にあれば）
        if idx in X_sample.index:
            sample_idx = X_sample.index.get_loc(idx)
            shap_vals = shap_values[sample_idx]

            # 上位5特徴量を表示
            top_contrib = pd.DataFrame({
                'feature': X_sample.columns,
                'shap_value': shap_vals,
                'feature_value': X_sample.loc[idx].values
            }).sort_values('shap_value', ascending=False).head(5)

            print(f"\nレースID: {df_test.loc[idx, 'race_id'] if 'race_id' in df_test.columns else 'N/A'}")
            print(f"  予測確率: {pred_prob:.2%}, 実際: {'勝' if actual == 1 else '負'}")
            print(f"  主要寄与特徴量:")

            for _, contrib_row in top_contrib.iterrows():
                print(f"    {contrib_row['feature']:30s} = {contrib_row['feature_value']:8.2f} (SHAP: {contrib_row['shap_value']:+.4f})")

print(f"\n完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
print("\n注: SHAP値分析により、会場・級別特徴量の実際の寄与度が明らかになりました。")
print("   高い寄与度 = 予測に大きく影響している特徴量")
