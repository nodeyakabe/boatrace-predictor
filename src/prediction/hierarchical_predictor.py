"""
階層的確率モデル統合予測パイプライン
Phase 3-4: 条件付き確率モデルと既存システムの統合

特徴量生成 → Stage1/2/3予測 → 三連単確率計算 → 買い目推奨
"""
import os
import sys
import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import json

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.features.feature_transforms import FeatureTransformer, RaceRelativeFeatureBuilder
from src.prediction.trifecta_calculator import TrifectaCalculator, NaiveTrifectaCalculator


class HierarchicalPredictor:
    """
    階層的確率モデル統合予測クラス

    1. 特徴量生成（相対特徴量含む）
    2. Stage1/2/3モデルによる確率予測
    3. 三連単確率計算
    4. 期待値計算・買い目推奨
    """

    def __init__(self, db_path: str, model_dir: str = 'models', use_v2: bool = False):
        self.db_path = db_path
        self.model_dir = model_dir
        self.use_v2 = use_v2

        self.feature_transformer = FeatureTransformer()
        self.feature_builder = RaceRelativeFeatureBuilder()
        self.trifecta_calculator = TrifectaCalculator(model_dir, model_name='conditional', use_v2=use_v2)

        self._model_loaded = False

    def load_models(self):
        """モデルを読み込み"""
        if self._model_loaded:
            return

        try:
            self.trifecta_calculator.load_models()
            self._model_loaded = True
            print("条件付きモデルを読み込みました")
        except Exception as e:
            print(f"モデル読み込みエラー（フォールバックモード）: {e}")
            self._model_loaded = False

    def predict_race(self, race_id: str,
                     use_conditional_model: bool = True) -> Dict:
        """
        レースの予測を行う

        Args:
            race_id: レースID
            use_conditional_model: 条件付きモデルを使用するか

        Returns:
            予測結果（三連単確率、推奨買い目など）
        """
        # 特徴量を取得
        features_df = self._get_race_features(race_id)

        if features_df is None or len(features_df) != 6:
            return {'error': f'レースデータ取得失敗: {race_id}'}

        # モデル読み込み
        if use_conditional_model and not self._model_loaded:
            self.load_models()

        # 三連単確率を計算
        if use_conditional_model and self._model_loaded:
            trifecta_probs = self.trifecta_calculator.calculate(features_df)
        else:
            # フォールバック: 従来のナイーブ法
            first_probs = self._calculate_naive_first_probs(features_df)
            trifecta_probs = NaiveTrifectaCalculator.calculate(first_probs)

        # 上位組み合わせを取得
        top_combinations = self.trifecta_calculator.get_top_combinations(trifecta_probs, top_n=20)

        # オッズ情報があれば期待値計算
        odds = self._get_odds(race_id)
        positive_ev_bets = []
        if odds:
            positive_ev_bets = self.trifecta_calculator.get_positive_ev_bets(
                trifecta_probs, odds, min_ev=0.1, min_prob=0.005
            )

        # 各艇の順位予測確率
        rank_probs = self._calculate_rank_probs(trifecta_probs)

        return {
            'race_id': race_id,
            'trifecta_probs': trifecta_probs,
            'top_combinations': top_combinations,
            'positive_ev_bets': positive_ev_bets,
            'rank_probs': rank_probs,
            'model_used': 'conditional' if (use_conditional_model and self._model_loaded) else 'naive',
            'predicted_at': datetime.now().isoformat(),
        }

    def predict_race_from_features(self, features_df: pd.DataFrame,
                                    use_conditional_model: bool = True) -> Dict:
        """
        特徴量DataFrameから予測を行う

        Args:
            features_df: 6艇分の特徴量DataFrame
            use_conditional_model: 条件付きモデルを使用するか

        Returns:
            予測結果
        """
        if len(features_df) != 6:
            return {'error': f'6艇分のデータが必要です（現在: {len(features_df)}艇）'}

        # 相対特徴量を追加
        features_df = self.feature_builder.build_training_data(features_df)

        # モデル読み込み
        if use_conditional_model and not self._model_loaded:
            self.load_models()

        # 三連単確率を計算
        if use_conditional_model and self._model_loaded:
            trifecta_probs = self.trifecta_calculator.calculate(features_df)
        else:
            first_probs = self._calculate_naive_first_probs(features_df)
            trifecta_probs = NaiveTrifectaCalculator.calculate(first_probs)

        top_combinations = self.trifecta_calculator.get_top_combinations(trifecta_probs, top_n=20)
        rank_probs = self._calculate_rank_probs(trifecta_probs)

        return {
            'trifecta_probs': trifecta_probs,
            'top_combinations': top_combinations,
            'rank_probs': rank_probs,
            'model_used': 'conditional' if (use_conditional_model and self._model_loaded) else 'naive',
            'predicted_at': datetime.now().isoformat(),
        }

    def _get_race_features(self, race_id: str) -> Optional[pd.DataFrame]:
        """レースの特徴量を取得"""
        query = """
            SELECT
                e.pit_number,
                e.racer_number,
                e.win_rate,
                e.second_rate,
                e.motor_second_rate,
                e.boat_second_rate,
                rd.exhibition_time,
                rd.st_time as avg_st,
                COALESCE(rd.actual_course, e.pit_number) as actual_course,
                e.motor_number,
                e.boat_number
            FROM entries e
            LEFT JOIN race_details rd
                ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        """

        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn, params=(race_id,))

            if len(df) == 0:
                return None

            # race_idを追加（相対特徴量計算用）
            df['race_id'] = race_id

            # 相対特徴量を追加
            df = self.feature_builder.build_training_data(df)

            return df

        except Exception as e:
            print(f"特徴量取得エラー: {e}")
            return None

    def _get_odds(self, race_id: str) -> Optional[Dict[str, float]]:
        """オッズ情報を取得"""
        query = """
            SELECT combination, odds
            FROM odds
            WHERE race_id = ? AND bet_type = 'trifecta'
        """

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, (race_id,))
                rows = cursor.fetchall()

            if rows:
                return {row[0]: row[1] for row in rows}
            return None

        except Exception:
            return None

    def _calculate_naive_first_probs(self, features_df: pd.DataFrame) -> np.ndarray:
        """ナイーブ法で1着確率を計算"""
        # 勝率ベースの簡易計算
        win_rates = features_df['win_rate'].fillna(10).values

        # コース補正
        course_bonus = np.array([1.5, 1.2, 1.0, 0.9, 0.8, 0.7])
        actual_courses = features_df['actual_course'].fillna(features_df['pit_number']).values.astype(int)

        # コース別補正を適用
        adjusted_rates = win_rates.copy()
        for i, course in enumerate(actual_courses):
            if 1 <= course <= 6:
                adjusted_rates[i] *= course_bonus[course - 1]

        # 正規化
        probs = adjusted_rates / adjusted_rates.sum()

        return probs

    def _calculate_rank_probs(self, trifecta_probs: Dict[str, float]) -> Dict[int, Dict[int, float]]:
        """
        各艇の各順位になる確率を計算

        Returns:
            {pit_number: {rank: prob}}
        """
        rank_probs = {i: {1: 0, 2: 0, 3: 0} for i in range(1, 7)}

        for combination, prob in trifecta_probs.items():
            pits = [int(p) for p in combination.split('-')]
            rank_probs[pits[0]][1] += prob
            rank_probs[pits[1]][2] += prob
            rank_probs[pits[2]][3] += prob

        return rank_probs

    def get_recommended_bets(self, race_id: str,
                             budget: float = 10000,
                             max_bets: int = 5,
                             min_ev: float = 0.15) -> List[Dict]:
        """
        推奨買い目を取得

        Args:
            race_id: レースID
            budget: 予算
            max_bets: 最大買い目数
            min_ev: 最小期待値

        Returns:
            推奨買い目リスト
        """
        prediction = self.predict_race(race_id)

        if 'error' in prediction:
            return []

        positive_ev_bets = prediction.get('positive_ev_bets', [])

        if not positive_ev_bets:
            # 期待値計算できない場合は確率上位を返す
            top_combinations = prediction.get('top_combinations', [])[:max_bets]
            return [
                {
                    'combination': comb,
                    'prob': prob,
                    'odds': None,
                    'ev': None,
                    'amount': budget // max_bets
                }
                for comb, prob in top_combinations
            ]

        # Kelly基準による配分
        recommended = []
        remaining_budget = budget

        for comb, prob, odds, ev in positive_ev_bets[:max_bets]:
            if ev < min_ev:
                continue

            # Kelly基準: f* = (p * b - q) / b
            b = odds - 1
            q = 1 - prob
            kelly_fraction = max(0, (prob * b - q) / b) if b > 0 else 0

            # 控えめに設定（Kelly / 4）
            fraction = kelly_fraction / 4

            amount = min(remaining_budget * fraction, remaining_budget / len(positive_ev_bets))
            amount = round(amount / 100) * 100  # 100円単位

            if amount >= 100:
                recommended.append({
                    'combination': comb,
                    'prob': prob,
                    'odds': odds,
                    'ev': ev,
                    'amount': int(amount)
                })
                remaining_budget -= amount

        return recommended


