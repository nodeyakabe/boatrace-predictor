"""
確率チェーン計算
Phase 6: P(1着=A) × P(2着=B | A) × P(3着=C | A,B) の計算
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from itertools import permutations


class ProbabilityChainCalculator:
    """
    確率チェーン計算クラス

    階層的条件付き確率を用いて三連単確率を計算

    計算式:
    P(三連単 A-B-C) = P(1着=A) × P(2着=B | 1着=A) × P(3着=C | 1着=A, 2着=B)
    """

    def __init__(self):
        self.first_probs = None
        self.second_probs = None  # {first_idx: probs}
        self.third_probs = None   # {(first_idx, second_idx): probs}

    def set_first_probs(self, probs: np.ndarray) -> None:
        """
        1着確率を設定

        Args:
            probs: 各艇の1着確率（長さ6）
        """
        if len(probs) != 6:
            raise ValueError("6艇分の確率が必要です")

        # 正規化
        total = probs.sum()
        if total > 0:
            probs = probs / total

        self.first_probs = probs

    def set_second_probs(self, first_idx: int, probs: np.ndarray) -> None:
        """
        2着確率を設定（1着条件付き）

        Args:
            first_idx: 1着艇のインデックス
            probs: 各艇の2着確率（長さ6、first_idxは0）
        """
        if self.second_probs is None:
            self.second_probs = {}

        # 正規化（1着艇を除く）
        probs = probs.copy()
        probs[first_idx] = 0
        total = probs.sum()
        if total > 0:
            probs = probs / total

        self.second_probs[first_idx] = probs

    def set_third_probs(self, first_idx: int, second_idx: int, probs: np.ndarray) -> None:
        """
        3着確率を設定（1着・2着条件付き）

        Args:
            first_idx: 1着艇のインデックス
            second_idx: 2着艇のインデックス
            probs: 各艇の3着確率（長さ6、first/second_idxは0）
        """
        if self.third_probs is None:
            self.third_probs = {}

        # 正規化（1着・2着艇を除く）
        probs = probs.copy()
        probs[first_idx] = 0
        probs[second_idx] = 0
        total = probs.sum()
        if total > 0:
            probs = probs / total

        self.third_probs[(first_idx, second_idx)] = probs

    def calculate_all_trifecta_probs(self) -> Dict[str, float]:
        """
        全720通りの三連単確率を計算

        Returns:
            {'1-2-3': prob, ...} 形式の確率辞書
        """
        if self.first_probs is None:
            raise ValueError("1着確率が設定されていません")

        trifecta_probs = {}

        for i in range(6):
            p_first = self.first_probs[i]

            if p_first <= 0:
                continue

            # 2着確率
            if self.second_probs and i in self.second_probs:
                second_probs = self.second_probs[i]
            else:
                # フォールバック: 残り5艇で按分
                second_probs = self._fallback_second_probs(i)

            for j in range(6):
                if j == i:
                    continue

                p_second = second_probs[j]
                if p_second <= 0:
                    continue

                # 3着確率
                if self.third_probs and (i, j) in self.third_probs:
                    third_probs = self.third_probs[(i, j)]
                else:
                    # フォールバック: 残り4艇で按分
                    third_probs = self._fallback_third_probs(i, j)

                for k in range(6):
                    if k == i or k == j:
                        continue

                    p_third = third_probs[k]
                    if p_third <= 0:
                        continue

                    # 三連単確率
                    prob = p_first * p_second * p_third

                    # ピット番号（1始まり）で表現
                    combination = f"{i+1}-{j+1}-{k+1}"
                    trifecta_probs[combination] = float(prob)

        # 正規化（合計が1になるように）
        total = sum(trifecta_probs.values())
        if total > 0:
            trifecta_probs = {k: v / total for k, v in trifecta_probs.items()}

        return trifecta_probs

    def _fallback_second_probs(self, first_idx: int) -> np.ndarray:
        """フォールバック: 1着確率から2着確率を推定"""
        probs = np.zeros(6)

        if self.first_probs is not None:
            # 1着確率を按分
            for j in range(6):
                if j != first_idx:
                    probs[j] = self.first_probs[j]

        total = probs.sum()
        if total > 0:
            probs = probs / total

        return probs

    def _fallback_third_probs(self, first_idx: int, second_idx: int) -> np.ndarray:
        """フォールバック: 1着確率から3着確率を推定"""
        probs = np.zeros(6)

        if self.first_probs is not None:
            for k in range(6):
                if k != first_idx and k != second_idx:
                    probs[k] = self.first_probs[k]

        total = probs.sum()
        if total > 0:
            probs = probs / total

        return probs

    def calculate_with_entry_adjustment(self,
                                         entry_probs: np.ndarray,
                                         weight: float = 0.3) -> Dict[str, float]:
        """
        進入予測を考慮した三連単確率を計算

        Args:
            entry_probs: 進入確率行列 (6, 6)
            weight: 進入調整の重み

        Returns:
            調整後の三連単確率
        """
        # 進入による1着確率の調整
        if self.first_probs is not None and entry_probs is not None:
            # 各艇がインコースに入る確率で重み付け
            in_course_probs = entry_probs[:, 0] + entry_probs[:, 1] * 0.5  # 1コース + 2コース×0.5

            adjusted_first = self.first_probs * (1 - weight) + in_course_probs * weight
            adjusted_first = adjusted_first / adjusted_first.sum()

            # 元の確率を一時保存
            original_first = self.first_probs
            self.first_probs = adjusted_first

            result = self.calculate_all_trifecta_probs()

            # 元に戻す
            self.first_probs = original_first

            return result

        return self.calculate_all_trifecta_probs()


class IntegratedProbabilityCalculator:
    """
    統合確率計算クラス

    Phase 1-5の全モデルを統合して三連単確率を計算
    """

    def __init__(self, model_dir: str = 'models'):
        self.model_dir = model_dir
        self.chain_calculator = ProbabilityChainCalculator()

        # 各モデルをロード（遅延読み込み）
        self._entry_predictor = None
        self._style_embedding = None
        self._st_model = None
        self._model_selector = None

    @property
    def entry_predictor(self):
        if self._entry_predictor is None:
            from src.entry_model.entry_predictor import EntryPredictor
            self._entry_predictor = EntryPredictor(self.model_dir)
        return self._entry_predictor

    @property
    def style_embedding(self):
        if self._style_embedding is None:
            from src.style_cluster.style_embedding import StyleEmbedding
            self._style_embedding = StyleEmbedding(self.model_dir)
        return self._style_embedding

    @property
    def st_model(self):
        if self._st_model is None:
            from src.st_sequence.st_lstm_model import STSequenceModel
            self._st_model = STSequenceModel(self.model_dir)
        return self._st_model

    @property
    def model_selector(self):
        if self._model_selector is None:
            from src.race_type_model.model_selector import ModelSelector
            self._model_selector = ModelSelector(self.model_dir)
        return self._model_selector

    def calculate_integrated_probs(self,
                                    race_features: pd.DataFrame,
                                    venue_code: str,
                                    weather_data: Dict = None,
                                    use_entry: bool = True,
                                    use_style: bool = True,
                                    use_st: bool = True,
                                    use_type_model: bool = True) -> Dict[str, float]:
        """
        全モデルを統合して三連単確率を計算

        Args:
            race_features: 6艇分の特徴量
            venue_code: 会場コード
            weather_data: 気象データ
            use_entry: 進入予測を使用
            use_style: 走法embeddingを使用
            use_st: ST embeddingを使用
            use_type_model: タイプ別モデルを使用

        Returns:
            三連単確率
        """
        features_df = race_features.copy()

        # 1. 進入予測を反映
        entry_probs = None
        if use_entry:
            try:
                entry_probs = self.entry_predictor.predict_entry_probs(features_df)
            except Exception as e:
                print(f"進入予測エラー: {e}")

        # 2. 走法embeddingを追加
        if use_style:
            try:
                features_df = self.style_embedding.add_embedding_features(
                    features_df, 'racer_number', 'style_emb'
                )
            except Exception as e:
                print(f"走法embedding追加エラー: {e}")

        # 3. モデル選択と予測
        if use_type_model:
            # 1着確率
            first_probs = self.model_selector.predict_with_best_model(
                features_df, venue_code, 'stage1', weather_data
            )
        else:
            # デフォルト: 勝率ベース
            win_rates = features_df['win_rate'].fillna(10).values
            first_probs = win_rates / win_rates.sum()

        self.chain_calculator.set_first_probs(first_probs)

        # 2着・3着確率は条件付きで計算
        for i in range(6):
            # 2着確率
            second_probs = self._calculate_conditional_second(
                features_df, i, venue_code, weather_data, use_type_model
            )
            self.chain_calculator.set_second_probs(i, second_probs)

            for j in range(6):
                if j == i:
                    continue

                # 3着確率
                third_probs = self._calculate_conditional_third(
                    features_df, i, j, venue_code, weather_data, use_type_model
                )
                self.chain_calculator.set_third_probs(i, j, third_probs)

        # 進入調整を適用
        if entry_probs is not None:
            return self.chain_calculator.calculate_with_entry_adjustment(entry_probs)

        return self.chain_calculator.calculate_all_trifecta_probs()

    def _calculate_conditional_second(self, features_df: pd.DataFrame,
                                        first_idx: int,
                                        venue_code: str,
                                        weather_data: Dict,
                                        use_type_model: bool) -> np.ndarray:
        """条件付き2着確率を計算"""
        probs = np.zeros(6)

        for j in range(6):
            if j == first_idx:
                continue

            if use_type_model:
                try:
                    candidate_df = features_df.iloc[[j]].copy()
                    pred = self.model_selector.predict_with_best_model(
                        candidate_df, venue_code, 'stage2', weather_data
                    )
                    probs[j] = pred[0]
                except:
                    probs[j] = 1.0 / 5
            else:
                probs[j] = 1.0 / 5

        # 正規化
        total = probs.sum()
        if total > 0:
            probs = probs / total

        return probs

    def _calculate_conditional_third(self, features_df: pd.DataFrame,
                                       first_idx: int,
                                       second_idx: int,
                                       venue_code: str,
                                       weather_data: Dict,
                                       use_type_model: bool) -> np.ndarray:
        """条件付き3着確率を計算"""
        probs = np.zeros(6)

        for k in range(6):
            if k == first_idx or k == second_idx:
                continue

            if use_type_model:
                try:
                    candidate_df = features_df.iloc[[k]].copy()
                    pred = self.model_selector.predict_with_best_model(
                        candidate_df, venue_code, 'stage3', weather_data
                    )
                    probs[k] = pred[0]
                except:
                    probs[k] = 1.0 / 4
            else:
                probs[k] = 1.0 / 4

        # 正規化
        total = probs.sum()
        if total > 0:
            probs = probs / total

        return probs
