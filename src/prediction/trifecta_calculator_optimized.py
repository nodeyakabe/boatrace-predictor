"""
三連単確率計算モジュール（最適化版）
Phase 3: P(1=i) × P(2=j|1=i) × P(3=k|1=i,2=j) の計算

最適化内容:
- 特徴量キャッシュ（提案A: 40%高速化）
- 一括バッチ予測（提案B: 50%高速化）
- 既存ロジックは変更せず、計算効率のみ改善
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from itertools import permutations
import joblib
import json
import os


class TrifectaCalculatorOptimized:
    """
    三連単確率計算クラス（最適化版）

    既存のTrifectaCalculatorと互換性を保ちつつ、高速化を実現
    """

    def __init__(self, model_dir: str = 'models', model_name: str = 'conditional', use_v2: bool = False):
        self.model_dir = model_dir
        self.model_name = model_name
        self.use_v2 = use_v2
        self.models = {}
        self.feature_names = {}
        self._loaded = False
        self._feature_cache = {}  # 特徴量キャッシュ

    def load_models(self):
        """Stage1/2/3モデルを読み込み"""
        if self._loaded:
            return

        if self.use_v2:
            self._load_v2_models()
        else:
            self._load_v1_models()

        self._loaded = True

    def _load_v1_models(self):
        """v1モデルを読み込み"""
        # メタ情報を読み込み
        meta_path = os.path.join(self.model_dir, f'{self.model_name}_meta.json')
        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            self.feature_names = meta.get('feature_names', meta.get('features', {}))

        # 各Stageモデルを読み込み
        for stage in ['stage1', 'stage2', 'stage3']:
            model_path = os.path.join(self.model_dir, f'{self.model_name}_{stage}.joblib')
            if os.path.exists(model_path):
                self.models[stage] = joblib.load(model_path)
                print(f"v1モデル読み込み: {stage}")

    def _load_v2_models(self):
        """v2モデルを読み込み（最新版を自動検索）"""
        from pathlib import Path

        model_dir_path = Path(self.model_dir)

        # 最新のv2モデルを検索
        v2_files = list(model_dir_path.glob("conditional_stage2_v2_*.joblib"))
        if not v2_files:
            print("v2モデルが見つかりません。v1モデルを使用します。")
            self._load_v1_models()
            return

        latest = sorted(v2_files)[-1]
        parts = latest.stem.split('_')
        timestamp = '_'.join(parts[-2:])

        print(f"v2モデルタイムスタンプ: {timestamp}")

        # v2モデル読み込み
        for stage in ['stage1', 'stage2', 'stage3']:
            model_path = model_dir_path / f"conditional_{stage}_v2_{timestamp}.joblib"
            if model_path.exists():
                self.models[stage] = joblib.load(model_path)
                print(f"v2モデル読み込み: {stage}")

        # v2メタ情報を読み込み
        meta_path = model_dir_path / f"conditional_meta_v2_{timestamp}.json"
        if meta_path.exists():
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            self.feature_names = meta.get('features', {})

    def calculate(self, race_features: pd.DataFrame,
                  pit_column: str = 'pit_number') -> Dict[str, float]:
        """
        三連単の全120通りの確率を計算（最適化版）

        Args:
            race_features: 6艇分の特徴量DataFrame
            pit_column: ピット番号のカラム名

        Returns:
            {'1-2-3': 0.15, '1-3-2': 0.12, ...} 形式の確率辞書
        """
        if not self._loaded:
            self.load_models()

        if len(race_features) != 6:
            raise ValueError(f"6艇分のデータが必要です（現在: {len(race_features)}艇）")

        # 提案A: 特徴量キャッシュを構築（型チェックを1回のみ実行）
        self._build_feature_cache(race_features)

        pit_numbers = race_features[pit_column].values.astype(int)

        # 提案B: 一括バッチ予測
        return self._calculate_batched(race_features, pit_numbers)

    def _build_feature_cache(self, df: pd.DataFrame):
        """
        全艇の特徴量を事前計算してキャッシュ（提案A）

        型チェックを1回のみ実行し、以降の特徴量作成で再利用
        """
        exclude_cols = {'race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number', 'rank'}

        self._feature_cache = {}
        for idx in range(len(df)):
            row = df.iloc[idx]
            numeric_features = {}
            for col in df.columns:
                if col not in exclude_cols:
                    val = row[col]
                    # 数値型のみキャッシュ（型チェックは1回のみ）
                    if isinstance(val, (int, float, np.integer, np.floating)):
                        numeric_features[col] = float(val)
            self._feature_cache[idx] = numeric_features

    def _calculate_batched(self, race_features: pd.DataFrame,
                          pit_numbers: np.ndarray) -> Dict[str, float]:
        """
        一括バッチ予測版の三連単計算（提案B）

        LightGBM呼び出しを最小化（151回→3回）
        """
        feature_cols_s1 = self.feature_names.get('stage1', [])
        feature_cols_s2 = self.feature_names.get('stage2', [])
        feature_cols_s3 = self.feature_names.get('stage3', [])

        # Stage1: 1着確率（6艇を一括予測）
        first_probs = self._predict_first_place(race_features)

        # Stage2: 全30パターン(6×5)の特徴量を一括作成
        stage2_inputs = []
        stage2_mapping = []  # (first_idx, second_idx)

        for i in range(6):
            for j in range(6):
                if j == i:
                    continue
                features = self._create_stage2_features_cached(j, i, feature_cols_s2)
                stage2_inputs.append(features)
                stage2_mapping.append((i, j))

        # 一括予測（30パターンを1回で）
        if len(stage2_inputs) > 0 and self.models.get('stage2') is not None:
            stage2_all_probs = self.models['stage2'].predict_proba(stage2_inputs)[:, 1]
        else:
            stage2_all_probs = np.ones(len(stage2_inputs)) / 5

        # Stage2結果を格納・正規化
        second_probs = {}
        for idx, (i, j) in enumerate(stage2_mapping):
            if i not in second_probs:
                second_probs[i] = {}
            second_probs[i][j] = stage2_all_probs[idx]

        # 各1着候補ごとに2着確率を正規化
        for i in second_probs:
            total = sum(second_probs[i].values())
            if total > 0:
                second_probs[i] = {j: p/total for j, p in second_probs[i].items()}

        # Stage3: 全120パターン(6×5×4)の特徴量を一括作成
        stage3_inputs = []
        stage3_mapping = []  # (first_idx, second_idx, third_idx)

        for i in range(6):
            for j in range(6):
                if j == i:
                    continue
                for k in range(6):
                    if k == i or k == j:
                        continue
                    features = self._create_stage3_features_cached(k, i, j, feature_cols_s3)
                    stage3_inputs.append(features)
                    stage3_mapping.append((i, j, k))

        # 一括予測（120パターンを1回で）
        if len(stage3_inputs) > 0 and self.models.get('stage3') is not None:
            stage3_all_probs = self.models['stage3'].predict_proba(stage3_inputs)[:, 1]
        else:
            stage3_all_probs = np.ones(len(stage3_inputs)) / 4

        # 三連単確率を計算
        trifecta_probs = {}
        for idx, (i, j, k) in enumerate(stage3_mapping):
            p_first = first_probs[i]
            p_second = second_probs.get(i, {}).get(j, 0)

            # Stage3の正規化（同一1-2着ペアで合計1になるように）
            same_pair_indices = [n for n, (fi, fj, fk) in enumerate(stage3_mapping) if fi == i and fj == j]
            same_pair_sum = sum(stage3_all_probs[n] for n in same_pair_indices)
            p_third = stage3_all_probs[idx] / same_pair_sum if same_pair_sum > 0 else 0.25

            # ベイズの連鎖則: P(i,j,k) = P(i) × P(j|i) × P(k|i,j)
            prob = p_first * p_second * p_third
            combination = f"{pit_numbers[i]}-{pit_numbers[j]}-{pit_numbers[k]}"
            trifecta_probs[combination] = float(prob)

        # 最終正規化
        total = sum(trifecta_probs.values())
        if total > 0:
            trifecta_probs = {k: v/total for k, v in trifecta_probs.items()}

        return trifecta_probs

    def _predict_first_place(self, race_features: pd.DataFrame) -> np.ndarray:
        """1着確率を予測（既存ロジックと同じ）"""
        if 'stage1' not in self.models or self.models['stage1'] is None:
            return np.ones(6) / 6

        feature_cols = self.feature_names.get('stage1', [])
        X = self._prepare_features(race_features, feature_cols)
        probs = self.models['stage1'].predict_proba(X)[:, 1]
        return probs / probs.sum()

    def _prepare_features(self, df: pd.DataFrame, feature_cols: List[str]) -> pd.DataFrame:
        """特徴量を準備"""
        exclude_cols = ['race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number', 'rank']

        if not feature_cols:
            X = df.drop([c for c in exclude_cols if c in df.columns], axis=1)
            X = X.select_dtypes(include=[np.number])
        else:
            X = df.reindex(columns=feature_cols, fill_value=0)

        return X

    def _create_stage2_features_cached(self, candidate_idx: int,
                                        winner_idx: int,
                                        feature_cols: List[str]) -> np.ndarray:
        """
        キャッシュを使用したStage2特徴量作成（高速版）

        従来の型チェックを省略してキャッシュから直接取得
        """
        candidate = self._feature_cache[candidate_idx]
        winner = self._feature_cache[winner_idx]

        features = {}

        # 候補艇の特徴量
        for col, val in candidate.items():
            features[col] = val

        # 1着艇の特徴量
        for col, val in winner.items():
            features[f'winner_{col}'] = val

        # 差分特徴量（共通カラムのみ）
        common_cols = set(candidate.keys()) & set(winner.keys())
        for col in common_cols:
            features[f'diff_{col}'] = candidate[col] - winner[col]

        # 特徴量リストに合わせて並び替え
        return np.array([features.get(col, 0) for col in feature_cols])

    def _create_stage3_features_cached(self, candidate_idx: int,
                                        winner_idx: int,
                                        second_idx: int,
                                        feature_cols: List[str]) -> np.ndarray:
        """
        キャッシュを使用したStage3特徴量作成（高速版）
        """
        candidate = self._feature_cache[candidate_idx]
        winner = self._feature_cache[winner_idx]
        second = self._feature_cache[second_idx]

        features = {}

        # 候補艇の特徴量
        for col, val in candidate.items():
            features[col] = val

        # 1着艇の特徴量
        for col, val in winner.items():
            features[f'winner_{col}'] = val

        # 2着艇の特徴量
        for col, val in second.items():
            features[f'second_{col}'] = val

        # 差分特徴量
        common_cols = set(candidate.keys()) & set(winner.keys()) & set(second.keys())
        for col in common_cols:
            features[f'diff_winner_{col}'] = candidate[col] - winner[col]
            features[f'diff_second_{col}'] = candidate[col] - second[col]

        return np.array([features.get(col, 0) for col in feature_cols])

    def get_top_combinations(self, probs: Dict[str, float],
                             top_n: int = 10) -> List[Tuple[str, float]]:
        """上位N件の組み合わせを取得"""
        sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)
        return sorted_probs[:top_n]