class HierarchicalPredictionResult:
    """階層的予測結果を保持するクラス"""

    def __init__(self, race_id: str, prediction: Dict):
        self.race_id = race_id
        self.prediction = prediction
        self.trifecta_probs = prediction.get('trifecta_probs', {})
        self.rank_probs = prediction.get('rank_probs', {})
        self.model_used = prediction.get('model_used', 'unknown')

    def get_predicted_order(self) -> List[int]:
        """予測順位（確率最大の順序）を取得"""
        if not self.rank_probs:
            return [1, 2, 3, 4, 5, 6]

        # 1着確率でソート
        first_probs = [(pit, probs.get(1, 0)) for pit, probs in self.rank_probs.items()]
        sorted_by_first = sorted(first_probs, key=lambda x: x[1], reverse=True)

        return [pit for pit, _ in sorted_by_first]

    def get_top_trifecta(self, n: int = 1) -> List[str]:
        """上位N件の三連単を取得"""
        sorted_probs = sorted(self.trifecta_probs.items(), key=lambda x: x[1], reverse=True)
        return [comb for comb, _ in sorted_probs[:n]]

    def get_confidence(self) -> float:
        """予測の信頼度を取得（0-1）"""
        if not self.trifecta_probs:
            return 0

        # 上位組み合わせの確率集中度
        sorted_probs = sorted(self.trifecta_probs.values(), reverse=True)
        top5_prob = sum(sorted_probs[:5])

        # 1着確率の集中度
        first_probs = [probs.get(1, 0) for probs in self.rank_probs.values()]
        first_entropy = -sum(p * np.log(p + 1e-10) for p in first_probs if p > 0)
        max_entropy = np.log(6)

        # 信頼度 = 確率集中度と逆エントロピーの組み合わせ
        concentration = top5_prob
        diversity = 1 - (first_entropy / max_entropy)

        return 0.6 * concentration + 0.4 * diversity

    def to_dict(self) -> Dict:
        """辞書形式に変換"""
        return {
            'race_id': self.race_id,
            'predicted_order': self.get_predicted_order(),
            'top_trifecta': self.get_top_trifecta(5),
            'confidence': self.get_confidence(),
            'model_used': self.model_used,
            'rank_probs': self.rank_probs,
        }


def integrate_with_race_predictor(race_predictor, hierarchical_predictor: HierarchicalPredictor):
    """
    既存のRacePredictorと統合するためのラッパー

    Args:
        race_predictor: 既存のRacePredictorインスタンス
        hierarchical_predictor: HierarchicalPredictorインスタンス

    Returns:
        拡張されたpredict_race関数
    """

    original_predict = race_predictor.predict_race

    def enhanced_predict_race(race_id: str, **kwargs) -> Dict:
        # 元の予測を実行
        original_result = original_predict(race_id, **kwargs)

        # 条件付きモデルによる三連単予測を追加
        try:
            hierarchical_result = hierarchical_predictor.predict_race(race_id)

            if 'error' not in hierarchical_result:
                original_result['hierarchical_prediction'] = hierarchical_result
                original_result['trifecta_probs'] = hierarchical_result.get('trifecta_probs', {})
                original_result['recommended_bets'] = hierarchical_predictor.get_recommended_bets(race_id)

        except Exception as e:
            print(f"階層的予測エラー: {e}")

        return original_result

    return enhanced_predict_race
