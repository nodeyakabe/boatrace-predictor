"""
決まり手ベース統合予測システム

決まり手確率エンジン、シナリオエンジン、確率統合エンジンを統合し、
理論的な3連単買い目予測を提供
"""

from typing import Dict, List, Tuple, Optional
import logging

from .kimarite_probability_engine import KimariteProbabilityEngine
from .race_scenario_engine import RaceScenarioEngine
from .probability_integrator import ProbabilityIntegrator, BetRecommendation

logger = logging.getLogger(__name__)


class IntegratedKimaritePredictor:
    """決まり手ベース統合予測クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self.kimarite_engine = KimariteProbabilityEngine(db_path)
        self.scenario_engine = RaceScenarioEngine()
        self.probability_integrator = ProbabilityIntegrator()

    def predict_race(
        self,
        race_id: int,
        min_bets: int = 3,
        max_bets: int = 6,
        strategy: str = 'probability'
    ) -> Dict:
        """
        レースの総合予測を実行

        Args:
            race_id: レースID
            min_bets: 最小買い目数
            max_bets: 最大買い目数
            strategy: 買い目選定戦略

        Returns:
            {
                'bets': [BetRecommendation, ...],
                'scenarios': [RaceScenario, ...],
                'kimarite_probs': {pit: {Kimarite: prob}},
                'statistics': {...}
            }
        """
        try:
            # 1. 決まり手確率を計算
            logger.info(f"Race {race_id}: 決まり手確率を計算中...")
            kimarite_probs = self.kimarite_engine.calculate_kimarite_probabilities(race_id)

            # 2. 展開シナリオを計算
            logger.info(f"Race {race_id}: 展開シナリオを計算中...")
            scenarios = self.scenario_engine.calculate_race_scenarios(kimarite_probs)

            # 3. 最適な買い目を選定
            logger.info(f"Race {race_id}: 買い目を選定中...")
            bets = self.probability_integrator.select_optimal_bets(
                scenarios,
                min_bets=min_bets,
                max_bets=max_bets,
                strategy=strategy
            )

            # 4. 統計情報を計算
            statistics = self.probability_integrator.get_bet_statistics(bets)

            logger.info(f"Race {race_id}: 予測完了 ({len(bets)}点買い)")

            return {
                'bets': bets,
                'scenarios': scenarios,
                'kimarite_probs': kimarite_probs,
                'statistics': statistics
            }

        except Exception as e:
            logger.error(f"Race {race_id}: 予測エラー - {e}")
            raise

    def predict_race_by_key(
        self,
        race_date: str,
        venue_code: str,
        race_number: int,
        min_bets: int = 3,
        max_bets: int = 6
    ) -> Dict:
        """
        レースキーから予測を実行

        Args:
            race_date: レース日付 (例: '2024-10-01')
            venue_code: 競艇場コード (例: '20')
            race_number: レース番号 (例: 1)
            min_bets: 最小買い目数
            max_bets: 最大買い目数

        Returns:
            predict_race()と同じ形式
        """
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id
            FROM races
            WHERE race_date = ? AND venue_code = ? AND race_number = ?
        """, (race_date, venue_code, race_number))

        row = cursor.fetchone()
        conn.close()

        if not row:
            raise ValueError(f"Race not found: {race_date} {venue_code} R{race_number}")

        race_id = row[0]
        return self.predict_race(race_id, min_bets, max_bets)

    def get_win_probabilities(self, race_id: int) -> Dict[int, float]:
        """
        各艇の1着確率を取得

        Args:
            race_id: レースID

        Returns:
            {pit_number: win_probability}
        """
        kimarite_probs = self.kimarite_engine.calculate_kimarite_probabilities(race_id)
        return self.kimarite_engine.calculate_win_probability(kimarite_probs)

    def get_exacta_probabilities(self, race_id: int) -> Dict[Tuple[int, int], float]:
        """
        2連単確率を取得

        Args:
            race_id: レースID

        Returns:
            {(1着, 2着): 確率}
        """
        kimarite_probs = self.kimarite_engine.calculate_kimarite_probabilities(race_id)
        scenarios = self.scenario_engine.calculate_race_scenarios(kimarite_probs)
        return self.probability_integrator.calculate_exacta_probabilities(scenarios)

    def get_trifecta_probabilities(self, race_id: int) -> Dict[Tuple[int, int, int], float]:
        """
        3連単確率を取得

        Args:
            race_id: レースID

        Returns:
            {(1着, 2着, 3着): 確率}
        """
        kimarite_probs = self.kimarite_engine.calculate_kimarite_probabilities(race_id)
        scenarios = self.scenario_engine.calculate_race_scenarios(kimarite_probs)
        trifecta_probs, _ = self.probability_integrator.calculate_trifecta_probabilities(scenarios)
        return trifecta_probs

    def format_prediction_for_ui(self, prediction: Dict) -> Dict:
        """
        予測結果をUI表示用にフォーマット

        Args:
            prediction: predict_race()の結果

        Returns:
            UI表示用の辞書
        """
        bets = prediction['bets']
        statistics = prediction['statistics']

        # 買い目を表示用にフォーマット
        formatted_bets = self.probability_integrator.format_bets_for_display(bets)

        # 累積的中率を計算
        total_probability = statistics['total_probability']

        return {
            'bets': formatted_bets,
            'main_favorite': f"{statistics['main_favorite']}号艇",
            'total_coverage': f"{total_probability * 100:.1f}%",
            'bet_count': statistics['total_bets'],
            'recommendation': self._get_recommendation_message(total_probability, len(bets))
        }

    def _get_recommendation_message(self, total_probability: float, bet_count: int) -> str:
        """推奨メッセージを生成"""
        if total_probability >= 0.60:
            return f"高い的中率が期待できます（{bet_count}点買いで{total_probability*100:.1f}%カバー）"
        elif total_probability >= 0.45:
            return f"良好な的中率が期待できます（{bet_count}点買いで{total_probability*100:.1f}%カバー）"
        elif total_probability >= 0.30:
            return f"平均的な的中率です（{bet_count}点買いで{total_probability*100:.1f}%カバー）"
        else:
            return f"的中率はやや低めです（{bet_count}点買いで{total_probability*100:.1f}%カバー）"


if __name__ == "__main__":
    # テスト実行
    import sys

    logging.basicConfig(level=logging.INFO)

    predictor = IntegratedKimaritePredictor()

    # テスト用レースID
    test_race_id = 445  # 実際のデータがあるレースID

    print("=" * 80)
    print("決まり手ベース予測システム - テスト実行")
    print("=" * 80)

    try:
        # 予測実行
        result = predictor.predict_race(test_race_id, min_bets=3, max_bets=5)

        print(f"\n【レースID {test_race_id} の予測結果】\n")

        # 買い目を表示
        print("=== 推奨買い目 ===")
        formatted = predictor.format_prediction_for_ui(result)

        for bet_info in formatted['bets']:
            print(f"{bet_info['順位']}. {bet_info['買い目']} - {bet_info['確率']} ({bet_info['信頼度']})")
            print(f"   シナリオ: {bet_info['シナリオ']}\n")

        print(f"\n本命: {formatted['main_favorite']}")
        print(f"的中率カバー: {formatted['total_coverage']}")
        print(f"推奨: {formatted['recommendation']}")

        # シナリオサマリー
        print("\n" + predictor.scenario_engine.get_scenario_summary(result['scenarios']))

    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
