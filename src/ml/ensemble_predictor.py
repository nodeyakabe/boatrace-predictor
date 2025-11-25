"""
アンサンブル予測システム
Phase 2: 会場別モデル × 統合モデルの重み付けアンサンブル
"""
import numpy as np
import json
import os


class EnsemblePredictor:
    """アンサンブル予測クラス"""

    # 会場別モデルの性能（AUC）に基づく重み
    VENUE_WEIGHTS = {
        '07': 0.9341,  # 蒲郡（最高性能）
        '08': 0.8715,  # 常滑
        '05': 0.8512,  # 多摩川
        '12': 0.8496,  # 住之江
        '06': 0.8451,  # 浜名湖
        '01': 0.8343,  # 桐生
        '04': 0.8062,  # 平和島
        '02': 0.7658,  # 戸田
        '03': 0.7553,  # 江戸川
    }

    # 統合モデルのベース性能
    GENERAL_MODEL_AUC = 0.8324

    def __init__(self, models_dir='models'):
        """
        初期化

        Args:
            models_dir: モデルファイルのディレクトリ
        """
        self.models_dir = models_dir
        self.venue_models = {}
        self.general_model = None
        self.load_models()

    def load_models(self):
        """すべてのモデルを読み込み"""
        import xgboost as xgb

        # 統合モデルの読み込み
        general_model_path = os.path.join(self.models_dir, 'stage2_combined_8months.json')
        if os.path.exists(general_model_path):
            self.general_model = xgb.XGBClassifier()
            self.general_model.load_model(general_model_path)
            print(f"[OK] Loaded general model: {general_model_path}")

        # 会場別モデルの読み込み
        for venue_code in self.VENUE_WEIGHTS.keys():
            venue_model_path = os.path.join(self.models_dir, f'stage2_venue_{venue_code}.json')
            if os.path.exists(venue_model_path):
                model = xgb.XGBClassifier()
                model.load_model(venue_model_path)
                self.venue_models[venue_code] = model
                print(f"[OK] Loaded venue model: {venue_code}")

    def calculate_adaptive_weight(self, venue_code, race_grade, confidence_required=0.5):
        """
        状況に応じた適応的重み計算

        Args:
            venue_code: 会場コード
            race_grade: レースグレード
            confidence_required: 必要な確信度

        Returns:
            float: 会場別モデルの重み（0-1）
        """
        # 会場の性能を取得
        venue_auc = self.VENUE_WEIGHTS.get(venue_code, 0.75)

        # ベース重み: 会場性能 / (会場性能 + 統合モデル性能)
        base_weight = venue_auc / (venue_auc + self.GENERAL_MODEL_AUC)

        # レース重要度による調整
        grade_bonus = {
            'SG': 0.0,      # 重要レースでは統合モデル重視
            'G1': 0.05,
            'G2': 0.10,
            'G3': 0.15,
            '一般': 0.20,   # 一般戦では会場特化重視
        }
        weight_adjustment = grade_bonus.get(race_grade, 0.10)

        # 高確信度が必要な場合は会場特化モデルを重視
        if confidence_required > 0.7 and venue_auc > 0.85:
            weight_adjustment += 0.15

        # 最終重み（0.3-0.9の範囲に制限）
        final_weight = np.clip(base_weight + weight_adjustment, 0.3, 0.9)

        return final_weight

    def predict_proba(self, features, venue_code, race_grade='一般', confidence_required=0.5):
        """
        アンサンブル予測

        Args:
            features: 特徴量データ
            venue_code: 会場コード
            race_grade: レースグレード
            confidence_required: 必要な確信度

        Returns:
            float: 勝利確率
        """
        predictions = []
        weights = []

        # 会場別モデルの予測
        if venue_code in self.venue_models:
            venue_pred = self.venue_models[venue_code].predict_proba(features)[0, 1]
            venue_weight = self.calculate_adaptive_weight(venue_code, race_grade, confidence_required)
            predictions.append(venue_pred)
            weights.append(venue_weight)

        # 統合モデルの予測
        if self.general_model is not None:
            general_pred = self.general_model.predict_proba(features)[0, 1]
            general_weight = 1.0 - weights[0] if len(weights) > 0 else 1.0
            predictions.append(general_pred)
            weights.append(general_weight)

        # 重み付き平均
        if len(predictions) == 0:
            raise ValueError("No models available for prediction")

        ensemble_pred = np.average(predictions, weights=weights)

        return ensemble_pred

    def predict_race(self, race_features_list, venue_code, race_grade='一般'):
        """
        レース全体の予測

        Args:
            race_features_list: 各選手の特徴量リスト
            venue_code: 会場コード
            race_grade: レースグレード

        Returns:
            list: 各選手の勝利確率
        """
        predictions = []

        for features in race_features_list:
            pred = self.predict_proba(features, venue_code, race_grade)
            predictions.append(pred)

        return predictions

    def get_model_contribution(self, features, venue_code):
        """
        各モデルの貢献度を取得

        Args:
            features: 特徴量データ
            venue_code: 会場コード

        Returns:
            dict: 各モデルの予測値と重み
        """
        contribution = {}

        # 会場別モデル
        if venue_code in self.venue_models:
            venue_pred = self.venue_models[venue_code].predict_proba(features)[0, 1]
            venue_weight = self.calculate_adaptive_weight(venue_code, '一般')
            contribution['venue_model'] = {
                'prediction': venue_pred,
                'weight': venue_weight,
                'auc': self.VENUE_WEIGHTS.get(venue_code, 0.75)
            }

        # 統合モデル
        if self.general_model is not None:
            general_pred = self.general_model.predict_proba(features)[0, 1]
            general_weight = 1.0 - contribution.get('venue_model', {}).get('weight', 0.0)
            contribution['general_model'] = {
                'prediction': general_pred,
                'weight': general_weight,
                'auc': self.GENERAL_MODEL_AUC
            }

        return contribution
