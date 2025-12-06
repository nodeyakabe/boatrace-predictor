# -*- coding: utf-8 -*-
"""
2着予測用の拡張特徴量 v2

1着が決まった後の2着予測精度を向上させるための特徴量
"""

import sqlite3
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np


@dataclass
class SecondPlaceFeatures:
    """2着予測用の特徴量セット"""
    # 基本特徴量
    pit_number: int
    course: int
    motor_second_rate: float
    racer_rank_score: int  # A1=4, A2=3, B1=2, B2=1

    # 1着艇との相対特徴量
    course_diff_from_winner: int  # 1着艇とのコース差
    is_immediate_outside_winner: bool  # 1着艇のすぐ外か
    is_immediate_inside_winner: bool  # 1着艇のすぐ内か
    motor_diff_from_winner: float  # モーター2連率の差

    # 会場・パターン特徴量
    venue_second_rate_this_course: float  # この会場このコースの2着率
    historical_second_rate_after_winner_course: float  # 1着コースの時のこのコースの2着率

    # 選手特徴量
    racer_second_rate_at_venue: float  # この選手のこの会場での2着率
    racer_second_rate_from_course: float  # このコースからの2着率


class SecondFeaturesGenerator:
    """
    2着予測用特徴量生成器
    """

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path
        self._cache = {}
        self._load_venue_patterns()

    def _load_venue_patterns(self):
        """会場別の2着パターンをキャッシュ"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 会場・1着コース・2着コース別の確率
            cursor.execute('''
                SELECT
                    r.venue_code,
                    e1.pit_number as winner_course,
                    e2.pit_number as second_course,
                    COUNT(*) as count
                FROM results r1
                JOIN results r2 ON r1.race_id = r2.race_id
                JOIN entries e1 ON r1.race_id = e1.race_id AND r1.pit_number = e1.pit_number
                JOIN entries e2 ON r2.race_id = e2.race_id AND r2.pit_number = e2.pit_number
                JOIN races r ON r1.race_id = r.id
                WHERE r1.rank = 1 AND r2.rank = 2
                  AND r1.is_invalid = 0 AND r2.is_invalid = 0
                GROUP BY r.venue_code, e1.pit_number, e2.pit_number
            ''')

            self._venue_second_patterns = {}
            for venue, w_course, s_course, count in cursor.fetchall():
                if venue not in self._venue_second_patterns:
                    self._venue_second_patterns[venue] = {}
                if w_course not in self._venue_second_patterns[venue]:
                    self._venue_second_patterns[venue][w_course] = {}
                self._venue_second_patterns[venue][w_course][s_course] = count

            # 各会場・1着コースでの合計を計算
            self._venue_second_totals = {}
            for venue in self._venue_second_patterns:
                self._venue_second_totals[venue] = {}
                for w_course in self._venue_second_patterns[venue]:
                    self._venue_second_totals[venue][w_course] = sum(
                        self._venue_second_patterns[venue][w_course].values()
                    )

            # 会場・コース別の2着率
            cursor.execute('''
                SELECT
                    r.venue_code,
                    e.pit_number,
                    COUNT(*) as total,
                    SUM(CASE WHEN res.rank = 2 THEN 1 ELSE 0 END) as second_count
                FROM results res
                JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
                JOIN races r ON res.race_id = r.id
                WHERE res.is_invalid = 0
                GROUP BY r.venue_code, e.pit_number
            ''')

            self._venue_course_second_rate = {}
            for venue, course, total, second_count in cursor.fetchall():
                if venue not in self._venue_course_second_rate:
                    self._venue_course_second_rate[venue] = {}
                self._venue_course_second_rate[venue][course] = second_count / total if total > 0 else 0.167

    def get_venue_second_probability(
        self,
        venue_code: str,
        winner_course: int,
        candidate_course: int
    ) -> float:
        """
        特定会場・1着コースでの2着コース確率を取得
        """
        if venue_code not in self._venue_second_patterns:
            return 0.167  # デフォルト: 1/6

        if winner_course not in self._venue_second_patterns[venue_code]:
            return 0.167

        total = self._venue_second_totals[venue_code].get(winner_course, 0)
        if total == 0:
            return 0.167

        count = self._venue_second_patterns[venue_code][winner_course].get(candidate_course, 0)
        return count / total

    def get_venue_course_second_rate(
        self,
        venue_code: str,
        course: int
    ) -> float:
        """
        会場・コース別の2着率を取得
        """
        if venue_code not in self._venue_course_second_rate:
            return 0.167
        return self._venue_course_second_rate[venue_code].get(course, 0.167)

    def generate_features(
        self,
        race_id: int,
        winner_pit: int,
        candidate_pit: int
    ) -> Optional[Dict]:
        """
        2着候補艇の特徴量を生成

        Args:
            race_id: レースID
            winner_pit: 1着艇の艇番
            candidate_pit: 2着候補艇の艇番

        Returns:
            特徴量辞書
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # レース・エントリー情報取得
            cursor.execute('''
                SELECT
                    r.venue_code,
                    e.pit_number,
                    COALESCE(e.pit_number, e.pit_number) as course,
                    COALESCE(e.motor_second_rate, 0.30) as motor_rate,
                    e.racer_rank,
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
                    'motor_rate': row[3],
                    'racer_rank': row[4],
                    'racer_number': row[5]
                }

            if winner_pit not in entries or candidate_pit not in entries:
                return None

            winner = entries[winner_pit]
            candidate = entries[candidate_pit]

            # ランクスコア変換
            rank_score_map = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
            candidate_rank_score = rank_score_map.get(candidate['racer_rank'], 1)

            # 1着艇との相対特徴量
            course_diff = candidate['course'] - winner['course']
            is_immediate_outside = (candidate['course'] == winner['course'] + 1)
            is_immediate_inside = (candidate['course'] == winner['course'] - 1)
            motor_diff = candidate['motor_rate'] - winner['motor_rate']

            # 会場パターン特徴量
            venue_second_prob = self.get_venue_second_probability(
                venue_code, winner['course'], candidate['course']
            )
            venue_course_rate = self.get_venue_course_second_rate(
                venue_code, candidate['course']
            )

            # 選手の2着率（この会場・コース）- キャッシュがあれば使用
            racer_second_rate = self._get_racer_second_rate(
                cursor, candidate['racer_number'], venue_code, candidate['course']
            )

            return {
                'pit_number': candidate_pit,
                'course': candidate['course'],
                'motor_second_rate': candidate['motor_rate'],
                'racer_rank_score': candidate_rank_score,
                'course_diff_from_winner': course_diff,
                'is_immediate_outside_winner': 1 if is_immediate_outside else 0,
                'is_immediate_inside_winner': 1 if is_immediate_inside else 0,
                'motor_diff_from_winner': motor_diff,
                'venue_second_prob_after_winner': venue_second_prob,
                'venue_course_second_rate': venue_course_rate,
                'racer_second_rate_venue_course': racer_second_rate,
                # 組み合わせ特徴量
                'outside_and_good_motor': 1 if (course_diff > 0 and motor_diff > 0.05) else 0,
                'inside_sashi_potential': 1 if (is_immediate_inside and candidate_rank_score >= 3) else 0,
            }

    def _get_racer_second_rate(
        self,
        cursor,
        racer_number: int,
        venue_code: str,
        course: int
    ) -> float:
        """選手のこの会場・コースでの2着率"""
        cache_key = (racer_number, venue_code, course)
        if cache_key in self._cache:
            return self._cache[cache_key]

        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN res.rank = 2 THEN 1 ELSE 0 END) as second_count
            FROM results res
            JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
            JOIN races r ON res.race_id = r.id
            WHERE e.racer_number = ?
              AND r.venue_code = ?
              AND e.pit_number = ?
              AND res.is_invalid = 0
        ''', (racer_number, venue_code, course))

        row = cursor.fetchone()
        if row and row[0] >= 5:  # 5レース以上のデータがある場合
            rate = row[1] / row[0]
        else:
            rate = 0.167  # デフォルト

        self._cache[cache_key] = rate
        return rate

    def generate_all_candidates_features(
        self,
        race_id: int,
        winner_pit: int
    ) -> List[Dict]:
        """
        1着艇以外の全艇の2着候補特徴量を生成
        """
        features_list = []
        for pit in range(1, 7):
            if pit == winner_pit:
                continue
            features = self.generate_features(race_id, winner_pit, pit)
            if features:
                features_list.append(features)

        return features_list

    def rank_second_candidates(
        self,
        race_id: int,
        winner_pit: int,
        prediction_scores: Dict[int, float] = None
    ) -> List[Tuple[int, float]]:
        """
        2着候補をランキング

        Args:
            race_id: レースID
            winner_pit: 1着艇の艇番
            prediction_scores: 既存の予測スコア（オプション）

        Returns:
            [(艇番, スコア), ...] の降順リスト
        """
        candidates = self.generate_all_candidates_features(race_id, winner_pit)

        scored = []
        for c in candidates:
            # 複合スコアを計算
            score = 0.0

            # 会場パターンからの確率
            score += c['venue_second_prob_after_winner'] * 30

            # コース別の2着率
            score += c['venue_course_second_rate'] * 20

            # モーター差（1着より良いモーターなら有利）
            if c['motor_diff_from_winner'] > 0:
                score += min(c['motor_diff_from_winner'] * 50, 10)

            # すぐ外にいる場合（差しやすい）
            if c['is_immediate_outside_winner']:
                score += 8

            # すぐ内にいる場合（差されやすい位置）
            if c['is_immediate_inside_winner']:
                score += 5

            # 選手ランク
            score += c['racer_rank_score'] * 3

            # 既存の予測スコアがあれば加味
            if prediction_scores and c['pit_number'] in prediction_scores:
                score += prediction_scores[c['pit_number']] * 0.5

            scored.append((c['pit_number'], score))

        # スコア降順でソート
        scored.sort(key=lambda x: -x[1])
        return scored


if __name__ == "__main__":
    print("=" * 70)
    print("2着予測特徴量 v2 テスト")
    print("=" * 70)

    generator = SecondFeaturesGenerator()

    # サンプルレースでテスト
    import sqlite3
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT r.id, res.pit_number as winner_pit
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE r.race_date LIKE '2025-11%' AND res.rank = 1
        LIMIT 5
    ''')

    for race_id, winner_pit in cursor.fetchall():
        print(f"\nRace {race_id}, Winner: Pit {winner_pit}")
        print("-" * 50)

        candidates = generator.rank_second_candidates(race_id, winner_pit)
        print("2着候補ランキング:")
        for i, (pit, score) in enumerate(candidates, 1):
            print(f"  {i}. Pit {pit}: Score {score:.2f}")

        # 実際の2着を確認
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND rank = 2
        ''', (race_id,))
        actual = cursor.fetchone()
        if actual:
            print(f"  -> Actual 2nd: Pit {actual[0]}")

    conn.close()
