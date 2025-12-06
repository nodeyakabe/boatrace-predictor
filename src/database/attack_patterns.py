# -*- coding: utf-8 -*-
"""
Attack Patterns Database - Phase 3

会場攻略・選手攻略のためのパターンDB構築
想定外を減らすための詳細データ分析
"""

import sqlite3
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import json


@dataclass
class VenuePattern:
    """会場の攻略パターン"""
    venue_code: str
    venue_name: str
    # コース別1着率
    course_win_rates: List[float]  # [1C, 2C, 3C, 4C, 5C, 6C]
    # コース別2着率
    course_second_rates: List[float]
    # コース別3着率
    course_third_rates: List[float]
    # 逃げ決まり率
    nige_rate: float
    # 差し決まり率
    sashi_rate: float
    # まくり決まり率
    makuri_rate: float
    # まくり差し決まり率
    makurisashi_rate: float
    # 荒れやすさ（1コース以外が勝つ率）
    upset_rate: float
    # 高配当出現率（5000円以上）
    high_payout_rate: float


@dataclass
class RacerPattern:
    """選手の攻略パターン"""
    racer_number: int
    racer_name: str
    rank: str  # A1, A2, B1, B2
    # コース別1着率
    course_win_rates: Dict[int, float]  # {1: 0.55, 2: 0.12, ...}
    # コース別2着率
    course_second_rates: Dict[int, float]
    # 得意会場
    strong_venues: List[str]  # venue_codes
    # 苦手会場
    weak_venues: List[str]
    # スタートタイミング平均
    avg_start_timing: float
    # スタート安定度（標準偏差）
    start_stability: float


