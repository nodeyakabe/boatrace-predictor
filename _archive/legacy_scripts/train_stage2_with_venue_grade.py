"""
Stage2モデル学習スクリプト（会場・級別特徴量追加版）

実験#004: 会場特性と級別情報を特徴量化して予測精度を向上
- venue_pit1_win_rate（会場別1号艇勝率）
- venue_category（会場カテゴリ: super_inner/inner/balanced/outer）
- grade_win_rate（級別平均勝率）
- is_a_class（A級フラグ）
- pit1_venue_inner（1号艇×会場インコース有利度の交互作用）
"""

import sys
sys.path.append('.')

from src.ml.dataset_builder import DatasetBuilder
from src.ml.model_trainer import ModelTrainer
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, log_loss
from datetime import datetime
import pandas as pd
import numpy as np

print("=" * 70)
print("Stage2モデル学習 - 会場・級別特徴量追加版")
print("=" * 70)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# データセット構築
print("\n[Step 1] データセット構築（2024-04-01〜2024-06-30）")
builder = DatasetBuilder(db_path="data/boatrace.db")
df_raw = builder.build_training_dataset(start_date="2024-04-01", end_date="2024-06-30", venue_codes=None)
print(f"  生データ: {len(df_raw):,}件")

# 結果がないデータを除外
df_raw = df_raw[df_raw['result_rank'].notna()].copy()
print(f"  結果あり: {len(df_raw):,}件")

# 目的変数作成
print("\n[Step 2] 目的変数作成")
df_raw['is_win'] = (df_raw['result_rank'].astype(str) == '1').astype(int)
print(f"  is_win: {df_raw['is_win'].sum():,}件")

# 基本派生特徴量追加
print("\n[Step 3] 基本派生特徴量追加")
df = df_raw.copy()

# 枠番ダミー
for i in range(1, 7):
    df[f'pit_number_{i}'] = (df['pit_number'] == i).astype(int)

# コース別ダミー
if 'actual_course' in df.columns:
    for i in range(1, 7):
        df[f'actual_course_{i}'] = (df['actual_course'] == i).astype(int)
    # 枠-コース差分
    df['pit_course_diff'] = df['pit_number'] - df['actual_course']

print(f"  基本特徴量追加後: {len(df.columns)}カラム")

# 会場特性特徴量追加
print("\n[Step 4] 会場特性特徴量追加")

# 会場別1号艇勝率マッピング（分析結果より）
VENUE_PIT1_WIN_RATE = {
    '01': 55.6, '02': 46.3, '03': 50.0, '04': 41.7, '05': 60.0,
    '06': 62.0, '07': 62.0, '08': 61.1, '09': 72.5, '10': 61.1,
    '11': 66.7, '12': 68.3, '13': 61.9, '14': 49.2, '15': 59.7,
    '16': 61.7, '17': 65.7, '18': 66.7, '19': 56.7, '20': 55.2,
    '21': 61.1, '22': 59.3, '23': 51.9, '24': 75.9
}

# 会場別2号艇勝率マッピング
VENUE_PIT2_WIN_RATE = {
    '01': 8.3, '02': 15.7, '03': 15.5, '04': 22.6, '05': 14.2,
    '06': 11.1, '07': 10.2, '08': 13.2, '09': 6.7, '10': 15.7,
    '11': 4.8, '12': 8.3, '13': 8.3, '14': 16.7, '15': 9.7,
    '16': 10.0, '17': 10.2, '18': 16.7, '19': 16.7, '20': 19.8,
    '21': 12.0, '22': 19.4, '23': 17.6, '24': 11.1
}

# 1. venue_pit1_win_rate（会場別1号艇勝率）
df['venue_pit1_win_rate'] = df['venue_code'].map(VENUE_PIT1_WIN_RATE)
print("  [追加] venue_pit1_win_rate")

# 2. venue_inner_bias（会場のインコース有利度）
df['venue_pit2_win_rate'] = df['venue_code'].map(VENUE_PIT2_WIN_RATE)
df['venue_inner_bias'] = df['venue_pit1_win_rate'] / (df['venue_pit1_win_rate'] + df['venue_pit2_win_rate'] + 0.001)
print("  [追加] venue_inner_bias")

# 3. venue_category（会場カテゴリ）
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
print("  [追加] venue_category (ダミー変数化)")

# 級別特徴量追加
print("\n[Step 5] 級別特徴量追加")

# 級別平均勝率マッピング（分析結果より）
GRADE_WIN_RATE = {'A1': 25.5, 'A2': 23.5, 'B1': 11.7, 'B2': 5.3}
GRADE_RANK = {'A1': 1, 'A2': 2, 'B1': 3, 'B2': 4}

# 1. grade_win_rate（級別平均勝率）
df['grade_win_rate'] = df['racer_rank'].map(GRADE_WIN_RATE)
print("  [追加] grade_win_rate")

# 2. grade_rank（級別順位）
df['grade_rank'] = df['racer_rank'].map(GRADE_RANK)
print("  [追加] grade_rank")

