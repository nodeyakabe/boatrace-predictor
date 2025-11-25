"""
複勝・3連単予測モデル学習スクリプト

実験#018: 複勝（3着以内）と3連単（1-2-3着順）の予測
- 複勝モデル: 3着以内に入る確率を予測（Multi-class）
- 3連単特徴量: レース内の相対的な強さを特徴量化
- 学習期間: 2023-06-01 〜 2024-05-31（12ヶ月）
- テスト期間: 2024-06-01 〜 2024-06-30（1ヶ月）
"""

import sys
sys.path.append('.')

import sqlite3
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score, log_loss, accuracy_score
from datetime import datetime
from src.ml.model_trainer import ModelTrainer
import xgboost as xgb

print("=" * 80)
print("複勝・3連単予測モデル学習（実験#018）")
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

def add_features_with_relative_strength(df):
    """特徴量追加（レース内相対強度含む）"""
    df = df.copy()

    # ベースライン特徴量
    for i in range(1, 7):
        df[f'pit_number_{i}'] = (df['pit_number'] == i).astype(int)

    if 'actual_course' in df.columns:
        for i in range(1, 7):
            df[f'actual_course_{i}'] = (df['actual_course'] == i).astype(int)
        df['pit_course_diff'] = df['pit_number'] - df['actual_course']

    # レース内の相対的な強さ
    df['win_rate_rank_in_race'] = df.groupby('race_id')['win_rate'].rank(ascending=False)
    df['second_rate_rank_in_race'] = df.groupby('race_id')['second_rate'].rank(ascending=False)
    df['motor_rate_rank_in_race'] = df.groupby('race_id')['motor_second_rate'].rank(ascending=False)

    # 勝率の差（トップとの差）
    df['win_rate_diff_from_top'] = df.groupby('race_id')['win_rate'].transform('max') - df['win_rate']

    # モーター性能の差
    df['motor_diff_from_top'] = df.groupby('race_id')['motor_second_rate'].transform('max') - df['motor_second_rate']

    return df

# データセット構築
print("\n[Step 1] データセット構築")
df_train_raw = load_dataset("2023-06-01", "2024-05-31")
df_train_raw = df_train_raw[df_train_raw['result_rank'].notna()].copy()
print(f"  学習データ: {len(df_train_raw):,}件")

df_test_raw = load_dataset("2024-06-01", "2024-06-30")
df_test_raw = df_test_raw[df_test_raw['result_rank'].notna()].copy()
print(f"  テストデータ: {len(df_test_raw):,}件")

# 目的変数作成
df_train_raw['is_win'] = (df_train_raw['result_rank'].astype(str) == '1').astype(int)
df_train_raw['is_place'] = df_train_raw['result_rank'].astype(str).isin(['1', '2', '3']).astype(int)
df_train_raw['result_rank_int'] = df_train_raw['result_rank'].astype(int)

df_test_raw['is_win'] = (df_test_raw['result_rank'].astype(str) == '1').astype(int)
df_test_raw['is_place'] = df_test_raw['result_rank'].astype(str).isin(['1', '2', '3']).astype(int)
df_test_raw['result_rank_int'] = df_test_raw['result_rank'].astype(int)

print(f"\n  複勝（3着以内）:")
print(f"    学習: {df_train_raw['is_place'].sum():,}件 ({df_train_raw['is_place'].mean()*100:.2f}%)")
print(f"    テスト: {df_test_raw['is_place'].sum():,}件 ({df_test_raw['is_place'].mean()*100:.2f}%)")

# 特徴量追加
print("\n[Step 2] 特徴量追加（相対強度含む）")
df_train = add_features_with_relative_strength(df_train_raw)
df_test = add_features_with_relative_strength(df_test_raw)

# 特徴量抽出
train_numeric_cols = df_train.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
test_numeric_cols = df_test.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'is_place', 'result_rank', 'result_rank_int']

common_features = set(train_numeric_cols) & set(test_numeric_cols)
feature_cols = [col for col in common_features if col not in exclude_cols]
feature_cols = sorted(feature_cols)

print(f"  特徴量数: {len(feature_cols)}個")

# 相対強度特徴量を確認
relative_features = [col for col in feature_cols if 'rank_in_race' in col or 'diff_from_top' in col]
if len(relative_features) > 0:
    print(f"\n  相対強度特徴量:")
    for feat in relative_features:
        print(f"    - {feat}")

# 欠損値処理
X_train = df_train[feature_cols].copy()
X_test = df_test[feature_cols].copy()

for col in X_train.columns:
    if X_train[col].isna().any():
        mean_val = X_train[col].mean()
        X_train.loc[:, col] = X_train[col].fillna(mean_val)
        X_test.loc[:, col] = X_test[col].fillna(mean_val)

y_train_win = df_train['is_win']
y_test_win = df_test['is_win']

y_train_place = df_train['is_place']
y_test_place = df_test['is_place']

print(f"\n[Step 3] データセット準備完了")
print(f"  X_train shape: {X_train.shape}")
print(f"  X_test shape: {X_test.shape}")

# =====================================
# モデル1: 単勝予測（ベースライン）
# =====================================
print(f"\n{'='*80}")
print("モデル1: 単勝予測（ベースライン）")
print(f"{'='*80}")

trainer_win = ModelTrainer(model_dir="models")
trainer_win.train(X_train, y_train_win, X_test, y_test_win)
model_path_win = trainer_win.save_model("stage2_win_with_relative.json")

y_pred_win = trainer_win.predict(X_test)
auc_win = roc_auc_score(y_test_win, y_pred_win)

print(f"\n単勝モデル結果:")
print(f"  AUC: {auc_win:.4f}")

