"""
チルト・風スコアラー
チルト角と風向・風速から艇の有利不利を評価

仕様:
- チルト角: -0.5°〜+3.0°の範囲で評価
- 風向: 追い風（有利）vs 向かい風（不利）
- 風速: 強風時の影響
"""

import sqlite3
from typing import Dict, Optional
from src.utils.db_connection_pool import get_connection


class TiltWindScorer:
    """チルト・風スコアラー"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path

        # チルト角スコア
        # 標準: -0.5°、プラスチルト（+1〜+3°）は高速だが不安定
        self.TILT_OPTIMAL = 0.0    # 最適チルト角
        self.TILT_SCORE_FACTOR = 5.0  # スコア係数

        # 風向スコア（コース別）
        # 追い風（3-4時方向）は1コースに有利、向かい風（9-10時方向）は不利
        self.WIND_DIRECTION_EFFECT = {
            1: {'favorable': [3, 4, 5], 'unfavorable': [9, 10, 11]},  # 1コースは追い風が有利
            2: {'favorable': [2, 3, 4], 'unfavorable': [8, 9, 10]},
            3: {'favorable': [1, 2, 3], 'unfavorable': [7, 8, 9]},
            4: {'favorable': [12, 1, 2], 'unfavorable': [6, 7, 8]},
            5: {'favorable': [11, 12, 1], 'unfavorable': [5, 6, 7]},
            6: {'favorable': [10, 11, 12], 'unfavorable': [4, 5, 6]}
        }

        # スコアリングパラメータ
        self.MAX_SCORE = 15.0
        self.MIN_SCORE = -15.0

    def calculate_tilt_wind_score(
        self,
        race_id: int,
        pit_number: int,
        course: Optional[int] = None
    ) -> Dict:
        """
        チルト・風スコアを計算

        Args:
            race_id: レースID
            pit_number: 艇番（1-6）
            course: コース番号（進入後のコース、1-6）

        Returns:
            {'tilt_wind_score': float, 'tilt_score': float, 'wind_score': float}
        """
        # チルトデータを取得
        tilt_angle = self._get_tilt_angle(race_id, pit_number)

        # 風データを取得
        wind_data = self._get_wind_data(race_id)

        # チルトスコア
        tilt_score = 0.0
        if tilt_angle is not None:
            # 最適チルトからの距離に応じてスコア
            deviation = abs(tilt_angle - self.TILT_OPTIMAL)
            if deviation <= 0.5:
                tilt_score = 5.0  # 最適範囲
            elif deviation <= 1.0:
                tilt_score = 2.0
            elif deviation >= 2.0:
                tilt_score = -5.0  # 大きく外れる

        # 風スコア
        wind_score = 0.0
        if wind_data and course:
            wind_direction = wind_data.get('wind_direction')
            wind_speed = wind_data.get('wind_speed', 0)

            if wind_direction and wind_speed:
                # 風向の影響
                effect = self.WIND_DIRECTION_EFFECT.get(course, {})
                if wind_direction in effect.get('favorable', []):
                    wind_score = 5.0 * (wind_speed / 10.0)  # 風速10m/sで最大5点
                elif wind_direction in effect.get('unfavorable', []):
                    wind_score = -5.0 * (wind_speed / 10.0)

        # 総合スコア
        total_score = tilt_score * 0.6 + wind_score * 0.4

        # スコアをクリップ
        total_score = max(min(total_score, self.MAX_SCORE), self.MIN_SCORE)

        return {
            'tilt_wind_score': round(total_score, 1),
            'tilt_score': round(tilt_score, 1),
            'wind_score': round(wind_score, 1),
            'tilt_angle': tilt_angle,
            'wind_direction': wind_data.get('wind_direction') if wind_data else None,
            'wind_speed': wind_data.get('wind_speed') if wind_data else None
        }

    def _get_tilt_angle(self, race_id: int, pit_number: int) -> Optional[float]:
        """
        チルト角を取得

        Args:
            race_id: レースID
            pit_number: 艇番

        Returns:
            チルト角（度）、なければNone
        """
        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            query = """
                SELECT tilt_angle
                FROM race_details
                WHERE race_id = ? AND pit_number = ?
            """
            cursor.execute(query, (race_id, pit_number))
            row = cursor.fetchone()
            cursor.close()

            return row[0] if row and row[0] is not None else None
        except Exception as e:
            print(f"Warning: チルト角取得エラー (race_id={race_id}, pit={pit_number}): {e}")
            return None

    def _get_wind_data(self, race_id: int) -> Optional[Dict]:
        """
        風データを取得

        Args:
            race_id: レースID

        Returns:
            風データ辞書、なければNone
        """
        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            query = """
                SELECT wind_direction, wind_speed
                FROM race_conditions
                WHERE race_id = ?
            """
            cursor.execute(query, (race_id,))
            row = cursor.fetchone()
            cursor.close()

            if row and any(r is not None for r in row):
                return {
                    'wind_direction': row[0],
                    'wind_speed': row[1]
                }
            return None
        except Exception as e:
            print(f"Warning: 風データ取得エラー (race_id={race_id}): {e}")
            return None


if __name__ == '__main__':
    # テスト実行
    scorer = TiltWindScorer()

    print("=== チルト・風スコアラー テスト ===")

    test_race_id = 133159

    for pit in range(1, 7):
        course = pit  # 枠なりと仮定
        result = scorer.calculate_tilt_wind_score(test_race_id, pit, course)
        score = result.get('tilt_wind_score', 0)
        tilt = result.get('tilt_angle', '?')
        wind_dir = result.get('wind_direction', '?')
        wind_spd = result.get('wind_speed', '?')
        print(f"艇{pit}（{course}コース）: チルト={tilt}°、風向={wind_dir}時、風速={wind_spd}m/s → スコア={score:.1f}点")