class AttackPatternDB:
    """
    攻略パターンデータベース

    会場・選手の詳細パターンを分析・キャッシュして
    予測精度向上に活用
    """

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path
        self._venue_cache = {}
        self._racer_cache = {}
        self._venue_racer_cache = {}
        self._ensure_tables()

    def _ensure_tables(self):
        """攻略パターン用のテーブルを作成"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 会場攻略パターンテーブル
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS venue_attack_patterns (
                    venue_code TEXT PRIMARY KEY,
                    venue_name TEXT,
                    course_win_rates TEXT,  -- JSON
                    course_second_rates TEXT,
                    course_third_rates TEXT,
                    nige_rate REAL,
                    sashi_rate REAL,
                    makuri_rate REAL,
                    makurisashi_rate REAL,
                    upset_rate REAL,
                    high_payout_rate REAL,
                    total_races INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 選手攻略パターンテーブル
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS racer_attack_patterns (
                    racer_number INTEGER PRIMARY KEY,
                    racer_name TEXT,
                    rank TEXT,
                    course_win_rates TEXT,  -- JSON
                    course_second_rates TEXT,
                    strong_venues TEXT,  -- JSON array
                    weak_venues TEXT,
                    avg_start_timing REAL,
                    start_stability REAL,
                    total_races INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 会場×選手クロスパターンテーブル
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS venue_racer_patterns (
                    venue_code TEXT,
                    racer_number INTEGER,
                    win_rate REAL,
                    second_rate REAL,
                    third_rate REAL,
                    avg_rank REAL,
                    total_races INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (venue_code, racer_number)
                )
            ''')

            conn.commit()

    def build_venue_patterns(self, min_races: int = 100):
        """
        全会場の攻略パターンを構築

        Args:
            min_races: 最低レース数（これ以上のデータがある会場のみ）
        """
        print("Building venue attack patterns...")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 会場一覧を取得
            cursor.execute('''
                SELECT DISTINCT venue_code FROM races
            ''')
            venues = [row[0] for row in cursor.fetchall()]

            for venue_code in venues:
                pattern = self._analyze_venue(cursor, venue_code, min_races)
                if pattern:
                    self._save_venue_pattern(cursor, pattern)
                    self._venue_cache[venue_code] = pattern

            conn.commit()

        print(f"Built patterns for {len(self._venue_cache)} venues")

    def _analyze_venue(self, cursor, venue_code: str, min_races: int) -> Optional[Dict]:
        """会場の攻略パターンを分析"""

        # コース別成績（pit_numberをコースとして使用）
        cursor.execute('''
            SELECT
                e.pit_number as course,
                COUNT(*) as total,
                SUM(CASE WHEN res.rank = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN res.rank = 2 THEN 1 ELSE 0 END) as seconds,
                SUM(CASE WHEN res.rank = 3 THEN 1 ELSE 0 END) as thirds
            FROM results res
            JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
            JOIN races r ON res.race_id = r.id
            WHERE r.venue_code = ? AND res.is_invalid = 0
            GROUP BY e.pit_number
        ''', (venue_code,))

        course_stats = {}
        total_races = 0
        for course, total, wins, seconds, thirds in cursor.fetchall():
            if course and 1 <= course <= 6:
                course_stats[course] = {
                    'total': total,
                    'wins': wins,
                    'seconds': seconds,
                    'thirds': thirds
                }
                total_races = max(total_races, total)

        if total_races < min_races:
            return None

        # コース別の率を計算
        course_win_rates = []
        course_second_rates = []
        course_third_rates = []

        for c in range(1, 7):
            if c in course_stats and course_stats[c]['total'] > 0:
                stats = course_stats[c]
                course_win_rates.append(stats['wins'] / stats['total'])
                course_second_rates.append(stats['seconds'] / stats['total'])
                course_third_rates.append(stats['thirds'] / stats['total'])
            else:
                course_win_rates.append(0.0)
                course_second_rates.append(0.0)
                course_third_rates.append(0.0)

        # 決まり手別集計
        cursor.execute('''
            SELECT
                res.winning_technique,
                COUNT(*) as count
            FROM results res
            JOIN races r ON res.race_id = r.id
            WHERE r.venue_code = ? AND res.rank = 1 AND res.is_invalid = 0
            GROUP BY res.winning_technique
        ''', (venue_code,))

        techniques = {}
        total_wins = 0
        for tech, count in cursor.fetchall():
            if tech:
                techniques[tech] = count
                total_wins += count

        nige_rate = techniques.get('逃げ', 0) / total_wins if total_wins > 0 else 0
        sashi_rate = techniques.get('差し', 0) / total_wins if total_wins > 0 else 0
        makuri_rate = techniques.get('まくり', 0) / total_wins if total_wins > 0 else 0
        makurisashi_rate = techniques.get('まくり差し', 0) / total_wins if total_wins > 0 else 0

        # 荒れ率（1コース以外が勝つ率）
        upset_rate = 1.0 - course_win_rates[0] if course_win_rates else 0.5

        # 高配当率
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN p.amount >= 5000 THEN 1 ELSE 0 END) as high_payout
            FROM payouts p
            JOIN races r ON p.race_id = r.id
            WHERE r.venue_code = ? AND p.bet_type = 'trifecta'
        ''', (venue_code,))

        row = cursor.fetchone()
        high_payout_rate = row[1] / row[0] if row and row[0] > 0 else 0.2

        # 会場名を取得（venue_dataテーブルから）
        cursor.execute('''
            SELECT venue_name FROM venue_data WHERE venue_code = ? LIMIT 1
        ''', (venue_code,))
        name_row = cursor.fetchone()
        venue_name = name_row[0] if name_row else venue_code

        return {
            'venue_code': venue_code,
            'venue_name': venue_name,
            'course_win_rates': course_win_rates,
            'course_second_rates': course_second_rates,
            'course_third_rates': course_third_rates,
            'nige_rate': nige_rate,
            'sashi_rate': sashi_rate,
            'makuri_rate': makuri_rate,
            'makurisashi_rate': makurisashi_rate,
            'upset_rate': upset_rate,
            'high_payout_rate': high_payout_rate,
            'total_races': total_races
        }

    def _save_venue_pattern(self, cursor, pattern: Dict):
        """会場パターンを保存"""
        cursor.execute('''
            INSERT OR REPLACE INTO venue_attack_patterns
            (venue_code, venue_name, course_win_rates, course_second_rates,
             course_third_rates, nige_rate, sashi_rate, makuri_rate,
             makurisashi_rate, upset_rate, high_payout_rate, total_races)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            pattern['venue_code'],
            pattern['venue_name'],
            json.dumps(pattern['course_win_rates']),
            json.dumps(pattern['course_second_rates']),
            json.dumps(pattern['course_third_rates']),
            pattern['nige_rate'],
            pattern['sashi_rate'],
            pattern['makuri_rate'],
            pattern['makurisashi_rate'],
            pattern['upset_rate'],
            pattern['high_payout_rate'],
            pattern['total_races']
        ))

    def build_racer_patterns(self, min_races: int = 30):
        """
        全選手の攻略パターンを構築

        Args:
            min_races: 最低レース数
        """
        print("Building racer attack patterns...")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 一定以上出走している選手を取得
            cursor.execute('''
                SELECT e.racer_number, e.racer_name, e.racer_rank,
                       COUNT(*) as race_count
                FROM entries e
                JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                WHERE res.is_invalid = 0
                GROUP BY e.racer_number
                HAVING race_count >= ?
            ''', (min_races,))

            racers = cursor.fetchall()
            print(f"Analyzing {len(racers)} racers...")

            for racer_number, racer_name, rank, _ in racers:
                pattern = self._analyze_racer(cursor, racer_number, racer_name, rank)
                if pattern:
                    self._save_racer_pattern(cursor, pattern)
                    self._racer_cache[racer_number] = pattern

            conn.commit()

        print(f"Built patterns for {len(self._racer_cache)} racers")

    def _analyze_racer(self, cursor, racer_number: int, racer_name: str, rank: str) -> Optional[Dict]:
        """選手の攻略パターンを分析"""

        # コース別成績（pit_numberをコースとして使用）
        cursor.execute('''
            SELECT
                e.pit_number as course,
                COUNT(*) as total,
                SUM(CASE WHEN res.rank = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN res.rank = 2 THEN 1 ELSE 0 END) as seconds
            FROM entries e
            JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            WHERE e.racer_number = ? AND res.is_invalid = 0
            GROUP BY e.pit_number
        ''', (racer_number,))

        course_win_rates = {}
        course_second_rates = {}
        total_races = 0

        for course, total, wins, seconds in cursor.fetchall():
            if course and 1 <= course <= 6 and total >= 5:
                course_win_rates[course] = wins / total
                course_second_rates[course] = seconds / total
                total_races += total

        if total_races < 10:
            return None

        # 会場別成績
        cursor.execute('''
            SELECT
                r.venue_code,
                COUNT(*) as total,
                AVG(res.rank) as avg_rank
            FROM entries e
            JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            JOIN races r ON e.race_id = r.id
            WHERE e.racer_number = ? AND res.is_invalid = 0
            GROUP BY r.venue_code
            HAVING total >= 5
        ''', (racer_number,))

        venue_results = []
        for venue_code, total, avg_rank in cursor.fetchall():
            venue_results.append({
                'venue_code': venue_code,
                'total': total,
                'avg_rank': avg_rank
            })

        # 得意・苦手会場を特定（平均着順で判定）
        strong_venues = [v['venue_code'] for v in venue_results if v['avg_rank'] < 3.0]
        weak_venues = [v['venue_code'] for v in venue_results if v['avg_rank'] > 4.0]

        # スタートタイミング（avg_stを使用）
        cursor.execute('''
            SELECT AVG(e.avg_st),
                   AVG(e.avg_st * e.avg_st) - AVG(e.avg_st) * AVG(e.avg_st)
            FROM entries e
            WHERE e.racer_number = ? AND e.avg_st IS NOT NULL
              AND e.avg_st > -1.0 AND e.avg_st < 1.0
        ''', (racer_number,))

        st_row = cursor.fetchone()
        avg_st = st_row[0] if st_row and st_row[0] else 0.15
        st_var = st_row[1] if st_row and st_row[1] else 0.01
        st_stability = st_var ** 0.5 if st_var and st_var >= 0 else 0.1

        return {
            'racer_number': racer_number,
            'racer_name': racer_name,
            'rank': rank,
            'course_win_rates': course_win_rates,
            'course_second_rates': course_second_rates,
            'strong_venues': strong_venues[:5],  # 上位5会場
            'weak_venues': weak_venues[:5],
            'avg_start_timing': avg_st,
            'start_stability': st_stability,
            'total_races': total_races
        }

    def _save_racer_pattern(self, cursor, pattern: Dict):
        """選手パターンを保存"""
        cursor.execute('''
            INSERT OR REPLACE INTO racer_attack_patterns
            (racer_number, racer_name, rank, course_win_rates, course_second_rates,
             strong_venues, weak_venues, avg_start_timing, start_stability, total_races)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            pattern['racer_number'],
            pattern['racer_name'],
            pattern['rank'],
            json.dumps(pattern['course_win_rates']),
            json.dumps(pattern['course_second_rates']),
            json.dumps(pattern['strong_venues']),
            json.dumps(pattern['weak_venues']),
            pattern['avg_start_timing'],
            pattern['start_stability'],
            pattern['total_races']
        ))

    def build_venue_racer_patterns(self, min_races: int = 10):
        """
        会場×選手のクロスパターンを構築
        """
        print("Building venue-racer cross patterns...")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    r.venue_code,
                    e.racer_number,
                    COUNT(*) as total,
                    AVG(res.rank) as avg_rank,
                    SUM(CASE WHEN res.rank = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN res.rank = 2 THEN 1 ELSE 0 END) as seconds,
                    SUM(CASE WHEN res.rank = 3 THEN 1 ELSE 0 END) as thirds
                FROM entries e
                JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                JOIN races r ON e.race_id = r.id
                WHERE res.is_invalid = 0
                GROUP BY r.venue_code, e.racer_number
                HAVING total >= ?
            ''', (min_races,))

            rows = cursor.fetchall()
            print(f"Processing {len(rows)} venue-racer combinations...")

            for venue_code, racer_number, total, avg_rank, wins, seconds, thirds in rows:
                cursor.execute('''
                    INSERT OR REPLACE INTO venue_racer_patterns
                    (venue_code, racer_number, win_rate, second_rate, third_rate,
                     avg_rank, total_races)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    venue_code,
                    racer_number,
                    wins / total,
                    seconds / total,
                    thirds / total,
                    avg_rank,
                    total
                ))

                key = (venue_code, racer_number)
                self._venue_racer_cache[key] = {
                    'win_rate': wins / total,
                    'second_rate': seconds / total,
                    'third_rate': thirds / total,
                    'avg_rank': avg_rank,
                    'total_races': total
                }

            conn.commit()

        print(f"Built {len(self._venue_racer_cache)} venue-racer patterns")

    def get_venue_pattern(self, venue_code: str) -> Optional[Dict]:
        """会場の攻略パターンを取得"""
        if venue_code in self._venue_cache:
            return self._venue_cache[venue_code]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM venue_attack_patterns WHERE venue_code = ?
            ''', (venue_code,))

            row = cursor.fetchone()
            if row:
                pattern = {
                    'venue_code': row[0],
                    'venue_name': row[1],
                    'course_win_rates': json.loads(row[2]) if row[2] else [],
                    'course_second_rates': json.loads(row[3]) if row[3] else [],
                    'course_third_rates': json.loads(row[4]) if row[4] else [],
                    'nige_rate': row[5],
                    'sashi_rate': row[6],
                    'makuri_rate': row[7],
                    'makurisashi_rate': row[8],
                    'upset_rate': row[9],
                    'high_payout_rate': row[10],
                    'total_races': row[11]
                }
                self._venue_cache[venue_code] = pattern
                return pattern

        return None

    def get_racer_pattern(self, racer_number: int) -> Optional[Dict]:
        """選手の攻略パターンを取得"""
        if racer_number in self._racer_cache:
            return self._racer_cache[racer_number]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM racer_attack_patterns WHERE racer_number = ?
            ''', (racer_number,))

            row = cursor.fetchone()
            if row:
                pattern = {
                    'racer_number': row[0],
                    'racer_name': row[1],
                    'rank': row[2],
                    'course_win_rates': json.loads(row[3]) if row[3] else {},
                    'course_second_rates': json.loads(row[4]) if row[4] else {},
                    'strong_venues': json.loads(row[5]) if row[5] else [],
                    'weak_venues': json.loads(row[6]) if row[6] else [],
                    'avg_start_timing': row[7],
                    'start_stability': row[8],
                    'total_races': row[9]
                }
                self._racer_cache[racer_number] = pattern
                return pattern

        return None

    def get_venue_racer_pattern(self, venue_code: str, racer_number: int) -> Optional[Dict]:
        """会場×選手のクロスパターンを取得"""
        key = (venue_code, racer_number)
        if key in self._venue_racer_cache:
            return self._venue_racer_cache[key]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT win_rate, second_rate, third_rate, avg_rank, total_races
                FROM venue_racer_patterns
                WHERE venue_code = ? AND racer_number = ?
            ''', (venue_code, racer_number))

            row = cursor.fetchone()
            if row:
                pattern = {
                    'win_rate': row[0],
                    'second_rate': row[1],
                    'third_rate': row[2],
                    'avg_rank': row[3],
                    'total_races': row[4]
                }
                self._venue_racer_cache[key] = pattern
                return pattern

        return None

    def get_upset_risk_venues(self, threshold: float = 0.55) -> List[Tuple[str, float]]:
        """
        荒れやすい会場（1コース勝率が低い）をリストアップ

        Args:
            threshold: 1コース勝率のしきい値（これ以下が荒れやすい）

        Returns:
            [(venue_code, upset_rate), ...]
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT venue_code, venue_name, upset_rate
                FROM venue_attack_patterns
                WHERE upset_rate > ?
                ORDER BY upset_rate DESC
            ''', (1.0 - threshold,))

            return [(row[0], row[2]) for row in cursor.fetchall()]

    def get_racer_strength_at_venue(
        self,
        venue_code: str,
        racer_numbers: List[int]
    ) -> Dict[int, float]:
        """
        指定会場での各選手の強さスコアを取得

        Args:
            venue_code: 会場コード
            racer_numbers: 選手番号リスト

        Returns:
            {racer_number: strength_score, ...}
        """
        strengths = {}

        for racer_number in racer_numbers:
            vr_pattern = self.get_venue_racer_pattern(venue_code, racer_number)
            racer_pattern = self.get_racer_pattern(racer_number)

            if vr_pattern:
                # 会場での実績あり
                # 勝率×2 + 2着率 + 3着率 - (平均着順-3.5)/10
                score = (
                    vr_pattern['win_rate'] * 2 +
                    vr_pattern['second_rate'] +
                    vr_pattern['third_rate'] -
                    (vr_pattern['avg_rank'] - 3.5) / 10
                )
                strengths[racer_number] = score
            elif racer_pattern:
                # 全体成績から推定
                avg_win = sum(racer_pattern['course_win_rates'].values()) / 6 if racer_pattern['course_win_rates'] else 0.1
                strengths[racer_number] = avg_win
            else:
                strengths[racer_number] = 0.1

        return strengths

    def build_all_patterns(self):
        """全パターンを一括構築"""
        print("=" * 60)
        print("Building all attack patterns...")
        print("=" * 60)

        self.build_venue_patterns()
        self.build_racer_patterns()
        self.build_venue_racer_patterns()

        print("=" * 60)
        print("All patterns built successfully!")
        print("=" * 60)


class PatternBasedPredictor:
    """
    攻略パターンを使った予測補正器
    """

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.attack_db = AttackPatternDB(db_path)

    def get_prediction_adjustments(
        self,
        race_id: int,
        base_predictions: Dict[int, float]
    ) -> Dict[int, float]:
        """
        攻略パターンに基づいて予測を補正

        Args:
            race_id: レースID
            base_predictions: {pit_number: base_score, ...}

        Returns:
            {pit_number: adjusted_score, ...}
        """
        with sqlite3.connect(self.attack_db.db_path) as conn:
            cursor = conn.cursor()

            # レース・エントリー情報を取得
            cursor.execute('''
                SELECT
                    r.venue_code,
                    e.pit_number,
                    e.pit_number as course,
                    e.racer_number
                FROM races r
                JOIN entries e ON r.id = e.race_id
                WHERE r.id = ?
            ''', (race_id,))

            entries = {}
            venue_code = None
            for row in cursor.fetchall():
                venue_code = row[0]
                entries[row[1]] = {
                    'course': row[2],
                    'racer_number': row[3]
                }

        if not venue_code:
            return base_predictions

        # 会場パターンを取得
        venue_pattern = self.attack_db.get_venue_pattern(venue_code)

        adjustments = {}
        for pit, entry in entries.items():
            base_score = base_predictions.get(pit, 0.0)
            adjustment = 0.0

            # 会場でのコース別成績補正
            if venue_pattern and entry['course']:
                course_idx = entry['course'] - 1
                if 0 <= course_idx < len(venue_pattern['course_win_rates']):
                    venue_course_rate = venue_pattern['course_win_rates'][course_idx]
                    # 全国平均との差分を補正
                    avg_rates = [0.55, 0.14, 0.12, 0.10, 0.06, 0.03]
                    diff = venue_course_rate - avg_rates[course_idx]
                    adjustment += diff * 10  # スケール調整

            # 選手の会場相性補正
            vr_pattern = self.attack_db.get_venue_racer_pattern(
                venue_code, entry['racer_number']
            )
            if vr_pattern and vr_pattern['total_races'] >= 10:
                # 平均着順が良ければプラス補正
                rank_bonus = (3.5 - vr_pattern['avg_rank']) * 2
                adjustment += rank_bonus

            adjustments[pit] = base_score + adjustment

        return adjustments


if __name__ == "__main__":
    print("=" * 70)
    print("Attack Patterns Database - Build and Test")
    print("=" * 70)

    db = AttackPatternDB()

    # 全パターンを構築
    db.build_all_patterns()

    # テスト: 会場パターン
    print("\n" + "=" * 70)
    print("Venue Pattern Examples")
    print("=" * 70)

    for venue_code in ['01', '12', '24']:
        pattern = db.get_venue_pattern(venue_code)
        if pattern:
            print(f"\n[{pattern['venue_code']}] {pattern['venue_name']}")
            print(f"  1C Win Rate: {pattern['course_win_rates'][0]*100:.1f}%")
            print(f"  Upset Rate: {pattern['upset_rate']*100:.1f}%")
            print(f"  Nige Rate: {pattern['nige_rate']*100:.1f}%")
            print(f"  Sashi Rate: {pattern['sashi_rate']*100:.1f}%")
            print(f"  High Payout Rate: {pattern['high_payout_rate']*100:.1f}%")

    # テスト: 荒れやすい会場
    print("\n" + "=" * 70)
    print("High Upset Risk Venues")
    print("=" * 70)

    upset_venues = db.get_upset_risk_venues(0.50)
    for venue_code, upset_rate in upset_venues[:5]:
        pattern = db.get_venue_pattern(venue_code)
        if pattern:
            print(f"  [{venue_code}] {pattern['venue_name']}: {upset_rate*100:.1f}% upset rate")

    print("\n" + "=" * 70)
    print("Build Complete!")
    print("=" * 70)
