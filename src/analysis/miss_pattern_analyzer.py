# -*- coding: utf-8 -*-
"""
外れパターン分析モジュール

1着的中時に2-3着で外れるパターンを分析し、
改善のための特徴量や条件を発見する。
"""

import sqlite3
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import json


@dataclass
class MissPattern:
    """外れパターン"""
    pattern_type: str  # 'diff_2nd', 'upset_2nd', 'order_swap' など
    description: str
    count: int
    rate: float
    conditions: Dict


class MissPatternAnalyzer:
    """
    外れパターン分析クラス

    1着が当たった時に2-3着で外れるケースを分析
    """

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path

    def analyze_second_place_misses(
        self,
        start_date: str = '2025-11-01',
        end_date: str = '2025-11-30',
        prediction_type: str = 'advance'
    ) -> Dict:
        """
        2着外れパターンを詳細分析

        Returns:
            分析結果の辞書
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # レース取得
            cursor.execute('''
                SELECT DISTINCT r.id, r.venue_code, r.race_number
                FROM races r
                WHERE r.race_date >= ? AND r.race_date <= ?
            ''', (start_date, end_date))
            races = cursor.fetchall()

        results = {
            'total_races': 0,
            'hit_1st_races': 0,
            'miss_2nd_in_234': 0,
            'patterns': defaultdict(int),
            'by_venue': defaultdict(lambda: {'total': 0, 'miss': 0}),
            'by_confidence': defaultdict(lambda: {'total': 0, 'miss': 0}),
            'by_winner_course': defaultdict(lambda: {'total': 0, 'miss': 0}),
            'actual_2nd_course_when_miss': defaultdict(int),
            'predicted_rank_of_actual_2nd': defaultdict(int),
            'details': []
        }

        for race_id, venue_code, race_number in races:
            analysis = self._analyze_single_race(race_id, prediction_type)
            if analysis is None:
                continue

            results['total_races'] += 1

            if not analysis['hit_1st']:
                continue

            results['hit_1st_races'] += 1
            conf = analysis['confidence']
            winner_course = analysis['winner_course']

            # 信頼度別
            results['by_confidence'][conf]['total'] += 1

            # 勝者コース別
            results['by_winner_course'][winner_course]['total'] += 1

            # 会場別
            results['by_venue'][venue_code]['total'] += 1

            if not analysis['hit_2nd_in_234']:
                results['miss_2nd_in_234'] += 1
                results['by_confidence'][conf]['miss'] += 1
                results['by_winner_course'][winner_course]['miss'] += 1
                results['by_venue'][venue_code]['miss'] += 1

                # 実際の2着のコース
                results['actual_2nd_course_when_miss'][analysis['actual_2nd_course']] += 1

                # 実際の2着が予測何位だったか
                results['predicted_rank_of_actual_2nd'][analysis['actual_2nd_predicted_rank']] += 1

                # パターン分類
                pattern = self._classify_miss_pattern(analysis)
                results['patterns'][pattern] += 1

                results['details'].append(analysis)

        return results

    def _analyze_single_race(
        self,
        race_id: int,
        prediction_type: str
    ) -> Optional[Dict]:
        """単一レースの分析"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 予測データ
            cursor.execute('''
                SELECT pit_number, rank_prediction, confidence, total_score
                FROM race_predictions
                WHERE race_id = ? AND prediction_type = ?
                ORDER BY rank_prediction
            ''', (race_id, prediction_type))
            preds = cursor.fetchall()

            if len(preds) < 6:
                return None

            preds_sorted = sorted(preds, key=lambda x: x[1])
            predicted_ranks = [x[0] for x in preds_sorted]
            scores = [x[3] if x[3] else 0 for x in preds_sorted]
            confidence = preds_sorted[0][2]

            # 実際の結果
            cursor.execute('''
                SELECT pit_number, rank
                FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            actuals = cursor.fetchall()

            if len(actuals) < 3:
                return None

            actual_1st = actuals[0][0]
            actual_2nd = actuals[1][0]
            actual_3rd = actuals[2][0]

            # 各艇のコース情報取得
            cursor.execute('''
                SELECT pit_number,
                       COALESCE(pit_number, pit_number) as course,
                       motor_second_rate,
                       racer_rank
                FROM entries
                WHERE race_id = ?
            ''', (race_id,))
            entries = {row[0]: {'course': row[1], 'motor': row[2], 'rank': row[3]}
                      for row in cursor.fetchall()}

            # 判定
            hit_1st = (predicted_ranks[0] == actual_1st)
            hit_2nd = (predicted_ranks[1] == actual_2nd)
            hit_2nd_in_234 = actual_2nd in predicted_ranks[1:4]
            hit_3rd_in_2345 = actual_3rd in predicted_ranks[1:5]

            # 実際の2着が予測何位だったか
            actual_2nd_pred_rank = predicted_ranks.index(actual_2nd) + 1 if actual_2nd in predicted_ranks else 7

            # スコア差
            score_diff_12 = scores[0] - scores[1] if len(scores) >= 2 else 0
            score_diff_23 = scores[1] - scores[2] if len(scores) >= 3 else 0

            return {
                'race_id': race_id,
                'confidence': confidence,
                'predicted_ranks': predicted_ranks,
                'actual_1st': actual_1st,
                'actual_2nd': actual_2nd,
                'actual_3rd': actual_3rd,
                'hit_1st': hit_1st,
                'hit_2nd': hit_2nd,
                'hit_2nd_in_234': hit_2nd_in_234,
                'hit_3rd_in_2345': hit_3rd_in_2345,
                'actual_2nd_predicted_rank': actual_2nd_pred_rank,
                'winner_course': entries.get(actual_1st, {}).get('course', actual_1st),
                'actual_2nd_course': entries.get(actual_2nd, {}).get('course', actual_2nd),
                'score_diff_12': score_diff_12,
                'score_diff_23': score_diff_23,
            }

    def _classify_miss_pattern(self, analysis: Dict) -> str:
        """外れパターンを分類"""
        pred_rank = analysis['actual_2nd_predicted_rank']
        winner_course = analysis['winner_course']
        actual_2nd_course = analysis['actual_2nd_course']

        if pred_rank == 5:
            return 'low_rank_upset'  # 低評価艇が2着
        elif pred_rank == 6:
            return 'complete_upset'  # 完全な伏兵
        elif actual_2nd_course < winner_course:
            return 'inner_sashi'  # 内から差された
        elif actual_2nd_course > winner_course:
            return 'outer_makuri'  # 外から捲られた
        else:
            return 'order_swap'  # 予測順序の入れ替わり

    def analyze_venue_patterns(
        self,
        start_date: str = '2025-01-01',
        end_date: str = '2025-11-30'
    ) -> Dict:
        """
        会場別の2着パターンを分析

        1着コース別に、2着になりやすいコースを集計
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    r.venue_code,
                    e1.pit_number as winner_course,
                    e2.pit_number as second_course,
                    COUNT(*) as count
                FROM results r1
                JOIN results r2 ON r1.race_id = r2.race_id
                JOIN entries e1 ON r1.race_id = e1.race_id AND r1.pit_number = e1.pit_number
                JOIN entries e2 ON r2.race_id = e2.race_id AND r2.pit_number = e2.pit_number
                JOIN races r ON r1.race_id = r.id
                WHERE r1.rank = 1 AND r2.rank = 2
                  AND r1.is_invalid = 0 AND r2.is_invalid = 0
                  AND r.race_date >= ? AND r.race_date <= ?
                GROUP BY r.venue_code, e1.pit_number, e2.pit_number
                ORDER BY r.venue_code, e1.pit_number, count DESC
            ''', (start_date, end_date))

            venue_patterns = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

            for venue, w_course, s_course, count in cursor.fetchall():
                if w_course and s_course:
                    venue_patterns[venue][w_course][s_course] = count

            return dict(venue_patterns)

    def get_second_place_probability_by_course(
        self,
        venue_code: str,
        winner_course: int,
        start_date: str = '2025-01-01',
        end_date: str = '2025-11-30'
    ) -> Dict[int, float]:
        """
        特定会場・1着コースでの2着コース確率を取得
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    e2.pit_number as second_course,
                    COUNT(*) as count
                FROM results r1
                JOIN results r2 ON r1.race_id = r2.race_id
                JOIN entries e1 ON r1.race_id = e1.race_id AND r1.pit_number = e1.pit_number
                JOIN entries e2 ON r2.race_id = e2.race_id AND r2.pit_number = e2.pit_number
                JOIN races r ON r1.race_id = r.id
                WHERE r1.rank = 1 AND r2.rank = 2
                  AND r1.is_invalid = 0 AND r2.is_invalid = 0
                  AND r.venue_code = ?
                  AND e1.pit_number = ?
                  AND r.race_date >= ? AND r.race_date <= ?
                GROUP BY e2.pit_number
            ''', (venue_code, winner_course, start_date, end_date))

            results = cursor.fetchall()
            total = sum(r[1] for r in results)

            if total == 0:
                return {}

            return {r[0]: r[1] / total for r in results}

    def format_analysis_report(self, results: Dict) -> str:
        """分析結果をレポート形式で出力"""
        lines = []
        lines.append("=" * 80)
        lines.append("外れパターン分析レポート")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"総レース数: {results['total_races']}")
        lines.append(f"1着的中レース: {results['hit_1st_races']}")
        lines.append(f"2着外れ（234外）: {results['miss_2nd_in_234']}")

        if results['hit_1st_races'] > 0:
            miss_rate = results['miss_2nd_in_234'] / results['hit_1st_races'] * 100
            lines.append(f"2着外れ率: {miss_rate:.1f}%")

        lines.append("")
        lines.append("[パターン別]")
        lines.append("-" * 60)
        total_patterns = sum(results['patterns'].values())
        for pattern, count in sorted(results['patterns'].items(), key=lambda x: -x[1]):
            pct = count / total_patterns * 100 if total_patterns > 0 else 0
            lines.append(f"  {pattern}: {count} ({pct:.1f}%)")

        lines.append("")
        lines.append("[実際の2着が予測何位だったか]")
        lines.append("-" * 60)
        for rank in sorted(results['predicted_rank_of_actual_2nd'].keys()):
            count = results['predicted_rank_of_actual_2nd'][rank]
            pct = count / results['miss_2nd_in_234'] * 100 if results['miss_2nd_in_234'] > 0 else 0
            lines.append(f"  予測{rank}位: {count} ({pct:.1f}%)")

        lines.append("")
        lines.append("[信頼度別の2着外れ率]")
        lines.append("-" * 60)
        for conf in ['B', 'C', 'D', 'E']:
            if conf in results['by_confidence']:
                data = results['by_confidence'][conf]
                if data['total'] > 0:
                    rate = data['miss'] / data['total'] * 100
                    lines.append(f"  {conf}: {data['miss']}/{data['total']} ({rate:.1f}%)")

        lines.append("")
        lines.append("[1着コース別の2着外れ率]")
        lines.append("-" * 60)
        for course in sorted(results['by_winner_course'].keys()):
            data = results['by_winner_course'][course]
            if data['total'] > 0:
                rate = data['miss'] / data['total'] * 100
                lines.append(f"  {course}コース: {data['miss']}/{data['total']} ({rate:.1f}%)")

        lines.append("")
        lines.append("[2着外れ時の実際の2着コース]")
        lines.append("-" * 60)
        for course in sorted(results['actual_2nd_course_when_miss'].keys()):
            count = results['actual_2nd_course_when_miss'][course]
            pct = count / results['miss_2nd_in_234'] * 100 if results['miss_2nd_in_234'] > 0 else 0
            lines.append(f"  {course}コース: {count} ({pct:.1f}%)")

        return "\n".join(lines)


class SecondPlaceAnalyzer:
    """
    2着専門分析クラス

    1着が決まった後の2着予測精度向上のための分析
    """

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path

    def analyze_second_place_features(
        self,
        start_date: str = '2025-01-01',
        end_date: str = '2025-11-30'
    ) -> Dict:
        """
        2着になる艇の特徴を分析
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 2着艇の特徴を取得
            cursor.execute('''
                SELECT
                    e.pit_number,
                    e.motor_second_rate,
                    e.racer_rank,
                    r.venue_code,
                    e1.pit_number as winner_course,
                    COUNT(*) as count
                FROM results res
                JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
                JOIN races r ON res.race_id = r.id
                JOIN results res1 ON res.race_id = res1.race_id AND res1.rank = 1
                JOIN entries e1 ON res1.race_id = e1.race_id AND res1.pit_number = e1.pit_number
                WHERE res.rank = 2 AND res.is_invalid = 0
                  AND r.race_date >= ? AND r.race_date <= ?
                GROUP BY e.pit_number,
                         CASE WHEN e.motor_second_rate >= 0.35 THEN 'high'
                              WHEN e.motor_second_rate >= 0.28 THEN 'mid'
                              ELSE 'low' END,
                         e.racer_rank,
                         r.venue_code,
                         e1.pit_number
                HAVING count >= 5
                ORDER BY count DESC
            ''', (start_date, end_date))

            return cursor.fetchall()

    def get_second_place_candidates(
        self,
        race_id: int,
        winner_pit: int,
        top_n: int = 3
    ) -> List[Dict]:
        """
        2着候補を会場・コースパターンから取得
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # レース情報取得
            cursor.execute('''
                SELECT r.venue_code, e.pit_number
                FROM races r
                JOIN entries e ON r.id = e.race_id
                WHERE r.id = ? AND e.pit_number = ?
            ''', (race_id, winner_pit))
            row = cursor.fetchone()

            if not row:
                return []

            venue_code, winner_course = row

            # 同会場・同1着コースでの2着コース分布を取得
            cursor.execute('''
                SELECT
                    e2.pit_number,
                    COUNT(*) as count
                FROM results r1
                JOIN results r2 ON r1.race_id = r2.race_id
                JOIN entries e1 ON r1.race_id = e1.race_id AND r1.pit_number = e1.pit_number
                JOIN entries e2 ON r2.race_id = e2.race_id AND r2.pit_number = e2.pit_number
                JOIN races r ON r1.race_id = r.id
                WHERE r1.rank = 1 AND r2.rank = 2
                  AND r.venue_code = ?
                  AND e1.pit_number = ?
                  AND r1.is_invalid = 0 AND r2.is_invalid = 0
                GROUP BY e2.pit_number
                ORDER BY count DESC
                LIMIT ?
            ''', (venue_code, winner_course, top_n))

            results = []
            for course, count in cursor.fetchall():
                # このレースでそのコースにいる艇を取得
                cursor.execute('''
                    SELECT pit_number
                    FROM entries
                    WHERE race_id = ? AND pit_number = ?
                ''', (race_id, course))
                pit_row = cursor.fetchone()
                if pit_row:
                    results.append({
                        'course': course,
                        'pit_number': pit_row[0],
                        'historical_count': count
                    })

            return results


if __name__ == "__main__":
    # テスト実行
    print("=" * 80)
    print("外れパターン分析 テスト")
    print("=" * 80)

    analyzer = MissPatternAnalyzer()

    # 11月データで分析
    results = analyzer.analyze_second_place_misses('2025-11-01', '2025-11-30')
    print(analyzer.format_analysis_report(results))

    print("")
    print("=" * 80)
    print("会場別2着パターン（サンプル: 戸田）")
    print("=" * 80)

    venue_patterns = analyzer.analyze_venue_patterns('2025-01-01', '2025-11-30')
    if '02' in venue_patterns:  # 戸田
        print("\n戸田競艇場:")
        for w_course in sorted(venue_patterns['02'].keys()):
            print(f"  1着{w_course}コース時の2着コース:")
            total = sum(venue_patterns['02'][w_course].values())
            for s_course, count in sorted(venue_patterns['02'][w_course].items(), key=lambda x: -x[1]):
                pct = count / total * 100 if total > 0 else 0
                print(f"    {s_course}コース: {count} ({pct:.1f}%)")
