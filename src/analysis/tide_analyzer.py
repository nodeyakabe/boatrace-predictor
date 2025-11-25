"""
潮位補正分析
潮位による各コースへの影響を計算
"""

import sqlite3
from typing import Dict, Optional
from datetime import datetime
from config.settings import DATABASE_PATH


class TideAnalyzer:
    """潮位補正クラス"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = DATABASE_PATH
        self.db_path = db_path

        # 会場別の潮位影響係数（今後チューニング）
        self.venue_tide_coefficients = {
            # 潮の影響が大きい会場
            '03': {'満潮_イン係数': 1.02, '干潮_イン係数': 0.98},  # 江戸川
            '06': {'満潮_イン係数': 1.01, '干潮_イン係数': 0.99},  # 浜名湖
            '14': {'満潮_イン係数': 1.015, '干潮_イン係数': 0.985},  # 鳴門
            '20': {'満潮_イン係数': 1.02, '干潮_イン係数': 0.98},  # 若松
            '21': {'満潮_イン係数': 1.015, '干潮_イン係数': 0.985},  # 芦屋
            '22': {'満潮_イン係数': 1.02, '干潮_イン係数': 0.98},  # 福岡
            '23': {'満潮_イン係数': 1.015, '干潮_イン係数': 0.985},  # 唐津
            '24': {'満潮_イン係数': 1.01, '干潮_イン係数': 0.99},  # 大村
        }

    def calculate_tide_adjustment(
        self,
        race_id: int,
        pit_number: int,
        tide_level: Optional[str] = None
    ) -> Dict[str, float]:
        """
        潮位による補正を計算

        Args:
            race_id: レースID
            pit_number: 艇番
            tide_level: 潮位レベル（'満潮', '干潮', '中潮', None）

        Returns:
            {
                'course_adjustment': コース点への補正係数（0.95-1.05）,
                'confidence_adjustment': 信頼度への影響（-0.02 ~ +0.02）,
                'reason': 補正理由
            }
        """
        # tide_levelが指定されていない場合は補正なし
        if tide_level is None:
            return {
                'course_adjustment': 1.0,
                'confidence_adjustment': 0.0,
                'reason': '潮位データなし'
            }

        # 会場コードを取得
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT venue_code FROM races WHERE id = ?
        """, (race_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return {
                'course_adjustment': 1.0,
                'confidence_adjustment': 0.0,
                'reason': 'レース情報なし'
            }

        venue_code = row[0]

        # 会場別の係数を取得
        if venue_code not in self.venue_tide_coefficients:
            # 潮の影響が小さい会場（淡水・プール型）
            return {
                'course_adjustment': 1.0,
                'confidence_adjustment': 0.0,
                'reason': '潮位影響軽微（淡水会場）'
            }

        coeffs = self.venue_tide_coefficients[venue_code]

        # コース番号を取得（actual_courseがあればそれを使用）
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT actual_course
            FROM actual_courses
            WHERE race_id = ? AND pit_number = ?
        """, (race_id, pit_number))

        course_row = cursor.fetchone()
        conn.close()

        course = course_row[0] if course_row else pit_number

        # 潮位による補正
        course_adj = 1.0
        conf_adj = 0.0
        reason = ''

        if tide_level == '満潮':
            if course == 1:
                # インコースは満潮で有利
                course_adj = coeffs['満潮_イン係数']
                conf_adj = 0.01
                reason = f'満潮（イン有利 x{course_adj:.2f}）'
            else:
                # 外コースは不利
                course_adj = 1.0 / coeffs['満潮_イン係数']
                reason = f'満潮（外不利 x{course_adj:.2f}）'

        elif tide_level == '干潮':
            if course == 1:
                # インコースは干潮で不利
                course_adj = coeffs['干潮_イン係数']
                conf_adj = -0.01
                reason = f'干潮（イン不利 x{course_adj:.2f}）'
            else:
                # 外コースは有利
                course_adj = 1.0 / coeffs['干潮_イン係数']
                reason = f'干潮（外有利 x{course_adj:.2f}）'

        else:
            # 中潮は影響なし
            reason = '中潮（影響なし）'

        return {
            'course_adjustment': course_adj,
            'confidence_adjustment': conf_adj,
            'reason': reason
        }

    def get_tide_level(self, race_datetime: datetime, venue_code: str) -> Optional[str]:
        """
        レース時刻の潮位レベルを取得

        Args:
            race_datetime: レース日時
            venue_code: 会場コード

        Returns:
            '満潮' / '干潮' / '中潮' / None

        TODO: 今後、気象庁APIや天文計算で自動取得を実装
        現在は手動入力またはNone
        """
        # TODO: 実装予定
        # - 気象庁潮汐表APIから取得
        # - または天文推定計算
        return None
