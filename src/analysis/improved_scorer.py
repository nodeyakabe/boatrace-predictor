# -*- coding: utf-8 -*-
"""
改善版スコアリングモジュール
2024年11月27日

バックテスト結果: 58.75% → 59.71% (+0.96%)

改善内容:
1. 会場別1コース勝率の除外（venue_in1を使わない）
2. モーター配点を20→14に軽減
3. 展示ST順位スコア追加（当日ST順位）
4. 展示タイム順位スコア追加
5. コース配点を35→20に軽減
"""

import sqlite3
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH, SCORING_WEIGHTS


class ImprovedScorer:
    """改善版スコアリング"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DATABASE_PATH
        self.weights = SCORING_WEIGHTS.copy()

    def calculate_total_score(
        self,
        entry: Dict,
        race_entries: List[Dict],
        race_id: int = None
    ) -> Dict:
        """
        改善版総合スコアを計算

        Args:
            entry: エントリー情報
            race_entries: レース全体のエントリーリスト
            race_id: レースID（展示データ取得用）

        Returns:
            {
                'total_score': float,
                'course_score': float,
                'racer_score': float,
                'motor_score': float,
                'rank_score': float,
                'exhibition_st_score': float,
                'exhibition_time_score': float,
                'details': dict
            }
        """
        pit = entry['pit_number']

        # 1. コーススコア（20%）
        course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
        course_score = course_base.get(pit, 10) / 55 * 100
        course_score = course_score * self.weights.get('course', 20) / 100

        # 2. 選手スコア（31%）
        win_rate = entry.get('win_rate') or 0
        local_win_rate = entry.get('local_win_rate') or 0
        racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
        racer_score = racer_score * self.weights.get('racer', 31) / 100

        # 3. モータースコア（14%）
        motor_rate = entry.get('motor_second_rate') or 30
        motor_score = motor_rate * self.weights.get('motor', 14) / 100

        # 4. 級別スコア（10%）
        rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
        rank = entry.get('racer_rank') or 'B1'
        rank_score = rank_scores.get(rank, 40)
        rank_score = rank_score * self.weights.get('rank', 10) / 100

        # 5. 展示ST順位スコア（15%）
        exhibition_st_score = self._calculate_exhibition_st_rank_score(
            entry, race_entries, self.weights.get('exhibition_st', 15)
        )

        # 6. 展示タイム順位スコア（10%）
        exhibition_time_score = self._calculate_exhibition_time_rank_score(
            entry, race_entries, self.weights.get('exhibition_time', 10)
        )

        # 総合スコア
        total_score = (
            course_score +
            racer_score +
            motor_score +
            rank_score +
            exhibition_st_score +
            exhibition_time_score
        )

        return {
            'total_score': round(total_score, 2),
            'course_score': round(course_score, 2),
            'racer_score': round(racer_score, 2),
            'motor_score': round(motor_score, 2),
            'rank_score': round(rank_score, 2),
            'exhibition_st_score': round(exhibition_st_score, 2),
            'exhibition_time_score': round(exhibition_time_score, 2),
            'details': {
                'pit_number': pit,
                'win_rate': win_rate,
                'local_win_rate': local_win_rate,
                'motor_second_rate': motor_rate,
                'racer_rank': rank,
            }
        }

    def _calculate_exhibition_st_rank_score(
        self,
        entry: Dict,
        race_entries: List[Dict],
        max_score: float
    ) -> float:
        """
        展示ST（当日ST）の順位スコアを計算

        ST順位別勝率（実データ）:
        - 1位: 33.23%
        - 2位: 19.72%
        - 3位: 14.42%
        - 4位: 11.22%
        - 5位: 8.91%
        - 6位: 5.44%
        """
        exhibition_st = entry.get('exhibition_st')
        pit = entry['pit_number']

        if not exhibition_st or exhibition_st <= 0:
            return max_score * 0.5  # データなしは中間値

        # 有効な展示STを収集
        valid_sts = []
        for e in race_entries:
            st = e.get('exhibition_st')
            if st and st > 0:
                valid_sts.append((e['pit_number'], st))

        if not valid_sts:
            return max_score * 0.5

        # ST順でソート（早い順）
        sorted_sts = sorted(valid_sts, key=lambda x: x[1])

        # 順位を特定
        for rank, (p, st) in enumerate(sorted_sts, 1):
            if p == pit:
                # 順位スコア: 1位=100%, 6位≈0%
                rank_factor = (len(sorted_sts) + 1 - rank) / len(sorted_sts)
                return max_score * rank_factor

        return max_score * 0.5

    def _calculate_exhibition_time_rank_score(
        self,
        entry: Dict,
        race_entries: List[Dict],
        max_score: float
    ) -> float:
        """
        展示タイムの順位スコアを計算

        展示タイム順位別勝率（実データ）:
        - 1位: 27.30%
        - 2位: 20.48%
        - 3位: 16.42%
        - 4位: 13.58%
        - 5位: 11.03%
        - 6位: 8.64%
        """
        exhibition_time = entry.get('exhibition_time')
        pit = entry['pit_number']

        if not exhibition_time or exhibition_time <= 0:
            return max_score * 0.5  # データなしは中間値

        # 有効な展示タイムを収集
        valid_times = []
        for e in race_entries:
            t = e.get('exhibition_time')
            if t and t > 0:
                valid_times.append((e['pit_number'], t))

        if not valid_times:
            return max_score * 0.5

        # タイム順でソート（早い順）
        sorted_times = sorted(valid_times, key=lambda x: x[1])

        # 順位を特定
        for rank, (p, t) in enumerate(sorted_times, 1):
            if p == pit:
                # 順位スコア: 1位=100%, 6位≈0%
                rank_factor = (len(sorted_times) + 1 - rank) / len(sorted_times)
                return max_score * rank_factor

        return max_score * 0.5


def get_race_entries_with_exhibition(race_id: int, db_path: str = None) -> List[Dict]:
    """
    レースのエントリー情報を展示データ込みで取得

    Args:
        race_id: レースID
        db_path: データベースパス

    Returns:
        エントリーリスト（展示ST、展示タイム含む）
    """
    db_path = db_path or DATABASE_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            e.pit_number,
            e.racer_number,
            e.racer_name,
            e.racer_rank,
            e.win_rate,
            e.local_win_rate,
            e.motor_second_rate,
            e.avg_st,
            e.f_count,
            e.l_count,
            rd.exhibition_time,
            rd.st_time as exhibition_st
        FROM entries e
        LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
        WHERE e.race_id = ?
        ORDER BY e.pit_number
    """, (race_id,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def predict_race_improved(race_id: int, db_path: str = None) -> List[Dict]:
    """
    改善版スコアリングでレース予測を実行

    Args:
        race_id: レースID
        db_path: データベースパス

    Returns:
        予測結果リスト（スコア順）
    """
    entries = get_race_entries_with_exhibition(race_id, db_path)

    if len(entries) < 6:
        return []

    scorer = ImprovedScorer(db_path)

    predictions = []
    for entry in entries:
        result = scorer.calculate_total_score(entry, entries, race_id)
        result['pit_number'] = entry['pit_number']
        result['racer_name'] = entry.get('racer_name', '')
        result['racer_number'] = entry.get('racer_number', '')
        predictions.append(result)

    # スコア順にソート
    predictions.sort(key=lambda x: -x['total_score'])

    # 順位を付与
    for rank, pred in enumerate(predictions, 1):
        pred['rank_prediction'] = rank

    return predictions


if __name__ == '__main__':
    # テスト
    print('改善版スコアリング テスト')
    print('=' * 50)

    # 最新レースを取得してテスト
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE race_date >= '2024-11-01'
        ORDER BY race_date DESC, race_number DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()

    if row:
        race_id, race_date, venue_code, race_number = row
        print(f"テストレース: {race_date} {venue_code}場 {race_number}R")
        print()

        predictions = predict_race_improved(race_id)

        print(f"{'順位':<4} {'枠':<4} {'選手名':<10} {'総合':>8} {'コース':>8} {'選手':>8} {'モーター':>8} {'展示ST':>8} {'展示T':>8}")
        print('-' * 80)

        for pred in predictions:
            print(f"{pred['rank_prediction']:<4} "
                  f"{pred['pit_number']:<4} "
                  f"{pred['racer_name']:<10} "
                  f"{pred['total_score']:>7.2f} "
                  f"{pred['course_score']:>7.2f} "
                  f"{pred['racer_score']:>7.2f} "
                  f"{pred['motor_score']:>7.2f} "
                  f"{pred['exhibition_st_score']:>7.2f} "
                  f"{pred['exhibition_time_score']:>7.2f}")
    else:
        print('テストデータなし')
