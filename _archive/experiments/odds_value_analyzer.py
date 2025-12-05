"""
オッズ情報活用分析スクリプト

実験#019: モデル予測とオッズを組み合わせた期待値分析
- 予測確率とオッズから期待値を計算
- 期待値がプラスのレースのみ推奨
- オッズデータは仮想データで検証
"""

import sys
sys.path.append('.')

import sqlite3
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score
from datetime import datetime
import xgboost as xgb

print("=" * 80)
print("オッズ情報活用分析（実験#019）")
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

# モデルが期待する特徴量の順序（実験#012のログから）
feature_cols = [
    'actual_course', 'actual_course_1', 'actual_course_2', 'actual_course_3',
    'actual_course_4', 'actual_course_5', 'actual_course_6', 'avg_st',
    'boat_number', 'boat_second_rate', 'boat_third_rate', 'exhibition_time',
    'f_count', 'l_count', 'motor_number', 'motor_second_rate', 'motor_third_rate',
    'pit_course_diff', 'pit_number', 'pit_number_1', 'pit_number_2',
    'pit_number_3', 'pit_number_4', 'pit_number_5', 'pit_number_6',
    'race_number', 'racer_age', 'racer_weight', 'second_rate', 'st_time',
    'temperature', 'third_rate', 'tilt_angle', 'water_temperature',
    'wave_height', 'win_rate', 'wind_speed'
]

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

# オッズの生成（仮想データ）
# 実際のシステムでは外部APIから取得
print("\n[Step 4] オッズ情報の生成（仮想データ）")

df_test_with_pred = df_test.copy()
df_test_with_pred['win_probability'] = y_pred

# オッズを予測確率から逆算（実際には外部から取得）
# オッズ = 1 / 確率、ただし控除率（約25%）を考慮
df_test_with_pred['estimated_odds'] = 1.0 / (df_test_with_pred['win_probability'] * 0.75 + 0.01)

# オッズに現実的なノイズを追加
np.random.seed(42)
noise = np.random.normal(0, 0.2, len(df_test_with_pred))
df_test_with_pred['estimated_odds'] = np.maximum(1.0, df_test_with_pred['estimated_odds'] * (1 + noise))

print(f"  オッズ範囲: {df_test_with_pred['estimated_odds'].min():.2f}〜{df_test_with_pred['estimated_odds'].max():.2f}")

# 期待値計算
print("\n[Step 5] 期待値計算")

# 期待値 = 的中確率 × オッズ - 1.0
df_test_with_pred['expected_value'] = df_test_with_pred['win_probability'] * df_test_with_pred['estimated_odds'] - 1.0

# 期待値がプラスのレースを抽出
positive_ev = df_test_with_pred[df_test_with_pred['expected_value'] > 0].copy()
print(f"  期待値プラスのレース: {len(positive_ev):,}件 / {len(df_test_with_pred):,}件 ({len(positive_ev)/len(df_test_with_pred)*100:.2f}%)")

# 期待値別の分析
print("\n[Step 6] 期待値帯別の実績分析")
print("-" * 80)
print(f"{'期待値帯':<15} {'件数':<10} {'的中数':<10} {'的中率':<10} {'実際のROI':<15}")
print("-" * 80)

ev_bins = [(-np.inf, -0.5), (-0.5, -0.2), (-0.2, 0.0), (0.0, 0.1), (0.1, 0.2), (0.2, np.inf)]
ev_labels = ['< -50%', '-50% to -20%', '-20% to 0%', '0% to +10%', '+10% to +20%', '> +20%']

for (lower, upper), label in zip(ev_bins, ev_labels):
    mask = (df_test_with_pred['expected_value'] >= lower) & (df_test_with_pred['expected_value'] < upper)
    subset = df_test_with_pred[mask]

    if len(subset) > 0:
        wins = subset['is_win'].sum()
        hit_rate = wins / len(subset)

        # 実際のROI（100円購入と仮定）
        total_investment = len(subset) * 100
        total_return = (subset['is_win'] * subset['estimated_odds'] * 100).sum()
        actual_roi = (total_return - total_investment) / total_investment

        print(f"{label:<15} {len(subset):<10} {int(wins):<10} {hit_rate:>7.2%}   {actual_roi:>12.2%}")

