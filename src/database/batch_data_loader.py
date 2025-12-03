"""
データ一括取得・キャッシュクラス

予想生成の高速化のため、日単位で必要なデータを一括取得してキャッシュする。
従来のN+1問題（1レースあたり850回のDBクエリ）を解消し、
日次で数回のクエリに削減する。
"""

import sqlite3
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from src.utils.db_connection_pool import get_connection


class BatchDataLoader:
    """日単位データ一括取得・キャッシュクラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースファイルのパス
        """
        self.db_path = db_path
        self._cache = {}
        self._cache_date = None
        self._cache_loaded = False

    def _connect(self):
        """データベース接続（接続プールから取得）"""
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def clear_cache(self):
        """キャッシュをクリア"""
        self._cache = {}
        self._cache_date = None
        self._cache_loaded = False

    def load_daily_data(self, target_date: str) -> None:
        """
        指定日の全データを一括取得

        Args:
            target_date: 対象日（YYYY-MM-DD形式）
        """
        # 既にキャッシュ済みの場合はスキップ
        if self._cache_loaded and self._cache_date == target_date:
            return

        # キャッシュクリア
        self.clear_cache()
        self._cache_date = target_date

        print(f"[BatchDataLoader] {target_date}のデータを一括取得中...")

        # 各種データを一括取得
        self._load_races_and_entries_batch(target_date)
        self._load_racer_stats_batch(target_date)
        self._load_motor_stats_batch(target_date)
        self._load_kimarite_stats_batch(target_date)
        self._load_grade_stats_batch(target_date)

        # Phase 1: 高効果項目のバッチロード
        self._load_racer_st_stats_batch(target_date)
        self._load_racer_recent_form_batch(target_date)
        self._load_boat_stats_batch(target_date)
        self._load_motor_recent_form_batch(target_date)

        # ExtendedScorer用の追加データ（一時的に無効化 - 最適化が必要）
        # self._load_race_details_batch(target_date)
        # self._load_racer_features_batch(target_date)
        # self._load_racer_venue_features_batch(target_date)
        # self._load_course_entry_tendency_batch(target_date)
        # self._load_session_performance_batch(target_date)
        # self._load_previous_race_batch(target_date)

        self._cache_loaded = True
        print(f"[BatchDataLoader] データ取得完了")

    def _load_races_and_entries_batch(self, target_date: str) -> None:
        """
        その日のレース情報とエントリー情報を一括取得
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # レース情報を取得
        cursor.execute('''
            SELECT id, venue_code, race_date, race_number, race_grade
            FROM races
            WHERE race_date = ?
        ''', [target_date])

        races = {}
        for row in cursor.fetchall():
            races[row['id']] = {
                'id': row['id'],
                'venue_code': row['venue_code'],
                'race_date': row['race_date'],
                'race_number': row['race_number'],
                'race_grade': row['race_grade']
            }

        self._cache['races'] = races

        # エントリー情報を取得
        race_ids = list(races.keys())
        if not race_ids:
            self._cache['entries'] = {}
            cursor.close()
            return

        placeholders = ','.join('?' * len(race_ids))
        cursor.execute(f'''
            SELECT
                e.race_id,
                e.pit_number,
                e.racer_number,
                e.racer_name,
                e.motor_number,
                e.boat_number,
                rd.actual_course
            FROM entries e
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.race_id IN ({placeholders})
            ORDER BY e.race_id, e.pit_number
        ''', race_ids)

        entries = {}
        for row in cursor.fetchall():
            race_id = row['race_id']
            if race_id not in entries:
                entries[race_id] = []

            entries[race_id].append({
                'pit_number': row['pit_number'],
                'racer_number': row['racer_number'],
                'racer_name': row['racer_name'],
                'motor_number': row['motor_number'],
                'boat_number': row['boat_number'],
                'actual_course': row['actual_course']
            })

        self._cache['entries'] = entries
        cursor.close()

    def _load_racer_stats_batch(self, target_date: str) -> None:
        """
        選手成績を一括取得（180日分）

        対象日に出走する全選手の以下のデータを取得:
        - 全体成績
        - コース別成績
        - 会場別成績
        - ST統計
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 対象日に出走する全選手を取得
        cursor.execute("""
            SELECT DISTINCT e.racer_number
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
        """, [target_date])

        racer_numbers = [row['racer_number'] for row in cursor.fetchall()]

        if not racer_numbers:
            cursor.close()
            return

        # 180日前の日付
        start_date = (datetime.strptime(target_date, '%Y-%m-%d') - timedelta(days=180)).strftime('%Y-%m-%d')

        # プレースホルダー作成
        placeholders = ','.join('?' * len(racer_numbers))

        # 1. 全体成績を一括取得
        query_overall = f"""
            SELECT
                e.racer_number,
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
            WHERE e.racer_number IN ({placeholders})
              AND ra.race_date >= ?
              AND ra.race_date < ?
              AND r.is_invalid = 0
            GROUP BY e.racer_number
        """

        cursor.execute(query_overall, racer_numbers + [start_date, target_date])

        racer_overall = {}
        for row in cursor.fetchall():
            racer_num = row['racer_number']
            total = row['total_races']
            racer_overall[racer_num] = {
                'total_races': total,
                'win_count': row['win_count'],
                'win_rate': row['win_count'] / total if total > 0 else 0.0,
                'place_rate_2': row['place_2'] / total if total > 0 else 0.0,
                'place_rate_3': row['place_3'] / total if total > 0 else 0.0,
                'avg_rank': row['avg_rank'],
                'avg_st': row['avg_st']
            }

        # 2. コース別成績を一括取得
        query_course = f"""
            SELECT
                e.racer_number,
                e.pit_number as course,
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN r.rank <= 2 THEN 1 ELSE 0 END) as place_2,
                SUM(CASE WHEN r.rank <= 3 THEN 1 ELSE 0 END) as place_3,
                AVG(r.rank) as avg_rank
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number IN ({placeholders})
              AND ra.race_date >= ?
              AND ra.race_date < ?
              AND r.is_invalid = 0
            GROUP BY e.racer_number, e.pit_number
        """

        cursor.execute(query_course, racer_numbers + [start_date, target_date])

        racer_course = defaultdict(dict)
        for row in cursor.fetchall():
            racer_num = row['racer_number']
            course = row['course']
            total = row['total_races']
            racer_course[racer_num][course] = {
                'total_races': total,
                'win_count': row['win_count'],
                'win_rate': row['win_count'] / total if total > 0 else 0.0,
                'place_rate_2': row['place_2'] / total if total > 0 else 0.0,
                'place_rate_3': row['place_3'] / total if total > 0 else 0.0,
                'avg_rank': row['avg_rank']
            }

        # 3. 会場別成績を一括取得
        query_venue = f"""
            SELECT
                e.racer_number,
                ra.venue_code,
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN r.rank <= 2 THEN 1 ELSE 0 END) as place_2,
                SUM(CASE WHEN r.rank <= 3 THEN 1 ELSE 0 END) as place_3,
                AVG(r.rank) as avg_rank
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number IN ({placeholders})
              AND ra.race_date >= ?
              AND ra.race_date < ?
              AND r.is_invalid = 0
            GROUP BY e.racer_number, ra.venue_code
        """

        cursor.execute(query_venue, racer_numbers + [start_date, target_date])

        racer_venue = defaultdict(dict)
        for row in cursor.fetchall():
            racer_num = row['racer_number']
            venue = row['venue_code']
            total = row['total_races']
            racer_venue[racer_num][venue] = {
                'total_races': total,
                'win_count': row['win_count'],
                'win_rate': row['win_count'] / total if total > 0 else 0.0,
                'place_rate_2': row['place_2'] / total if total > 0 else 0.0,
                'place_rate_3': row['place_3'] / total if total > 0 else 0.0,
                'avg_rank': row['avg_rank']
            }

        # キャッシュに保存
        self._cache['racer_overall'] = racer_overall
        self._cache['racer_course'] = dict(racer_course)
        self._cache['racer_venue'] = dict(racer_venue)

        cursor.close()

    def _load_motor_stats_batch(self, target_date: str) -> None:
        """
        モーター成績を一括取得（90日分）
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 対象日に使用される全モーター（会場別）を取得
        cursor.execute("""
            SELECT DISTINCT ra.venue_code, e.motor_number
            FROM entries e
            JOIN races ra ON e.race_id = ra.id
            WHERE ra.race_date = ?
              AND e.motor_number IS NOT NULL
        """, [target_date])

        motors = [(row['venue_code'], row['motor_number']) for row in cursor.fetchall()]

        if not motors:
            cursor.close()
            return

        # 90日前の日付
        start_date = (datetime.strptime(target_date, '%Y-%m-%d') - timedelta(days=90)).strftime('%Y-%m-%d')

        motor_stats = {}

        # 会場ごとにグループ化してクエリを発行
        venue_motors = defaultdict(list)
        for venue_code, motor_number in motors:
            venue_motors[venue_code].append(motor_number)

        for venue_code, motor_numbers in venue_motors.items():
            placeholders = ','.join('?' * len(motor_numbers))
            query = f"""
                SELECT
                    e.motor_number,
                    COUNT(*) as total_races,
                    SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN r.rank <= 2 THEN 1 ELSE 0 END) as place_2,
                    SUM(CASE WHEN r.rank <= 3 THEN 1 ELSE 0 END) as place_3,
                    AVG(r.rank) as avg_rank
                FROM results r
                JOIN races ra ON r.race_id = ra.id
                JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
                WHERE ra.venue_code = ?
                  AND e.motor_number IN ({placeholders})
                  AND ra.race_date >= ?
                  AND ra.race_date < ?
                  AND r.is_invalid = 0
                GROUP BY e.motor_number
            """

            cursor.execute(query, [venue_code] + motor_numbers + [start_date, target_date])

            for row in cursor.fetchall():
                motor_num = row['motor_number']
                total = row['total_races']
                key = (venue_code, motor_num)
                motor_stats[key] = {
                    'total_races': total,
                    'win_count': row['win_count'],
                    'win_rate': row['win_count'] / total if total > 0 else 0.0,
                    'place_rate_2': row['place_2'] / total if total > 0 else 0.0,
                    'place_rate_3': row['place_3'] / total if total > 0 else 0.0,
                    'avg_rank': row['avg_rank']
                }

        self._cache['motor_stats'] = motor_stats
        cursor.close()

    def _load_racer_st_stats_batch(self, target_date: str) -> None:
        """
        選手のST統計を一括取得（180日分）

        get_racer_st_stats用のデータ:
        - avg_st: 平均ST
        - flying_rate: フライング率
        - late_rate: 出遅れ率
        - total_st_records: ST記録数
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 対象日に出走する全選手を取得
        cursor.execute("""
            SELECT DISTINCT e.racer_number
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
        """, [target_date])

        racer_numbers = [row['racer_number'] for row in cursor.fetchall()]

        if not racer_numbers:
            cursor.close()
            return

        # 180日前の日付
        start_date = (datetime.strptime(target_date, '%Y-%m-%d') - timedelta(days=180)).strftime('%Y-%m-%d')

        # プレースホルダー作成
        placeholders = ','.join('?' * len(racer_numbers))

        # ST統計を一括取得
        query = f"""
            SELECT
                e.racer_number,
                AVG(rd.st_time) as avg_st,
                COUNT(*) as total_st,
                SUM(CASE WHEN rd.st_time < 0 THEN 1 ELSE 0 END) as flying_count,
                SUM(CASE WHEN rd.st_time > 0.20 THEN 1 ELSE 0 END) as late_count
            FROM race_details rd
            JOIN races ra ON rd.race_id = ra.id
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            WHERE e.racer_number IN ({placeholders})
              AND ra.race_date >= ?
              AND ra.race_date < ?
              AND rd.st_time IS NOT NULL
            GROUP BY e.racer_number
        """

        cursor.execute(query, racer_numbers + [start_date, target_date])

        racer_st_stats = {}
        for row in cursor.fetchall():
            racer_num = row['racer_number']
            total = row['total_st']
            if total > 0:
                racer_st_stats[racer_num] = {
                    'avg_st': row['avg_st'],
                    'flying_rate': row['flying_count'] / total,
                    'late_rate': row['late_count'] / total,
                    'total_st_records': total
                }
            else:
                racer_st_stats[racer_num] = {
                    'avg_st': None,
                    'flying_rate': 0.0,
                    'late_rate': 0.0,
                    'total_st_records': 0
                }

        self._cache['racer_st_stats'] = racer_st_stats
        cursor.close()

    def _load_racer_recent_form_batch(self, target_date: str, recent_races: int = 10) -> None:
        """
        選手の直近成績を一括取得

        get_racer_recent_form用のデータ:
        - recent_races: 直近のレース着順リスト
        - recent_win_rate: 直近勝率
        - recent_place_rate_3: 直近3連対率
        - form_trend: 調子の傾向 ('up', 'down', 'stable', 'unknown')
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 対象日に出走する全選手を取得
        cursor.execute("""
            SELECT DISTINCT e.racer_number
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
        """, [target_date])

        racer_numbers = [row['racer_number'] for row in cursor.fetchall()]

        if not racer_numbers:
            cursor.close()
            return

        placeholders = ','.join('?' * len(racer_numbers))

        # ウィンドウ関数を使用して各選手の直近10レースを取得
        query = f"""
            SELECT
                racer_number,
                rank,
                race_date,
                rn
            FROM (
                SELECT
                    e.racer_number,
                    r.rank,
                    ra.race_date,
                    ROW_NUMBER() OVER (
                        PARTITION BY e.racer_number
                        ORDER BY ra.race_date DESC, ra.race_number DESC
                    ) as rn
                FROM results r
                JOIN races ra ON r.race_id = ra.id
                JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
                WHERE e.racer_number IN ({placeholders})
                  AND ra.race_date < ?
                  AND r.is_invalid = 0
            ) sub
            WHERE rn <= ?
            ORDER BY racer_number, rn
        """

        cursor.execute(query, racer_numbers + [target_date, recent_races])

        # 選手ごとにグループ化
        racer_recent_form = defaultdict(list)
        for row in cursor.fetchall():
            racer_num = row['racer_number']
            rank = int(row['rank']) if row['rank'] else 0
            racer_recent_form[racer_num].append(rank)

        # 統計計算
        racer_form_stats = {}
        for racer_num, ranks in racer_recent_form.items():
            total = len(ranks)
            if total > 0:
                win_count = sum(1 for r in ranks if r == 1)
                place_3_count = sum(1 for r in ranks if r <= 3)

                # 調子の傾向（前半5レースと後半5レースで比較）
                form_trend = 'unknown'
                if total >= 10:
                    first_half_avg = sum(ranks[:5]) / 5
                    second_half_avg = sum(ranks[5:]) / 5
                    if second_half_avg < first_half_avg - 0.5:
                        form_trend = 'up'  # 着順が改善（数字が小さく）
                    elif second_half_avg > first_half_avg + 0.5:
                        form_trend = 'down'
                    else:
                        form_trend = 'stable'

                racer_form_stats[racer_num] = {
                    'recent_races': ranks,
                    'recent_win_rate': win_count / total,
                    'recent_place_rate_3': place_3_count / total,
                    'form_trend': form_trend
                }
            else:
                racer_form_stats[racer_num] = {
                    'recent_races': [],
                    'recent_win_rate': 0.0,
                    'recent_place_rate_3': 0.0,
                    'form_trend': 'unknown'
                }

        self._cache['racer_recent_form'] = racer_form_stats
        cursor.close()

    def _load_boat_stats_batch(self, target_date: str) -> None:
        """
        ボート成績を一括取得（90日分）

        get_boat_stats用のデータ:
        - total_races: レース数
        - win_count: 1着回数
        - win_rate: 勝率
        - place_rate_2, place_rate_3: 2連対率、3連対率
        - avg_rank: 平均着順
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 対象日に出走するボート（会場+ボート番号）を取得
        cursor.execute("""
            SELECT DISTINCT r.venue_code, e.boat_number
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
              AND e.boat_number IS NOT NULL
        """, [target_date])

        boats = [(row['venue_code'], row['boat_number']) for row in cursor.fetchall()]

        if not boats:
            cursor.close()
            return

        # 90日前の日付
        start_date = (datetime.strptime(target_date, '%Y-%m-%d') - timedelta(days=90)).strftime('%Y-%m-%d')

        boat_stats = {}

        # 会場ごとにグループ化してクエリを発行
        venue_boats = defaultdict(list)
        for venue_code, boat_number in boats:
            venue_boats[venue_code].append(boat_number)

        for venue_code, boat_numbers in venue_boats.items():
            placeholders = ','.join('?' * len(boat_numbers))
            query = f"""
                SELECT
                    e.boat_number,
                    COUNT(*) as total_races,
                    SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN r.rank <= 2 THEN 1 ELSE 0 END) as place_2,
                    SUM(CASE WHEN r.rank <= 3 THEN 1 ELSE 0 END) as place_3,
                    AVG(r.rank) as avg_rank
                FROM results r
                JOIN races ra ON r.race_id = ra.id
                JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
                WHERE ra.venue_code = ?
                  AND e.boat_number IN ({placeholders})
                  AND ra.race_date >= ?
                  AND ra.race_date < ?
                  AND r.is_invalid = 0
                GROUP BY e.boat_number
            """

            cursor.execute(query, [venue_code] + boat_numbers + [start_date, target_date])

            for row in cursor.fetchall():
                boat_num = row['boat_number']
                total = row['total_races']
                key = (venue_code, boat_num)
                if total > 0:
                    boat_stats[key] = {
                        'total_races': total,
                        'win_count': row['win_count'],
                        'win_rate': row['win_count'] / total,
                        'place_rate_2': row['place_2'] / total,
                        'place_rate_3': row['place_3'] / total,
                        'avg_rank': row['avg_rank']
                    }
                else:
                    boat_stats[key] = {
                        'total_races': 0,
                        'win_count': 0,
                        'win_rate': 0.0,
                        'place_rate_2': 0.0,
                        'place_rate_3': 0.0,
                        'avg_rank': 0.0
                    }

        self._cache['boat_stats'] = boat_stats
        cursor.close()

    def _load_motor_recent_form_batch(self, target_date: str, recent_races: int = 10) -> None:
        """
        モーターの直近成績を一括取得

        get_motor_recent_form用のデータ:
        - recent_races: 直近のレース着順リスト
        - recent_win_rate: 直近勝率
        - recent_place_rate_3: 直近3連対率
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 対象日に出走するモーター（会場+モーター番号）を取得
        cursor.execute("""
            SELECT DISTINCT r.venue_code, e.motor_number
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
              AND e.motor_number IS NOT NULL
        """, [target_date])

        motors = [(row['venue_code'], row['motor_number']) for row in cursor.fetchall()]

        if not motors:
            cursor.close()
            return

        motor_recent_form = {}

        # 会場ごとにグループ化
        venue_motors = defaultdict(list)
        for venue_code, motor_number in motors:
            venue_motors[venue_code].append(motor_number)

        for venue_code, motor_numbers in venue_motors.items():
            placeholders = ','.join('?' * len(motor_numbers))

            # ウィンドウ関数を使用して各モーターの直近10レースを取得
            query = f"""
                SELECT
                    motor_number,
                    rank,
                    rn
                FROM (
                    SELECT
                        e.motor_number,
                        r.rank,
                        ROW_NUMBER() OVER (
                            PARTITION BY e.motor_number
                            ORDER BY ra.race_date DESC, ra.race_number DESC
                        ) as rn
                    FROM results r
                    JOIN races ra ON r.race_id = ra.id
                    JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
                    WHERE ra.venue_code = ?
                      AND e.motor_number IN ({placeholders})
                      AND ra.race_date < ?
                      AND r.is_invalid = 0
                ) sub
                WHERE rn <= ?
                ORDER BY motor_number, rn
            """

            cursor.execute(query, [venue_code] + motor_numbers + [target_date, recent_races])

            # モーターごとにグループ化
            motor_ranks = defaultdict(list)
            for row in cursor.fetchall():
                motor_num = row['motor_number']
                rank = int(row['rank']) if row['rank'] else 0
                motor_ranks[motor_num].append(rank)

            # 統計計算
            for motor_num, ranks in motor_ranks.items():
                total = len(ranks)
                key = (venue_code, motor_num)
                if total > 0:
                    win_count = sum(1 for r in ranks if r == 1)
                    place_3_count = sum(1 for r in ranks if r <= 3)
                    motor_recent_form[key] = {
                        'recent_races': ranks,
                        'recent_win_rate': win_count / total,
                        'recent_place_rate_3': place_3_count / total
                    }
                else:
                    motor_recent_form[key] = {
                        'recent_races': [],
                        'recent_win_rate': 0.0,
                        'recent_place_rate_3': 0.0
                    }

        self._cache['motor_recent_form'] = motor_recent_form
        cursor.close()

    def _load_kimarite_stats_batch(self, target_date: str) -> None:
        """
        決まり手統計を一括取得（180日分）

        - 選手×コース別の決まり手傾向
        - 会場×コース別の決まり手傾向
        """
        conn = self._connect()
        cursor = conn.cursor()

        start_date = (datetime.strptime(target_date, '%Y-%m-%d') - timedelta(days=180)).strftime('%Y-%m-%d')

        # 対象日に出走する選手を取得
        cursor.execute("""
            SELECT DISTINCT e.racer_number
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
        """, [target_date])

        racer_numbers = [row['racer_number'] for row in cursor.fetchall()]

        if racer_numbers:
            placeholders = ','.join('?' * len(racer_numbers))

            # 選手×コース別の決まり手統計
            query_racer = f"""
                SELECT
                    e.racer_number,
                    e.pit_number as course,
                    r.winning_technique,
                    COUNT(*) as count
                FROM results r
                JOIN races ra ON r.race_id = ra.id
                JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
                WHERE e.racer_number IN ({placeholders})
                  AND r.rank = 1
                  AND r.winning_technique IS NOT NULL
                  AND ra.race_date >= ?
                  AND ra.race_date < ?
                GROUP BY e.racer_number, e.pit_number, r.winning_technique
            """

            cursor.execute(query_racer, racer_numbers + [start_date, target_date])

            racer_kimarite = defaultdict(lambda: defaultdict(dict))
            for row in cursor.fetchall():
                racer_num = row['racer_number']
                course = row['course']
                technique = row['winning_technique']
                count = row['count']
                racer_kimarite[racer_num][course][technique] = count

            self._cache['racer_kimarite'] = dict(racer_kimarite)

        # 会場×コース別の決まり手統計
        cursor.execute("""
            SELECT DISTINCT ra.venue_code
            FROM entries e
            JOIN races ra ON e.race_id = ra.id
            WHERE ra.race_date = ?
        """, [target_date])

        venue_codes = [row['venue_code'] for row in cursor.fetchall()]

        if venue_codes:
            placeholders = ','.join('?' * len(venue_codes))

            query_venue = f"""
                SELECT
                    ra.venue_code,
                    r.pit_number as course,
                    r.winning_technique,
                    COUNT(*) as count
                FROM results r
                JOIN races ra ON r.race_id = ra.id
                WHERE ra.venue_code IN ({placeholders})
                  AND r.rank = 1
                  AND r.winning_technique IS NOT NULL
                  AND ra.race_date >= ?
                  AND ra.race_date < ?
                GROUP BY ra.venue_code, r.pit_number, r.winning_technique
            """

            cursor.execute(query_venue, venue_codes + [start_date, target_date])

            venue_kimarite = defaultdict(lambda: defaultdict(dict))
            for row in cursor.fetchall():
                venue = row['venue_code']
                course = row['course']
                technique = row['winning_technique']
                count = row['count']
                venue_kimarite[venue][course][technique] = count

            self._cache['venue_kimarite'] = dict(venue_kimarite)

        cursor.close()

    def _load_grade_stats_batch(self, target_date: str) -> None:
        """
        グレード別成績を一括取得（365日分）
        """
        conn = self._connect()
        cursor = conn.cursor()

        start_date = (datetime.strptime(target_date, '%Y-%m-%d') - timedelta(days=365)).strftime('%Y-%m-%d')

        # 対象日に出走する選手を取得
        cursor.execute("""
            SELECT DISTINCT e.racer_number
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
        """, [target_date])

        racer_numbers = [row['racer_number'] for row in cursor.fetchall()]

        if not racer_numbers:
            cursor.close()
            return

        placeholders = ','.join('?' * len(racer_numbers))

        # 選手×グレード別成績
        query = f"""
            SELECT
                e.racer_number,
                ra.race_grade,
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN r.rank <= 3 THEN 1 ELSE 0 END) as top3,
                AVG(r.rank) as avg_rank
            FROM entries e
            JOIN races ra ON e.race_id = ra.id
            LEFT JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
            WHERE e.racer_number IN ({placeholders})
              AND ra.race_date >= ?
              AND ra.race_date < ?
              AND r.rank IS NOT NULL
            GROUP BY e.racer_number, ra.race_grade
        """

        cursor.execute(query, racer_numbers + [start_date, target_date])

        grade_stats = defaultdict(dict)
        for row in cursor.fetchall():
            racer_num = row['racer_number']
            grade = row['race_grade'] or '一般'
            total = row['total_races']
            grade_stats[racer_num][grade] = {
                'total_races': total,
                'wins': row['wins'],
                'win_rate': (row['wins'] / total * 100) if total > 0 else 0.0,
                'top3': row['top3'],
                'top3_rate': (row['top3'] / total * 100) if total > 0 else 0.0,
                'avg_rank': row['avg_rank']
            }

        self._cache['grade_stats'] = dict(grade_stats)
        cursor.close()

    # ========================================
    # キャッシュ取得メソッド
    # ========================================

    def get_racer_overall_stats(self, racer_number: int) -> Optional[Dict]:
        """選手の全体成績を取得"""
        return self._cache.get('racer_overall', {}).get(racer_number)

    def get_racer_course_stats(self, racer_number: int, course: int) -> Optional[Dict]:
        """選手のコース別成績を取得"""
        return self._cache.get('racer_course', {}).get(racer_number, {}).get(course)

    def get_racer_venue_stats(self, racer_number: int, venue_code: str) -> Optional[Dict]:
        """選手の会場別成績を取得"""
        return self._cache.get('racer_venue', {}).get(racer_number, {}).get(venue_code)

    def get_motor_stats(self, venue_code: str, motor_number: int) -> Optional[Dict]:
        """モーター成績を取得"""
        key = (venue_code, motor_number)
        return self._cache.get('motor_stats', {}).get(key)

    def get_racer_kimarite(self, racer_number: int, course: int) -> Dict:
        """選手×コースの決まり手統計を取得"""
        return self._cache.get('racer_kimarite', {}).get(racer_number, {}).get(course, {})

    def get_venue_kimarite(self, venue_code: str, course: int) -> Dict:
        """会場×コースの決まり手統計を取得"""
        return self._cache.get('venue_kimarite', {}).get(venue_code, {}).get(course, {})

    def get_grade_stats(self, racer_number: int, race_grade: str) -> Optional[Dict]:
        """選手のグレード別成績を取得"""
        grade = race_grade or '一般'
        return self._cache.get('grade_stats', {}).get(racer_number, {}).get(grade)

    def is_loaded(self) -> bool:
        """キャッシュがロード済みか確認"""
        return self._cache_loaded

    def get_cache_date(self) -> Optional[str]:
        """キャッシュされているデータの日付を取得"""
        return self._cache_date

    # ========================================
    # ExtendedScorer用の追加メソッド
    # ========================================

    def _load_race_details_batch(self, target_date: str) -> None:
        """
        レース詳細データを一括取得

        展示タイム、チルト角度、ST、実際のコースなど
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 対象日の全レース詳細を取得
        cursor.execute("""
            SELECT
                rd.race_id,
                rd.pit_number,
                rd.exhibition_time,
                rd.tilt_angle,
                rd.st_time,
                rd.actual_course
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date = ?
        """, [target_date])

        race_details = defaultdict(dict)
        for row in cursor.fetchall():
            race_id = row['race_id']
            pit = row['pit_number']
            race_details[race_id][pit] = {
                'exhibition_time': row['exhibition_time'],
                'tilt_angle': row['tilt_angle'],
                'st_time': row['st_time'],
                'actual_course': row['actual_course']
            }

        self._cache['race_details'] = dict(race_details)
        cursor.close()

    def _load_racer_features_batch(self, target_date: str) -> None:
        """
        選手特徴データを一括取得（racer_features テーブル）

        直近3/5/10走の成績など
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 対象日に出走する選手を取得
        cursor.execute("""
            SELECT DISTINCT e.racer_number
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
        """, [target_date])

        racer_numbers = [row['racer_number'] for row in cursor.fetchall()]

        if not racer_numbers:
            cursor.close()
            return

        placeholders = ','.join('?' * len(racer_numbers))

        # 各選手の最新のracer_featuresを取得
        query = f"""
            SELECT
                racer_number,
                recent_avg_rank_3,
                recent_avg_rank_5,
                recent_avg_rank_10,
                recent_win_rate_3,
                recent_win_rate_5,
                recent_win_rate_10,
                total_races,
                race_date
            FROM racer_features
            WHERE racer_number IN ({placeholders})
              AND race_date <= ?
            ORDER BY racer_number, race_date DESC
        """

        cursor.execute(query, racer_numbers + [target_date])

        # 各選手の最新データのみ保持
        racer_features = {}
        seen_racers = set()
        for row in cursor.fetchall():
            racer_num = row['racer_number']
            if racer_num in seen_racers:
                continue
            seen_racers.add(racer_num)

            racer_features[racer_num] = {
                'recent_avg_rank_3': row['recent_avg_rank_3'],
                'recent_avg_rank_5': row['recent_avg_rank_5'],
                'recent_avg_rank_10': row['recent_avg_rank_10'],
                'recent_win_rate_3': row['recent_win_rate_3'],
                'recent_win_rate_5': row['recent_win_rate_5'],
                'recent_win_rate_10': row['recent_win_rate_10'],
                'total_races': row['total_races'],
                'feature_date': row['race_date']
            }

        self._cache['racer_features'] = racer_features
        cursor.close()

    def _load_racer_venue_features_batch(self, target_date: str) -> None:
        """
        選手×会場特徴データを一括取得

        会場別勝率など
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 対象日に出走する選手と会場の組み合わせを取得
        cursor.execute("""
            SELECT DISTINCT e.racer_number, r.venue_code
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
        """, [target_date])

        racer_venue_pairs = [(row['racer_number'], row['venue_code']) for row in cursor.fetchall()]

        if not racer_venue_pairs:
            cursor.close()
            return

        racer_venue_features = defaultdict(dict)

        # 各組み合わせの最新データを取得
        for racer_num, venue_code in racer_venue_pairs:
            cursor.execute("""
                SELECT
                    venue_win_rate,
                    venue_avg_rank,
                    venue_races
                FROM racer_venue_features
                WHERE racer_number = ?
                  AND venue_code = ?
                  AND race_date <= ?
                ORDER BY race_date DESC
                LIMIT 1
            """, [racer_num, venue_code, target_date])

            row = cursor.fetchone()
            if row:
                racer_venue_features[racer_num][venue_code] = {
                    'venue_win_rate': row['venue_win_rate'],
                    'venue_avg_rank': row['venue_avg_rank'],
                    'venue_races': row['venue_races']
                }

        self._cache['racer_venue_features'] = dict(racer_venue_features)
        cursor.close()

    def _load_course_entry_tendency_batch(self, target_date: str) -> None:
        """
        進入コース傾向データを一括取得

        選手ごとの枠番→実際のコースの傾向
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 対象日に出走する選手を取得
        cursor.execute("""
            SELECT DISTINCT e.racer_number
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
        """, [target_date])

        racer_numbers = [row['racer_number'] for row in cursor.fetchall()]

        if not racer_numbers:
            cursor.close()
            return

        placeholders = ','.join('?' * len(racer_numbers))

        # 選手の過去の進入傾向を集計
        query = f"""
            SELECT
                e.racer_number,
                e.pit_number,
                rd.actual_course,
                COUNT(*) as cnt
            FROM entries e
            JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.racer_number IN ({placeholders})
              AND rd.actual_course IS NOT NULL
            GROUP BY e.racer_number, e.pit_number, rd.actual_course
        """

        cursor.execute(query, racer_numbers)

        course_entry_tendency = defaultdict(lambda: defaultdict(dict))
        for row in cursor.fetchall():
            racer_num = row['racer_number']
            pit = row['pit_number']
            course = row['actual_course']
            cnt = row['cnt']
            course_entry_tendency[racer_num][pit][course] = cnt

        self._cache['course_entry_tendency'] = dict(course_entry_tendency)
        cursor.close()

    def _load_session_performance_batch(self, target_date: str) -> None:
        """
        節間成績データを一括取得

        同一会場での直近7日以内の成績
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 対象日に出走する選手×会場の組み合わせを取得
        cursor.execute("""
            SELECT DISTINCT e.racer_number, r.venue_code
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
        """, [target_date])

        racer_venue_pairs = [(row['racer_number'], row['venue_code']) for row in cursor.fetchall()]

        if not racer_venue_pairs:
            cursor.close()
            return

        session_performance = defaultdict(dict)

        # 各組み合わせの節間成績を取得
        for racer_num, venue_code in racer_venue_pairs:
            cursor.execute('''
                SELECT res.rank, r.race_date, r.race_number
                FROM entries e
                JOIN races r ON e.race_id = r.id
                LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
                WHERE e.racer_number = ?
                  AND r.venue_code = ?
                  AND r.race_date < ?
                  AND r.race_date >= date(?, '-7 days')
                  AND res.rank IS NOT NULL
                  AND res.rank NOT IN ('F', 'L', '欠', '失')
                ORDER BY r.race_date DESC, r.race_number DESC
                LIMIT 12
            ''', [racer_num, venue_code, target_date, target_date])

            results = cursor.fetchall()

            if results:
                session_performance[racer_num][venue_code] = [
                    {'rank': row['rank'], 'race_date': row['race_date'], 'race_number': row['race_number']}
                    for row in results
                ]

        self._cache['session_performance'] = dict(session_performance)
        cursor.close()

    def _load_previous_race_batch(self, target_date: str) -> None:
        """
        前走データを一括取得

        各選手の直前のレース結果とグレード
        """
        conn = self._connect()
        cursor = conn.cursor()

        # 対象日に出走する選手を取得
        cursor.execute("""
            SELECT DISTINCT e.racer_number
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
        """, [target_date])

        racer_numbers = [row['racer_number'] for row in cursor.fetchall()]

        if not racer_numbers:
            cursor.close()
            return

        # 一括で全選手の前走を取得（サブクエリで最新を特定）
        placeholders = ','.join('?' * len(racer_numbers))
        query = f"""
            SELECT
                e.racer_number,
                r.race_grade,
                res.rank,
                r.race_date,
                ROW_NUMBER() OVER (PARTITION BY e.racer_number ORDER BY r.race_date DESC, r.race_number DESC) as rn
            FROM entries e
            JOIN races r ON e.race_id = r.id
            LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
            WHERE e.racer_number IN ({placeholders})
              AND r.race_date < ?
        """

        cursor.execute(query, racer_numbers + [target_date])

        previous_race = {}
        for row in cursor.fetchall():
            racer_num = row['racer_number']
            rn = row['rn'] if 'rn' in row.keys() else row[4]  # ROW_NUMBER

            # 各選手の最新（rn=1）のみ保持
            if rn == 1:
                previous_race[racer_num] = {
                    'prev_grade': row['race_grade'],
                    'prev_rank': row['rank'],
                    'prev_date': row['race_date']
                }

        self._cache['previous_race'] = previous_race
        cursor.close()

    # 新しいゲッターメソッド

    def get_race_details(self, race_id: int, pit_number: int) -> Optional[Dict]:
        """レース詳細データを取得"""
        return self._cache.get('race_details', {}).get(race_id, {}).get(pit_number)

    def get_racer_features(self, racer_number: int) -> Optional[Dict]:
        """選手特徴データを取得"""
        return self._cache.get('racer_features', {}).get(racer_number)

    def get_racer_venue_features(self, racer_number: int, venue_code: str) -> Optional[Dict]:
        """選手×会場特徴データを取得"""
        return self._cache.get('racer_venue_features', {}).get(racer_number, {}).get(venue_code)

    def get_course_entry_tendency(self, racer_number: int, pit_number: int) -> Dict:
        """進入コース傾向を取得"""
        return self._cache.get('course_entry_tendency', {}).get(racer_number, {}).get(pit_number, {})

    def get_session_performance(self, racer_number: int, venue_code: str) -> List:
        """節間成績を取得"""
        return self._cache.get('session_performance', {}).get(racer_number, {}).get(venue_code, [])

    def get_previous_race(self, racer_number: int) -> Optional[Dict]:
        """前走データを取得"""
        return self._cache.get('previous_race', {}).get(racer_number)

    def get_racer_recent_form(self, racer_number: int, recent_races: int = 10) -> Optional[Dict]:
        """選手の直近成績を取得（キャッシュから）"""
        return self._cache.get('racer_recent_form', {}).get(racer_number)

    def get_racer_st_stats(self, racer_number: int) -> Optional[Dict]:
        """選手のST統計を取得（キャッシュから）"""
        return self._cache.get('racer_st_stats', {}).get(racer_number)

    def get_motor_recent_form(self, venue_code: str, motor_number: int, recent_races: int = 10) -> Optional[Dict]:
        """モーターの直近成績を取得（キャッシュから）"""
        return self._cache.get('motor_recent_form', {}).get((venue_code, motor_number))

    def get_boat_stats(self, venue_code: str, boat_number: int) -> Optional[Dict]:
        """ボートの成績統計を取得（キャッシュから）"""
        return self._cache.get('boat_stats', {}).get((venue_code, boat_number))

    def get_race_info(self, race_id: int) -> Optional[Dict]:
        """レース情報を取得（キャッシュから）"""
        return self._cache.get('races', {}).get(race_id)

    def get_race_entries(self, race_id: int) -> List[Dict]:
        """エントリー情報を取得（キャッシュから）"""
        return self._cache.get('entries', {}).get(race_id, [])
