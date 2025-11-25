"""
Stage1モデルの学習・評価・最適化スクリプト

新しい特徴量（22個）とOptunaによるハイパーパラメータチューニングを実施
"""

import sys
sys.path.append('.')

from src.ml.race_selector import RaceSelector
from sklearn.model_selection import train_test_split
import matplotlib.pyplot as plt
import pandas as pd


def main():
    print("=" * 70)
    print("Stage1: レース選別モデル - 学習・評価・最適化")
    print("=" * 70)

    # 1. データ準備
    print("\n【Step 1】 学習データを準備中...")
    selector = RaceSelector()

    # 最近6ヶ月のデータを使用
    X, y = selector.prepare_training_data(
        start_date='2024-01-01',
        end_date='2024-06-30'
    )

    print(f"\n【データ統計】")
    print(f"  データ数: {len(X):,}件")
    print(f"  正例率: {y.mean():.2%}")
    print(f"  特徴量数: {len([col for col in X.columns if col != 'race_id'])}個")

    # 特徴量一覧
    feature_cols = [col for col in X.columns if col != 'race_id']
    print(f"\n【特徴量一覧】")
    for i, col in enumerate(feature_cols, 1):
        print(f"  {i:2d}. {col}")

    # 2. データ分割
    print(f"\n【Step 2】 データ分割中...")
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.3, random_state=42, shuffle=False
    )
    X_valid, X_test, y_valid, y_test = train_test_split(
        X_temp, y_temp, test_size=0.5, random_state=42, shuffle=False
    )

    print(f"  訓練: {len(X_train):,}件 ({len(X_train)/len(X):.1%})")
    print(f"  検証: {len(X_valid):,}件 ({len(X_valid)/len(X):.1%})")
    print(f"  テスト: {len(X_test):,}件 ({len(X_test)/len(X):.1%})")

    # 3. ベースライン学習（デフォルトパラメータ）
    print(f"\n【Step 3】 ベースラインモデル学習中...")
    summary_baseline = selector.train(X_train, y_train, X_valid, y_valid)

    print(f"\n【ベースライン結果】")
    print(f"  Train AUC: {summary_baseline['train_auc']:.4f}")
    print(f"  Valid AUC: {summary_baseline['valid_auc']:.4f}")

    # 4. ハイパーパラメータ最適化（Optuna）
    print(f"\n【Step 4】 ハイパーパラメータ最適化中（Optuna, 30試行）...")
    optimization_result = selector.optimize_hyperparameters(
        X_train, y_train, X_valid, y_valid, n_trials=30
    )

    best_params = optimization_result['best_params']
    best_auc = optimization_result['best_auc']

    print(f"\n【最適化結果】")
    print(f"  Best Valid AUC: {best_auc:.4f}")
    print(f"  改善度: {(best_auc - summary_baseline['valid_auc']) / summary_baseline['valid_auc'] * 100:+.2f}%")

    # 5. 最適パラメータで再学習
    print(f"\n【Step 5】 最適パラメータで再学習中...")
    # XGBoostパラメータに変換
    final_params = {
        'objective': 'binary:logistic',
        'eval_metric': 'auc',
        **best_params
    }

    summary_final = selector.train(X_train, y_train, X_valid, y_valid, params=final_params)

    print(f"\n【最終モデル性能】")
    print(f"  Train AUC: {summary_final['train_auc']:.4f}")
    print(f"  Valid AUC: {summary_final['valid_auc']:.4f}")

    # 6. テストデータで評価
    print(f"\n【Step 6】 テストデータで最終評価中...")
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score, precision_recall_curve, confusion_matrix, classification_report

    feature_cols = [col for col in X_test.columns if col != 'race_id']
    X_test_features = X_test[feature_cols]
    dtest = xgb.DMatrix(X_test_features, feature_names=feature_cols)

    y_pred_proba = selector.model.predict(dtest)
    test_auc = roc_auc_score(y_test, y_pred_proba)

    print(f"\n【テスト結果】")
    print(f"  Test AUC: {test_auc:.4f}")

    # 閾値別の評価
    print(f"\n【閾値別評価】")
    for threshold in [0.3, 0.4, 0.5, 0.6, 0.7]:
        y_pred_binary = (y_pred_proba >= threshold).astype(int)
        from sklearn.metrics import precision_score, recall_score, f1_score

        precision = precision_score(y_test, y_pred_binary, zero_division=0)
        recall = recall_score(y_test, y_pred_binary, zero_division=0)
        f1 = f1_score(y_test, y_pred_binary, zero_division=0)

        print(f"  閾値 {threshold:.1f}: Precision={precision:.3f}, Recall={recall:.3f}, F1={f1:.3f}")

    # 7. 特徴量重要度
    print(f"\n【特徴量重要度 Top 10】")
    importance_dict = selector.model.get_score(importance_type='gain')

    # 重要度でソート
    importance_sorted = sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)

    for i, (feature, importance) in enumerate(importance_sorted[:10], 1):
        print(f"  {i:2d}. {feature:<25} {importance:>10.2f}")

    # 8. モデル保存
    print(f"\n【Step 7】 モデル保存中...")
    model_path = selector.save_model("race_selector_optimized.json")
    print(f"  保存完了: {model_path}")

    # 9. サマリーレポート
    print(f"\n" + "=" * 70)
    print("学習完了サマリー")
    print("=" * 70)
    print(f"【データ】")
    print(f"  総データ数: {len(X):,}件")
    print(f"  特徴量数: {len(feature_cols)}個（元10個 → 新規12個追加）")
    print(f"  学習期間: 2024-01-01 ~ 2024-06-30")

    print(f"\n【性能】")
    print(f"  ベースライン Valid AUC: {summary_baseline['valid_auc']:.4f}")
    print(f"  最適化後 Valid AUC: {best_auc:.4f}")
    print(f"  テスト AUC: {test_auc:.4f}")

    print(f"\n【目標達成状況】")
    if test_auc >= 0.75:
        print(f"  ✅ 目標達成！ Test AUC {test_auc:.4f} >= 0.75")
    else:
        print(f"  ⚠️ 目標未達 Test AUC {test_auc:.4f} < 0.75")
        print(f"  差分: {0.75 - test_auc:.4f}")

    print(f"\n【推奨 buy_score 閾値】")
    print(f"  - 保守的: 0.7以上（高精度、少数選択）")
    print(f"  - 標準: 0.6以上（バランス型）")
    print(f"  - 積極的: 0.5以上（多数選択、網羅的）")

    print(f"\n" + "=" * 70)
    print("全ての処理が完了しました")
    print("=" * 70)


if __name__ == "__main__":
    main()
