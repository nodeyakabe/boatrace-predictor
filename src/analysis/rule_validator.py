"""
法則検証システム
新規追加された法則の統計的信憑性を計算

機能:
- 法則の条件に合致するレースを抽出
- 実際の結果と法則の予測を比較
- 統計的有意性を検証（カイ二乗検定）
- 信頼度スコアを算出
"""

import sqlite3
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import math


class RuleValidator:
    """法則検証クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def validate_venue_rule(self, rule_id: int) -> Dict:
        """
        競艇場法則の信憑性を検証

        Args:
            rule_id: venue_rulesテーブルのID

        Returns:
            dict: {
                'rule_id': 法則ID,
                'description': 法則の説明,
                'sample_size': サンプル数,
                'hit_rate': 的中率（%）,
                'expected_rate': 期待的中率（%）,
                'improvement': 改善率（%）,
                'confidence_score': 信頼度スコア（0-100）,
                'p_value': p値（統計的有意性）,
                'is_significant': 統計的に有意か（p < 0.05）,
                'recommendation': 推奨（採用/要検証/棄却）
            }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 法則情報を取得
        cursor.execute("""
            SELECT venue_code, rule_type, condition_type, condition_value,
                   target_pit, effect_type, effect_value, description
            FROM venue_rules
            WHERE id = ?
        """, [rule_id])

        rule = cursor.fetchone()
        if not rule:
            conn.close()
            return {'error': '法則が見つかりません'}

        venue_code, rule_type, condition_type, condition_value, \
            target_pit, effect_type, effect_value, description = rule

        # 条件に合致するレースを抽出
        matching_races = self._get_matching_races(
            cursor, venue_code, condition_type, condition_value
        )

        conn.close()

        if len(matching_races) < 10:
            return {
                'rule_id': rule_id,
                'description': description,
                'sample_size': len(matching_races),
                'error': 'サンプル数が不足しています（最低10件必要）',
                'recommendation': '要検証（データ不足）'
            }

        # 的中率を計算
        hit_count = 0
        total_count = len(matching_races)

        for race_id in matching_races:
            if self._check_rule_hit(race_id, target_pit, effect_type):
                hit_count += 1

        hit_rate = (hit_count / total_count) * 100

        # 期待的中率（ベースライン）を計算
        expected_rate = self._get_expected_rate(effect_type, target_pit)

        # 改善率
        improvement = ((hit_rate - expected_rate) / expected_rate) * 100 if expected_rate > 0 else 0

        # 統計的有意性検証（カイ二乗検定）
        p_value = self._chi_square_test(hit_count, total_count, expected_rate)
        is_significant = p_value < 0.05

        # 信頼度スコア算出（0-100）
        confidence_score = self._calculate_confidence_score(
            hit_rate, expected_rate, total_count, p_value
        )

        # 推奨判定
        recommendation = self._get_recommendation(
            confidence_score, is_significant, improvement
        )

        return {
            'rule_id': rule_id,
            'description': description,
            'venue_code': venue_code,
            'condition': f'{condition_type}: {condition_value}',
            'target': f'{target_pit}号艇の{effect_type}',
            'sample_size': total_count,
            'hit_count': hit_count,
            'hit_rate': round(hit_rate, 2),
            'expected_rate': round(expected_rate, 2),
            'improvement': round(improvement, 2),
            'confidence_score': round(confidence_score, 2),
            'p_value': round(p_value, 4),
            'is_significant': is_significant,
            'recommendation': recommendation
        }

    def validate_racer_rule(self, rule_id: int) -> Dict:
        """
        選手法則の信憑性を検証

        Args:
            rule_id: racer_rulesテーブルのID

        Returns:
            dict: 検証結果
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 法則情報を取得
        cursor.execute("""
            SELECT racer_number, racer_name, rule_type, venue_code,
                   course_number, condition_type, effect_type, effect_value, description
            FROM racer_rules
            WHERE id = ?
        """, [rule_id])

        rule = cursor.fetchone()
        if not rule:
            conn.close()
            return {'error': '法則が見つかりません'}

        racer_number, racer_name, rule_type, venue_code, \
            course_number, condition_type, effect_type, effect_value, description = rule

        # 条件に合致するレースを抽出
        matching_races = self._get_matching_races_for_racer(
            cursor, racer_number, venue_code, course_number, condition_type
        )

        conn.close()

        if len(matching_races) < 10:
            return {
                'rule_id': rule_id,
                'description': description,
                'sample_size': len(matching_races),
                'error': 'サンプル数が不足しています（最低10件必要）',
                'recommendation': '要検証（データ不足）'
            }

        # 的中率を計算
        hit_count = 0
        total_count = len(matching_races)

        for race_id, pit_number in matching_races:
            if self._check_rule_hit(race_id, pit_number, effect_type):
                hit_count += 1

        hit_rate = (hit_count / total_count) * 100

        # 期待的中率（ベースライン）
        expected_rate = self._get_expected_rate(effect_type, course_number)

        # 改善率
        improvement = ((hit_rate - expected_rate) / expected_rate) * 100 if expected_rate > 0 else 0

        # 統計的有意性検証
        p_value = self._chi_square_test(hit_count, total_count, expected_rate)
        is_significant = p_value < 0.05

        # 信頼度スコア
        confidence_score = self._calculate_confidence_score(
            hit_rate, expected_rate, total_count, p_value
        )

        # 推奨判定
        recommendation = self._get_recommendation(
            confidence_score, is_significant, improvement
        )

        return {
            'rule_id': rule_id,
            'description': description,
            'racer_name': racer_name,
            'racer_number': racer_number,
            'venue': venue_code if venue_code else '全場',
            'course': f'{course_number}コース' if course_number else '全コース',
            'sample_size': total_count,
            'hit_count': hit_count,
            'hit_rate': round(hit_rate, 2),
            'expected_rate': round(expected_rate, 2),
            'improvement': round(improvement, 2),
            'confidence_score': round(confidence_score, 2),
            'p_value': round(p_value, 4),
            'is_significant': is_significant,
            'recommendation': recommendation
        }

    def _get_matching_races(self, cursor, venue_code: str,
                           condition_type: Optional[str],
                           condition_value: Optional[str]) -> List[int]:
        """条件に合致するレースIDリストを取得"""

        if condition_type == 'tide':
            # 潮汐条件（例: '干潮'）
            # TODO: 潮汐データが実装されたら対応
            return []

        elif condition_type == 'weather':
            # 天候条件
            query = """
                SELECT DISTINCT r.id
                FROM races r
                JOIN weather w ON r.venue_code = w.venue_code
                    AND r.race_date = w.weather_date
                WHERE r.venue_code = ?
                  AND w.weather = ?
                  AND r.race_date >= date('now', '-2 years')
                ORDER BY r.race_date DESC
                LIMIT 1000
            """
            cursor.execute(query, [venue_code, condition_value])

        elif condition_type == 'wind_speed':
            # 風速条件
            query = """
                SELECT DISTINCT r.id
                FROM races r
                JOIN weather w ON r.venue_code = w.venue_code
                    AND r.race_date = w.weather_date
                WHERE r.venue_code = ?
                  AND w.wind_speed >= ?
                  AND r.race_date >= date('now', '-2 years')
                ORDER BY r.race_date DESC
                LIMIT 1000
            """
            cursor.execute(query, [venue_code, float(condition_value)])

        else:
            # 条件なし（全レース）
            query = """
                SELECT id
                FROM races
                WHERE venue_code = ?
                  AND race_date >= date('now', '-2 years')
                ORDER BY race_date DESC
                LIMIT 1000
            """
            cursor.execute(query, [venue_code])

        return [row[0] for row in cursor.fetchall()]

    def _get_matching_races_for_racer(self, cursor, racer_number: str,
                                      venue_code: Optional[str],
                                      course_number: Optional[int],
                                      condition_type: Optional[str]) -> List[Tuple[int, int]]:
        """選手の条件に合致するレースIDとpit_numberリストを取得"""

        query_parts = ["""
            SELECT DISTINCT r.id, e.pit_number
            FROM races r
            JOIN entries e ON r.id = e.race_id
        """]

        conditions = ["e.racer_number = ?"]
        params = [racer_number]

        if venue_code:
            conditions.append("r.venue_code = ?")
            params.append(venue_code)

        if course_number:
            # 実際のコース（進入コース）
            query_parts.append("JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number")
            conditions.append("rd.actual_course = ?")
            params.append(course_number)

        conditions.append("r.race_date >= date('now', '-2 years')")

        query = " ".join(query_parts) + " WHERE " + " AND ".join(conditions)
        query += " ORDER BY r.race_date DESC LIMIT 1000"

        cursor.execute(query, params)
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def _check_rule_hit(self, race_id: int, pit_number: int, effect_type: str) -> bool:
        """法則が的中したかチェック"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if effect_type == '1着':
            cursor.execute("""
                SELECT 1
                FROM results
                WHERE race_id = ? AND pit_number = ? AND rank = 1
            """, [race_id, pit_number])
        elif effect_type == '2着以内':
            cursor.execute("""
                SELECT 1
                FROM results
                WHERE race_id = ? AND pit_number = ? AND rank <= 2
            """, [race_id, pit_number])
        elif effect_type == '3着以内':
            cursor.execute("""
                SELECT 1
                FROM results
                WHERE race_id = ? AND pit_number = ? AND rank <= 3
            """, [race_id, pit_number])
        else:
            conn.close()
            return False

        result = cursor.fetchone()
        conn.close()
        return result is not None

    def _get_expected_rate(self, effect_type: str, target_pit: Optional[int]) -> float:
        """期待的中率（ベースライン）を取得"""

        # コース別の平均1着率（競艇の一般的な統計）
        course_win_rates = {
            1: 55.0,  # 1コース
            2: 14.0,  # 2コース
            3: 12.0,  # 3コース
            4: 10.0,  # 4コース
            5: 6.0,   # 5コース
            6: 3.0    # 6コース
        }

        course_quinella_rates = {
            1: 70.0,
            2: 40.0,
            3: 35.0,
            4: 30.0,
            5: 25.0,
            6: 20.0
        }

        course_trifecta_rates = {
            1: 80.0,
            2: 55.0,
            3: 50.0,
            4: 45.0,
            5: 40.0,
            6: 35.0
        }

        if effect_type == '1着':
            return course_win_rates.get(target_pit, 16.7)  # 1/6 = 16.7%
        elif effect_type == '2着以内':
            return course_quinella_rates.get(target_pit, 33.3)  # 2/6 = 33.3%
        elif effect_type == '3着以内':
            return course_trifecta_rates.get(target_pit, 50.0)  # 3/6 = 50.0%

        return 16.7

    def _chi_square_test(self, hit_count: int, total_count: int,
                        expected_rate: float) -> float:
        """
        カイ二乗検定でp値を算出

        Returns:
            float: p値（0-1）、小さいほど統計的に有意
        """
        expected_hit = total_count * (expected_rate / 100)
        expected_miss = total_count * (1 - expected_rate / 100)

        miss_count = total_count - hit_count

        # カイ二乗統計量
        chi_square = 0
        if expected_hit > 0:
            chi_square += ((hit_count - expected_hit) ** 2) / expected_hit
        if expected_miss > 0:
            chi_square += ((miss_count - expected_miss) ** 2) / expected_miss

        # 自由度1のカイ二乗分布のp値（簡易計算）
        # 正確にはscipy.stats.chi2.sf()を使うべきだが、ここでは近似式
        if chi_square > 10.83:
            return 0.001
        elif chi_square > 7.88:
            return 0.005
        elif chi_square > 6.63:
            return 0.01
        elif chi_square > 3.84:
            return 0.05
        elif chi_square > 2.71:
            return 0.10
        else:
            return 0.50  # 有意差なし

    def _calculate_confidence_score(self, hit_rate: float, expected_rate: float,
                                    sample_size: int, p_value: float) -> float:
        """
        信頼度スコアを算出（0-100）

        要素:
        - 改善率（的中率 vs 期待的中率）
        - サンプル数
        - 統計的有意性（p値）
        """
        # 改善率スコア（0-40点）
        improvement = ((hit_rate - expected_rate) / expected_rate) * 100 if expected_rate > 0 else 0
        improvement_score = min(40, max(0, improvement * 2))  # 20%改善で40点

        # サンプル数スコア（0-30点）
        if sample_size >= 100:
            sample_score = 30
        elif sample_size >= 50:
            sample_score = 25
        elif sample_size >= 30:
            sample_score = 20
        else:
            sample_score = 10

        # 統計的有意性スコア（0-30点）
        if p_value < 0.001:
            significance_score = 30
        elif p_value < 0.01:
            significance_score = 25
        elif p_value < 0.05:
            significance_score = 20
        elif p_value < 0.10:
            significance_score = 10
        else:
            significance_score = 0

        return improvement_score + sample_score + significance_score

    def _get_recommendation(self, confidence_score: float,
                          is_significant: bool, improvement: float) -> str:
        """推奨判定"""

        if confidence_score >= 70 and is_significant and improvement > 10:
            return '✅ 採用推奨（信頼性高）'
        elif confidence_score >= 50 and is_significant:
            return '⚠️ 条件付き採用（要注意）'
        elif confidence_score >= 30:
            return '🔍 要検証（データ追加必要）'
        else:
            return '❌ 棄却推奨（信頼性低）'


if __name__ == "__main__":
    # テスト実行
    validator = RuleValidator()

    print("="*80)
    print("法則検証システム - テスト実行")
    print("="*80)

    # 若松競艇場の法則を検証（例）
    result = validator.validate_venue_rule(1)

    if 'error' not in result:
        print(f"\n法則: {result['description']}")
        print(f"サンプル数: {result['sample_size']}件")
        print(f"的中率: {result['hit_rate']}%")
        print(f"期待的中率: {result['expected_rate']}%")
        print(f"改善率: {result['improvement']:+.2f}%")
        print(f"信頼度スコア: {result['confidence_score']}/100")
        print(f"p値: {result['p_value']}")
        print(f"統計的有意: {'はい' if result['is_significant'] else 'いいえ'}")
        print(f"\n推奨: {result['recommendation']}")
    else:
        print(f"エラー: {result.get('error', 'Unknown')}")
