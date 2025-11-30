"""
条件付き着順モデルの学習スクリプト
Phase 2: Stage1/2/3モデルの学習と評価
"""
import os
import sys
import sqlite3
import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score, log_loss, accuracy_score
from datetime import datetime, timedelta
import json
import joblib
from typing import Dict, List, Tuple, Optional

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.features.feature_transforms import FeatureTransformer, create_training_dataset_with_relative_features


class ConditionalModelTrainer:
    """
    条件付き着順モデルのトレーナー

    Stage1: 1着予測（6艇から1艇を選択）
    Stage2: 2着予測（1着確定後、残り5艇から1艇を選択）
    Stage3: 3着予測（1-2着確定後、残り4艇から1艇を選択）
    """

    def __init__(self, db_path: str, model_dir: str = 'models'):
        self.db_path = db_path
        self.model_dir = model_dir
        self.feature_transformer = FeatureTransformer()

        self.models = {
            'stage1': None,
            'stage2': None,
            'stage3': None,
        }

        self.feature_names = {
            'stage1': None,
            'stage2': None,
            'stage3': None,
        }

        self.metrics = {}

    def load_training_data(self, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """学習データを読み込み"""
        print("=== 学習データ読み込み ===")

        with sqlite3.connect(self.db_path) as conn:
            df = create_training_dataset_with_relative_features(
                conn, start_date=start_date, end_date=end_date
            )

        print(f"読み込み件数: {len(df):,}件")
        print(f"レース数: {df['race_id'].nunique():,}レース")

        return df

    def prepare_stage1_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """Stage1（1着予測）用のデータを準備"""
        # 6艇揃っているレースのみを使用
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df_valid = df[df['race_id'].isin(valid_races)].copy()

        if len(df_valid) == 0:
            return pd.DataFrame(), np.array([])

        # 特徴量カラム（非数値・ターゲット除外）
        exclude_cols = ['rank', 'race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number']
        feature_cols = [c for c in df_valid.columns if c not in exclude_cols]

        X = df_valid[feature_cols].select_dtypes(include=[np.number])
        y = (df_valid['rank'] == 1).astype(int).values

        return X, y

    def prepare_stage2_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """Stage2（2着予測）用のデータを準備"""
        # 6艇揃っているレースのみ
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df_valid = df[df['race_id'].isin(valid_races)].copy()

        if len(df_valid) == 0:
            return pd.DataFrame(), np.array([])

        # 1着艇の情報を取得
        first_place = df_valid[df_valid['rank'] == 1][['race_id', 'pit_number']].copy()
        first_place.columns = ['race_id', 'first_pit']

        # 1着艇の特徴量を取得
        feature_cols = [c for c in df_valid.columns
                       if c not in ['rank', 'race_id', 'pit_number', 'race_date',
                                   'venue_code', 'racer_number', 'race_number']]
        first_features = df_valid[df_valid['rank'] == 1][['race_id'] + feature_cols].copy()
        first_features.columns = ['race_id'] + [f'winner_{c}' for c in feature_cols]

        # 1着艇を除外した候補データ
        df_with_first = df_valid.merge(first_place, on='race_id')
        remaining = df_with_first[df_with_first['pit_number'] != df_with_first['first_pit']].copy()
        remaining = remaining.drop('first_pit', axis=1)

        # 1着艇の特徴量をマージ
        remaining = remaining.merge(first_features, on='race_id')

        # 差分特徴量を追加
        for col in feature_cols:
            if col in remaining.columns and f'winner_{col}' in remaining.columns:
                if remaining[col].dtype in [np.float64, np.int64, float, int]:
                    remaining[f'diff_{col}'] = remaining[col] - remaining[f'winner_{col}']

        # ラベル
        y = (remaining['rank'] == 2).astype(int).values

        # 特徴量
        exclude_cols = ['rank', 'race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number']
        X = remaining.drop([c for c in exclude_cols if c in remaining.columns], axis=1)
        X = X.select_dtypes(include=[np.number])

        return X, y

    def prepare_stage3_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """Stage3（3着予測）用のデータを準備"""
        # 6艇揃っているレースのみ
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df_valid = df[df['race_id'].isin(valid_races)].copy()

        if len(df_valid) == 0:
            return pd.DataFrame(), np.array([])

        # 1着・2着艇の情報
        first_place = df_valid[df_valid['rank'] == 1][['race_id', 'pit_number']].copy()
        first_place.columns = ['race_id', 'first_pit']

        second_place = df_valid[df_valid['rank'] == 2][['race_id', 'pit_number']].copy()
        second_place.columns = ['race_id', 'second_pit']

        # 特徴量カラム
        feature_cols = [c for c in df_valid.columns
                       if c not in ['rank', 'race_id', 'pit_number', 'race_date',
                                   'venue_code', 'racer_number', 'race_number']]

        # 1着・2着艇の特徴量
        first_features = df_valid[df_valid['rank'] == 1][['race_id'] + feature_cols].copy()
        first_features.columns = ['race_id'] + [f'winner_{c}' for c in feature_cols]

        second_features = df_valid[df_valid['rank'] == 2][['race_id'] + feature_cols].copy()
        second_features.columns = ['race_id'] + [f'second_{c}' for c in feature_cols]

        # 1着・2着艇を除外
        df_with_places = df_valid.merge(first_place, on='race_id').merge(second_place, on='race_id')
        remaining = df_with_places[
            (df_with_places['pit_number'] != df_with_places['first_pit']) &
            (df_with_places['pit_number'] != df_with_places['second_pit'])
        ].copy()
        remaining = remaining.drop(['first_pit', 'second_pit'], axis=1)

        # 1着・2着艇の特徴量をマージ
        remaining = remaining.merge(first_features, on='race_id')
        remaining = remaining.merge(second_features, on='race_id')

        # 差分特徴量を追加
        for col in feature_cols:
            if col in remaining.columns:
                if remaining[col].dtype in [np.float64, np.int64, float, int]:
                    if f'winner_{col}' in remaining.columns:
                        remaining[f'diff_winner_{col}'] = remaining[col] - remaining[f'winner_{col}']
                    if f'second_{col}' in remaining.columns:
                        remaining[f'diff_second_{col}'] = remaining[col] - remaining[f'second_{col}']

        # ラベル
        y = (remaining['rank'] == 3).astype(int).values

        # 特徴量
        exclude_cols = ['rank', 'race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number']
        X = remaining.drop([c for c in exclude_cols if c in remaining.columns], axis=1)
        X = X.select_dtypes(include=[np.number])

        return X, y

    def train_xgboost(self, X: pd.DataFrame, y: np.ndarray,
                      stage_name: str, params: Dict = None) -> Tuple[xgb.XGBClassifier, Dict]:
        """XGBoostモデルを学習"""
        if params is None:
            params = {
                'objective': 'binary:logistic',
                'eval_metric': 'auc',
                'max_depth': 6,
                'learning_rate': 0.05,
                'n_estimators': 500,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'min_child_weight': 3,
                'gamma': 0.1,
                'random_state': 42,
                'n_jobs': -1,
                'early_stopping_rounds': 50,
            }

        print(f"\n=== {stage_name}モデル学習 (XGBoost) ===")
        print(f"データサイズ: {len(X):,}件, 特徴量数: {len(X.columns)}")

        # TimeSeriesSplitでCV
        tscv = TimeSeriesSplit(n_splits=5)
        cv_scores = []

        for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            model = xgb.XGBClassifier(**params)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False
            )

            val_pred = model.predict_proba(X_val)[:, 1]
            auc = roc_auc_score(y_val, val_pred)
            cv_scores.append(auc)
            print(f"Fold {fold+1}: AUC = {auc:.4f}")

        mean_auc = np.mean(cv_scores)
        print(f"CV平均AUC: {mean_auc:.4f} (+/- {np.std(cv_scores):.4f})")

        # 全データで最終モデルを学習
        final_model = xgb.XGBClassifier(**{k: v for k, v in params.items()
                                           if k != 'early_stopping_rounds'})
        final_model.fit(X, y, verbose=False)

        metrics = {
            'cv_auc_mean': mean_auc,
            'cv_auc_std': np.std(cv_scores),
            'cv_scores': cv_scores,
            'n_features': len(X.columns),
            'n_samples': len(X),
        }

        return final_model, metrics

    def train_lightgbm(self, X: pd.DataFrame, y: np.ndarray,
                       stage_name: str, params: Dict = None) -> Tuple[lgb.LGBMClassifier, Dict]:
        """LightGBMモデルを学習"""
        if params is None:
            params = {
                'objective': 'binary',
                'metric': 'auc',
                'max_depth': 6,
                'learning_rate': 0.05,
                'n_estimators': 500,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'min_child_samples': 20,
                'reg_alpha': 0.1,
                'reg_lambda': 0.1,
                'random_state': 42,
                'n_jobs': -1,
                'verbose': -1,
            }

        print(f"\n=== {stage_name}モデル学習 (LightGBM) ===")
        print(f"データサイズ: {len(X):,}件, 特徴量数: {len(X.columns)}")

        # TimeSeriesSplitでCV
        tscv = TimeSeriesSplit(n_splits=5)
        cv_scores = []

        for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            model = lgb.LGBMClassifier(**params)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
            )

            val_pred = model.predict_proba(X_val)[:, 1]
            auc = roc_auc_score(y_val, val_pred)
            cv_scores.append(auc)
            print(f"Fold {fold+1}: AUC = {auc:.4f}")

        mean_auc = np.mean(cv_scores)
        print(f"CV平均AUC: {mean_auc:.4f} (+/- {np.std(cv_scores):.4f})")

        # 全データで最終モデルを学習
        final_model = lgb.LGBMClassifier(**params)
        final_model.fit(X, y)

        metrics = {
            'cv_auc_mean': mean_auc,
            'cv_auc_std': np.std(cv_scores),
            'cv_scores': cv_scores,
            'n_features': len(X.columns),
            'n_samples': len(X),
        }

        return final_model, metrics

    def train_all(self, df: pd.DataFrame, model_type: str = 'xgboost') -> Dict:
        """全Stageのモデルを学習"""
        print("\n" + "="*60)
        print("条件付き着順モデル学習開始")
        print("="*60)

        train_func = self.train_xgboost if model_type == 'xgboost' else self.train_lightgbm

        # Stage1: 1着予測
        X1, y1 = self.prepare_stage1_data(df)
        if len(X1) > 0:
            self.models['stage1'], self.metrics['stage1'] = train_func(X1, y1, 'Stage1(1着予測)')
            self.feature_names['stage1'] = list(X1.columns)

        # Stage2: 2着予測
        X2, y2 = self.prepare_stage2_data(df)
        if len(X2) > 0:
            self.models['stage2'], self.metrics['stage2'] = train_func(X2, y2, 'Stage2(2着予測)')
            self.feature_names['stage2'] = list(X2.columns)

        # Stage3: 3着予測
        X3, y3 = self.prepare_stage3_data(df)
        if len(X3) > 0:
            self.models['stage3'], self.metrics['stage3'] = train_func(X3, y3, 'Stage3(3着予測)')
            self.feature_names['stage3'] = list(X3.columns)

        print("\n" + "="*60)
        print("学習完了サマリ")
        print("="*60)
        for stage, metrics in self.metrics.items():
            print(f"{stage}: AUC = {metrics['cv_auc_mean']:.4f} (n={metrics['n_samples']:,})")

        return self.metrics

    def save(self, name: str = 'conditional'):
        """モデルを保存"""
        os.makedirs(self.model_dir, exist_ok=True)

        for stage, model in self.models.items():
            if model is not None:
                model_path = os.path.join(self.model_dir, f'{name}_{stage}.joblib')
                joblib.dump(model, model_path)
                print(f"保存: {model_path}")

        # メタ情報
        meta = {
            'feature_names': self.feature_names,
            'metrics': {k: {kk: vv if not isinstance(vv, np.ndarray) else vv.tolist()
                           for kk, vv in v.items()}
                       for k, v in self.metrics.items()},
            'created_at': datetime.now().isoformat(),
        }
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print(f"保存: {meta_path}")

    def load(self, name: str = 'conditional'):
        """モデルを読み込み"""
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        self.feature_names = meta['feature_names']
        self.metrics = meta.get('metrics', {})

        for stage in ['stage1', 'stage2', 'stage3']:
            model_path = os.path.join(self.model_dir, f'{name}_{stage}.joblib')
            if os.path.exists(model_path):
                self.models[stage] = joblib.load(model_path)
                print(f"読み込み: {model_path}")


def main():
    """メイン実行"""
    import argparse

    parser = argparse.ArgumentParser(description='条件付き着順モデルの学習')
    parser.add_argument('--db', default='data/boatrace.db', help='DBパス')
    parser.add_argument('--start-date', default='2024-01-01', help='開始日')
    parser.add_argument('--end-date', default=None, help='終了日')
    parser.add_argument('--model-type', default='xgboost', choices=['xgboost', 'lightgbm'])
    parser.add_argument('--output-name', default='conditional', help='出力モデル名')

    args = parser.parse_args()

    trainer = ConditionalModelTrainer(args.db)

    # データ読み込み
    df = trainer.load_training_data(args.start_date, args.end_date)

    if len(df) == 0:
        print("学習データがありません")
        return

    # 学習
    trainer.train_all(df, args.model_type)

    # 保存
    trainer.save(args.output_name)

    print("\n学習完了！")


if __name__ == '__main__':
    main()
