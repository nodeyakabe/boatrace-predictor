# -*- coding: utf-8 -*-
"""
逃げ率計算モジュール

選手別の逃げ率（1コースから1着になる率）を計算
- 全国逃げ率: 母数50走以上
- 当地逃げ率: 母数25走以上

※ 統計的信頼性を重視（95%CI: +/-14%程度）
"""

import sqlite3
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass


@dataclass
class EscapeRateResult:
    """逃げ率計算結果"""
    player_id: str
    stadium_id: Optional[str]  # None = 全国
    races_1course: int
    wins_1course: int
    escape_rate: Optional[float]  # None = 母数不足
    period_start: str
    period_end: str


class EscapeRateCalculator:
    """逃げ率計算クラス"""

    # 母数制限（統計的信頼性を重視）
    # - 全国50回: 95%CI ≒ ±14%
    # - 当地25回: 95%CI ≒ ±20%
    # ※カバレッジ約60%（1コースに入る現役選手はほぼカバー）
    MIN_RACES_NATIONAL = 50  # 全国逃げ率
    MIN_RACES_LOCAL = 25     # 当地逃げ率

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path

    def calculate_national_escape_rates(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None
    ) -> List[EscapeRateResult]:
        """
        全国逃げ率を全選手について計算

        Args:
            period_start: 集計開始日 (YYYY-MM-DD)、None=全期間
            period_end: 集計終了日 (YYYY-MM-DD)、None=今日

        Returns:
            List[EscapeRateResult]
        """
        if period_end is None:
            period_end = datetime.now().strftime('%Y-%m-%d')
        if period_start is None:
            period_start = '2000-01-01'

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 1コース出走 = actual_course=1 優先、なければ pit_number=1
            query = '''
                SELECT
                    e.racer_number as player_id,
                    COUNT(*) as races_1course,
                    SUM(CASE WHEN res.rank = '1' OR res.rank = 1 THEN 1 ELSE 0 END) as wins_1course
                FROM entries e
                JOIN races r ON e.race_id = r.id
                JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                WHERE r.race_date >= ? AND r.race_date <= ?
                  AND res.is_invalid = 0
                  AND COALESCE(rd.actual_course, e.pit_number) = 1
                GROUP BY e.racer_number
            '''

            cursor.execute(query, (period_start, period_end))
            rows = cursor.fetchall()

        results = []
        for player_id, races_1course, wins_1course in rows:
            # 母数チェック
            if races_1course >= self.MIN_RACES_NATIONAL:
                escape_rate = wins_1course / races_1course
            else:
                escape_rate = None

            results.append(EscapeRateResult(
                player_id=str(player_id),
                stadium_id=None,
                races_1course=races_1course,
                wins_1course=wins_1course,
                escape_rate=escape_rate,
                period_start=period_start,
                period_end=period_end
            ))

        return results

    def calculate_local_escape_rates(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None
    ) -> List[EscapeRateResult]:
        """
        当地逃げ率を全選手×全会場について計算

        Args:
            period_start: 集計開始日 (YYYY-MM-DD)、None=全期間
            period_end: 集計終了日 (YYYY-MM-DD)、None=今日

        Returns:
            List[EscapeRateResult]
        """
        if period_end is None:
            period_end = datetime.now().strftime('%Y-%m-%d')
        if period_start is None:
            period_start = '2000-01-01'

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            query = '''
                SELECT
                    e.racer_number as player_id,
                    r.venue_code as stadium_id,
                    COUNT(*) as races_1course,
                    SUM(CASE WHEN res.rank = '1' OR res.rank = 1 THEN 1 ELSE 0 END) as wins_1course
                FROM entries e
                JOIN races r ON e.race_id = r.id
                JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                WHERE r.race_date >= ? AND r.race_date <= ?
                  AND res.is_invalid = 0
                  AND COALESCE(rd.actual_course, e.pit_number) = 1
                GROUP BY e.racer_number, r.venue_code
            '''

            cursor.execute(query, (period_start, period_end))
            rows = cursor.fetchall()

        results = []
        for player_id, stadium_id, races_1course, wins_1course in rows:
            # 母数チェック
            if races_1course >= self.MIN_RACES_LOCAL:
                escape_rate = wins_1course / races_1course
            else:
                escape_rate = None

            results.append(EscapeRateResult(
                player_id=str(player_id),
                stadium_id=stadium_id,
                races_1course=races_1course,
                wins_1course=wins_1course,
                escape_rate=escape_rate,
                period_start=period_start,
                period_end=period_end
            ))

        return results

    def save_results(self, results: List[EscapeRateResult]):
        """
        計算結果をDBに保存（UPSERT方式）

        Args:
            results: 逃げ率計算結果リスト
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for r in results:
                cursor.execute('''
                    INSERT INTO player_escape_stats
                    (player_id, stadium_id, races_1course, wins_1course, escape_rate, period_start, period_end, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(player_id, stadium_id, period_start, period_end)
                    DO UPDATE SET
                        races_1course = excluded.races_1course,
                        wins_1course = excluded.wins_1course,
                        escape_rate = excluded.escape_rate,
                        updated_at = CURRENT_TIMESTAMP
                ''', (
                    r.player_id,
                    r.stadium_id,
                    r.races_1course,
                    r.wins_1course,
                    r.escape_rate,
                    r.period_start,
                    r.period_end
                ))

            conn.commit()

    def get_escape_rate(
        self,
        player_id: str,
        stadium_id: Optional[str] = None,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None
    ) -> Optional[float]:
        """
        選手の逃げ率を取得

        Args:
            player_id: 選手ID
            stadium_id: 会場ID（None=全国）
            period_start: 期間開始
            period_end: 期間終了

        Returns:
            逃げ率（母数不足の場合はNone）
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            if stadium_id is None:
                query = '''
                    SELECT escape_rate FROM player_escape_stats
                    WHERE player_id = ? AND stadium_id IS NULL
                '''
                params = [player_id]
            else:
                query = '''
                    SELECT escape_rate FROM player_escape_stats
                    WHERE player_id = ? AND stadium_id = ?
                '''
                params = [player_id, stadium_id]

            if period_start:
                query += ' AND period_start = ?'
                params.append(period_start)
            if period_end:
                query += ' AND period_end = ?'
                params.append(period_end)

            query += ' ORDER BY updated_at DESC LIMIT 1'

            cursor.execute(query, params)
            row = cursor.fetchone()

            return row[0] if row else None


if __name__ == "__main__":
    calc = EscapeRateCalculator()

    print("=" * 60)
    print("逃げ率計算テスト")
    print("=" * 60)

    # 全国逃げ率計算（サンプル：2024年）
    print("\n【全国逃げ率（2024年）】")
    national_results = calc.calculate_national_escape_rates(
        period_start='2024-01-01',
        period_end='2024-12-31'
    )
    valid_national = [r for r in national_results if r.escape_rate is not None]
    print(f"  対象選手数: {len(national_results)}")
    print(f"  母数充足選手数: {len(valid_national)}")

    if valid_national:
        # 上位5名
        sorted_results = sorted(valid_national, key=lambda x: x.escape_rate, reverse=True)
        print("\n  逃げ率トップ5:")
        for r in sorted_results[:5]:
            print(f"    選手{r.player_id}: {r.escape_rate:.1%} ({r.wins_1course}/{r.races_1course})")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