# 期待値プラスのレースのみの分析
print(f"\n[Step 7] 期待値プラスのレースのみの分析")
print("-" * 80)

if len(positive_ev) > 0:
    wins_positive = positive_ev['is_win'].sum()
    hit_rate_positive = wins_positive / len(positive_ev)

    total_investment = len(positive_ev) * 100
    total_return = (positive_ev['is_win'] * positive_ev['estimated_odds'] * 100).sum()
    roi_positive = (total_return - total_investment) / total_investment

    print(f"購入レース数: {len(positive_ev)}")
    print(f"的中数: {int(wins_positive)}")
    print(f"的中率: {hit_rate_positive:.2%}")
    print(f"投資額: {total_investment:,}円")
    print(f"払戻額: {total_return:,.0f}円")
    print(f"収支: {total_return - total_investment:+,.0f}円")
    print(f"ROI: {roi_positive:.2%}")

# 予測確率とオッズの相関分析
print(f"\n[Step 8] 予測確率とオッズの関係")
print("-" * 80)

# レースごとに最高予測確率の艇を抽出
race_top_pred = df_test_with_pred.loc[df_test_with_pred.groupby('race_id')['win_probability'].idxmax()]

print(f"\n各レースの最高予測確率艇:")
print(f"  平均予測確率: {race_top_pred['win_probability'].mean():.2%}")
print(f"  平均オッズ: {race_top_pred['estimated_odds'].mean():.2f}倍")
print(f"  平均期待値: {race_top_pred['expected_value'].mean():.2%}")
print(f"  実際の的中率: {race_top_pred['is_win'].mean():.2%}")

# 推奨購入戦略
print(f"\n[Step 9] 推奨購入戦略")
print("=" * 80)

# 戦略1: 期待値+10%以上
strategy1 = df_test_with_pred[df_test_with_pred['expected_value'] >= 0.1]
if len(strategy1) > 0:
    wins_s1 = strategy1['is_win'].sum()
    roi_s1 = ((strategy1['is_win'] * strategy1['estimated_odds']).sum() - len(strategy1)) / len(strategy1)

    print(f"\n戦略1: 期待値+10%以上のレースのみ購入")
    print(f"  購入数: {len(strategy1)}件")
    print(f"  的中率: {wins_s1 / len(strategy1):.2%}")
    print(f"  ROI: {roi_s1:.2%}")

# 戦略2: 予測確率0.8以上 AND 期待値プラス
strategy2 = df_test_with_pred[(df_test_with_pred['win_probability'] >= 0.8) & (df_test_with_pred['expected_value'] > 0)]
if len(strategy2) > 0:
    wins_s2 = strategy2['is_win'].sum()
    roi_s2 = ((strategy2['is_win'] * strategy2['estimated_odds']).sum() - len(strategy2)) / len(strategy2)

    print(f"\n戦略2: 予測確率0.8以上 AND 期待値プラス")
    print(f"  購入数: {len(strategy2)}件")
    print(f"  的中率: {wins_s2 / len(strategy2):.2%}")
    print(f"  ROI: {roi_s2:.2%}")

# 戦略3: 予測確率0.5以上 AND 期待値+20%以上（穴狙い）
strategy3 = df_test_with_pred[(df_test_with_pred['win_probability'] >= 0.3) & (df_test_with_pred['expected_value'] >= 0.2)]
if len(strategy3) > 0:
    wins_s3 = strategy3['is_win'].sum()
    roi_s3 = ((strategy3['is_win'] * strategy3['estimated_odds']).sum() - len(strategy3)) / len(strategy3)

    print(f"\n戦略3: 予測確率0.3以上 AND 期待値+20%以上（穴狙い）")
    print(f"  購入数: {len(strategy3)}件")
    print(f"  的中率: {wins_s3 / len(strategy3):.2%}")
    print(f"  ROI: {roi_s3:.2%}")

print("\n" + "=" * 80)
print("実験#019完了")
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)

print("\n注意:")
print("  - 本分析では仮想オッズを使用しています")
print("  - 実運用では実際のオッズAPIから取得する必要があります")
print("  - オッズは投票締切直前まで変動するため、リアルタイム取得が推奨されます")
