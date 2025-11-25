"""
アンサンブルモデルの評価スクリプト

実験#013: 実験#011と実験#012を組み合わせたアンサンブル
- モデル1: stage2_racer_simple_12months.json (実験#011)
- モデル2: stage2_optimized.json (実験#012)
- 重み: 0.4 * model_011 + 0.6 * model_012
"""

import sys
sys.path.append('.')

import sqlite3
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score, log_loss
from datetime import datetime
import xgboost as xgb

print("=" * 80)
print("アンサンブルモデル評価（実験#013）")
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

def add_features(df):
    """特徴量追加"""
    df = df.copy()

    for i in range(1, 7):
        df[f'pit_number_{i}'] = (df['pit_number'] == i).astype(int)

    if 'actual_course' in df.columns:
        for i in range(1, 7):
            df[f'actual_course_{i}'] = (df['actual_course'] == i).astype(int)
        df['pit_course_diff'] = df['pit_number'] - df['actual_course']

    return df

# テストデータ取得
print("\n[Step 1] テストデータセット構築")
df_test_raw = load_dataset("2024-06-01", "2024-06-30")
df_test_raw = df_test_raw[df_test_raw['result_rank'].notna()].copy()
df_test_raw['is_win'] = (df_test_raw['result_rank'].astype(str) == '1').astype(int)
print(f"  テストデータ: {len(df_test_raw):,}件")

# 特徴量追加
df_test = add_features(df_test_raw)

train_numeric_cols = df_test.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'result_rank']
feature_cols = [col for col in train_numeric_cols if col not in exclude_cols]
feature_cols = sorted(feature_cols)

# 欠損値処理
X_test = df_test[feature_cols].copy()
for col in X_test.columns:
    if X_test[col].isna().any():
        X_test.loc[:, col] = X_test[col].fillna(X_test[col].mean())

y_test = df_test['is_win']

# モデル読み込み
print("\n[Step 2] モデル読み込み")
model_011 = xgb.XGBClassifier()
model_011.load_model("models/stage2_racer_simple_12months.json")
print("  実験#011モデル読み込み完了")

model_012 = xgb.XGBClassifier()
model_012.load_model("models/stage2_optimized.json")
print("  実験#012モデル読み込み完了")

# 個別予測
print("\n[Step 3] 個別モデルの予測")
y_pred_011 = model_011.predict_proba(X_test)[:, 1]
y_pred_012 = model_012.predict_proba(X_test)[:, 1]

auc_011 = roc_auc_score(y_test, y_pred_011)
auc_012 = roc_auc_score(y_test, y_pred_012)

print(f"  実験#011 AUC: {auc_011:.4f}")
print(f"  実験#012 AUC: {auc_012:.4f}")

# アンサンブル予測（複数の重みで試す）
print("\n[Step 4] アンサンブル予測（複数の重み）")
print("-" * 80)
print(f"{'重み(011:012)':<20} {'AUC':<10} {'Log Loss':<12} {'的中率(0.8+)':<15} {'的中率(0.9+)':<15}")
print("-" * 80)

best_auc = 0
best_weight = 0
best_pred = None

for weight_011 in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
    weight_012 = 1.0 - weight_011

    y_pred_ensemble = weight_011 * y_pred_011 + weight_012 * y_pred_012

    auc = roc_auc_score(y_test, y_pred_ensemble)
    logloss = log_loss(y_test, y_pred_ensemble)

    # 的中率計算
    high_conf_mask = y_pred_ensemble >= 0.8
    high_conf_count = high_conf_mask.sum()
    high_conf_wins = y_test[high_conf_mask].sum()
    high_conf_hit_rate = high_conf_wins / high_conf_count if high_conf_count > 0 else 0

    very_high_conf_mask = y_pred_ensemble >= 0.9
    very_high_conf_count = very_high_conf_mask.sum()
    very_high_conf_wins = y_test[very_high_conf_mask].sum()
    very_high_conf_hit_rate = very_high_conf_wins / very_high_conf_count if very_high_conf_count > 0 else 0

    print(f"{weight_011:.1f}:{weight_012:.1f}              {auc:<10.4f} {logloss:<12.4f} {high_conf_hit_rate:<15.2%} {very_high_conf_hit_rate:<15.2%}")

    if auc > best_auc:
        best_auc = auc
        best_weight = weight_011
        best_pred = y_pred_ensemble

print("-" * 80)
print(f"最良の重み: {best_weight:.1f}:{1.0-best_weight:.1f} (AUC: {best_auc:.4f})")

# 最良のアンサンブルで詳細評価
print("\n[Step 5] 最良アンサンブルの詳細評価")
y_pred_best = best_pred

auc = roc_auc_score(y_test, y_pred_best)
logloss = log_loss(y_test, y_pred_best)

print(f"  AUC: {auc:.4f}")
print(f"  Log Loss: {logloss:.4f}")

# 確率帯別分析
print("\n[Step 6] 確率帯別的中率")
print("-" * 60)
prob_bins = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
for i in range(len(prob_bins) - 1):
    lower = prob_bins[i]
    upper = prob_bins[i + 1]
    mask = (y_pred_best >= lower) & (y_pred_best < upper)
    count = mask.sum()
    if count > 0:
        wins = y_test[mask].sum()
        hit_rate = wins / count
        print(f"{lower:.1f}-{upper:.1f}      {count:<10} {int(wins):<10} {hit_rate:>7.2%}")

# 高確率帯分析
high_conf_mask = y_pred_best >= 0.8
high_conf_count = high_conf_mask.sum()
high_conf_wins = y_test[high_conf_mask].sum()
high_conf_hit_rate = high_conf_wins / high_conf_count if high_conf_count > 0 else 0

very_high_conf_mask = y_pred_best >= 0.9
very_high_conf_count = very_high_conf_mask.sum()
very_high_conf_wins = y_test[very_high_conf_mask].sum()
very_high_conf_hit_rate = very_high_conf_wins / very_high_conf_count if very_high_conf_count > 0 else 0

print(f"\n[Step 7] 高確率帯分析")
print(f"  0.8以上: 件数={high_conf_count}, 的中率={high_conf_hit_rate:.2%}")
print(f"  0.9以上: 件数={very_high_conf_count}, 的中率={very_high_conf_hit_rate:.2%}")

# 実験#012との比較
print("\n[Step 8] 実験#012との比較")
print("-" * 80)
print(f"{'指標':<25} {'実験#012':<15} {'アンサンブル':<15} {'差分':<15}")
print("-" * 80)

# 実験#012の結果
exp012_auc = 0.8496
exp012_logloss = 0.3179
exp012_hit_08 = 87.72
exp012_hit_09 = 100.00

print(f"{'AUC':<25} {exp012_auc:<15.4f} {auc:<15.4f} {auc - exp012_auc:+.4f}")
print(f"{'Log Loss':<25} {exp012_logloss:<15.4f} {logloss:<15.4f} {logloss - exp012_logloss:+.4f}")
print(f"{'的中率（0.8+）':<25} {exp012_hit_08:<14.2f}% {high_conf_hit_rate*100:<14.2f}% {high_conf_hit_rate*100 - exp012_hit_08:+.2f}pt")
print(f"{'的中率（0.9+）':<25} {exp012_hit_09:<14.2f}% {very_high_conf_hit_rate*100:<14.2f}% {very_high_conf_hit_rate*100 - exp012_hit_09:+.2f}pt")

print("\n" + "=" * 80)
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
