"""
全会場別モデル学習スクリプト

実験#021: 全24会場それぞれに専用モデルを学習
- 対象会場: 全24会場 (01〜24)
- 学習期間: 2023-06-01 〜 2024-05-31（12ヶ月）
- テスト期間: 2024-06-01 〜 2024-06-30（1ヶ月）
- データ量が少ない会場は統合モデルを使用
"""

import sys
sys.path.append('.')

import sqlite3
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score, log_loss
from datetime import datetime
from src.ml.model_trainer import ModelTrainer
import os

print("=" * 80)
print("全会場別モデル学習（実験#021）")
print("=" * 80)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def load_dataset(start_date, end_date, venue_codes=None):
    """データセット取得"""
    conn = sqlite3.connect('data/boatrace.db')

    where_venue = ""
    params = [start_date, end_date]

    if venue_codes:
        placeholders = ','.join(['?'] * len(venue_codes))
        where_venue = f"AND r.venue_code IN ({placeholders})"
        params.extend(venue_codes)

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
        WHERE r.race_date BETWEEN ? AND ? {where_venue}
        ORDER BY r.race_date, r.venue_code, r.race_number, e.pit_number
    """

    df = pd.read_sql_query(query, conn, params=params)
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

# 全会場のデータ量を確認
print("\n[Step 1] 全会場データ量確認")
conn = sqlite3.connect('data/boatrace.db')
query_venue_stats = """
    SELECT
        r.venue_code,
        COUNT(*) as race_count,
        COUNT(DISTINCT r.race_date) as race_days
    FROM races r
    WHERE r.race_date BETWEEN '2023-06-01' AND '2024-05-31'
    GROUP BY r.venue_code
    ORDER BY r.venue_code
