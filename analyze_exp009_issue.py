"""
実験#009の問題分析スクリプト

問題: 選手特徴量を追加したら性能が低下した（AUC 0.8473 → 0.8166）
原因調査:
1. 追加した特徴量の統計確認
2. 実験#007との特徴量比較
3. データリークの可能性
"""

import sys
sys.path.append('.')

from src.ml.dataset_builder import DatasetBuilder
import pandas as pd
import numpy as np

print("=" * 80)
print("実験#009 問題分析")
print("=" * 80)

# データ読み込み
print("\n[Step 1] データ読み込み")
builder = DatasetBuilder(db_path="data/boatrace.db")

# 学習データ
df_train_raw = builder.build_training_dataset(
    start_date="2023-10-01",
    end_date="2024-05-31",
    venue_codes=None
)
df_train_raw = df_train_raw[df_train_raw['result_rank'].notna()].copy()
df_train_raw['is_win'] = (df_train_raw['result_rank'].astype(str) == '1').astype(int)

print(f"  学習データ: {len(df_train_raw):,}件")

# テストデータ
df_test_raw = builder.build_training_dataset(
    start_date="2024-06-01",
    end_date="2024-06-30",
    venue_codes=None
)
df_test_raw = df_test_raw[df_test_raw['result_rank'].notna()].copy()
df_test_raw['is_win'] = (df_test_raw['result_rank'].astype(str) == '1').astype(int)

print(f"  テストデータ: {len(df_test_raw):,}件")

# === 実験#007と実験#009の特徴量比較 ===
print("\n[Step 2] 実験#007と実験#009の特徴量数比較")
print("-" * 80)

# 実験#007: ベースライン
exp007_features = [
    'pit_number_1', 'pit_number_2', 'pit_number_3', 'pit_number_4', 'pit_number_5', 'pit_number_6',
    'actual_course_1', 'actual_course_2', 'actual_course_3', 'actual_course_4', 'actual_course_5', 'actual_course_6',
    'pit_course_diff',
    # DatasetBuilderが自動追加する特徴量
    'race_number', 'pit_number', 'racer_age', 'racer_weight', 'motor_number', 'boat_number',
    'win_rate', 'second_rate', 'third_rate', 'avg_st',
    'st_time', 'exhibition_time', 'tilt_angle', 'wind_speed', 'wave_height',
    'water_temperature', 'temperature', 'actual_course'
]

# 実験#009: 選手拡張
exp009_new_features = [
    'pit1_win_rate',
    'racer_total_score',
    'pit1_racer_power'
]

print(f"実験#007 特徴量数: {len(exp007_features)}個")
print(f"実験#009 追加特徴量: {len(exp009_new_features)}個")
print(f"実験#009 合計特徴量: {len(exp007_features) + len(exp009_new_features)}個")
print()

# === データセット構築の違いを確認 ===
print("\n[Step 3] DatasetBuilderの出力確認")
print("-" * 80)

# DatasetBuilderが何を返しているか確認
print("DatasetBuilderが返すカラム:")
print(f"  合計: {len(df_train_raw.columns)}カラム")
print()

# DatasetBuilderに含まれていないカラムを確認
missing_in_train = set(exp007_features) - set(df_train_raw.columns)
if missing_in_train:
    print(f"[WARNING] 学習データに含まれていないベースライン特徴量:")
    for col in missing_in_train:
        print(f"  - {col}")
    print()

# === 選手特徴量が原因かを確認 ===
print("\n[Step 4] 選手特徴量の統計確認")
print("-" * 80)

# f_count, l_countの利用可能性確認
if 'f_count' in df_train_raw.columns:
    print("f_count統計（学習データ）:")
    print(f"  平均: {df_train_raw['f_count'].mean():.2f}")
    print(f"  中央値: {df_train_raw['f_count'].median():.0f}")
    print(f"  最大値: {df_train_raw['f_count'].max():.0f}")
    print(f"  欠損率: {df_train_raw['f_count'].isna().mean()*100:.1f}%")
    print()
else:
    print("[ERROR] f_countカラムが存在しません")
    print()

if 'l_count' in df_train_raw.columns:
    print("l_count統計（学習データ）:")
    print(f"  平均: {df_train_raw['l_count'].mean():.2f}")
    print(f"  中央値: {df_train_raw['l_count'].median():.0f}")
    print(f"  最大値: {df_train_raw['l_count'].max():.0f}")
    print(f"  欠損率: {df_train_raw['l_count'].isna().mean()*100:.1f}%")
    print()
