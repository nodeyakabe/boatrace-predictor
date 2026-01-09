# -*- coding: utf-8 -*-
"""
まくり率・差し率計算モジュール

会場別の展開指標を計算
- まくり率: 3コース or 4コースの選手が1着になる率
- 差し率: 2コース or 5コースの選手が1着になる率

※ 公式の決まり手分類は使用せず、コースベースの簡易定義
"""

import sqlite3
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class AttackRateResult:
    """会場別展開指標の計算結果"""
    stadium_id: str
    total_races: int
    course2_wins: int
    course3_wins: int
    course4_wins: int
    course5_wins: int
    makuri_rate: float   # (3C + 4C) / total
    sashi_rate: float    # (2C + 5C) / total
    period_start: str
    period_end: str


class AttackRateCalculator:
    """まくり率・差し率計算クラス"""

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path

    def calculate_stadium_attack_rates(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None
    ) -> List[AttackRateResult]:
        """
        全会場のまくり率・差し率を計算

        Args:
            period_start: 集計開始日 (YYYY-MM-DD)、None=全期間
            period_end: 集計終了日 (YYYY-MM-DD)、None=今日

        Returns:
            List[AttackRateResult]
        """
        if period_end is None:
            period_end = datetime.now().strftime('%Y-%m-%d')
        if period_start is None:
            period_start = '2000-01-01'

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 会場ごとにコース別1着数を集計
            # actual_course優先、なければpit_number
            query = '''
                SELECT
                    r.venue_code as stadium_id,
                    COUNT(DISTINCT r.id) as total_races,
                    SUM(CASE WHEN COALESCE(rd.actual_course, e.pit_number) = 2 AND (res.rank = '1' OR res.rank = 1) THEN 1 ELSE 0 END) as course2_wins,
                    SUM(CASE WHEN COALESCE(rd.actual_course, e.pit_number) = 3 AND (res.rank = '1' OR res.rank = 1) THEN 1 ELSE 0 END) as course3_wins,
                    SUM(CASE WHEN COALESCE(rd.actual_course, e.pit_number) = 4 AND (res.rank = '1' OR res.rank = 1) THEN 1 ELSE 0 END) as course4_wins,
                    SUM(CASE WHEN COALESCE(rd.actual_course, e.pit_number) = 5 AND (res.rank = '1' OR res.rank = 1) THEN 1 ELSE 0 END) as course5_wins
                FROM races r
                JOIN entries e ON r.id = e.race_id
                JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                WHERE r.race_date >= ? AND r.race_date <= ?
                  AND res.is_invalid = 0
                GROUP BY r.venue_code
            '''

            cursor.execute(query, (period_start, period_end))
            rows = cursor.fetchall()

        results = []
        for stadium_id, total_races, c2, c3, c4, c5 in rows:
            if total_races > 0:
                makuri_rate = (c3 + c4) / total_races
                sashi_rate = (c2 + c5) / total_races
            else:
                makuri_rate = 0.0
                sashi_rate = 0.0

            results.append(AttackRateResult(
                stadium_id=stadium_id,
                total_races=total_races,
                course2_wins=c2,
                course3_wins=c3,
                course4_wins=c4,
                course5_wins=c5,
                makuri_rate=makuri_rate,
                sashi_rate=sashi_rate,
                period_start=period_start,
                period_end=period_end
            ))

        return results

    def save_results(self, results: List[AttackRateResult]):
        """
        計算結果をDBに保存（UPSERT方式）

        Args:
            results: 計算結果リスト
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for r in results:
                cursor.execute('''
                    INSERT INTO stadium_attack_stats
                    (stadium_id, total_races, course2_wins, course3_wins, course4_wins, course5_wins,
                     makuri_rate, sashi_rate, period_start, period_end, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(stadium_id, period_start, period_end)
                    DO UPDATE SET
                        total_races = excluded.total_races,
                        course2_wins = excluded.course2_wins,
                        course3_wins = excluded.course3_wins,
                        course4_wins = excluded.course4_wins,
                        course5_wins = excluded.course5_wins,
                        makuri_rate = excluded.makuri_rate,
                        sashi_rate = excluded.sashi_rate,
                        updated_at = CURRENT_TIMESTAMP
                ''', (
                    r.stadium_id,
                    r.total_races,
                    r.course2_wins,
                    r.course3_wins,
                    r.course4_wins,
                    r.course5_wins,
                    r.makuri_rate,
                    r.sashi_rate,
                    r.period_start,
                    r.period_end
                ))

            conn.commit()

    def get_attack_rates(
        self,
        stadium_id: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None
    ) -> Optional[Dict]:
        """
        会場のまくり率・差し率を取得

        Args:
            stadium_id: 会場ID
            period_start: 期間開始
            period_end: 期間終了

        Returns:
            {'makuri_rate': float, 'sashi_rate': float, ...} or None
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            query = '''
                SELECT stadium_id, total_races, course2_wins, course3_wins, course4_wins, course5_wins,
                       makuri_rate, sashi_rate, period_start, period_end
                FROM stadium_attack_stats
                WHERE stadium_id = ?
            '''
            params = [stadium_id]

            if period_start:
                query += ' AND period_start = ?'
                params.append(period_start)
            if period_end:
                query += ' AND period_end = ?'
                params.append(period_end)

            query += ' ORDER BY updated_at DESC LIMIT 1'

            cursor.execute(query, params)
            row = cursor.fetchone()

            if row:
                return {
                    'stadium_id': row[0],
                    'total_races': row[1],
                    'course2_wins': row[2],
                    'course3_wins': row[3],
                    'course4_wins': row[4],
                    'course5_wins': row[5],
                    'makuri_rate': row[6],
                    'sashi_rate': row[7],
                    'period_start': row[8],
                    'period_end': row[9]
                }

            return None

    def get_all_stadium_rates(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None
    ) -> List[Dict]:
        """
        全会場のまくり率・差し率を取得

        Args:
            period_start: 期間開始
            period_end: 期間終了

        Returns:
            List of dicts
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            query = '''
                SELECT stadium_id, total_races, makuri_rate, sashi_rate, period_start, period_end
                FROM stadium_attack_stats
            '''
            params = []

            conditions = []
            if period_start:
                conditions.append('period_start = ?')
                params.append(period_start)
            if period_end:
                conditions.append('period_end = ?')
                params.append(period_end)

            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)

            query += ' ORDER BY stadium_id'

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [
                {
                    'stadium_id': row[0],
                    'total_races': row[1],
                    'makuri_rate': row[2],
                    'sashi_rate': row[3],
                    'period_start': row[4],
                    'period_end': row[5]
                }
                for row in rows
            ]


if __name__ == "__main__":
    calc = AttackRateCalculator()

    print("=" * 60)
    print("まくり率・差し率計算テスト")
    print("=" * 60)

    # 2024年で計算
    print("\n【会場別まくり率・差し率（2024年）】")
    results = calc.calculate_stadium_attack_rates(
        period_start='2024-01-01',
        period_end='2024-12-31'
    )

    print(f"  対象会場数: {len(results)}")

    if results:
        # まくり率でソート
        sorted_makuri = sorted(results, key=lambda x: x.makuri_rate, reverse=True)
        print("\n  まくり率トップ5:")
        for r in sorted_makuri[:5]:
            print(f"    会場{r.stadium_id}: {r.makuri_rate:.1%} (3C:{r.course3_wins}, 4C:{r.course4_wins})")

        # 差し率でソート
        sorted_sashi = sorted(results, key=lambda x: x.sashi_rate, reverse=True)
        print("\n  差し率トップ5:")
        for r in sorted_sashi[:5]:
            print(f"    会場{r.stadium_id}: {r.sashi_rate:.1%} (2C:{r.course2_wins}, 5C:{r.course5_wins})")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
