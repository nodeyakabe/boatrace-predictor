"""
閾値最適化の評価スクリプト

実験#014: 実験#012の予測確率に対して最適な閾値を探索
- 閾値を0.5〜0.95まで0.05刻みで試す
- 購入機会数と的中率のトレードオフを分析
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
print("閾値最適化評価（実験#014）")
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
print("\n[Step 2] 実験#012モデル読み込み")
model = xgb.XGBClassifier()
model.load_model("models/stage2_optimized.json")
print("  モデル読み込み完了")

# 予測
print("\n[Step 3] 予測実行")
y_pred = model.predict_proba(X_test)[:, 1]
auc = roc_auc_score(y_test, y_pred)
print(f"  AUC: {auc:.4f}")

# 閾値最適化
print("\n[Step 4] 閾値最適化")
print("-" * 100)
print(f"{'閾値':<8} {'購入機会数':<12} {'的中数':<10} {'的中率':<10} {'収益率(単勝)':<15} {'期待収益':<15}")
print("-" * 100)

thresholds = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
results = []

for threshold in thresholds:
    mask = y_pred >= threshold
    count = mask.sum()

    if count > 0:
        wins = y_test[mask].sum()
        hit_rate = wins / count

        # 簡易的な収益率計算（平均オッズを仮定）
        # 的中率が高いレースは低オッズと仮定
        # 簡易計算: オッズ = 1 / 予測確率
        avg_pred_prob = y_pred[mask].mean()
        estimated_odds = 1.0 / avg_pred_prob if avg_pred_prob > 0 else 1.0
        # 実際のオッズは予測より低い傾向があるので0.7倍
        estimated_odds *= 0.7

        # 収益率 = 的中率 * オッズ - 1.0
        roi = hit_rate * estimated_odds - 1.0

        # 期待収益（1レースあたり100円購入と仮定）
        expected_profit = count * 100 * roi

        print(f"{threshold:<8.2f} {count:<12} {int(wins):<10} {hit_rate:>7.2%}   {roi:>12.2%}      {expected_profit:>12.0f}円")

        results.append({
            'threshold': threshold,
            'count': count,
            'wins': int(wins),
            'hit_rate': hit_rate,
            'roi': roi,
            'expected_profit': expected_profit
        })
    else:
        print(f"{threshold:<8.2f} {'0':<12} {'0':<10} {'N/A':<10} {'N/A':<15} {'N/A':<15}")

# 最適閾値の推奨
print("\n[Step 5] 推奨閾値の分析")
print("-" * 80)

if len(results) > 0:
    df_results = pd.DataFrame(results)

    # 的中率が最も高い閾値
    best_hit_rate_idx = df_results['hit_rate'].idxmax()
    best_hit_rate_threshold = df_results.loc[best_hit_rate_idx]

    # ROIが最も高い閾値
    best_roi_idx = df_results['roi'].idxmax()
    best_roi_threshold = df_results.loc[best_roi_idx]

    # 期待収益が最も高い閾値
    best_profit_idx = df_results['expected_profit'].idxmax()
    best_profit_threshold = df_results.loc[best_profit_idx]

    print(f"1. 的中率重視（最高的中率）:")
    print(f"   閾値: {best_hit_rate_threshold['threshold']:.2f}")
    print(f"   購入機会: {best_hit_rate_threshold['count']}件")
    print(f"   的中率: {best_hit_rate_threshold['hit_rate']:.2%}")
    print(f"   ROI: {best_hit_rate_threshold['roi']:.2%}")
    print()

    print(f"2. ROI重視（最高収益率）:")
    print(f"   閾値: {best_roi_threshold['threshold']:.2f}")
    print(f"   購入機会: {best_roi_threshold['count']}件")
    print(f"   的中率: {best_roi_threshold['hit_rate']:.2%}")
    print(f"   ROI: {best_roi_threshold['roi']:.2%}")
    print()

    print(f"3. 期待収益重視（最高総収益）:")
    print(f"   閾値: {best_profit_threshold['threshold']:.2f}")
    print(f"   購入機会: {best_profit_threshold['count']}件")
    print(f"   的中率: {best_profit_threshold['hit_rate']:.2%}")
    print(f"   期待収益: {best_profit_threshold['expected_profit']:.0f}円")
    print()

    print(f"4. バランス重視（購入機会100件以上で最高的中率）:")
    df_balanced = df_results[df_results['count'] >= 100]
    if len(df_balanced) > 0:
        balanced_idx = df_balanced['hit_rate'].idxmax()
        balanced_threshold = df_balanced.loc[balanced_idx]

        print(f"   閾値: {balanced_threshold['threshold']:.2f}")
        print(f"   購入機会: {balanced_threshold['count']}件")
        print(f"   的中率: {balanced_threshold['hit_rate']:.2%}")
        print(f"   ROI: {balanced_threshold['roi']:.2%}")
    else:
        print(f"   該当なし（購入機会100件以上の閾値が存在しない）")

# 実験#012（閾値0.8）との比較
print("\n[Step 6] 実験#012（閾値0.8）との比較")
print("-" * 80)

original_threshold = 0.8
mask_original = y_pred >= original_threshold
count_original = mask_original.sum()
wins_original = y_test[mask_original].sum()
hit_rate_original = wins_original / count_original if count_original > 0 else 0

print(f"実験#012（閾値0.8）:")
print(f"  購入機会: {count_original}件")
print(f"  的中率: {hit_rate_original:.2%}")

print("\n" + "=" * 80)
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
