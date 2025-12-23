"""
最適化モデルの再トレーニングスクリプト
Phase 1-3の改善を反映した新モデルを学習
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pickle
import json

from src.ml.optimized_trainer import OptimizedModelTrainer
from src.features.optimized_features import OptimizedFeatureGenerator
from src.features.timeseries_features import TimeseriesFeatureGenerator
from config.settings import DATABASE_PATH


def prepare_training_data(venue_code=None, months=8):
    """
    トレーニングデータの準備

    Args:
        venue_code: 会場コード（Noneなら全会場）
        months: 過去何ヶ月分のデータを使用

    Returns:
        X, y, feature_names
    """
    print(f"\n{'='*60}")
    print(f"データ準備: {'全会場' if venue_code is None else f'会場{venue_code}'}")
    print(f"{'='*60}")

    conn = sqlite3.connect(DATABASE_PATH)

    # 日付範囲を設定
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30)

    # レース結果を取得
    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            e.pit_number,
            e.racer_number,
            e.motor_number,
            res.rank,
            r.race_grade
        FROM results res
        JOIN races r ON res.race_id = r.id
        JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
        WHERE r.race_date BETWEEN ? AND ?
    """

    params = [start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')]

    if venue_code:
        query += " AND r.venue_code = ?"
        params.append(venue_code)

    query += " ORDER BY r.race_date, r.venue_code, r.race_number, e.pit_number"

    print(f"データ取得中...")
    df = pd.read_sql_query(query, conn, params=params)
    print(f"取得レコード数: {len(df):,}件")

    # 特徴量生成器の初期化
    opt_feature_gen = OptimizedFeatureGenerator(DATABASE_PATH)
    ts_feature_gen = TimeseriesFeatureGenerator(conn)

    features_list = []
    labels_list = []

    print(f"\n特徴量生成中...")
    total_rows = len(df)
    processed = 0

    for idx, row in df.iterrows():
        try:
            # Phase 1: 最適化特徴量
            opt_features = opt_feature_gen.generate_all_features(
                row['racer_number'],
                row['venue_code'],
                row['race_date']
            )

            # Phase 2: 時系列特徴量
            ts_features = ts_feature_gen.generate_all_timeseries_features(
                row['racer_number'],
                row['motor_number'],
                row['venue_code'],
                row['race_date']
            )

            # 特徴量を統合
            combined_features = {**opt_features, **ts_features}
            combined_features['pit_number'] = row['pit_number']

            # ラベル（1着なら1, それ以外は0）
            label = 1 if row['rank'] == 1 else 0

            features_list.append(combined_features)
            labels_list.append(label)

            processed += 1
            if processed % 1000 == 0:
                progress = (processed / total_rows) * 100
                print(f"  進捗: {processed:,}/{total_rows:,} ({progress:.1f}%)")

        except Exception as e:
            # エラーは無視して続行
            pass

    conn.close()

    print(f"\n特徴量生成完了: {len(features_list):,}サンプル")

    # DataFrameに変換
    X = pd.DataFrame(features_list)
    y = np.array(labels_list)

    # 欠損値を処理
    X = X.fillna(0)

    # 無限値をクリップ
    X = X.replace([np.inf, -np.inf], 0)

    print(f"特徴量数: {X.shape[1]}")
    print(f"正例: {sum(y):,} ({sum(y)/len(y)*100:.2f}%)")
    print(f"負例: {len(y)-sum(y):,} ({(len(y)-sum(y))/len(y)*100:.2f}%)")

    return X, y, list(X.columns)


def train_venue_model(venue_code, months=8):
    """
    会場別モデルをトレーニング

    Args:
        venue_code: 会場コード
        months: 学習データの期間（月）

    Returns:
        dict: トレーニング結果
    """
    print(f"\n{'='*60}")
    print(f"会場別モデル訓練: 会場{venue_code}")
    print(f"{'='*60}")

    # データ準備
    X, y, feature_names = prepare_training_data(venue_code=venue_code, months=months)

    if len(X) < 100:
        print(f"⚠️ データ不足: {len(X)}サンプル < 100")
        return None

    # トレーニング
    trainer = OptimizedModelTrainer()
    model, metrics, calibrated_model = trainer.train(X, y, feature_names)

    # モデル保存
    os.makedirs('models', exist_ok=True)
    model_path = f'models/optimized_venue_{venue_code}.pkl'
    with open(model_path, 'wb') as f:
        pickle.dump(calibrated_model, f)
    print(f"✅ モデル保存: {model_path}")

    # メタデータ保存
    metadata = {
        'venue_code': venue_code,
        'trained_at': datetime.now().isoformat(),
        'n_samples': len(X),
        'n_features': len(feature_names),
        'feature_names': feature_names,
        'metrics': metrics,
        'model_version': 'optimized_v1.0'
    }

    meta_path = f'models/optimized_venue_{venue_code}_meta.json'
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"✅ メタデータ保存: {meta_path}")

    return {
        'venue_code': venue_code,
        'model_path': model_path,
        'metrics': metrics,
        'n_samples': len(X)
    }


