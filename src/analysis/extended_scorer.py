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

from config.settings import DATABASE_PATH, EXTENDED_SCORE_WEIGHTS


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

    # 平均STスコア基準（勝率との相関に基づく）
    # ST 0.10-0.15が最も勝率高い（24.38%）、0.20以上は低い（9.64%）
    ST_SCORE_RANGES = [
        (0.00, 0.10, 0.7),   # 早すぎ（Fリスク）
        (0.10, 0.15, 1.0),   # 最適（最高勝率）
        (0.15, 0.18, 0.8),   # 良好
        (0.18, 0.20, 0.6),   # やや遅い
        (0.20, 1.00, 0.4),   # 遅い
    ]

    # 進入コース予測用：枠番別の進入傾向（デフォルト）
    DEFAULT_COURSE_TENDENCY = {
        1: {1: 0.98, 2: 0.02},  # 1号艇は98%で1コース
        2: {1: 0.01, 2: 0.95, 3: 0.04},
        3: {2: 0.02, 3: 0.93, 4: 0.05},
        4: {3: 0.03, 4: 0.90, 5: 0.07},
        5: {4: 0.05, 5: 0.85, 6: 0.10},
        6: {5: 0.08, 6: 0.92},
    }

    def __init__(self, db_path: str = None, batch_loader=None):
        self.db_path = db_path or DATABASE_PATH
        self.batch_loader = batch_loader

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

    def calculate_start_timing_score(
        self,
        avg_st: float,
        pit_number: int,
        max_score: float = 8.0
    ) -> Dict:
        """
        平均STスコアを計算

        スタートタイミングは勝率に強く影響する。
        0.10-0.15秒が最も勝率が高く（24.38%）、
        0.20秒以上は低い（9.64%）。

        Args:
            avg_st: 平均スタートタイミング（秒）
            pit_number: 枠番（1コースはST影響大）
            max_score: 最大スコア

        Returns:
            {'score': float, 'avg_st': float, 'category': str, 'description': str}
        """
        if avg_st is None or avg_st <= 0:
            return {
                'score': max_score * 0.5,  # データなしは中間
                'avg_st': None,
                'category': 'unknown',
                'description': 'STデータなし'
            }

        # ST範囲に基づくスコア係数を取得
        score_factor = 0.5  # デフォルト
        category = 'average'
        for st_min, st_max, factor in self.ST_SCORE_RANGES:
            if st_min <= avg_st < st_max:
                score_factor = factor
                if factor >= 1.0:
                    category = 'excellent'
                elif factor >= 0.8:
                    category = 'good'
                elif factor >= 0.6:
                    category = 'average'
                else:
                    category = 'slow'
                break

        # 1コースはSTが特に重要（係数1.2倍）
        if pit_number == 1:
            score_factor = min(1.0, score_factor * 1.2)

        score = max_score * score_factor

        # 説明文生成
        if avg_st < 0.10:
            desc = f'ST{avg_st:.2f}秒（Fリスク）'
        elif avg_st < 0.15:
            desc = f'ST{avg_st:.2f}秒（絶好）'
        elif avg_st < 0.18:
            desc = f'ST{avg_st:.2f}秒（良好）'
        elif avg_st < 0.20:
            desc = f'ST{avg_st:.2f}秒（やや遅）'
        else:
            desc = f'ST{avg_st:.2f}秒（遅い）'

        return {
            'score': score,
            'avg_st': avg_st,
            'category': category,
            'description': desc
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

    def calculate_course_entry_tendency(
        self,
        racer_number: str,
        pit_number: int,
        max_score: float = 5.0
    ) -> Dict:
        """
        選手の進入コース傾向（前付け傾向）を分析

        外枠から内コースへ進入する傾向がある選手を特定し、
        進入予測の信頼度と補正スコアを計算する。

        Args:
            racer_number: 選手番号
            pit_number: 枠番（1-6）
            max_score: 最大スコア

        Returns:
            {
                'front_entry_rate': float,  # 前付け率（0-100%）
                'predicted_course': int,    # 予測コース
                'confidence': float,        # 進入予測の信頼度（0-1）
                'score': float,             # スコア（有利不利の補正）
                'description': str
            }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 選手の過去の進入傾向を集計
            cursor.execute('''
                SELECT
                    e.pit_number,
                    rd.actual_course,
                    COUNT(*) as cnt
                FROM entries e
                JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                WHERE e.racer_number = ?
                  AND rd.actual_course IS NOT NULL
                GROUP BY e.pit_number, rd.actual_course
            ''', (racer_number,))

            rows = cursor.fetchall()

            if not rows:
                # データがない場合はデフォルト（枠番=コース）
                return {
                    'front_entry_rate': 0.0,
                    'predicted_course': pit_number,
                    'confidence': 0.8,  # データなしでも枠番=コースは高確率
                    'score': max_score * 0.5,
                    'is_front_entry_prone': False,
                    'description': '進入データなし（枠番進入を予測）'
                }

            # 枠番ごとの進入コース分布を構築
            course_counts = {}  # {pit: {course: count}}
            for pit, course, cnt in rows:
                if pit not in course_counts:
                    course_counts[pit] = {}
                course_counts[pit][course] = cnt

            # 該当枠番での傾向を分析
            if pit_number in course_counts:
                pit_distribution = course_counts[pit_number]
                total = sum(pit_distribution.values())

                # 最も多いコースを予測
                predicted_course = max(pit_distribution, key=pit_distribution.get)
                predicted_prob = pit_distribution[predicted_course] / total

                # 前付け（内コースへ移動）の割合
                front_entry_count = sum(
                    cnt for c, cnt in pit_distribution.items() if c < pit_number
                )
                front_entry_rate = (front_entry_count / total) * 100

            else:
                # 該当枠番のデータがない場合は全体傾向から推定
                total_front = sum(
                    cnt for pit, dist in course_counts.items()
                    for c, cnt in dist.items() if c < pit
                )
                total_all = sum(
                    cnt for dist in course_counts.values()
                    for cnt in dist.values()
                )
                front_entry_rate = (total_front / total_all * 100) if total_all > 0 else 0
                predicted_course = pit_number
                predicted_prob = 0.7  # デフォルト信頼度

            # 信頼度計算
            # - 枠番=コースの確率が高いほど高信頼
            # - 前付け傾向が強い選手は信頼度低下
            confidence = predicted_prob
            if front_entry_rate > 50:
                confidence *= 0.7  # 前付け常習者は進入予測が難しい
            elif front_entry_rate > 30:
                confidence *= 0.85

            # スコア計算
            # - 前付けで内コースを取れると有利
            # - ただし進入予測の不安定さはペナルティ
            score = max_score * 0.5  # 基準点

            if predicted_course < pit_number:
                # 内コースを取る予測 → 有利
                course_advantage = (pit_number - predicted_course) * 0.1
                score += max_score * course_advantage
            elif predicted_course > pit_number:
                # 外コースに流れる予測 → 不利
                course_disadvantage = (predicted_course - pit_number) * 0.1
                score -= max_score * course_disadvantage

            # 不安定さペナルティ
            if confidence < 0.6:
                score *= 0.8

            score = max(0, min(max_score, score))

            # 前付け常習者フラグ
            is_front_entry_prone = front_entry_rate > 40

            # 説明文
            if front_entry_rate > 50:
                desc = f'前付け常習（{front_entry_rate:.0f}%）→{predicted_course}コース予測'
            elif front_entry_rate > 20:
                desc = f'前付け傾向あり（{front_entry_rate:.0f}%）'
            else:
                desc = f'{pit_number}号艇→{predicted_course}コース予測（{confidence*100:.0f}%）'

            return {
                'front_entry_rate': round(front_entry_rate, 1),
                'predicted_course': predicted_course,
                'confidence': round(confidence, 2),
                'score': round(score, 2),
                'is_front_entry_prone': is_front_entry_prone,
                'description': desc
            }

        finally:
            conn.close()

    def calculate_exhibition_time_score(
        self,
        race_id: int,
        pit_number: int,
        max_score: float = 8.0
    ) -> Dict:
        """
        展示タイムに基づくスコアを計算

        展示タイムはレース当日のモーター調子を反映する重要な指標。
        他艇との相対比較でスコアを算出。

        Args:
            race_id: レースID
            pit_number: 枠番
            max_score: 最大スコア

        Returns:
            {'score': float, 'exhibition_time': float, 'rank': int, 'description': str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 該当レースの全艇の展示タイムを取得
            cursor.execute('''
                SELECT pit_number, exhibition_time
                FROM race_details
                WHERE race_id = ? AND exhibition_time IS NOT NULL
                ORDER BY exhibition_time ASC
            ''', (race_id,))

            rows = cursor.fetchall()

            if not rows:
                return {
                    'score': max_score * 0.5,
                    'exhibition_time': None,
                    'rank': None,
                    'description': '展示タイムデータなし'
                }

            # 順位を付与
            times = [(pit, time) for pit, time in rows]
            target_time = None
            target_rank = None

            for rank, (pit, time) in enumerate(times, 1):
                if pit == pit_number:
                    target_time = time
                    target_rank = rank
                    break

            if target_time is None:
                return {
                    'score': max_score * 0.5,
                    'exhibition_time': None,
                    'rank': None,
                    'description': '展示タイムデータなし'
                }

            # スコア計算（1位が最高、6位が最低）
            # 線形補間: 1位=max_score, 6位=0
            total_boats = len(times)
            if total_boats > 1:
                score = max_score * (total_boats - target_rank) / (total_boats - 1)
            else:
                score = max_score * 0.5

            # 説明文
            if target_rank == 1:
                desc = f'展示タイム{target_time:.2f}秒（1位/トップ）'
            elif target_rank <= 2:
                desc = f'展示タイム{target_time:.2f}秒（{target_rank}位/好調）'
            elif target_rank <= 4:
                desc = f'展示タイム{target_time:.2f}秒（{target_rank}位/普通）'
            else:
                desc = f'展示タイム{target_time:.2f}秒（{target_rank}位/不調）'

            return {
                'score': round(score, 2),
                'exhibition_time': target_time,
                'rank': target_rank,
                'description': desc
            }

        finally:
            conn.close()

    def calculate_tilt_angle_score(
        self,
        race_id: int,
        pit_number: int,
        racer_number: str,
        max_score: float = 3.0
    ) -> Dict:
        """
        チルト角度に基づくスコアを計算

        チルト角度は選手のセッティング傾向を示す。
        - マイナス（跳ね）: 出足重視、まくり向き
        - プラス（伏せ）: 伸び重視、逃げ・差し向き
        コース特性との相性を評価。

        Args:
            race_id: レースID
            pit_number: 枠番
            racer_number: 選手番号
            max_score: 最大スコア

        Returns:
            {'score': float, 'tilt_angle': float, 'setting_type': str, 'description': str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 該当レースのチルト角度を取得
            cursor.execute('''
                SELECT tilt_angle
                FROM race_details
                WHERE race_id = ? AND pit_number = ?
            ''', (race_id, pit_number))

            row = cursor.fetchone()

            if not row or row[0] is None:
                return {
                    'score': max_score * 0.5,
                    'tilt_angle': None,
                    'setting_type': 'unknown',
                    'description': 'チルトデータなし'
                }

            tilt = row[0]

            # セッティングタイプを判定
            if tilt <= -0.5:
                setting_type = 'dash'  # 出足重視
                type_desc = '出足重視'
            elif tilt >= 0.5:
                setting_type = 'stretch'  # 伸び重視
                type_desc = '伸び重視'
            else:
                setting_type = 'balanced'  # バランス
                type_desc = 'バランス'

            # コースとの相性スコア
            score = max_score * 0.5  # 基準点

            if pit_number == 1:
                # 1コース: 伸び重視（逃げ）が有利
                if setting_type == 'stretch':
                    score = max_score * 0.8
                elif setting_type == 'balanced':
                    score = max_score * 0.6
                else:
                    score = max_score * 0.4  # 出足重視は1コース逃げには不向き
            elif pit_number in [2, 3]:
                # 2-3コース: 差しにはバランスか伸び
                if setting_type in ['balanced', 'stretch']:
                    score = max_score * 0.7
                else:
                    score = max_score * 0.5
            elif pit_number in [4, 5, 6]:
                # 4-6コース: まくりには出足重視が有利
                if setting_type == 'dash':
                    score = max_score * 0.8
                elif setting_type == 'balanced':
                    score = max_score * 0.6
                else:
                    score = max_score * 0.4

            desc = f'チルト{tilt:+.1f}°（{type_desc}）'

            return {
                'score': round(score, 2),
                'tilt_angle': tilt,
                'setting_type': setting_type,
                'description': desc
            }

        finally:
            conn.close()

    def calculate_recent_form_score(
        self,
        racer_number: str,
        race_date: str,
        max_score: float = 8.0
    ) -> Dict:
        """
        直近成績（短期の調子）に基づくスコアを計算

        racer_features テーブルから直近3/5/10走の成績を取得し、
        短期的な調子を評価する。

        Args:
            racer_number: 選手番号
            race_date: 対象日付
            max_score: 最大スコア

        Returns:
            {'score': float, 'recent_win_rate': float, 'recent_avg_rank': float,
             'trend': str, 'description': str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 最も近い日付のracer_featuresを取得
            cursor.execute('''
                SELECT
                    recent_avg_rank_3, recent_avg_rank_5, recent_avg_rank_10,
                    recent_win_rate_3, recent_win_rate_5, recent_win_rate_10,
                    total_races, race_date
                FROM racer_features
                WHERE racer_number = ? AND race_date <= ?
                ORDER BY race_date DESC
                LIMIT 1
            ''', (racer_number, race_date))

            row = cursor.fetchone()

            if not row:
                return {
                    'score': max_score * 0.5,
                    'recent_win_rate': None,
                    'recent_avg_rank': None,
                    'trend': 'unknown',
                    'description': '直近成績データなし'
                }

            (avg_rank_3, avg_rank_5, avg_rank_10,
             win_rate_3, win_rate_5, win_rate_10,
             total_races, feature_date) = row

            # メイン指標として直近5走を使用
            recent_win_rate = win_rate_5 if win_rate_5 is not None else (win_rate_3 or win_rate_10 or 0)
            recent_avg_rank = avg_rank_5 if avg_rank_5 is not None else (avg_rank_3 or avg_rank_10 or 3.5)

            # トレンド判定（直近3走 vs 直近10走）
            if win_rate_3 is not None and win_rate_10 is not None:
                if win_rate_3 > win_rate_10 + 10:  # 10%以上改善
                    trend = 'improving'
                    trend_desc = '上昇中'
                elif win_rate_3 < win_rate_10 - 10:  # 10%以上低下
                    trend = 'declining'
                    trend_desc = '下降中'
                else:
                    trend = 'stable'
                    trend_desc = '安定'
            else:
                trend = 'unknown'
                trend_desc = '不明'

            # スコア計算
            # 勝率ベース（0-100%を0-max_scoreに変換）
            # 平均勝率は約16.7%（1/6）なので、30%以上で高評価
            win_rate_score = min(recent_win_rate / 30.0, 1.0) * max_score * 0.6

            # 平均着順ベース（1.0-6.0を逆転してスコア化）
            # 平均着順3.5が普通、2.0以下で高評価
            rank_score = max(0, (4.5 - recent_avg_rank) / 3.5) * max_score * 0.4

            score = win_rate_score + rank_score

            # トレンドボーナス/ペナルティ
            if trend == 'improving':
                score *= 1.1  # 10%ボーナス
            elif trend == 'declining':
                score *= 0.9  # 10%ペナルティ

            score = max(0, min(max_score, score))

            # 説明文
            desc = f'直近5走: 勝率{recent_win_rate:.0f}%, 平均{recent_avg_rank:.1f}着（{trend_desc}）'

            return {
                'score': round(score, 2),
                'recent_win_rate': recent_win_rate,
                'recent_avg_rank': recent_avg_rank,
                'trend': trend,
                'description': desc
            }

        finally:
            conn.close()

    def calculate_venue_affinity_score(
        self,
        racer_number: str,
        venue_code: str,
        race_date: str,
        max_score: float = 6.0
    ) -> Dict:
        """
        会場別成績（地元/得意水面）に基づくスコアを計算

        選手によっては特定の会場で高い勝率を持つ。
        地元選手や得意水面を持つ選手を評価する。

        Args:
            racer_number: 選手番号
            venue_code: 会場コード
            race_date: 対象日付
            max_score: 最大スコア

        Returns:
            {'score': float, 'venue_win_rate': float, 'venue_races': int,
             'is_local': bool, 'description': str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # racer_venue_featuresから会場別成績を取得
            cursor.execute('''
                SELECT venue_win_rate, venue_avg_rank, venue_races
                FROM racer_venue_features
                WHERE racer_number = ? AND venue_code = ? AND race_date <= ?
                ORDER BY race_date DESC
                LIMIT 1
            ''', (racer_number, venue_code, race_date))

            row = cursor.fetchone()

            if not row or row[2] < 5:  # 5レース未満はデータ不足
                return {
                    'score': max_score * 0.5,
                    'venue_win_rate': None,
                    'venue_avg_rank': None,
                    'venue_races': row[2] if row else 0,
                    'is_local': False,
                    'description': '会場別データ不足'
                }

            venue_win_rate, venue_avg_rank, venue_races = row

            # 全国平均勝率（16.7%）との比較でスコア計算
            national_avg_win_rate = 0.167
            win_rate_ratio = venue_win_rate / national_avg_win_rate if national_avg_win_rate > 0 else 1.0

            # 勝率が全国平均の2倍（33%）以上なら満点、半分（8%）以下なら0点
            if win_rate_ratio >= 2.0:
                score = max_score
            elif win_rate_ratio <= 0.5:
                score = 0
            else:
                # 線形補間
                score = max_score * (win_rate_ratio - 0.5) / 1.5

            # データ量によるボーナス
            if venue_races >= 30:
                score = min(max_score, score * 1.1)  # 十分なサンプル数
            elif venue_races < 10:
                score *= 0.9  # サンプル数不足で減点

            # 得意/不得意判定
            is_strong = venue_win_rate > national_avg_win_rate * 1.5  # 1.5倍以上
            is_weak = venue_win_rate < national_avg_win_rate * 0.7  # 0.7倍以下

            # 説明文
            if is_strong:
                desc = f'得意水面（当地勝率{venue_win_rate*100:.1f}%, {venue_races}走）'
            elif is_weak:
                desc = f'苦手水面（当地勝率{venue_win_rate*100:.1f}%, {venue_races}走）'
            else:
                desc = f'当地勝率{venue_win_rate*100:.1f}%（{venue_races}走）'

            return {
                'score': round(max(0, min(max_score, score)), 2),
                'venue_win_rate': round(venue_win_rate * 100, 1),
                'venue_avg_rank': round(venue_avg_rank, 2) if venue_avg_rank else None,
                'venue_races': venue_races,
                'is_strong': is_strong,
                'description': desc
            }

        finally:
            conn.close()

    def calculate_place_rate_score(
        self,
        racer_number: str,
        race_date: str,
        max_score: float = 5.0
    ) -> Dict:
        """
        2着率・3着率（連対率）に基づくスコアを計算

        勝率だけでなく、2着・3着に入る確率も重要。
        連に絡む確率が高い選手を評価する。

        Args:
            racer_number: 選手番号
            race_date: 対象日付
            max_score: 最大スコア

        Returns:
            {'score': float, 'second_rate': float, 'third_rate': float,
             'rentai_rate': float, 'description': str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 直近の成績から2着率・3着率を計算
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN res.rank IN ('1', '2') THEN 1 ELSE 0 END) as second_count,
                    SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as third_count
                FROM entries e
                JOIN races r ON e.race_id = r.id
                JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
                WHERE e.racer_number = ?
                  AND r.race_date < ?
                  AND r.race_date >= date(?, '-180 days')
                  AND res.rank IN ('1', '2', '3', '4', '5', '6')
            ''', (racer_number, race_date, race_date))

            row = cursor.fetchone()

            if not row or row[0] < 10:  # 10レース未満はデータ不足
                return {
                    'score': max_score * 0.5,
                    'win_rate': None,
                    'second_rate': None,
                    'third_rate': None,
                    'rentai_rate': None,
                    'description': '連対率データ不足'
                }

            total, win_count, second_count, third_count = row

            win_rate = win_count / total
            second_rate = second_count / total  # 2連対率
            third_rate = third_count / total  # 3連対率

            # 連対率ベースのスコア
            # 平均的な2連対率: 33.3% (1/3)
            # 平均的な3連対率: 50.0% (1/2)
            # 2連対率を重視（連勝式で重要）

            # 2連対率スコア（60%の重み）
            avg_second_rate = 0.333
            second_score = (second_rate / avg_second_rate) * (max_score * 0.6)

            # 3連対率スコア（40%の重み）
            avg_third_rate = 0.500
            third_score = (third_rate / avg_third_rate) * (max_score * 0.4)

            score = second_score + third_score
            score = max(0, min(max_score, score))

            # 連対強さ判定
            is_strong_rentai = second_rate > 0.45  # 2連対率45%以上

            # 説明文
            if is_strong_rentai:
                desc = f'連対力◎（2連対{second_rate*100:.0f}%, 3連対{third_rate*100:.0f}%）'
            elif second_rate > avg_second_rate:
                desc = f'連対○（2連対{second_rate*100:.0f}%）'
            else:
                desc = f'連対△（2連対{second_rate*100:.0f}%）'

            return {
                'score': round(score, 2),
                'win_rate': round(win_rate * 100, 1),
                'second_rate': round(second_rate * 100, 1),
                'third_rate': round(third_rate * 100, 1),
                'rentai_rate': round(second_rate * 100, 1),  # 2連対率
                'is_strong_rentai': is_strong_rentai,
                'description': desc
            }

        finally:
            conn.close()

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
        race_entries: List[Dict] = None,
        race_id: int = None
    ) -> Dict:
        """
        総合拡張スコアを計算

        2024年11月27日更新: EXTENDED_SCORE_WEIGHTSの設定を使用

        Args:
            entry: {'pit_number', 'racer_number', 'racer_rank', 'f_count', 'l_count', 'motor_number', ...}
            venue_code: 会場コード
            target_date: 対象日付
            race_entries: 同レースの全出走者リスト
            race_id: レースID（展示データ取得用）

        Returns:
            総合スコアと各要素の詳細
        """
        # TEMPORARY BYPASS: DBアクセスを全てスキップしてデフォルト値を返す
        pit_number = entry.get('pit_number')
        weights = EXTENDED_SCORE_WEIGHTS

        # 最小限の計算のみ
        class_result = self.calculate_class_score(entry.get('racer_rank'), max_score=float(weights.get('class', 10)))
        fl_result = self.calculate_fl_penalty(entry.get('f_count', 0), entry.get('l_count', 0))
        st_result = self.calculate_start_timing_score(entry.get('avg_st'), pit_number, max_score=float(weights.get('start_timing', 10)))

        # 全てのDBアクセスメソッドをデフォルト値に置き換え
        total_score = (
            class_result['score'] + fl_result['penalty'] + st_result['score'] +
            2.5 + 2.5 + 2.5 + 2.5 + 2.5 + 4.0 + 1.0 + 4.0 + 3.0 + 2.5
        )

        return {
            'total_extended_score': total_score,
            'max_possible_score': sum(v for k, v in weights.items() if k != 'fl_penalty'),
            'weights_used': weights,
            'class': class_result,
            'fl_penalty': fl_result,
            'session': {'score': 2.5, 'description': 'バイパス中'},
            'prev_race': {'score': 2.5, 'description': 'バイパス中'},
            'course_entry': {'score': 2.5, 'description': 'バイパス中'},
            'matchup': {'relative_score': 2.5},
            'motor': {'score': 2.5, 'description': 'バイパス中'},
            'start_timing': st_result,
            'exhibition': {'score': 4.0, 'description': 'バイパス中'},
            'tilt': {'score': 1.0, 'description': 'バイパス中'},
            'recent_form': {'score': 4.0, 'description': 'バイパス中'},
            'venue_affinity': {'score': 3.0, 'description': 'バイパス中'},
            'place_rate': {'score': 2.5, 'description': 'バイパス中'},
            'course_prediction': {'predicted_course': pit_number, 'confidence': 0.5, 'description': 'バイパス中'}
        }

        # ORIGINAL CODE BELOW - TEMPORARILY BYPASSED
        pit_number = entry.get('pit_number')
        racer_number = entry.get('racer_number')

        # 設定ファイルから重みを取得
        weights = EXTENDED_SCORE_WEIGHTS

        # 1. 級別スコア (設定: class)
        class_result = self.calculate_class_score(
            entry.get('racer_rank'),
            max_score=float(weights.get('class', 10))
        )

        # 2. F/Lペナルティ (max: 0, min: -10)
        fl_result = self.calculate_fl_penalty(
            entry.get('f_count', 0),
            entry.get('l_count', 0)
        )

        # 3. 節間成績 (設定: session)
        session_result = self.calculate_session_performance(
            racer_number,
            venue_code,
            target_date,
            max_score=float(weights.get('session', 5))
        )

        # 4. 前走レベル (設定: prev_race)
        prev_race_result = self.calculate_previous_race_level(
            racer_number,
            target_date,
            max_score=float(weights.get('prev_race', 5))
        )

        # 5. 進入コース傾向分析 (設定: course_entry)
        course_entry_result = self.calculate_course_entry_tendency(
            racer_number,
            pit_number,
            max_score=float(weights.get('course_entry', 5))
        )

        # 6. 選手間相性（race_entriesがあれば）(設定: matchup)
        matchup_result = {}
        matchup_max = float(weights.get('matchup', 5))
        if race_entries:
            all_matchups = self.analyze_racer_matchup(race_entries, max_score=matchup_max)
            matchup_result = all_matchups.get(pit_number, {})

        # 7. モーター特性 (設定: motor)
        motor_result = self.analyze_motor_characteristics(
            entry.get('motor_number'),
            venue_code,
            max_score=float(weights.get('motor', 5))
        )

        # 8. 平均STスコア (設定: start_timing) - 重要指標のため強化
        st_result = self.calculate_start_timing_score(
            entry.get('avg_st'),
            pit_number,
            max_score=float(weights.get('start_timing', 10))  # 8→10に強化
        )

        # 9. 展示タイムスコア (設定: exhibition) - 重要指標のため強化
        exhibition_max = float(weights.get('exhibition', 10))  # 8→10に強化
        exhibition_result = {'score': exhibition_max * 0.5, 'description': '展示データなし'}
        if race_id:
            exhibition_result = self.calculate_exhibition_time_score(
                race_id,
                pit_number,
                max_score=exhibition_max
            )

        # 10. チルト角度スコア (設定: tilt) - 影響小のため低下
        tilt_max = float(weights.get('tilt', 2))  # 3→2に低下
        tilt_result = {'score': tilt_max * 0.5, 'description': 'チルトデータなし'}
        if race_id:
            tilt_result = self.calculate_tilt_angle_score(
                race_id,
                pit_number,
                racer_number,
                max_score=tilt_max
            )

        # 11. 直近成績スコア (設定: recent_form)
        recent_form_result = self.calculate_recent_form_score(
            racer_number,
            target_date,
            max_score=float(weights.get('recent_form', 8))
        )

        # 12. 会場別勝率スコア (設定: venue_affinity) - 強化
        venue_affinity_result = self.calculate_venue_affinity_score(
            racer_number,
            venue_code,
            target_date,
            max_score=float(weights.get('venue_affinity', 8))  # 6→8に強化
        )

        # 13. 連対率スコア (設定: place_rate)
        place_rate_result = self.calculate_place_rate_score(
            racer_number,
            target_date,
            max_score=float(weights.get('place_rate', 5))
        )

        # 総合スコア計算
        # 各スコアを合算
        total_score = (
            class_result['score'] +
            fl_result['penalty'] +
            session_result['score'] +
            prev_race_result['score'] +
            course_entry_result['score'] +
            matchup_result.get('relative_score', matchup_max * 0.5) +
            motor_result['score'] +
            st_result['score'] +
            exhibition_result['score'] +
            tilt_result['score'] +
            recent_form_result['score'] +
            venue_affinity_result['score'] +
            place_rate_result['score']
        )

        # 最大可能スコアを計算（正規化用）
        max_possible = sum(
            v for k, v in weights.items() if k != 'fl_penalty'
        )

        # 進入予測の信頼度を考慮した補正
        # 前付け常習者がいる場合、他艇の予測信頼度も下がる
        entry_confidence = course_entry_result.get('confidence', 0.8)
        if entry_confidence < 0.6:
            # 進入不安定な選手は全体スコアにペナルティ
            total_score *= 0.95

        return {
            'total_extended_score': total_score,
            'max_possible_score': max_possible,  # 動的計算（78点）
            'weights_used': weights,  # 使用した重み設定
            'class': class_result,
            'fl_penalty': fl_result,
            'session': session_result,
            'prev_race': prev_race_result,
            'course_entry': course_entry_result,
            'course_prediction': {  # 後方互換性
                'predicted_course': course_entry_result.get('predicted_course', pit_number),
                'confidence': course_entry_result.get('confidence', 0.8),
                'description': course_entry_result.get('description', '')
            },
            'matchup': matchup_result,
            'motor': motor_result,
            'start_timing': st_result,
            'exhibition': exhibition_result,
            'tilt': tilt_result,
            'recent_form': recent_form_result,
            'venue_affinity': venue_affinity_result,
            'place_rate': place_rate_result
        }
