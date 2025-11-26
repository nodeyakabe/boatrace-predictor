"""
拡張スコアリングモジュール

追加の予測要素を実装:
1. 選手級別スコア（A1/A2/B1/B2）
2. F/L持ちペナルティ
3. 節間成績分析
4. 前走レベル評価
5. 進入コース予測
6. 選手間相性分析
7. モーター特性分析
"""
import sqlite3
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


class ExtendedScorer:
    """拡張スコアリング"""

    # 級別基準スコア（max_score=10として）
    CLASS_SCORES = {
        'A1': 10.0,  # トップ選手
        'A2': 7.0,   # 上位選手
        'B1': 4.0,   # 中堅選手
        'B2': 1.0,   # 新人・下位選手
    }

    # F/Lペナルティ（1回あたり）
    FL_PENALTIES = {
        'F': -3.0,  # フライング1回で-3点
        'L': -1.5,  # 出遅れ1回で-1.5点
    }

    # 進入コース予測用：枠番別の進入傾向（デフォルト）
    DEFAULT_COURSE_TENDENCY = {
        1: {1: 0.98, 2: 0.02},  # 1号艇は98%で1コース
        2: {1: 0.01, 2: 0.95, 3: 0.04},
        3: {2: 0.02, 3: 0.93, 4: 0.05},
        4: {3: 0.03, 4: 0.90, 5: 0.07},
        5: {4: 0.05, 5: 0.85, 6: 0.10},
        6: {5: 0.08, 6: 0.92},
    }

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DATABASE_PATH

    def calculate_class_score(self, racer_rank: str, max_score: float = 10.0) -> Dict:
        """
        選手級別スコアを計算

        Args:
            racer_rank: 級別（A1, A2, B1, B2）
            max_score: 最大スコア

        Returns:
            {'score': float, 'rank': str, 'description': str}
        """
        if not racer_rank:
            return {
                'score': max_score * 0.4,  # 不明時は中間値
                'rank': 'unknown',
                'description': '級別不明'
            }

        base_score = self.CLASS_SCORES.get(racer_rank.upper(), 4.0)
        # 10点満点を max_score に正規化
        score = base_score * (max_score / 10.0)

        descriptions = {
            'A1': 'トップ選手',
            'A2': '上位選手',
            'B1': '中堅選手',
            'B2': '新人・下位選手'
        }

        return {
            'score': score,
            'rank': racer_rank,
            'description': descriptions.get(racer_rank.upper(), '不明')
        }

    def calculate_fl_penalty(self, f_count: int, l_count: int, max_penalty: float = -10.0) -> Dict:
        """
        F/L持ちペナルティを計算

        F持ち選手は慎重なスタートになり、特に1コースで不利

        Args:
            f_count: フライング回数
            l_count: 出遅れ回数
            max_penalty: 最大ペナルティ（負の値）

        Returns:
            {'penalty': float, 'f_count': int, 'l_count': int, 'risk_level': str}
        """
        f_count = f_count or 0
        l_count = l_count or 0

        # ペナルティ計算
        f_penalty = f_count * self.FL_PENALTIES['F']
        l_penalty = l_count * self.FL_PENALTIES['L']
        total_penalty = max(f_penalty + l_penalty, max_penalty)  # max_penaltyで下限

        # リスクレベル判定
        if f_count >= 2:
            risk_level = 'critical'  # 即帰郷の危険
        elif f_count == 1:
            risk_level = 'high'  # 慎重スタート必須
        elif l_count >= 2:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        return {
            'penalty': total_penalty,
            'f_count': f_count,
            'l_count': l_count,
            'risk_level': risk_level,
            'description': f'F{f_count}L{l_count}' if (f_count + l_count) > 0 else 'クリーン'
        }

    def calculate_session_performance(
        self,
        racer_number: str,
        venue_code: str,
        target_date: str,
        max_score: float = 5.0
    ) -> Dict:
        """
        節間成績スコアを計算

        同一会場での直近成績（同じ開催期間内）を評価

        Args:
            racer_number: 選手番号
            venue_code: 会場コード
            target_date: 対象日付（YYYY-MM-DD）
            max_score: 最大スコア

        Returns:
            {'score': float, 'races': int, 'avg_rank': float, 'trend': str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 同一会場で直近7日以内（≒同一開催）のレース
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
            ''', (racer_number, venue_code, target_date, target_date))

            results = cursor.fetchall()

            if not results:
                return {
                    'score': max_score * 0.5,  # データなしは中間
                    'races': 0,
                    'avg_rank': None,
                    'trend': 'unknown',
                    'description': '節間データなし'
                }

            # 着順を数値化
            ranks = []
            for row in results:
                try:
                    rank = int(row[0])
                    if 1 <= rank <= 6:
                        ranks.append(rank)
                except (ValueError, TypeError):
                    pass

            if not ranks:
                return {
                    'score': max_score * 0.5,
                    'races': len(results),
                    'avg_rank': None,
                    'trend': 'unknown',
                    'description': '有効データなし'
                }

            avg_rank = sum(ranks) / len(ranks)

            # スコア計算（平均着順が低いほど高スコア）
            # 1着=max_score, 6着=0
            score = max(0, (6 - avg_rank) / 5 * max_score)

            # トレンド判定（前半vs後半）
            if len(ranks) >= 4:
                first_half = sum(ranks[:len(ranks)//2]) / (len(ranks)//2)
                second_half = sum(ranks[len(ranks)//2:]) / (len(ranks) - len(ranks)//2)
                if second_half < first_half - 0.5:
                    trend = 'improving'
                elif second_half > first_half + 0.5:
                    trend = 'declining'
                else:
                    trend = 'stable'
            else:
                trend = 'insufficient'

            return {
                'score': score,
                'races': len(ranks),
                'avg_rank': round(avg_rank, 2),
                'trend': trend,
                'description': f'節間{len(ranks)}走 平均{avg_rank:.1f}着'
            }

        finally:
            conn.close()

    def calculate_previous_race_level(
        self,
        racer_number: str,
        target_date: str,
        max_score: float = 5.0
    ) -> Dict:
        """
        前走レベル評価

        直前のレースがSG/G1だったか、一般戦だったかで調子を推定

        Args:
            racer_number: 選手番号
            target_date: 対象日付
            max_score: 最大スコア

        Returns:
            {'score': float, 'prev_grade': str, 'prev_result': int, 'description': str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 直近のレース（対象日より前）
            cursor.execute('''
                SELECT r.race_grade, res.rank, r.race_date
                FROM entries e
                JOIN races r ON e.race_id = r.id
                LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
                WHERE e.racer_number = ?
                  AND r.race_date < ?
                ORDER BY r.race_date DESC, r.race_number DESC
                LIMIT 1
            ''', (racer_number, target_date))

            row = cursor.fetchone()

            if not row:
                return {
                    'score': max_score * 0.5,
                    'prev_grade': None,
                    'prev_result': None,
                    'description': '前走データなし'
                }

            prev_grade, prev_rank, prev_date = row

            # グレード評価
            grade_scores = {
                'SG': 1.0,
                'G1': 0.9,
                'G2': 0.8,
                'G3': 0.7,
                '一般': 0.5,
                'ルーキーシリーズ': 0.4,
            }
            grade_factor = grade_scores.get(prev_grade, 0.5)

            # 前走結果評価
            try:
                rank = int(prev_rank)
                if rank == 1:
                    result_factor = 1.0
                elif rank == 2:
                    result_factor = 0.8
                elif rank <= 3:
                    result_factor = 0.6
                else:
                    result_factor = 0.4
            except (ValueError, TypeError):
                result_factor = 0.3  # F/L等

            # 複合スコア
            score = max_score * (grade_factor * 0.4 + result_factor * 0.6)

            return {
                'score': score,
                'prev_grade': prev_grade,
                'prev_result': prev_rank,
                'description': f'前走{prev_grade or "不明"} {prev_rank or "-"}着'
            }

        finally:
            conn.close()

    def predict_course_entry(
        self,
        pit_number: int,
        racer_number: str,
        venue_code: str
    ) -> Dict:
        """
        進入コース予測

        過去の進入傾向から実際のコースを予測

        Args:
            pit_number: 枠番（1-6）
            racer_number: 選手番号
            venue_code: 会場コード

        Returns:
            {'predicted_course': int, 'confidence': float, 'probabilities': dict}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # その選手のコース取り傾向を確認（resultsにactual_courseがあれば）
            # 現状はデフォルトの傾向を使用
            probabilities = self.DEFAULT_COURSE_TENDENCY.get(pit_number, {pit_number: 1.0})

            # 最も確率が高いコースを予測
            predicted_course = max(probabilities, key=probabilities.get)
            confidence = probabilities[predicted_course]

            return {
                'predicted_course': predicted_course,
                'confidence': confidence,
                'probabilities': probabilities,
                'description': f'{pit_number}号艇→{predicted_course}コース予測（{confidence*100:.0f}%）'
            }

        finally:
            conn.close()

    def analyze_racer_matchup(
        self,
        race_entries: List[Dict],
        max_score: float = 5.0
    ) -> Dict[int, Dict]:
        """
        選手間相性・力関係分析

        同じレースに出走する選手同士の相対的な力関係を評価

        Args:
            race_entries: [{'pit_number': int, 'racer_number': str, 'racer_rank': str, 'win_rate': float}, ...]
            max_score: 最大スコア

        Returns:
            {pit_number: {'relative_score': float, 'rank_in_race': int, ...}}
        """
        if not race_entries:
            return {}

        # 勝率でランキング
        sorted_entries = sorted(
            race_entries,
            key=lambda x: (
                self.CLASS_SCORES.get(x.get('racer_rank', 'B1'), 4),
                x.get('win_rate', 0) or 0
            ),
            reverse=True
        )

        results = {}
        for rank, entry in enumerate(sorted_entries, 1):
            pit = entry.get('pit_number')

            # 相対スコア：1位に対する相対評価
            top_win_rate = sorted_entries[0].get('win_rate', 0) or 1
            current_win_rate = entry.get('win_rate', 0) or 0
            relative_factor = current_win_rate / top_win_rate if top_win_rate > 0 else 0.5

            score = max_score * relative_factor

            # 級別差
            top_class = sorted_entries[0].get('racer_rank', 'B1')
            current_class = entry.get('racer_rank', 'B1')
            class_diff = self.CLASS_SCORES.get(current_class, 4) - self.CLASS_SCORES.get(top_class, 4)

            results[pit] = {
                'relative_score': score,
                'rank_in_race': rank,
                'class_diff': class_diff,
                'description': f'レース内{rank}位' + (f'（{current_class}）' if current_class else '')
            }

        return results

    def analyze_motor_characteristics(
        self,
        motor_number: int,
        venue_code: str,
        max_score: float = 5.0
    ) -> Dict:
        """
        モーター特性分析

        モーターの詳細特性（加速/最高速/安定性）を分析

        Args:
            motor_number: モーター番号
            venue_code: 会場コード
            max_score: 最大スコア

        Returns:
            {'score': float, 'characteristics': dict, 'description': str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # モーターの成績を取得
            cursor.execute('''
                SELECT
                    e.motor_number,
                    AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as win_rate,
                    AVG(CASE WHEN res.rank IN ('1', '2') THEN 1.0 ELSE 0.0 END) as second_rate,
                    COUNT(*) as races
                FROM entries e
                JOIN races r ON e.race_id = r.id
                LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
                WHERE e.motor_number = ?
                  AND r.venue_code = ?
                  AND res.rank IS NOT NULL
                GROUP BY e.motor_number
            ''', (motor_number, venue_code))

            row = cursor.fetchone()

            if not row or row[3] < 5:  # 5レース未満はデータ不足
                return {
                    'score': max_score * 0.5,
                    'characteristics': {},
                    'races': row[3] if row else 0,
                    'description': 'モーターデータ不足'
                }

            win_rate = row[1] or 0
            second_rate = row[2] or 0
            races = row[3]

            # スコア計算（勝率ベース）
            score = min(max_score, max_score * (win_rate / 0.20))  # 20%を最高評価

            # 特性判定（簡易版）
            characteristics = {
                'power': 'high' if win_rate > 0.15 else 'medium' if win_rate > 0.08 else 'low',
                'stability': 'high' if second_rate > 0.30 else 'medium' if second_rate > 0.20 else 'low'
            }

            return {
                'score': score,
                'characteristics': characteristics,
                'win_rate': round(win_rate * 100, 1),
                'second_rate': round(second_rate * 100, 1),
                'races': races,
                'description': f'勝率{win_rate*100:.1f}% ({races}走)'
            }

        finally:
            conn.close()

    def get_comprehensive_score(
        self,
        entry: Dict,
        venue_code: str,
        target_date: str,
        race_entries: List[Dict] = None
    ) -> Dict:
        """
        総合拡張スコアを計算

        Args:
            entry: {'pit_number', 'racer_number', 'racer_rank', 'f_count', 'l_count', 'motor_number', ...}
            venue_code: 会場コード
            target_date: 対象日付
            race_entries: 同レースの全出走者リスト

        Returns:
            総合スコアと各要素の詳細
        """
        # 1. 級別スコア
        class_result = self.calculate_class_score(
            entry.get('racer_rank'),
            max_score=10.0
        )

        # 2. F/Lペナルティ
        fl_result = self.calculate_fl_penalty(
            entry.get('f_count', 0),
            entry.get('l_count', 0)
        )

        # 3. 節間成績
        session_result = self.calculate_session_performance(
            entry.get('racer_number'),
            venue_code,
            target_date,
            max_score=5.0
        )

        # 4. 前走レベル
        prev_race_result = self.calculate_previous_race_level(
            entry.get('racer_number'),
            target_date,
            max_score=5.0
        )

        # 5. 進入コース予測
        course_result = self.predict_course_entry(
            entry.get('pit_number'),
            entry.get('racer_number'),
            venue_code
        )

        # 6. 選手間相性（race_entriesがあれば）
        matchup_result = {}
        if race_entries:
            all_matchups = self.analyze_racer_matchup(race_entries, max_score=5.0)
            matchup_result = all_matchups.get(entry.get('pit_number'), {})

        # 7. モーター特性
        motor_result = self.analyze_motor_characteristics(
            entry.get('motor_number'),
            venue_code,
            max_score=5.0
        )

        # 総合スコア
        total_score = (
            class_result['score'] +
            fl_result['penalty'] +
            session_result['score'] +
            prev_race_result['score'] +
            matchup_result.get('relative_score', 2.5) +
            motor_result['score']
        )

        return {
            'total_extended_score': total_score,
            'class': class_result,
            'fl_penalty': fl_result,
            'session': session_result,
            'prev_race': prev_race_result,
            'course_prediction': course_result,
            'matchup': matchup_result,
            'motor': motor_result
        }