else:
    print("[ERROR] l_countカラムが存在しません")
    print()

# motor_second_rate, boat_second_rateの利用可能性確認
if 'motor_second_rate' in df_train_raw.columns:
    print("motor_second_rate統計（学習データ）:")
    print(f"  平均: {df_train_raw['motor_second_rate'].mean():.2f}")
    print(f"  中央値: {df_train_raw['motor_second_rate'].median():.2f}")
    print(f"  最小-最大: {df_train_raw['motor_second_rate'].min():.2f}〜{df_train_raw['motor_second_rate'].max():.2f}")
    print(f"  欠損率: {df_train_raw['motor_second_rate'].isna().mean()*100:.1f}%")
    print()
else:
    print("[ERROR] motor_second_rateカラムが存在しません")
    print()

if 'boat_second_rate' in df_train_raw.columns:
    print("boat_second_rate統計（学習データ）:")
    print(f"  平均: {df_train_raw['boat_second_rate'].mean():.2f}")
    print(f"  中央値: {df_train_raw['boat_second_rate'].median():.2f}")
    print(f"  最小-最大: {df_train_raw['boat_second_rate'].min():.2f}〜{df_train_raw['boat_second_rate'].max():.2f}")
    print(f"  欠損率: {df_train_raw['boat_second_rate'].isna().mean()*100:.1f}%")
    print()
else:
    print("[ERROR] boat_second_rateカラムが存在しません")
    print()

# === 実験#007のスクリプトとの比較 ===
print("\n[Step 5] 実験#007との主要な違い")
print("-" * 80)

# 実験#007では add_baseline_features 関数で特徴量追加
# 実験#009では add_racer_features 関数で特徴量追加

print("実験#007:")
print("  - add_baseline_features()関数を使用")
print("  - 枠番ダミー、コース別ダミー、pit_course_diffのみ追加")
print("  - DatasetBuilderが返す特徴量をそのまま使用")
print()

print("実験#009:")
print("  - add_racer_features()関数を使用")
print("  - 枠番ダミー、コース別ダミー、pit_course_diffに加えて")
print("  - 選手特徴量（pit1_win_rate, racer_total_score等）を追加")
print()

# === 特徴量数の謎を解明 ===
print("\n[Step 6] 特徴量数の不一致の原因")
print("-" * 80)

print("実験#007の結果:")
print("  - 報告された特徴量数: 30個")
print("  - 実際のAUC: 0.8473")
print()

print("実験#009の結果:")
print("  - 報告された特徴量数: 33個")
print("  - 実際のAUC: 0.8166")
print("  - 追加された特徴量: 3個（pit1_win_rate, racer_total_score, pit1_racer_power）")
print()

# DatasetBuilderが返すカラムで数値型のものを確認
numeric_cols = df_train_raw.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'is_place_2', 'is_place_3', 'result_rank']
available_features = [col for col in numeric_cols if col not in exclude_cols]

print(f"DatasetBuilderが返す数値カラム数: {len(available_features)}個")
print()

# === 考えられる原因 ===
print("\n[Step 7] 性能低下の原因仮説")
print("-" * 80)

print("仮説1: 特徴量の追加方法が不適切")
print("  - 実験#009では多くの派生特徴量（reliability_score, equipment_score等）を")
print("    計算したが、最終的に使用されたのは3個のみ")
print("  - 他の特徴量が共通特徴量として認識されなかった可能性")
print()

print("仮説2: データセットの構築が異なる")
print("  - 実験#007と実験#009でDatasetBuilderの返すカラムが異なる可能性")
print("  - 実験#007では30個、実験#009では33個と報告されている")
print()

print("仮説3: 選手特徴量がノイズになっている")
print("  - pit1_win_rateなどの特徴量が過学習を引き起こしている")
print("  - 特に、訓練データから計算した統計をテストデータに適用するため")
print()

# === 次のアクション ===
print("\n[Step 8] 推奨される次のアクション")
print("-" * 80)

print("1. 実験#007を再現して、正確な特徴量リストを確認")
print("2. 実験#009のスクリプトを修正:")
print("   - f_count, l_count, motor_second_rate, boat_second_rateを直接使用")
print("   - 複雑な派生特徴量（reliability_score等）を削除")
print("   - シンプルな特徴量のみを追加")
print("3. 実験#009bとして再実行")
print()

print("=" * 80)
print("分析完了")
print("=" * 80)
