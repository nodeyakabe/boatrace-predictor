"""
予測更新と変更点追跡
"""

import sqlite3
from typing import Dict, List, Optional
from datetime import datetime
from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor
from src.analysis.exhibition_analyzer import ExhibitionAnalyzer


class PredictionUpdater:
    """レース直前データに基づく予測更新"""

    def __init__(self):
        self.conn = sqlite3.connect(DATABASE_PATH)
        self.cursor = self.conn.cursor()
        self.predictor = RacePredictor()
        self.exhibition_analyzer = ExhibitionAnalyzer()

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

    def save_initial_prediction_to_history(self, race_id: int) -> bool:
        """
        現在のrace_predictionsテーブルの予測を履歴に保存

        Args:
            race_id: レースID

        Returns:
            bool: 保存成功したか
        """
        try:
            # 既存の初期予測を取得
            self.cursor.execute("""
                SELECT
                    pit_number,
                    rank_prediction,
                    confidence,
                    total_score
                FROM race_predictions
                WHERE race_id = ?
            """, (race_id,))

            predictions = self.cursor.fetchall()

            if not predictions:
                return False

            # 履歴テーブルに保存
            for pit_number, rank_prediction, confidence, total_score in predictions:
                self.cursor.execute("""
                    INSERT INTO prediction_history (
                        race_id,
                        pit_number,
                        prediction_type,
                        rank_prediction,
                        confidence,
                        total_score,
                        has_exhibition_data,
                        has_condition_data,
                        has_course_data
                    ) VALUES (?, ?, 'initial', ?, ?, ?, 0, 0, 0)
                """, (race_id, pit_number, rank_prediction, confidence, total_score))

            self.conn.commit()
            return True

        except Exception as e:
            print(f"初期予測保存エラー: {e}")
            return False

    def update_prediction_with_exhibition_data(self, race_id: int) -> Dict[str, any]:
        """
        展示航走・気象・進入データで予測を更新

        Args:
            race_id: レースID

        Returns:
            {
                'success': bool,
                'updated_pits': [更新された艇番のリスト],
                'changes': {pit_number: 変更内容},
                'error': エラーメッセージ（失敗時）
            }
        """
        try:
            # 初期予測を履歴に保存
            if not self.save_initial_prediction_to_history(race_id):
                return {
                    'success': False,
                    'error': '初期予測が見つかりません'
                }

            # 利用可能なデータを確認
            self.cursor.execute("""
                SELECT COUNT(*) FROM exhibition_data WHERE race_id = ?
            """, (race_id,))
            has_exhibition = self.cursor.fetchone()[0] > 0

            self.cursor.execute("""
                SELECT COUNT(*) FROM race_conditions WHERE race_id = ?
            """, (race_id,))
            has_conditions = self.cursor.fetchone()[0] > 0

            self.cursor.execute("""
                SELECT COUNT(*) FROM actual_courses WHERE race_id = ?
            """, (race_id,))
            has_courses = self.cursor.fetchone()[0] > 0

            if not (has_exhibition or has_conditions or has_courses):
                return {
                    'success': False,
                    'error': 'レース直前データがありません'
                }

            # 全艇の予測を更新
            self.cursor.execute("""
                SELECT pit_number
                FROM entries
                WHERE race_id = ?
            """, (race_id,))

            entries = self.cursor.fetchall()
            changes = {}

            for (pit_number,) in entries:
                # 予定コースは通常pit_numberと同じ
                expected_course = pit_number
                # 初期予測を取得
                self.cursor.execute("""
                    SELECT
                        rank_prediction,
                        total_score,
                        COALESCE(course_score, 0),
                        COALESCE(racer_score, 0),
                        COALESCE(motor_score, 0),
                        COALESCE(kimarite_score, 0),
                        COALESCE(grade_score, 0),
                        confidence
                    FROM race_predictions
                    WHERE race_id = ? AND pit_number = ?
                """, (race_id, pit_number))

                initial = self.cursor.fetchone()
                if not initial:
                    continue

                (initial_rank, initial_total, initial_course_score,
                 initial_racer_score, initial_motor_score,
                 initial_kimarite_score, initial_grade_score,
                 initial_confidence) = initial

                # 補正を取得
                adjustments = self.exhibition_analyzer.get_all_adjustments(
                    race_id, pit_number, expected_course
                )

                # 新しいスコアを計算
                new_course_score = initial_course_score + adjustments['course_score_adjustment']
                new_racer_score = initial_racer_score + adjustments['racer_score_adjustment']
                new_motor_score = initial_motor_score + adjustments['motor_score_adjustment']
                new_total_score = (
                    new_course_score +
                    new_racer_score +
                    new_motor_score +
                    initial_kimarite_score +
                    initial_grade_score
                )

                # 信頼度を再計算
                base_confidence = self._calculate_confidence(new_total_score)
                confidence_adj = adjustments['confidence_adjustment']
                new_confidence = self._adjust_confidence(base_confidence, confidence_adj)

                # 変更を記録
                if (abs(new_total_score - initial_total) >= 0.5 or
                    new_confidence != initial_confidence):
                    changes[pit_number] = {
                        'initial': {
                            'rank': initial_rank,
                            'total_score': initial_total,
                            'confidence': initial_confidence,
                            'course_score': initial_course_score,
                            'racer_score': initial_racer_score,
                            'motor_score': initial_motor_score
                        },
                        'updated': {
                            'total_score': new_total_score,
                            'confidence': new_confidence,
                            'course_score': new_course_score,
                            'racer_score': new_racer_score,
                            'motor_score': new_motor_score
                        },
                        'adjustments': {
                            'course': adjustments['course_score_adjustment'],
                            'racer': adjustments['racer_score_adjustment'],
                            'motor': adjustments['motor_score_adjustment'],
                            'confidence': confidence_adj
                        },
                        'reasons': adjustments['reasons']
                    }

                # 更新予測をrace_predictionsテーブルに保存
                self.cursor.execute("""
                    UPDATE race_predictions
                    SET
                        total_score = ?,
                        course_score = ?,
                        racer_score = ?,
                        motor_score = ?,
                        kimarite_score = ?,
                        grade_score = ?,
                        confidence = ?
                    WHERE race_id = ? AND pit_number = ?
                """, (new_total_score, new_course_score, new_racer_score,
                      new_motor_score, initial_kimarite_score, initial_grade_score,
                      new_confidence, race_id, pit_number))

                # 履歴テーブルに更新予測を保存
                self.cursor.execute("""
                    INSERT INTO prediction_history (
                        race_id,
                        pit_number,
                        prediction_type,
                        rank_prediction,
                        confidence,
                        total_score,
                        course_score,
                        racer_score,
                        motor_score,
                        kimarite_score,
                        grade_score,
                        has_exhibition_data,
                        has_condition_data,
                        has_course_data
                    ) VALUES (?, ?, 'updated', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (race_id, pit_number, initial_rank, new_confidence,
                      new_total_score, new_course_score, new_racer_score,
                      new_motor_score, initial_kimarite_score, initial_grade_score,
                      has_exhibition, has_conditions, has_courses))

            # 順位を再計算
            self._recalculate_rankings(race_id)

            self.conn.commit()

            return {
                'success': True,
                'updated_pits': list(changes.keys()),
                'changes': changes,
                'data_sources': {
                    'exhibition': has_exhibition,
                    'conditions': has_conditions,
                    'courses': has_courses
                }
            }

        except Exception as e:
            self.conn.rollback()
            return {
                'success': False,
                'error': str(e)
            }

    def _calculate_confidence(self, total_score: float) -> str:
        """スコアから信頼度を計算"""
        if total_score >= 75:
            return 'A'
        elif total_score >= 65:
            return 'B'
        elif total_score >= 55:
            return 'C'
        elif total_score >= 45:
            return 'D'
        else:
            return 'E'

    def _adjust_confidence(self, base_confidence: str, adjustment: float) -> str:
        """補正値を考慮して信頼度を調整"""
        confidence_levels = ['E', 'D', 'C', 'B', 'A']
        current_index = confidence_levels.index(base_confidence)

        # 補正値が大きければランクアップ、小さければランクダウン
        if adjustment >= 0.15:
            new_index = min(current_index + 1, len(confidence_levels) - 1)
        elif adjustment <= -0.15:
            new_index = max(current_index - 1, 0)
        else:
            new_index = current_index

        return confidence_levels[new_index]

    def _recalculate_rankings(self, race_id: int):
        """総合得点に基づいて順位を再計算"""
        # 全艇のスコアを取得してソート
        self.cursor.execute("""
            SELECT pit_number, total_score
            FROM race_predictions
            WHERE race_id = ?
            ORDER BY total_score DESC
        """, (race_id,))

        ranked_pits = self.cursor.fetchall()

        # 順位を更新
        for rank, (pit_number, _) in enumerate(ranked_pits, 1):
            self.cursor.execute("""
                UPDATE race_predictions
                SET rank_prediction = ?
                WHERE race_id = ? AND pit_number = ?
            """, (rank, race_id, pit_number))

    def compare_predictions(self, race_id: int) -> Optional[Dict]:
        """
        初期予測と更新予測を比較

        Returns:
            {
                'race_id': レースID,
                'has_initial': 初期予測があるか,
                'has_updated': 更新予測があるか,
                'comparisons': [
                    {
                        'pit_number': 艇番,
                        'initial': 初期予測,
                        'updated': 更新予測,
                        'changed': 変更があったか,
                        'score_diff': スコア差,
                        'rank_changed': 順位変化
                    },
                    ...
                ]
            }
        """
        # 初期予測を取得
        self.cursor.execute("""
            SELECT
                pit_number,
                rank_prediction,
                confidence,
                total_score
            FROM prediction_history
            WHERE race_id = ? AND prediction_type = 'initial'
        """, (race_id,))

        initial_preds = {row[0]: {
            'rank': row[1],
            'confidence': row[2],
            'total_score': row[3]
        } for row in self.cursor.fetchall()}

        # 更新予測を取得
        self.cursor.execute("""
            SELECT
                pit_number,
                rank_prediction,
                confidence,
                total_score
            FROM prediction_history
            WHERE race_id = ? AND prediction_type = 'updated'
        """, (race_id,))

        updated_preds = {row[0]: {
            'rank': row[1],
            'confidence': row[2],
            'total_score': row[3]
        } for row in self.cursor.fetchall()}

        if not initial_preds:
            return None

        # 比較結果を生成
        comparisons = []
        for pit_number in sorted(initial_preds.keys()):
            initial = initial_preds[pit_number]
            updated = updated_preds.get(pit_number)

            if updated:
                score_diff = updated['total_score'] - initial['total_score']
                rank_changed = updated['rank'] != initial['rank']
                confidence_changed = updated['confidence'] != initial['confidence']
                changed = abs(score_diff) >= 0.5 or rank_changed or confidence_changed
            else:
                score_diff = 0
                rank_changed = False
                changed = False

            comparisons.append({
                'pit_number': pit_number,
                'initial': initial,
                'updated': updated if updated else initial,
                'changed': changed,
                'score_diff': score_diff,
                'rank_changed': rank_changed
            })

        return {
            'race_id': race_id,
            'has_initial': len(initial_preds) > 0,
            'has_updated': len(updated_preds) > 0,
            'comparisons': comparisons
        }
