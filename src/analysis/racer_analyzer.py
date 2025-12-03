"""
選手分析モジュール

選手の過去成績、コース別勝率、平均STなどを分析し、
予想スコアリングに必要なデータを提供する
"""

from typing import Dict, List, Optional
import sqlite3
from datetime import datetime, timedelta
from src.utils.db_connection_pool import get_connection


def laplace_smoothing(wins: int, trials: int, alpha: float = 2.0, k: int = 6) -> float:
    """
    ラプラス平滑化による勝率推定

    外枠の0%問題（データ不足による勝率0%）を解消する。

    Args:
        wins: 勝利数
        trials: 総試行数（レース数）
        alpha: 平滑化パラメータ（デフォルト2.0）
        k: カテゴリ数（ボートレースは6艇なのでデフォルト6）

    Returns:
        平滑化された勝率 (wins + alpha) / (trials + alpha * k)

    例:
        - 0勝/0レース → 2/(0+12) = 0.167 (全国平均相当)
        - 0勝/5レース → 2/(5+12) = 0.118
        - 1勝/5レース → 3/(5+12) = 0.176
        - 5勝/20レース → 7/(20+12) = 0.219
    """
    return (wins + alpha) / (trials + alpha * k)


class RacerAnalyzer:
    """選手分析クラス"""

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
    # 選手基本成績
    # ========================================

    def get_racer_overall_stats(self, racer_number: int, days: int = 180) -> Dict:
        """
        選手の全体成績を取得

        Args:
            racer_number: 選手登録番号
            days: 集計期間（日数）

        Returns:
            {
                'total_races': 50,
                'win_count': 12,
                'win_rate': 0.24,
                'place_rate_2': 0.40,  # 2着以内率
                'place_rate_3': 0.56,  # 3着以内率
                'avg_rank': 3.2,
                'avg_st': 0.14
            }
        """
        # キャッシュ使用時
        if self._use_cache and self.batch_loader:
            cached = self.batch_loader.get_racer_overall_stats(racer_number)
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
                AVG(r.rank) as avg_rank,
                AVG(rd.st_time) as avg_st
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            LEFT JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date >= ?
              AND r.is_invalid = 0
        """

        row = self._fetch_one(query, [racer_number, start_date])

        if row and row['total_races'] > 0:
            total = row['total_races']
            return {
                'total_races': total,
                'win_count': row['win_count'],
                'win_rate': row['win_count'] / total,
                'place_rate_2': row['place_2'] / total,
                'place_rate_3': row['place_3'] / total,
                'avg_rank': row['avg_rank'],
                'avg_st': row['avg_st']
            }

        return {
            'total_races': 0,
            'win_count': 0,
            'win_rate': 0.0,
            'place_rate_2': 0.0,
            'place_rate_3': 0.0,
            'avg_rank': 0.0,
            'avg_st': None
        }

    def get_racer_course_stats(self, racer_number: int, course: int, days: int = 180) -> Dict:
        """
        選手のコース別成績を取得

        Args:
            racer_number: 選手登録番号
            course: コース番号（1-6）
            days: 集計期間（日数）

        Returns:
            {
                'total_races': 15,
                'win_count': 5,
                'win_rate': 0.33,
                'place_rate_2': 0.53,
                'place_rate_3': 0.67,
                'avg_rank': 2.8
            }
        """
        # キャッシュ使用時
        if self._use_cache and self.batch_loader:
            cached = self.batch_loader.get_racer_course_stats(racer_number, course)
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
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            WHERE e.racer_number = ?
              AND rd.actual_course = ?
              AND ra.race_date >= ?
              AND r.is_invalid = 0
        """

        row = self._fetch_one(query, [racer_number, course, start_date])

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

    def get_racer_venue_stats(self, racer_number: int, venue_code: str, days: int = 180) -> Dict:
        """
        選手の競艇場別成績を取得

        Args:
            racer_number: 選手登録番号
            venue_code: 競艇場コード
            days: 集計期間（日数）

        Returns:
            {
                'total_races': 20,
                'win_rate': 0.30,
                'place_rate_2': 0.50,
                'place_rate_3': 0.65
            }
        """
        # キャッシュ使用時
        if self._use_cache and self.batch_loader:
            cached = self.batch_loader.get_racer_venue_stats(racer_number, venue_code)
            if cached:
                return cached

        # 従来のDB直接クエリ
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN r.rank <= 2 THEN 1 ELSE 0 END) as place_2,
                SUM(CASE WHEN r.rank <= 3 THEN 1 ELSE 0 END) as place_3
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND ra.venue_code = ?
              AND ra.race_date >= ?
              AND r.is_invalid = 0
        """

        row = self._fetch_one(query, [racer_number, venue_code, start_date])

        if row and row['total_races'] > 0:
            total = row['total_races']
            return {
                'total_races': total,
                'win_rate': row['win_count'] / total,
                'place_rate_2': row['place_2'] / total,
                'place_rate_3': row['place_3'] / total
            }

        return {
            'total_races': 0,
            'win_rate': 0.0,
            'place_rate_2': 0.0,
            'place_rate_3': 0.0
        }

    # ========================================
    # 直近成績
    # ========================================

    def get_racer_recent_form(self, racer_number: int, recent_races: int = 10) -> Dict:
        """
        選手の直近成績を取得

        Args:
            racer_number: 選手登録番号
            recent_races: 直近レース数

        Returns:
            {
                'recent_races': [1, 3, 2, 4, 1, 5, 2, 3, 1, 2],  # 着順
                'recent_win_rate': 0.30,
                'recent_place_rate_3': 0.70,
                'form_trend': 'up'  # 'up', 'down', 'stable'
            }
        """
        # キャッシュ使用時
        if self._use_cache and self.batch_loader:
            cached = self.batch_loader.get_racer_recent_form(racer_number, recent_races)
            if cached:
                return cached

        # 従来のDB直接クエリ
        query = """
            SELECT r.rank, ra.race_date
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND r.is_invalid = 0
            ORDER BY ra.race_date DESC, ra.race_number DESC
            LIMIT ?
        """

        rows = self._fetch_all(query, [racer_number, recent_races])

        if not rows:
            return {
                'recent_races': [],
                'recent_win_rate': 0.0,
                'recent_place_rate_3': 0.0,
                'form_trend': 'unknown'
            }

        ranks = [int(row['rank']) for row in rows]  # 文字列を整数に変換
        total = len(ranks)

        # 勝率・連対率
        win_count = sum(1 for r in ranks if r == 1)
        place_3_count = sum(1 for r in ranks if r <= 3)

        # 調子の傾向（前半5レースと後半5レースで比較）
        if total >= 10:
            first_half_avg = sum(ranks[:5]) / 5
            second_half_avg = sum(ranks[5:]) / 5

            if second_half_avg < first_half_avg - 0.5:
                trend = 'up'  # 調子上昇
            elif second_half_avg > first_half_avg + 0.5:
                trend = 'down'  # 調子下降
            else:
                trend = 'stable'  # 安定
        else:
            trend = 'unknown'

        return {
            'recent_races': ranks,
            'recent_win_rate': win_count / total,
            'recent_place_rate_3': place_3_count / total,
            'form_trend': trend
        }

    # ========================================
    # ST（スタートタイミング）分析
    # ========================================

    def get_racer_st_stats(self, racer_number: int, days: int = 180) -> Dict:
        """
        選手のST（スタートタイミング）統計

        Args:
            racer_number: 選手登録番号
            days: 集計期間（日数）

        Returns:
            {
                'avg_st': 0.14,
                'st_deviation': 0.03,  # 標準偏差
                'flying_rate': 0.05,  # フライング率
                'late_rate': 0.10  # 出遅れ率
            }
        """
        # キャッシュ使用時
        if self._use_cache and self.batch_loader:
            cached = self.batch_loader.get_racer_st_stats(racer_number)
            if cached:
                return cached

        # 従来のDB直接クエリ
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                AVG(rd.st_time) as avg_st,
                COUNT(*) as total_st,
                SUM(CASE WHEN rd.st_time < 0 THEN 1 ELSE 0 END) as flying_count,
                SUM(CASE WHEN rd.st_time > 0.20 THEN 1 ELSE 0 END) as late_count
            FROM race_details rd
            JOIN races ra ON rd.race_id = ra.id
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date >= ?
              AND rd.st_time IS NOT NULL
        """

        row = self._fetch_one(query, [racer_number, start_date])

        if row and row['total_st'] > 0:
            total = row['total_st']
            return {
                'avg_st': row['avg_st'],
                'flying_rate': row['flying_count'] / total,
                'late_rate': row['late_count'] / total,
                'total_st_records': total
            }

        return {
            'avg_st': None,
            'flying_rate': 0.0,
            'late_rate': 0.0,
            'total_st_records': 0
        }

    # ========================================
    # レース単位での選手分析
    # ========================================

    def analyze_race_entries(self, race_id: int) -> List[Dict]:
        """
        レース出走選手全員の分析結果を取得

        Args:
            race_id: レースID

        Returns:
            [
                {
                    'pit_number': 1,
                    'racer_number': 4444,
                    'racer_name': '山田太郎',
                    'overall_stats': {...},
                    'course_stats': {...},  # 進入コース別
                    'venue_stats': {...},
                    'recent_form': {...},
                    'st_stats': {...}
                },
                ...
            ]
        """
        # キャッシュ使用時
        if self._use_cache and self.batch_loader:
            race_info = self.batch_loader.get_race_info(race_id)
            entries = self.batch_loader.get_race_entries(race_id)

            if race_info and entries:
                venue_code = race_info['venue_code']

                results = []
                for entry in entries:
                    racer_number = entry['racer_number']
                    actual_course = entry['actual_course']

                    # 各種統計を取得
                    overall_stats = self.get_racer_overall_stats(racer_number)

                    # コース別成績（進入コースが分かる場合）
                    if actual_course:
                        course_stats = self.get_racer_course_stats(racer_number, actual_course)
                    else:
                        # 進入コース不明の場合は枠番を仮のコースとして使用
                        course_stats = self.get_racer_course_stats(racer_number, entry['pit_number'])

                    venue_stats = self.get_racer_venue_stats(racer_number, venue_code)
                    recent_form = self.get_racer_recent_form(racer_number)
                    st_stats = self.get_racer_st_stats(racer_number)

                    results.append({
                        'pit_number': entry['pit_number'],
                        'racer_number': racer_number,
                        'racer_name': entry['racer_name'],
                        'overall_stats': overall_stats,
                        'course_stats': course_stats,
                        'venue_stats': venue_stats,
                        'recent_form': recent_form,
                        'st_stats': st_stats
                    })

                return results

        # 従来のDB直接クエリ
        # レース情報取得
        race_query = """
            SELECT venue_code, race_date
            FROM races
            WHERE id = ?
        """
        race_info = self._fetch_one(race_query, [race_id])

        if not race_info:
            return []

        venue_code = race_info['venue_code']

        # エントリー取得（racer_rankを追加）
        entry_query = """
            SELECT
                e.pit_number,
                e.racer_number,
                e.racer_name,
                e.racer_rank,
                rd.actual_course
            FROM entries e
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        """
        entries = self._fetch_all(entry_query, [race_id])

        results = []
        for entry in entries:
            racer_number = entry['racer_number']
            actual_course = entry['actual_course']
            racer_rank = entry['racer_rank'] if entry['racer_rank'] else 'B2'  # デフォルトB2

            # 各種統計を取得
            overall_stats = self.get_racer_overall_stats(racer_number)

            # コース別成績（進入コースが分かる場合）
            if actual_course:
                course_stats = self.get_racer_course_stats(racer_number, actual_course)
            else:
                # 進入コース不明の場合は枠番を仮のコースとして使用
                course_stats = self.get_racer_course_stats(racer_number, entry['pit_number'])

            venue_stats = self.get_racer_venue_stats(racer_number, venue_code)
            recent_form = self.get_racer_recent_form(racer_number)
            st_stats = self.get_racer_st_stats(racer_number)

            results.append({
                'pit_number': entry['pit_number'],
                'racer_number': racer_number,
                'racer_name': entry['racer_name'],
                'racer_rank': racer_rank,
                'overall_stats': overall_stats,
                'course_stats': course_stats,
                'venue_stats': venue_stats,
                'recent_form': recent_form,
                'st_stats': st_stats
            })

        return results

    # ========================================
    # スコアリング用評価値
    # ========================================

    def calculate_racer_score(self, racer_analysis: Dict) -> float:
        """
        選手の総合スコアを計算（最大40点、最低8点保証）

        注意: 選手ランク（A1/A2/B1/B2）はコース×ランクスコアで既に反映済み。
        ここでは純粋に実績（勝率、コース別、当地、直近）のみで評価する。

        配点:
        - 全国勝率: 0-8点
        - コース別勝率: 0-8点
        - 当地成績: 0-6点
        - 直近5走: 0-8点（★強化）
        - ST評価: 0-2点

        Args:
            racer_analysis: analyze_race_entries()の各選手データ

        Returns:
            選手スコア（8-40点）
        """
        # 基礎点（最低保証）
        BASE_SCORE = 8.0
        score = BASE_SCORE

        # 1. 全国勝率（0-8点）- ラプラス平滑化を使用
        overall_stats = racer_analysis['overall_stats']
        total_races = overall_stats['total_races']
        win_count = overall_stats['win_count']

        # ラプラス平滑化で勝率を計算（データなしでも16.7%相当になる）
        smoothed_win_rate = laplace_smoothing(win_count, total_races, alpha=2.0, k=6)

        # 勝率30%で8点満点（全国平均16.7%で約4.5点）
        score += min(smoothed_win_rate * 26.7, 8.0)

        # 2. コース別勝率（0-8点）- ラプラス平滑化を使用
        course_stats = racer_analysis['course_stats']
        course_races = course_stats['total_races']
        course_wins = course_stats['win_count']

        # ラプラス平滑化（コースデータは少ないのでalphaを小さめに）
        smoothed_course_rate = laplace_smoothing(course_wins, course_races, alpha=1.5, k=6)

        # 25%で8点満点
        score += min(smoothed_course_rate * 32, 8.0)

        # 3. 当地成績（0-6点）- ラプラス平滑化を使用
        venue_stats = racer_analysis['venue_stats']
        venue_races = venue_stats['total_races']
        # venue_statsにwin_countがない場合は計算
        venue_wins = int(venue_stats.get('win_rate', 0) * venue_races) if venue_races > 0 else 0

        # ラプラス平滑化（当地データも少ないのでalphaを小さめに）
        smoothed_venue_rate = laplace_smoothing(venue_wins, venue_races, alpha=1.0, k=6)

        # 25%で6点満点
        score += min(smoothed_venue_rate * 24, 6.0)

        # 4. 直近調子（0-8点）★強化：競艇は直近パフォーマンスが非常に重要
        recent_form = racer_analysis['recent_form']
        if recent_form['recent_races']:
            recent_count = len(recent_form['recent_races'])

            # 直近5走を特に重視（最新ほど重要）
            recent_5 = recent_form['recent_races'][:5] if recent_count >= 5 else recent_form['recent_races']
            recent_5_wins = sum(1 for r in recent_5 if r == 1)
            recent_5_place3 = sum(1 for r in recent_5 if r <= 3)

            # 直近5走の勝率（0-4点）
            recent_5_win_rate = recent_5_wins / len(recent_5) if recent_5 else 0
            score += min(recent_5_win_rate * 20, 4.0)  # 20%で4点

            # 直近5走の3着以内率（0-3点）
            recent_5_place3_rate = recent_5_place3 / len(recent_5) if recent_5 else 0
            score += min(recent_5_place3_rate * 5, 3.0)  # 60%で3点

            # 調子の傾向でボーナス/ペナルティ（0-1点）
            if recent_count >= 5:
                if recent_form['form_trend'] == 'up':
                    score += 1.0  # 調子上昇
                elif recent_form['form_trend'] == 'down':
                    score -= 1.0  # 調子下降は大きなペナルティ
        else:
            # 直近データなしでもラプラス平滑化で最低限のスコア
            smoothed_recent_rate = laplace_smoothing(0, 0, alpha=1.0, k=6)
            score += min(smoothed_recent_rate * 16 * 0.5, 2.0)

        # 5. ST評価（0-2点）
        st_stats = racer_analysis['st_stats']
        if st_stats['avg_st'] is not None:
            # ST 0.15秒以内で満点
            if st_stats['avg_st'] <= 0.15:
                score += 2.0
            elif st_stats['avg_st'] <= 0.18:
                score += 1.0
            # ST 0.20秒以下でも最低0.5点は付与
            elif st_stats['avg_st'] <= 0.20:
                score += 0.5

        return min(score, 40.0)

    # ========================================
    # 会場別分析
    # ========================================

    def get_racer_venue_stats(self, racer_number: int, venue_code: str, days: int = 180) -> Dict:
        """
        選手の会場別成績を取得

        Args:
            racer_number: 選手登録番号
            venue_code: 会場コード（'01'〜'24'）
            days: 集計期間（日数）デフォルト180日

        Returns:
            {
                'venue_code': '01',
                'total_races': 20,
                'win_count': 5,
                'win_rate': 0.25,
                'avg_rank': 3.1,
                'favorite_venue': True  # この会場が得意かどうか
            }
        """
        # キャッシュ使用時
        if self._use_cache and self.batch_loader:
            cached = self.batch_loader.get_racer_venue_stats(racer_number, venue_code)
            if cached:
                return cached

        # 従来のDB直接クエリ
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                COUNT(*) as total_races,
                SUM(CASE WHEN CAST(r.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) as win_count,
                AVG(CAST(r.rank AS REAL)) as avg_rank
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND ra.venue_code = ?
              AND ra.race_date >= ?
              AND r.is_invalid = 0
        """

        row = self._fetch_one(query, [str(racer_number), venue_code, start_date])

        if row and row['total_races'] > 0:
            total = row['total_races']
            win_rate = row['win_count'] / total

            # 全会場平均との比較で得意会場判定（後で全体勝率と比較）
            return {
                'venue_code': venue_code,
                'total_races': total,
                'win_count': row['win_count'],
                'win_rate': win_rate,
                'avg_rank': row['avg_rank'],
                'favorite_venue': win_rate > 0.20  # 暫定閾値
            }

        return {
            'venue_code': venue_code,
            'total_races': 0,
            'win_count': 0,
            'win_rate': 0.0,
            'avg_rank': 0.0,
            'favorite_venue': False
        }

    def get_racer_all_venues_stats(self, racer_number: int, days: int = 365) -> List[Dict]:
        """
        選手の全会場別成績を取得

        Args:
            racer_number: 選手登録番号
            days: 集計期間（日数）

        Returns:
            [
                {'venue_code': '01', 'venue_name': '桐生', 'win_rate': 0.28, ...},
                {'venue_code': '02', 'venue_name': '戸田', 'win_rate': 0.15, ...},
                ...
            ]
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                ra.venue_code,
                COUNT(*) as total_races,
                SUM(CASE WHEN CAST(r.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) as win_count,
                AVG(CAST(r.rank AS REAL)) as avg_rank
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date >= ?
              AND r.is_invalid = 0
            GROUP BY ra.venue_code
            ORDER BY win_count DESC, total_races DESC
        """

        rows = self._fetch_all(query, [str(racer_number), start_date])

        # 会場名マッピング
        venue_names = {
            '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
            '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
            '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
            '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
            '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
            '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
        }

        results = []
        for row in rows:
            venue_code = row['venue_code']
            total = row['total_races']

            if total > 0:
                results.append({
                    'venue_code': venue_code,
                    'venue_name': venue_names.get(venue_code, '不明'),
                    'total_races': total,
                    'win_count': row['win_count'],
                    'win_rate': row['win_count'] / total,
                    'avg_rank': row['avg_rank']
                })

        return results

    def get_racer_recent_trend(self, racer_number: int, recent_n: int = 10) -> Dict:
        """
        選手の直近N戦のトレンド分析

        Args:
            racer_number: 選手登録番号
            recent_n: 直近何戦を分析するか

        Returns:
            {
                'recent_races': 10,
                'recent_wins': 3,
                'recent_win_rate': 0.30,
                'recent_avg_rank': 2.8,
                'trend': 'improving' | 'stable' | 'declining'
            }
        """
        query = """
            SELECT CAST(r.rank AS INTEGER) as rank, ra.race_date
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND r.is_invalid = 0
            ORDER BY ra.race_date DESC, ra.race_number DESC
            LIMIT ?
        """

        rows = self._fetch_all(query, [str(racer_number), recent_n])

        if not rows or len(rows) == 0:
            return {
                'recent_races': 0,
                'recent_wins': 0,
                'recent_win_rate': 0.0,
                'recent_avg_rank': 0.0,
                'trend': 'unknown'
            }

        ranks = [row['rank'] for row in rows]
        recent_races = len(ranks)
        recent_wins = sum(1 for r in ranks if r == 1)
        recent_avg_rank = sum(ranks) / recent_races

        # トレンド判定（前半と後半の平均順位を比較）
        if recent_races >= 6:
            half = recent_races // 2
            first_half_avg = sum(ranks[:half]) / half
            second_half_avg = sum(ranks[half:]) / (recent_races - half)

            if first_half_avg - second_half_avg >= 0.5:
                trend = 'improving'  # 後半が良い
            elif second_half_avg - first_half_avg >= 0.5:
                trend = 'declining'  # 前半が良い
            else:
                trend = 'stable'
        else:
            trend = 'stable'

        return {
            'recent_races': recent_races,
            'recent_wins': recent_wins,
            'recent_win_rate': recent_wins / recent_races,
            'recent_avg_rank': recent_avg_rank,
            'trend': trend
        }


if __name__ == "__main__":
    # テスト実行
    analyzer = RacerAnalyzer()

    print("=" * 60)
    print("選手分析テスト")
    print("=" * 60)

    # テスト用選手番号（実際のデータがあれば）
    test_racer_number = 4444

    print(f"\n【選手番号 {test_racer_number} の全体成績】")
    overall = analyzer.get_racer_overall_stats(test_racer_number)
    print(f"  総レース数: {overall['total_races']}")
    print(f"  勝率: {overall['win_rate']:.1%}")
    print(f"  2連対率: {overall['place_rate_2']:.1%}")
    print(f"  3連対率: {overall['place_rate_3']:.1%}")
    print(f"  平均ST: {overall['avg_st']:.3f}秒" if overall['avg_st'] else "  平均ST: データなし")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
