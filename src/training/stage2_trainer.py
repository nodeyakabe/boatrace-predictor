"""
Stage2予測モデル学習・評価モジュール

Stage1の出力（1-2-3着確率）+ 追加特徴量を使って最終的な着順予測を行う
LightGBM/XGBoostによる学習パイプライン、CV、ハイパーパラメータチューニング、評価機能を提供
"""

import lightgbm as lgb
import xgboost as xgb
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union
import json
import joblib
from pathlib import Path
from datetime import datetime
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    log_loss,
    roc_auc_score
)
import optuna
from optuna.samplers import TPESampler


class Stage2Trainer:
    """Stage2モデル学習・評価クラス"""

    def __init__(self, model_dir: str = "models/stage2"):
        """
        初期化

        Args:
            model_dir: モデル保存ディレクトリ
        """
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.models = {}  # {position: model} (position: 1-6)
        self.feature_names = None
        self.training_history = {}
        self.cv_results = {}
        self.best_params = {}

    # ========================================
    # データ準備
    # ========================================

    def prepare_training_data(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        test_size: float = 0.2,
        random_state: int = 42
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
        """
        訓練データと検証データに分割

        Args:
            X: 特徴量データフレーム
            y: 目的変数（着順: 1-6）
            test_size: テストデータの割合
            random_state: 乱数シード

        Returns:
            X_train, X_test, y_train, y_test
        """
        from sklearn.model_selection import train_test_split

        return train_test_split(
            X, y,
            test_size=test_size,
            random_state=random_state,
            stratify=y  # 着順の分布を保持
        )

    # ========================================
    # モデル学習（基本）
    # ========================================

    def train_lightgbm(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_valid: Optional[pd.DataFrame] = None,
        y_valid: Optional[pd.Series] = None,
        target_position: int = 1,
        params: Optional[Dict] = None,
        num_boost_round: int = 1000,
        early_stopping_rounds: int = 50,
        verbose: int = 100
    ) -> Dict:
        """
        LightGBMでStage2モデルを学習（特定の着順を予測）

        Args:
            X_train: 訓練データ特徴量
            y_train: 訓練データ目的変数（着順: 1-6）
            X_valid: 検証データ特徴量
            y_valid: 検証データ目的変数
            target_position: 予測対象の着順（1-6）
            params: LightGBM パラメータ
            num_boost_round: ブースティング回数
            early_stopping_rounds: Early stopping ラウンド数
            verbose: ログ出力間隔

        Returns:
            学習結果サマリー
        """
        self.feature_names = list(X_train.columns)

        # 二値分類タスクに変換（target_position着になるか否か）
        y_train_binary = (y_train == target_position).astype(int)

        if y_valid is not None:
            y_valid_binary = (y_valid == target_position).astype(int)

        # デフォルトパラメータ
        if params is None:
            params = {
                'objective': 'binary',
                'metric': 'auc',
                'boosting_type': 'gbdt',
                'num_leaves': 31,
                'learning_rate': 0.05,
                'feature_fraction': 0.8,
                'bagging_fraction': 0.8,
                'bagging_freq': 5,
                'verbose': -1,
                'seed': 42
            }

        # データセット作成
        train_data = lgb.Dataset(X_train, label=y_train_binary, feature_name=self.feature_names)

        valid_sets = [train_data]
        valid_names = ['train']

        if X_valid is not None and y_valid is not None:
            valid_data = lgb.Dataset(X_valid, label=y_valid_binary, feature_name=self.feature_names, reference=train_data)
            valid_sets.append(valid_data)
            valid_names.append('valid')

        # 学習履歴を保存するコールバック
        evals_result = {}

        # 学習
        model = lgb.train(
            params,
            train_data,
            num_boost_round=num_boost_round,
            valid_sets=valid_sets,
            valid_names=valid_names,
            callbacks=[
                lgb.log_evaluation(verbose),
                lgb.early_stopping(early_stopping_rounds) if X_valid is not None else None,
                lgb.record_evaluation(evals_result)
            ]
        )

        # モデルを保存
        self.models[target_position] = model
        self.training_history[target_position] = evals_result

        # 評価指標計算
        train_pred = model.predict(X_train)
        train_auc = roc_auc_score(y_train_binary, train_pred)

        result = {
            'target_position': target_position,
            'train_auc': train_auc,
            'num_boost_round': model.num_trees(),
            'feature_importance': dict(zip(self.feature_names, model.feature_importance()))
        }

        if X_valid is not None:
            valid_pred = model.predict(X_valid)
            valid_auc = roc_auc_score(y_valid_binary, valid_pred)
            result['valid_auc'] = valid_auc

        return result

    def train_all_positions(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_valid: Optional[pd.DataFrame] = None,
        y_valid: Optional[pd.Series] = None,
        params: Optional[Dict] = None,
        num_boost_round: int = 1000,
        early_stopping_rounds: int = 50
    ) -> Dict:
        """
        全着順（1-6着）のモデルを学習

        Args:
            X_train: 訓練データ特徴量
            y_train: 訓練データ目的変数
            X_valid: 検証データ特徴量
            y_valid: 検証データ目的変数
            params: LightGBM パラメータ
            num_boost_round: ブースティング回数
            early_stopping_rounds: Early stopping ラウンド数

        Returns:
            全着順の学習結果
        """
        results = {}

        print("="*70)
        print("Stage2モデル学習開始: 全着順（1-6着）")
        print("="*70)

        for position in range(1, 7):
            print(f"\n[{position}着モデル学習中...]")

            result = self.train_lightgbm(
                X_train, y_train,
                X_valid, y_valid,
                target_position=position,
                params=params,
                num_boost_round=num_boost_round,
                early_stopping_rounds=early_stopping_rounds,
                verbose=0
            )

            results[position] = result

            print(f"  Train AUC: {result['train_auc']:.4f}")
            if 'valid_auc' in result:
                print(f"  Valid AUC: {result['valid_auc']:.4f}")

        print("\n"+"="*70)
        print("全着順モデル学習完了")
        print("="*70)

        return results

    # ========================================
    # クロスバリデーション
    # ========================================

    def cross_validate(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        n_splits: int = 5,
        target_position: int = 1,
        params: Optional[Dict] = None,
        num_boost_round: int = 1000,
        early_stopping_rounds: int = 50
    ) -> Dict:
        """
        クロスバリデーションでモデル性能を評価

        Args:
            X: 特徴量データフレーム
            y: 目的変数
            n_splits: Fold数
            target_position: 予測対象の着順
            params: LightGBM パラメータ
            num_boost_round: ブースティング回数
            early_stopping_rounds: Early stopping ラウンド数

        Returns:
            CVスコアとfold別結果
        """
        kf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

        y_binary = (y == target_position).astype(int)

        cv_scores = []
        fold_results = []

        print(f"\n{'='*70}")
        print(f"{n_splits}-Fold Cross Validation: {target_position}着予測")
        print(f"{'='*70}")

        for fold_idx, (train_idx, valid_idx) in enumerate(kf.split(X, y_binary), 1):
            print(f"\n[Fold {fold_idx}/{n_splits}]")

            X_train_fold = X.iloc[train_idx]
            y_train_fold = y.iloc[train_idx]
            X_valid_fold = X.iloc[valid_idx]
            y_valid_fold = y.iloc[valid_idx]

            result = self.train_lightgbm(
                X_train_fold, y_train_fold,
                X_valid_fold, y_valid_fold,
                target_position=target_position,
                params=params,
                num_boost_round=num_boost_round,
                early_stopping_rounds=early_stopping_rounds,
                verbose=0
            )

            cv_scores.append(result['valid_auc'])
            fold_results.append(result)

            print(f"  Valid AUC: {result['valid_auc']:.4f}")

        mean_score = np.mean(cv_scores)
        std_score = np.std(cv_scores)

        print(f"\n{'='*70}")
        print(f"CV結果: Mean AUC = {mean_score:.4f} (+/- {std_score:.4f})")
        print(f"{'='*70}")

        cv_result = {
            'target_position': target_position,
            'mean_auc': mean_score,
            'std_auc': std_score,
            'fold_scores': cv_scores,
            'fold_results': fold_results
        }

        self.cv_results[target_position] = cv_result

        return cv_result

    # ========================================
    # ハイパーパラメータチューニング
    # ========================================

    def optimize_hyperparameters(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_valid: pd.DataFrame,
        y_valid: pd.Series,
        target_position: int = 1,
        n_trials: int = 100,
        timeout: Optional[int] = None
    ) -> Dict:
        """
        Optunaを使ったハイパーパラメータチューニング

        Args:
            X_train: 訓練データ特徴量
            y_train: 訓練データ目的変数
            X_valid: 検証データ特徴量
            y_valid: 検証データ目的変数
            target_position: 予測対象の着順
            n_trials: 試行回数
            timeout: タイムアウト（秒）

        Returns:
            最適パラメータと結果
        """
        y_train_binary = (y_train == target_position).astype(int)
        y_valid_binary = (y_valid == target_position).astype(int)

        train_data = lgb.Dataset(X_train, label=y_train_binary)
        valid_data = lgb.Dataset(X_valid, label=y_valid_binary, reference=train_data)

        def objective(trial):
            params = {
                'objective': 'binary',
                'metric': 'auc',
                'boosting_type': 'gbdt',
                'num_leaves': trial.suggest_int('num_leaves', 20, 100),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
                'feature_fraction': trial.suggest_float('feature_fraction', 0.5, 1.0),
                'bagging_fraction': trial.suggest_float('bagging_fraction', 0.5, 1.0),
                'bagging_freq': trial.suggest_int('bagging_freq', 1, 10),
                'min_child_samples': trial.suggest_int('min_child_samples', 5, 100),
                'verbose': -1,
                'seed': 42
            }

            model = lgb.train(
                params,
                train_data,
                num_boost_round=1000,
                valid_sets=[valid_data],
                callbacks=[
                    lgb.early_stopping(50),
                    lgb.log_evaluation(0)
                ]
            )

            valid_pred = model.predict(X_valid)
            auc = roc_auc_score(y_valid_binary, valid_pred)

            return auc

        print(f"\n{'='*70}")
        print(f"ハイパーパラメータ最適化開始: {target_position}着予測")
        print(f"Trials: {n_trials}")
        print(f"{'='*70}\n")

        study = optuna.create_study(
            direction='maximize',
            sampler=TPESampler(seed=42)
        )

        study.optimize(objective, n_trials=n_trials, timeout=timeout, show_progress_bar=True)

        best_params = study.best_params
        best_score = study.best_value

        print(f"\n{'='*70}")
        print(f"最適化完了")
        print(f"Best AUC: {best_score:.4f}")
        print(f"Best Params: {json.dumps(best_params, indent=2)}")
        print(f"{'='*70}")

        self.best_params[target_position] = best_params

        return {
            'target_position': target_position,
            'best_params': best_params,
            'best_score': best_score,
            'study': study
        }

    # ========================================
    # 予測
    # ========================================

    def predict_probabilities(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        全着順の予測確率を計算

        Args:
            X: 特徴量データフレーム

        Returns:
            各着順の確率を含むDataFrame（カラム: prob_1, prob_2, ..., prob_6）
        """
        if not self.models:
            raise ValueError("モデルが学習されていません。先にtrain_all_positions()を実行してください。")

        probs = {}
        for position in range(1, 7):
            if position in self.models:
                probs[f'prob_{position}'] = self.models[position].predict(X)
            else:
                probs[f'prob_{position}'] = np.zeros(len(X))

        prob_df = pd.DataFrame(probs)

        # 確率の正規化（合計が1になるように）
        prob_df = prob_df.div(prob_df.sum(axis=1), axis=0)

        return prob_df

    def predict_rank(self, X: pd.DataFrame) -> np.ndarray:
        """
        最も確率の高い着順を予測

        Args:
            X: 特徴量データフレーム

        Returns:
            予測着順（1-6）
        """
        prob_df = self.predict_probabilities(X)
        return prob_df.idxmax(axis=1).str.replace('prob_', '').astype(int).values

    # ========================================
    # モデル評価
    # ========================================

    def evaluate(
        self,
        X_test: pd.DataFrame,
        y_test: pd.Series,
        odds_data: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        テストデータでモデルを評価

        Args:
            X_test: テストデータ特徴量
            y_test: テストデータ目的変数（着順）
            odds_data: オッズデータ（回収率計算用）

        Returns:
            評価結果（的中率、回収率など）
        """
        # 予測
        prob_df = self.predict_probabilities(X_test)
        pred_ranks = self.predict_rank(X_test)

        # 的中率計算
        accuracy_1st = accuracy_score(y_test == 1, pred_ranks == 1)
        accuracy_2nd = accuracy_score(y_test == 2, pred_ranks == 2)
        accuracy_3rd = accuracy_score(y_test == 3, pred_ranks == 3)

        # 全体の着順的中率
        overall_accuracy = accuracy_score(y_test, pred_ranks)

        result = {
            '1着的中率': accuracy_1st,
            '2着的中率': accuracy_2nd,
            '3着的中率': accuracy_3rd,
            '全体的中率': overall_accuracy,
            'AUC_scores': {}
        }

        # 各着順のAUCスコア
        for position in range(1, 7):
            if position in self.models:
                y_binary = (y_test == position).astype(int)
                auc = roc_auc_score(y_binary, prob_df[f'prob_{position}'])
                result['AUC_scores'][f'{position}着'] = auc

        # 回収率計算（オッズデータがある場合）
        if odds_data is not None:
            result['回収率'] = self._calculate_roi(pred_ranks, y_test, odds_data)

        return result

    def _calculate_roi(
        self,
        pred_ranks: np.ndarray,
        true_ranks: pd.Series,
        odds_data: pd.DataFrame
    ) -> float:
        """
        回収率を計算

        Args:
            pred_ranks: 予測着順
            true_ranks: 実際の着順
            odds_data: オッズデータ（'odds_win'カラムが必要）

        Returns:
            回収率（%）
        """
        # 1着を予測したレースのみを対象
        pred_win_mask = (pred_ranks == 1)

        if pred_win_mask.sum() == 0:
            return 0.0

        # 実際に1着だったレース
        correct_win_mask = (true_ranks == 1).values

        # 的中したレースのオッズ
        hit_odds = odds_data.loc[pred_win_mask & correct_win_mask, 'odds_win']

        # 投資額（予測した全レース）
        total_bet = pred_win_mask.sum() * 100  # 100円/レース

        # 払戻金
        total_return = hit_odds.sum() * 100

        # 回収率
        roi = (total_return / total_bet) * 100 if total_bet > 0 else 0.0

        return roi

    # ========================================
    # モデル保存・読み込み
    # ========================================

    def save_models(self, model_name: str = "stage2_model"):
        """
        全着順のモデルを保存

        Args:
            model_name: モデル名（拡張子なし）
        """
        if not self.models:
            raise ValueError("保存するモデルがありません。")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_dir = self.model_dir / f"{model_name}_{timestamp}"
        save_dir.mkdir(parents=True, exist_ok=True)

        # 各着順のモデルを保存
        for position, model in self.models.items():
            model_path = save_dir / f"model_position_{position}.txt"
            model.save_model(str(model_path))

        # メタデータ保存
        metadata = {
            'feature_names': self.feature_names,
            'timestamp': timestamp,
            'positions': list(self.models.keys())
        }

        metadata_path = save_dir / "metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        print(f"\n[OK] モデル保存完了: {save_dir}")

        return str(save_dir)

    def load_models(self, model_path: str):
        """
        保存されたモデルを読み込み

        Args:
            model_path: モデルディレクトリパス
        """
        model_dir = Path(model_path)

        if not model_dir.exists():
            raise FileNotFoundError(f"モデルディレクトリが見つかりません: {model_dir}")

        # メタデータ読み込み
        metadata_path = model_dir / "metadata.json"
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        self.feature_names = metadata['feature_names']

        # 各着順のモデルを読み込み
        self.models = {}
        for position in metadata['positions']:
            model_path = model_dir / f"model_position_{position}.txt"
            self.models[position] = lgb.Booster(model_file=str(model_path))

        print(f"[OK] モデル読み込み完了: {model_dir}")
        print(f"  読み込んだ着順モデル: {list(self.models.keys())}")


if __name__ == "__main__":
    # テスト実行
    print("="*70)
    print("Stage2Trainer テスト")
    print("="*70)

    # ダミーデータ作成
    np.random.seed(42)
    n_samples = 1000
    n_features = 20

    X = pd.DataFrame(
        np.random.randn(n_samples, n_features),
        columns=[f'feature_{i}' for i in range(n_features)]
    )
    y = pd.Series(np.random.choice([1, 2, 3, 4, 5, 6], n_samples))

    # トレーナー初期化
    trainer = Stage2Trainer()

    # データ分割
    X_train, X_test, y_train, y_test = trainer.prepare_training_data(X, y)

    print(f"\nデータ分割:")
    print(f"  訓練データ: {len(X_train)}件")
    print(f"  テストデータ: {len(X_test)}件")

    # モデル学習
    results = trainer.train_all_positions(X_train, y_train, X_test, y_test, num_boost_round=100)

    # 評価
    print("\n" + "="*70)
    print("モデル評価")
    print("="*70)
    eval_result = trainer.evaluate(X_test, y_test)

    for key, value in eval_result.items():
        if key == 'AUC_scores':
            print(f"\n{key}:")
            for pos, score in value.items():
                print(f"  {pos}: {score:.4f}")
        else:
            print(f"{key}: {value:.4f}")

    print("\n" + "="*70)
    print("テスト完了")
    print("="*70)
