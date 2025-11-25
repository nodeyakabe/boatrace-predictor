"""
Stage2モデル学習スクリプト（会場・級別+選手特徴量併用版）

実験#010: 会場・級別特徴量と選手特徴量を併用して最高性能を目指す
- 学習期間: 2023-10-01 〜 2024-05-31（8ヶ月）
- テスト期間: 2024-06-01 〜 2024-06-30（1ヶ月）
- 特徴量: ベースライン30 + 会場・級別14 + 選手基本4 = 48個
- 目的: 全ての有効特徴量を組み合わせて性能向上
- 期待: AUC 0.855以上、的中率（0.8+）68%以上
"""

import sys
sys.path.append('.')

import sqlite3
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score, log_loss
from datetime import datetime
from src.ml.model_trainer import ModelTrainer

print("=" * 80)
print("Stage2モデル学習 - 会場・級別+選手特徴量併用版（実験#010）")
print("=" * 80)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def load_dataset(start_date, end_date):
    """データベースから学習データを取得"""
    conn = sqlite3.connect('data/boatrace.db')

    query = f"""
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,

            e.pit_number,
            e.racer_number,
            e.racer_name,
            e.racer_rank,
            e.racer_age,
            e.racer_weight,
            e.motor_number,
            e.boat_number,
            e.win_rate,
            e.second_rate,
            e.third_rate,
            e.f_count,
            e.l_count,
            e.avg_st,
            e.motor_second_rate,
            e.motor_third_rate,
            e.boat_second_rate,
            e.boat_third_rate,

            rd.exhibition_time,
            rd.tilt_angle,
            rd.actual_course,
            rd.st_time,

            w.temperature,
            w.wind_speed,
            w.water_temperature,
            w.wave_height,

            res.rank as result_rank

        FROM entries e
        JOIN races r ON e.race_id = r.id
        LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
        LEFT JOIN weather w ON r.venue_code = w.venue_code
            AND DATE(r.race_date) = DATE(w.weather_date)
        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
        WHERE r.race_date BETWEEN ? AND ?
        ORDER BY r.race_date, r.venue_code, r.race_number, e.pit_number
    """

    df = pd.read_sql_query(query, conn, params=[start_date, end_date])
    conn.close()

    return df

# データセット構築
print("\n[Step 1] 学習データセット構築（2023-10-01〜2024-05-31: 8ヶ月）")
df_train_raw = load_dataset("2023-10-01", "2024-05-31")
print(f"  生データ: {len(df_train_raw):,}件")

df_train_raw = df_train_raw[df_train_raw['result_rank'].notna()].copy()
print(f"  結果あり: {len(df_train_raw):,}件")

print("\n[Step 2] テストデータセット構築（2024-06-01〜2024-06-30: 1ヶ月）")
df_test_raw = load_dataset("2024-06-01", "2024-06-30")
print(f"  生データ: {len(df_test_raw):,}件")

df_test_raw = df_test_raw[df_test_raw['result_rank'].notna()].copy()
print(f"  結果あり: {len(df_test_raw):,}件")

# 目的変数作成
df_train_raw['is_win'] = (df_train_raw['result_rank'].astype(str) == '1').astype(int)
df_test_raw['is_win'] = (df_test_raw['result_rank'].astype(str) == '1').astype(int)

print(f"  学習データ正例: {df_train_raw['is_win'].sum():,}件 ({df_train_raw['is_win'].mean()*100:.2f}%)")
print(f"  テストデータ正例: {df_test_raw['is_win'].sum():,}件 ({df_test_raw['is_win'].mean()*100:.2f}%)")

