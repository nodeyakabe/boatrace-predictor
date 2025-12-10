"""
三連対率ベースのスコアリングモジュール

1着確率ではなく、3着以内に入る確率（三連対率）を軸にスコアリング
2着・3着予測の精度向上を目的とする
"""

from typing import Dict, List, Optional
import sqlite3
from datetime import datetime, timedelta


class Top3Scorer:
    """三連対率ベースのスコアリング"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def calculate_top3_score(
        self,
        racer_number: str,
        venue_code: str,
        course: int,
        motor_number: int,
        race_date: str,
        days: int = 180
    ) -> Dict:
        """
        三連対率ベースの総合スコアを計算

        Args:
            racer_number: 選手登録番号
            venue_code: 場コード
            course: コース（1-6）
            motor_number: モーター番号
            race_date: レース日
            days: 集計対象期間（日数）

        Returns:
            {
                'top3_score': 三連対スコア（0-100）,
                'racer_top3_rate': 選手三連対率,
                'course_top3_rate': コース別三連対率,
                'motor_top3_rate': モーター三連対率,
                'venue_top3_rate': 会場別三連対率
            }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 基準日
        base_date = datetime.strptime(race_date, '%Y-%m-%d')
        start_date = (base_date - timedelta(days=days)).strftime('%Y-%m-%d')

        result = {
            'top3_score': 0.0,
            'racer_top3_rate': 0.0,
            'course_top3_rate': 0.0,
            'motor_top3_rate': 0.0,
            'venue_top3_rate': 0.0
        }

        # 1. 選手の三連対率
        racer_top3_rate = self._get_racer_top3_rate(
            cursor, racer_number, start_date, race_date
        )
        result['racer_top3_rate'] = racer_top3_rate

        # 2. コース別三連対率（全体統計）
        course_top3_rate = self._get_course_top3_rate(
            cursor, venue_code, course
        )
        result['course_top3_rate'] = course_top3_rate

        # 3. モーターの三連対率
        motor_top3_rate = self._get_motor_top3_rate(
            cursor, venue_code, motor_number, start_date, race_date
        )
        result['motor_top3_rate'] = motor_top3_rate

        # 4. 選手×会場の三連対率
        venue_top3_rate = self._get_racer_venue_top3_rate(
            cursor, racer_number, venue_code, start_date, race_date
        )
        result['venue_top3_rate'] = venue_top3_rate

        # スコア計算（0-100）
        # 重み: 選手40%, コース30%, モーター20%, 会場10%
        top3_score = (
            racer_top3_rate * 0.40 +
            course_top3_rate * 0.30 +
            motor_top3_rate * 0.20 +
            venue_top3_rate * 0.10
        )
        result['top3_score'] = round(top3_score, 1)

        conn.close()
        return result

    def _get_racer_top3_rate(
        self,
        cursor,
        racer_number: str,
        start_date: str,
        end_date: str
    ) -> float:
        """選手の三連対率を取得"""
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN CAST(r.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as top3
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date >= ?
              AND ra.race_date < ?
              AND r.is_invalid = 0
        ''', (racer_number, start_date, end_date))

        row = cursor.fetchone()
        if row and row[0] > 0:
            return (row[1] / row[0]) * 100
        return 0.0

    def _get_course_top3_rate(
        self,
        cursor,
        venue_code: str,
        course: int
    ) -> float:
        """コース別三連対率を取得（過去2年の統計）"""
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN CAST(r.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as top3
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            WHERE ra.venue_code = ?
              AND r.pit_number = ?
              AND ra.race_date >= date('now', '-2 years')
              AND r.is_invalid = 0
        ''', (venue_code, course))

        row = cursor.fetchone()
        if row and row[0] >= 100:  # 最低100レース
            return (row[1] / row[0]) * 100
        return 50.0  # デフォルト

    def _get_motor_top3_rate(
        self,
        cursor,
        venue_code: str,
        motor_number: int,
        start_date: str,
        end_date: str
    ) -> float:
        """モーターの三連対率を取得"""
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN CAST(r.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as top3
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE ra.venue_code = ?
              AND e.motor_number = ?
              AND ra.race_date >= ?
              AND ra.race_date < ?
              AND r.is_invalid = 0
        ''', (venue_code, motor_number, start_date, end_date))

        row = cursor.fetchone()
        if row and row[0] > 0:
            return (row[1] / row[0]) * 100
        return 0.0

    def _get_racer_venue_top3_rate(
        self,
        cursor,
        racer_number: str,
        venue_code: str,
        start_date: str,
        end_date: str
    ) -> float:
        """選手×会場の三連対率を取得"""
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN CAST(r.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as top3
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND ra.venue_code = ?
              AND ra.race_date >= ?
              AND ra.race_date < ?
              AND r.is_invalid = 0
        ''', (racer_number, venue_code, start_date, end_date))

        row = cursor.fetchone()
        if row and row[0] > 0:
            return (row[1] / row[0]) * 100
        return 0.0

    def rank_by_top3_probability(
        self,
        race_entries: List[Dict],
        venue_code: str,
        race_date: str
    ) -> List[Dict]:
        """
        三連対確率でランク付け

        Args:
            race_entries: エントリー情報のリスト
            venue_code: 場コード
            race_date: レース日

        Returns:
            三連対スコアでソートされたエントリーリスト
        """
        scored_entries = []

        for entry in race_entries:
            top3_result = self.calculate_top3_score(
                racer_number=entry['racer_number'],
                venue_code=venue_code,
                course=entry['pit_number'],
                motor_number=entry.get('motor_number', 0),
                race_date=race_date
            )

            scored_entry = entry.copy()
            scored_entry.update(top3_result)
            scored_entries.append(scored_entry)

        # 三連対スコアでソート
        scored_entries.sort(key=lambda x: x['top3_score'], reverse=True)

        return scored_entries
