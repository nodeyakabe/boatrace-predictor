"""
予測更新と変更点追跡
"""

import sqlite3
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor
from src.analysis.exhibition_analyzer import ExhibitionAnalyzer
from src.database.data_manager import DataManager

logger = logging.getLogger(__name__)


class PredictionUpdater:
    """レース直前データに基づく予測更新"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = DATABASE_PATH

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.predictor = RacePredictor(db_path=db_path, use_cache=True)
        self.exhibition_analyzer = ExhibitionAnalyzer()
        self.data_manager = DataManager(db_path)

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

    def check_beforeinfo_exists(self, race_id: int) -> bool:
        """
        直前情報（展示データ）が存在するかチェック

        Args:
            race_id: レースID

        Returns:
            直前情報が存在する場合True
        """
        try:
            # race_detailsのbeforeinfo列をチェック
            self.cursor.execute("""
                SELECT beforeinfo
                FROM race_details
                WHERE race_id = ?
            """, (race_id,))

            row = self.cursor.fetchone()
            if row and row[0]:
                # beforeinfoが存在する（NULLでも空文字でもない）
                return True

            return False

        except Exception as e:
            logger.error(f"直前情報チェックエラー: {e}", exc_info=True)
            return False

    def update_to_before_prediction(self, race_id: int, force: bool = False) -> bool:
        """
        レースの予想を直前予想（before）に更新

        prediction_type='before'として新規保存

        Args:
            race_id: レースID
            force: Trueの場合、展示データがなくても強制更新

        Returns:
            更新成功: True, 失敗: False
        """
        try:
            # 直前情報の存在チェック
            has_beforeinfo = self.check_beforeinfo_exists(race_id)

            if not has_beforeinfo and not force:
                logger.warning(f"Race {race_id}: 直前情報が存在しないため更新をスキップ")
                return False

            # 既に直前予想が存在するかチェック
            existing = self.data_manager.get_race_predictions(race_id, prediction_type='before')
            if existing and not force:
                logger.info(f"Race {race_id}: 直前予想は既に存在します")
                return True

            # 予想を生成
            logger.info(f"Race {race_id}: 直前予想を生成中...")
            predictions = self.predictor.predict_race(race_id)

            if not predictions:
                logger.error(f"Race {race_id}: 予想生成に失敗")
                return False

            # 直前予想として保存
            success = self.data_manager.save_race_predictions(
                race_id=race_id,
                predictions=predictions,
                prediction_type='before'
            )

            if success:
                logger.info(f"Race {race_id}: 直前予想を保存しました")
            else:
                logger.error(f"Race {race_id}: 直前予想の保存に失敗")

            return success

        except Exception as e:
            logger.error(f"Race {race_id}: 直前予想更新エラー - {e}", exc_info=True)
            return False

    def update_daily_before_predictions(
        self,
        target_date: str,
        hours_before_deadline: float = 0.33
    ) -> Dict[str, int]:
        """
        指定日の全レースについて、締切前のレースの直前予想を更新

        Args:
            target_date: 対象日（YYYY-MM-DD）
            hours_before_deadline: 締切何時間前までを対象とするか（デフォルト: 20分前 = 0.33時間）

        Returns:
            {'total': 対象レース数, 'updated': 更新成功数, 'skipped': スキップ数, 'failed': 失敗数}
        """
        try:
            # 指定日のレース一覧を取得
            self.cursor.execute("""
                SELECT r.id, r.race_date, r.race_time
                FROM races r
                WHERE r.race_date = ?
                ORDER BY r.venue_code, r.race_number
            """, (target_date,))

            races = self.cursor.fetchall()

            if not races:
                logger.info(f"{target_date}: 対象レースが見つかりません")
                return {'total': 0, 'updated': 0, 'skipped': 0, 'failed': 0}

            # 現在時刻
            now = datetime.now()

            # 日次データを一括ロード（高速化）
            if self.predictor.batch_loader:
                logger.info(f"{target_date}: 日次データを一括ロード中...")
                self.predictor.batch_loader.load_daily_data(target_date)

            stats = {'total': 0, 'updated': 0, 'skipped': 0, 'failed': 0}

            for race_id, race_date, race_time in races:
                stats['total'] += 1

                # レース締切時刻を計算
                if race_time:
                    deadline_dt = datetime.strptime(f"{race_date} {race_time}", "%Y-%m-%d %H:%M:%S")
                    deadline_dt -= timedelta(hours=hours_before_deadline)

                    # 締切時刻を過ぎている場合はスキップ
                    if now > deadline_dt:
                        logger.info(f"Race {race_id}: 締切時刻を過ぎているためスキップ")
                        stats['skipped'] += 1
                        continue

                # 予想を更新
                success = self.update_to_before_prediction(race_id, force=False)

                if success:
                    stats['updated'] += 1
                else:
                    stats['failed'] += 1

            logger.info(f"{target_date}: 更新完了 - {stats}")
            return stats

        except Exception as e:
            logger.error(f"{target_date}: 日次更新エラー - {e}", exc_info=True)
            return {'total': 0, 'updated': 0, 'skipped': 0, 'failed': 0}