"""
df_venue_stats = pd.read_sql_query(query_venue_stats, conn)
conn.close()

print(f"{'会場':<8} {'レース数':<12} {'開催日数':<12}")
print("-" * 40)
for _, row in df_venue_stats.iterrows():
    print(f"{row['venue_code']:<8} {row['race_count']:<12} {row['race_days']:<12}")

# 会場ごとにモデル学習
results = []
min_train_samples = 500  # 最小学習サンプル数
min_test_samples = 30    # 最小テストサンプル数

for _, row in df_venue_stats.iterrows():
    venue_code = row['venue_code']

    print(f"\n{'='*80}")
    print(f"会場 {venue_code} のモデル学習")
    print(f"{'='*80}")

    # 学習データ
    df_train_raw = load_dataset("2023-06-01", "2024-05-31", [venue_code])
    df_train_raw = df_train_raw[df_train_raw['result_rank'].notna()].copy()
    df_train_raw['is_win'] = (df_train_raw['result_rank'].astype(str) == '1').astype(int)

    # テストデータ
    df_test_raw = load_dataset("2024-06-01", "2024-06-30", [venue_code])
    df_test_raw = df_test_raw[df_test_raw['result_rank'].notna()].copy()
    df_test_raw['is_win'] = (df_test_raw['result_rank'].astype(str) == '1').astype(int)

    print(f"  学習データ: {len(df_train_raw):,}件")
    print(f"  テストデータ: {len(df_test_raw):,}件")

    if len(df_train_raw) < min_train_samples or len(df_test_raw) < min_test_samples:
        print(f"  [スキップ] データ量不足（学習: {len(df_train_raw)}, テスト: {len(df_test_raw)}）")
        results.append({
            'venue_code': venue_code,
            'status': 'skipped',
            'reason': 'insufficient_data',
            'train_count': len(df_train_raw),
            'test_count': len(df_test_raw),
            'auc': None,
            'hit_rate_08': None
        })
        continue

    # 特徴量追加
    df_train = add_features(df_train_raw)
    df_test = add_features(df_test_raw)

    # 特徴量抽出
    train_numeric_cols = df_train.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
    test_numeric_cols = df_test.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
    exclude_cols = ['race_id', 'is_win', 'result_rank', 'venue_code']

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

    print(f"  X_train: {X_train.shape}, X_test: {X_test.shape}")

    # モデル学習
    try:
        trainer = ModelTrainer(model_dir="models")
        trainer.train(X_train, y_train, X_test, y_test)

        # モデル保存
        model_path = trainer.save_model(f"stage2_venue_{venue_code}.json")
        print(f"  保存: {model_path}")

        # 評価
        y_pred = trainer.predict(X_test)
        auc = roc_auc_score(y_test, y_pred)
        logloss = log_loss(y_test, y_pred)

        # 高確率帯分析
        high_conf_mask = y_pred >= 0.8
        high_conf_count = high_conf_mask.sum()
        high_conf_wins = y_test[high_conf_mask].sum()
        high_conf_hit_rate = high_conf_wins / high_conf_count if high_conf_count > 0 else 0

        print(f"  AUC: {auc:.4f}")
        print(f"  Log Loss: {logloss:.4f}")
        print(f"  的中率(0.8+): {high_conf_hit_rate:.2%} ({high_conf_count}件)")

        results.append({
            'venue_code': venue_code,
            'status': 'success',
            'train_count': len(X_train),
            'test_count': len(X_test),
            'auc': auc,
            'logloss': logloss,
            'hit_rate_08': high_conf_hit_rate,
            'high_conf_count': high_conf_count
        })
    except Exception as e:
        print(f"  [エラー] {str(e)}")
        results.append({
            'venue_code': venue_code,
            'status': 'error',
            'reason': str(e),
            'train_count': len(X_train),
            'test_count': len(X_test),
            'auc': None,
            'hit_rate_08': None
        })

# 結果サマリー
print(f"\n{'='*80}")
print("全会場別モデルの評価サマリー")
print(f"{'='*80}")

df_results = pd.DataFrame(results)

print(f"\n{'会場':<8} {'状態':<12} {'学習':<8} {'テスト':<8} {'AUC':<10} {'的中率(0.8+)':<15}")
print("-" * 80)
for _, row in df_results.iterrows():
    if row['status'] == 'success':
        print(f"{row['venue_code']:<8} {row['status']:<12} {row['train_count']:<8} {row['test_count']:<8} {row['auc']:<10.4f} {row['hit_rate_08']:<15.2%}")
    else:
        print(f"{row['venue_code']:<8} {row['status']:<12} {row['train_count']:<8} {row['test_count']:<8} {'N/A':<10} {'N/A':<15}")

# 成功した会場のみで統計
df_success = df_results[df_results['status'] == 'success']

if len(df_success) > 0:
    print(f"\n成功した会場の平均性能:")
    print(f"  対象会場数: {len(df_success)}")
    print(f"  平均AUC: {df_success['auc'].mean():.4f}")
    print(f"  最高AUC: {df_success['auc'].max():.4f} (会場: {df_success.loc[df_success['auc'].idxmax(), 'venue_code']})")
    print(f"  最低AUC: {df_success['auc'].min():.4f} (会場: {df_success.loc[df_success['auc'].idxmin(), 'venue_code']})")
    print(f"  平均的中率(0.8+): {df_success['hit_rate_08'].mean():.2%}")

    # 実験#012（全会場統合モデル）との比較
    print(f"\n実験#012（全会場統合）との比較:")
    print(f"  実験#012 AUC: 0.8496")
    print(f"  会場別平均 AUC: {df_success['auc'].mean():.4f}")
    print(f"  差分: {df_success['auc'].mean() - 0.8496:+.4f}")

    # 統合モデルより良い会場
    better_venues = df_success[df_success['auc'] > 0.8496]
    print(f"\n統合モデル(0.8496)を上回る会場: {len(better_venues)}会場")
    if len(better_venues) > 0:
        for _, row in better_venues.iterrows():
            print(f"  会場{row['venue_code']}: AUC {row['auc']:.4f} (差分: +{row['auc'] - 0.8496:.4f})")

print(f"\nスキップされた会場: {len(df_results[df_results['status'] == 'skipped'])}")
print(f"エラーが発生した会場: {len(df_results[df_results['status'] == 'error'])}")

print("\n" + "=" * 80)
print(f"実験#021完了")
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
