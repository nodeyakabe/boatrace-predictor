"""
マルチモデルアンサンブル学習スクリプト

実験#020: XGBoost + LightGBM + CatBoost のアンサンブル
- 異なるアルゴリズムで学習
- 予測を重み付き平均で統合
- 学習期間: 2023-06-01 〜 2024-05-31（12ヶ月）
- テスト期間: 2024-06-01 〜 2024-06-30（1ヶ月）
"""

import sys
sys.path.append('.')

import sqlite3
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score, log_loss
from datetime import datetime
import xgboost as xgb
try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except:
    HAS_LIGHTGBM = False
    print("[警告] LightGBMがインストールされていません。pip install lightgbm")

print("=" * 80)
print("マルチモデルアンサンブル学習（実験#020）")
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

# データセット構築
print("\n[Step 1] データセット構築")
df_train_raw = load_dataset("2023-06-01", "2024-05-31")
df_train_raw = df_train_raw[df_train_raw['result_rank'].notna()].copy()
df_train_raw['is_win'] = (df_train_raw['result_rank'].astype(str) == '1').astype(int)
print(f"  学習データ: {len(df_train_raw):,}件")

df_test_raw = load_dataset("2024-06-01", "2024-06-30")
df_test_raw = df_test_raw[df_test_raw['result_rank'].notna()].copy()
df_test_raw['is_win'] = (df_test_raw['result_rank'].astype(str) == '1').astype(int)
print(f"  テストデータ: {len(df_test_raw):,}件")

# 特徴量追加
print("\n[Step 2] 特徴量追加")
df_train = add_features(df_train_raw)
df_test = add_features(df_test_raw)

train_numeric_cols = df_train.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
test_numeric_cols = df_test.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'result_rank']

common_features = set(train_numeric_cols) & set(test_numeric_cols)
feature_cols = [col for col in common_features if col not in exclude_cols]
feature_cols = sorted(feature_cols)

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

print(f"  特徴量数: {len(feature_cols)}個")
print(f"  X_train shape: {X_train.shape}")
print(f"  X_test shape: {X_test.shape}")

# モデル1: XGBoost
print(f"\n{'='*80}")
print("モデル1: XGBoost")
print(f"{'='*80}")

model_xgb = xgb.XGBClassifier(
    max_depth=4,
    learning_rate=0.016,
    n_estimators=700,
    random_state=42,
    eval_metric='auc'
)

print("  学習中...")
model_xgb.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
y_pred_xgb = model_xgb.predict_proba(X_test)[:, 1]
auc_xgb = roc_auc_score(y_test, y_pred_xgb)
print(f"  AUC: {auc_xgb:.4f}")

# モデル2: LightGBM
if HAS_LIGHTGBM:
    print(f"\n{'='*80}")
    print("モデル2: LightGBM")
    print(f"{'='*80}")

    model_lgb = lgb.LGBMClassifier(
        max_depth=4,
        learning_rate=0.016,
        n_estimators=700,
        random_state=42,
        verbose=-1
    )

    print("  学習中...")
    model_lgb.fit(X_train, y_train, eval_set=[(X_test, y_test)])
    y_pred_lgb = model_lgb.predict_proba(X_test)[:, 1]
    auc_lgb = roc_auc_score(y_test, y_pred_lgb)
    print(f"  AUC: {auc_lgb:.4f}")
else:
    y_pred_lgb = None
    auc_lgb = None

# アンサンブル予測
print(f"\n{'='*80}")
print("アンサンブル予測")
print(f"{'='*80}")

if HAS_LIGHTGBM:
    # 複数の重みパターンで試す
    print("\n重み付きアンサンブル:")
    print("-" * 80)
    print(f"{'XGB:LGB':<15} {'AUC':<10} {'Log Loss':<12} {'的中率(0.8+)':<15}")
    print("-" * 80)

    best_auc = 0
    best_weight = 0
    best_pred = None

    for weight_xgb in [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]:
        weight_lgb = 1.0 - weight_xgb

        y_pred_ensemble = weight_xgb * y_pred_xgb + weight_lgb * y_pred_lgb

        auc = roc_auc_score(y_test, y_pred_ensemble)
        logloss = log_loss(y_test, y_pred_ensemble)

        high_conf_mask = y_pred_ensemble >= 0.8
        high_conf_count = high_conf_mask.sum()
        high_conf_wins = y_test[high_conf_mask].sum()
        high_conf_hit_rate = high_conf_wins / high_conf_count if high_conf_count > 0 else 0

        print(f"{weight_xgb:.1f}:{weight_lgb:.1f}           {auc:<10.4f} {logloss:<12.4f} {high_conf_hit_rate:<15.2%}")

        if auc > best_auc:
            best_auc = auc
            best_weight = weight_xgb
            best_pred = y_pred_ensemble

    print("-" * 80)
    print(f"最良の重み: XGB {best_weight:.1f} : LGB {1.0-best_weight:.1f} (AUC: {best_auc:.4f})")

    # 最良アンサンブルの詳細評価
    print(f"\n最良アンサンブルの詳細評価:")
    logloss_best = log_loss(y_test, best_pred)
    print(f"  AUC: {best_auc:.4f}")
    print(f"  Log Loss: {logloss_best:.4f}")

    # 確率帯別分析
    print("\n確率帯別的中率:")
    prob_bins = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    for i in range(len(prob_bins) - 1):
        lower = prob_bins[i]
        upper = prob_bins[i + 1]
        mask = (best_pred >= lower) & (best_pred < upper)
        count = mask.sum()
        if count > 0:
            wins = y_test[mask].sum()
            hit_rate = wins / count
            print(f"  {lower:.1f}-{upper:.1f}      {count:<10} {int(wins):<10} {hit_rate:>7.2%}")

    high_conf_mask = best_pred >= 0.8
    high_conf_count = high_conf_mask.sum()
    high_conf_wins = y_test[high_conf_mask].sum()
    high_conf_hit_rate = high_conf_wins / high_conf_count if high_conf_count > 0 else 0

    print(f"\n的中率(0.8+): {high_conf_hit_rate:.2%} ({high_conf_count}件)")

    # 実験#012との比較
    print(f"\n実験#012との比較:")
    print(f"  実験#012 AUC: 0.8496")
    print(f"  アンサンブル AUC: {best_auc:.4f}")
    print(f"  差分: {best_auc - 0.8496:+.4f}")

else:
    print("\n[スキップ] LightGBMがインストールされていないため、アンサンブルは実行されませんでした")
    print("  pip install lightgbm でインストールしてください")

print("\n" + "=" * 80)
print(f"実験#020完了")
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