high_conf_mask = y_pred_win >= 0.8
high_conf_count = high_conf_mask.sum()
high_conf_wins = y_test_win[high_conf_mask].sum()
high_conf_hit_rate = high_conf_wins / high_conf_count if high_conf_count > 0 else 0
print(f"  的中率(0.8+): {high_conf_hit_rate:.2%} ({high_conf_count}件)")

# =====================================
# モデル2: 複勝予測（3着以内）
# =====================================
print(f"\n{'='*80}")
print("モデル2: 複勝予測（3着以内）")
print(f"{'='*80}")

trainer_place = ModelTrainer(model_dir="models")
trainer_place.train(X_train, y_train_place, X_test, y_test_place)
model_path_place = trainer_place.save_model("stage2_place_with_relative.json")

y_pred_place = trainer_place.predict(X_test)
auc_place = roc_auc_score(y_test_place, y_pred_place)

print(f"\n複勝モデル結果:")
print(f"  AUC: {auc_place:.4f}")

# 確率帯別分析
print("\n確率帯別的中率:")
print("-" * 60)
prob_bins = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
for i in range(len(prob_bins) - 1):
    lower = prob_bins[i]
    upper = prob_bins[i + 1]
    mask = (y_pred_place >= lower) & (y_pred_place < upper)
    count = mask.sum()
    if count > 0:
        places = y_test_place[mask].sum()
        hit_rate = places / count
        print(f"{lower:.1f}-{upper:.1f}      {count:<10} {int(places):<10} {hit_rate:>7.2%}")

# 高確率帯
high_conf_mask_place = y_pred_place >= 0.8
high_conf_count_place = high_conf_mask_place.sum()
high_conf_places = y_test_place[high_conf_mask_place].sum()
high_conf_hit_rate_place = high_conf_places / high_conf_count_place if high_conf_count_place > 0 else 0

print(f"\n的中率(0.8+): {high_conf_hit_rate_place:.2%} ({high_conf_count_place}件)")

# =====================================
# モデル3: 3連単用特徴量スコア
# =====================================
print(f"\n{'='*80}")
print("モデル3: 3連単用相対強度スコア")
print(f"{'='*80}")

# 各艇の総合スコアを計算
df_test_score = df_test.copy()
df_test_score['win_pred'] = y_pred_win
df_test_score['place_pred'] = y_pred_place

# レースごとに予測確率でランキング
df_test_score['predicted_rank'] = df_test_score.groupby('race_id')['win_pred'].rank(ascending=False)

print("\n3連単予測のための相対ランク:")
print("（各レースの1-2-3着を予測確率順に推定）")

# サンプルレースで確認
sample_races = df_test_score['race_id'].unique()[:5]
for race_id in sample_races:
    race_data = df_test_score[df_test_score['race_id'] == race_id].sort_values('predicted_rank')

    if len(race_data) > 0:
        print(f"\nレースID: {race_id}")
        print(f"{'枠':<4} {'予測順位':<10} {'単勝確率':<12} {'複勝確率':<12} {'実際の着順':<10}")
        print("-" * 60)

        for _, row in race_data.head(3).iterrows():
            print(f"{int(row['pit_number']):<4} {int(row['predicted_rank']):<10} "
                  f"{row['win_pred']:<12.2%} {row['place_pred']:<12.2%} "
                  f"{int(row['result_rank_int']):<10}")

# 3連単的中率の計算（予測順位と実際の順位を比較）
print(f"\n{'='*80}")
print("3連単的中率の推定")
print(f"{'='*80}")

correct_trifecta = 0
total_races = 0

for race_id in df_test_score['race_id'].unique():
    race_data = df_test_score[df_test_score['race_id'] == race_id].sort_values('predicted_rank')

    if len(race_data) >= 3:
        # 予測上位3艇
        predicted_top3 = race_data.head(3)['pit_number'].tolist()

        # 実際の上位3艇
        race_data_actual = race_data.sort_values('result_rank_int')
        actual_top3 = race_data_actual.head(3)['pit_number'].tolist()

        # 完全一致チェック
        if predicted_top3 == actual_top3:
            correct_trifecta += 1

        total_races += 1

trifecta_accuracy = correct_trifecta / total_races if total_races > 0 else 0

print(f"\n3連単的中数: {correct_trifecta} / {total_races}")
print(f"3連単的中率: {trifecta_accuracy:.2%}")

# 順位ごとの的中率
print(f"\n順位別的中率:")
for rank in [1, 2, 3]:
    correct_rank = 0

    for race_id in df_test_score['race_id'].unique():
        race_data = df_test_score[df_test_score['race_id'] == race_id].sort_values('predicted_rank')

        if len(race_data) >= rank:
            predicted_pit = race_data.iloc[rank-1]['pit_number']

            race_data_actual = race_data.sort_values('result_rank_int')
            actual_pit = race_data_actual.iloc[rank-1]['pit_number']

            if predicted_pit == actual_pit:
                correct_rank += 1

    rank_accuracy = correct_rank / total_races if total_races > 0 else 0
    print(f"  {rank}着的中率: {rank_accuracy:.2%}")

# 比較サマリー
print(f"\n{'='*80}")
print("モデル比較サマリー")
print(f"{'='*80}")

print(f"\n{'モデル':<25} {'AUC':<10} {'的中率(0.8+)':<15}")
print("-" * 50)
print(f"{'単勝モデル':<25} {auc_win:<10.4f} {high_conf_hit_rate:<15.2%}")
print(f"{'複勝モデル':<25} {auc_place:<10.4f} {high_conf_hit_rate_place:<15.2%}")
print(f"{'3連単推定':<25} {'-':<10} {trifecta_accuracy:<15.2%}")

print("\n" + "=" * 80)
print(f"実験#018完了")
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
