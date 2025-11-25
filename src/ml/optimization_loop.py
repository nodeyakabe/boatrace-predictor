"""
MLモデル最適化ループ

機能:
- 訓練 → テスト → 改善のサイクル
- ハイパーパラメータ最適化
- 特徴量選択
- モデル比較
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import sqlite3
import json
import pickle
from pathlib import Path

from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

from .backtest_engine import BacktestEngine
from .evaluation_metrics import ComprehensiveEvaluator


class OptimizationLoop:
    """MLモデル最適化ループ"""

    def __init__(self, db_path: str = "boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self.backtest_engine = BacktestEngine(db_path)
        self.evaluator = ComprehensiveEvaluator()
        self.results_history = []

    def prepare_features(
        self,
        df: pd.DataFrame,
        feature_columns: Optional[List[str]] = None
    ) -> Tuple[pd.DataFrame, List[str]]:
        """
        特徴量を準備

        Args:
            df: 入力データ
            feature_columns: 使用する特徴量（Noneなら自動選択）

        Returns:
            (特徴量DataFrame, 使用した特徴量名リスト)
        """
        if feature_columns is None:
            # 数値型カラムを自動選択
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

            # 除外すべきカラム
            exclude = ['race_id', 'result_place', 'is_winner', 'race_number']
            feature_columns = [c for c in numeric_cols if c not in exclude]

        # 存在するカラムのみ
        available = [c for c in feature_columns if c in df.columns]

        return df[available], available

    def train_xgboost(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        XGBoostモデルを訓練

        Args:
            X_train: 訓練特徴量
            y_train: 訓練ラベル
            params: ハイパーパラメータ

        Returns:
            訓練済みモデル
        """
        if not HAS_XGBOOST:
            raise ImportError("XGBoostがインストールされていません")

        if params is None:
            params = {
                'objective': 'binary:logistic',
                'eval_metric': 'auc',
                'max_depth': 6,
                'learning_rate': 0.1,
                'n_estimators': 100,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'random_state': 42
            }

        model = xgb.XGBClassifier(**params)
        model.fit(X_train, y_train, verbose=False)

        return model

    def train_lightgbm(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        LightGBMモデルを訓練

        Args:
            X_train: 訓練特徴量
            y_train: 訓練ラベル
            params: ハイパーパラメータ

        Returns:
            訓練済みモデル
        """
        if not HAS_LIGHTGBM:
            raise ImportError("LightGBMがインストールされていません")

        if params is None:
            params = {
                'objective': 'binary',
                'metric': 'auc',
                'max_depth': 6,
                'learning_rate': 0.1,
                'n_estimators': 100,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'random_state': 42,
                'verbose': -1
            }

        model = lgb.LGBMClassifier(**params)
        model.fit(X_train, y_train)

        return model

    def evaluate_model(
        self,
        model,
        X_test: pd.DataFrame,
        y_test: pd.Series
    ) -> Dict[str, float]:
        """
        モデルを評価

        Args:
            model: 訓練済みモデル
            X_test: テスト特徴量
            y_test: テストラベル

        Returns:
            評価指標
        """
        y_pred_prob = model.predict_proba(X_test)[:, 1]

        metrics = {
            'auc': roc_auc_score(y_test, y_pred_prob),
            'brier_score': brier_score_loss(y_test, y_pred_prob),
            'log_loss': log_loss(y_test, y_pred_prob)
        }

        return metrics

    def optimize_hyperparameters(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        model_type: str = 'xgboost',
        n_trials: int = 20
    ) -> Dict[str, Any]:
        """
        ハイパーパラメータを最適化

        Args:
            X_train: 訓練特徴量
            y_train: 訓練ラベル
            model_type: 'xgboost' or 'lightgbm'
            n_trials: 試行回数

        Returns:
            最適パラメータ
        """
        # 時系列交差検証
        tscv = TimeSeriesSplit(n_splits=3)

        best_score = 0
        best_params = None

        # パラメータグリッド
        param_grid = {
            'max_depth': [4, 6, 8],
            'learning_rate': [0.05, 0.1, 0.2],
            'n_estimators': [50, 100, 200],
            'subsample': [0.7, 0.8, 0.9]
        }

        # ランダムサーチ
        for trial in range(n_trials):
            params = {
                'max_depth': np.random.choice(param_grid['max_depth']),
                'learning_rate': np.random.choice(param_grid['learning_rate']),
                'n_estimators': np.random.choice(param_grid['n_estimators']),
                'subsample': np.random.choice(param_grid['subsample']),
                'colsample_bytree': 0.8,
                'random_state': 42
            }

            if model_type == 'xgboost':
                params['objective'] = 'binary:logistic'
                params['eval_metric'] = 'auc'
            else:
                params['objective'] = 'binary'
                params['metric'] = 'auc'
                params['verbose'] = -1

            # 交差検証スコア
            scores = []
            for train_idx, val_idx in tscv.split(X_train):
                X_tr = X_train.iloc[train_idx]
                y_tr = y_train.iloc[train_idx]
                X_val = X_train.iloc[val_idx]
                y_val = y_train.iloc[val_idx]

                try:
                    if model_type == 'xgboost':
                        model = xgb.XGBClassifier(**params)
                    else:
                        model = lgb.LGBMClassifier(**params)

                    model.fit(X_tr, y_tr, verbose=False if model_type == 'xgboost' else None)
                    y_pred = model.predict_proba(X_val)[:, 1]
                    score = roc_auc_score(y_val, y_pred)
                    scores.append(score)
                except Exception:
                    continue

            if scores:
                avg_score = np.mean(scores)
                if avg_score > best_score:
                    best_score = avg_score
                    best_params = params

        return best_params or {}

    def run_optimization_cycle(
        self,
        model_type: str = 'xgboost',
        optimize_params: bool = True,
        train_ratio: float = 0.8
    ) -> Dict[str, Any]:
        """
        最適化サイクルを実行

        Args:
            model_type: 'xgboost' or 'lightgbm'
            optimize_params: パラメータ最適化を行うか
            train_ratio: 訓練データ割合

        Returns:
            最適化結果
        """
        print("=" * 60)
        print(f"ML最適化サイクル開始 ({model_type})")
        print("=" * 60)

        # データ準備
        print("\n1. データ準備...")
        _, split_date, _ = self.backtest_engine.get_time_split_dates(train_ratio)
        train_df, test_df = self.backtest_engine.load_backtest_data(split_date)

        # ラベル作成
        train_df['is_winner'] = (train_df['result_place'] == 1).astype(int)
        test_df['is_winner'] = (test_df['result_place'] == 1).astype(int)

        # 特徴量準備
        X_train, feature_names = self.prepare_features(train_df)
        y_train = train_df['is_winner']

        X_test, _ = self.prepare_features(test_df, feature_names)
        y_test = test_df['is_winner']

        # NaN除去
        train_mask = ~X_train.isna().any(axis=1)
        test_mask = ~X_test.isna().any(axis=1)

        X_train = X_train[train_mask]
        y_train = y_train[train_mask]
        X_test = X_test[test_mask]
        y_test = y_test[test_mask]

        print(f"  訓練サンプル: {len(X_train):,}")
        print(f"  テストサンプル: {len(X_test):,}")
        print(f"  特徴量数: {len(feature_names)}")

        # ハイパーパラメータ最適化
        if optimize_params:
            print("\n2. ハイパーパラメータ最適化...")
            best_params = self.optimize_hyperparameters(
                X_train, y_train, model_type, n_trials=20
            )
            print(f"  最適パラメータ: {best_params}")
        else:
            best_params = None

        # モデル訓練
        print("\n3. モデル訓練...")
        if model_type == 'xgboost':
            model = self.train_xgboost(X_train, y_train, best_params)
        else:
            model = self.train_lightgbm(X_train, y_train, best_params)

        # 評価
        print("\n4. モデル評価...")
        metrics = self.evaluate_model(model, X_test, y_test)

        print(f"  AUC: {metrics['auc']:.4f}")
        print(f"  Brier Score: {metrics['brier_score']:.4f}")
        print(f"  Log Loss: {metrics['log_loss']:.4f}")

        # 特徴量重要度
        if hasattr(model, 'feature_importances_'):
            importance = dict(zip(feature_names, model.feature_importances_))
            sorted_importance = sorted(
                importance.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]

            print("\n5. 特徴量重要度 TOP10:")
            for i, (name, value) in enumerate(sorted_importance, 1):
                print(f"  {i:2d}. {name}: {value:.4f}")
        else:
            sorted_importance = []

        # 結果保存
        result = {
            'timestamp': datetime.now().isoformat(),
            'model_type': model_type,
            'train_samples': len(X_train),
            'test_samples': len(X_test),
            'features': feature_names,
            'params': best_params,
            'metrics': metrics,
            'feature_importance': dict(sorted_importance),
            'split_date': split_date
        }

        self.results_history.append(result)

        print("\n" + "=" * 60)
        print("最適化サイクル完了")
        print("=" * 60)

        return result

    def compare_models(self) -> str:
        """
        履歴からモデルを比較

        Returns:
            比較レポート
        """
        if not self.results_history:
            return "比較可能な結果がありません"

        lines = [
            "=" * 60,
            "モデル比較レポート",
            "=" * 60,
            ""
        ]

        # ヘッダー
        lines.append(f"{'モデル':15} {'AUC':8} {'Brier':8} {'LogLoss':8} {'日時'}")
        lines.append("-" * 60)

        for result in self.results_history:
            model = result.get('model_type', 'unknown')
            metrics = result.get('metrics', {})
            timestamp = result.get('timestamp', '')[:16]

            lines.append(
                f"{model:15} "
                f"{metrics.get('auc', 0):7.4f} "
                f"{metrics.get('brier_score', 0):7.4f} "
                f"{metrics.get('log_loss', 0):7.4f} "
                f"{timestamp}"
            )

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def save_best_model(
        self,
        model,
        output_path: str = "best_model.pkl"
    ):
        """
        最良モデルを保存

        Args:
            model: モデルオブジェクト
            output_path: 出力パス
        """
        with open(output_path, 'wb') as f:
            pickle.dump(model, f)
        print(f"モデルを保存: {output_path}")

    def save_results(self, output_path: str = "optimization_results.json"):
        """
        結果履歴を保存

        Args:
            output_path: 出力パス
        """
        def convert(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        results_serializable = json.loads(
            json.dumps(self.results_history, default=convert)
        )

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results_serializable, f, ensure_ascii=False, indent=2)

        print(f"結果を保存: {output_path}")


def run_full_optimization(
    db_path: str = "boatrace.db",
    models: List[str] = ['xgboost', 'lightgbm']
) -> Dict[str, Any]:
    """
    フル最適化を実行

    Args:
        db_path: データベースパス
        models: 評価するモデルタイプ

    Returns:
        最良モデルの結果
    """
    optimizer = OptimizationLoop(db_path)

    best_result = None
    best_auc = 0

    for model_type in models:
        try:
            result = optimizer.run_optimization_cycle(
                model_type=model_type,
                optimize_params=True
            )

            auc = result['metrics']['auc']
            if auc > best_auc:
                best_auc = auc
                best_result = result

        except Exception as e:
            print(f"{model_type}でエラー: {e}")

    # 比較レポート
    print("\n")
    print(optimizer.compare_models())

    # 結果保存
    optimizer.save_results()

    return best_result


if __name__ == "__main__":
    # テスト
    print("ML最適化ループ テスト")
    print("-" * 40)

    optimizer = OptimizationLoop()

    # XGBoostで最適化
    if HAS_XGBOOST:
        try:
            result = optimizer.run_optimization_cycle(
                model_type='xgboost',
                optimize_params=False  # テスト用に高速化
            )
        except Exception as e:
            print(f"エラー: {e}")
    else:
        print("XGBoostが利用できません")

    # LightGBMで最適化
    if HAS_LIGHTGBM:
        try:
            result = optimizer.run_optimization_cycle(
                model_type='lightgbm',
                optimize_params=False
            )
        except Exception as e:
            print(f"エラー: {e}")
    else:
        print("LightGBMが利用できません")

    # 比較
    print(optimizer.compare_models())
