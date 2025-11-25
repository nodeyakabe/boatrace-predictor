"""
強化版統合予測システム
Phase 1-3の全改善を統合した予測パイプライン
"""
import sys
import os

# パス設定（直接実行時用）
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# 新規モジュールのインポート
from src.ml.conditional_rank_model import ConditionalRankModel
from src.features.interaction_features import InteractionFeatureGenerator
from src.features.equipment_embedding import EquipmentEmbedding
from src.betting.risk_adjuster import RiskAdjuster
from src.betting.odds_calibration import OddsCalibrator
from src.monitoring.prediction_monitor import PredictionMonitor
from src.utils.error_handler import ErrorHandler, safe_execution


class EnhancedPredictor:
    """
    強化版予測システム

    主要改善点:
    1. 条件付き着順予測（1着→2着→3着）
    2. 交互作用特徴量
    3. 機材Embedding
    4. リスク調整とオッズ校正
    5. リアルタイムモニタリング
    """

    def __init__(
        self,
        db_path: str = 'data/boatrace.db',
        model_dir: str = 'models',
        enable_monitoring: bool = True
    ):
        self.db_path = db_path
        self.model_dir = model_dir
        self.enable_monitoring = enable_monitoring

        # エラーハンドラー
        self.error_handler = ErrorHandler()

        # モデル初期化
        self.conditional_model = None
        self.interaction_generator = None
        self.equipment_embedding = None
        self.risk_adjuster = None
        self.odds_calibrator = None
        self.prediction_monitor = None

        self._initialize_components()

    def _initialize_components(self):
        """コンポーネントを初期化"""
        print("強化版予測システムを初期化...")

        # 条件付きモデル
        try:
            self.conditional_model = ConditionalRankModel(self.model_dir)
            # 学習済みモデルがあれば読み込み
            model_path = os.path.join(self.model_dir, 'conditional_rank_v1.1st.json')
            if os.path.exists(model_path):
                self.conditional_model.load('conditional_rank_v1')
                print("  [OK] 条件付きモデルを読み込みました")
            else:
                print("  [INFO] 条件付きモデルは未学習です")
        except Exception as e:
            print(f"  [WARN] 条件付きモデル初期化エラー: {e}")

        # 交互作用特徴量生成器
        try:
            self.interaction_generator = InteractionFeatureGenerator()
            print("  [OK] 交互作用特徴量生成器を初期化")
        except Exception as e:
            print(f"  [WARN] 交互作用生成器エラー: {e}")

        # 機材Embedding
        try:
            self.equipment_embedding = EquipmentEmbedding(self.db_path)
            embedding_path = os.path.join(self.model_dir, 'equipment_embeddings.json')
            if os.path.exists(embedding_path):
                self.equipment_embedding.load(embedding_path)
                print("  [OK] 機材Embeddingを読み込みました")
            else:
                print("  [INFO] 機材Embeddingは未構築です")
        except Exception as e:
            print(f"  [WARN] 機材Embeddingエラー: {e}")

        # リスク調整器
        try:
            self.risk_adjuster = RiskAdjuster()
            print("  [OK] リスク調整器を初期化")
        except Exception as e:
            print(f"  [WARN] リスク調整器エラー: {e}")

        # オッズ校正器
        try:
            self.odds_calibrator = OddsCalibrator(takeout_rate=0.25)
            print("  [OK] オッズ校正器を初期化")
        except Exception as e:
            print(f"  [WARN] オッズ校正器エラー: {e}")

        # 予測モニター
        if self.enable_monitoring:
            try:
                self.prediction_monitor = PredictionMonitor()
                print("  [OK] 予測モニターを初期化")
            except Exception as e:
                print(f"  [WARN] 予測モニターエラー: {e}")

        print("初期化完了\n")

    @safe_execution(default_return={})
    def predict_race(
        self,
        race_data: Dict,
        odds_data: Optional[Dict[str, float]] = None,
        bankroll: float = 10000
    ) -> Dict:
        """
        レースの予測を実行

        Args:
            race_data: レースデータ
                {
                    'race_id': 'R001',
                    'venue_code': '01',
                    'entries': [
                        {
                            'pit_number': 1,
                            'racer_number': '1234',
                            'win_rate': 6.5,
                            'second_rate': 8.2,
                            ...
                        },
                        ...
                    ],
                    'weather': {
                        'wind_speed': 3.0,
                        'wind_direction': 90,
                        ...
                    }
                }
            odds_data: オッズデータ {'1-2-3': 10.5, ...}
            bankroll: 現在の資金

        Returns:
            予測結果
        """
        start_time = datetime.now()

        # 特徴量準備
        features_df = self._prepare_features(race_data)

        # 三連単確率予測
        trifecta_probs = {}

        if self.conditional_model and self._is_model_trained():
            # 条件付きモデルによる予測
            trifecta_probs = self.conditional_model.predict_trifecta_probabilities(features_df)
        else:
            # フォールバック：単純な確率計算
            trifecta_probs = self._fallback_prediction(features_df)

        # オッズ校正
        if odds_data and self.odds_calibrator:
            trifecta_probs = self.odds_calibrator.calibrate_predictions(
                trifecta_probs, odds_data, method='blend'
            )

            # 整合性チェック
            consistency = self.odds_calibrator.check_probability_consistency(
                trifecta_probs, odds_data
            )
        else:
            consistency = {'is_consistent': True}

        # 上位予測を取得
        top_predictions = sorted(trifecta_probs.items(), key=lambda x: x[1], reverse=True)[:20]

        # リスク調整と買い目生成
        recommended_bets = []
        if odds_data and self.risk_adjuster:
            # 期待値計算
            bets_for_adjustment = []
            for combo, prob in top_predictions[:10]:
                if combo in odds_data:
                    ev = prob * odds_data[combo] - 1.0
                    if ev > 0.05:  # 5%以上の期待値
                        bets_for_adjustment.append({
                            'combination': combo,
                            'prob': prob,
                            'odds': odds_data[combo],
                            'bet_amount': bankroll * 0.02 * ev  # 期待値に比例
                        })

            # リスク調整
            if bets_for_adjustment:
                adjusted_bets = self.risk_adjuster.adjust_bets_for_correlation(
                    bets_for_adjustment, bankroll
                )

                for bet in adjusted_bets:
                    if bet.recommended_bet > 100:  # 最小100円
                        recommended_bets.append({
                            'combination': bet.combination,
                            'prob': bet.original_prob,
                            'adjusted_prob': bet.adjusted_prob,
                            'odds': bet.odds,
                            'expected_value': bet.expected_value,
                            'risk_score': bet.risk_score,
                            'recommended_bet': round(bet.recommended_bet / 100) * 100,
                            'confidence': bet.confidence_score
                        })

        # 処理時間
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

        # 結果まとめ
        result = {
            'race_id': race_data.get('race_id', ''),
            'timestamp': datetime.now().isoformat(),
            'top_predictions': [
                {'combination': combo, 'probability': prob}
                for combo, prob in top_predictions[:10]
            ],
            'recommended_bets': recommended_bets,
            'total_bet_amount': sum(b['recommended_bet'] for b in recommended_bets),
            'expected_return': sum(
                b['recommended_bet'] * b['adjusted_prob'] * b['odds']
                for b in recommended_bets
            ) if recommended_bets else 0,
            'consistency_check': consistency,
            'processing_time_ms': elapsed_ms,
            'model_used': 'conditional' if self._is_model_trained() else 'fallback'
        }

        return result

    def _prepare_features(self, race_data: Dict) -> pd.DataFrame:
        """レースデータから特徴量を準備"""
        entries = race_data.get('entries', [])
        weather = race_data.get('weather', {})
        venue_code = race_data.get('venue_code', '01')

        features_list = []

        for entry in entries:
            features = {
                'pit_number': entry.get('pit_number', 1),
                'win_rate': entry.get('win_rate', 0),
                'second_rate': entry.get('second_rate', 0),
                'third_rate': entry.get('third_rate', 0),
                'motor_2nd_rate': entry.get('motor_2nd_rate', 0),
                'motor_3rd_rate': entry.get('motor_3rd_rate', 0),
                'boat_2nd_rate': entry.get('boat_2nd_rate', 0),
                'boat_3rd_rate': entry.get('boat_3rd_rate', 0),
                'weight': entry.get('weight', 52),
                'avg_st': entry.get('avg_st', 0.15),
                'local_win_rate': entry.get('local_win_rate', 0),
                'racer_rank_score': self._rank_to_score(entry.get('racer_rank', 'B1')),
            }

            # 天候情報
            features.update({
                'wind_speed': weather.get('wind_speed', 0),
                'wind_direction': weather.get('wind_direction', 0),
                'wave_height': weather.get('wave_height', 0),
                'water_temp': weather.get('water_temp', 20),
                'air_temp': weather.get('air_temp', 20),
            })

            features_list.append(features)

        df = pd.DataFrame(features_list)

        # 交互作用特徴量を追加
        if self.interaction_generator:
            try:
                df = self.interaction_generator.generate_all_interactions(df)
            except Exception:
                pass

        # 機材Embeddingを追加
        if self.equipment_embedding:
            try:
                for i, entry in enumerate(entries):
                    motor_emb = self.equipment_embedding.get_motor_embedding(
                        venue_code, entry.get('motor_number', 1)
                    )
                    boat_emb = self.equipment_embedding.get_boat_embedding(
                        venue_code, entry.get('boat_number', 1)
                    )

                    for j in range(len(motor_emb)):
                        df.loc[i, f'motor_emb_{j}'] = motor_emb[j]
                        df.loc[i, f'boat_emb_{j}'] = boat_emb[j]
            except Exception:
                pass

        return df

    def _rank_to_score(self, rank: str) -> int:
        """級別をスコアに変換"""
        rank_map = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
        return rank_map.get(rank, 2)

    def _is_model_trained(self) -> bool:
        """モデルが学習済みかチェック"""
        if self.conditional_model is None:
            return False

        return all(
            self.conditional_model.models.get(k) is not None
            for k in ['first', 'second', 'third']
        )

    def _fallback_prediction(self, features_df: pd.DataFrame) -> Dict[str, float]:
        """フォールバック予測（モデル未学習時）"""
        # 勝率ベースの単純予測
        win_rates = features_df['win_rate'].values
        total_win_rate = sum(win_rates)

        if total_win_rate == 0:
            win_probs = [1/6] * 6
        else:
            win_probs = [w / total_win_rate for w in win_rates]

        # 三連単確率を近似計算
        trifecta_probs = {}

        for i in range(6):
            for j in range(6):
                if j == i:
                    continue
                for k in range(6):
                    if k == i or k == j:
                        continue

                    # P(i-j-k) ≈ P(i) × P(j|not i) × P(k|not i,j)
                    p_1st = win_probs[i]

                    remaining_for_2nd = sum(win_probs[m] for m in range(6) if m != i)
                    p_2nd = win_probs[j] / remaining_for_2nd if remaining_for_2nd > 0 else 0

                    remaining_for_3rd = sum(win_probs[m] for m in range(6) if m != i and m != j)
                    p_3rd = win_probs[k] / remaining_for_3rd if remaining_for_3rd > 0 else 0

                    combo = f"{i+1}-{j+1}-{k+1}"
                    trifecta_probs[combo] = p_1st * p_2nd * p_3rd

        return trifecta_probs

    def get_system_status(self) -> Dict:
        """システムステータスを取得"""
        status = {
            'conditional_model': 'trained' if self._is_model_trained() else 'not_trained',
            'interaction_generator': 'ready' if self.interaction_generator else 'not_available',
            'equipment_embedding': 'loaded' if self.equipment_embedding and self.equipment_embedding.motor_embeddings else 'not_loaded',
            'risk_adjuster': 'ready' if self.risk_adjuster else 'not_available',
            'odds_calibrator': 'ready' if self.odds_calibrator else 'not_available',
            'monitoring': 'enabled' if self.prediction_monitor else 'disabled',
        }

        if self.prediction_monitor:
            status['monitoring_metrics'] = self.prediction_monitor.get_current_metrics()

        return status


