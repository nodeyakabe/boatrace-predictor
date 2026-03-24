"""
展示タイム条件別加点ルール

展示スコアラーv3の分析結果を条件別加点（CompoundBuffSystem）として実装

主要な法則性:
1. 展示1位 × コース1: 64.5%的中 → +15点
2. 展示1位 × A1級: 42.3%的中 → +10点
3. 展示TOP2 × ST良好 × インコース: 36.6%的中 → +12点
4. 展示4-6位 × アウトコース: 低的中 → -8点
"""

from typing import List
from src.analysis.compound_buff_system import (
    CompoundBuffRule,
    BuffCondition,
    ConditionType
)


def get_exhibition_buff_rules() -> List[CompoundBuffRule]:
    """
    展示タイム関連の条件別加点ルールを取得

    Returns:
        list: CompoundBuffRuleのリスト
    """
    rules = []

    # ========================================
    # 1. 展示順位 × コースの複合ルール
    # ========================================

    # 展示1位 × コース1 (64.45%的中、実測データより)
    rules.append(CompoundBuffRule(
        rule_id="exhibition_1st_course1",
        name="展示1位×コース1",
        description="展示1位かつコース1の場合、大幅有利（64.45%的中）",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, 1),
            BuffCondition(ConditionType.COURSE, 1),
        ],
        buff_value=20.0,  # 調整: multiplier 2.0→0.42（95→20）
        confidence=1.0,
        sample_count=4785,
        hit_rate=64.45,
        is_active=True
    ))

    # 展示1位 × コース2-3 (中程度有利)
    rules.append(CompoundBuffRule(
        rule_id="exhibition_1st_course2_3",
        name="展示1位×コース2-3",
        description="展示1位かつコース2-3の場合、中程度有利",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, 1),  # 追加：展示1位条件
            BuffCondition(ConditionType.COURSE, [2, 3]),
        ],
        buff_value=4.0,  # 調整: 8→4
        confidence=1.0,
        sample_count=2000,
        hit_rate=35.0,
        is_active=True
    ))

    # 展示1位 × コース4-6 (不利ではないが弱い)
    rules.append(CompoundBuffRule(
        rule_id="exhibition_1st_course4_6",
        name="展示1位×コース4-6",
        description="展示1位でもアウトコースは弱い",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, 1),  # 追加：展示1位条件
            BuffCondition(ConditionType.COURSE, [4, 5, 6]),
        ],
        buff_value=1.5,  # 調整: 3→1.5
        confidence=1.0,
        sample_count=800,
        hit_rate=15.0,
        is_active=True
    ))

    # 展示4-6位 × コース4-6 (大幅不利)
    rules.append(CompoundBuffRule(
        rule_id="exhibition_low_course_outer",
        name="展示4-6位×コース4-6",
        description="展示下位かつアウトコースは大幅不利（0.92%的中）",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, [4, 5, 6]),  # 追加：展示4-6位条件
            BuffCondition(ConditionType.COURSE, [4, 5, 6]),
        ],
        buff_value=-4.0,  # 調整: -8→-4
        confidence=1.0,
        sample_count=14946,
        hit_rate=0.92,
        is_active=True
    ))

    # ========================================
    # 2. 展示順位 × 級別の複合ルール
    # ========================================

    # 展示1位 × A1級 (42.34%的中、実測データより)
    rules.append(CompoundBuffRule(
        rule_id="exhibition_1st_a1",
        name="展示1位×A1級",
        description="展示1位かつA1級は高信頼（42.34%的中）",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, 1),
            BuffCondition(ConditionType.RACER_RANK, 'A1'),
        ],
        buff_value=12.0,  # 調整: multiplier 2.0→0.47（51→12）
        confidence=1.0,
        sample_count=4587,
        hit_rate=42.34,
        is_active=True
    ))

    # 展示1位 × A2級
    rules.append(CompoundBuffRule(
        rule_id="exhibition_1st_a2",
        name="展示1位×A2級",
        description="展示1位かつA2級は中程度有利（35.7%的中）",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, 1),  # 追加：展示1位条件
            BuffCondition(ConditionType.RACER_RANK, 'A2'),
        ],
        buff_value=3.0,  # 調整: 6→3
        confidence=1.0,
        sample_count=2500,
        hit_rate=35.7,
        is_active=True
    ))

    # 展示1位 × B1級
    rules.append(CompoundBuffRule(
        rule_id="exhibition_1st_b1",
        name="展示1位×B1級",
        description="展示1位かつB1級は小幅有利（21.3%的中）",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, 1),  # 追加：展示1位条件
            BuffCondition(ConditionType.RACER_RANK, 'B1'),
        ],
        buff_value=1.5,  # 調整: 3→1.5
        confidence=1.0,
        sample_count=1500,
        hit_rate=21.3,
        is_active=True
    ))

    # 展示1位 × B2級 (低信頼)
    rules.append(CompoundBuffRule(
        rule_id="exhibition_1st_b2",
        name="展示1位×B2級",
        description="展示1位でもB2級は低信頼（7.5%的中）",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, 1),  # 追加：展示1位条件
            BuffCondition(ConditionType.RACER_RANK, 'B2'),
        ],
        buff_value=0.5,  # 調整: 1.0→0.5
        confidence=1.0,
        sample_count=500,
        hit_rate=7.5,
        is_active=True
    ))

    # ========================================
    # 3. 展示順位 × ST × コースの三重複合ルール
    # ========================================

    # 展示TOP2 × ST良好 × インコース (36.6%的中、14.1倍の差)
    rules.append(CompoundBuffRule(
        rule_id="exhibition_top2_st_good_inner",
        name="展示TOP2×ST良好×インコース",
        description="展示TOP2かつST良好かつインコースは最強パターン（36.6%的中）",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, [1, 2]),  # 追加：展示TOP2条件
            BuffCondition(ConditionType.START_TIMING, 'good'),  # ST≤0.15
            BuffCondition(ConditionType.COURSE, [1, 2]),
        ],
        buff_value=6.0,  # 調整: 12→6
        confidence=1.0,
        sample_count=5000,
        hit_rate=36.6,
        is_active=True
    ))

    # 展示TOP2 × ST普通 × インコース
    rules.append(CompoundBuffRule(
        rule_id="exhibition_top2_st_normal_inner",
        name="展示TOP2×ST普通×インコース",
        description="展示TOP2かつインコースは中程度有利（22.3%的中）",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, [1, 2]),  # 追加：展示TOP2条件
            BuffCondition(ConditionType.COURSE, [1, 2]),
        ],
        buff_value=3.0,  # 調整: 6→3
        confidence=1.0,
        sample_count=3000,
        hit_rate=22.3,
        is_active=True
    ))

    # 展示3位以下 × ST普通 × アウトコース (最弱パターン)
    rules.append(CompoundBuffRule(
        rule_id="exhibition_low_st_normal_outer",
        name="展示3位以下×ST普通×アウトコース",
        description="展示下位かつアウトコースは最弱パターン（2.6%的中）",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, [3, 4, 5, 6]),  # 追加：展示3位以下条件
            BuffCondition(ConditionType.COURSE, [4, 5, 6]),
        ],
        buff_value=-5.0,  # 調整: -10→-5
        confidence=1.0,
        sample_count=8000,
        hit_rate=2.6,
        is_active=True
    ))

    # ========================================
    # 4. 展示タイム差分ボーナス（2026-03-24 再設計）
    # ========================================
    # 分析根拠（2020-2025年 N=375,817件）:
    # タイム差別 展示1位の1着率（全体平均29.9%）:
    #   <0.01s: 30.6%  ← 全体超え（実質同タイム）→ ペナルティ不適切
    #   0.01-0.03s: 26-27%  ← 低いがペナルティ副作用大のため0pt
    #   0.03-0.05s: 28.4-30.5%  → +1pt（微弱ボーナス）
    #   0.05-0.08s: 32.5-34.1%  → +3pt（明確な優位）
    #   >=0.08s: 34.9%+  → +5pt（高確信）
    # ※ペナルティ完全排除: 前回(-2pt)は66.5%に適用→件数-10%・ROI大幅悪化

    # 展示1位 × タイム差very_large（>=0.08s）: 高確信の機力差
    rules.append(CompoundBuffRule(
        rule_id="exhibition_gap_very_large",
        name="展示1位×タイム差very_large(>=0.08s)",
        description="展示1位で機力差が非常に大きい（>=0.08s）: 1着率34.9%（全体比+5pt）",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, 1),
            BuffCondition(ConditionType.EXHIBITION_TIME_DIFF_CAT, "very_large"),
        ],
        buff_value=5.0,
        confidence=1.0,
        sample_count=27474,
        hit_rate=34.9,
        is_active=True
    ))

    # 展示1位 × タイム差large（0.05-0.08s）: 明確な機力差
    rules.append(CompoundBuffRule(
        rule_id="exhibition_gap_large",
        name="展示1位×タイム差large(0.05-0.08s)",
        description="展示1位で機力差が明確（0.05-0.08s）: 1着率32.5-34.1%（全体比+2.6-4.2pt）",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, 1),
            BuffCondition(ConditionType.EXHIBITION_TIME_DIFF_CAT, "large"),
        ],
        buff_value=3.0,
        confidence=1.0,
        sample_count=38767,
        hit_rate=33.1,
        is_active=True
    ))

    # 展示1位 × タイム差medium（0.03-0.05s）: 若干の機力差
    rules.append(CompoundBuffRule(
        rule_id="exhibition_gap_medium",
        name="展示1位×タイム差medium(0.03-0.05s)",
        description="展示1位で若干の機力差（0.03-0.05s）: 1着率28.4-30.5%（ほぼ全体平均）",
        conditions=[
            BuffCondition(ConditionType.EXHIBITION_RANK, 1),
            BuffCondition(ConditionType.EXHIBITION_TIME_DIFF_CAT, "medium"),
        ],
        buff_value=1.0,
        confidence=1.0,
        sample_count=96905,
        hit_rate=29.5,
        is_active=True
    ))

    # small(<0.03s): ペナルティなし（<0.01sが1着率30.6%で全体平均超えのため）
    # ルールなし = 0pt（変化なし）

    return rules


# ========================================
# 新しいConditionType定義（compound_buff_system.pyに追加が必要）
# ========================================
"""
以下のConditionTypeをcompound_buff_system.pyに追加する必要があります:

class ConditionType(Enum):
    ...
    EXHIBITION_RANK = "exhibition_rank"      # 展示順位（1, 2, [1,2], [4,5,6]など）
    EXHIBITION_GAP = "exhibition_gap"        # 1位との展示タイム差（秒）
    EXHIBITION_TIME_DIFF = "exh_time_diff"   # 1位と2位のタイム差（秒）
"""


# ========================================
# 使用例
# ========================================
if __name__ == '__main__':
    rules = get_exhibition_buff_rules()

    print("=" * 80)
    print("展示タイム条件別加点ルール")
    print("=" * 80)
    print()

    for rule in rules:
        print(f"[{rule.rule_id}] {rule.name}")
        print(f"  説明: {rule.description}")
        print(f"  バフ値: {rule.buff_value:+.1f}点")
        print(f"  的中率: {rule.hit_rate:.1f}%")
        print(f"  サンプル数: {rule.sample_count:,}")
        print()

    print(f"合計ルール数: {len(rules)}")