def add_combined_features(df, train_stats=None):
    """ベースライン + 会場・級別 + 選手特徴量を追加"""
    df = df.copy()

    # ベースライン: 枠番ダミー
    for i in range(1, 7):
        df[f'pit_number_{i}'] = (df['pit_number'] == i).astype(int)

    # ベースライン: コース別ダミー
    if 'actual_course' in df.columns:
        for i in range(1, 7):
            df[f'actual_course_{i}'] = (df['actual_course'] == i).astype(int)
        df['pit_course_diff'] = df['pit_number'] - df['actual_course']

    # 会場・級別特徴量の追加
    if train_stats is None:
        # 訓練データから統計を計算
        train_stats = {}

        # 会場別1号艇勝率
        venue_pit1 = df[(df['pit_number'] == 1)].groupby('venue_code')['is_win'].mean()
        train_stats['venue_pit1_win_rate'] = venue_pit1

        # 会場別2号艇勝率
        venue_pit2 = df[(df['pit_number'] == 2)].groupby('venue_code')['is_win'].mean()
        train_stats['venue_pit2_win_rate'] = venue_pit2

        # 級別勝率
        grade_win = df.groupby('racer_rank')['is_win'].mean()
        train_stats['grade_win_rate'] = grade_win

    # 会場別1号艇勝率
    df['venue_pit1_win_rate'] = df['venue_code'].map(train_stats['venue_pit1_win_rate'])
    df['venue_pit1_win_rate'] = df['venue_pit1_win_rate'].fillna(train_stats['venue_pit1_win_rate'].mean())

    # 会場別2号艇勝率
    df['venue_pit2_win_rate'] = df['venue_code'].map(train_stats['venue_pit2_win_rate'])
    df['venue_pit2_win_rate'] = df['venue_pit2_win_rate'].fillna(train_stats['venue_pit2_win_rate'].mean())

    # インコースバイアス
    df['venue_inner_bias'] = df['venue_pit1_win_rate'] / (df['venue_pit1_win_rate'] + df['venue_pit2_win_rate'] + 0.01)

    # 級別勝率
    df['grade_win_rate'] = df['racer_rank'].map(train_stats['grade_win_rate'])
    df['grade_win_rate'] = df['grade_win_rate'].fillna(train_stats['grade_win_rate'].mean())

    # 交互作用特徴量
    df['pit1_venue_inner'] = df['pit_number_1'] * df['venue_inner_bias']
    df['pit1_grade_win'] = df['pit_number_1'] * df['grade_win_rate']
    df['venue_grade_interaction'] = df['venue_inner_bias'] * df['grade_win_rate']

    # 選手特徴量はload_datasetで既に取得済み
    # f_count, l_count, motor_second_rate, boat_second_rate

    return df, train_stats

# 学習データに特徴量追加
print("\n[Step 3] 学習データに特徴量追加（全特徴量）")
df_train, train_stats = add_combined_features(df_train_raw)
print(f"  特徴量追加後: {len(df_train.columns)}カラム")

# テストデータに特徴量追加
print("\n[Step 4] テストデータに特徴量追加（訓練統計使用）")
df_test, _ = add_combined_features(df_test_raw, train_stats=train_stats)
print(f"  特徴量追加後: {len(df_test.columns)}カラム")

# 共通の特徴量カラムを抽出
train_numeric_cols = df_train.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
test_numeric_cols = df_test.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'result_rank']

common_features = set(train_numeric_cols) & set(test_numeric_cols)
feature_cols = [col for col in common_features if col not in exclude_cols]
feature_cols = sorted(feature_cols)

print(f"\n[Step 5] 特徴量抽出")
print(f"  共通特徴量数: {len(feature_cols)}個")

# 欠損値処理
X_train = df_train[feature_cols].copy()
X_test = df_test[feature_cols].copy()

for col in X_train.columns:
    if X_train[col].isna().any():
        mean_val = X_train[col].mean()
        X_train.loc[:, col] = X_train[col].fillna(mean_val)
        X_test.loc[:, col] = X_test[col].fillna(mean_val)

y_train = df_train['is_win']
y_test = df_test['is_win']

print(f"\n[Step 6] データセット準備完了")
print(f"  X_train shape: {X_train.shape}")
print(f"  X_test shape: {X_test.shape}")

# モデル学習
print(f"\n[Step 7] XGBoost学習開始")
trainer = ModelTrainer(model_dir="models")
trainer.train(X_train, y_train, X_test, y_test)

# モデル保存
print(f"\n[Step 8] モデル保存")
model_path = trainer.save_model("stage2_combined_8months.json")
print(f"  保存先: {model_path}")

# 評価
print(f"\n[Step 9] モデル評価")
y_pred = trainer.predict(X_test)
auc = roc_auc_score(y_test, y_pred)
logloss = log_loss(y_test, y_pred)

print(f"  AUC: {auc:.4f}")
print(f"  Log Loss: {logloss:.4f}")

# 確率帯別分析
print("\n[Step 10] 確率帯別的中率")
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

print(f"\n[Step 11] 高確率帯（0.8以上）: {high_conf_hit_rate:.2%}")

very_high_conf_mask = y_pred >= 0.9
very_high_conf_count = very_high_conf_mask.sum()
very_high_conf_wins = y_test[very_high_conf_mask].sum()
very_high_conf_hit_rate = very_high_conf_wins / very_high_conf_count if very_high_conf_count > 0 else 0

print(f"[Step 12] 超高確率帯（0.9以上）: {very_high_conf_hit_rate:.2%}")

print("\n" + "=" * 80)
print(f"実験#010完了: AUC={auc:.4f}, 的中率(0.8+)={high_conf_hit_rate:.2%}, 的中率(0.9+)={very_high_conf_hit_rate:.2%}")
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