# 3. is_a_class（A級フラグ）
df['is_a_class'] = df['racer_rank'].isin(['A1', 'A2']).astype(int)
print("  [追加] is_a_class")

# 交互作用項追加
print("\n[Step 6] 交互作用項追加")

# 1. pit1_venue_inner（1号艇×会場インコース有利度）
if 'pit_number_1' in df.columns and 'venue_inner_bias' in df.columns:
    df['pit1_venue_inner'] = df['pit_number_1'] * df['venue_inner_bias']
    print("  [追加] pit1_venue_inner = pit_number_1 × venue_inner_bias")

# 2. grade_venue_inner（級別勝率×会場インコース有利度）
if 'grade_win_rate' in df.columns and 'venue_inner_bias' in df.columns:
    df['grade_venue_inner'] = df['grade_win_rate'] * df['venue_inner_bias']
    print("  [追加] grade_venue_inner = grade_win_rate × venue_inner_bias")

# 3. pit1_grade_a1（1号艇×A級）
if 'pit_number_1' in df.columns and 'is_a_class' in df.columns:
    df['pit1_grade_a'] = df['pit_number_1'] * df['is_a_class']
    print("  [追加] pit1_grade_a = pit_number_1 × is_a_class")

# 4. venue_pit1_rate × actual_course_1（会場1号艇勝率×1コース取得）
if 'venue_pit1_win_rate' in df.columns and 'actual_course_1' in df.columns:
    df['venue_course1'] = df['venue_pit1_win_rate'] * df['actual_course_1']
    print("  [追加] venue_course1 = venue_pit1_win_rate × actual_course_1")

print(f"  特徴量追加後: {len(df.columns)}カラム")

# 特徴量とラベル分離
print("\n[Step 7] 特徴量とラベル分離")
numeric_cols = df.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'is_place_2', 'is_place_3', 'result_rank']
feature_cols = [col for col in numeric_cols if col not in exclude_cols]

print(f"  特徴量数: {len(feature_cols)}個")
print(f"  ベースライン比: +{len(feature_cols) - 30}個の会場・級別特徴量")

# 欠損値処理
X = df[feature_cols].copy()
for col in X.columns:
    if X[col].isna().any():
        X[col].fillna(X[col].mean(), inplace=True)

y = df['is_win']

print(f"  X shape: {X.shape}")
print(f"  y shape: {y.shape}")
print(f"  正例: {y.sum():,}件 ({y.mean()*100:.2f}%)")

# データ分割
print("\n[Step 8] データ分割")
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"  Train: {len(X_train):,}件")
print(f"  Test: {len(X_test):,}件")

# モデル学習
print(f"\n[Step 9] XGBoost学習開始")
trainer = ModelTrainer(model_dir="models")
trainer.train(X_train, y_train, X_test, y_test)

# モデル保存
print(f"\n[Step 10] モデル保存")
model_path = trainer.save_model("stage2_with_venue_grade_3months.json")
print(f"  保存先: {model_path}")

# 評価
print(f"\n[Step 11] モデル評価")
y_pred = trainer.predict(X_test)
auc = roc_auc_score(y_test, y_pred)
logloss = log_loss(y_test, y_pred)

print(f"  AUC: {auc:.4f}")
print(f"  Log Loss: {logloss:.4f}")

# ベースラインとの比較
print(f"\n[Step 12] ベースラインとの比較")
baseline_auc = 0.8551
print(f"  ベースライン AUC: {baseline_auc:.4f}")
print(f"  会場・級別版 AUC: {auc:.4f}")
print(f"  差分: {auc - baseline_auc:+.4f} ({(auc - baseline_auc) / baseline_auc * 100:+.2f}%)")

if auc > baseline_auc:
    print(f"  結果: 改善 (+{(auc - baseline_auc) * 100:.2f}%)")
else:
    print(f"  結果: 悪化 ({(auc - baseline_auc) * 100:.2f}%)")

# 特徴量重要度トップ40（会場・級別系がどこにランクインするか）
print(f"\n[Step 13] 特徴量重要度 Top 40")
importance = trainer.get_feature_importance()
if importance is not None:
    import pandas as pd
    if isinstance(importance, pd.DataFrame):
        importance_list = list(zip(importance['feature'], importance['importance']))
    else:
        importance_list = importance

    if len(importance_list) > 0:
        print(f"  {'順位':<4} {'特徴量':<40} {'重要度':<10} {'種別'}")
        print("  " + "-" * 75)
        for i, (feat, val) in enumerate(importance_list[:40], 1):
            # 特徴量種別判定
            if any(x in feat for x in ['venue', 'grade', 'is_a_class']):
                feat_type = "会場/級別"
            elif any(x in feat for x in ['pit1_venue', 'grade_venue', 'pit1_grade', 'venue_course']):
                feat_type = "交互作用"
            elif 'actual_course' in feat:
                feat_type = "コース"
            elif 'pit_number' in feat:
                feat_type = "枠番"
            else:
                feat_type = "基本"

            print(f"  {i:2d}.  {feat:40s} {val:8.4f}   {feat_type}")

print(f"\n完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
