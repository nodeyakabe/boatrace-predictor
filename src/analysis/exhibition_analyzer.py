"""
展示航走データの分析と補正計算
"""

import sqlite3
from typing import Dict, Optional, Tuple
from config.settings import DATABASE_PATH


class ExhibitionAnalyzer:
    """展示航走データに基づく予測補正"""

    def __init__(self):
        self.conn = sqlite3.connect(DATABASE_PATH)
        self.cursor = self.conn.cursor()

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

    def calculate_exhibition_adjustment(
        self,
        race_id: int,
        pit_number: int
    ) -> Dict[str, float]:
        """
        展示データに基づく補正値を計算

        Returns:
            {
                'motor_adjustment': モーター性能補正（-10 ~ +10点）
                'racer_adjustment': 選手評価補正（-5 ~ +5点）
                'confidence_adjustment': 信頼度への影響（-0.1 ~ +0.1）
                'reason': 補正理由
            }
        """
        # 展示データを取得
        self.cursor.execute("""
            SELECT
                exhibition_time,
                start_timing,
                turn_quality,
                weight_change
            FROM exhibition_data
            WHERE race_id = ? AND pit_number = ?
        """, (race_id, pit_number))

        row = self.cursor.fetchone()
        if not row:
            return {
                'motor_adjustment': 0.0,
                'racer_adjustment': 0.0,
                'confidence_adjustment': 0.0,
                'reason': '展示データなし'
            }

        exhibition_time, start_timing, turn_quality, weight_change = row

        motor_adj = 0.0
        racer_adj = 0.0
        conf_adj = 0.0
        reasons = []

        # 1. 展示タイムによるモーター補正
        if exhibition_time:
            # 同レースの他艇との比較
            self.cursor.execute("""
                SELECT exhibition_time
                FROM exhibition_data
                WHERE race_id = ? AND exhibition_time IS NOT NULL
                ORDER BY exhibition_time
            """, (race_id,))

            times = [t[0] for t in self.cursor.fetchall()]
            if len(times) >= 3:
                avg_time = sum(times) / len(times)
                time_diff = avg_time - exhibition_time  # 正の値 = 速い

                if time_diff >= 0.3:
                    motor_adj += 8.0
                    conf_adj += 0.08
                    reasons.append(f"展示タイム優秀（平均より{time_diff:.2f}秒速い）")
                elif time_diff >= 0.15:
                    motor_adj += 4.0
                    conf_adj += 0.04
                    reasons.append(f"展示タイム良好（平均より{time_diff:.2f}秒速い）")
                elif time_diff <= -0.3:
                    motor_adj -= 8.0
                    conf_adj -= 0.05
                    reasons.append(f"展示タイム不良（平均より{-time_diff:.2f}秒遅い）")
                elif time_diff <= -0.15:
                    motor_adj -= 4.0
                    conf_adj -= 0.03
                    reasons.append(f"展示タイム遅め（平均より{-time_diff:.2f}秒遅い）")

        # 2. スタートタイミング評価
        if start_timing:
            if start_timing >= 4:
                racer_adj += 3.0
                conf_adj += 0.03
                reasons.append(f"スタート評価良好（{start_timing}/5）")
            elif start_timing <= 2:
                racer_adj -= 3.0
                conf_adj -= 0.02
                reasons.append(f"スタート評価不安（{start_timing}/5）")

        # 3. ターン評価
        if turn_quality:
            if turn_quality >= 4:
                racer_adj += 2.0
                conf_adj += 0.02
                reasons.append(f"ターン評価良好（{turn_quality}/5）")
            elif turn_quality <= 2:
                racer_adj -= 2.0
                conf_adj -= 0.02
                reasons.append(f"ターン評価不安（{turn_quality}/5）")

        # 4. 体重変化（大幅な増減は不調のサイン）
        if weight_change:
            if abs(weight_change) >= 2.0:
                racer_adj -= 3.0
                conf_adj -= 0.03
                reasons.append(f"体重変化大（{weight_change:+.1f}kg）")

        return {
            'motor_adjustment': round(motor_adj, 2),
            'racer_adjustment': round(racer_adj, 2),
            'confidence_adjustment': round(conf_adj, 3),
            'reason': ' / '.join(reasons) if reasons else '展示データ影響なし'
        }

    def calculate_course_change_adjustment(
        self,
        race_id: int,
        pit_number: int,
        expected_course: int
    ) -> Dict[str, float]:
        """
        実際の進入コース変化による補正

        Args:
            expected_course: 予想していたコース（通常は枠番と同じ）

        Returns:
            {
                'course_adjustment': コース点への補正（-30 ~ +30点）
                'confidence_adjustment': 信頼度への影響（-0.2 ~ +0.2）
                'reason': 補正理由
            }
        """
        # 実際の進入コースを取得
        self.cursor.execute("""
            SELECT actual_course
            FROM actual_courses
            WHERE race_id = ? AND pit_number = ?
        """, (race_id, pit_number))

        row = self.cursor.fetchone()
        if not row:
            return {
                'course_adjustment': 0.0,
                'confidence_adjustment': 0.0,
                'reason': '進入コース情報なし'
            }

        actual_course = row[0]

        if actual_course == expected_course:
            return {
                'course_adjustment': 0.0,
                'confidence_adjustment': 0.0,
                'reason': f'進入予想通り（{actual_course}コース）'
            }

        # コース変化による補正
        course_adj = 0.0
        conf_adj = 0.0
        reason = ''

        # 会場のコース別勝率を取得
        self.cursor.execute("""
            SELECT venue_code FROM races WHERE id = ?
        """, (race_id,))
        venue_code = self.cursor.fetchone()[0]

        # 実際のコースと予想コースの勝率差を計算
        self.cursor.execute("""
            SELECT
                e.pit_number as course,
                COUNT(*) as total,
                SUM(CASE WHEN CAST(rank AS INTEGER) = 1 THEN 1 ELSE 0 END) as wins
            FROM entries e
            JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
            JOIN races ra ON e.race_id = ra.id
            WHERE ra.venue_code = ? AND e.pit_number IN (?, ?)
            GROUP BY e.pit_number
        """, (venue_code, expected_course, actual_course))

        course_stats = {row[0]: row[2] / row[1] * 100 for row in self.cursor.fetchall()}

        if expected_course in course_stats and actual_course in course_stats:
            expected_rate = course_stats[expected_course]
            actual_rate = course_stats[actual_course]
            rate_diff = actual_rate - expected_rate

            # 勝率差を点数に変換（1%差 = 約0.8点）
            course_adj = rate_diff * 0.8

            # 信頼度への影響（大きな変化は予測の不確実性を増す）
            conf_adj = -abs(rate_diff) * 0.01

            reason = f'進入変化 {expected_course}→{actual_course}コース（勝率{rate_diff:+.1f}%）'
        else:
            reason = f'進入変化 {expected_course}→{actual_course}コース（統計データ不足）'

        return {
            'course_adjustment': round(course_adj, 2),
            'confidence_adjustment': round(conf_adj, 3),
            'reason': reason
        }

    def calculate_weather_adjustment(
        self,
        race_id: int,
        pit_number: int
    ) -> Dict[str, float]:
        """
        天候・風向による補正

        Returns:
            {
                'course_adjustment': コース点への補正（-5 ~ +5点）
                'confidence_adjustment': 信頼度への影響（-0.05 ~ +0.05）
                'reason': 補正理由
            }
        """
        # レース条件を取得
        self.cursor.execute("""
            SELECT
                weather,
                wind_direction,
                wind_speed,
                wave_height
            FROM race_conditions
            WHERE race_id = ?
        """, (race_id,))

        row = self.cursor.fetchone()
        if not row:
            return {
                'course_adjustment': 0.0,
                'confidence_adjustment': 0.0,
                'reason': '気象データなし'
            }

        weather, wind_direction, wind_speed, wave_height = row

        course_adj = 0.0
        conf_adj = 0.0
        reasons = []

        # コース情報を取得（コースは通常pit_numberと同じ）
        # 実際の進入コースがあればそれを使用、なければpit_numberを使用
        self.cursor.execute("""
            SELECT actual_course
            FROM actual_courses
            WHERE race_id = ? AND pit_number = ?
        """, (race_id, pit_number))

        course_row = self.cursor.fetchone()
        if course_row:
            course = course_row[0]
        else:
            # 実際の進入データがなければpit_numberをコースとして使用
            course = pit_number

        # 1. 風向・風速の影響
        if wind_speed and wind_speed >= 3.0:
            if wind_direction == '向い風':
                if course == 1:
                    # インコースは向い風に強い
                    course_adj += 2.0
                    conf_adj += 0.02
                    reasons.append(f'向い風{wind_speed:.1f}m/s（イン有利）')
                else:
                    # 外コースは不利
                    course_adj -= 1.0
                    reasons.append(f'向い風{wind_speed:.1f}m/s（外不利）')
            elif wind_direction == '追い風':
                if course == 1:
                    # インコースは追い風に弱い
                    course_adj -= 2.0
                    conf_adj -= 0.02
                    reasons.append(f'追い風{wind_speed:.1f}m/s（イン不利）')
                else:
                    # 外コースは有利
                    course_adj += 1.0
                    reasons.append(f'追い風{wind_speed:.1f}m/s（外有利）')

        # 2. 荒天の影響
        if weather == '雨' and wind_speed and wind_speed >= 5.0:
            conf_adj -= 0.03
            reasons.append('荒天（予測困難）')

        # 3. 波高の影響
        if wave_height and wave_height >= 5:
            if course == 1:
                course_adj -= 1.5
                reasons.append(f'波高{wave_height}cm（イン不利）')
            conf_adj -= 0.02

        return {
            'course_adjustment': round(course_adj, 2),
            'confidence_adjustment': round(conf_adj, 3),
            'reason': ' / '.join(reasons) if reasons else '気象影響軽微'
        }

    def get_all_adjustments(
        self,
        race_id: int,
        pit_number: int,
        expected_course: int
    ) -> Dict[str, any]:
        """
        すべての補正を統合して取得

        Returns:
            {
                'motor_score_adjustment': モーター点への補正
                'racer_score_adjustment': 選手点への補正
                'course_score_adjustment': コース点への補正
                'confidence_adjustment': 信頼度への補正
                'reasons': 補正理由のリスト
            }
        """
        # 各補正を取得
        exhibition = self.calculate_exhibition_adjustment(race_id, pit_number)
        course_change = self.calculate_course_change_adjustment(race_id, pit_number, expected_course)
        weather = self.calculate_weather_adjustment(race_id, pit_number)

        # 統合
        return {
            'motor_score_adjustment': exhibition['motor_adjustment'],
            'racer_score_adjustment': exhibition['racer_adjustment'],
            'course_score_adjustment': course_change['course_adjustment'] + weather['course_adjustment'],
            'confidence_adjustment': (
                exhibition['confidence_adjustment'] +
                course_change['confidence_adjustment'] +
                weather['confidence_adjustment']
            ),
            'reasons': [
                exhibition['reason'],
                course_change['reason'],
                weather['reason']
            ]
        }
