"""
Stage2モデル学習スクリプト（会場・級別8ヶ月学習版）

実験#008: データ量と会場・級別特徴量を組み合わせて最高性能を目指す
- 学習期間: 2023-10-01 〜 2024-05-31（8ヶ月）
- テスト期間: 2024-06-01 〜 2024-06-30（1ヶ月）
- 特徴量: 44個（ベースライン30 + 会場・級別14）
- 目的: AUC 0.85以上、的中率（0.8+）70%以上を達成
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
print("Stage2モデル学習 - 会場・級別8ヶ月学習版（実験#008）")
print("=" * 70)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# データセット構築（学習用: 8ヶ月）
print("\n[Step 1] 学習データセット構築（2023-10-01〜2024-05-31: 8ヶ月）")
builder = DatasetBuilder(db_path="data/boatrace.db")
df_train_raw = builder.build_training_dataset(
    start_date="2023-10-01",
    end_date="2024-05-31",
    venue_codes=None
)
print(f"  生データ: {len(df_train_raw):,}件")

df_train_raw = df_train_raw[df_train_raw['result_rank'].notna()].copy()
print(f"  結果あり: {len(df_train_raw):,}件")

# データセット構築（テスト用: 1ヶ月）
print("\n[Step 2] テストデータセット構築（2024-06-01〜2024-06-30: 1ヶ月）")
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

print(f"  学習データ正例: {df_train_raw['is_win'].sum():,}件 ({df_train_raw['is_win'].mean()*100:.2f}%)")
print(f"  テストデータ正例: {df_test_raw['is_win'].sum():,}件 ({df_test_raw['is_win'].mean()*100:.2f}%)")

# 会場別勝率を学習データのみから計算（データ漏洩対策）
print("\n[Step 3] 会場別勝率計算（学習データのみ）")

# 学習データから会場別統計を計算
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

print(f"  会場数: {len(VENUE_PIT1_WIN_RATE)}")
print(f"  1号艇勝率範囲: {min(VENUE_PIT1_WIN_RATE.values()):.1f}% 〜 {max(VENUE_PIT1_WIN_RATE.values()):.1f}%")

# 級別勝率を学習データのみから計算
print("\n[Step 4] 級別勝率計算（学習データのみ）")

grade_stats = df_train_raw.groupby('racer_rank')['is_win'].agg(['sum', 'count'])
grade_stats['win_rate'] = grade_stats['sum'] / grade_stats['count'] * 100

GRADE_WIN_RATE = grade_stats['win_rate'].to_dict()
GRADE_RANK = {'A1': 1, 'A2': 2, 'B1': 3, 'B2': 4}

print(f"  級別数: {len(GRADE_WIN_RATE)}")
for grade, rate in sorted(GRADE_WIN_RATE.items()):
    print(f"    {grade}: {rate:.2f}%")

# 特徴量追加関数
def add_features(df, venue_pit1_map, venue_pit2_map, grade_win_map):
    """特徴量を追加する共通関数（会場・級別特徴量あり）"""
    df = df.copy()

    # 枠番ダミー
    for i in range(1, 7):
        df[f'pit_number_{i}'] = (df['pit_number'] == i).astype(int)

    # コース別ダミー
    if 'actual_course' in df.columns:
        for i in range(1, 7):
            df[f'actual_course_{i}'] = (df['actual_course'] == i).astype(int)
        df['pit_course_diff'] = df['pit_number'] - df['actual_course']

    # 会場特性特徴量
    df['venue_pit1_win_rate'] = df['venue_code'].map(venue_pit1_map)
    df['venue_pit2_win_rate'] = df['venue_code'].map(venue_pit2_map)
    df['venue_inner_bias'] = df['venue_pit1_win_rate'] / (
        df['venue_pit1_win_rate'] + df['venue_pit2_win_rate'] + 0.001
    )

    # 会場カテゴリ
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
    df['grade_win_rate'] = df['racer_rank'].map(grade_win_map)
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

    return df

# 学習データに特徴量追加
print("\n[Step 5] 学習データに特徴量追加（会場・級別あり）")
df_train = add_features(df_train_raw, VENUE_PIT1_WIN_RATE, VENUE_PIT2_WIN_RATE, GRADE_WIN_RATE)
print(f"  特徴量追加後: {len(df_train.columns)}カラム")

# テストデータに特徴量追加（同じマッピングを使用）
print("\n[Step 6] テストデータに特徴量追加（会場・級別あり）")
df_test = add_features(df_test_raw, VENUE_PIT1_WIN_RATE, VENUE_PIT2_WIN_RATE, GRADE_WIN_RATE)
print(f"  特徴量追加後: {len(df_test.columns)}カラム")

# 共通の特徴量カラムを抽出
train_numeric_cols = df_train.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
test_numeric_cols = df_test.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'is_place_2', 'is_place_3', 'result_rank']

# 学習とテストで共通の特徴量のみ使用
common_features = set(train_numeric_cols) & set(test_numeric_cols)
feature_cols = [col for col in common_features if col not in exclude_cols]
feature_cols = sorted(feature_cols)  # 順序を固定

print(f"\n[Step 7] 特徴量抽出")
print(f"  共通特徴量数: {len(feature_cols)}個")

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

print(f"  X_train shape: {X_train.shape}")
print(f"  X_test shape: {X_test.shape}")
print(f"  y_train 正例: {y_train.sum():,}件 ({y_train.mean()*100:.2f}%)")
print(f"  y_test 正例: {y_test.sum():,}件 ({y_test.mean()*100:.2f}%)")

# データ量の比較
print(f"\n[参考] データ量の比較:")
print(f"  実験#005（2ヶ月、44特徴）: 9,881件")
print(f"  実験#007（8ヶ月、30特徴）: 39,771件")
print(f"  実験#008（8ヶ月、{len(feature_cols)}特徴）: {len(X_train):,}件")

# モデル学習
print(f"\n[Step 8] XGBoost学習開始")
trainer = ModelTrainer(model_dir="models")
trainer.train(X_train, y_train, X_test, y_test)

# モデル保存
print(f"\n[Step 9] モデル保存")
model_path = trainer.save_model("stage2_venue_grade_8months.json")
print(f"  保存先: {model_path}")

# 評価
print(f"\n[Step 10] モデル評価（テストデータ: 2024-06）")
y_pred = trainer.predict(X_test)
auc = roc_auc_score(y_test, y_pred)
logloss = log_loss(y_test, y_pred)

print(f"  AUC: {auc:.4f}")
print(f"  Log Loss: {logloss:.4f}")

# 確率帯別分析
print("\n[Step 11] 確率帯別的中率")
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

print(f"\n[Step 12] 高確率帯（0.8以上）分析")
print(f"  対象レース数: {high_conf_count:,}件")
print(f"  的中数: {int(high_conf_wins):,}件")
print(f"  的中率: {high_conf_hit_rate:.2%}")

# 超高確率帯分析
very_high_conf_mask = y_pred >= 0.9
very_high_conf_count = very_high_conf_mask.sum()
very_high_conf_wins = y_test[very_high_conf_mask].sum()
very_high_conf_hit_rate = very_high_conf_wins / very_high_conf_count if very_high_conf_count > 0 else 0

print(f"\n[Step 13] 超高確率帯（0.9以上）分析")
print(f"  対象レース数: {very_high_conf_count:,}件")
print(f"  的中数: {int(very_high_conf_wins):,}件")
print(f"  的中率: {very_high_conf_hit_rate:.2%}")

# 実験比較
print("\n[Step 14] 実験比較")
print("=" * 70)
print("データ量 × 特徴量による性能変化")
print("-" * 70)

# 過去の実験結果
exp005_auc = 0.8322  # 2ヶ月、44特徴
exp005_hit_rate_08 = 66.85
exp005_hit_rate_09 = 73.09

exp007_auc = 0.8473  # 8ヶ月、30特徴
exp007_hit_rate_08 = 66.45
exp007_hit_rate_09 = 72.21

print(f"{'指標':<25} {'実験#005':<15} {'実験#007':<15} {'実験#008':<15}")
print(f"{'　　':<25} {'(2ヶ月,44特徴)':<15} {'(8ヶ月,30特徴)':<15} {'(8ヶ月,44特徴)':<15}")
print("-" * 70)
print(f"{'学習データ数':<25} {'9,881件':<15} {'39,771件':<15} {f'{len(X_train):,}件':<15}")
print(f"{'AUC':<25} {exp005_auc:<15.4f} {exp007_auc:<15.4f} {auc:<15.4f}")
print(f"{'的中率（0.8+）':<25} {exp005_hit_rate_08:<14.2f}% {exp007_hit_rate_08:<14.2f}% {high_conf_hit_rate*100:<14.2f}%")
print(f"{'的中率（0.9+）':<25} {exp005_hit_rate_09:<14.2f}% {exp007_hit_rate_09:<14.2f}% {very_high_conf_hit_rate*100:<14.2f}%")

# 目標達成確認
print("\n[Step 15] 目標達成確認")
print("=" * 70)

target_auc = 0.85
target_hit_rate = 70.0

print(f"目標値:")
print(f"  AUC: {target_auc:.2f}以上")
print(f"  的中率（0.8+）: {target_hit_rate:.1f}%以上")
print()
print(f"実績値:")
print(f"  AUC: {auc:.4f} {'[達成]' if auc >= target_auc else '[未達成]'}")
print(f"  的中率（0.8+）: {high_conf_hit_rate*100:.2f}% {'[達成]' if high_conf_hit_rate*100 >= target_hit_rate else '[未達成]'}")

# 結論
print("\n[Step 16] 結論")
print("=" * 70)

auc_vs_exp007 = auc - exp007_auc
hit_rate_vs_exp007 = high_conf_hit_rate * 100 - exp007_hit_rate_08

if auc >= target_auc and high_conf_hit_rate * 100 >= target_hit_rate:
    print(f"[SUCCESS] 目標を達成！")
    print(f"          AUC {auc:.4f}、的中率（0.8+）{high_conf_hit_rate*100:.2f}%")
    print(f"          -> 実験#008を最終推奨モデルとする")
elif auc >= exp007_auc + 0.005:
    print(f"[OK] 会場・級別特徴量が有効（AUC {auc_vs_exp007:+.4f}）")
    print(f"     的中率も{hit_rate_vs_exp007:+.2f}pt向上" if hit_rate_vs_exp007 > 0 else f"     的中率は{abs(hit_rate_vs_exp007):.2f}pt低下")
    print(f"     -> 実験#008を推奨モデルとする")
elif auc >= exp007_auc - 0.002:
    print(f"[INFO] 会場・級別特徴量の効果は限定的（AUC差 {auc_vs_exp007:+.4f}）")
    if hit_rate_vs_exp007 > 1:
        print(f"       ただし、的中率は{hit_rate_vs_exp007:+.2f}pt向上")
        print(f"       -> 実験#008を推奨（的中率優先）")
    else:
        print(f"       -> 実験#007と実験#008の両方を候補とする")
else:
    print(f"[WARNING] 会場・級別特徴量が性能低下を招いた（AUC {auc_vs_exp007:+.4f}）")
    print(f"          -> 実験#007（ベースライン）を推奨")

print("\n" + "=" * 70)
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
