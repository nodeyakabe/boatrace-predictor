"""
2着予測モデル
Phase 2: 1着確定後の条件付き2着予測
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
import joblib
import json


class SecondPlacePredictor:
    """
    2着予測クラス（条件付き）

    1着艇が確定した前提で、残り5艇から2着を予測
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

        model_path = os.path.join(self.model_dir, 'second_model.joblib')
        meta_path = os.path.join(self.model_dir, 'second_model_meta.json')

        if not os.path.exists(model_path):
            print(f"2着予測モデルが見つかりません: {model_path}")
            return False

        try:
            self.model = joblib.load(model_path)
            print(f"2着予測モデル読み込み: {model_path}")

            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                self.feature_names = meta.get('feature_names', [])

            self._loaded = True
            return True

        except Exception as e:
            print(f"モデル読み込みエラー: {e}")
            return False

    def predict_second_probs(self, features_df: pd.DataFrame,
                              winner_idx: int) -> np.ndarray:
        """
        2着確率を予測

        Args:
            features_df: 6艇分の特徴量DataFrame
            winner_idx: 1着艇のインデックス（0-5）

        Returns:
            各艇の2着確率（長さ6、winner_idxは0）
        """
        if not self._loaded:
            if not self.load_model():
                return self._default_second_probs(features_df, winner_idx)

        probs = np.zeros(6)

        # 5艇分の予測
        for i in range(6):
            if i == winner_idx:
                continue

            # 特徴量を準備
            candidate_features = self._prepare_candidate_features(
                features_df, i, winner_idx
            )

            if self.model is not None and len(candidate_features) > 0:
                prob = self.model.predict_proba([candidate_features])[:, 1]
                probs[i] = prob[0]

        # 正規化
        total = probs.sum()
        if total > 0:
            probs = probs / total

        return probs

    def _prepare_candidate_features(self, df: pd.DataFrame,
                                      candidate_idx: int,
                                      winner_idx: int) -> np.ndarray:
        """候補艇の特徴量を準備"""
        candidate = df.iloc[candidate_idx]
        winner = df.iloc[winner_idx]

        features = {}

        # 候補艇の基本特徴量
        for col in candidate.index:
            if col not in ['race_id', 'pit_number', 'race_date', 'venue_code',
                          'racer_number', 'rank', 'is_second']:
                try:
                    features[col] = float(candidate[col]) if pd.notna(candidate[col]) else 0.0
                except (TypeError, ValueError):
                    pass

        # 1着艇の特徴量
        for col in ['st_time', 'exhibition_time', 'win_rate', 'actual_course']:
            if col in winner.index:
                try:
                    features[f'winner_{col}'] = float(winner[col]) if pd.notna(winner[col]) else 0.0
                except (TypeError, ValueError):
                    pass

        # 相対特徴量
        if 'st_time' in candidate.index and 'st_time' in winner.index:
            try:
                cand_st = float(candidate['st_time']) if pd.notna(candidate['st_time']) else 0.15
                win_st = float(winner['st_time']) if pd.notna(winner['st_time']) else 0.15
                features['relative_st'] = win_st - cand_st
            except (TypeError, ValueError):
                features['relative_st'] = 0.0

        # コース関連
        cand_course = candidate.get('actual_course', candidate.get('pit_number', candidate_idx + 1))
        win_course = winner.get('actual_course', winner.get('pit_number', winner_idx + 1))
        try:
            features['course_diff_from_winner'] = float(cand_course) - float(win_course)
            features['is_outside_winner'] = 1 if float(cand_course) > float(win_course) else 0
        except (TypeError, ValueError):
            features['course_diff_from_winner'] = 0.0
            features['is_outside_winner'] = 0

        # 特徴量リストに合わせて配列化
        if self.feature_names:
            result = [features.get(col, 0.0) for col in self.feature_names]
        else:
            result = list(features.values())

        return np.array(result)

    def _default_second_probs(self, features_df: pd.DataFrame,
                               winner_idx: int) -> np.ndarray:
        """モデルがない場合のデフォルト確率"""
        probs = np.zeros(6)

        # 勝率ベースで按分
        for i, row in features_df.iterrows():
            if i == winner_idx:
                continue

            win_rate = row.get('win_rate', 10) or 10
            second_rate = row.get('second_rate', 15) or win_rate * 0.8

            # コース補正
            course = row.get('actual_course', row.get('pit_number', i + 1))
            winner_course = features_df.iloc[winner_idx].get('actual_course',
                features_df.iloc[winner_idx].get('pit_number', winner_idx + 1))

            if course > winner_course:
                # 外コースは差しやすい
                probs[i] = second_rate * 1.2
            else:
                probs[i] = second_rate

        # 正規化
        total = probs.sum()
        if total > 0:
            probs = probs / total

        return probs

    def predict_top_candidates(self, features_df: pd.DataFrame,
                                winner_idx: int,
                                top_n: int = 3) -> List[Dict]:
        """
        上位N件の2着候補を取得

        Args:
            features_df: 6艇分の特徴量DataFrame
            winner_idx: 1着艇のインデックス
            top_n: 取得する候補数

        Returns:
            [{pit_number, probability}, ...]
        """
        probs = self.predict_second_probs(features_df, winner_idx)
        pit_numbers = features_df['pit_number'].values if 'pit_number' in features_df.columns else range(1, 7)

        candidates = []
        for i, prob in enumerate(probs):
            if i != winner_idx and prob > 0:
                candidates.append({
                    'pit_number': int(pit_numbers[i]),
                    'probability': float(prob),
                })

        candidates.sort(key=lambda x: x['probability'], reverse=True)
        return candidates[:top_n]