if __name__ == "__main__":
    print("=" * 60)
    print("強化版統合予測システム テスト")
    print("=" * 60)

    # システム初期化
    predictor = EnhancedPredictor()

    # ステータス確認
    print("\n【システムステータス】")
    status = predictor.get_system_status()
    for key, value in status.items():
        if not isinstance(value, dict):
            print(f"  {key}: {value}")

    # サンプル予測
    print("\n【サンプル予測】")
    sample_race = {
        'race_id': 'TEST001',
        'venue_code': '01',
        'entries': [
            {'pit_number': 1, 'win_rate': 7.5, 'second_rate': 9.2, 'third_rate': 11.5,
             'motor_2nd_rate': 35.0, 'motor_3rd_rate': 50.0, 'boat_2nd_rate': 32.0, 'boat_3rd_rate': 48.0,
             'weight': 52, 'avg_st': 0.14, 'local_win_rate': 8.0, 'racer_rank': 'A1'},
            {'pit_number': 2, 'win_rate': 6.2, 'second_rate': 8.0, 'third_rate': 10.5,
             'motor_2nd_rate': 33.0, 'motor_3rd_rate': 48.0, 'boat_2nd_rate': 30.0, 'boat_3rd_rate': 46.0,
             'weight': 54, 'avg_st': 0.15, 'local_win_rate': 6.5, 'racer_rank': 'A2'},
            {'pit_number': 3, 'win_rate': 5.8, 'second_rate': 7.5, 'third_rate': 10.0,
             'motor_2nd_rate': 32.0, 'motor_3rd_rate': 47.0, 'boat_2nd_rate': 31.0, 'boat_3rd_rate': 45.0,
             'weight': 51, 'avg_st': 0.16, 'local_win_rate': 5.0, 'racer_rank': 'B1'},
            {'pit_number': 4, 'win_rate': 5.0, 'second_rate': 7.0, 'third_rate': 9.5,
             'motor_2nd_rate': 30.0, 'motor_3rd_rate': 45.0, 'boat_2nd_rate': 29.0, 'boat_3rd_rate': 44.0,
             'weight': 53, 'avg_st': 0.17, 'local_win_rate': 4.5, 'racer_rank': 'B1'},
            {'pit_number': 5, 'win_rate': 4.5, 'second_rate': 6.5, 'third_rate': 9.0,
             'motor_2nd_rate': 28.0, 'motor_3rd_rate': 43.0, 'boat_2nd_rate': 27.0, 'boat_3rd_rate': 42.0,
             'weight': 50, 'avg_st': 0.18, 'local_win_rate': 3.8, 'racer_rank': 'B1'},
            {'pit_number': 6, 'win_rate': 4.0, 'second_rate': 6.0, 'third_rate': 8.5,
             'motor_2nd_rate': 26.0, 'motor_3rd_rate': 41.0, 'boat_2nd_rate': 25.0, 'boat_3rd_rate': 40.0,
             'weight': 55, 'avg_st': 0.19, 'local_win_rate': 3.0, 'racer_rank': 'B2'},
        ],
        'weather': {
            'wind_speed': 3.0,
            'wind_direction': 90,
            'wave_height': 5,
            'water_temp': 22,
            'air_temp': 25,
        }
    }

    sample_odds = {
        '1-2-3': 8.5,
        '1-2-4': 12.3,
        '1-3-2': 10.2,
        '1-3-4': 15.8,
        '2-1-3': 18.5,
        '2-1-4': 22.0,
    }

    result = predictor.predict_race(sample_race, sample_odds, bankroll=10000)

    print(f"処理時間: {result['processing_time_ms']:.1f}ms")
    print(f"使用モデル: {result['model_used']}")
    print(f"\n上位予測:")
    for pred in result['top_predictions'][:5]:
        print(f"  {pred['combination']}: {pred['probability']:.2%}")

    if result['recommended_bets']:
        print(f"\n推奨買い目:")
        for bet in result['recommended_bets'][:3]:
            print(f"  {bet['combination']}: {bet['recommended_bet']}円 (EV: {bet['expected_value']:.1%})")
        print(f"\n総賭け金: {result['total_bet_amount']}円")
        print(f"期待リターン: {result['expected_return']:.0f}円")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
