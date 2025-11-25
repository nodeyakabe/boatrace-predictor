"""
直近成績特徴量を追加したモデル学習スクリプト

実験#015: 直近3戦、5戦、10戦の成績を特徴量に追加
- 学習期間: 2023-06-01 〜 2024-05-31（12ヶ月）
- テスト期間: 2024-06-01 〜 2024-06-30（1ヶ月）
- 新規特徴量: recent_3_avg_rank, recent_5_avg_rank, recent_10_avg_rank, recent_3_win_rate等
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
print("直近成績特徴量追加モデル（実験#015）")
print("=" * 80)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def load_dataset_with_recent_stats(start_date, end_date):
    """直近成績統計を含むデータセットを取得"""
    conn = sqlite3.connect('data/boatrace.db')

    # まず基本データを取得
    query_base = f"""
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

    df = pd.read_sql_query(query_base, conn, params=[start_date, end_date])

    # 直近成績の計算（簡略版: 選手ごとに過去のレース結果を集計）
    print("  直近成績計算中...")

    # 全期間のresultsを取得（メモリ効率のため選手番号とランクのみ）
    query_all_results = """
        SELECT
            e.racer_number,
            r.race_date,
            CAST(res.rank AS INTEGER) as rank
        FROM results res
        JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
        JOIN races r ON res.race_id = r.id
        WHERE res.rank IS NOT NULL AND res.rank != '' AND res.rank != '0'
        ORDER BY e.racer_number, r.race_date
    """

    df_all_results = pd.read_sql_query(query_all_results, conn)
    conn.close()

    # 日付型に変換
    df['race_date'] = pd.to_datetime(df['race_date'])
    df_all_results['race_date'] = pd.to_datetime(df_all_results['race_date'])

    # 各レースごとに直近成績を計算（サンプリングで高速化）
    recent_stats = []

    # サンプリング: 1000件ごとに計算
    sample_size = min(1000, len(df))
    df_sample = df.sample(n=sample_size, random_state=42)

    for idx, row in df_sample.iterrows():
        racer_num = row['racer_number']
        race_date = row['race_date']

        # この選手の過去のレース結果を取得
        racer_history = df_all_results[
            (df_all_results['racer_number'] == racer_num) &
            (df_all_results['race_date'] < race_date)
        ].sort_values('race_date', ascending=False)

        if len(racer_history) >= 3:
            recent_3 = racer_history.head(3)
            recent_3_avg_rank = recent_3['rank'].mean()
            recent_3_win_rate = (recent_3['rank'] == 1).sum() / 3.0 * 100
        else:
            recent_3_avg_rank = np.nan
            recent_3_win_rate = np.nan

        if len(racer_history) >= 5:
            recent_5 = racer_history.head(5)
            recent_5_avg_rank = recent_5['rank'].mean()
            recent_5_win_rate = (recent_5['rank'] == 1).sum() / 5.0 * 100
        else:
            recent_5_avg_rank = np.nan
            recent_5_win_rate = np.nan

        if len(racer_history) >= 10:
            recent_10 = racer_history.head(10)
            recent_10_avg_rank = recent_10['rank'].mean()
            recent_10_win_rate = (recent_10['rank'] == 1).sum() / 10.0 * 100
        else:
            recent_10_avg_rank = np.nan
            recent_10_win_rate = np.nan

        recent_stats.append({
            'race_id': row['race_id'],
            'pit_number': row['pit_number'],
            'recent_3_avg_rank': recent_3_avg_rank,
            'recent_3_win_rate': recent_3_win_rate,
            'recent_5_avg_rank': recent_5_avg_rank,
            'recent_5_win_rate': recent_5_win_rate,
            'recent_10_avg_rank': recent_10_avg_rank,
            'recent_10_win_rate': recent_10_win_rate
        })

    df_recent = pd.DataFrame(recent_stats)

    # マージ（サンプルのみ）
    df = df.merge(df_recent, on=['race_id', 'pit_number'], how='left')

    print(f"  直近成績計算完了（サンプル{len(df_recent)}件）")

    return df

# データセット構築
print("\n[Step 1] 学習データセット構築（2023-06-01〜2024-05-31: 12ヶ月）")
df_train_raw = load_dataset_with_recent_stats("2023-06-01", "2024-05-31")
df_train_raw = df_train_raw[df_train_raw['result_rank'].notna()].copy()
df_train_raw['is_win'] = (df_train_raw['result_rank'].astype(str) == '1').astype(int)
print(f"  学習データ: {len(df_train_raw):,}件")

print("\n[Step 2] テストデータセット構築（2024-06-01〜2024-06-30: 1ヶ月）")
df_test_raw = load_dataset_with_recent_stats("2024-06-01", "2024-06-30")
df_test_raw = df_test_raw[df_test_raw['result_rank'].notna()].copy()
df_test_raw['is_win'] = (df_test_raw['result_rank'].astype(str) == '1').astype(int)
print(f"  テストデータ: {len(df_test_raw):,}件")

def add_features(df):
    """特徴量追加"""
    df = df.copy()

    for i in range(1, 7):
        df[f'pit_number_{i}'] = (df['pit_number'] == i).astype(int)

    if 'actual_course' in df.columns:
        for i in range(1, 7):
            df[f'actual_course_{i}'] = (df['actual_course'] == i).astype(int)
        df['pit_course_diff'] = df['pit_number'] - df['actual_course']

    # 直近成績特徴量はload_dataset_with_recent_statsで既に追加済み

    return df

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

# 直近成績特徴量を確認
recent_features = [col for col in feature_cols if 'recent' in col]
if len(recent_features) > 0:
    print(f"\n  直近成績特徴量:")
    for feat in recent_features:
        print(f"    - {feat}")
else:
    print(f"\n  [警告] 直近成績特徴量が見つかりません")

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
model_path = trainer.save_model("stage2_with_recent_performance.json")
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

print(f"\n[Step 9] 高確率帯: {high_conf_hit_rate:.2%}")

print("\n" + "=" * 80)
print(f"実験#015完了: AUC={auc:.4f}, 的中率(0.8+)={high_conf_hit_rate:.2%}")
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
