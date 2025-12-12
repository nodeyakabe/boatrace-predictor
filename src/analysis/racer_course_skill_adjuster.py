"""
選手のコース別得意・不得意による補正スコア計算

過去3年分のデータ（2023-2025）に基づく選手×コース別の得意・不得意を考慮
"""
import os
import json
from typing import Optional

# 選手×コース別得意・不得意テーブルの読み込み
_SKILL_TABLE = None


def _load_skill_table():
    """選手×コース別得意・不得意テーブルを読み込み"""
    global _SKILL_TABLE

    if _SKILL_TABLE is not None:
        return _SKILL_TABLE

    # テーブルファイルのパス
    current_dir = os.path.dirname(os.path.abspath(__file__))
    table_path = os.path.join(current_dir, 'racer_course_skill_table.json')

    try:
        with open(table_path, 'r', encoding='utf-8') as f:
            _SKILL_TABLE = json.load(f)
        return _SKILL_TABLE
    except FileNotFoundError:
        # テーブルが見つからない場合は空の辞書を返す
        _SKILL_TABLE = {}
        return _SKILL_TABLE


def calculate_racer_course_skill_adjustment(
    racer_number: str,
    course: int
) -> float:
    """
    選手のコース別得意・不得意による補正スコアを計算

    過去3年分のデータ（2023-2025）に基づく:
    - サンプル数20レース以上
    - 差分±10pt以上のケースのみテーブル化
    - 808選手、1,187件のパターン

    Args:
        racer_number: 選手番号（文字列）
        course: コース番号(1-6)

    Returns:
        補正スコア（-5.0 ~ +5.0点）
    """
    skill_table = _load_skill_table()

    # 選手番号を文字列に変換
    racer_number_str = str(racer_number)

    # テーブルに選手が存在しない場合は0
    if racer_number_str not in skill_table:
        return 0.0

    racer_skills = skill_table[racer_number_str]

    # コース番号を文字列に変換してチェック
    course_str = str(course)

    # 選手×コースの組み合わせがテーブルにない場合は0
    if course_str not in racer_skills:
        return 0.0

    # 差分を取得（±10pt以上の場合のみテーブルに存在）
    diff_pt = racer_skills[course_str]

    # 補正スコアに変換
    # 実データの差分（±10pt ~ ±50pt）を±5点のスコアに変換
    # 差分が大きいほど補正も大きくするが、上限を設ける

    if abs(diff_pt) >= 30.0:
        # 大幅な得意・不得意（±30pt以上）: ±5.0点
        score = 5.0 if diff_pt > 0 else -5.0
    elif abs(diff_pt) >= 20.0:
        # 明確な得意・不得意（±20pt以上）: ±3.5点
        score = 3.5 if diff_pt > 0 else -3.5
    elif abs(diff_pt) >= 15.0:
        # やや得意・不得意（±15pt以上）: ±2.0点
        score = 2.0 if diff_pt > 0 else -2.0
    else:
        # 最小レベルの得意・不得意（±10pt以上）: ±1.0点
        score = 1.0 if diff_pt > 0 else -1.0

    # スコア範囲を制限（-5.0 ~ +5.0点）
    return min(max(score, -5.0), 5.0)


if __name__ == "__main__":
    # テスト
    print("=" * 80)
    print("選手×コース別得意・不得意補正スコアのテスト")
    print("=" * 80)

    # テーブルを読み込み
    skill_table = _load_skill_table()

    print(f"\nテーブル読み込み: {len(skill_table):,}選手")

    # テストケース（実際のデータから）
    test_cases = [
        # (選手番号, コース, 期待される効果)
        ('4747', 1, "大幅苦手（-53.3pt → -5.0点）"),
        ('4908', 1, "大幅得意（+34.8pt → +5.0点）"),
        ('4826', 1, "大幅得意（+30.6pt → +5.0点）"),
        ('4571', 4, "大幅得意（+35.6pt → +5.0点）"),
        ('3212', 1, "大幅苦手（-43.8pt → -5.0点）"),
        ('4571', 2, "大幅得意（+32.7pt → +5.0点）"),
        ('9999', 1, "テーブルにない選手（0点）"),
        ('4747', 2, "テーブルにないコース（0点）"),
    ]

    print("\nテストケース:")
    print(f"{'選手':<10} {'コース':<8} {'補正スコア':<12} {'説明':<40}")
    print("-" * 80)

    for racer_number, course, expected in test_cases:
        score = calculate_racer_course_skill_adjustment(racer_number, course)
        print(f"{racer_number:<10} {course}コース   {score:+6.1f}点     {expected}")

    # 統計情報
    print("\n" + "=" * 80)
    print("テーブル統計")
    print("=" * 80)

    total_patterns = sum(len(skills) for skills in skill_table.values())

    print(f"\n登録選手数: {len(skill_table):,}人")
    print(f"登録パターン数: {total_patterns:,}件")

    # コース別の分布
    course_count = {i: 0 for i in range(1, 7)}
    for racer_skills in skill_table.values():
        for course_str in racer_skills.keys():
            course = int(course_str)
            course_count[course] += 1

    print("\nコース別の登録パターン数:")
    for course in sorted(course_count.keys()):
        print(f"  {course}コース: {course_count[course]:,}件")
