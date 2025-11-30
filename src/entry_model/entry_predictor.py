"""
進入予測モデル
Phase 1: 本番レースの進入コースを予測
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
import joblib
import json


class EntryPredictor:
    """
    進入（コース取り）予測クラス

    各艇の進入確率分布 P(in_i = 1〜6) を予測
    """

    def __init__(self, model_dir: str = 'models'):
        self.model_dir = model_dir
        self.model = None
        self.feature_names = None
        self._loaded = False

    def load_model(self) -> bool:
        """モデルを読み込み"""
        if self._loaded:
            return True

        model_path = os.path.join(self.model_dir, 'entry_model.joblib')
        meta_path = os.path.join(self.model_dir, 'entry_model_meta.json')

        if not os.path.exists(model_path):
            print(f"進入予測モデルが見つかりません: {model_path}")
            return False

        try:
            self.model = joblib.load(model_path)
            print(f"進入予測モデル読み込み: {model_path}")

            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                self.feature_names = meta.get('feature_names', [])

            self._loaded = True
            return True

        except Exception as e:
            print(f"モデル読み込みエラー: {e}")
            return False

    def predict_entry_probs(self, features_df: pd.DataFrame) -> np.ndarray:
        """
        各艇の進入確率を予測

        Args:
            features_df: 6艇分の特徴量DataFrame

        Returns:
            (6, 6)の確率行列 - [艇インデックス, コースインデックス]
        """
        if not self._loaded:
            if not self.load_model():
                # モデルがない場合はデフォルト確率を返す
                return self._default_entry_probs(features_df)

        if len(features_df) != 6:
            raise ValueError(f"6艇分のデータが必要です（現在: {len(features_df)}艇）")

        # 特徴量を準備
        X = self._prepare_features(features_df)

        # 各艇の進入確率を予測
        # XGBoostのmulti:softprobは各クラスの確率を返す
        probs = self.model.predict_proba(X)

        return probs

    def predict_most_likely_entry(self, features_df: pd.DataFrame) -> np.ndarray:
        """
        最も可能性の高い進入コースを予測

        Args:
            features_df: 6艇分の特徴量DataFrame

        Returns:
            各艇の予測進入コース (1-6)
        """
        probs = self.predict_entry_probs(features_df)
        return np.argmax(probs, axis=1) + 1

    def predict_entry_distribution(self, features_df: pd.DataFrame) -> Dict[int, Dict[int, float]]:
        """
        各艇の進入確率分布を辞書形式で返す

        Args:
            features_df: 6艇分の特徴量DataFrame

        Returns:
            {pit_number: {course: probability}}
        """
        probs = self.predict_entry_probs(features_df)
        pit_numbers = features_df['pit_number'].values

        result = {}
        for i, pit in enumerate(pit_numbers):
            result[int(pit)] = {
                course: float(probs[i, course - 1])
                for course in range(1, 7)
            }

        return result

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """特徴量を準備"""
        exclude_cols = ['race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'actual_course']

        if self.feature_names:
            # 保存された特徴量リストに合わせる
            X = df.reindex(columns=self.feature_names, fill_value=0)
        else:
            X = df.drop([c for c in exclude_cols if c in df.columns], axis=1)
            X = X.select_dtypes(include=[np.number])

        return X

    def _default_entry_probs(self, features_df: pd.DataFrame) -> np.ndarray:
        """
        モデルがない場合のデフォルト確率

        枠番と同じコースになる確率を高めに設定
        """
        n_boats = len(features_df)
        probs = np.zeros((n_boats, 6))

        for i, row in features_df.iterrows():
            pit = int(row['pit_number'])

            # 基本確率（枠番と同じコースが高い）
            for course in range(1, 7):
                if course == pit:
                    probs[i, course - 1] = 0.7
                elif abs(course - pit) == 1:
                    probs[i, course - 1] = 0.1
                else:
                    probs[i, course - 1] = 0.05

            # 正規化
            probs[i] = probs[i] / probs[i].sum()

        return probs

    def adjust_probabilities_for_race(self, probs: np.ndarray) -> np.ndarray:
        """
        レース制約を考慮して確率を調整

        - 各コースには1艇のみ
        - 全艇がどこかのコースに入る

        Args:
            probs: (6, 6)の確率行列

        Returns:
            調整後の確率行列
        """
        n_boats = probs.shape[0]
        adjusted = probs.copy()

        # Sinkhorn-Knopp アルゴリズムで行和・列和が1になるよう調整
        for _ in range(10):
            # 行正規化
            row_sums = adjusted.sum(axis=1, keepdims=True)
            adjusted = adjusted / np.maximum(row_sums, 1e-10)

            # 列正規化
            col_sums = adjusted.sum(axis=0, keepdims=True)
            adjusted = adjusted / np.maximum(col_sums, 1e-10)

        return adjusted

    def sample_entry_permutation(self, probs: np.ndarray,
                                  n_samples: int = 100) -> List[Tuple[int, ...]]:
        """
        確率に基づいて進入順をサンプリング

        Args:
            probs: (6, 6)の確率行列
            n_samples: サンプル数

        Returns:
            サンプリングされた進入順のリスト
        """
        from itertools import permutations as perm

        # 全順列の確率を計算
        all_perms = list(perm(range(6)))
        perm_probs = []

        for p in all_perms:
            prob = 1.0
            for boat_idx, course_idx in enumerate(p):
                prob *= probs[boat_idx, course_idx]
            perm_probs.append(prob)

        # 正規化
        perm_probs = np.array(perm_probs)
        perm_probs = perm_probs / perm_probs.sum()

        # サンプリング
        indices = np.random.choice(len(all_perms), size=n_samples, p=perm_probs)

        return [tuple(c + 1 for c in all_perms[i]) for i in indices]

    def get_top_entry_patterns(self, probs: np.ndarray,
                                top_n: int = 5) -> List[Tuple[Tuple[int, ...], float]]:
        """
        確率の高い進入パターンを取得

        Args:
            probs: (6, 6)の確率行列
            top_n: 取得するパターン数

        Returns:
            [(進入パターン, 確率), ...]
        """
        from itertools import permutations as perm

        all_perms = list(perm(range(6)))
        perm_probs = []

        for p in all_perms:
            prob = 1.0
            for boat_idx, course_idx in enumerate(p):
                prob *= probs[boat_idx, course_idx]
            perm_probs.append((tuple(c + 1 for c in p), prob))

        # 確率でソート
        perm_probs.sort(key=lambda x: x[1], reverse=True)

        # 正規化
        total = sum(p[1] for p in perm_probs)
        normalized = [(p[0], p[1] / total) for p in perm_probs[:top_n]]

        return normalized


class EntryPredictionResult:
    """進入予測結果を保持するクラス"""

    def __init__(self, pit_numbers: List[int], probs: np.ndarray):
        self.pit_numbers = pit_numbers
        self.probs = probs
        self._predictor = EntryPredictor()

    def get_most_likely_entry(self) -> Dict[int, int]:
        """各艇の最も可能性の高い進入コース"""
        courses = np.argmax(self.probs, axis=1) + 1
        return {pit: int(course) for pit, course in zip(self.pit_numbers, courses)}

    def get_entry_distribution(self) -> Dict[int, Dict[int, float]]:
        """各艇の進入確率分布"""
        result = {}
        for i, pit in enumerate(self.pit_numbers):
            result[pit] = {
                course: float(self.probs[i, course - 1])
                for course in range(1, 7)
            }
        return result

    def get_top_patterns(self, top_n: int = 5) -> List[Tuple[Dict[int, int], float]]:
        """確率の高い進入パターン"""
        patterns = self._predictor.get_top_entry_patterns(self.probs, top_n)

        result = []
        for pattern, prob in patterns:
            entry_dict = {self.pit_numbers[i]: pattern[i] for i in range(6)}
            result.append((entry_dict, prob))

        return result

    def get_deviation_probability(self) -> float:
        """枠なり以外になる確率"""
        # 対角成分（枠なり）以外の確率合計
        off_diagonal = 0
        for i in range(6):
            for j in range(6):
                if i != j:
                    off_diagonal += self.probs[i, j]

        return off_diagonal / 6  # 平均

    def to_dict(self) -> Dict:
        """辞書形式に変換"""
        return {
            'most_likely_entry': self.get_most_likely_entry(),
            'entry_distribution': self.get_entry_distribution(),
            'top_patterns': [
                {'pattern': pattern, 'probability': prob}
                for pattern, prob in self.get_top_patterns(3)
            ],
            'deviation_probability': self.get_deviation_probability(),
        }
