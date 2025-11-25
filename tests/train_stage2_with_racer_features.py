"""
Stage2モデル再学習スクリプト - 選手特徴量追加版

新しい選手特徴量（7個）を含むデータセットでStage2モデルを再学習し、
性能改善を検証します。

期待される改善:
- AUC: +0.03〜0.05
- Log Loss: 5〜10%改善
- 最終的なROI: +10〜15%改善
"""

import sys
sys.path.append('.')

from src.ml.dataset_builder import DatasetBuilder
from src.ml.model_trainer import ModelTrainer
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, log_loss, accuracy_score
import pandas as pd
import numpy as np
from datetime import datetime


def main():
    print("=" * 70)
    print("Stage2モデル再学習 - 選手特徴量追加版")
    print("=" * 70)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. データセット構築
    print("\n【Step 1】学習データセット構築")
    print("  期間: 2024-01-01 〜 2024-06-30（6ヶ月間）")

    builder = DatasetBuilder(db_path='data/boatrace.db')

    df_raw = builder.build_training_dataset(
        start_date='2024-01-01',
        end_date='2024-06-30',
        venue_codes=None  # 全会場
    )

    print(f"  生データ: {len(df_raw):,}件")
    print(f"  レース数: {df_raw['race_id'].nunique():,}レース")

    # 2. 派生特徴量を追加（選手特徴量含む）
    print("\n【Step 2】派生特徴量追加（選手特徴量7個含む）")
    print("  ※ データ量が多いため、時間がかかります...")

    df_features = builder.add_derived_features(df_raw)

    print(f"  特徴量追加後: {len(df_features):,}件")
    print(f"  カラム数: {len(df_features.columns)}個")

    # 選手特徴量の確認
    racer_feature_cols = [
        'recent_avg_rank_3', 'recent_avg_rank_5', 'recent_avg_rank_10',
        'recent_win_rate_3', 'recent_win_rate_5', 'recent_win_rate_10',
        'motor_recent_2rate_diff'
    ]
    present = [col for col in racer_feature_cols if col in df_features.columns]
    print(f"  選手特徴量: {len(present)}/{len(racer_feature_cols)}個 ({', '.join(present[:3])}...)")

    # 3. 特徴量とラベル分離
    print("\n【Step 3】特徴量とラベル分離")

    # 目的変数: is_win（1着フラグ）
    if 'is_win' not in df_features.columns:
        print("  [ERROR] is_win カラムが見つかりません")
        return 1

    # 有効なデータのみフィルタ
    df_features = df_features[df_features['is_win'].notna()].copy()
    print(f"  有効データ: {len(df_features):,}件")

    # 数値特徴量のみ抽出
    numeric_cols = df_features.select_dtypes(include=['int64', 'float64', 'bool']).columns.tolist()

    # 除外するカラム
    exclude_cols = ['race_id', 'is_win', 'is_place_2', 'is_place_3', 'result_rank']
    feature_cols = [col for col in numeric_cols if col not in exclude_cols]

    print(f"  特徴量: {len(feature_cols)}個")
    print(f"  正例（1着）: {df_features['is_win'].sum():,}件 ({df_features['is_win'].mean():.2%})")

    X = df_features[feature_cols]
    y = df_features['is_win']

    # 欠損値を平均値で補完
    X = X.fillna(X.mean())

    # 4. データ分割
    print("\n【Step 4】データ分割")

    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.3, random_state=42, shuffle=True
    )
    X_valid, X_test, y_valid, y_test = train_test_split(
        X_temp, y_temp, test_size=0.5, random_state=42, shuffle=True
    )

    print(f"  訓練: {len(X_train):,}件 ({len(X_train)/len(X):.1%})")
    print(f"  検証: {len(X_valid):,}件 ({len(X_valid)/len(X):.1%})")
    print(f"  テスト: {len(X_test):,}件 ({len(X_test)/len(X):.1%})")

    # 5. モデル学習
    print("\n【Step 5】モデル学習")

    trainer = ModelTrainer(model_dir='models')

    # クラス不均衡を考慮したパラメータ
    scale_pos_weight = (len(y_train) - y_train.sum()) / y_train.sum()

    params = {
        'objective': 'binary:logistic',
        'eval_metric': 'auc',
        'max_depth': 6,
        'learning_rate': 0.05,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'scale_pos_weight': scale_pos_weight,
        'random_state': 42
    }

    print(f"  scale_pos_weight: {scale_pos_weight:.2f}")
    print("  学習中...")

    summary = trainer.train(
        X_train, y_train,
        X_valid, y_valid,
        params=params,
        num_boost_round=1000,
        early_stopping_rounds=50
    )

    print(f"\n  Train AUC: {summary['train_auc']:.4f}")
    print(f"  Valid AUC: {summary['valid_auc']:.4f}")

    # 6. テストデータで評価
    print("\n【Step 6】テストデータで最終評価")

    y_pred_proba = trainer.predict(X_test)

    test_auc = roc_auc_score(y_test, y_pred_proba)
    test_logloss = log_loss(y_test, y_pred_proba)

    # 閾値0.5での精度
    y_pred_binary = (y_pred_proba >= 0.5).astype(int)
    test_accuracy = accuracy_score(y_test, y_pred_binary)

    print(f"  Test AUC: {test_auc:.4f}")
    print(f"  Test Log Loss: {test_logloss:.4f}")
    print(f"  Test Accuracy: {test_accuracy:.4f}")

    # 閾値別の評価
    print(f"\n【閾値別評価】")
    for threshold in [0.1, 0.2, 0.3, 0.4, 0.5]:
        y_pred_t = (y_pred_proba >= threshold).astype(int)
        from sklearn.metrics import precision_score, recall_score, f1_score

        precision = precision_score(y_test, y_pred_t, zero_division=0)
        recall = recall_score(y_test, y_pred_t, zero_division=0)
        f1 = f1_score(y_pred_t, y_test, zero_division=0)

        print(f"  閾値 {threshold:.1f}: Precision={precision:.3f}, Recall={recall:.3f}, F1={f1:.3f}")

    # 7. 選手特徴量の重要度確認
    print(f"\n【選手特徴量の重要度】")

    if hasattr(trainer.model, 'get_score'):
        importance_dict = trainer.model.get_score(importance_type='gain')

        # 選手特徴量のみフィルタ
        racer_importance = {k: v for k, v in importance_dict.items() if k in racer_feature_cols}

        if racer_importance:
            racer_importance_sorted = sorted(racer_importance.items(), key=lambda x: x[1], reverse=True)

            print("  選手特徴量の重要度ランキング:")
            for i, (feature, importance) in enumerate(racer_importance_sorted, 1):
                print(f"    {i}. {feature:<30} {importance:>10.2f}")
        else:
            print("  [WARNING] 選手特徴量の重要度が取得できませんでした")

    # 8. モデル保存
    print(f"\n【Step 7】モデル保存")

    model_path = trainer.save_model('stage2_with_racer_features.json')
    print(f"  保存完了: {model_path}")

    # 9. サマリー
    print("\n" + "=" * 70)
    print("学習完了サマリー")
    print("=" * 70)

    print(f"【データ】")
    print(f"  総データ数: {len(X):,}件")
    print(f"  特徴量数: {len(feature_cols)}個")
    print(f"  選手特徴量: {len(present)}個")
    print(f"  学習期間: 2024-01-01 〜 2024-06-30")

    print(f"\n【性能】")
    print(f"  Train AUC: {summary['train_auc']:.4f}")
    print(f"  Valid AUC: {summary['valid_auc']:.4f}")
    print(f"  Test AUC: {test_auc:.4f}")
    print(f"  Test Log Loss: {test_logloss:.4f}")

    print(f"\n【目標達成状況】")
    # ベースライン（仮定）: AUC 0.70
    baseline_auc = 0.70
    improvement = test_auc - baseline_auc

    if test_auc >= 0.73:  # +0.03改善
        print(f"  [SUCCESS] 目標達成！ Test AUC {test_auc:.4f}")
        print(f"  改善度: {improvement:+.4f} ({improvement/baseline_auc*100:+.2f}%)")
    else:
        print(f"  [INFO] Test AUC {test_auc:.4f}")
        print(f"  ベースライン（仮定）からの改善: {improvement:+.4f}")

    print(f"\n【次のステップ】")
    print(f"  1. バックテスト実施 (python tests/backtest_with_racer_features.py)")
    print(f"  2. 実運用テスト（少額）")
    print(f"  3. 継続的モニタリング")

    print("\n" + "=" * 70)
    print("全ての処理が完了しました")
    print("=" * 70)
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return 0


if __name__ == "__main__":
    exit(main())
