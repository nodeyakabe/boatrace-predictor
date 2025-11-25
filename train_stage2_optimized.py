"""
Stage2モデル学習スクリプト（ハイパーパラメータ最適化版）

実験#012: Optunaでハイパーパラメータをチューニングして最高性能を目指す
- 学習期間: 2023-06-01 〜 2024-05-31（12ヶ月）
- テスト期間: 2024-06-01 〜 2024-06-30（1ヶ月）
- 特徴量: 37個（実験#011と同じ）
- 最適化: Optuna（50試行）
- 目的: AUC 0.86以上達成
"""

import sys
sys.path.append('.')

import sqlite3
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score, log_loss
from sklearn.model_selection import train_test_split
from datetime import datetime
import xgboost as xgb
import optuna

print("=" * 80)
print("Stage2モデル学習 - ハイパーパラメータ最適化版（実験#012）")
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
    """ベースライン + 選手基本特徴量を追加"""
    df = df.copy()

    # 枠番ダミー
    for i in range(1, 7):
        df[f'pit_number_{i}'] = (df['pit_number'] == i).astype(int)

    # コース別ダミー
    if 'actual_course' in df.columns:
        for i in range(1, 7):
            df[f'actual_course_{i}'] = (df['actual_course'] == i).astype(int)
        df['pit_course_diff'] = df['pit_number'] - df['actual_course']

    return df

# データセット構築
print("\n[Step 1] 学習データセット構築（2023-06-01〜2024-05-31: 12ヶ月）")
df_train_raw = load_dataset("2023-06-01", "2024-05-31")
df_train_raw = df_train_raw[df_train_raw['result_rank'].notna()].copy()
df_train_raw['is_win'] = (df_train_raw['result_rank'].astype(str) == '1').astype(int)
print(f"  学習データ: {len(df_train_raw):,}件")

print("\n[Step 2] テストデータセット構築（2024-06-01〜2024-06-30: 1ヶ月）")
df_test_raw = load_dataset("2024-06-01", "2024-06-30")
df_test_raw = df_test_raw[df_test_raw['result_rank'].notna()].copy()
df_test_raw['is_win'] = (df_test_raw['result_rank'].astype(str) == '1').astype(int)
print(f"  テストデータ: {len(df_test_raw):,}件")

# 特徴量追加
print("\n[Step 3] 特徴量追加")
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

# 欠損値処理
X_train_full = df_train[feature_cols].copy()
X_test = df_test[feature_cols].copy()

for col in X_train_full.columns:
    if X_train_full[col].isna().any():
        mean_val = X_train_full[col].mean()
        X_train_full.loc[:, col] = X_train_full[col].fillna(mean_val)
        X_test.loc[:, col] = X_test[col].fillna(mean_val)

y_train_full = df_train['is_win']
y_test = df_test['is_win']

# 検証用に訓練データをさらに分割
print("\n[Step 4] 訓練データを学習用と検証用に分割")
X_train, X_val, y_train, y_val = train_test_split(
    X_train_full, y_train_full, test_size=0.2, random_state=42, stratify=y_train_full
)

print(f"  学習用: {len(X_train):,}件")
print(f"  検証用: {len(X_val):,}件")
print(f"  テスト用: {len(X_test):,}件")

# Optuna最適化
print("\n[Step 5] Optunaでハイパーパラメータ最適化（50試行）")

def objective(trial):
    """Optunaの目的関数"""
    params = {
        'objective': 'binary:logistic',
        'eval_metric': 'auc',
        'tree_method': 'hist',
        'random_state': 42,

        # 最適化対象パラメータ
        'max_depth': trial.suggest_int('max_depth', 3, 10),
        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
        'n_estimators': trial.suggest_int('n_estimators', 100, 1000, step=100),
        'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
        'subsample': trial.suggest_float('subsample', 0.6, 1.0),
        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
        'gamma': trial.suggest_float('gamma', 0.0, 1.0),
        'reg_alpha': trial.suggest_float('reg_alpha', 0.0, 1.0),
        'reg_lambda': trial.suggest_float('reg_lambda', 0.0, 1.0),
    }

    model = xgb.XGBClassifier(**params)
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    y_pred_val = model.predict_proba(X_val)[:, 1]
    auc = roc_auc_score(y_val, y_pred_val)

    return auc

# Optunaの設定（出力を抑制）
optuna.logging.set_verbosity(optuna.logging.WARNING)

study = optuna.create_study(direction='maximize', study_name='xgboost_optimization')
study.optimize(objective, n_trials=50, show_progress_bar=False)

print(f"\n  最適化完了")
print(f"  最良AUC: {study.best_value:.4f}")
print(f"  最良パラメータ:")
for key, value in study.best_params.items():
    print(f"    {key}: {value}")

# 最良パラメータで全訓練データを使って再学習
print("\n[Step 6] 最良パラメータで全訓練データを使って再学習")
best_params = study.best_params
best_params.update({
    'objective': 'binary:logistic',
    'eval_metric': 'auc',
    'tree_method': 'hist',
    'random_state': 42
})

model = xgb.XGBClassifier(**best_params)
model.fit(X_train_full, y_train_full, eval_set=[(X_test, y_test)], verbose=False)

# モデル保存
print("\n[Step 7] モデル保存")
model.save_model("models/stage2_optimized.json")
print(f"  保存先: models/stage2_optimized.json")

# 評価
print(f"\n[Step 8] モデル評価")
y_pred = model.predict_proba(X_test)[:, 1]
auc = roc_auc_score(y_test, y_pred)
logloss = log_loss(y_test, y_pred)

print(f"  AUC: {auc:.4f}")
print(f"  Log Loss: {logloss:.4f}")

# 確率帯別分析
print("\n[Step 9] 確率帯別的中率")
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

print(f"\n[Step 10] 高確率帯（0.8以上）: {high_conf_hit_rate:.2%}")

very_high_conf_mask = y_pred >= 0.9
very_high_conf_count = very_high_conf_mask.sum()
very_high_conf_wins = y_test[very_high_conf_mask].sum()
very_high_conf_hit_rate = very_high_conf_wins / very_high_conf_count if very_high_conf_count > 0 else 0

print(f"[Step 11] 超高確率帯（0.9以上）: {very_high_conf_hit_rate:.2%}")

print("\n" + "=" * 80)
print(f"実験#012完了: AUC={auc:.4f}, 的中率(0.8+)={high_conf_hit_rate:.2%}, 的中率(0.9+)={very_high_conf_hit_rate:.2%}")
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
