"""
Stage2モデル学習スクリプト（交互作用項追加版）

実験#003: 交互作用項を追加して予測精度が向上するか検証
- actual_course_1 × tenji_time
- actual_course_1 × start_timing
- actual_course_1 × motor_2rate
- tenji_time × start_timing
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
print("Stage2モデル学習 - 交互作用項追加版")
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

# 派生特徴量追加
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

# 交互作用項追加（重要な組み合わせのみ）
print("\n[Step 4] 交互作用項追加")

# 1. 1コース × 展示タイム（1コース取得時の展示タイムの影響）
if 'actual_course_1' in df.columns and 'exhibition_time' in df.columns:
    df['course1_exhibition'] = df['actual_course_1'] * df['exhibition_time']
    print("  [追加] course1_exhibition = actual_course_1 × exhibition_time")

# 2. 1コース × スタートタイミング（1コース取得時のスタートの重要性）
if 'actual_course_1' in df.columns and 'st_time' in df.columns:
    df['course1_st'] = df['actual_course_1'] * df['st_time']
    print("  [追加] course1_st = actual_course_1 × st_time")

# 3. 1コース × モーター2連対率（1コース取得時のモーター性能の影響）
if 'actual_course_1' in df.columns and 'second_rate' in df.columns:
    df['course1_motor'] = df['actual_course_1'] * df['second_rate']
    print("  [追加] course1_motor = actual_course_1 × second_rate")

# 4. 展示タイム × スタートタイミング（両方良い時の相乗効果）
if 'exhibition_time' in df.columns and 'st_time' in df.columns:
    df['exhibition_st'] = df['exhibition_time'] * df['st_time']
    print("  [追加] exhibition_st = exhibition_time × st_time")

# 5. 2コース × 展示タイム（2コースも重要）
if 'actual_course_2' in df.columns and 'exhibition_time' in df.columns:
    df['course2_exhibition'] = df['actual_course_2'] * df['exhibition_time']
    print("  [追加] course2_exhibition = actual_course_2 × exhibition_time")

# 6. 枠番-コース差分 × 展示タイム（進入変化の影響）
if 'pit_course_diff' in df.columns and 'exhibition_time' in df.columns:
    df['diff_exhibition'] = df['pit_course_diff'] * df['exhibition_time']
    print("  [追加] diff_exhibition = pit_course_diff × exhibition_time")

print(f"  交互作用項追加後: {len(df.columns)}カラム")

# 特徴量とラベル分離
print("\n[Step 5] 特徴量とラベル分離")
numeric_cols = df.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'is_place_2', 'is_place_3', 'result_rank']
feature_cols = [col for col in numeric_cols if col not in exclude_cols]

print(f"  特徴量数: {len(feature_cols)}個")
print(f"  ベースライン比: +{len(feature_cols) - 30}個の交互作用項")

X = df[feature_cols].fillna(df[feature_cols].mean())
y = df['is_win']

print(f"  X shape: {X.shape}")
print(f"  y shape: {y.shape}")
print(f"  正例: {y.sum():,}件 ({y.mean()*100:.2f}%)")

# データ分割
print("\n[Step 6] データ分割")
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"  Train: {len(X_train):,}件")
print(f"  Test: {len(X_test):,}件")

# モデル学習
print(f"\n[Step 7] XGBoost学習開始")
trainer = ModelTrainer(model_dir="models")
trainer.train(X_train, y_train, X_test, y_test)

# モデル保存
print(f"\n[Step 8] モデル保存")
model_path = trainer.save_model("stage2_with_interactions_3months.json")
print(f"  保存先: {model_path}")

# 評価
print(f"\n[Step 9] モデル評価")
y_pred = trainer.predict(X_test)
auc = roc_auc_score(y_test, y_pred)
logloss = log_loss(y_test, y_pred)

print(f"  AUC: {auc:.4f}")
print(f"  Log Loss: {logloss:.4f}")

# ベースラインとの比較
print(f"\n[Step 10] ベースラインとの比較")
print(f"  ベースライン AUC: 0.8551")
print(f"  交互作用項版 AUC: {auc:.4f}")
print(f"  差分: {auc - 0.8551:+.4f}")

# 特徴量重要度トップ30（交互作用項がどこにランクインするか）
print(f"\n[Step 11] 特徴量重要度 Top 30")
importance = trainer.get_feature_importance()
if importance is not None:
    # DataFrameの場合の処理
    import pandas as pd
    if isinstance(importance, pd.DataFrame):
        importance_list = list(zip(importance['feature'], importance['importance']))
    else:
        importance_list = importance

    if len(importance_list) > 0:
        print(f"  {'順位':<4} {'特徴量':<35} {'重要度':<10} {'種別'}")
        print("  " + "-" * 65)
        for i, (feat, val) in enumerate(importance_list[:30], 1):
            # 交互作用項かどうか判定
            is_interaction = any(x in feat for x in ['course1', 'course2', 'exhibition', 'diff'])
            feat_type = "🔥交互作用" if is_interaction else "基本"
            print(f"  {i:2d}.  {feat:35s} {val:8.4f}   {feat_type}")

print(f"\n完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
