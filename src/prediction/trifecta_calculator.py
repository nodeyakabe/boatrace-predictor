"""
三連単確率計算モジュール
Phase 3: P(1=i) × P(2=j|1=i) × P(3=k|1=i,2=j) の計算

ベイズの連鎖則に基づく条件付き確率の統合
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from itertools import permutations
import joblib
import json
import os


class TrifectaCalculator:
    """
    三連単確率計算クラス

    Stage1/2/3モデルを統合して120通りの三連単確率を計算
    """

    def __init__(self, model_dir: str = 'models', model_name: str = 'conditional', use_v2: bool = False):
        self.model_dir = model_dir
        self.model_name = model_name
        self.use_v2 = use_v2
        self.models = {}
        self.feature_names = {}
        self._loaded = False

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
        三連単の全120通りの確率を計算

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

        pit_numbers = race_features[pit_column].values.astype(int)

        # Stage1: 1着確率を計算
        first_probs = self._predict_first_place(race_features)

        # 全120通りの確率を計算
        trifecta_probs = {}

        for i in range(6):  # 1着候補
            p_first = first_probs[i]

            # Stage2: この艇が1着の場合の2着確率
            second_probs = self._predict_second_place(race_features, i)

            for j in range(6):  # 2着候補
                if j == i:
                    continue

                p_second = second_probs[j]

                # Stage3: この艇が1着、j番が2着の場合の3着確率
                third_probs = self._predict_third_place(race_features, i, j)

                for k in range(6):  # 3着候補
                    if k == i or k == j:
                        continue

                    p_third = third_probs[k]

                    # 三連単確率 = P(1st) × P(2nd|1st) × P(3rd|1st,2nd)
                    prob = p_first * p_second * p_third

                    combination = f"{pit_numbers[i]}-{pit_numbers[j]}-{pit_numbers[k]}"
                    trifecta_probs[combination] = float(prob)

        # 確率の正規化（合計が1になるように）
        total = sum(trifecta_probs.values())
        if total > 0:
            trifecta_probs = {k: v / total for k, v in trifecta_probs.items()}

        return trifecta_probs

    def _predict_first_place(self, race_features: pd.DataFrame) -> np.ndarray:
        """1着確率を予測"""
        if 'stage1' not in self.models or self.models['stage1'] is None:
            # モデルがない場合は均等確率
            return np.ones(6) / 6

        # 特徴量を準備
        feature_cols = self.feature_names.get('stage1', [])
        X = self._prepare_features(race_features, feature_cols)

        # 予測
        probs = self.models['stage1'].predict_proba(X)[:, 1]

        # 正規化
        probs = probs / probs.sum()

        return probs

    def _predict_second_place(self, race_features: pd.DataFrame,
                               first_idx: int) -> np.ndarray:
        """1着が確定した場合の2着確率を予測（バッチ最適化版）"""
        if 'stage2' not in self.models or self.models['stage2'] is None:
            # モデルがない場合は残り5艇で均等確率
            probs = np.ones(6) / 5
            probs[first_idx] = 0
            return probs

        feature_cols = self.feature_names.get('stage2', [])

        # 1着艇の特徴量
        first_features = race_features.iloc[first_idx]

        # 候補艇の特徴量を一括作成（バッチ処理）
        candidate_indices = [j for j in range(6) if j != first_idx]
        feature_batch = []

        for j in candidate_indices:
            candidate_features = self._create_stage2_features(
                race_features.iloc[j], first_features, feature_cols
            )
            if len(candidate_features) > 0:
                feature_batch.append(candidate_features)

        # バッチ予測（1回のpredict_probaで全候補を予測）
        probs = np.zeros(6)
        if len(feature_batch) > 0:
            batch_preds = self.models['stage2'].predict_proba(feature_batch)[:, 1]
            for i, j in enumerate(candidate_indices):
                probs[j] = batch_preds[i]

        # 正規化
        total = probs.sum()
        if total > 0:
            probs = probs / total

        return probs

    def _predict_third_place(self, race_features: pd.DataFrame,
                              first_idx: int, second_idx: int) -> np.ndarray:
        """1着・2着が確定した場合の3着確率を予測（バッチ最適化版）"""
        if 'stage3' not in self.models or self.models['stage3'] is None:
            # モデルがない場合は残り4艇で均等確率
            probs = np.ones(6) / 4
            probs[first_idx] = 0
            probs[second_idx] = 0
            return probs

        feature_cols = self.feature_names.get('stage3', [])

        # 1着・2着艇の特徴量
        first_features = race_features.iloc[first_idx]
        second_features = race_features.iloc[second_idx]

        # 候補艇の特徴量を一括作成（バッチ処理）
        candidate_indices = [k for k in range(6) if k != first_idx and k != second_idx]
        feature_batch = []

        for k in candidate_indices:
            candidate_features = self._create_stage3_features(
                race_features.iloc[k], first_features, second_features, feature_cols
            )
            if len(candidate_features) > 0:
                feature_batch.append(candidate_features)

        # バッチ予測（1回のpredict_probaで全候補を予測）
        probs = np.zeros(6)
        if len(feature_batch) > 0:
            batch_preds = self.models['stage3'].predict_proba(feature_batch)[:, 1]
            for i, k in enumerate(candidate_indices):
                probs[k] = batch_preds[i]

        # 正規化
        total = probs.sum()
        if total > 0:
            probs = probs / total

        return probs

    def _prepare_features(self, df: pd.DataFrame, feature_cols: List[str]) -> pd.DataFrame:
        """特徴量を準備"""
        exclude_cols = ['race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number', 'rank']

        if not feature_cols:
            # 特徴量リストがない場合は数値カラムを使用
            X = df.drop([c for c in exclude_cols if c in df.columns], axis=1)
            X = X.select_dtypes(include=[np.number])
        else:
            X = df.reindex(columns=feature_cols, fill_value=0)

        return X

    def _create_stage2_features(self, candidate: pd.Series,
                                 winner: pd.Series,
                                 feature_cols: List[str]) -> np.ndarray:
        """Stage2用の特徴量を作成（高速化版）"""
        if not feature_cols:
            return np.array([])

        # 除外カラム
        exclude_cols = {'race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number', 'rank'}

        features = {}

        # 数値型カラムのみを事前フィルタリング
        candidate_numeric = candidate[candidate.apply(lambda x: isinstance(x, (int, float, np.number)))]
        winner_numeric = winner[winner.apply(lambda x: isinstance(x, (int, float, np.number)))]

        # 候補艇の特徴量（ベクトル化）
        for col in candidate_numeric.index:
            if col not in exclude_cols:
                features[col] = candidate_numeric[col]

        # 1着艇の特徴量（ベクトル化）
        for col in winner_numeric.index:
            if col not in exclude_cols:
                features[f'winner_{col}'] = winner_numeric[col]

        # 差分特徴量（共通カラムのみ）
        common_cols = set(candidate_numeric.index) & set(winner_numeric.index) - exclude_cols
        for col in common_cols:
            features[f'diff_{col}'] = candidate_numeric[col] - winner_numeric[col]

        # 特徴量リストに合わせて並び替え
        result = np.array([features.get(col, 0) for col in feature_cols])

        return result

    def _create_stage3_features(self, candidate: pd.Series,
                                 winner: pd.Series,
                                 second: pd.Series,
                                 feature_cols: List[str]) -> np.ndarray:
        """Stage3用の特徴量を作成（高速化版）"""
        if not feature_cols:
            return np.array([])

        # 除外カラム
        exclude_cols = {'race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number', 'rank'}

        features = {}

        # 数値型カラムのみを事前フィルタリング
        candidate_numeric = candidate[candidate.apply(lambda x: isinstance(x, (int, float, np.number)))]
        winner_numeric = winner[winner.apply(lambda x: isinstance(x, (int, float, np.number)))]
        second_numeric = second[second.apply(lambda x: isinstance(x, (int, float, np.number)))]

        # 候補艇の特徴量（ベクトル化）
        for col in candidate_numeric.index:
            if col not in exclude_cols:
                features[col] = candidate_numeric[col]

        # 1着艇の特徴量（ベクトル化）
        for col in winner_numeric.index:
            if col not in exclude_cols:
                features[f'winner_{col}'] = winner_numeric[col]

        # 2着艇の特徴量（ベクトル化）
        for col in second_numeric.index:
            if col not in exclude_cols:
                features[f'second_{col}'] = second_numeric[col]

        # 差分特徴量（共通カラムのみ）
        common_cols = set(candidate_numeric.index) & set(winner_numeric.index) & set(second_numeric.index) - exclude_cols
        for col in common_cols:
            features[f'diff_winner_{col}'] = candidate_numeric[col] - winner_numeric[col]
            features[f'diff_second_{col}'] = candidate_numeric[col] - second_numeric[col]

        # 特徴量リストに合わせて並び替え
        result = np.array([features.get(col, 0) for col in feature_cols])

        return result

    def get_top_combinations(self, probs: Dict[str, float],
                             top_n: int = 10) -> List[Tuple[str, float]]:
        """上位N件の組み合わせを取得"""
        sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)
        return sorted_probs[:top_n]

    def calculate_ev(self, probs: Dict[str, float],
                     odds: Dict[str, float]) -> Dict[str, float]:
        """
        期待値（Expected Value）を計算

        Args:
            probs: 三連単確率
            odds: 三連単オッズ

        Returns:
            期待値（EV = prob × odds - 1）
        """
        ev = {}
        for combination in probs:
            if combination in odds:
                ev[combination] = probs[combination] * odds[combination] - 1
            else:
                ev[combination] = 0
        return ev

    def get_positive_ev_bets(self, probs: Dict[str, float],
                             odds: Dict[str, float],
                             min_ev: float = 0.1,
                             min_prob: float = 0.01) -> List[Tuple[str, float, float, float]]:
        """
        プラス期待値の買い目を取得

        Args:
            probs: 三連単確率
            odds: 三連単オッズ
            min_ev: 最小期待値
            min_prob: 最小確率

        Returns:
            [(combination, prob, odds, ev), ...]
        """
        ev = self.calculate_ev(probs, odds)

        positive_bets = []
        for combination, ev_value in ev.items():
            if ev_value >= min_ev and probs.get(combination, 0) >= min_prob:
                positive_bets.append((
                    combination,
                    probs[combination],
                    odds.get(combination, 0),
                    ev_value
                ))

        # EVの高い順にソート
        positive_bets.sort(key=lambda x: x[3], reverse=True)

        return positive_bets


class NaiveTrifectaCalculator:
    """
    ナイーブ法による三連単確率計算（比較用）

    1着確率から2着・3着を按分で推定する従来方式
    """

    @staticmethod
    def calculate(first_probs: np.ndarray) -> Dict[str, float]:
        """
        1着確率から三連単確率を計算

        P(i-j-k) = P(1st=i) × [P(1st=j) / Σ_not_i P(1st)] × [P(1st=k) / Σ_not_i,j P(1st)]
        """
        trifecta_probs = {}

        for i in range(6):
            p1 = first_probs[i]

            # 残り5艇の1着確率の合計
            remaining_for_2nd = sum(first_probs[j] for j in range(6) if j != i)

            for j in range(6):
                if j == i:
                    continue

                p2 = first_probs[j] / remaining_for_2nd if remaining_for_2nd > 0 else 0

                # 残り4艇の1着確率の合計
                remaining_for_3rd = sum(first_probs[k] for k in range(6) if k != i and k != j)

                for k in range(6):
                    if k == i or k == j:
                        continue

                    p3 = first_probs[k] / remaining_for_3rd if remaining_for_3rd > 0 else 0

                    prob = p1 * p2 * p3
                    combination = f"{i+1}-{j+1}-{k+1}"
                    trifecta_probs[combination] = prob

        return trifecta_probs


def calculate_trio_from_trifecta(trifecta_probs: Dict[str, float]) -> Dict[str, float]:
    """
    三連単確率から三連複確率を計算（スタンドアロン関数）

    三連複「1-2-3」= 三連単の6パターンを合計
    （1-2-3, 1-3-2, 2-1-3, 2-3-1, 3-1-2, 3-2-1）

    Args:
        trifecta_probs: 三連単確率（120通り）

    Returns:
        三連複確率（20通り）
    """
    trio_probs = {}

    for combo, prob in trifecta_probs.items():
        parts = combo.split('-')
        # ソートして順不同のキーを作成
        sorted_parts = sorted(parts, key=int)
        trio_key = '-'.join(sorted_parts)

        if trio_key not in trio_probs:
            trio_probs[trio_key] = 0
        trio_probs[trio_key] += prob

    return trio_probs


def get_top_trio(trifecta_probs: Dict[str, float], top_n: int = 10) -> List[Tuple[str, float]]:
    """三連複の上位N件を取得"""
    trio_probs = calculate_trio_from_trifecta(trifecta_probs)
    sorted_probs = sorted(trio_probs.items(), key=lambda x: x[1], reverse=True)
    return sorted_probs[:top_n]


def calculate_exacta_from_trifecta(trifecta_probs: Dict[str, float]) -> Dict[str, float]:
    """
    三連単確率から2連単確率を計算

    2連単「1-2」= 三連単で1着=1, 2着=2の全パターン合計
    （1-2-3, 1-2-4, 1-2-5, 1-2-6の4通り）

    Args:
        trifecta_probs: 三連単確率（120通り）

    Returns:
        2連単確率（30通り）
    """
    exacta_probs = {}

    for combo, prob in trifecta_probs.items():
        parts = combo.split('-')
        # 1着-2着のみ抽出
        exacta_key = f"{parts[0]}-{parts[1]}"

        if exacta_key not in exacta_probs:
            exacta_probs[exacta_key] = 0
        exacta_probs[exacta_key] += prob

    return exacta_probs


def get_top_exacta(trifecta_probs: Dict[str, float], top_n: int = 10) -> List[Tuple[str, float]]:
    """2連単の上位N件を取得"""
    exacta_probs = calculate_exacta_from_trifecta(trifecta_probs)
    sorted_probs = sorted(exacta_probs.items(), key=lambda x: x[1], reverse=True)
    return sorted_probs[:top_n]


def calculate_quinella_from_trifecta(trifecta_probs: Dict[str, float]) -> Dict[str, float]:
    """
    三連単確率から2連複確率を計算

    2連複「1-2」= 2連単「1-2」+「2-1」の合計

    Args:
        trifecta_probs: 三連単確率（120通り）

    Returns:
        2連複確率（15通り）
    """
    exacta_probs = calculate_exacta_from_trifecta(trifecta_probs)
    quinella_probs = {}

    for combo, prob in exacta_probs.items():
        parts = combo.split('-')
        # ソートして順不同のキーを作成
        sorted_parts = sorted(parts, key=int)
        quinella_key = '-'.join(sorted_parts)

        if quinella_key not in quinella_probs:
            quinella_probs[quinella_key] = 0
        quinella_probs[quinella_key] += prob

    return quinella_probs


def get_top_quinella(trifecta_probs: Dict[str, float], top_n: int = 10) -> List[Tuple[str, float]]:
    """2連複の上位N件を取得"""
    quinella_probs = calculate_quinella_from_trifecta(trifecta_probs)
    sorted_probs = sorted(quinella_probs.items(), key=lambda x: x[1], reverse=True)
    return sorted_probs[:top_n]
