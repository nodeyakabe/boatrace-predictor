"""
モーター・ボート分析モジュール

モーター・ボートの過去成績を分析し、性能評価スコアを算出
"""

from typing import Dict, List
import sqlite3
from datetime import datetime, timedelta


class MotorAnalyzer:
    """モーター・ボート分析クラス"""

    def __init__(self, db_path="data/boatrace.db"):
        self.db_path = db_path

    def _connect(self):
        """データベース接続"""
        return sqlite3.connect(self.db_path)

    def _fetch_all(self, query, params=None):
        """クエリ実行（複数行）"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params or [])
        results = cursor.fetchall()
        conn.close()
        return results

    def _fetch_one(self, query, params=None):
        """クエリ実行（1行）"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params or [])
        result = cursor.fetchone()
        conn.close()
        return result

    # ========================================
    # モーター成績分析
    # ========================================

    def get_motor_stats(self, venue_code: str, motor_number: int, days: int = 90) -> Dict:
        """
        モーターの成績統計を取得

        Args:
            venue_code: 競艇場コード
            motor_number: モーター番号
            days: 集計期間（日数）

        Returns:
            {
                'total_races': 30,
                'win_count': 8,
                'win_rate': 0.27,
                'place_rate_2': 0.43,  # 2連対率
                'place_rate_3': 0.57,  # 3連対率
                'avg_rank': 3.1
            }
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN r.rank <= 2 THEN 1 ELSE 0 END) as place_2,
                SUM(CASE WHEN r.rank <= 3 THEN 1 ELSE 0 END) as place_3,
                AVG(r.rank) as avg_rank
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE ra.venue_code = ?
              AND e.motor_number = ?
              AND ra.race_date >= ?
              AND r.is_invalid = 0
        """

        row = self._fetch_one(query, [venue_code, motor_number, start_date])

        if row and row['total_races'] > 0:
            total = row['total_races']
            return {
                'total_races': total,
                'win_count': row['win_count'],
                'win_rate': row['win_count'] / total,
                'place_rate_2': row['place_2'] / total,
                'place_rate_3': row['place_3'] / total,
                'avg_rank': row['avg_rank']
            }

        return {
            'total_races': 0,
            'win_count': 0,
            'win_rate': 0.0,
            'place_rate_2': 0.0,
            'place_rate_3': 0.0,
            'avg_rank': 0.0
        }

    def get_motor_recent_form(self, venue_code: str, motor_number: int, recent_races: int = 10) -> Dict:
        """
        モーターの直近成績を取得

        Args:
            venue_code: 競艇場コード
            motor_number: モーター番号
            recent_races: 直近レース数

        Returns:
            {
                'recent_races': [1, 3, 2, 4, 1],
                'recent_win_rate': 0.40,
                'recent_place_rate_3': 0.60
            }
        """
        query = """
            SELECT r.rank
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE ra.venue_code = ?
              AND e.motor_number = ?
              AND r.is_invalid = 0
            ORDER BY ra.race_date DESC, ra.race_number DESC
            LIMIT ?
        """

        rows = self._fetch_all(query, [venue_code, motor_number, recent_races])

        if not rows:
            return {
                'recent_races': [],
                'recent_win_rate': 0.0,
                'recent_place_rate_3': 0.0
            }

        ranks = [int(row['rank']) for row in rows]  # 文字列を整数に変換
        total = len(ranks)

        win_count = sum(1 for r in ranks if r == 1)
        place_3_count = sum(1 for r in ranks if r <= 3)

        return {
            'recent_races': ranks,
            'recent_win_rate': win_count / total,
            'recent_place_rate_3': place_3_count / total
        }

    # ========================================
    # ボート成績分析
    # ========================================

    def get_boat_stats(self, venue_code: str, boat_number: int, days: int = 90) -> Dict:
        """
        ボートの成績統計を取得

        Args:
            venue_code: 競艇場コード
            boat_number: ボート番号
            days: 集計期間（日数）

        Returns:
            {
                'total_races': 25,
                'win_count': 6,
                'win_rate': 0.24,
                'place_rate_2': 0.40,
                'place_rate_3': 0.52,
                'avg_rank': 3.2
            }
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN r.rank <= 2 THEN 1 ELSE 0 END) as place_2,
                SUM(CASE WHEN r.rank <= 3 THEN 1 ELSE 0 END) as place_3,
                AVG(r.rank) as avg_rank
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE ra.venue_code = ?
              AND e.boat_number = ?
              AND ra.race_date >= ?
              AND r.is_invalid = 0
        """

        row = self._fetch_one(query, [venue_code, boat_number, start_date])

        if row and row['total_races'] > 0:
            total = row['total_races']
            return {
                'total_races': total,
                'win_count': row['win_count'],
                'win_rate': row['win_count'] / total,
                'place_rate_2': row['place_2'] / total,
                'place_rate_3': row['place_3'] / total,
                'avg_rank': row['avg_rank']
            }

        return {
            'total_races': 0,
            'win_count': 0,
            'win_rate': 0.0,
            'place_rate_2': 0.0,
            'place_rate_3': 0.0,
            'avg_rank': 0.0
        }

    # ========================================
    # レース単位でのモーター・ボート分析
    # ========================================

    def analyze_race_motors(self, race_id: int) -> List[Dict]:
        """
        レース出走モーター・ボート全ての分析結果を取得

        Args:
            race_id: レースID

        Returns:
            [
                {
                    'pit_number': 1,
                    'motor_number': 12,
                    'boat_number': 34,
                    'motor_stats': {...},
                    'motor_recent_form': {...},
                    'boat_stats': {...}
                },
                ...
            ]
        """
        # レース情報取得
        race_query = """
            SELECT venue_code
            FROM races
            WHERE id = ?
        """
        race_info = self._fetch_one(race_query, [race_id])

        if not race_info:
            return []

        venue_code = race_info['venue_code']

        # エントリー取得
        entry_query = """
            SELECT
                pit_number,
                motor_number,
                boat_number
            FROM entries
            WHERE race_id = ?
            ORDER BY pit_number
        """
        entries = self._fetch_all(entry_query, [race_id])

        results = []
        for entry in entries:
            motor_number = entry['motor_number']
            boat_number = entry['boat_number']

            # モーター成績
            motor_stats = self.get_motor_stats(venue_code, motor_number)
            motor_recent = self.get_motor_recent_form(venue_code, motor_number)

            # ボート成績
            boat_stats = self.get_boat_stats(venue_code, boat_number)

            results.append({
                'pit_number': entry['pit_number'],
                'motor_number': motor_number,
                'boat_number': boat_number,
                'motor_stats': motor_stats,
                'motor_recent_form': motor_recent,
                'boat_stats': boat_stats
            })

        return results

    # ========================================
    # スコアリング用評価値
    # ========================================

    def calculate_motor_score(self, motor_analysis: Dict) -> float:
        """
        モーター・ボートの総合スコアを計算（最大20点）

        全国平均を基準に、相対的な性能で評価。
        データ不足時は平滑化を適用。

        Args:
            motor_analysis: analyze_race_motors()の各モーターデータ

        Returns:
            モータースコア（0-20点）
        """
        score = 0.0

        # 全国平均値（基準値）
        NATIONAL_AVG_PLACE_RATE_2 = 0.45  # 2連対率45%
        NATIONAL_AVG_PLACE_RATE_3 = 0.60  # 3連対率60%

        # 1. モーター2連対率（0-10点）
        motor_stats = motor_analysis['motor_stats']
        motor_races = motor_stats['total_races']

        if motor_races > 0:
            # データ信頼度（10レースで60%, 30レースで95%）
            motor_weight = min(motor_races / 30.0, 1.0)

            place_rate_2 = motor_stats['place_rate_2']
            # データ不足時は全国平均で平滑化
            smoothed_rate = (place_rate_2 * motor_weight +
                           NATIONAL_AVG_PLACE_RATE_2 * (1 - motor_weight))

            # 全国平均45%を5点（中央値）とし、60%以上で10点満点
            # 式: (rate - 0.45) / (0.60 - 0.45) * 5 + 5
            #   = (rate - 0.45) / 0.15 * 5 + 5
            #   = (rate - 0.45) * 33.33 + 5
            relative_score = (smoothed_rate - NATIONAL_AVG_PLACE_RATE_2) * 33.33 + 5.0
            score += max(0.0, min(relative_score, 10.0))
        else:
            # データなしは平均値（5点）
            score += 5.0

        # 2. モーター直近成績（0-5点）
        motor_recent = motor_analysis['motor_recent_form']
        if motor_recent['recent_races']:
            recent_count = len(motor_recent['recent_races'])
            # 直近データは5レース以上で評価
            if recent_count >= 5:
                recent_weight = min(recent_count / 15.0, 1.0)

                recent_place_3 = motor_recent['recent_place_rate_3']
                smoothed_recent = (recent_place_3 * recent_weight +
                                 NATIONAL_AVG_PLACE_RATE_3 * (1 - recent_weight))

                # 全国平均60%を2.5点（中央値）とし、75%以上で5点満点
                # 式: (rate - 0.60) / (0.75 - 0.60) * 2.5 + 2.5
                #   = (rate - 0.60) / 0.15 * 2.5 + 2.5
                #   = (rate - 0.60) * 16.67 + 2.5
                relative_score = (smoothed_recent - NATIONAL_AVG_PLACE_RATE_3) * 16.67 + 2.5
                score += max(0.0, min(relative_score, 5.0))
            else:
                # データ不足は平均値（2.5点）
                score += 2.5
        else:
            # データなしは平均値（2.5点）
            score += 2.5

        # 3. ボート2連対率（0-5点）
        boat_stats = motor_analysis['boat_stats']
        boat_races = boat_stats['total_races']

        if boat_races > 0:
            # データ信頼度（10レースで60%, 30レースで95%）
            boat_weight = min(boat_races / 30.0, 1.0)

            boat_place_rate_2 = boat_stats['place_rate_2']
            smoothed_boat = (boat_place_rate_2 * boat_weight +
                           NATIONAL_AVG_PLACE_RATE_2 * (1 - boat_weight))

            # 全国平均45%を2.5点（中央値）とし、60%以上で5点満点
            # 式: (rate - 0.45) / 0.15 * 2.5 + 2.5
            #   = (rate - 0.45) * 16.67 + 2.5
            relative_score = (smoothed_boat - NATIONAL_AVG_PLACE_RATE_2) * 16.67 + 2.5
            score += max(0.0, min(relative_score, 5.0))
        else:
            # データなしは平均値（2.5点）
            score += 2.5

        return min(score, 20.0)

    # ========================================
    # 競艇場別のモーター・ボートランキング
    # ========================================

    def rank_motors_by_venue(self, venue_code: str, days: int = 90, min_races: int = 10) -> List[Dict]:
        """
        競艇場別のモーターランキング

        Args:
            venue_code: 競艇場コード
            days: 集計期間（日数）
            min_races: 最低レース数

        Returns:
            [
                {'motor_number': 12, 'place_rate_2': 0.45, 'total_races': 25},
                {'motor_number': 5, 'place_rate_2': 0.42, 'total_races': 30},
                ...
            ]
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                e.motor_number,
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank <= 2 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as place_rate_2
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE ra.venue_code = ?
              AND ra.race_date >= ?
              AND r.is_invalid = 0
            GROUP BY e.motor_number
            HAVING COUNT(*) >= ?
            ORDER BY place_rate_2 DESC
        """

        rows = self._fetch_all(query, [venue_code, start_date, min_races])

        return [
            {
                'motor_number': row['motor_number'],
                'place_rate_2': row['place_rate_2'],
                'total_races': row['total_races']
            }
            for row in rows
        ]


if __name__ == "__main__":
    # テスト実行
    analyzer = MotorAnalyzer()

    print("=" * 60)
    print("モーター・ボート分析テスト")
    print("=" * 60)

    # テスト用（競艇場コード、モーター番号）
    test_venue = "03"
    test_motor = 12

    print(f"\n【{test_venue}場 モーター{test_motor}番 の成績】")
    motor_stats = analyzer.get_motor_stats(test_venue, test_motor)
    print(f"  総レース数: {motor_stats['total_races']}")
    print(f"  勝率: {motor_stats['win_rate']:.1%}")
    print(f"  2連対率: {motor_stats['place_rate_2']:.1%}")
    print(f"  3連対率: {motor_stats['place_rate_3']:.1%}")

    print(f"\n【{test_venue}場 モーターランキング TOP5】")
    motor_ranking = analyzer.rank_motors_by_venue(test_venue)[:5]
    for i, motor in enumerate(motor_ranking, 1):
        print(f"  {i}位: モーター{motor['motor_number']}番 "
              f"2連対率{motor['place_rate_2']:.1%} ({motor['total_races']}レース)")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
