"""
バックテストモジュール

過去レースデータを使って予想精度を検証
"""

import sqlite3
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from .race_predictor import RacePredictor


class Backtester:
    """バックテスト実行クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path
        self.predictor = RacePredictor(db_path)

    def run_backtest(
        self,
        start_date: str,
        end_date: str,
        venue_code: str = None,
        min_confidence: str = None
    ) -> Dict:
        """
        バックテスト実行

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)
            venue_code: 競艇場コード (Noneで全競艇場)
            min_confidence: 最低信頼度 ('A', 'B', 'C', 'D', 'E')

        Returns:
            バックテスト結果
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # レース取得
        if venue_code:
            query = """
                SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
                FROM races r
                JOIN results res ON r.id = res.race_id
                WHERE r.race_date BETWEEN ? AND ?
                AND r.venue_code = ?
                AND res.is_invalid = 0
                ORDER BY r.race_date, r.race_number
            """
            cursor.execute(query, (start_date, end_date, venue_code))
        else:
            query = """
                SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
                FROM races r
                JOIN results res ON r.id = res.race_id
                WHERE r.race_date BETWEEN ? AND ?
                AND res.is_invalid = 0
                ORDER BY r.race_date, r.race_number
            """
            cursor.execute(query, (start_date, end_date))

        races = cursor.fetchall()
        conn.close()

        # バックテスト実行
        results = {
            'total_races': 0,
            'predictions': [],
            '3tan_hit': 0,
            '3fuku_hit': 0,
            '2tan_hit': 0,
            '2fuku_hit': 0,
            'rank1_correct': 0,
            'rank1_2_correct': 0,
            'rank1_3_correct': 0,
            'confidence_distribution': {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0},
            'confidence_accuracy': {'A': {'total': 0, 'correct': 0}, 'B': {'total': 0, 'correct': 0}, 'C': {'total': 0, 'correct': 0}, 'D': {'total': 0, 'correct': 0}, 'E': {'total': 0, 'correct': 0}}
        }

        for race_id, venue_code, race_date, race_number in races:
            # 予想実行
            predictions = self.predictor.predict_race(race_id)

            if not predictions:
                continue

            # 信頼度フィルター
            top_confidence = predictions[0]['confidence']
            if min_confidence:
                confidence_order = ['E', 'D', 'C', 'B', 'A']
                if confidence_order.index(top_confidence) < confidence_order.index(min_confidence):
                    continue

            # 実際の結果を取得
            actual_result = self._get_actual_result(race_id)

            if not actual_result:
                continue

            results['total_races'] += 1
            results['confidence_distribution'][top_confidence] += 1

            # 予想vs実際の比較
            prediction_result = self._evaluate_prediction(predictions, actual_result)

            # 的中判定
            if prediction_result['rank1_correct']:
                results['rank1_correct'] += 1
                results['confidence_accuracy'][top_confidence]['correct'] += 1

            if prediction_result['rank1_2_correct']:
                results['rank1_2_correct'] += 1

            if prediction_result['rank1_3_correct']:
                results['rank1_3_correct'] += 1

            results['confidence_accuracy'][top_confidence]['total'] += 1

            # 買い目的中判定
            recommendations = self.predictor.recommend_bets(predictions, bet_types=['3tan', '3fuku', '2tan', '2fuku'])

            if self._check_bet_hit(recommendations.get('3tan', []), actual_result, '3tan'):
                results['3tan_hit'] += 1

            if self._check_bet_hit(recommendations.get('3fuku', []), actual_result, '3fuku'):
                results['3fuku_hit'] += 1

            if self._check_bet_hit(recommendations.get('2tan', []), actual_result, '2tan'):
                results['2tan_hit'] += 1

            if self._check_bet_hit(recommendations.get('2fuku', []), actual_result, '2fuku'):
                results['2fuku_hit'] += 1

            # 詳細記録
            results['predictions'].append({
                'race_id': race_id,
                'venue_code': venue_code,
                'race_date': race_date,
                'race_number': race_number,
                'predicted_top3': [p['pit_number'] for p in predictions[:3]],
                'actual_top3': [actual_result['rank1'], actual_result['rank2'], actual_result['rank3']],
                'confidence': top_confidence,
                'rank1_correct': prediction_result['rank1_correct']
            })

        # 精度計算
        if results['total_races'] > 0:
            results['rank1_accuracy'] = results['rank1_correct'] / results['total_races']
            results['rank1_2_accuracy'] = results['rank1_2_correct'] / results['total_races']
            results['rank1_3_accuracy'] = results['rank1_3_correct'] / results['total_races']
            results['3tan_hit_rate'] = results['3tan_hit'] / results['total_races']
            results['3fuku_hit_rate'] = results['3fuku_hit'] / results['total_races']
            results['2tan_hit_rate'] = results['2tan_hit'] / results['total_races']
            results['2fuku_hit_rate'] = results['2fuku_hit'] / results['total_races']

        return results

    def _get_actual_result(self, race_id: int) -> Dict:
        """実際のレース結果を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ?
            AND is_invalid = 0
            ORDER BY rank
            LIMIT 3
        """, (race_id,))

        rows = cursor.fetchall()
        conn.close()

        if len(rows) < 3:
            return None

        return {
            'rank1': rows[0][0],
            'rank2': rows[1][0],
            'rank3': rows[2][0]
        }

    def _evaluate_prediction(self, predictions: List[Dict], actual_result: Dict) -> Dict:
        """予想と実際の結果を比較"""
        predicted_top3 = [p['pit_number'] for p in predictions[:3]]

        return {
            'rank1_correct': predicted_top3[0] == actual_result['rank1'],
            'rank1_2_correct': actual_result['rank1'] in predicted_top3[:2],
            'rank1_3_correct': actual_result['rank1'] in predicted_top3[:3]
        }

    def _check_bet_hit(self, bets: List[Dict], actual_result: Dict, bet_type: str) -> bool:
        """買い目が的中したかチェック"""
        if not bets:
            return False

        actual_combination = None

        if bet_type == '3tan':
            actual_combination = f"{actual_result['rank1']}-{actual_result['rank2']}-{actual_result['rank3']}"
        elif bet_type == '3fuku':
            actual_set = set([actual_result['rank1'], actual_result['rank2'], actual_result['rank3']])
        elif bet_type == '2tan':
            actual_combination = f"{actual_result['rank1']}-{actual_result['rank2']}"
        elif bet_type == '2fuku':
            actual_set = set([actual_result['rank1'], actual_result['rank2']])

        for bet in bets:
            if bet_type in ['3tan', '2tan']:
                if bet['combination'] == actual_combination:
                    return True
            else:  # 3fuku, 2fuku
                bet_numbers = set(map(int, bet['combination'].split('-')))
                if bet_numbers == actual_set:
                    return True

        return False

    def generate_report(self, results: Dict) -> str:
        """バックテスト結果のレポートを生成"""
        report = []
        report.append("=" * 80)
        report.append("バックテストレポート")
        report.append("=" * 80)
        report.append(f"\n総レース数: {results['total_races']}")

        if results['total_races'] == 0:
            report.append("\n該当するレースがありませんでした")
            return "\n".join(report)

        report.append("\n【予想精度】")
        report.append(f"  1着的中率: {results['rank1_accuracy']:.1%} ({results['rank1_correct']}/{results['total_races']})")
        report.append(f"  1着が予想TOP2内: {results['rank1_2_accuracy']:.1%} ({results['rank1_2_correct']}/{results['total_races']})")
        report.append(f"  1着が予想TOP3内: {results['rank1_3_accuracy']:.1%} ({results['rank1_3_correct']}/{results['total_races']})")

        report.append("\n【買い目的中率】")
        report.append(f"  三連単: {results['3tan_hit_rate']:.1%} ({results['3tan_hit']}/{results['total_races']})")
        report.append(f"  三連複: {results['3fuku_hit_rate']:.1%} ({results['3fuku_hit']}/{results['total_races']})")
        report.append(f"  二連単: {results['2tan_hit_rate']:.1%} ({results['2tan_hit']}/{results['total_races']})")
        report.append(f"  二連複: {results['2fuku_hit_rate']:.1%} ({results['2fuku_hit']}/{results['total_races']})")

        report.append("\n【信頼度分布】")
        for conf in ['A', 'B', 'C', 'D', 'E']:
            count = results['confidence_distribution'][conf]
            if count > 0:
                acc_data = results['confidence_accuracy'][conf]
                accuracy = acc_data['correct'] / acc_data['total'] if acc_data['total'] > 0 else 0
                report.append(f"  {conf}: {count}レース (1着的中率: {accuracy:.1%})")

        return "\n".join(report)
