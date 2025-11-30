"""
三連単生成
Phase 6: 統合予測エンジン
"""
import os
import sys
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)


class EnhancedTrifectaGenerator:
    """
    強化版三連単生成クラス

    全Phaseのモデルを統合して三連単予測を生成
    """

    def __init__(self, model_dir: str = 'models', db_path: str = None):
        self.model_dir = model_dir
        self.db_path = db_path

        # 各モジュールを遅延読み込み
        self._entry_predictor = None
        self._second_predictor = None
        self._third_predictor = None
        self._style_embedding = None
        self._st_model = None
        self._model_selector = None
        self._probability_calculator = None

        self._initialized = False

    def initialize(self) -> None:
        """全モジュールを初期化"""
        if self._initialized:
            return

        print("三連単生成エンジン初期化中...")

        # Phase 1: 進入予測
        try:
            from src.entry_model.entry_predictor import EntryPredictor
            self._entry_predictor = EntryPredictor(self.model_dir)
            self._entry_predictor.load_model()
        except Exception as e:
            print(f"進入予測モデル初期化スキップ: {e}")

        # Phase 2: 2着・3着予測
        try:
            from src.second_model.second_predictor import SecondPlacePredictor
            from src.third_model.third_predictor import ThirdPlacePredictor
            self._second_predictor = SecondPlacePredictor(self.model_dir)
            self._third_predictor = ThirdPlacePredictor(self.model_dir)
        except Exception as e:
            print(f"条件付き着順モデル初期化スキップ: {e}")

        # Phase 3: 走法embedding
        try:
            from src.style_cluster.style_embedding import StyleEmbedding
            self._style_embedding = StyleEmbedding(self.model_dir)
            self._style_embedding.load()
        except Exception as e:
            print(f"走法embedding初期化スキップ: {e}")

        # Phase 4: ST embedding
        try:
            from src.st_sequence.st_lstm_model import STSequenceModel
            self._st_model = STSequenceModel(self.model_dir)
            self._st_model.load()
        except Exception as e:
            print(f"ST LSTM初期化スキップ: {e}")

        # Phase 5: モデルセレクター
        try:
            from src.race_type_model.model_selector import ModelSelector
            self._model_selector = ModelSelector(self.model_dir)
            self._model_selector.load()
        except Exception as e:
            print(f"モデルセレクター初期化スキップ: {e}")

        # 確率計算器
        from src.tricast_engine.probability_chain import ProbabilityChainCalculator
        self._probability_calculator = ProbabilityChainCalculator()

        self._initialized = True
        print("三連単生成エンジン初期化完了")

    def generate(self, race_features: pd.DataFrame,
                 venue_code: str,
                 race_date: str = None,
                 weather_data: Dict = None) -> Dict:
        """
        三連単予測を生成

        Args:
            race_features: 6艇分の特徴量DataFrame
            venue_code: 会場コード
            race_date: レース日
            weather_data: 気象データ

        Returns:
            予測結果
        """
        if not self._initialized:
            self.initialize()

        if len(race_features) != 6:
            return {'error': f'6艇分のデータが必要です（現在: {len(race_features)}艇）'}

        result = {
            'venue_code': venue_code,
            'race_date': race_date,
            'generated_at': datetime.now().isoformat(),
            'components_used': [],
        }

        # === Phase 1: 進入予測 ===
        entry_probs = None
        if self._entry_predictor is not None:
            try:
                entry_probs = self._entry_predictor.predict_entry_probs(race_features)
                entry_distribution = self._entry_predictor.predict_entry_distribution(race_features)
                result['entry_prediction'] = entry_distribution
                result['components_used'].append('entry')
            except Exception as e:
                print(f"進入予測エラー: {e}")

        # === Phase 3: 走法embedding ===
        features_df = race_features.copy()
        if self._style_embedding is not None:
            try:
                features_df = self._style_embedding.add_embedding_features(
                    features_df, 'racer_number', 'style_emb'
                )
                result['components_used'].append('style')
            except Exception as e:
                print(f"走法embedding追加エラー: {e}")

        # === Phase 5: レースタイプ分析 ===
        race_analysis = None
        if self._model_selector is not None:
            try:
                race_analysis = self._model_selector.get_race_analysis(venue_code, weather_data)
                result['race_analysis'] = race_analysis
                result['components_used'].append('type_model')
            except Exception as e:
                print(f"レース分析エラー: {e}")

        # === 1着確率計算 ===
        first_probs = self._calculate_first_probs(features_df, venue_code, weather_data)
        self._probability_calculator.set_first_probs(first_probs)

        # === 2着・3着確率計算（条件付き）===
        for i in range(6):
            # 2着確率
            second_probs = self._calculate_second_probs(features_df, i)
            self._probability_calculator.set_second_probs(i, second_probs)

            for j in range(6):
                if j == i:
                    continue

                # 3着確率
                third_probs = self._calculate_third_probs(features_df, i, j)
                self._probability_calculator.set_third_probs(i, j, third_probs)

        # === 三連単確率計算 ===
        if entry_probs is not None:
            trifecta_probs = self._probability_calculator.calculate_with_entry_adjustment(entry_probs)
        else:
            trifecta_probs = self._probability_calculator.calculate_all_trifecta_probs()

        # === 結果整理 ===
        result['trifecta_probs'] = trifecta_probs

        # 上位10件
        sorted_probs = sorted(trifecta_probs.items(), key=lambda x: x[1], reverse=True)
        result['top10'] = [
            {'combination': combo, 'probability': prob}
            for combo, prob in sorted_probs[:10]
        ]

        # 各艇の着順確率
        result['rank_probs'] = self._calculate_rank_probs(trifecta_probs)

        # 予測順位
        result['predicted_order'] = self._get_predicted_order(result['rank_probs'])

        return result

    def _calculate_first_probs(self, features_df: pd.DataFrame,
                                venue_code: str,
                                weather_data: Dict) -> np.ndarray:
        """1着確率を計算"""
        if self._model_selector is not None:
            try:
                probs = self._model_selector.predict_with_best_model(
                    features_df, venue_code, 'stage1', weather_data
                )
                return probs / probs.sum()
            except Exception:
                pass

        # フォールバック: 勝率ベース
        win_rates = features_df['win_rate'].fillna(10).values
        return win_rates / win_rates.sum()

    def _calculate_second_probs(self, features_df: pd.DataFrame,
                                 first_idx: int) -> np.ndarray:
        """2着確率を計算（1着条件付き）"""
        if self._second_predictor is not None:
            try:
                return self._second_predictor.predict_second_probs(features_df, first_idx)
            except Exception:
                pass

        # フォールバック: 勝率ベース
        probs = np.zeros(6)
        win_rates = features_df['win_rate'].fillna(10).values

        for j in range(6):
            if j != first_idx:
                probs[j] = win_rates[j]

        total = probs.sum()
        return probs / total if total > 0 else probs

    def _calculate_third_probs(self, features_df: pd.DataFrame,
                                first_idx: int,
                                second_idx: int) -> np.ndarray:
        """3着確率を計算（1着・2着条件付き）"""
        if self._third_predictor is not None:
            try:
                return self._third_predictor.predict_third_probs(features_df, first_idx, second_idx)
            except Exception:
                pass

        # フォールバック: 勝率ベース
        probs = np.zeros(6)
        win_rates = features_df['win_rate'].fillna(10).values

        for k in range(6):
            if k != first_idx and k != second_idx:
                probs[k] = win_rates[k]

        total = probs.sum()
        return probs / total if total > 0 else probs

    def _calculate_rank_probs(self, trifecta_probs: Dict[str, float]) -> Dict[int, Dict[int, float]]:
        """各艇の着順確率を計算"""
        rank_probs = {i: {1: 0.0, 2: 0.0, 3: 0.0} for i in range(1, 7)}

        for combination, prob in trifecta_probs.items():
            pits = [int(p) for p in combination.split('-')]
            rank_probs[pits[0]][1] += prob
            rank_probs[pits[1]][2] += prob
            rank_probs[pits[2]][3] += prob

        return rank_probs

    def _get_predicted_order(self, rank_probs: Dict[int, Dict[int, float]]) -> List[int]:
        """予測順位を取得"""
        first_probs = [(pit, probs[1]) for pit, probs in rank_probs.items()]
        sorted_by_first = sorted(first_probs, key=lambda x: x[1], reverse=True)
        return [pit for pit, _ in sorted_by_first]

    def get_positive_ev_bets(self, trifecta_probs: Dict[str, float],
                              odds: Dict[str, float],
                              min_ev: float = 0.1,
                              min_prob: float = 0.005) -> List[Dict]:
        """
        プラス期待値の買い目を取得

        Args:
            trifecta_probs: 三連単確率
            odds: 三連単オッズ
            min_ev: 最小期待値
            min_prob: 最小確率

        Returns:
            プラス期待値の買い目リスト
        """
        positive_bets = []

        for combination, prob in trifecta_probs.items():
            if combination in odds:
                odd = odds[combination]
                ev = prob * odd - 1

                if ev >= min_ev and prob >= min_prob:
                    positive_bets.append({
                        'combination': combination,
                        'probability': prob,
                        'odds': odd,
                        'expected_value': ev,
                    })

        # EVの高い順にソート
        positive_bets.sort(key=lambda x: x['expected_value'], reverse=True)

        return positive_bets
