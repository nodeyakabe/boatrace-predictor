"""
時系列特徴量追加モデル学習スクリプト

実験#017: 時系列的な特徴量を追加
- モーター・ボートの使用期間特徴量
- 選手の成績トレンド（過去3ヶ月の勝率変化）
- 学習期間: 2023-06-01 〜 2024-05-31（12ヶ月）
- テスト期間: 2024-06-01 〜 2024-06-30（1ヶ月）
"""

import sys
sys.path.append('.')

import sqlite3
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score, log_loss
from datetime import datetime, timedelta
from src.ml.model_trainer import ModelTrainer

print("=" * 80)
print("時系列特徴量追加モデル（実験#017）")
print("=" * 80)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def load_dataset(start_date, end_date):
    """データセット取得"""
    conn = sqlite3.connect('data/boatrace.db')

    query = f"""
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,

            e.pit_number,
            e.racer_number,
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
            e.boat_second_rate,

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

def add_timeseries_features(df):
    """時系列特徴量を追加"""
    df = df.copy()

    # 日付型に変換
    df['race_date'] = pd.to_datetime(df['race_date'])

    # 1. レース日の時系列特徴量
    df['day_of_week'] = df['race_date'].dt.dayofweek  # 0=月曜, 6=日曜
    df['day_of_month'] = df['race_date'].dt.day
    df['month'] = df['race_date'].dt.month

    # 2. 週末フラグ
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)

    # 3. モーター・ボート使用期間の推定
    # 簡易的にrace_numberから推定（1日12レースと仮定）
    df['motor_usage_days'] = (df['race_number'] / 12.0).astype(int)
    df['boat_usage_days'] = (df['race_number'] / 12.0).astype(int)

    # 4. 選手成績のトレンド（勝率と2連率の比較）
    # 勝率が2連率の何%かを見ることで、最近の調子を推測
    df['win_vs_second_ratio'] = df['win_rate'] / (df['second_rate'] + 0.01)

    # 5. モーター・ボート性能のバランス
    df['motor_boat_balance'] = df['motor_second_rate'] - df['boat_second_rate']

    # 6. 選手経験値（年齢ベース）
    # 年齢が高いほど経験豊富と仮定
    df['experience_score'] = df['racer_age'] / 40.0  # 正規化

    return df

def add_features(df):
    """ベースライン特徴量追加"""
    df = df.copy()

    for i in range(1, 7):
        df[f'pit_number_{i}'] = (df['pit_number'] == i).astype(int)

    if 'actual_course' in df.columns:
        for i in range(1, 7):
            df[f'actual_course_{i}'] = (df['actual_course'] == i).astype(int)
        df['pit_course_diff'] = df['pit_number'] - df['actual_course']

    # 時系列特徴量を追加
    df = add_timeseries_features(df)

    return df

# データセット構築
print("\n[Step 1] 学習データセット構築")
df_train_raw = load_dataset("2023-06-01", "2024-05-31")
df_train_raw = df_train_raw[df_train_raw['result_rank'].notna()].copy()
df_train_raw['is_win'] = (df_train_raw['result_rank'].astype(str) == '1').astype(int)
print(f"  学習データ: {len(df_train_raw):,}件")

print("\n[Step 2] テストデータセット構築")
df_test_raw = load_dataset("2024-06-01", "2024-06-30")
df_test_raw = df_test_raw[df_test_raw['result_rank'].notna()].copy()
df_test_raw['is_win'] = (df_test_raw['result_rank'].astype(str) == '1').astype(int)
print(f"  テストデータ: {len(df_test_raw):,}件")

# 特徴量追加
print("\n[Step 3] 特徴量追加（時系列特徴量含む）")
df_train = add_features(df_train_raw)
df_test = add_features(df_test_raw)

# 特徴量抽出
train_numeric_cols = df_train.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
test_numeric_cols = df_test.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'result_rank']

common_features = set(train_numeric_cols) & set(test_numeric_cols)
feature_cols = [col for col in common_features if col not in exclude_cols]
feature_cols = sorted(feature_cols)

print(f"  特徴量数: {len(feature_cols)}個")

# 時系列特徴量を確認
timeseries_keywords = ['day_', 'month', 'weekend', 'usage', 'ratio', 'balance', 'experience']
timeseries_features = [col for col in feature_cols if any(kw in col for kw in timeseries_keywords)]

if len(timeseries_features) > 0:
    print(f"\n  時系列特徴量:")
    for feat in timeseries_features:
        print(f"    - {feat}")

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

print(f"\n[Step 4] データセット準備完了")
print(f"  X_train shape: {X_train.shape}")
print(f"  X_test shape: {X_test.shape}")

# モデル学習
print(f"\n[Step 5] XGBoost学習開始")
trainer = ModelTrainer(model_dir="models")
trainer.train(X_train, y_train, X_test, y_test)

# モデル保存
print(f"\n[Step 6] モデル保存")
model_path = trainer.save_model("stage2_with_timeseries.json")
print(f"  保存先: {model_path}")

# 評価
print(f"\n[Step 7] モデル評価")
y_pred = trainer.predict(X_test)
auc = roc_auc_score(y_test, y_pred)
logloss = log_loss(y_test, y_pred)

print(f"  AUC: {auc:.4f}")
print(f"  Log Loss: {logloss:.4f}")

# 確率帯別分析
print("\n[Step 8] 確率帯別的中率")
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

very_high_conf_mask = y_pred >= 0.9
very_high_conf_count = very_high_conf_mask.sum()
very_high_conf_wins = y_test[very_high_conf_mask].sum()
very_high_conf_hit_rate = very_high_conf_wins / very_high_conf_count if very_high_conf_count > 0 else 0

print(f"\n[Step 9] 高確率帯分析")
print(f"  0.8以上: {high_conf_hit_rate:.2%} ({high_conf_count}件)")
print(f"  0.9以上: {very_high_conf_hit_rate:.2%} ({very_high_conf_count}件)")

# 実験#012との比較
print(f"\n[Step 10] 実験#012との比較")
print("-" * 80)
print(f"{'指標':<25} {'実験#012':<15} {'実験#017':<15} {'差分':<15}")
print("-" * 80)

exp012_auc = 0.8496
exp012_logloss = 0.3179
exp012_hit_08 = 87.72
exp012_hit_09 = 100.00

print(f"{'AUC':<25} {exp012_auc:<15.4f} {auc:<15.4f} {auc - exp012_auc:+.4f}")
print(f"{'Log Loss':<25} {exp012_logloss:<15.4f} {logloss:<15.4f} {logloss - exp012_logloss:+.4f}")
print(f"{'的中率（0.8+）':<25} {exp012_hit_08:<14.2f}% {high_conf_hit_rate*100:<14.2f}% {high_conf_hit_rate*100 - exp012_hit_08:+.2f}pt")
print(f"{'的中率（0.9+）':<25} {exp012_hit_09:<14.2f}% {very_high_conf_hit_rate*100:<14.2f}% {very_high_conf_hit_rate*100 - exp012_hit_09:+.2f}pt")

print("\n" + "=" * 80)
print(f"実験#017完了: AUC={auc:.4f}, 的中率(0.8+)={high_conf_hit_rate:.2%}, 的中率(0.9+)={very_high_conf_hit_rate:.2%}")
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
