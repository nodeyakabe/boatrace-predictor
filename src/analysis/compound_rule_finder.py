# -*- coding: utf-8 -*-
"""
Compound Rule Finder - Phase 4

複合条件ルール発見システム
複数の条件を組み合わせて、高精度の予測ルールを発見する
"""

import sqlite3
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict
from itertools import combinations
import json


@dataclass
class PredictionRule:
    """予測ルール"""
    rule_id: str
    conditions: List[Dict]  # 条件リスト
    description: str
    # 統計
    total_races: int
    hit_count: int
    hit_rate: float
    # 収益性
    avg_payout: float
    roi: float
    # メタ
    confidence_level: str  # A, B, C
    priority: int = 0


@dataclass
class RuleCondition:
    """ルール条件"""
    field: str  # 条件対象フィールド
    operator: str  # eq, ne, gt, lt, gte, lte, in
    value: any  # 比較値


class CompoundRuleFinder:
    """
    複合条件ルール発見器

    複数の条件を組み合わせて、高的中率のパターンを自動発見
    """

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path
        self.discovered_rules: List[PredictionRule] = []
        self._ensure_tables()

    def _ensure_tables(self):
        """ルール保存用テーブルを作成"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS compound_rules (
                    rule_id TEXT PRIMARY KEY,
                    conditions TEXT,  -- JSON
                    description TEXT,
                    total_races INTEGER,
                    hit_count INTEGER,
                    hit_rate REAL,
                    avg_payout REAL,
                    roi REAL,
                    confidence_level TEXT,
                    priority INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.commit()

    def discover_first_place_rules(self, min_races: int = 50, min_hit_rate: float = 0.6):
        """
        1着予測の高精度ルールを発見

        Args:
            min_races: 最低レース数
            min_hit_rate: 最低的中率
        """
        print("Discovering 1st place prediction rules...")

        rules = []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # ルール1: 1コース + A1選手 + モーター2連率35%以上
            rules.extend(self._find_course_rank_motor_rules(cursor, min_races, min_hit_rate))

            # ルール2: 会場別の決まりパターン
            rules.extend(self._find_venue_specific_rules(cursor, min_races, min_hit_rate))

            # ルール3: 選手ランク差パターン
            rules.extend(self._find_rank_gap_rules(cursor, min_races, min_hit_rate))

            # ルール4: スタートタイミング優位
            rules.extend(self._find_start_timing_rules(cursor, min_races, min_hit_rate))

        self.discovered_rules.extend(rules)
        print(f"Discovered {len(rules)} 1st place rules")
        return rules

    def _find_course_rank_motor_rules(
        self,
        cursor,
        min_races: int,
        min_hit_rate: float
    ) -> List[PredictionRule]:
        """コース×ランク×モーターの複合ルールを発見"""
        rules = []

        # 各コースについて調査
        for course in range(1, 7):
            for rank in ['A1', 'A2', 'B1']:
                for motor_threshold in [0.30, 0.35, 0.40]:
                    cursor.execute('''
                        SELECT
                            COUNT(*) as total,
                            SUM(CASE WHEN res.rank = 1 THEN 1 ELSE 0 END) as hits,
                            AVG(CASE WHEN res.rank = 1 THEN p.amount ELSE 0 END) as avg_payout
                        FROM entries e
                        JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                        LEFT JOIN payouts p ON e.race_id = p.race_id AND p.bet_type = 'trifecta'
                        WHERE e.pit_number = ?
                          AND e.racer_rank = ?
                          AND COALESCE(e.motor_second_rate, 0.30) >= ?
                          AND res.is_invalid = 0
                    ''', (course, rank, motor_threshold))

                    row = cursor.fetchone()
                    if row and row[0] >= min_races:
                        hit_rate = row[1] / row[0]
                        if hit_rate >= min_hit_rate:
                            rule = PredictionRule(
                                rule_id=f"C{course}_{rank}_M{int(motor_threshold*100)}",
                                conditions=[
                                    {'field': 'course', 'op': 'eq', 'value': course},
                                    {'field': 'racer_rank', 'op': 'eq', 'value': rank},
                                    {'field': 'motor_second_rate', 'op': 'gte', 'value': motor_threshold}
                                ],
                                description=f"{course}C + {rank} + Motor>={motor_threshold*100}%",
                                total_races=row[0],
                                hit_count=row[1],
                                hit_rate=hit_rate,
                                avg_payout=row[2] or 0,
                                roi=0,  # 後で計算
                                confidence_level='A' if hit_rate >= 0.7 else 'B'
                            )
                            rules.append(rule)

        return rules

    def _find_venue_specific_rules(
        self,
        cursor,
        min_races: int,
        min_hit_rate: float
    ) -> List[PredictionRule]:
        """会場別の特殊ルールを発見"""
        rules = []

        # 1コース逃げが強い会場
        cursor.execute('''
            SELECT
                r.venue_code,
                COUNT(*) as total,
                SUM(CASE WHEN res.rank = 1 AND e.pit_number = 1 THEN 1 ELSE 0 END) as c1_wins
            FROM entries e
            JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            JOIN races r ON e.race_id = r.id
            WHERE res.is_invalid = 0 AND e.pit_number = 1
            GROUP BY r.venue_code
            HAVING total >= ?
        ''', (min_races,))

        for venue_code, total, c1_wins in cursor.fetchall():
            hit_rate = c1_wins / total
            if hit_rate >= min_hit_rate:
                # 更に条件を絞る: A級選手の場合
                cursor.execute('''
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN res.rank = 1 THEN 1 ELSE 0 END) as hits
                    FROM entries e
                    JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                    JOIN races r ON e.race_id = r.id
                    WHERE r.venue_code = ?
                      AND e.pit_number = 1
                      AND e.racer_rank IN ('A1', 'A2')
                      AND res.is_invalid = 0
                ''', (venue_code,))

                a_row = cursor.fetchone()
                if a_row and a_row[0] >= min_races // 2:
                    a_hit_rate = a_row[1] / a_row[0]
                    if a_hit_rate >= 0.65:
                        rule = PredictionRule(
                            rule_id=f"V{venue_code}_C1_A",
                            conditions=[
                                {'field': 'venue_code', 'op': 'eq', 'value': venue_code},
                                {'field': 'course', 'op': 'eq', 'value': 1},
                                {'field': 'racer_rank', 'op': 'in', 'value': ['A1', 'A2']}
                            ],
                            description=f"Venue {venue_code} + 1C + A-class",
                            total_races=a_row[0],
                            hit_count=a_row[1],
                            hit_rate=a_hit_rate,
                            avg_payout=0,
                            roi=0,
                            confidence_level='A' if a_hit_rate >= 0.75 else 'B'
                        )
                        rules.append(rule)

        return rules

    def _find_rank_gap_rules(
        self,
        cursor,
        min_races: int,
        min_hit_rate: float
    ) -> List[PredictionRule]:
        """ランク格差パターンを発見"""
        rules = []

        # 1コースがA1で、他にA1がいない場合
        cursor.execute('''
            WITH race_a1_counts AS (
                SELECT
                    e.race_id,
                    SUM(CASE WHEN e.racer_rank = 'A1' THEN 1 ELSE 0 END) as a1_count,
                    MAX(CASE WHEN e.pit_number = 1 AND e.racer_rank = 'A1' THEN 1 ELSE 0 END) as c1_is_a1
                FROM entries e
                GROUP BY e.race_id
            )
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN res.rank = 1 AND e.pit_number = 1 THEN 1 ELSE 0 END) as c1_wins
            FROM race_a1_counts rac
            JOIN entries e ON rac.race_id = e.race_id AND e.pit_number = 1
            JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            WHERE rac.c1_is_a1 = 1 AND rac.a1_count = 1
              AND res.is_invalid = 0
        ''')

        row = cursor.fetchone()
        if row and row[0] >= min_races:
            hit_rate = row[1] / row[0]
            if hit_rate >= min_hit_rate:
                rule = PredictionRule(
                    rule_id="C1_ONLY_A1",
                    conditions=[
                        {'field': 'course', 'op': 'eq', 'value': 1},
                        {'field': 'racer_rank', 'op': 'eq', 'value': 'A1'},
                        {'field': 'race_a1_count', 'op': 'eq', 'value': 1}
                    ],
                    description="1C is only A1 racer in race",
                    total_races=row[0],
                    hit_count=row[1],
                    hit_rate=hit_rate,
                    avg_payout=0,
                    roi=0,
                    confidence_level='A' if hit_rate >= 0.7 else 'B'
                )
                rules.append(rule)

        return rules

    def _find_start_timing_rules(
        self,
        cursor,
        min_races: int,
        min_hit_rate: float
    ) -> List[PredictionRule]:
        """スタートタイミング優位ルール"""
        rules = []

        # 1コースが最速スタート（平均ST最小）の場合
        cursor.execute('''
            WITH race_min_st AS (
                SELECT
                    e.race_id,
                    MIN(e.avg_st) as min_st,
                    MIN(CASE WHEN e.pit_number = 1 THEN e.avg_st ELSE 999 END) as c1_st
                FROM entries e
                WHERE e.avg_st IS NOT NULL
                  AND e.avg_st > -0.5 AND e.avg_st < 0.5
                GROUP BY e.race_id
            )
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN res.rank = 1 AND e.pit_number = 1 THEN 1 ELSE 0 END) as c1_wins
            FROM race_min_st rms
            JOIN entries e ON rms.race_id = e.race_id AND e.pit_number = 1
            JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            WHERE rms.c1_st <= rms.min_st + 0.02  -- 最速±0.02秒以内
              AND res.is_invalid = 0
        ''')

        row = cursor.fetchone()
        if row and row[0] >= min_races:
            hit_rate = row[1] / row[0]
            if hit_rate >= min_hit_rate:
                rule = PredictionRule(
                    rule_id="C1_FASTEST_ST",
                    conditions=[
                        {'field': 'course', 'op': 'eq', 'value': 1},
                        {'field': 'start_timing_rank', 'op': 'eq', 'value': 1}
                    ],
                    description="1C has fastest start timing",
                    total_races=row[0],
                    hit_count=row[1],
                    hit_rate=hit_rate,
                    avg_payout=0,
                    roi=0,
                    confidence_level='B'
                )
                rules.append(rule)

        return rules

    def discover_second_place_rules(self, min_races: int = 50, min_hit_rate: float = 0.35):
        """
        2着予測の高精度ルールを発見（1着が当たった前提）
        """
        print("Discovering 2nd place prediction rules...")

        rules = []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # ルール1: 1着のすぐ外コースが2着
            rules.extend(self._find_immediate_outside_rules(cursor, min_races, min_hit_rate))

            # ルール2: モーター優位者が2着
            rules.extend(self._find_motor_advantage_second_rules(cursor, min_races, min_hit_rate))

            # ルール3: 会場別2着パターン
            rules.extend(self._find_venue_second_patterns(cursor, min_races, min_hit_rate))

        self.discovered_rules.extend(rules)
        print(f"Discovered {len(rules)} 2nd place rules")
        return rules

    def _find_immediate_outside_rules(
        self,
        cursor,
        min_races: int,
        min_hit_rate: float
    ) -> List[PredictionRule]:
        """1着のすぐ外が2着パターン"""
        rules = []

        # 1着コース別に、すぐ外が2着になる確率
        for winner_course in range(1, 6):  # 1-5コース
            outside_course = winner_course + 1

            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN e2.pit_number = ? THEN 1 ELSE 0 END) as outside_second
                FROM results res1
                JOIN entries e1 ON res1.race_id = e1.race_id AND res1.pit_number = e1.pit_number
                JOIN results res2 ON res1.race_id = res2.race_id AND res2.rank = 2
                JOIN entries e2 ON res2.race_id = e2.race_id AND res2.pit_number = e2.pit_number
                WHERE res1.rank = 1 AND e1.pit_number = ?
                  AND res1.is_invalid = 0 AND res2.is_invalid = 0
            ''', (outside_course, winner_course))

            row = cursor.fetchone()
            if row and row[0] >= min_races:
                hit_rate = row[1] / row[0]
                if hit_rate >= min_hit_rate:
                    rule = PredictionRule(
                        rule_id=f"W{winner_course}_OUTSIDE_2ND",
                        conditions=[
                            {'field': 'winner_course', 'op': 'eq', 'value': winner_course},
                            {'field': 'candidate_course', 'op': 'eq', 'value': outside_course}
                        ],
                        description=f"When {winner_course}C wins, {outside_course}C gets 2nd",
                        total_races=row[0],
                        hit_count=row[1],
                        hit_rate=hit_rate,
                        avg_payout=0,
                        roi=0,
                        confidence_level='B' if hit_rate >= 0.3 else 'C'
                    )
                    rules.append(rule)

        return rules

    def _find_motor_advantage_second_rules(
        self,
        cursor,
        min_races: int,
        min_hit_rate: float
    ) -> List[PredictionRule]:
        """モーター優位者が2着になるルール"""
        rules = []

        # 1着以外で最もモーター率が高い艇が2着になる確率
        cursor.execute('''
            WITH winner_info AS (
                SELECT res.race_id, e.motor_second_rate as winner_motor
                FROM results res
                JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
                WHERE res.rank = 1 AND res.is_invalid = 0
            ),
            best_motor_except_winner AS (
                SELECT
                    e.race_id,
                    e.pit_number,
                    e.motor_second_rate,
                    ROW_NUMBER() OVER (PARTITION BY e.race_id ORDER BY e.motor_second_rate DESC) as motor_rank
                FROM entries e
                JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                WHERE res.rank != 1 AND res.is_invalid = 0
            )
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN res.rank = 2 THEN 1 ELSE 0 END) as hits
            FROM best_motor_except_winner bm
            JOIN results res ON bm.race_id = res.race_id AND bm.pit_number = res.pit_number
            WHERE bm.motor_rank = 1
        ''')

        row = cursor.fetchone()
        if row and row[0] >= min_races:
            hit_rate = row[1] / row[0]
            if hit_rate >= min_hit_rate:
                rule = PredictionRule(
                    rule_id="BEST_MOTOR_2ND",
                    conditions=[
                        {'field': 'motor_rank_except_winner', 'op': 'eq', 'value': 1}
                    ],
                    description="Best motor (excluding winner) gets 2nd",
                    total_races=row[0],
                    hit_count=row[1],
                    hit_rate=hit_rate,
                    avg_payout=0,
                    roi=0,
                    confidence_level='C'
                )
                rules.append(rule)

        return rules

    def _find_venue_second_patterns(
        self,
        cursor,
        min_races: int,
        min_hit_rate: float
    ) -> List[PredictionRule]:
        """会場別の2着パターン"""
        rules = []

        # 会場×1着コース別に2着コースのパターンを分析
        cursor.execute('''
            SELECT
                r.venue_code,
                e1.pit_number as winner_course,
                e2.pit_number as second_course,
                COUNT(*) as count
            FROM results res1
            JOIN results res2 ON res1.race_id = res2.race_id
            JOIN entries e1 ON res1.race_id = e1.race_id AND res1.pit_number = e1.pit_number
            JOIN entries e2 ON res2.race_id = e2.race_id AND res2.pit_number = e2.pit_number
            JOIN races r ON res1.race_id = r.id
            WHERE res1.rank = 1 AND res2.rank = 2
              AND res1.is_invalid = 0 AND res2.is_invalid = 0
            GROUP BY r.venue_code, e1.pit_number, e2.pit_number
        ''')

        venue_patterns = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        venue_totals = defaultdict(lambda: defaultdict(int))

        for venue, w_course, s_course, count in cursor.fetchall():
            venue_patterns[venue][w_course][s_course] = count
            venue_totals[venue][w_course] += count

        # 高確率パターンをルール化
        for venue in venue_patterns:
            for w_course in venue_patterns[venue]:
                total = venue_totals[venue][w_course]
                if total < min_races:
                    continue

                for s_course, count in venue_patterns[venue][w_course].items():
                    hit_rate = count / total
                    if hit_rate >= min_hit_rate:
                        rule = PredictionRule(
                            rule_id=f"V{venue}_W{w_course}_S{s_course}",
                            conditions=[
                                {'field': 'venue_code', 'op': 'eq', 'value': venue},
                                {'field': 'winner_course', 'op': 'eq', 'value': w_course},
                                {'field': 'candidate_course', 'op': 'eq', 'value': s_course}
                            ],
                            description=f"Venue {venue}: {w_course}C wins -> {s_course}C 2nd",
                            total_races=total,
                            hit_count=count,
                            hit_rate=hit_rate,
                            avg_payout=0,
                            roi=0,
                            confidence_level='B'
                        )
                        rules.append(rule)

        return rules

    def discover_upset_warning_rules(self, min_races: int = 30):
        """
        番狂わせの警告ルールを発見

        「1コース有利だが実は荒れる」パターンを見つける
        """
        print("Discovering upset warning rules...")

        rules = []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 1コースが予想通り勝てないパターン
            # 条件: 1コースがB級 + 外にA級がいる
            cursor.execute('''
                WITH race_config AS (
                    SELECT
                        e.race_id,
                        MAX(CASE WHEN e.pit_number = 1 AND e.racer_rank IN ('B1', 'B2') THEN 1 ELSE 0 END) as c1_is_b,
                        MAX(CASE WHEN e.pit_number > 1 AND e.racer_rank = 'A1' THEN 1 ELSE 0 END) as has_outer_a1
                    FROM entries e
                    GROUP BY e.race_id
                )
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN res.rank = 1 AND e.pit_number != 1 THEN 1 ELSE 0 END) as upset_count
                FROM race_config rc
                JOIN entries e ON rc.race_id = e.race_id
                JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                WHERE rc.c1_is_b = 1 AND rc.has_outer_a1 = 1
                  AND res.rank = 1 AND res.is_invalid = 0
            ''')

            row = cursor.fetchone()
            if row and row[0] >= min_races:
                upset_rate = row[1] / row[0]
                if upset_rate >= 0.4:  # 40%以上で番狂わせ
                    rule = PredictionRule(
                        rule_id="UPSET_B_VS_OUTER_A1",
                        conditions=[
                            {'field': 'c1_racer_rank', 'op': 'in', 'value': ['B1', 'B2']},
                            {'field': 'has_outer_a1', 'op': 'eq', 'value': True}
                        ],
                        description="1C is B-class with outer A1 -> High upset chance",
                        total_races=row[0],
                        hit_count=row[1],  # 番狂わせ数
                        hit_rate=upset_rate,
                        avg_payout=0,
                        roi=0,
                        confidence_level='B',
                        priority=-1  # 警告ルールなのでマイナス優先度
                    )
                    rules.append(rule)

        self.discovered_rules.extend(rules)
        print(f"Discovered {len(rules)} upset warning rules")
        return rules

    def save_rules(self):
        """発見したルールをDBに保存"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for rule in self.discovered_rules:
                cursor.execute('''
                    INSERT OR REPLACE INTO compound_rules
                    (rule_id, conditions, description, total_races, hit_count,
                     hit_rate, avg_payout, roi, confidence_level, priority)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    rule.rule_id,
                    json.dumps(rule.conditions),
                    rule.description,
                    rule.total_races,
                    rule.hit_count,
                    rule.hit_rate,
                    rule.avg_payout,
                    rule.roi,
                    rule.confidence_level,
                    rule.priority
                ))

            conn.commit()

        print(f"Saved {len(self.discovered_rules)} rules to database")

    def load_rules(self) -> List[PredictionRule]:
        """保存されたルールを読み込み"""
        rules = []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT rule_id, conditions, description, total_races, hit_count,
                       hit_rate, avg_payout, roi, confidence_level, priority
                FROM compound_rules
                WHERE is_active = 1
                ORDER BY hit_rate DESC, total_races DESC
            ''')

            for row in cursor.fetchall():
                rule = PredictionRule(
                    rule_id=row[0],
                    conditions=json.loads(row[1]) if row[1] else [],
                    description=row[2],
                    total_races=row[3],
                    hit_count=row[4],
                    hit_rate=row[5],
                    avg_payout=row[6] or 0,
                    roi=row[7] or 0,
                    confidence_level=row[8],
                    priority=row[9] or 0
                )
                rules.append(rule)

        return rules

    def get_applicable_rules(
        self,
        race_id: int,
        pit_number: int
    ) -> List[PredictionRule]:
        """
        特定のレース・艇に適用可能なルールを取得

        Args:
            race_id: レースID
            pit_number: 艇番

        Returns:
            適用可能なルールのリスト
        """
        applicable = []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # レース・エントリー情報を取得
            cursor.execute('''
                SELECT
                    r.venue_code,
                    e.pit_number as course,
                    e.racer_rank,
                    COALESCE(e.motor_second_rate, 0.30) as motor_rate
                FROM races r
                JOIN entries e ON r.id = e.race_id
                WHERE r.id = ? AND e.pit_number = ?
            ''', (race_id, pit_number))

            row = cursor.fetchone()
            if not row:
                return applicable

            venue_code, course, rank, motor_rate = row

            # 各ルールをチェック
            for rule in self.load_rules():
                if self._check_rule_conditions(rule.conditions, {
                    'venue_code': venue_code,
                    'course': course,
                    'racer_rank': rank,
                    'motor_second_rate': motor_rate
                }):
                    applicable.append(rule)

        return applicable

    def _check_rule_conditions(self, conditions: List[Dict], data: Dict) -> bool:
        """ルール条件をチェック"""
        for cond in conditions:
            field = cond.get('field')
            op = cond.get('op')
            value = cond.get('value')

            if field not in data:
                continue

            actual = data[field]

            if op == 'eq' and actual != value:
                return False
            elif op == 'ne' and actual == value:
                return False
            elif op == 'gt' and actual <= value:
                return False
            elif op == 'lt' and actual >= value:
                return False
            elif op == 'gte' and actual < value:
                return False
            elif op == 'lte' and actual > value:
                return False
            elif op == 'in' and actual not in value:
                return False

        return True

    def discover_all_rules(self):
        """全ルールを発見"""
        print("=" * 70)
        print("Compound Rule Discovery")
        print("=" * 70)

        self.discover_first_place_rules()
        self.discover_second_place_rules()
        self.discover_upset_warning_rules()

        print(f"\nTotal rules discovered: {len(self.discovered_rules)}")

        # 保存
        self.save_rules()

        return self.discovered_rules


if __name__ == "__main__":
    print("=" * 70)
    print("Compound Rule Finder - Build and Test")
    print("=" * 70)

    finder = CompoundRuleFinder()

    # 全ルールを発見
    rules = finder.discover_all_rules()

    # 結果表示
    print("\n" + "=" * 70)
    print("Top 10 Rules by Hit Rate")
    print("=" * 70)

    sorted_rules = sorted(rules, key=lambda x: (-x.hit_rate, -x.total_races))

    for i, rule in enumerate(sorted_rules[:10], 1):
        print(f"\n[{i}] {rule.rule_id}")
        print(f"    Description: {rule.description}")
        print(f"    Hit Rate: {rule.hit_rate*100:.1f}%")
        print(f"    Total Races: {rule.total_races}")
        print(f"    Confidence: {rule.confidence_level}")

    print("\n" + "=" * 70)
    print("Rule Discovery Complete!")
    print("=" * 70)
