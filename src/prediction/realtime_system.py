"""
リアルタイム予測システム
Phase 3: 直前情報の反映とオッズ変動活用
"""
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional


class RealtimePredictionSystem:
    """リアルタイム予測システム"""

    def __init__(self, ensemble_predictor, feature_generator):
        """
        初期化

        Args:
            ensemble_predictor: アンサンブル予測器
            feature_generator: 特徴量生成器
        """
        self.ensemble_predictor = ensemble_predictor
        self.feature_generator = feature_generator
        self.odds_history = {}  # オッズ履歴

    def update_with_latest_info(self, base_features, latest_info):
        """
        直前情報で特徴量を更新

        Args:
            base_features: ベース特徴量
            latest_info: 直前情報（dict）

        Returns:
            dict: 更新された特徴量
        """
        updated_features = base_features.copy()

        # 展示タイムの更新
        if 'exhibition_time' in latest_info:
            updated_features['exhibition_time'] = latest_info['exhibition_time']

        # スタートタイミングの更新
        if 'st_time' in latest_info:
            updated_features['st_time'] = latest_info['st_time']

        # 実際のコース取り
        if 'actual_course' in latest_info:
            updated_features['actual_course'] = latest_info['actual_course']

        # 天候の更新
        if 'wind_speed' in latest_info:
            updated_features['current_wind'] = latest_info['wind_speed']

        if 'wave_height' in latest_info:
            updated_features['current_wave'] = latest_info['wave_height']

        return updated_features

    def track_odds_movement(self, race_id, pit_number, current_odds, timestamp=None):
        """
        オッズ変動を追跡

        Args:
            race_id: レースID
            pit_number: 枠番
            current_odds: 現在のオッズ
            timestamp: タイムスタンプ（Noneの場合は現在時刻）
        """
        if timestamp is None:
            timestamp = datetime.now()

        key = f"{race_id}_{pit_number}"

        if key not in self.odds_history:
            self.odds_history[key] = []

        self.odds_history[key].append({
            'timestamp': timestamp,
            'odds': current_odds
        })

    def calculate_odds_features(self, race_id, pit_number):
        """
        オッズ変動特徴量を計算

        Args:
            race_id: レースID
            pit_number: 枠番

        Returns:
            dict: オッズ変動特徴量
        """
        key = f"{race_id}_{pit_number}"

        if key not in self.odds_history or len(self.odds_history[key]) < 2:
            return {
                'odds_trend': 0.0,
                'odds_volatility': 0.0,
                'odds_momentum': 0.0,
                'betting_pressure': 0.0
            }

        history = self.odds_history[key]
        odds_values = [h['odds'] for h in history]

        # トレンド: 最初と最後のオッズ変化率
        odds_trend = (odds_values[-1] - odds_values[0]) / odds_values[0]

        # ボラティリティ: オッズの標準偏差
        odds_volatility = np.std(odds_values)

        # モメンタム: 直近3点の変化率
        if len(odds_values) >= 3:
            recent_values = odds_values[-3:]
            odds_momentum = (recent_values[-1] - recent_values[0]) / recent_values[0]
        else:
            odds_momentum = odds_trend

        # ベッティングプレッシャー: 急激な変化の検出
        if len(odds_values) >= 2:
            changes = np.diff(odds_values)
            betting_pressure = np.max(np.abs(changes)) / odds_values[0]
        else:
            betting_pressure = 0.0

        return {
            'odds_trend': float(odds_trend),
            'odds_volatility': float(odds_volatility),
            'odds_momentum': float(odds_momentum),
            'betting_pressure': float(betting_pressure)
        }

    def predict_with_realtime_update(self, race_id, racers_data, latest_info_list=None):
        """
        リアルタイム情報を反映した予測

        Args:
            race_id: レースID
            racers_data: 各選手の基本データ
            latest_info_list: 各選手の直前情報リスト（オプション）

        Returns:
            list: 各選手の予測確率（更新後）
        """
        predictions = []

        for i, racer_data in enumerate(racers_data):
            # ベース特徴量
            base_features = racer_data['features']

            # 直前情報がある場合は更新
            if latest_info_list and i < len(latest_info_list):
                updated_features = self.update_with_latest_info(
                    base_features,
                    latest_info_list[i]
                )
            else:
                updated_features = base_features

            # オッズ特徴量を追加
            odds_features = self.calculate_odds_features(race_id, racer_data['pit_number'])
            updated_features.update(odds_features)

            # アンサンブル予測
            pred_proba = self.ensemble_predictor.predict_proba(
                updated_features,
                racer_data['venue_code'],
                racer_data.get('race_grade', '一般')
            )

            predictions.append({
                'pit_number': racer_data['pit_number'],
                'racer_name': racer_data.get('racer_name', ''),
                'probability': pred_proba,
                'updated_at': datetime.now().isoformat()
            })

        return predictions

    def calculate_confidence_interval(self, predictions, confidence_level=0.95):
        """
        予測の信頼区間を計算

        Args:
            predictions: 予測確率リスト
            confidence_level: 信頼水準

        Returns:
            dict: 信頼区間情報
        """
        probabilities = [p['probability'] for p in predictions]

        # ブートストラップ法で信頼区間を推定
        n_bootstrap = 1000
        bootstrap_samples = np.random.choice(
            probabilities,
            size=(n_bootstrap, len(probabilities)),
            replace=True
        )

        bootstrap_means = np.mean(bootstrap_samples, axis=1)

        # パーセンタイル法
        alpha = (1 - confidence_level) / 2
        lower_bound = np.percentile(bootstrap_means, alpha * 100)
        upper_bound = np.percentile(bootstrap_means, (1 - alpha) * 100)

        return {
            'lower_bound': float(lower_bound),
            'upper_bound': float(upper_bound),
            'confidence_level': confidence_level
        }

    def detect_anomalies(self, predictions, historical_data=None):
        """
        予測の異常値を検出

        Args:
            predictions: 予測結果
            historical_data: 過去のデータ（オプション）

        Returns:
            list: 異常値のインデックス
        """
        probabilities = np.array([p['probability'] for p in predictions])

        # Z-scoreによる異常検出
        mean = np.mean(probabilities)
        std = np.std(probabilities)

        if std < 0.01:  # 標準偏差が極小の場合
            return []

        z_scores = np.abs((probabilities - mean) / std)

        # Z-score > 2.5を異常とする
        anomaly_indices = np.where(z_scores > 2.5)[0].tolist()

        return anomaly_indices
