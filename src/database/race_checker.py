"""
レース存在チェッカー
DBに既に存在するレースを効率的に確認し、重複収集を防ぐ
"""
import sqlite3
from typing import Set, Tuple, Optional
from datetime import datetime, timedelta


class RaceChecker:
    """レース存在確認クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def get_existing_races(
        self,
        start_date: str,
        end_date: str,
        venue_codes: Optional[list] = None
    ) -> Set[Tuple[str, str, int]]:
        """
        指定期間で既にDBに存在するレースを取得

        Args:
            start_date: 開始日 (YYYY-MM-DD形式)
            end_date: 終了日 (YYYY-MM-DD形式)
            venue_codes: 会場コードリスト（省略時は全会場）

        Returns:
            Set[Tuple[venue_code, race_date, race_number]]
            例: {('01', '2024-11-25', 1), ('01', '2024-11-25', 2), ...}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            if venue_codes:
                placeholders = ','.join(['?' for _ in venue_codes])
                query = f"""
                    SELECT venue_code, race_date, race_number
                    FROM races
                    WHERE race_date >= ? AND race_date <= ?
                    AND venue_code IN ({placeholders})
                """
                params = [start_date, end_date] + venue_codes
            else:
                query = """
                    SELECT venue_code, race_date, race_number
                    FROM races
                    WHERE race_date >= ? AND race_date <= ?
                """
                params = [start_date, end_date]

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # (venue_code, race_date, race_number) のセットを返す
            return {(row[0], row[1], row[2]) for row in rows}

        finally:
            conn.close()

    def is_race_collected(
        self,
        venue_code: str,
        race_date: str,
        race_number: int
    ) -> bool:
        """
        単一レースがDBに存在するか確認

        Args:
            venue_code: 会場コード
            race_date: レース日付 (YYYY-MM-DD形式)
            race_number: レース番号

        Returns:
            存在する場合 True
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT COUNT(*) FROM races
                WHERE venue_code = ? AND race_date = ? AND race_number = ?
            """, (venue_code, race_date, race_number))

            count = cursor.fetchone()[0]
            return count > 0

        finally:
            conn.close()

    def get_missing_races(
        self,
        start_date: str,
        end_date: str,
        venue_codes: Optional[list] = None,
        race_count: int = 12
    ) -> Set[Tuple[str, str, int]]:
        """
        指定期間で不足しているレースを取得

        Args:
            start_date: 開始日 (YYYY-MM-DD形式)
            end_date: 終了日 (YYYY-MM-DD形式)
            venue_codes: 会場コードリスト（省略時は全会場 01-24）
            race_count: 1日あたりのレース数（デフォルト12）

        Returns:
            Set[Tuple[venue_code, race_date, race_number]]
            存在しないレースのセット
        """
        if venue_codes is None:
            venue_codes = [f"{i:02d}" for i in range(1, 25)]

        # 既存レースを取得
        existing = self.get_existing_races(start_date, end_date, venue_codes)

        # 期待されるレースセットを生成
        expected = set()
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        current = start
        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            for venue_code in venue_codes:
                for race_number in range(1, race_count + 1):
                    expected.add((venue_code, date_str, race_number))
            current += timedelta(days=1)

        # 不足分を返す
        return expected - existing

    def get_collection_stats(
        self,
        start_date: str,
        end_date: str,
        venue_codes: Optional[list] = None
    ) -> dict:
        """
        収集状況の統計を取得

        Args:
            start_date: 開始日 (YYYY-MM-DD形式)
            end_date: 終了日 (YYYY-MM-DD形式)
            venue_codes: 会場コードリスト

        Returns:
            統計情報の辞書
        """
        existing = self.get_existing_races(start_date, end_date, venue_codes)

        # 日付ごとの集計
        date_stats = {}
        for venue_code, race_date, race_number in existing:
            if race_date not in date_stats:
                date_stats[race_date] = {'venues': set(), 'races': 0}
            date_stats[race_date]['venues'].add(venue_code)
            date_stats[race_date]['races'] += 1

        # 集計
        total_races = len(existing)
        total_dates = len(date_stats)

        return {
            'total_races': total_races,
            'total_dates': total_dates,
            'date_stats': {
                date: {
                    'venue_count': len(stats['venues']),
                    'race_count': stats['races']
                }
                for date, stats in sorted(date_stats.items())
            }
        }


def get_existing_races(start_date: str, end_date: str, venue_codes: list = None) -> Set[Tuple[str, str, int]]:
    """便利関数: 既存レースを取得"""
    checker = RaceChecker()
    return checker.get_existing_races(start_date, end_date, venue_codes)


def is_race_collected(venue_code: str, race_date: str, race_number: int) -> bool:
    """便利関数: レース存在確認"""
    checker = RaceChecker()
    return checker.is_race_collected(venue_code, race_date, race_number)