def train_general_model(months=8):
    """
    汎用モデルをトレーニング

    Args:
        months: 学習データの期間（月）

    Returns:
        dict: トレーニング結果
    """
    print(f"\n{'='*60}")
    print(f"汎用モデル訓練: 全会場統合")
    print(f"{'='*60}")

    # データ準備（全会場）
    X, y, feature_names = prepare_training_data(venue_code=None, months=months)

    if len(X) < 1000:
        print(f"⚠️ データ不足: {len(X)}サンプル < 1000")
        return None

    # トレーニング
    trainer = OptimizedModelTrainer()
    model, metrics, calibrated_model = trainer.train(X, y, feature_names)

    # モデル保存
    os.makedirs('models', exist_ok=True)
    model_path = 'models/optimized_general.pkl'
    with open(model_path, 'wb') as f:
        pickle.dump(calibrated_model, f)
    print(f"✅ モデル保存: {model_path}")

    # メタデータ保存
    metadata = {
        'model_type': 'general',
        'trained_at': datetime.now().isoformat(),
        'n_samples': len(X),
        'n_features': len(feature_names),
        'feature_names': feature_names,
        'metrics': metrics,
        'model_version': 'optimized_v1.0'
    }

    meta_path = 'models/optimized_general_meta.json'
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"✅ メタデータ保存: {meta_path}")

    return {
        'model_type': 'general',
        'model_path': model_path,
        'metrics': metrics,
        'n_samples': len(X)
    }


def main():
    """メイン処理"""
    print("\n" + "="*60)
    print(" 最適化モデル再トレーニング")
    print(" Phase 1-3の改善を反映")
    print("="*60 + "\n")

    results = []

    # 汎用モデルのトレーニング
    print("\n【ステップ 1/2】汎用モデルのトレーニング")
    general_result = train_general_model(months=8)
    if general_result:
        results.append(general_result)

    # 会場別モデルのトレーニング（上位5会場）
    print("\n【ステップ 2/2】会場別モデルのトレーニング")
    top_venues = ['07', '08', '05', '14', '09']

    for venue_code in top_venues:
        venue_result = train_venue_model(venue_code, months=8)
        if venue_result:
            results.append(venue_result)

    # 結果サマリー
    print("\n" + "="*60)
    print(" トレーニング結果サマリー")
    print("="*60 + "\n")

    for result in results:
        if 'venue_code' in result:
            print(f"【会場{result['venue_code']}】")
        else:
            print(f"【汎用モデル】")

        print(f"  サンプル数: {result['n_samples']:,}")
        print(f"  AUC: {result['metrics']['mean_auc']:.4f} (±{result['metrics']['std_auc']:.4f})")
        print(f"  Accuracy: {result['metrics']['mean_accuracy']:.4f}")
        print(f"  モデルパス: {result['model_path']}")
        print()

    # 全体統計
    aucs = [r['metrics']['mean_auc'] for r in results]
    print(f"全モデル平均AUC: {np.mean(aucs):.4f}")
    print(f"最高AUC: {np.max(aucs):.4f}")
    print(f"最低AUC: {np.min(aucs):.4f}")

    print("\n✅ すべてのトレーニングが完了しました")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
