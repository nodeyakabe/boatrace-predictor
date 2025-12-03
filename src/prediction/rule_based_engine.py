"""
法則ベース予想エンジン

競艇場の法則（venue_rules）と選手の法則（racer_rules）を統合して
予測確率を補正するエンジン
"""

import sqlite3
import numpy as np
from typing import Dict, List, Tuple, Optional
from src.utils.db_connection_pool import get_connection


class RuleBasedEngine:
    """法則ベース予想エンジン"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path

    def get_venue_rules(self, venue_code: str, is_active: int = 1) -> List[Dict]:
        """
        競艇場の法則を取得

        Args:
            venue_code: 競艇場コード（例: '20'）
            is_active: 有効な法則のみ（1）か全て（0）か

        Returns:
            法則のリスト
        """
        conn = get_connection(self.db_path)
        c = conn.cursor()

        query = """
            SELECT
                rule_type,
                condition_type,
                target_pit,
                effect_type,
                effect_value,
                description
            FROM venue_rules
            WHERE (venue_code = ? OR venue_code IS NULL)
              AND is_active = ?
            ORDER BY
                CASE WHEN venue_code IS NULL THEN 1 ELSE 0 END,
                ABS(effect_value) DESC
        """

        c.execute(query, (venue_code, is_active))
        results = c.fetchall()

        c.close()

        rules = []
        for row in results:
            rules.append({
                'rule_type': row[0],
                'condition_type': row[1],
                'target_pit': row[2],
                'effect_type': row[3],
                'effect_value': row[4],
                'description': row[5]
            })

        return rules

    def get_racer_rules(
        self,
        racer_number: str,
        venue_code: Optional[str] = None,
        course_number: Optional[int] = None,
        is_active: int = 1
    ) -> List[Dict]:
        """
        選手の法則を取得

        Args:
            racer_number: 選手登録番号
            venue_code: 競艇場コード（指定すると場限定の法則も取得）
            course_number: コース番号（指定するとコース限定の法則も取得）
            is_active: 有効な法則のみ

        Returns:
            法則のリスト
        """
        conn = get_connection(self.db_path)
        c = conn.cursor()

        # 基本クエリ
        query = """
            SELECT
                rule_type,
                venue_code,
                course_number,
                condition_type,
                effect_type,
                effect_value,
                description
            FROM racer_rules
            WHERE racer_number = ?
              AND is_active = ?
        """

        params = [racer_number, is_active]

        # 競艇場指定がある場合
        if venue_code:
            query += " AND (venue_code IS NULL OR venue_code = ?)"
            params.append(venue_code)

        # コース指定がある場合
        if course_number:
            query += " AND (course_number IS NULL OR course_number = ?)"
            params.append(course_number)

        query += " ORDER BY ABS(effect_value) DESC"

        c.execute(query, params)
        results = c.fetchall()

        c.close()

        rules = []
        for row in results:
            rules.append({
                'rule_type': row[0],
                'venue_code': row[1],
                'course_number': row[2],
                'condition_type': row[3],
                'effect_type': row[4],
                'effect_value': row[5],
                'description': row[6]
            })

        return rules

    def apply_rules(
        self,
        base_probabilities: Dict[int, float],
        race_info: Dict,
        entries: List[Dict],
        damping_factor: float = 0.7
    ) -> Dict[int, float]:
        """
        法則を適用して予測確率を補正

        Args:
            base_probabilities: 基本予測確率 {pit_number: probability}
            race_info: レース情報 {'venue_code': '20', 'race_date': '2025-10-01', ...}
            entries: 出走情報のリスト [{'pit_number': 1, 'racer_number': '4050', 'actual_course': 1}, ...]
            damping_factor: 法則の効果減衰係数（0.0～1.0、デフォルト0.7）

        Returns:
            補正後の予測確率 {pit_number: probability}
        """
        venue_code = race_info.get('venue_code')

        # 競艇場の法則を取得
        venue_rules = self.get_venue_rules(venue_code)

        # 補正後の確率を初期化
        adjusted_probs = base_probabilities.copy()

        # 各艇に法則を適用
        for entry in entries:
            pit_number = entry['pit_number']
            racer_number = entry.get('racer_number')
            actual_course = entry.get('actual_course')

            if pit_number not in adjusted_probs:
                continue

            # 基本確率
            prob = adjusted_probs[pit_number]

            # 競艇場法則を適用
            for rule in venue_rules:
                if rule['target_pit'] == pit_number:
                    if rule['effect_type'] == 'win_rate_boost':
                        # 減衰係数を適用
                        prob += rule['effect_value'] * damping_factor
                    elif rule['effect_type'] == 'win_rate_penalty':
                        prob += rule['effect_value'] * damping_factor

            # 選手法則を適用
            if racer_number:
                racer_rules = self.get_racer_rules(
                    racer_number,
                    venue_code=venue_code,
                    course_number=actual_course
                )

                for rule in racer_rules:
                    # 得意場の法則
                    if rule['rule_type'] == 'venue_strong':
                        if rule['venue_code'] == venue_code:
                            prob += rule['effect_value'] * damping_factor

                    # 得意コースの法則
                    elif rule['rule_type'] == 'course_strong':
                        if rule['course_number'] == actual_course:
                            prob += rule['effect_value'] * damping_factor

                    # STの法則
                    elif rule['rule_type'] == 'st_fast':
                        # ST展示データがあれば適用（将来実装）
                        prob += rule['effect_value'] * damping_factor * 0.5  # STは控えめに

            # 確率を0～1の範囲に制限
            adjusted_probs[pit_number] = max(0.01, min(0.99, prob))

        # 確率を正規化（合計を1.0に）
        total = sum(adjusted_probs.values())
        if total > 0:
            normalized_probs = {k: v / total for k, v in adjusted_probs.items()}
        else:
            normalized_probs = adjusted_probs

        return normalized_probs

    def get_applied_rules(
        self,
        race_info: Dict,
        entries: List[Dict]
    ) -> List[Dict]:
        """
        適用される法則を取得（説明用）

        Args:
            race_info: レース情報（wind_directionを含むことを推奨）
            entries: 出走情報（racer_rank, genderを含む必要あり）

        Returns:
            適用される法則のリスト
        """
        venue_code = race_info.get('venue_code')
        wind_direction = race_info.get('wind_direction', '')  # 現在の風向
        applied_rules = []

        # エントリーから艇番→選手ランクのマッピングを作成
        pit_to_rank = {}
        pit_to_gender = {}
        for entry in entries:
            pit = entry.get('pit_number')
            rank = entry.get('racer_rank', '')
            gender = entry.get('gender', '')
            pit_to_rank[pit] = rank
            pit_to_gender[pit] = gender

        # 風向の正規化マッピング
        wind_direction_map = {
            '北': '北', '南': '南', '東': '東', '西': '西',
            '北東': '北東', '北西': '北西', '南東': '南東', '南西': '南西',
            '東北東': '北東', '東南東': '南東', '西北西': '北西', '西南西': '南西',
            '北北東': '北東', '北北西': '北西', '南南東': '南東', '南南西': '南西',
        }

        # 競艇場法則
        venue_rules = self.get_venue_rules(venue_code)
        for rule in venue_rules:
            description = rule['description']
            target_pit = rule['target_pit']
            condition_type = rule.get('condition_type', 'general')

            # === 選手ランク系法則のチェック ===
            rank_prefixes = ['A1選手', 'A2選手', 'B1選手', 'B2選手']
            is_rank_rule = any(prefix in description for prefix in rank_prefixes)

            if is_rank_rule:
                entry_rank = pit_to_rank.get(target_pit, '')
                rule_rank = None
                for prefix in rank_prefixes:
                    if prefix in description:
                        rule_rank = prefix.replace('選手', '')
                        break
                if not (rule_rank and entry_rank == rule_rank):
                    continue  # ランク不一致ならスキップ

            # === 女子法則のチェック ===
            if '女子' in description:
                entry_gender = pit_to_gender.get(target_pit, '')
                if entry_gender != '女':
                    continue  # 女子選手でなければスキップ

            # === 風向系法則のチェック ===
            if condition_type == 'wind':
                # descriptionから風向を抽出（例: 「南風_1号艇」→「南」、「福岡_北西風_1号艇」→「北西」）
                wind_keywords = ['北北東風', '北北西風', '南南東風', '南南西風',
                                 '東北東風', '東南東風', '西北西風', '西南西風',
                                 '北東風', '北西風', '南東風', '南西風',
                                 '北風', '南風', '東風', '西風']
                rule_wind = None
                for keyword in wind_keywords:
                    if keyword in description:
                        rule_wind = keyword.replace('風', '')
                        break

                if rule_wind:
                    # 現在の風向と法則の風向を比較
                    current_wind_normalized = wind_direction_map.get(wind_direction, wind_direction)
                    if current_wind_normalized != rule_wind:
                        continue  # 風向不一致ならスキップ

            # すべてのチェックをパスした法則を追加
            applied_rules.append({
                'type': '競艇場法則',
                'description': rule['description'],
                'effect_value': rule['effect_value'],
                'target_pit': rule['target_pit']
            })

        # 選手法則
        for entry in entries:
            racer_number = entry.get('racer_number')
            racer_name = entry.get('racer_name', '不明')
            actual_course = entry.get('actual_course')
            pit_number = entry['pit_number']

            if racer_number:
                racer_rules = self.get_racer_rules(
                    racer_number,
                    venue_code=venue_code,
                    course_number=actual_course
                )

                for rule in racer_rules:
                    applied_rules.append({
                        'type': '選手法則',
                        'description': f"{racer_name}({pit_number}号艇): {rule['description']}",
                        'effect_value': rule['effect_value'],
                        'target_pit': pit_number
                    })

        # 効果の大きい順にソート
        applied_rules.sort(key=lambda x: abs(x['effect_value']), reverse=True)

        return applied_rules


if __name__ == "__main__":
    # テスト実行
    engine = RuleBasedEngine()

    # テストケース: 若松競艇場で田口節子が大村で1コース
    race_info = {
        'venue_code': '20',  # 若松
        'race_date': '2025-10-01'
    }

    entries = [
        {'pit_number': 1, 'racer_number': '4050', 'racer_name': '田口節子', 'actual_course': 1},
        {'pit_number': 2, 'racer_number': '4530', 'racer_name': '小野生奈', 'actual_course': 2},
        {'pit_number': 3, 'racer_number': '3257', 'racer_name': '田頭実', 'actual_course': 3},
        {'pit_number': 4, 'racer_number': '4238', 'racer_name': '毒島誠', 'actual_course': 4},
        {'pit_number': 5, 'racer_number': '4544', 'racer_name': '松田大志郎', 'actual_course': 5},
        {'pit_number': 6, 'racer_number': '5257', 'racer_name': '西丸侑太朗', 'actual_course': 6},
    ]

    # 基本予測（仮）
    base_probs = {
        1: 0.50,  # 1コース
        2: 0.18,  # 2コース
        3: 0.12,  # 3コース
        4: 0.10,  # 4コース
        5: 0.07,  # 5コース
        6: 0.03,  # 6コース
    }

    print("=" * 80)
    print("法則ベース予想エンジン テスト")
    print("=" * 80)
    print()

    print("【基本予測】")
    for pit, prob in base_probs.items():
        print(f"  {pit}号艇: {prob*100:5.1f}%")
    print()

    # 法則適用
    adjusted_probs = engine.apply_rules(base_probs, race_info, entries)

    print("【法則適用後】")
    for pit, prob in adjusted_probs.items():
        diff = (prob - base_probs[pit]) * 100
        print(f"  {pit}号艇: {prob*100:5.1f}% ({diff:+.1f}%)")
    print()

    # 適用された法則
    applied_rules = engine.get_applied_rules(race_info, entries)
    print("【適用された法則】")
    for i, rule in enumerate(applied_rules[:10], 1):
        print(f"  {i}. {rule['description']} ({rule['effect_value']:+.2f})")
    print()

    print("=" * 80)
