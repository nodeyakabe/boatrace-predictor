"""
モデル性能ベンチマーク
新旧モデルの比較評価
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
from sklearn.metrics import roc_auc_score, accuracy_score, precision_score, recall_score, f1_score


def load_model(model_path):
    """モデルをロード"""
    if not os.path.exists(model_path):
        return None
    try:
        with open(model_path, 'rb') as f:
            return pickle.load(f)
    except:
        return None


def prepare_test_data(venue_code=None, days=30):
    """
    テストデータの準備（最近のデータ）

    Args:
        venue_code: 会場コード
        days: 過去何日分

    Returns:
        X, y, race_info
    """
    from config.settings import DATABASE_PATH
    from src.features.optimized_features import OptimizedFeatureGenerator
    from src.features.timeseries_features import TimeseriesFeatureGenerator

    conn = sqlite3.connect(DATABASE_PATH)

    # 日付範囲
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # レース結果を取得
    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            e.pit_number,
            e.racer_number,
            e.racer_name,
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

    query += " ORDER BY r.race_date DESC, r.venue_code, r.race_number, e.pit_number"

    df = pd.read_sql_query(query, conn, params=params)

    if len(df) == 0:
        conn.close()
        return None, None, None

    # 特徴量生成
    opt_feature_gen = OptimizedFeatureGenerator(DATABASE_PATH)
    ts_feature_gen = TimeseriesFeatureGenerator(conn)

    features_list = []
    labels_list = []
    race_info_list = []

    for idx, row in df.iterrows():
        try:
            # 特徴量生成
            opt_features = opt_feature_gen.generate_all_features(
                row['racer_number'],
                row['venue_code'],
                row['race_date']
            )

            ts_features = ts_feature_gen.generate_all_timeseries_features(
                row['racer_number'],
                row['motor_number'],
                row['venue_code'],
                row['race_date']
            )

            combined_features = {**opt_features, **ts_features}
            combined_features['pit_number'] = row['pit_number']

            label = 1 if row['rank'] == 1 else 0

            features_list.append(combined_features)
            labels_list.append(label)
            race_info_list.append({
                'race_id': row['race_id'],
                'venue_code': row['venue_code'],
                'race_date': row['race_date'],
                'race_number': row['race_number'],
                'pit_number': row['pit_number'],
                'racer_name': row['racer_name'],
                'actual_rank': row['rank']
            })

        except:
            pass

    conn.close()

    X = pd.DataFrame(features_list).fillna(0).replace([np.inf, -np.inf], 0)
    y = np.array(labels_list)

    return X, y, race_info_list


def evaluate_model(model, X, y, model_name):
    """
    モデルを評価

    Args:
        model: 評価対象モデル
        X: テストデータ
        y: ラベル
        model_name: モデル名

    Returns:
        dict: 評価指標
    """
    if model is None or X is None or len(X) == 0:
        return None

    # 予測
    y_pred_proba = model.predict_proba(X)[:, 1]
    y_pred = (y_pred_proba >= 0.5).astype(int)

    # 評価指標
    metrics = {
        'model_name': model_name,
        'n_samples': len(y),
        'auc': float(roc_auc_score(y, y_pred_proba)),
        'accuracy': float(accuracy_score(y, y_pred)),
        'precision': float(precision_score(y, y_pred, zero_division=0)),
        'recall': float(recall_score(y, y_pred, zero_division=0)),
        'f1': float(f1_score(y, y_pred, zero_division=0))
    }

    return metrics


def compare_models(old_model_path, new_model_path, venue_code=None):
    """
    新旧モデルを比較

    Args:
        old_model_path: 旧モデルパス
        new_model_path: 新モデルパス
        venue_code: 会場コード

    Returns:
        dict: 比較結果
    """
    print(f"\n{'='*60}")
    print(f"モデル比較: {'全会場' if venue_code is None else f'会場{venue_code}'}")
    print(f"{'='*60}")

    # モデルロード
    old_model = load_model(old_model_path)
    new_model = load_model(new_model_path)

    if old_model is None and new_model is None:
        print("⚠️ 両方のモデルが存在しません")
        return None

    # テストデータ準備
    print("テストデータ準備中...")
    X, y, race_info = prepare_test_data(venue_code=venue_code, days=30)

    if X is None or len(X) == 0:
        print("⚠️ テストデータが不足しています")
        return None

    print(f"テストサンプル数: {len(X):,}")

    # 旧モデル評価
    old_metrics = None
    if old_model is not None:
        print("\n旧モデル評価中...")
        old_metrics = evaluate_model(old_model, X, y, "旧モデル")
        if old_metrics:
            print(f"  AUC: {old_metrics['auc']:.4f}")
            print(f"  Accuracy: {old_metrics['accuracy']:.4f}")

    # 新モデル評価
    new_metrics = None
    if new_model is not None:
        print("\n新モデル評価中...")
        new_metrics = evaluate_model(new_model, X, y, "新モデル")
        if new_metrics:
            print(f"  AUC: {new_metrics['auc']:.4f}")
            print(f"  Accuracy: {new_metrics['accuracy']:.4f}")

    # 比較
    comparison = {
        'venue_code': venue_code if venue_code else 'general',
        'old_model': old_metrics,
        'new_model': new_metrics,
        'n_test_samples': len(X)
    }

    if old_metrics and new_metrics:
        comparison['improvements'] = {
            'auc_diff': new_metrics['auc'] - old_metrics['auc'],
            'auc_improvement_pct': ((new_metrics['auc'] - old_metrics['auc']) / old_metrics['auc']) * 100,
            'accuracy_diff': new_metrics['accuracy'] - old_metrics['accuracy']
        }

        print("\n改善度:")
        print(f"  AUC改善: {comparison['improvements']['auc_diff']:+.4f} ({comparison['improvements']['auc_improvement_pct']:+.2f}%)")
        print(f"  Accuracy改善: {comparison['improvements']['accuracy_diff']:+.4f}")

    return comparison


def main():
    """メイン処理"""
    print("\n" + "="*60)
    print(" モデル性能ベンチマーク")
    print(" 新旧モデルの比較評価")
    print("="*60 + "\n")

    comparisons = []

    # 汎用モデルの比較
    print("\n【汎用モデル】")
    general_comparison = compare_models(
        'models/stage2_combined_8months.pkl',
        'models/optimized_general.pkl',
        venue_code=None
    )
    if general_comparison:
        comparisons.append(general_comparison)

    # 会場別モデルの比較
    top_venues = ['07', '08', '05', '14', '09']

    for venue_code in top_venues:
        print(f"\n【会場{venue_code}】")
        venue_comparison = compare_models(
            f'models/stage2_venue_{venue_code}.pkl',
            f'models/optimized_venue_{venue_code}.pkl',
            venue_code=venue_code
        )
        if venue_comparison:
            comparisons.append(venue_comparison)

    # 総合レポート
    print("\n" + "="*60)
    print(" 総合ベンチマークレポート")
    print("="*60 + "\n")

    for comp in comparisons:
        venue = comp['venue_code']
        print(f"【{venue}】")

        if comp.get('old_model'):
            print(f"  旧モデルAUC: {comp['old_model']['auc']:.4f}")
        if comp.get('new_model'):
            print(f"  新モデルAUC: {comp['new_model']['auc']:.4f}")

        if comp.get('improvements'):
            imp = comp['improvements']
            symbol = "📈" if imp['auc_diff'] > 0 else "📉"
            print(f"  {symbol} 改善度: {imp['auc_diff']:+.4f} ({imp['auc_improvement_pct']:+.2f}%)")

        print()

    # 統計サマリー
    if comparisons:
        improvements = [c['improvements']['auc_diff'] for c in comparisons if 'improvements' in c]
        if improvements:
            print(f"平均改善度: {np.mean(improvements):+.4f}")
            print(f"最大改善: {np.max(improvements):+.4f}")
            print(f"最小改善: {np.min(improvements):+.4f}")

    # 結果をJSONで保存
    os.makedirs('benchmarks', exist_ok=True)
    benchmark_path = f'benchmarks/benchmark_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(benchmark_path, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'comparisons': comparisons
        }, f, indent=2, ensure_ascii=False)

    print(f"\n✅ ベンチマーク結果保存: {benchmark_path}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
