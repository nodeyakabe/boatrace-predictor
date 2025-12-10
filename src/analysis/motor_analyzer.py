"""
モーター・ボート分析モジュール

モーター・ボートの過去成績を分析し、性能評価スコアを算出
"""

from typing import Dict, List
import sqlite3
from datetime import datetime, timedelta
from src.utils.db_connection_pool import get_connection


def laplace_smoothing(successes: int, trials: int, alpha: float = 2.0, k: int = 2) -> float:
    """
    ラプラス平滑化による確率推定

    Args:
        successes: 成功数（勝利数、2連対数など）
        trials: 総試行数（レース数）
        alpha: 平滑化パラメータ（デフォルト2.0）
        k: カテゴリ数（2連対なら2：連対 or 非連対）

    Returns:
        平滑化された確率
    """
    return (successes + alpha) / (trials + alpha * k)


class MotorAnalyzer:
    """モーター・ボート分析クラス"""

    def __init__(self, db_path="data/boatrace.db", batch_loader=None):
        self.db_path = db_path
        self.batch_loader = batch_loader
        self._use_cache = batch_loader is not None

    def _connect(self):
        """データベース接続（接続プールから取得）"""
        return get_connection(self.db_path)

    def _fetch_all(self, query, params=None):
        """クエリ実行（複数行）"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params or [])
        results = cursor.fetchall()
        cursor.close()  # カーソルのみ閉じる（接続は再利用）
        return results

    def _fetch_one(self, query, params=None):
        """クエリ実行（1行）"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params or [])
        result = cursor.fetchone()
        cursor.close()  # カーソルのみ閉じる（接続は再利用）
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
        # キャッシュ使用時
        if self._use_cache and self.batch_loader:
            cached = self.batch_loader.get_motor_stats(venue_code, motor_number)
            if cached:
                return cached

        # 従来のDB直接クエリ
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
        # キャッシュ使用時
        if self._use_cache and self.batch_loader:
            cached = self.batch_loader.get_motor_recent_form(venue_code, motor_number, recent_races)
            if cached:
                return cached

        # 従来のDB直接クエリ
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
        # キャッシュ使用時
        if self._use_cache and self.batch_loader:
            cached = self.batch_loader.get_boat_stats(venue_code, boat_number)
            if cached:
                return cached

        # 従来のDB直接クエリ
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
    # バッチ取得メソッド（高速化）
    # ========================================

    def _get_motors_batch(self, venue_code: str, motor_numbers: List[int]) -> Dict:
        """
        複数モーターのデータを一括取得（高速化）

        Returns:
            {motor_number: {'stats': {...}, 'recent': {...}}, ...}
        """
        if not motor_numbers:
            return {}

        placeholders = ','.join('?' * len(motor_numbers))

        # モーター統計を一括取得
        stats_query = f"""
            SELECT
                e.motor_number,
                COUNT(*) as total_races,
                SUM(CASE WHEN CAST(r.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN CAST(r.rank AS INTEGER) <= 2 THEN 1 ELSE 0 END) as place_2_count,
                SUM(CASE WHEN CAST(r.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as place_3_count,
                AVG(CAST(r.rank AS INTEGER)) as avg_rank
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE ra.venue_code = ?
              AND e.motor_number IN ({placeholders})
              AND r.is_invalid = 0
              AND ra.race_date >= date('now', '-90 days')
            GROUP BY e.motor_number
        """

        rows = self._fetch_all(stats_query, [venue_code] + motor_numbers)

        result = {}
        for row in rows:
            motor_num = row['motor_number']
            total = row['total_races']
            if total > 0:
                result[motor_num] = {
                    'stats': {
                        'total_races': total,
                        'win_count': row['win_count'],
                        'win_rate': row['win_count'] / total,
                        'place_rate_2': row['place_2_count'] / total,
                        'place_rate_3': row['place_3_count'] / total,
                        'avg_rank': row['avg_rank']
                    },
                    'recent': {}
                }

        # 直近成績を一括取得
        recent_query = f"""
            SELECT
                e.motor_number,
                r.rank,
                ra.race_date,
                ra.race_number
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE ra.venue_code = ?
              AND e.motor_number IN ({placeholders})
              AND r.is_invalid = 0
            ORDER BY e.motor_number, ra.race_date DESC, ra.race_number DESC
        """

        rows = self._fetch_all(recent_query, [venue_code] + motor_numbers)

        # モーター番号ごとにグループ化
        recent_by_motor = {}
        for row in rows:
            motor_num = row['motor_number']
            if motor_num not in recent_by_motor:
                recent_by_motor[motor_num] = []
            if len(recent_by_motor[motor_num]) < 10:  # 直近10レース
                recent_by_motor[motor_num].append(int(row['rank']))

        # 統計計算
        for motor_num, ranks in recent_by_motor.items():
            if motor_num in result and ranks:
                total = len(ranks)
                result[motor_num]['recent'] = {
                    'recent_races': ranks,
                    'recent_win_rate': sum(1 for r in ranks if r == 1) / total,
                    'recent_place_rate_3': sum(1 for r in ranks if r <= 3) / total
                }

        # デフォルト値を設定（データがないモーター用）
        for motor_num in motor_numbers:
            if motor_num not in result:
                result[motor_num] = {
                    'stats': {
                        'total_races': 0,
                        'win_count': 0,
                        'win_rate': 0.0,
                        'place_rate_2': 0.0,
                        'place_rate_3': 0.0,
                        'avg_rank': 0.0
                    },
                    'recent': {
                        'recent_races': [],
                        'recent_win_rate': 0.0,
                        'recent_place_rate_3': 0.0
                    }
                }

        return result

    def _get_boats_batch(self, venue_code: str, boat_numbers: List[int]) -> Dict:
        """
        複数ボートのデータを一括取得（高速化）

        Returns:
            {boat_number: {...}, ...}
        """
        if not boat_numbers:
            return {}

        placeholders = ','.join('?' * len(boat_numbers))

        query = f"""
            SELECT
                e.boat_number,
                COUNT(*) as total_races,
                SUM(CASE WHEN CAST(r.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN CAST(r.rank AS INTEGER) <= 2 THEN 1 ELSE 0 END) as place_2_count,
                SUM(CASE WHEN CAST(r.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as place_3_count,
                AVG(CAST(r.rank AS INTEGER)) as avg_rank
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE ra.venue_code = ?
              AND e.boat_number IN ({placeholders})
              AND r.is_invalid = 0
              AND ra.race_date >= date('now', '-90 days')
            GROUP BY e.boat_number
        """

        rows = self._fetch_all(query, [venue_code] + boat_numbers)

        result = {}
        for row in rows:
            boat_num = row['boat_number']
            total = row['total_races']
            if total > 0:
                result[boat_num] = {
                    'total_races': total,
                    'win_count': row['win_count'],
                    'win_rate': row['win_count'] / total,
                    'place_rate_2': row['place_2_count'] / total,
                    'place_rate_3': row['place_3_count'] / total,
                    'avg_rank': row['avg_rank']
                }

        # デフォルト値を設定（データがないボート用）
        for boat_num in boat_numbers:
            if boat_num not in result:
                result[boat_num] = {
                    'total_races': 0,
                    'win_count': 0,
                    'win_rate': 0.0,
                    'place_rate_2': 0.0,
                    'place_rate_3': 0.0,
                    'avg_rank': 0.0
                }

        return result

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
        # キャッシュ使用時（バッチ取得で高速化）
        if self._use_cache and self.batch_loader:
            race_info = self.batch_loader.get_race_info(race_id)
            entries = self.batch_loader.get_race_entries(race_id)

            if race_info and entries:
                venue_code = race_info['venue_code']

                # モーター番号・ボート番号のリストを取得
                motor_numbers = [e.get('motor_number') for e in entries if e.get('motor_number')]
                boat_numbers = [e.get('boat_number') for e in entries if e.get('boat_number')]

                # 一括取得
                motors_data = self._get_motors_batch(venue_code, motor_numbers) if motor_numbers else {}
                boats_data = self._get_boats_batch(venue_code, boat_numbers) if boat_numbers else {}

                results = []
                for entry in entries:
                    motor_number = entry.get('motor_number')
                    boat_number = entry.get('boat_number')

                    results.append({
                        'pit_number': entry['pit_number'],
                        'motor_number': motor_number,
                        'boat_number': boat_number,
                        'motor_stats': motors_data.get(motor_number, {}).get('stats', {}),
                        'motor_recent_form': motors_data.get(motor_number, {}).get('recent', {}),
                        'boat_stats': boats_data.get(boat_number, {})
                    })

                return results

        # 従来のDB直接クエリ
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
        モーター・ボートの総合スコアを計算（最大20点、最低12点保証）

        改善点:
        - 基礎点を高くし、モーター差の影響を縮小
        - ラプラス平滑化で小サンプル問題を解消
        - コース・選手より影響を小さくする

        Args:
            motor_analysis: analyze_race_motors()の各モーターデータ

        Returns:
            モータースコア（12-20点）
        """
        # 基礎点: 12点（60%）を保証 - モーターの影響を縮小
        BASE_SCORE = 12.0
        score = BASE_SCORE

        # 全国平均値（基準値）
        NATIONAL_AVG_PLACE_RATE_2 = 0.50  # 2連対率50%（ラプラス平滑化のデフォルト値）

        # 1. モーター2連対率（0-4点）- ラプラス平滑化を使用
        motor_stats = motor_analysis['motor_stats']
        motor_races = motor_stats['total_races']
        motor_place_2 = int(motor_stats.get('place_rate_2', 0) * motor_races) if motor_races > 0 else 0

        # ラプラス平滑化で2連対率を計算（データなしでも50%相当）
        smoothed_rate = laplace_smoothing(motor_place_2, motor_races, alpha=2.0, k=2)

        # 50%を2点（中央値）とし、65%以上で4点満点
        relative_score = (smoothed_rate - 0.50) / 0.15 * 2.0 + 2.0
        score += max(0.0, min(relative_score, 4.0))

        # 2. モーター直近成績（0-2点）- ラプラス平滑化を使用
        motor_recent = motor_analysis['motor_recent_form']
        if motor_recent['recent_races']:
            recent_count = len(motor_recent['recent_races'])
            recent_place_3_count = sum(1 for r in motor_recent['recent_races'] if r <= 3)

            # ラプラス平滑化で3連対率を計算
            smoothed_recent = laplace_smoothing(recent_place_3_count, recent_count, alpha=1.5, k=2)

            # 50%を1点（中央値）とし、70%以上で2点満点
            relative_score = (smoothed_recent - 0.50) / 0.20 * 1.0 + 1.0
            score += max(0.0, min(relative_score, 2.0))
        else:
            # データなしは平均値（1点）
            score += 1.0

        # 3. ボート2連対率（0-2点）- ラプラス平滑化を使用
        boat_stats = motor_analysis['boat_stats']
        boat_races = boat_stats['total_races']
        boat_place_2 = int(boat_stats.get('place_rate_2', 0) * boat_races) if boat_races > 0 else 0

        # ラプラス平滑化で2連対率を計算
        smoothed_boat = laplace_smoothing(boat_place_2, boat_races, alpha=1.5, k=2)

        # 50%を1点（中央値）とし、65%以上で2点満点
        relative_score = (smoothed_boat - 0.50) / 0.15 * 1.0 + 1.0
        score += max(0.0, min(relative_score, 2.0))

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
