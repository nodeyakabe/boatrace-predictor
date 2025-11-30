"""
タイプ別モデル管理
Phase 5: レースタイプごとの専用モデル
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
import joblib
import json
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score

from src.race_type_model.race_type_classifier import RaceTypeClassifier


class TypeSpecificModelManager:
    """
    レースタイプ別モデル管理クラス

    8種類のレースタイプごとに専用のStage1/2/3モデルを管理
    """

    def __init__(self, model_dir: str = 'models'):
        self.model_dir = model_dir
        self.classifier = RaceTypeClassifier()

        # {race_type: {'stage1': model, 'stage2': model, 'stage3': model}}
        self.models = {}
        self.feature_names = {}
        self.metrics = {}

        self._loaded = False

    def train_type_models(self, df: pd.DataFrame,
                           race_type: str,
                           model_type: str = 'xgboost') -> Dict:
        """
        特定のレースタイプ用モデルを学習

        Args:
            df: 学習データ
            race_type: レースタイプ
            model_type: モデルタイプ

        Returns:
            学習メトリクス
        """
        print(f"\n=== {race_type}タイプモデル学習 ===")

        # レースタイプでフィルタ
        type_venues = self.classifier.get_venues_for_type(race_type)
        df_type = df[df['venue_code'].isin(type_venues)].copy()

        if len(df_type) < 1000:
            print(f"データ不足: {len(df_type)}件 (最低1000件必要)")
            return {}

        print(f"対象データ: {len(df_type):,}件")

        # 特徴量重み
        feature_weights = self.classifier.get_feature_weights(race_type)

        # Stage1/2/3の学習
        self.models[race_type] = {}
        self.feature_names[race_type] = {}
        type_metrics = {}

        # Stage1
        X1, y1 = self._prepare_stage1_data(df_type)
        if len(X1) > 0:
            X1 = self._apply_feature_weights(X1, feature_weights)
            model1, metrics1 = self._train_xgboost(X1, y1, 'Stage1')
            self.models[race_type]['stage1'] = model1
            self.feature_names[race_type]['stage1'] = list(X1.columns)
            type_metrics['stage1'] = metrics1

        # Stage2
        X2, y2 = self._prepare_stage2_data(df_type)
        if len(X2) > 0:
            model2, metrics2 = self._train_xgboost(X2, y2, 'Stage2')
            self.models[race_type]['stage2'] = model2
            self.feature_names[race_type]['stage2'] = list(X2.columns)
            type_metrics['stage2'] = metrics2

        # Stage3
        X3, y3 = self._prepare_stage3_data(df_type)
        if len(X3) > 0:
            model3, metrics3 = self._train_xgboost(X3, y3, 'Stage3')
            self.models[race_type]['stage3'] = model3
            self.feature_names[race_type]['stage3'] = list(X3.columns)
            type_metrics['stage3'] = metrics3

        self.metrics[race_type] = type_metrics

        return type_metrics

    def train_all_types(self, df: pd.DataFrame) -> Dict:
        """
        全レースタイプのモデルを学習

        Args:
            df: 学習データ（venue_codeカラム必須）

        Returns:
            全タイプのメトリクス
        """
        print("\n" + "=" * 60)
        print("レースタイプ別モデル学習開始")
        print("=" * 60)

        all_metrics = {}

        for race_type in self.classifier.get_all_types():
            try:
                metrics = self.train_type_models(df, race_type)
                if metrics:
                    all_metrics[race_type] = metrics
            except Exception as e:
                print(f"{race_type}タイプの学習エラー: {e}")

        print("\n" + "=" * 60)
        print("学習完了サマリ")
        print("=" * 60)

        for race_type, metrics in all_metrics.items():
            type_name = self.classifier.get_type_config(race_type)['name']
            if 'stage1' in metrics:
                auc = metrics['stage1'].get('cv_auc_mean', 0)
                print(f"{type_name}: Stage1 AUC = {auc:.4f}")

        return all_metrics

    def _prepare_stage1_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """Stage1用データを準備"""
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df_valid = df[df['race_id'].isin(valid_races)].copy()

        if len(df_valid) == 0:
            return pd.DataFrame(), np.array([])

        exclude_cols = ['rank', 'race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number']
        X = df_valid.drop([c for c in exclude_cols if c in df_valid.columns], axis=1)
        X = X.select_dtypes(include=[np.number]).fillna(0)

        y = (df_valid['rank'] == 1).astype(int).values

        return X, y

    def _prepare_stage2_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """Stage2用データを準備"""
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df_valid = df[df['race_id'].isin(valid_races)].copy()

        if len(df_valid) == 0:
            return pd.DataFrame(), np.array([])

        first_place = df_valid[df_valid['rank'] == 1][['race_id', 'pit_number']].copy()
        first_place.columns = ['race_id', 'first_pit']

        df_with_first = df_valid.merge(first_place, on='race_id')
        remaining = df_with_first[df_with_first['pit_number'] != df_with_first['first_pit']].copy()

        y = (remaining['rank'] == 2).astype(int).values

        exclude_cols = ['rank', 'race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number', 'first_pit']
        X = remaining.drop([c for c in exclude_cols if c in remaining.columns], axis=1)
        X = X.select_dtypes(include=[np.number]).fillna(0)

        return X, y

    def _prepare_stage3_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """Stage3用データを準備"""
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df_valid = df[df['race_id'].isin(valid_races)].copy()

        if len(df_valid) == 0:
            return pd.DataFrame(), np.array([])

        first_place = df_valid[df_valid['rank'] == 1][['race_id', 'pit_number']].copy()
        first_place.columns = ['race_id', 'first_pit']

        second_place = df_valid[df_valid['rank'] == 2][['race_id', 'pit_number']].copy()
        second_place.columns = ['race_id', 'second_pit']

        df_merged = df_valid.merge(first_place, on='race_id').merge(second_place, on='race_id')
        remaining = df_merged[
            (df_merged['pit_number'] != df_merged['first_pit']) &
            (df_merged['pit_number'] != df_merged['second_pit'])
        ].copy()

        y = (remaining['rank'] == 3).astype(int).values

        exclude_cols = ['rank', 'race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number', 'first_pit', 'second_pit']
        X = remaining.drop([c for c in exclude_cols if c in remaining.columns], axis=1)
        X = X.select_dtypes(include=[np.number]).fillna(0)

        return X, y

    def _apply_feature_weights(self, X: pd.DataFrame,
                                feature_weights: Dict[str, float]) -> pd.DataFrame:
        """特徴量に重みを適用"""
        X = X.copy()

        for feature_key, weight in feature_weights.items():
            # 関連するカラムを見つける
            for col in X.columns:
                if feature_key.lower() in col.lower():
                    X[col] = X[col] * weight

        return X

    def _train_xgboost(self, X: pd.DataFrame, y: np.ndarray,
                       stage_name: str) -> Tuple[xgb.XGBClassifier, Dict]:
        """XGBoostモデルを学習"""
        params = {
            'objective': 'binary:logistic',
            'eval_metric': 'auc',
            'max_depth': 5,
            'learning_rate': 0.05,
            'n_estimators': 300,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'min_child_weight': 5,
            'gamma': 0.1,
            'random_state': 42,
            'n_jobs': -1,
        }

        tscv = TimeSeriesSplit(n_splits=3)
        cv_scores = []

        for train_idx, val_idx in tscv.split(X):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            model = xgb.XGBClassifier(**params)
            model.fit(X_train, y_train, verbose=False)

            val_pred = model.predict_proba(X_val)[:, 1]
            auc = roc_auc_score(y_val, val_pred)
            cv_scores.append(auc)

        # 全データで学習
        final_model = xgb.XGBClassifier(**params)
        final_model.fit(X, y, verbose=False)

        metrics = {
            'cv_auc_mean': np.mean(cv_scores),
            'cv_auc_std': np.std(cv_scores),
            'n_samples': len(X),
        }

        return final_model, metrics

    def get_model(self, race_type: str, stage: str) -> Optional[xgb.XGBClassifier]:
        """特定タイプ・ステージのモデルを取得"""
        if race_type in self.models:
            return self.models[race_type].get(stage)
        return None

    def save(self, name: str = 'type_models') -> None:
        """モデルを保存"""
        os.makedirs(self.model_dir, exist_ok=True)

        for race_type, stages in self.models.items():
            for stage, model in stages.items():
                if model is not None:
                    model_path = os.path.join(
                        self.model_dir, f'{name}_{race_type}_{stage}.joblib'
                    )
                    joblib.dump(model, model_path)

        meta = {
            'feature_names': self.feature_names,
            'metrics': self.metrics,
            'race_types': list(self.models.keys()),
        }
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        print(f"タイプ別モデル保存完了: {len(self.models)}タイプ")

    def load(self, name: str = 'type_models') -> bool:
        """モデルを読み込み"""
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')

        if not os.path.exists(meta_path):
            return False

        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            self.feature_names = meta.get('feature_names', {})
            self.metrics = meta.get('metrics', {})
            race_types = meta.get('race_types', [])

            for race_type in race_types:
                self.models[race_type] = {}
                for stage in ['stage1', 'stage2', 'stage3']:
                    model_path = os.path.join(
                        self.model_dir, f'{name}_{race_type}_{stage}.joblib'
                    )
                    if os.path.exists(model_path):
                        self.models[race_type][stage] = joblib.load(model_path)

            self._loaded = True
            print(f"タイプ別モデル読み込み: {len(self.models)}タイプ")
            return True

        except Exception as e:
            print(f"モデル読み込みエラー: {e}")
            return False
