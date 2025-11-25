"""
Stage2モデル学習スクリプト（選手特徴量込み）

racer_featuresとracer_venue_featuresを使って、
選手の過去成績を特徴量として追加したモデルを学習
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
print("Stage2モデル学習 - 選手特徴量込み")
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
df_raw['is_place_2'] = (df_raw['result_rank'].astype(str).isin(['1', '2'])).astype(int)
df_raw['is_place_3'] = (df_raw['result_rank'].astype(str).isin(['1', '2', '3'])).astype(int)
print(f"  is_win: {df_raw['is_win'].sum():,}件")

# 選手特徴量結合
print("\n[Step 3] 選手特徴量結合")
import sqlite3
conn = sqlite3.connect("data/boatrace.db")

# racer_features取得
df_racer_features = pd.read_sql_query("""
    SELECT
        racer_number,
        race_date,
        recent_avg_rank_3,
        recent_avg_rank_5,
        recent_avg_rank_10,
        recent_win_rate_3,
        recent_win_rate_5,
        recent_win_rate_10,
        total_races
    FROM racer_features
""", conn)
print(f"  racer_features: {len(df_racer_features):,}件")

# racer_venue_features取得
df_venue_features = pd.read_sql_query("""
    SELECT
        racer_number,
        venue_code,
        race_date,
        venue_win_rate,
        venue_avg_rank,
        venue_races
    FROM racer_venue_features
""", conn)
print(f"  racer_venue_features: {len(df_venue_features):,}件")

conn.close()

# データ結合
print("\n[Step 4] データ結合")
# race_idからrace_dateとvenue_codeを取得
df_raw_with_date = df_raw.merge(
    df_raw[['race_id', 'race_date', 'venue_code']].drop_duplicates(),
    on='race_id',
    how='left',
    suffixes=('', '_y')
)

# racer_featuresと結合
df = df_raw_with_date.merge(
    df_racer_features,
    on=['racer_number', 'race_date'],
    how='left'
)
print(f"  racer_features結合後: {len(df):,}件")

# venue_featuresと結合
df = df.merge(
    df_venue_features,
    on=['racer_number', 'venue_code', 'race_date'],
    how='left'
)
print(f"  venue_features結合後: {len(df):,}件")

# 派生特徴量追加
print("\n[Step 5] 派生特徴量追加")

# 枠番ダミー
for i in range(1, 7):
    df[f'pit_number_{i}'] = (df['pit_number'] == i).astype(int)

# コース別ダミー
if 'actual_course' in df.columns:
    for i in range(1, 7):
        df[f'actual_course_{i}'] = (df['actual_course'] == i).astype(int)
    # 枠-コース差分
    df['pit_course_diff'] = df['pit_number'] - df['actual_course']

print(f"  派生特徴量追加後: {len(df.columns)}カラム")

# 特徴量とラベル分離
print("\n[Step 6] 特徴量とラベル分離")
numeric_cols = df.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'is_place_2', 'is_place_3', 'result_rank']
feature_cols = [col for col in numeric_cols if col not in exclude_cols]

print(f"  特徴量数: {len(feature_cols)}個")
print(f"  選手特徴量追加分: recent_avg_rank_*, recent_win_rate_*, venue_win_rate, venue_avg_rank")

X = df[feature_cols].fillna(df[feature_cols].mean())
y = df['is_win']

print(f"  X shape: {X.shape}")
print(f"  y shape: {y.shape}")
print(f"  正例: {y.sum():,}件 ({y.mean()*100:.2f}%)")

# データ分割
print("\n[Step 7] データ分割")
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"  Train: {len(X_train):,}件")
print(f"  Test: {len(X_test):,}件")

# モデル学習
print(f"\n[Step 8] XGBoost学習開始")
trainer = ModelTrainer(model_dir="models")
trainer.train(X_train, y_train, X_test, y_test)

# モデル保存
print(f"\n[Step 9] モデル保存")
model_path = trainer.save_model("stage2_with_racer_features_3months.json")
print(f"  保存先: {model_path}")

# 評価
print(f"\n[Step 10] モデル評価")
y_pred = trainer.predict(X_test)
auc = roc_auc_score(y_test, y_pred)
logloss = log_loss(y_test, y_pred)

print(f"  AUC: {auc:.4f}")
print(f"  Log Loss: {logloss:.4f}")

# 特徴量重要度トップ20
print(f"\n[Step 11] 特徴量重要度 Top 20")
importance = trainer.get_feature_importance()
if importance:
    for i, (feat, val) in enumerate(importance[:20], 1):
        print(f"  {i:2d}. {feat:30s}: {val:.4f}")

print(f"\n完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
