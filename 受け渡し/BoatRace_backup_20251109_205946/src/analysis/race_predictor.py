"""
レース予想スコアリングモジュール

コース別傾向 + 選手成績 + モーター性能を統合して、
総合予想スコアと買い目推奨を提供
"""

from typing import Dict, List, Tuple
from .statistics_calculator import StatisticsCalculator
from .racer_analyzer import RacerAnalyzer
from .motor_analyzer import MotorAnalyzer
from .kimarite_scorer import KimariteScorer
from .grade_scorer import GradeScorer
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from src.utils.scoring_config import ScoringConfig
from src.prediction.rule_based_engine import RuleBasedEngine


class RacePredictor:
    """レース予想クラス"""

    def __init__(self, db_path="data/boatrace.db", custom_weights: Dict[str, float] = None):
        self.db_path = db_path
        self.stats_calc = StatisticsCalculator(db_path)
        self.racer_analyzer = RacerAnalyzer(db_path)
        self.motor_analyzer = MotorAnalyzer(db_path)
        self.kimarite_scorer = KimariteScorer(db_path)
        self.grade_scorer = GradeScorer(db_path)
        self.rule_engine = RuleBasedEngine(db_path)

        # 重み設定をロード
        if custom_weights:
            self.weights = custom_weights
        else:
            config = ScoringConfig()
            self.weights = config.load_weights()

        # デフォルトの重み設定（決まり手とグレードが含まれていない場合）
        # データが不足している段階では、決まり手とグレードの重みを0に設定
        if 'kimarite_weight' not in self.weights:
            self.weights['kimarite_weight'] = 0.0  # データ充実後に有効化
        if 'grade_weight' not in self.weights:
            self.weights['grade_weight'] = 0.0  # データ充実後に有効化

    # ========================================
    # コーススコア計算
    # ========================================

    def calculate_course_score(self, venue_code: str, course: int) -> float:
        """
        コース別スコアを計算（設定された重みに基づく）

        Args:
            venue_code: 競艇場コード
            course: コース番号（1-6）

        Returns:
            コーススコア
        """
        # コース別勝率を取得
        course_stats = self.stats_calc.calculate_course_stats(venue_code)

        if course not in course_stats:
            return 0.0

        stats = course_stats[course]
        max_score = self.weights['course_weight']

        # 1着率をスコアに変換（設定された重みを最大点とする）
        # 1コース: 55%で満点
        # 2コース: 15%で満点
        # 3-6コース: 10%以下が多いので、10%で満点

        if course == 1:
            # 1コースは勝率が高いので、55%で満点
            score = min(stats['win_rate'] / 0.55 * max_score, max_score)
        elif course == 2:
            # 2コースは15%で満点
            score = min(stats['win_rate'] / 0.15 * max_score, max_score)
        else:
            # 3-6コースは10%で満点
            score = min(stats['win_rate'] / 0.10 * max_score, max_score)

        return score

    # ========================================
    # レース単位での総合予想
    # ========================================

    def predict_race_by_key(self, race_date: str, venue_code: str, race_number: int) -> List[Dict]:
        """
        レースキー（日付・会場・レース番号）から予想を実行

        Args:
            race_date: レース日付 (例: '2024-10-01')
            venue_code: 競艇場コード (例: '20')
            race_number: レース番号 (例: 1)

        Returns:
            predict_race() と同じ形式の予測結果
        """
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # race_id を取得
        cursor.execute("""
            SELECT id
            FROM races
            WHERE race_date = ? AND venue_code = ? AND race_number = ?
        """, (race_date, venue_code, race_number))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return []

        race_id = row[0]
        return self.predict_race(race_id)

    def get_applied_rules_by_key(self, race_date: str, venue_code: str, race_number: int) -> List[Dict]:
        """
        レースキーから適用法則を取得

        Args:
            race_date: レース日付
            venue_code: 競艇場コード
            race_number: レース番号

        Returns:
            適用される法則のリスト
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
            return []

        race_id = row[0]
        return self.get_applied_rules(race_id)

    def predict_race(self, race_id: int) -> List[Dict]:
        """
        レースの総合予想を実行

        Args:
            race_id: レースID

        Returns:
            [
                {
                    'pit_number': 1,
                    'racer_name': '山田太郎',
                    'course_score': 35.2,
                    'racer_score': 28.5,
                    'motor_score': 15.3,
                    'total_score': 79.0,
                    'confidence': 'A',  # A, B, C, D, E
                    'rank_prediction': 1
                },
                ...
            ]
        """
        # レース情報取得
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT venue_code, race_grade FROM races WHERE id = ?", (race_id,))
        race_info = cursor.fetchone()
        conn.close()

        if not race_info:
            return []

        venue_code = race_info['venue_code']
        race_grade = race_info['race_grade'] if race_info['race_grade'] else '一般'

        # 選手・モーター分析
        racer_analyses = self.racer_analyzer.analyze_race_entries(race_id)
        motor_analyses = self.motor_analyzer.analyze_race_motors(race_id)

        # 各艇のスコア計算
        predictions = []

        for racer_analysis, motor_analysis in zip(racer_analyses, motor_analyses):
            pit_number = racer_analysis['pit_number']
            racer_name = racer_analysis['racer_name']

            # 進入コース（不明な場合は枠番を使用）
            course_stats = racer_analysis['course_stats']
            if course_stats['total_races'] > 0:
                # コース別成績がある場合、そのコースを使用
                # ※実際のコース番号は別途取得が必要だが、
                # ここでは簡易的に枠番を使用
                course = pit_number
            else:
                course = pit_number

            # 各スコア計算（デフォルト40/40/20から設定値にスケーリング）
            course_score_raw = self.calculate_course_score(venue_code, course)
            racer_score_raw = self.racer_analyzer.calculate_racer_score(racer_analysis)
            motor_score_raw = self.motor_analyzer.calculate_motor_score(motor_analysis)

            # 設定された重みに合わせてスケーリング
            # 各Analyzerは固定値(40/40/20)で計算するので、重み設定に応じて変換
            course_score = course_score_raw * (self.weights['course_weight'] / 40.0)
            racer_score = racer_score_raw * (self.weights['racer_weight'] / 40.0)
            motor_score = motor_score_raw * (self.weights['motor_weight'] / 20.0)

            # 決まり手適性スコアを計算
            kimarite_result = self.kimarite_scorer.calculate_kimarite_affinity_score(
                racer_analysis['racer_number'],
                venue_code,
                course,
                days=180,
                max_score=self.weights['kimarite_weight']
            )
            kimarite_score = kimarite_result['score']

            # グレード適性スコアを計算
            grade_result = self.grade_scorer.calculate_grade_affinity_score(
                racer_analysis['racer_number'],
                race_grade,
                days=365,
                max_score=self.weights['grade_weight']
            )
            grade_score = grade_result['score']

            total_score = course_score + racer_score + motor_score + kimarite_score + grade_score

            # 信頼度判定（A-E）
            confidence = self._calculate_confidence(total_score, racer_analysis, motor_analysis)

            predictions.append({
                'pit_number': pit_number,
                'racer_name': racer_name,
                'racer_number': racer_analysis['racer_number'],
                'motor_number': motor_analysis['motor_number'],
                'boat_number': motor_analysis['boat_number'],
                'course_score': round(course_score, 1),
                'racer_score': round(racer_score, 1),
                'motor_score': round(motor_score, 1),
                'kimarite_score': round(kimarite_score, 1),
                'grade_score': round(grade_score, 1),
                'total_score': round(total_score, 1),
                'confidence': confidence,
                # 詳細情報
                'kimarite_detail': kimarite_result,
                'grade_detail': grade_result
            })

        # 法則ベース補正を適用
        predictions = self._apply_rule_based_adjustment(
            predictions,
            race_id,
            venue_code,
            racer_analyses
        )

        # スコア順にソート
        predictions.sort(key=lambda x: x['total_score'], reverse=True)

        # 順位予想を付与
        for rank, pred in enumerate(predictions, 1):
            pred['rank_prediction'] = rank

        return predictions

    def _apply_rule_based_adjustment(
        self,
        predictions: List[Dict],
        race_id: int,
        venue_code: str,
        racer_analyses: List[Dict]
    ) -> List[Dict]:
        """
        法則ベースエンジンで予測確率を補正

        Args:
            predictions: 基本スコアによる予測結果
            race_id: レースID
            venue_code: 競艇場コード
            racer_analyses: 選手分析データ

        Returns:
            補正後の予測結果
        """
        # スコアを確率に変換（softmax）
        import numpy as np
        scores = np.array([p['total_score'] for p in predictions])

        # スコアが全て同じ場合は補正しない
        if np.std(scores) < 0.01:
            return predictions

        # 温度パラメータを使ったsoftmax（温度=10で緩やかな確率分布）
        temperature = 10.0
        exp_scores = np.exp(scores / temperature)
        base_probabilities = exp_scores / np.sum(exp_scores)

        # 基本確率を辞書形式に変換
        base_probs_dict = {
            p['pit_number']: float(base_probabilities[i])
            for i, p in enumerate(predictions)
        }

        # レース情報を取得
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT race_date FROM races WHERE id = ?",
            (race_id,)
        )
        race_date_row = cursor.fetchone()
        race_date = race_date_row[0] if race_date_row else None

        # 出走情報を準備
        cursor.execute("""
            SELECT pit_number, racer_number, racer_name
            FROM entries
            WHERE race_id = ?
            ORDER BY pit_number
        """, (race_id,))
        entries_data = cursor.fetchall()

        # actual_courseを取得
        cursor.execute("""
            SELECT pit_number, actual_course
            FROM race_details
            WHERE race_id = ?
        """, (race_id,))
        course_data = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        # エントリー情報を構築
        entries = []
        for pit, racer_num, racer_name in entries_data:
            entries.append({
                'pit_number': pit,
                'racer_number': racer_num,
                'racer_name': racer_name,
                'actual_course': course_data.get(pit, pit)  # コース未確定ならピット番号
            })

        # 法則を適用
        race_info = {
            'venue_code': venue_code,
            'race_date': race_date
        }

        adjusted_probs = self.rule_engine.apply_rules(
            base_probs_dict,
            race_info,
            entries,
            damping_factor=0.7
        )

        # 補正後の確率をスコアに反映
        for i, pred in enumerate(predictions):
            pit_number = pred['pit_number']
            original_score = pred['total_score']
            original_prob = base_probs_dict[pit_number]
            adjusted_prob = adjusted_probs[pit_number]

            # 確率の変化率をスコアに適用
            if original_prob > 0:
                prob_boost = adjusted_prob / original_prob
                adjusted_score = original_score * prob_boost
            else:
                adjusted_score = original_score

            pred['total_score'] = round(adjusted_score, 1)
            pred['rule_adjustment'] = round((adjusted_prob - original_prob) * 100, 1)  # パーセント表示用

        return predictions

    def get_applied_rules(self, race_id: int) -> List[Dict]:
        """
        レースに適用される法則を取得

        Args:
            race_id: レースID

        Returns:
            適用される法則のリスト
        """
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # レース情報を取得
        cursor.execute(
            "SELECT venue_code, race_date FROM races WHERE id = ?",
            (race_id,)
        )
        race_row = cursor.fetchone()
        if not race_row:
            conn.close()
            return []

        venue_code, race_date = race_row

        # 出走情報を取得
        cursor.execute("""
            SELECT e.pit_number, e.racer_number, e.racer_name, rd.actual_course
            FROM entries e
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        """, (race_id,))
        entries_data = cursor.fetchall()
        conn.close()

        # エントリー情報を構築
        entries = []
        for pit, racer_num, racer_name, course in entries_data:
            entries.append({
                'pit_number': pit,
                'racer_number': racer_num,
                'racer_name': racer_name,
                'actual_course': course if course else pit
            })

        # レース情報
        race_info = {
            'venue_code': venue_code,
            'race_date': race_date
        }

        # 法則エンジンから適用される法則を取得
        applied_rules = self.rule_engine.get_applied_rules(race_info, entries)

        return applied_rules

    def _calculate_confidence(self, total_score: float, racer_analysis: Dict, motor_analysis: Dict) -> str:
        """
        信頼度を判定（A-E）

        Args:
            total_score: 総合スコア
            racer_analysis: 選手分析データ
            motor_analysis: モーター分析データ

        Returns:
            信頼度（'A', 'B', 'C', 'D', 'E'）
        """
        # データ量チェック
        racer_total_races = racer_analysis['overall_stats']['total_races']
        motor_total_races = motor_analysis['motor_stats']['total_races']

        # データが少ない場合は信頼度を下げる
        if racer_total_races < 20 or motor_total_races < 10:
            max_confidence = 'C'
        else:
            max_confidence = 'A'

        # スコアに基づく判定
        if total_score >= 80:
            confidence = 'A'
        elif total_score >= 70:
            confidence = 'B'
        elif total_score >= 60:
            confidence = 'C'
        elif total_score >= 50:
            confidence = 'D'
        else:
            confidence = 'E'

        # データ量による制限
        if max_confidence == 'C' and confidence in ['A', 'B']:
            confidence = 'C'

        return confidence

    # ========================================
    # 買い目推奨
    # ========================================

    def recommend_bets(self, predictions: List[Dict], bet_types: List[str] = None) -> Dict:
        """
        買い目を推奨

        Args:
            predictions: predict_race()の結果
            bet_types: 舟券種別リスト（['3tan', '3fuku', '2tan']など）

        Returns:
            {
                '3tan': [
                    {'combination': '1-2-3', 'confidence': 'A'},
                    {'combination': '1-2-4', 'confidence': 'B'},
                    ...
                ],
                '3fuku': [...],
                ...
            }
        """
        if bet_types is None:
            bet_types = ['3tan', '3fuku']

        recommendations = {}

        # 上位3艇を取得
        top3 = predictions[:3]
        top_numbers = [p['pit_number'] for p in top3]

        # 三連単
        if '3tan' in bet_types:
            recommendations['3tan'] = self._recommend_3tan(predictions, top_numbers)

        # 三連複
        if '3fuku' in bet_types:
            recommendations['3fuku'] = self._recommend_3fuku(predictions, top_numbers)

        # 二連単
        if '2tan' in bet_types:
            recommendations['2tan'] = self._recommend_2tan(predictions, top_numbers)

        # 二連複
        if '2fuku' in bet_types:
            recommendations['2fuku'] = self._recommend_2fuku(predictions, top_numbers)

        return recommendations

    def _recommend_3tan(self, predictions: List[Dict], top_numbers: List[int]) -> List[Dict]:
        """三連単の推奨買い目"""
        bets = []

        # 1位固定で2-3位を変動
        first = top_numbers[0]
        for second in top_numbers[1:]:
            for third in top_numbers:
                if third != first and third != second:
                    combination = f"{first}-{second}-{third}"
                    # 信頼度は1位の信頼度を継承
                    confidence = predictions[0]['confidence']
                    bets.append({
                        'combination': combination,
                        'confidence': confidence
                    })

        return bets[:5]  # 上位5点に絞る

    def _recommend_3fuku(self, predictions: List[Dict], top_numbers: List[int]) -> List[Dict]:
        """三連複の推奨買い目"""
        # 上位3艇のBOX
        combination = '-'.join(map(str, sorted(top_numbers)))
        confidence = predictions[0]['confidence']

        return [{
            'combination': combination,
            'confidence': confidence
        }]

    def _recommend_2tan(self, predictions: List[Dict], top_numbers: List[int]) -> List[Dict]:
        """二連単の推奨買い目"""
        bets = []

        # 1位-2位、1位-3位
        first = top_numbers[0]
        for second in top_numbers[1:3]:
            combination = f"{first}-{second}"
            confidence = predictions[0]['confidence']
            bets.append({
                'combination': combination,
                'confidence': confidence
            })

        return bets

    def _recommend_2fuku(self, predictions: List[Dict], top_numbers: List[int]) -> List[Dict]:
        """二連複の推奨買い目"""
        # 上位2艇
        combination = '-'.join(map(str, sorted(top_numbers[:2])))
        confidence = predictions[0]['confidence']

        return [{
            'combination': combination,
            'confidence': confidence
        }]


if __name__ == "__main__":
    # テスト実行
    predictor = RacePredictor()

    print("=" * 60)
    print("レース予想テスト")
    print("=" * 60)

    # テスト用レースID（実際のデータがあれば）
    test_race_id = 1

    print(f"\n【レースID {test_race_id} の予想】")
    predictions = predictor.predict_race(test_race_id)

    if predictions:
        print("\n順位 | 枠 | 選手名 | コース | 選手 | モーター | 合計 | 信頼度")
        print("-" * 70)
        for pred in predictions:
            print(f" {pred['rank_prediction']}位 | "
                  f"{pred['pit_number']}号艇 | "
                  f"{pred['racer_name']:10s} | "
                  f"{pred['course_score']:5.1f} | "
                  f"{pred['racer_score']:5.1f} | "
                  f"{pred['motor_score']:5.1f} | "
                  f"{pred['total_score']:5.1f} | "
                  f"{pred['confidence']}")

        print("\n【推奨買い目】")
        recommendations = predictor.recommend_bets(predictions)
        for bet_type, bets in recommendations.items():
            print(f"\n{bet_type}:")
            for bet in bets:
                print(f"  {bet['combination']} (信頼度: {bet['confidence']})")
    else:
        print("  データなし")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
