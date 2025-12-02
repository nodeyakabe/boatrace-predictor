"""
複合バフ自動学習モジュール

過去データから複合条件と結果の相関を分析し、
バフルールを自動的に検証・更新する。
"""

import sqlite3
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import math
from .compound_buff_system import CompoundBuffRule, BuffCondition, ConditionType


@dataclass
class BuffValidationResult:
    """バフ検証結果"""
    rule_id: str
    sample_count: int
    hit_rate: float          # 実際の1着率
    expected_rate: float     # 期待1着率（ベースライン）
    lift: float              # リフト（実際/期待）
    statistical_significance: float  # 統計的有意性
    recommended_buff: float  # 推奨バフ値
    is_valid: bool           # 有効なルールか


class BuffAutoLearner:
    """バフ自動学習クラス"""

    # 最低サンプル数
    MIN_SAMPLES = 50

    # 統計的有意性の閾値（95%信頼区間）
    SIGNIFICANCE_THRESHOLD = 1.96

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def validate_rule(
        self,
        rule: CompoundBuffRule,
        start_date: str,
        end_date: str
    ) -> BuffValidationResult:
        """
        ルールを過去データで検証

        Args:
            rule: 検証するルール
            start_date: 検証期間開始日
            end_date: 検証期間終了日

        Returns:
            検証結果
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # ルール条件に合致するレースを抽出
            matching_races = self._find_matching_races(cursor, rule, start_date, end_date)

            if len(matching_races) < self.MIN_SAMPLES:
                return BuffValidationResult(
                    rule_id=rule.rule_id,
                    sample_count=len(matching_races),
                    hit_rate=0.0,
                    expected_rate=0.167,  # 1/6
                    lift=1.0,
                    statistical_significance=0.0,
                    recommended_buff=0.0,
                    is_valid=False
                )

            # 1着率を計算
            hit_count = sum(1 for r in matching_races if r['is_win'])
            hit_rate = hit_count / len(matching_races)

            # ベースライン（コース別平均勝率）
            expected_rate = self._get_baseline_win_rate(cursor, rule)

            # リフト計算
            lift = hit_rate / expected_rate if expected_rate > 0 else 1.0

            # 統計的有意性（z検定）
            n = len(matching_races)
            se = math.sqrt(expected_rate * (1 - expected_rate) / n)
            z_score = (hit_rate - expected_rate) / se if se > 0 else 0

            # 推奨バフ値の計算
            # リフトに基づく: 1.5倍以上で+5点、2倍で+10点
            if lift > 1.0:
                recommended_buff = min(15.0, (lift - 1.0) * 10.0)
            else:
                recommended_buff = max(-10.0, (lift - 1.0) * 10.0)

            return BuffValidationResult(
                rule_id=rule.rule_id,
                sample_count=len(matching_races),
                hit_rate=hit_rate,
                expected_rate=expected_rate,
                lift=lift,
                statistical_significance=z_score,
                recommended_buff=recommended_buff,
                is_valid=abs(z_score) >= self.SIGNIFICANCE_THRESHOLD
            )

        finally:
            conn.close()

    def _find_matching_races(
        self,
        cursor,
        rule: CompoundBuffRule,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        """
        ルール条件に合致するレースを抽出
        """
        # 基本クエリ
        query = '''
            SELECT
                r.id as race_id,
                r.venue_code,
                e.pit_number,
                rd.actual_course,
                res.rank,
                e.racer_number,
                e.racer_rank,
                m.motor_number
            FROM races r
            JOIN entries e ON r.id = e.race_id
            LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            LEFT JOIN motors m ON e.motor_number = m.motor_number AND r.venue_code = m.venue_code
            WHERE r.race_date BETWEEN ? AND ?
            AND res.rank IS NOT NULL
        '''

        params = [start_date, end_date]

        # 条件を追加
        for cond in rule.conditions:
            if cond.condition_type == ConditionType.VENUE:
                if isinstance(cond.value, list):
                    placeholders = ','.join('?' * len(cond.value))
                    query += f' AND r.venue_code IN ({placeholders})'
                    params.extend(cond.value)
                else:
                    query += ' AND r.venue_code = ?'
                    params.append(cond.value)

            elif cond.condition_type == ConditionType.COURSE:
                if isinstance(cond.value, list):
                    placeholders = ','.join('?' * len(cond.value))
                    query += f' AND COALESCE(rd.actual_course, e.pit_number) IN ({placeholders})'
                    params.extend(cond.value)
                else:
                    query += ' AND COALESCE(rd.actual_course, e.pit_number) = ?'
                    params.append(cond.value)

            elif cond.condition_type == ConditionType.RACER_RANK:
                if isinstance(cond.value, list):
                    placeholders = ','.join('?' * len(cond.value))
                    query += f' AND e.racer_rank IN ({placeholders})'
                    params.extend(cond.value)
                else:
                    query += ' AND e.racer_rank = ?'
                    params.append(cond.value)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            try:
                rank = int(row[4])
                is_win = (rank == 1)
            except (ValueError, TypeError):
                is_win = False

            results.append({
                'race_id': row[0],
                'venue_code': row[1],
                'pit_number': row[2],
                'actual_course': row[3] or row[2],
                'rank': row[4],
                'is_win': is_win,
                'racer_number': row[5],
                'racer_rank': row[6]
            })

        return results

    def _get_baseline_win_rate(self, cursor, rule: CompoundBuffRule) -> float:
        """
        ベースライン勝率を取得（条件なしの場合の平均勝率）
        """
        # コース条件がある場合はそのコースの平均勝率を使用
        for cond in rule.conditions:
            if cond.condition_type == ConditionType.COURSE:
                course = cond.value if not isinstance(cond.value, list) else cond.value[0]
                course_win_rates = {
                    1: 0.55, 2: 0.14, 3: 0.12,
                    4: 0.10, 5: 0.06, 6: 0.03
                }
                return course_win_rates.get(course, 0.167)

        return 0.167  # 1/6

    def discover_new_rules(
        self,
        start_date: str,
        end_date: str,
        min_lift: float = 1.3
    ) -> List[CompoundBuffRule]:
        """
        過去データから新しいルールを発見

        Args:
            start_date: 分析期間開始日
            end_date: 分析期間終了日
            min_lift: 最低リフト値

        Returns:
            発見されたルールのリスト
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        discovered_rules = []

        try:
            # 会場×コースの組み合わせを分析
            cursor.execute('''
                SELECT
                    r.venue_code,
                    COALESCE(rd.actual_course, e.pit_number) as course,
                    COUNT(*) as total,
                    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
                FROM races r
                JOIN entries e ON r.id = e.race_id
                LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
                LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
                WHERE r.race_date BETWEEN ? AND ?
                AND res.rank IS NOT NULL
                GROUP BY r.venue_code, course
                HAVING COUNT(*) >= ?
            ''', (start_date, end_date, self.MIN_SAMPLES))

            for venue, course, total, wins in cursor.fetchall():
                win_rate = wins / total
                expected = {1: 0.55, 2: 0.14, 3: 0.12, 4: 0.10, 5: 0.06, 6: 0.03}.get(course, 0.167)
                lift = win_rate / expected if expected > 0 else 1.0

                if lift >= min_lift:
                    # 有意なパターンを発見
                    buff_value = min(10.0, (lift - 1.0) * 8.0)

                    rule = CompoundBuffRule(
                        rule_id=f"auto_{venue}_{course}",
                        name=f"会場{venue}の{course}コース強化",
                        description=f"自動発見: 会場{venue}で{course}コースの勝率が{win_rate*100:.1f}%",
                        conditions=[
                            BuffCondition(ConditionType.VENUE, venue),
                            BuffCondition(ConditionType.COURSE, course),
                        ],
                        buff_value=buff_value,
                        confidence=0.7,  # 自動発見は初期信頼度を低めに
                        sample_count=total,
                        hit_rate=win_rate
                    )
                    discovered_rules.append(rule)

            return discovered_rules

        finally:
            conn.close()

    def update_rule_confidence(
        self,
        rule: CompoundBuffRule,
        validation_result: BuffValidationResult
    ) -> CompoundBuffRule:
        """
        検証結果に基づいてルールの信頼度とバフ値を更新
        """
        # 信頼度の更新（ベイズ更新的アプローチ）
        prior_confidence = rule.confidence
        evidence_weight = min(1.0, validation_result.sample_count / 100)

        if validation_result.is_valid:
            new_confidence = prior_confidence * 0.7 + 0.3 * evidence_weight
        else:
            new_confidence = prior_confidence * 0.8  # 無効な場合は徐々に低下

        # バフ値の更新
        new_buff = (rule.buff_value * 0.6 + validation_result.recommended_buff * 0.4)

        return CompoundBuffRule(
            rule_id=rule.rule_id,
            name=rule.name,
            description=rule.description,
            conditions=rule.conditions,
            buff_value=new_buff,
            confidence=new_confidence,
            sample_count=validation_result.sample_count,
            hit_rate=validation_result.hit_rate,
            is_active=new_confidence >= 0.3  # 信頼度0.3未満は無効化
        )
