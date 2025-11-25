"""
進入コース変化の分析
選手の前付け傾向、枠なり率を計算
"""

import sqlite3
from typing import Dict, Optional
from datetime import datetime, timedelta
from config.settings import DATABASE_PATH


class CourseChangeAnalyzer:
    """進入変化分析クラス"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = DATABASE_PATH
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def calculate_racer_course_change_tendency(
        self,
        racer_number: int,
        days: int = 180
    ) -> Dict[str, any]:
        """
        選手の進入変化傾向を計算

        Args:
            racer_number: 選手登録番号
            days: 集計期間（日数）

        Returns:
            {
                'total_races': 総レース数,
                'course_change_rate': 進入変化率,
                'forward_move_rate': 前付け率（枠番より内に入る率）,
                'stay_rate': 枠なり率,
                'backward_move_rate': 後退率,
                'avg_course_diff': 平均コース差（負=前付け傾向）
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # 進入データを取得（actual_courseがあるレースのみ）
        cursor.execute("""
            SELECT
                e.pit_number,
                rd.actual_course
            FROM entries e
            JOIN races ra ON e.race_id = ra.id
            JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date >= ?
              AND rd.actual_course IS NOT NULL
        """, (racer_number, start_date))

        course_data = cursor.fetchall()
        conn.close()

        if len(course_data) == 0:
            return {
                'total_races': 0,
                'course_change_rate': 0.0,
                'forward_move_rate': 0.0,
                'stay_rate': 0.0,
                'backward_move_rate': 0.0,
                'avg_course_diff': 0.0
            }

        total_races = len(course_data)
        course_changes = 0
        forward_moves = 0
        stays = 0
        backward_moves = 0
        course_diffs = []

        for pit_number, actual_course in course_data:
            diff = actual_course - pit_number  # 正=後退、負=前付け

            course_diffs.append(diff)

            if diff != 0:
                course_changes += 1

                if diff < 0:
                    forward_moves += 1  # 前付け
                else:
                    backward_moves += 1  # 後退
            else:
                stays += 1  # 枠なり

        return {
            'total_races': total_races,
            'course_change_rate': course_changes / total_races,
            'forward_move_rate': forward_moves / total_races,
            'stay_rate': stays / total_races,
            'backward_move_rate': backward_moves / total_races,
            'avg_course_diff': sum(course_diffs) / len(course_diffs) if course_diffs else 0.0
        }

    def predict_course_change_impact(
        self,
        race_id: int
    ) -> Dict[int, Dict]:
        """
        レース全体の進入変化リスクを予測

        Args:
            race_id: レースID

        Returns:
            {
                1: {'forward_move_risk': 0.1, 'likely_course': 1},
                2: {'forward_move_risk': 0.3, 'likely_course': 1},
                ...
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        # レースの出走選手を取得
        cursor.execute("""
            SELECT
                e.pit_number,
                e.racer_number,
                e.racer_name
            FROM entries e
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        """, (race_id,))

        entries = cursor.fetchall()
        conn.close()

        predictions = {}

        for pit_number, racer_number, racer_name in entries:
            # 選手の進入傾向を取得
            tendency = self.calculate_racer_course_change_tendency(racer_number)

            # 前付けリスク判定
            forward_move_risk = tendency['forward_move_rate']

            # 推定コース（枠なり率が高ければpit_number、前付け傾向が強ければ内側）
            if tendency['total_races'] >= 30:
                if forward_move_risk >= 0.3:
                    # 前付け傾向が強い
                    likely_course = max(1, pit_number - 1)
                elif tendency['backward_move_rate'] >= 0.2:
                    # 後退傾向
                    likely_course = min(6, pit_number + 1)
                else:
                    # 枠なり
                    likely_course = pit_number
            else:
                # データ不足の場合は枠なりと仮定
                likely_course = pit_number

            predictions[pit_number] = {
                'forward_move_risk': forward_move_risk,
                'likely_course': likely_course,
                'tendency_data_available': tendency['total_races'] >= 30,
                'racer_number': racer_number,
                'racer_name': racer_name
            }

        return predictions

    def should_adjust_first_place_lock(
        self,
        race_id: int
    ) -> Dict[str, any]:
        """
        進入変化リスクにより1着固定を外すべきかを判定

        Args:
            race_id: レースID

        Returns:
            {
                'should_unlock': bool,  # 固定を外すべきか
                'reason': str  # 理由
            }
        """
        course_predictions = self.predict_course_change_impact(race_id)

        # 2-4号艇で前付け傾向が強い選手がいるか
        high_risk_pits = []

        for pit_number in [2, 3, 4]:
            if pit_number in course_predictions:
                pred = course_predictions[pit_number]

                if pred['forward_move_risk'] >= 0.3 and pred['tendency_data_available']:
                    high_risk_pits.append(pit_number)

        if len(high_risk_pits) > 0:
            return {
                'should_unlock': True,
                'reason': f'前付け傾向の選手あり（{high_risk_pits}号艇）'
            }

        return {
            'should_unlock': False,
            'reason': '進入変化リスク低'
        }
