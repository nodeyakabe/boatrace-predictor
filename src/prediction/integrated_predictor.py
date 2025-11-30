"""
統合予測システム
Phase 1-3のすべての機能を統合
"""
import numpy as np
from typing import Dict, List, Optional
import pickle
import os
from datetime import datetime

from src.ml.ensemble_predictor import EnsemblePredictor
from src.features.optimized_features import OptimizedFeatureGenerator
from src.features.timeseries_features import TimeseriesFeatureGenerator
from src.prediction.realtime_system import RealtimePredictionSystem
from src.prediction.xai_explainer import XAIExplainer
from config.settings import DATABASE_PATH


class IntegratedPredictor:
    """Phase 1-3の機能を統合した予測システム"""

    def __init__(self, db_path=DATABASE_PATH):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path

        # Phase 1: 最適化特徴量生成器
        self.optimized_feature_gen = OptimizedFeatureGenerator(db_path)

        # Phase 2: 時系列特徴量生成器（DBパスを渡してスレッドセーフに）
        self.timeseries_feature_gen = TimeseriesFeatureGenerator(db_path)

        # Phase 2: アンサンブル予測器
        self.ensemble_predictor = EnsemblePredictor()

        # Phase 3: リアルタイム予測システム
        self.realtime_system = RealtimePredictionSystem(
            self.ensemble_predictor,
            self.optimized_feature_gen
        )

        # Phase 3: XAI説明器
        self.xai_explainer = None  # モデルロード後に初期化

        # モデルをロード
        self._load_models()

    def _load_models(self):
        """
        保存されたモデルをロード
        """
        # 会場別モデルをロード
        models_dir = 'models'
        if os.path.exists(models_dir):
            for venue_code in ['07', '08', '05', '14', '09']:
                model_path = os.path.join(
                    models_dir,
                    f'stage2_venue_{venue_code}.pkl'
                )
                if os.path.exists(model_path):
                    try:
                        with open(model_path, 'rb') as f:
                            self.ensemble_predictor.venue_models[venue_code] = pickle.load(f)
                    except Exception as e:
                        print(f"Warning: Failed to load model for venue {venue_code}: {e}")

            # 汎用モデルをロード
            general_model_path = os.path.join(models_dir, 'stage2_combined_8months.pkl')
            if os.path.exists(general_model_path):
                try:
                    with open(general_model_path, 'rb') as f:
                        self.ensemble_predictor.general_model = pickle.load(f)
                except Exception as e:
                    print(f"Warning: Failed to load general model: {e}")

        # XAI説明器を初期化（汎用モデルを使用）
        if self.ensemble_predictor.general_model:
            feature_names = self._get_feature_names()
            self.xai_explainer = XAIExplainer(
                self.ensemble_predictor.general_model,
                feature_names
            )

    def _get_feature_names(self):
        """
        特徴量名のリストを取得

        Returns:
            list: 特徴量名
        """
        # 基本特徴量
        base_features = [
            'pit_number', 'racer_class', 'win_rate', 'nationwide_win_rate',
            'avg_st', 'motor_2ren_rate', 'boat_2ren_rate',
            'wind_speed', 'wave_height', 'wind_direction'
        ]

        # Phase 1追加特徴量
        phase1_features = [
            'recent_form', 'venue_experience', 'head_to_head',
            'weather_change', 'race_importance'
        ]

        # Phase 2時系列特徴量
        phase2_features = [
            'momentum_score', 'recent_trend', 'consistency', 'peak_performance',
            'motor_age_days', 'motor_performance_trend', 'motor_stability',
            'motor_recent_performance', 'wind_volatility', 'wave_volatility',
            'temp_trend', 'condition_stability', 'month', 'season',
            'month_progress', 'month_sin', 'month_cos', 'is_summer', 'is_winter'
        ]

        # Phase 3リアルタイム特徴量
        phase3_features = [
            'odds_trend', 'odds_volatility', 'odds_momentum', 'betting_pressure'
        ]

        return base_features + phase1_features + phase2_features + phase3_features

    def predict_race(
        self,
        race_id: str,
        venue_code: str,
        race_date: str,
        racers_data: List[Dict],
        latest_info_list: Optional[List[Dict]] = None,
        odds_history: Optional[Dict] = None
    ) -> Dict:
        """
        レース予測（全機能統合版）

        Args:
            race_id: レースID
            venue_code: 会場コード
            race_date: レース日
            racers_data: 選手データリスト
            latest_info_list: 直前情報リスト（オプション）
            odds_history: オッズ履歴（オプション）

        Returns:
            dict: 予測結果と説明
        """
        # Step 1: 基本特徴量生成（Phase 1最適化済み）
        enhanced_racers_data = []

        for racer_data in racers_data:
            # Phase 1: 最適化特徴量（基本データを辞書で渡す）
            base_features = self.optimized_feature_gen.generate_optimized_features(
                racer_data,
                include_new_features=True
            )

            # Phase 2: 時系列特徴量
            timeseries_features = self.timeseries_feature_gen.generate_all_timeseries_features(
                racer_data['racer_number'],
                racer_data.get('motor_number', 0),
                venue_code,
                race_date
            )

            # 特徴量を統合
            combined_features = {**base_features, **timeseries_features}
            combined_features['pit_number'] = racer_data.get('pit_number', 0)

            enhanced_racers_data.append({
                'racer_number': racer_data['racer_number'],
                'racer_name': racer_data.get('racer_name', ''),
                'pit_number': racer_data.get('pit_number', 0),
                'motor_number': racer_data.get('motor_number', 0),
                'features': combined_features,
                'venue_code': venue_code,
                'race_grade': racer_data.get('race_grade', '一般')
            })

        # Step 2: オッズ履歴を反映（Phase 3）
        if odds_history:
            for pit_number, history in odds_history.items():
                for timestamp, odds in history:
                    self.realtime_system.track_odds_movement(
                        race_id,
                        pit_number,
                        odds,
                        timestamp
                    )

        # Step 3: リアルタイム予測（Phase 3）
        predictions = self.realtime_system.predict_with_realtime_update(
            race_id,
            enhanced_racers_data,
            latest_info_list
        )

        # Step 4: XAI説明生成（Phase 3）
        explanations = []
        if self.xai_explainer:
            for i, pred in enumerate(predictions):
                racer_data = enhanced_racers_data[i]
                feature_names = list(racer_data['features'].keys())
                feature_values = list(racer_data['features'].values())

                explanation = self.xai_explainer.explain_prediction(
                    feature_names,
                    feature_values
                )

                explanation_text = self.xai_explainer.generate_explanation_text(
                    racer_data['racer_name'],
                    explanation
                )

                explanations.append({
                    'pit_number': pred['pit_number'],
                    'racer_name': pred['racer_name'],
                    'explanation': explanation,
                    'explanation_text': explanation_text
                })

        # Step 5: 予測比較と波乱分析（Phase 3）
        comparison = None
        upset_analysis = None
        if self.xai_explainer:
            comparison = self.xai_explainer.compare_predictions(predictions)

            # オッズがあれば波乱分析
            if odds_history:
                current_odds = []
                for pred in predictions:
                    pit = pred['pit_number']
                    if str(pit) in odds_history and odds_history[str(pit)]:
                        # 最新のオッズを取得
                        current_odds.append(odds_history[str(pit)][-1][1])
                    else:
                        current_odds.append(10.0)  # デフォルト

                upset_analysis = self.xai_explainer.detect_upset_potential(
                    predictions,
                    current_odds
                )

        # Step 6: 信頼区間と異常検出（Phase 3）
        confidence_interval = self.realtime_system.calculate_confidence_interval(predictions)
        anomalies = self.realtime_system.detect_anomalies(predictions)

        return {
            'race_id': race_id,
            'venue_code': venue_code,
            'race_date': race_date,
            'predictions': predictions,
            'explanations': explanations,
            'comparison': comparison,
            'upset_analysis': upset_analysis,
            'confidence_interval': confidence_interval,
            'anomaly_indices': anomalies,
            'predicted_at': datetime.now().isoformat(),
            'model_version': 'integrated_v1.0_phase1-3'
        }

    def get_feature_importance(self, top_n=20):
        """
        特徴量重要度を取得

        Args:
            top_n: 上位N個

        Returns:
            dict: 特徴量重要度
        """
        if self.xai_explainer:
            return self.xai_explainer.get_feature_importance(top_n)
        return {}

    def batch_predict(
        self,
        races_data: List[Dict],
        show_progress=False
    ) -> List[Dict]:
        """
        複数レースの一括予測

        Args:
            races_data: レースデータのリスト
            show_progress: 進捗表示

        Returns:
            list: 予測結果のリスト
        """
        results = []

        for i, race_data in enumerate(races_data):
            if show_progress:
                print(f"Processing race {i+1}/{len(races_data)}...")

            try:
                prediction = self.predict_race(
                    race_data['race_id'],
                    race_data['venue_code'],
                    race_data['race_date'],
                    race_data['racers_data'],
                    race_data.get('latest_info_list'),
                    race_data.get('odds_history')
                )
                results.append(prediction)
            except Exception as e:
                print(f"Error predicting race {race_data['race_id']}: {e}")
                results.append({
                    'race_id': race_data['race_id'],
                    'error': str(e)
                })

        return results

    def close(self):
        """リソースを解放"""
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    def __del__(self):
        """デストラクタ"""
        self.close()
