"""
ディープラーニングモデル検討スクリプト

実験#022: TensorFlow/Kerasを使用したニューラルネットワーク
- 構造: 多層パーセプトロン（MLP）
- 学習期間: 2023-06-01 〜 2024-05-31（12ヶ月）
- テスト期間: 2024-06-01 〜 2024-06-30（1ヶ月）
- XGBoost（実験#012）との比較
"""

import sys
sys.path.append('.')

import sqlite3
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score, log_loss
from sklearn.preprocessing import StandardScaler
from datetime import datetime

# TensorFlow/Kerasのインポート（利用可能な場合）
try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers, callbacks
    HAS_TENSORFLOW = True
except ImportError:
    HAS_TENSORFLOW = False
    print("[警告] TensorFlowがインストールされていません。")
    print("  pip install tensorflow")

print("=" * 80)
print("ディープラーニングモデル検討（実験#022）")
print("=" * 80)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if not HAS_TENSORFLOW:
    print("\n[スキップ] TensorFlowがインストールされていないため、実験を実行できません。")
    print("  以下のコマンドでインストールしてください:")
    print("  pip install tensorflow")
    sys.exit(0)

print(f"TensorFlowバージョン: {tf.__version__}")

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

def create_mlp_model(input_dim, hidden_layers=[128, 64, 32], dropout_rate=0.3):
    """多層パーセプトロンモデルの作成"""
    model = keras.Sequential()

    # 入力層
    model.add(layers.Input(shape=(input_dim,)))

    # 隠れ層
    for i, units in enumerate(hidden_layers):
        model.add(layers.Dense(units, activation='relu', name=f'dense_{i+1}'))
        model.add(layers.BatchNormalization())
        model.add(layers.Dropout(dropout_rate))

    # 出力層（2値分類）
    model.add(layers.Dense(1, activation='sigmoid', name='output'))

    # コンパイル
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss='binary_crossentropy',
        metrics=['AUC', 'accuracy']
    )

    return model

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

# 特徴量抽出（実験#012と同じ順序）
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

print(f"  特徴量数: {len(feature_cols)}個")

# 欠損値処理
X_train = df_train[feature_cols].copy()
X_test = df_test[feature_cols].copy()

for col in X_train.columns:
    if X_train[col].isna().any():
        mean_val = X_train[col].mean()
        X_train.loc[:, col] = X_train[col].fillna(mean_val)
        X_test.loc[:, col] = X_test[col].fillna(mean_val)

y_train = df_train['is_win'].values
y_test = df_test['is_win'].values

print(f"\n[Step 3] データセット準備完了")
print(f"  X_train shape: {X_train.shape}")
print(f"  X_test shape: {X_test.shape}")
print(f"  y_train: {y_train.sum()} wins / {len(y_train)} total ({y_train.mean():.2%})")
print(f"  y_test: {y_test.sum()} wins / {len(y_test)} total ({y_test.mean():.2%})")

# 標準化（ディープラーニングでは重要）
print("\n[Step 4] 特徴量の標準化")
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# モデル作成
print("\n[Step 5] MLPモデル作成")
model = create_mlp_model(
    input_dim=X_train_scaled.shape[1],
    hidden_layers=[128, 64, 32, 16],
    dropout_rate=0.3
)

model.summary()

# コールバック設定
early_stopping = callbacks.EarlyStopping(
    monitor='val_loss',
    patience=10,
    restore_best_weights=True,
    verbose=1
)

reduce_lr = callbacks.ReduceLROnPlateau(
    monitor='val_loss',
    factor=0.5,
    patience=5,
    min_lr=1e-6,
    verbose=1
)

# 学習
print("\n[Step 6] モデル学習")
history = model.fit(
    X_train_scaled, y_train,
    validation_split=0.2,
    epochs=100,
    batch_size=256,
    callbacks=[early_stopping, reduce_lr],
    verbose=1
)

# 評価
print("\n[Step 7] モデル評価")
y_pred = model.predict(X_test_scaled, verbose=0).flatten()

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

print(f"\n[Step 9] 高確率帯分析")
print(f"  0.8以上: {high_conf_hit_rate:.2%} ({high_conf_count}件)")

# XGBoost（実験#012）との比較
print(f"\n[Step 10] 実験#012（XGBoost）との比較")
print("-" * 80)
print(f"{'指標':<25} {'実験#012':<15} {'実験#022':<15} {'差分':<15}")
print("-" * 80)

exp012_auc = 0.8496
exp012_logloss = 0.3179
exp012_hit_08 = 87.72

print(f"{'AUC':<25} {exp012_auc:<15.4f} {auc:<15.4f} {auc - exp012_auc:+.4f}")
print(f"{'Log Loss':<25} {exp012_logloss:<15.4f} {logloss:<15.4f} {logloss - exp012_logloss:+.4f}")
print(f"{'的中率（0.8+）':<25} {exp012_hit_08:<14.2f}% {high_conf_hit_rate*100:<14.2f}% {high_conf_hit_rate*100 - exp012_hit_08:+.2f}pt")

# モデル保存
print(f"\n[Step 11] モデル保存")
model.save('models/deep_learning_model.h5')
print("  保存先: models/deep_learning_model.h5")

# 学習履歴の表示
print(f"\n[Step 12] 学習履歴")
final_epoch = len(history.history['loss'])
print(f"  最終エポック: {final_epoch}")
print(f"  最終訓練Loss: {history.history['loss'][-1]:.4f}")
print(f"  最終検証Loss: {history.history['val_loss'][-1]:.4f}")
print(f"  最終訓練AUC: {history.history['auc'][-1]:.4f}")
print(f"  最終検証AUC: {history.history['val_auc'][-1]:.4f}")

print("\n" + "=" * 80)
print(f"実験#022完了: AUC={auc:.4f}, 的中率(0.8+)={high_conf_hit_rate:.2%}")
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)

print("\n考察:")
print("  - ディープラーニングは大量のデータで威力を発揮しますが、")
print("    表形式データではXGBoostが優れている場合が多いです")
print("  - ハイパーパラメータ調整により性能向上の余地があります")
print("  - より複雑なアーキテクチャ（残差接続、Attention機構）も検討できます")
