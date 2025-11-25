"""
XAI (Explainable AI) モジュール
Phase 3: 予測の説明可能性を提供
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')


class XAIExplainer:
    """予測の説明可能性を提供するクラス"""

    def __init__(self, model, feature_names):
        """
        初期化

        Args:
            model: 学習済みモデル
            feature_names: 特徴量名のリスト
        """
        self.model = model
        self.feature_names = feature_names

    def get_feature_importance(self, top_n=20):
        """
        特徴量重要度を取得

        Args:
            top_n: 上位N個を取得

        Returns:
            dict: 特徴量名と重要度のマッピング
        """
        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
        elif hasattr(self.model, 'get_score'):
            # XGBoostの場合
            importance_dict = self.model.get_score(importance_type='gain')
            importances = np.zeros(len(self.feature_names))
            for i, fname in enumerate(self.feature_names):
                importances[i] = importance_dict.get(f'f{i}', 0)
        else:
            return {}

        # 正規化
        if np.sum(importances) > 0:
            importances = importances / np.sum(importances)

        # 上位N個を取得
        indices = np.argsort(importances)[::-1][:top_n]

        result = {}
        for idx in indices:
            if idx < len(self.feature_names):
                result[self.feature_names[idx]] = float(importances[idx])

        return result

    def explain_prediction(self, features, feature_values):
        """
        個別予測の説明を生成

        Args:
            features: 特徴量名のリスト
            feature_values: 特徴量値のリスト

        Returns:
            dict: 説明情報
        """
        # 基準予測値（全特徴量の平均値を使用）
        base_prediction = 0.5  # デフォルト

        # 各特徴量の寄与度を計算（簡易版）
        contributions = {}

        # 特徴量重要度を取得
        importances = self.get_feature_importance(top_n=len(features))

        for feat_name, feat_value in zip(features, feature_values):
            if feat_name in importances:
                # 重要度に基づいて寄与度を推定
                importance = importances[feat_name]

                # 特徴量の値を正規化（0-1範囲）
                if feat_value is not None:
                    normalized_value = self._normalize_feature_value(
                        feat_name, feat_value
                    )
                    contribution = importance * (normalized_value - 0.5)
                    contributions[feat_name] = float(contribution)

        return {
            'base_prediction': base_prediction,
            'contributions': contributions,
            'top_positive_factors': self._get_top_factors(contributions, positive=True),
            'top_negative_factors': self._get_top_factors(contributions, positive=False)
        }

    def _normalize_feature_value(self, feature_name, value):
        """
        特徴量値を0-1範囲に正規化

        Args:
            feature_name: 特徴量名
            value: 特徴量値

        Returns:
            float: 正規化された値
        """
        # 既知の特徴量範囲（簡易版）
        feature_ranges = {
            'win_rate': (0, 1),
            'avg_st': (-0.5, 0.5),
            'pit_number': (1, 6),
            'nationwide_win_rate': (0, 1),
            'motor_2ren_rate': (0, 1),
            'boat_2ren_rate': (0, 1),
            'wind_speed': (0, 20),
            'wave_height': (0, 100),
        }

        if feature_name in feature_ranges:
            min_val, max_val = feature_ranges[feature_name]
            if max_val > min_val:
                return (value - min_val) / (max_val - min_val)

        # 範囲が不明な場合はそのまま返す
        return min(max(value, 0), 1)

    def _get_top_factors(self, contributions, positive=True, top_n=5):
        """
        上位の寄与因子を取得

        Args:
            contributions: 寄与度辞書
            positive: Trueなら正の寄与、Falseなら負の寄与
            top_n: 上位N個

        Returns:
            list: (特徴量名, 寄与度)のリスト
        """
        sorted_items = sorted(
            contributions.items(),
            key=lambda x: x[1] if positive else -x[1],
            reverse=True
        )

        if positive:
            # 正の寄与のみ
            return [(k, v) for k, v in sorted_items[:top_n] if v > 0]
        else:
            # 負の寄与のみ
            return [(k, v) for k, v in sorted_items[:top_n] if v < 0]

    def generate_explanation_text(self, racer_name, explanation_data):
        """
        人間が読める説明テキストを生成

        Args:
            racer_name: 選手名
            explanation_data: explain_predictionの結果

        Returns:
            str: 説明テキスト
        """
        lines = [f"## {racer_name} の予測説明"]

        # 基準予測
        base_pred = explanation_data['base_prediction'] * 100
        lines.append(f"\n基準予測確率: {base_pred:.1f}%")

        # 正の要因
        positive_factors = explanation_data['top_positive_factors']
        if positive_factors:
            lines.append("\n### 有利な要因:")
            for feat_name, contribution in positive_factors:
                readable_name = self._get_readable_feature_name(feat_name)
                impact = contribution * 100
                lines.append(f"- {readable_name}: +{impact:.2f}%")

        # 負の要因
        negative_factors = explanation_data['top_negative_factors']
        if negative_factors:
            lines.append("\n### 不利な要因:")
            for feat_name, contribution in negative_factors:
                readable_name = self._get_readable_feature_name(feat_name)
                impact = abs(contribution) * 100
                lines.append(f"- {readable_name}: -{impact:.2f}%")

        return "\n".join(lines)

    def _get_readable_feature_name(self, feature_name):
        """
        特徴量名を読みやすい日本語に変換

        Args:
            feature_name: 特徴量名

        Returns:
            str: 読みやすい名前
        """
        name_mapping = {
            'win_rate': '勝率',
            'avg_st': '平均ST',
            'pit_number': '枠番',
            'nationwide_win_rate': '全国勝率',
            'motor_2ren_rate': 'モーター2連率',
            'boat_2ren_rate': 'ボート2連率',
            'wind_speed': '風速',
            'wave_height': '波高',
            'momentum_score': '調子スコア',
            'recent_trend': '最近のトレンド',
            'consistency': '安定性',
            'peak_performance': 'ピークパフォーマンス',
            'motor_age_days': 'モーター使用日数',
            'motor_performance_trend': 'モーター性能トレンド',
            'motor_stability': 'モーター安定性',
            'motor_recent_performance': 'モーター直近成績',
            'odds_trend': 'オッズトレンド',
            'odds_volatility': 'オッズ変動性',
            'odds_momentum': 'オッズモメンタム',
            'betting_pressure': 'ベッティングプレッシャー',
            'recent_form': '最近の調子',
            'venue_experience': '会場経験',
            'head_to_head': '対戦成績',
            'weather_change': '天候変化',
            'race_importance': 'レース重要度',
        }

        return name_mapping.get(feature_name, feature_name)

    def compare_predictions(self, predictions_list):
        """
        複数の予測を比較

        Args:
            predictions_list: 予測結果のリスト

        Returns:
            dict: 比較分析結果
        """
        if len(predictions_list) < 2:
            return {'error': '比較には2つ以上の予測が必要です'}

        # 確率の分散を計算
        probabilities = [p['probability'] for p in predictions_list]
        variance = np.var(probabilities)
        std_dev = np.std(probabilities)

        # 最も確率が高い/低い選手
        sorted_preds = sorted(
            predictions_list,
            key=lambda x: x['probability'],
            reverse=True
        )

        # 確率の差
        prob_diff = sorted_preds[0]['probability'] - sorted_preds[-1]['probability']

        return {
            'highest_prob': {
                'racer': sorted_preds[0].get('racer_name', 'Unknown'),
                'pit_number': sorted_preds[0]['pit_number'],
                'probability': float(sorted_preds[0]['probability'])
            },
            'lowest_prob': {
                'racer': sorted_preds[-1].get('racer_name', 'Unknown'),
                'pit_number': sorted_preds[-1]['pit_number'],
                'probability': float(sorted_preds[-1]['probability'])
            },
            'probability_spread': float(prob_diff),
            'variance': float(variance),
            'std_deviation': float(std_dev),
            'competitiveness': self._calculate_competitiveness(probabilities)
        }

    def _calculate_competitiveness(self, probabilities):
        """
        レースの競争性を計算

        Args:
            probabilities: 確率のリスト

        Returns:
            str: 競争性の評価
        """
        std_dev = np.std(probabilities)

        if std_dev < 0.05:
            return '大混戦'
        elif std_dev < 0.10:
            return '混戦'
        elif std_dev < 0.15:
            return '普通'
        elif std_dev < 0.20:
            return '本命有力'
        else:
            return '本命一強'

    def detect_upset_potential(self, predictions_list, odds_list=None):
        """
        波乱の可能性を検出

        Args:
            predictions_list: 予測結果のリスト
            odds_list: オッズリスト（オプション）

        Returns:
            dict: 波乱可能性分析
        """
        comparison = self.compare_predictions(predictions_list)

        # 確率の標準偏差が小さい = 混戦 = 波乱の可能性高い
        upset_score = 1.0 - min(comparison['std_deviation'] / 0.2, 1.0)

        # オッズと予測確率の乖離をチェック
        if odds_list and len(odds_list) == len(predictions_list):
            # オッズから期待確率を計算（簡易版）
            odds_probs = [1.0 / odds for odds in odds_list]
            total = sum(odds_probs)
            odds_probs = [p / total for p in odds_probs]

            # 予測確率との差分
            pred_probs = [p['probability'] for p in predictions_list]
            divergence = np.mean([abs(p - o) for p, o in zip(pred_probs, odds_probs)])

            # 乖離が大きい = 波乱の可能性
            upset_score = max(upset_score, divergence * 2.0)

        upset_score = min(upset_score, 1.0)

        return {
            'upset_score': float(upset_score),
            'risk_level': self._get_risk_level(upset_score),
            'recommendation': self._get_upset_recommendation(upset_score)
        }

    def _get_risk_level(self, upset_score):
        """リスクレベルを判定"""
        if upset_score < 0.2:
            return '低リスク（本命決着の可能性高）'
        elif upset_score < 0.4:
            return '中リスク（やや波乱あり）'
        elif upset_score < 0.6:
            return '高リスク（波乱注意）'
        else:
            return '超高リスク（大波乱の可能性）'

    def _get_upset_recommendation(self, upset_score):
        """推奨アクションを返す"""
        if upset_score < 0.2:
            return '本命で勝負'
        elif upset_score < 0.4:
            return '本命+穴のヘッジ'
        elif upset_score < 0.6:
            return 'ワイド購入推奨'
        else:
            return '見送り推奨'
