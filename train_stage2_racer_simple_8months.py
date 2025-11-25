"""
Stage2モデル学習スクリプト（選手特徴量シンプル版8ヶ月学習）

実験#009b: 選手特徴量をシンプルに追加して性能向上を目指す
- 学習期間: 2023-10-01 〜 2024-05-31（8ヶ月）
- テスト期間: 2024-06-01 〜 2024-06-30（1ヶ月）
- 特徴量: ベースライン30 + 選手基本特徴量4
- 新規追加特徴量:
  1. f_count（フライング回数）
  2. l_count（出遅れ回数）
  3. motor_second_rate（モーター2連率）
  4. boat_second_rate（ボート2連率）
- 前回の失敗原因:
  - DatasetBuilderがf_count等を取得していなかった
  - 複雑な派生特徴量を作りすぎた
- 今回の改善:
  - SQLクエリを直接修正してf_count等を取得
  - シンプルな特徴量のみ追加
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
print("Stage2モデル学習 - 選手特徴量シンプル版8ヶ月学習（実験#009b）")
print("=" * 80)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ========================================
# データ取得関数（f_count等を含む）
# ========================================
def load_dataset(start_date, end_date):
    """データベースから学習データを取得（f_count, l_count等を含む）"""
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

# データセット構築（学習用: 8ヶ月）
print("\n[Step 1] 学習データセット構築（2023-10-01〜2024-05-31: 8ヶ月）")
df_train_raw = load_dataset("2023-10-01", "2024-05-31")
print(f"  生データ: {len(df_train_raw):,}件")

df_train_raw = df_train_raw[df_train_raw['result_rank'].notna()].copy()
print(f"  結果あり: {len(df_train_raw):,}件")

# データセット構築（テスト用: 1ヶ月）
print("\n[Step 2] テストデータセット構築（2024-06-01〜2024-06-30: 1ヶ月）")
df_test_raw = load_dataset("2024-06-01", "2024-06-30")
print(f"  生データ: {len(df_test_raw):,}件")

df_test_raw = df_test_raw[df_test_raw['result_rank'].notna()].copy()
print(f"  結果あり: {len(df_test_raw):,}件")

# 目的変数作成
df_train_raw['is_win'] = (df_train_raw['result_rank'].astype(str) == '1').astype(int)
df_test_raw['is_win'] = (df_test_raw['result_rank'].astype(str) == '1').astype(int)

print(f"  学習データ正例: {df_train_raw['is_win'].sum():,}件 ({df_train_raw['is_win'].mean()*100:.2f}%)")
print(f"  テストデータ正例: {df_test_raw['is_win'].sum():,}件 ({df_test_raw['is_win'].mean()*100:.2f}%)")

# ========================================
# 特徴量追加関数
# ========================================
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

    # 選手基本特徴量（そのまま使用）
    # f_count, l_count, motor_second_rate, boat_second_rate は
    # load_dataset()で既に取得済み

    return df

# 学習データに特徴量追加
print("\n[Step 3] 学習データに特徴量追加")
df_train = add_features(df_train_raw)
print(f"  特徴量追加後: {len(df_train.columns)}カラム")

# テストデータに特徴量追加
print("\n[Step 4] テストデータに特徴量追加")
df_test = add_features(df_test_raw)
print(f"  特徴量追加後: {len(df_test.columns)}カラム")

# 共通の特徴量カラムを抽出（数値型のみ）
train_numeric_cols = df_train.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
test_numeric_cols = df_test.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()
exclude_cols = ['race_id', 'is_win', 'result_rank']

# 学習とテストで共通の特徴量のみ使用
common_features = set(train_numeric_cols) & set(test_numeric_cols)
feature_cols = [col for col in common_features if col not in exclude_cols]
feature_cols = sorted(feature_cols)  # 順序を固定

print(f"\n[Step 5] 特徴量抽出")
print(f"  共通特徴量数: {len(feature_cols)}個")

# 新規追加された選手特徴量を確認
racer_feature_keywords = ['f_count', 'l_count', 'motor_second_rate', 'boat_second_rate']
racer_features = [col for col in feature_cols if col in racer_feature_keywords]

print(f"\n[INFO] 新規追加された選手関連特徴量（{len(racer_features)}個）:")
for i, col in enumerate(racer_features, 1):
    print(f"  {i}. {col}")

print(f"\n[INFO] 全特徴量一覧:")
for i, col in enumerate(feature_cols, 1):
    marker = " [NEW]" if col in racer_feature_keywords else ""
    print(f"  {i:2d}. {col}{marker}")

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

print(f"\n[Step 6] データセット準備完了")
print(f"  X_train shape: {X_train.shape}")
print(f"  X_test shape: {X_test.shape}")
print(f"  y_train 正例: {y_train.sum():,}件 ({y_train.mean()*100:.2f}%)")
print(f"  y_test 正例: {y_test.sum():,}件 ({y_test.mean()*100:.2f}%)")

# モデル学習
print(f"\n[Step 7] XGBoost学習開始")
trainer = ModelTrainer(model_dir="models")
trainer.train(X_train, y_train, X_test, y_test)

# モデル保存
print(f"\n[Step 8] モデル保存")
model_path = trainer.save_model("stage2_racer_simple_8months.json")
print(f"  保存先: {model_path}")

# 評価
print(f"\n[Step 9] モデル評価（テストデータ: 2024-06）")
y_pred = trainer.predict(X_test)
auc = roc_auc_score(y_test, y_pred)
logloss = log_loss(y_test, y_pred)

print(f"  AUC: {auc:.4f}")
print(f"  Log Loss: {logloss:.4f}")

# 特徴量重要度トップ20
print(f"\n[Step 10] 特徴量重要度 トップ20")
print("-" * 80)

feature_importance = trainer.model.get_score(importance_type='gain')
importance_df = pd.DataFrame([
    {'feature': k, 'importance': v}
    for k, v in feature_importance.items()
]).sort_values('importance', ascending=False)

print(f"{'順位':<6} {'特徴量':<40} {'重要度':<10}")
print("-" * 80)
for rank, (idx, row) in enumerate(importance_df.head(20).iterrows(), 1):
    marker = " [NEW]" if row['feature'] in racer_feature_keywords else ""
    print(f"{rank:<6} {row['feature']:<40}{marker} {row['importance']:<10.1f}")

# 確率帯別分析
print("\n[Step 11] 確率帯別的中率")
print("-" * 60)
print(f"{'確率帯':<15} {'件数':<10} {'的中数':<10} {'的中率':<10}")
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

print(f"\n[Step 12] 高確率帯（0.8以上）分析")
print(f"  対象レース数: {high_conf_count:,}件")
print(f"  的中数: {int(high_conf_wins):,}件")
print(f"  的中率: {high_conf_hit_rate:.2%}")

# 超高確率帯分析
very_high_conf_mask = y_pred >= 0.9
very_high_conf_count = very_high_conf_mask.sum()
very_high_conf_wins = y_test[very_high_conf_mask].sum()
very_high_conf_hit_rate = very_high_conf_wins / very_high_conf_count if very_high_conf_count > 0 else 0

print(f"\n[Step 13] 超高確率帯（0.9以上）分析")
print(f"  対象レース数: {very_high_conf_count:,}件")
print(f"  的中数: {int(very_high_conf_wins):,}件")
print(f"  的中率: {very_high_conf_hit_rate:.2%}")

# 実験比較
print("\n[Step 14] 実験比較")
print("=" * 80)
print("選手特徴量追加による性能変化")
print("-" * 80)

# 過去の実験結果
exp007_auc = 0.8473
exp007_hit_rate_08 = 66.45
exp007_hit_rate_09 = 72.21

print(f"{'指標':<30} {'実験#007':<20} {'実験#009b':<20} {'差分':<15}")
print(f"{'　　':<30} {'(ベースライン)':<20} {'(選手シンプル)':<20} {'　　':<15}")
print("-" * 80)
print(f"{'学習データ数':<30} {f'{len(X_train):,}件':<20} {f'{len(X_train):,}件':<20} {'同じ':<15}")
print(f"{'特徴量数':<30} {'30個':<20} {f'{len(feature_cols)}個':<20} {f'+{len(feature_cols) - 30}個':<15}")
print(f"{'AUC':<30} {exp007_auc:<20.4f} {auc:<20.4f} {auc - exp007_auc:+.4f}")
print(f"{'的中率（0.8+）':<30} {exp007_hit_rate_08:<19.2f}% {high_conf_hit_rate*100:<19.2f}% {high_conf_hit_rate*100 - exp007_hit_rate_08:+.2f}pt")
print(f"{'的中率（0.9+）':<30} {exp007_hit_rate_09:<19.2f}% {very_high_conf_hit_rate*100:<19.2f}% {very_high_conf_hit_rate*100 - exp007_hit_rate_09:+.2f}pt")

# 目標達成確認
print("\n[Step 15] 目標達成確認")
print("=" * 80)

target_auc = 0.86
target_hit_rate = 70.0

print(f"目標値:")
print(f"  AUC: {target_auc:.2f}以上")
print(f"  的中率（0.8+）: {target_hit_rate:.1f}%以上")
print()
print(f"実績値:")
print(f"  AUC: {auc:.4f} {'[達成]' if auc >= target_auc else '[未達成]'}")
print(f"  的中率（0.8+）: {high_conf_hit_rate*100:.2f}% {'[達成]' if high_conf_hit_rate*100 >= target_hit_rate else '[未達成]'}")

# 結論
print("\n[Step 16] 結論")
print("=" * 80)

auc_diff = auc - exp007_auc
hit_rate_diff = high_conf_hit_rate * 100 - exp007_hit_rate_08

if auc >= target_auc and high_conf_hit_rate * 100 >= target_hit_rate:
    print(f"[SUCCESS] 目標を達成！")
    print(f"          AUC {auc:.4f}、的中率（0.8+）{high_conf_hit_rate*100:.2f}%")
    print(f"          選手特徴量の追加が大きく貢献（AUC {auc_diff:+.4f}）")
    print(f"          -> 実験#009bを新たな推奨モデルとする")
elif auc >= exp007_auc + 0.01:
    print(f"[OK] 選手特徴量追加により性能が大幅に向上（AUC {auc_diff:+.4f}）")
    print(f"     的中率も{hit_rate_diff:+.2f}pt向上")
    print(f"     -> 実験#009bを推奨モデルとする")
elif auc >= exp007_auc:
    print(f"[OK] 選手特徴量追加により性能が向上（AUC {auc_diff:+.4f}）")
    print(f"     -> 実験#009bを推奨モデルとする")
elif auc >= exp007_auc - 0.005:
    print(f"[INFO] 選手特徴量追加の効果は限定的（AUC差 {auc_diff:+.4f}）")
    print(f"       -> 実験#007と実験#009bの両方を候補とする")
else:
    print(f"[WARNING] 選手特徴量追加により性能が低下（AUC {auc_diff:+.4f}）")
    print(f"          -> 過学習の可能性、実験#007を推奨")

print("\n特徴量重要度分析:")
# 新規追加特徴量がトップ20に入っているか確認
new_features_in_top20 = importance_df.head(20)[importance_df.head(20)['feature'].isin(racer_feature_keywords)]
if len(new_features_in_top20) > 0:
    print(f"  新規追加の選手特徴量がトップ20に{len(new_features_in_top20)}個入っています：")
    for idx, row in new_features_in_top20.iterrows():
        rank = importance_df.index.get_loc(idx) + 1
        print(f"    {rank}位. {row['feature']} (重要度: {row['importance']:.1f})")
else:
    print(f"  新規追加の選手特徴量はトップ20に入っていません")
    print(f"  -> これらの特徴量は予測に寄与していない可能性")

print("\n" + "=" * 80)
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
