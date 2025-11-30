"""
モデルセレクター
Phase 5: レース条件に応じた最適モデルの選択
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

from src.race_type_model.race_type_classifier import RaceTypeClassifier
from src.race_type_model.type_specific_models import TypeSpecificModelManager


class ModelSelector:
    """
    モデルセレクタークラス

    レース条件に応じて最適なモデルを選択
    """

    def __init__(self, model_dir: str = 'models'):
        self.model_dir = model_dir
        self.classifier = RaceTypeClassifier()
        self.type_models = TypeSpecificModelManager(model_dir)
        self.default_models = {}  # フォールバック用の汎用モデル
        self._loaded = False

    def load(self) -> bool:
        """モデルを読み込み"""
        if self._loaded:
            return True

        # タイプ別モデル
        type_loaded = self.type_models.load()

        # デフォルトモデル（条件付きモデル）のフォールバック
        self._load_default_models()

        self._loaded = True
        return type_loaded

    def _load_default_models(self) -> None:
        """デフォルトモデルを読み込み"""
        import joblib

        for stage in ['stage1', 'stage2', 'stage3']:
            model_path = os.path.join(self.model_dir, f'conditional_{stage}.joblib')
            if os.path.exists(model_path):
                try:
                    self.default_models[stage] = joblib.load(model_path)
                except Exception as e:
                    print(f"デフォルトモデル読み込みエラー ({stage}): {e}")

    def select_model(self, venue_code: str,
                     stage: str,
                     weather_data: Dict = None) -> Tuple[object, str]:
        """
        最適なモデルを選択

        Args:
            venue_code: 会場コード
            stage: ステージ（'stage1', 'stage2', 'stage3'）
            weather_data: 気象データ

        Returns:
            (モデル, 選択理由)
        """
        if not self._loaded:
            self.load()

        # レースタイプを判定
        wind_speed = weather_data.get('wind_speed') if weather_data else None
        wave_height = weather_data.get('wave_height') if weather_data else None

        race_type, confidence = self.classifier.classify_with_confidence(
            venue_code, wind_speed, wave_height
        )

        # タイプ別モデルを取得
        type_model = self.type_models.get_model(race_type, stage)

        if type_model is not None and confidence >= 0.7:
            type_name = self.classifier.get_type_config(race_type)['name']
            reason = f"{type_name}タイプモデル (信頼度: {confidence:.0%})"
            return type_model, reason

        # デフォルトモデルにフォールバック
        if stage in self.default_models:
            reason = f"汎用モデル (タイプモデル未対応または低信頼度)"
            return self.default_models[stage], reason

        return None, "モデルなし"

    def predict_with_best_model(self, features_df: pd.DataFrame,
                                 venue_code: str,
                                 stage: str,
                                 weather_data: Dict = None) -> np.ndarray:
        """
        最適モデルで予測

        Args:
            features_df: 特徴量DataFrame
            venue_code: 会場コード
            stage: ステージ
            weather_data: 気象データ

        Returns:
            予測確率
        """
        model, reason = self.select_model(venue_code, stage, weather_data)

        if model is None:
            # モデルがない場合は均等確率
            n = len(features_df)
            return np.ones(n) / n

        # 特徴量を準備
        feature_names = self.type_models.feature_names.get(
            self.classifier.classify(venue_code), {}
        ).get(stage, [])

        if feature_names:
            X = features_df.reindex(columns=feature_names, fill_value=0)
        else:
            exclude_cols = ['race_id', 'pit_number', 'race_date', 'venue_code',
                           'racer_number', 'rank']
            X = features_df.drop([c for c in exclude_cols if c in features_df.columns], axis=1)
            X = X.select_dtypes(include=[np.number]).fillna(0)

        try:
            probs = model.predict_proba(X)[:, 1]
        except Exception as e:
            print(f"予測エラー: {e}")
            probs = np.ones(len(X)) / len(X)

        return probs

    def get_model_weights(self, venue_code: str,
                           weather_data: Dict = None) -> Dict[str, float]:
        """
        レースタイプに応じたモデル重みを取得

        Args:
            venue_code: 会場コード
            weather_data: 気象データ

        Returns:
            {'first': weight, 'second': weight, 'third': weight}
        """
        wind_speed = weather_data.get('wind_speed') if weather_data else None
        wave_height = weather_data.get('wave_height') if weather_data else None

        race_type = self.classifier.classify(venue_code, wind_speed, wave_height)
        return self.classifier.get_model_weights(race_type)

    def get_feature_adjustments(self, venue_code: str,
                                 weather_data: Dict = None) -> Dict[str, float]:
        """
        レースタイプに応じた特徴量調整を取得

        Args:
            venue_code: 会場コード
            weather_data: 気象データ

        Returns:
            特徴量調整係数
        """
        wind_speed = weather_data.get('wind_speed') if weather_data else None
        wave_height = weather_data.get('wave_height') if weather_data else None

        race_type = self.classifier.classify(venue_code, wind_speed, wave_height)
        return self.classifier.get_feature_weights(race_type)

    def get_race_analysis(self, venue_code: str,
                           weather_data: Dict = None) -> Dict:
        """
        レースの分析情報を取得

        Args:
            venue_code: 会場コード
            weather_data: 気象データ

        Returns:
            分析結果
        """
        wind_speed = weather_data.get('wind_speed') if weather_data else None
        wave_height = weather_data.get('wave_height') if weather_data else None

        race_type, confidence = self.classifier.classify_with_confidence(
            venue_code, wind_speed, wave_height
        )
        config = self.classifier.get_type_config(race_type)

        return {
            'race_type': race_type,
            'type_name': config['name'],
            'characteristics': config['characteristics'],
            'confidence': confidence,
            'model_weights': config.get('model_weight', {}),
            'feature_weights': config.get('feature_weight', {}),
            'has_specific_model': race_type in self.type_models.models,
        }
