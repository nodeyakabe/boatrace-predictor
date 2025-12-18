"""
修正版pattern_scorer.pyの効果を測定

修正内容:
1. ポジティブ/ネガティブ分離処理（ネガティブ優先）
2. TOP3パターンのPRE1位除外

期待効果:
- 分離処理: +1.5~3.0pt
- TOP3除外: +0.77pt
- 合計: +2.27~3.77pt
"""

import sqlite3
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

# ==================================================
# パターン定義（修正版をシミュレート）
# ==================================================

BEFORE_PATTERNS_1ST = [
    # ポジティブパターン
    {
        'name': 'pre1_st1_ex1',
        'description': 'PRE1位 & ST1位 & 展示1位',
        'multiplier': 1.50,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 1 and ex_rank == 1,
    },
    {
        'name': 'pre1_st1',
        'description': 'PRE1位 & ST1位',
        'multiplier': 1.411,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 1 and ex_rank != 1,
    },
    {
        'name': 'pre1_ex1_3_st1_3',
        'description': 'PRE1位 & 展示1-3位 & ST1-3位',
        'multiplier': 1.328,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and ex_rank <= 3 and st_rank <= 3,
    },
    {
        'name': 'pre1_st1_3',
        'description': 'PRE1位 & ST1-3位',
        'multiplier': 1.310,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank <= 3,
    },
    {
        'name': 'pre1_ex1',
        'description': 'PRE1位 & 展示1位',
        'multiplier': 1.286,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and ex_rank == 1,
    },
    # ネガティブパターン
    {
        'name': 'pre1_st6',
        'description': 'PRE1位 & ST6位',
        'multiplier': 0.53,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 6,
    },
    {
        'name': 'pre1_st5_6',
        'description': 'PRE1位 & ST5-6位',
        'multiplier': 0.80,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank >= 5 and st_rank != 6,
    },
    {
        'name': 'pre1_st4_6',
        'description': 'PRE1位 & ST4-6位',
        'multiplier': 1.0,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank >= 4 and st_rank not in [5, 6],
    },
]

BEFORE_PATTERNS_TOP3 = [
    {
        'name': 'st1_2_ex1_2_double_top',
        'description': 'ST1-2位 & 展示1-2位',
        'multiplier': 1.193,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: st_rank <= 2 and ex_rank <= 2,
    },
    {
        'name': 'pre1_3_st1',
        'description': 'PRE1-3位 & ST1位',
        'multiplier': 1.23,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 3 and st_rank == 1,
    },
    {
        'name': 'st5_6_ex5_6_double_bottom',
        'description': 'ST5-6位 & 展示5-6位',
        'multiplier': 0.60,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: st_rank >= 5 and ex_rank >= 5,
    },
    {
        'name': 'pre1_3_st1_3',
        'description': 'PRE1-3位 & ST1-3位',
        'multiplier': 1.130,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 3 and st_rank <= 3 and st_rank != 1,
    },
    {
        'name': 'pre1_3_ex1_3',
        'description': 'PRE1-3位 & 展示1-3位',
        'multiplier': 1.123,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 3 and ex_rank <= 3,
    },
    {
        'name': 'ex1_3_st1_3',
        'description': '展示1-3位 & ST1-3位',
        'multiplier': 1.108,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: ex_rank <= 3 and st_rank <= 3,
    },
    {
        'name': 'pre1_4_ex1_2',
        'description': 'PRE1-4位 & 展示1-2位',
        'multiplier': 1.0,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 4 and ex_rank <= 2,
    },
    {
        'name': 'ex_rank_1_2',
        'description': '展示1-2位',
        'multiplier': 1.0,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: ex_rank <= 2,
    },
]


def load_2024_data() -> List[List[Dict]]:
    """2024年のBEFORE予測データを読み込む"""
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    query = """
    SELECT
        r.id as race_id,
        rp.pit_number,
        rp.rank_prediction,
        rp.total_score,
        rd.exhibition_time,
        rd.st_time,
        res.rank as actual_rank
    FROM races r
    INNER JOIN race_predictions rp ON r.id = rp.race_id
    LEFT JOIN race_details rd ON rd.race_id = r.id AND rd.pit_number = rp.pit_number
    LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = rp.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
        AND rp.prediction_type = 'before'
        AND res.is_invalid = 0
        AND res.rank IS NOT NULL
    ORDER BY r.id, rp.pit_number
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    # レースごとにグループ化
    races = defaultdict(list)
    for row in rows:
        race_id = row[0]
        try:
            actual_rank = int(row[6])
        except (ValueError, TypeError):
            continue

        races[race_id].append({
            'race_id': row[0],
            'pit_number': row[1],
            'rank_prediction': row[2],
            'total_score': row[3],
            'exhibition_time': row[4],
            'st_time': row[5],
            'actual_rank': actual_rank,
        })

    return list(races.values())


def get_ranks(race_data: List[Dict]) -> Dict[int, Tuple[int, int, int]]:
    """各艇のPRE順位、展示順位、ST順位を計算"""
    ranks = {}

    # PRE順位
    sorted_by_pre = sorted(race_data, key=lambda x: x['rank_prediction'])
    pre_ranks = {d['pit_number']: i+1 for i, d in enumerate(sorted_by_pre)}

    # 展示順位
    valid_ex = [d for d in race_data if d['exhibition_time'] is not None]
    sorted_by_ex = sorted(valid_ex, key=lambda x: x['exhibition_time'])
    ex_ranks = {d['pit_number']: i+1 for i, d in enumerate(sorted_by_ex)}

    # ST順位
    valid_st = [d for d in race_data if d['st_time'] is not None]
    sorted_by_st = sorted(valid_st, key=lambda x: abs(x['st_time']))
    st_ranks = {d['pit_number']: i+1 for i, d in enumerate(sorted_by_st)}

    # 統合
    for d in race_data:
        pit = d['pit_number']
        ranks[pit] = (
            pre_ranks.get(pit, 99),
            ex_ranks.get(pit, 99),
            st_ranks.get(pit, 99)
        )

    return ranks


def check_patterns_old(pre_rank: int, ex_rank: int, st_rank: int) -> List[Dict]:
    """旧実装: 全パターンを返す（積算方式）"""
    matched = []

    # 1STパターン
    for pattern in BEFORE_PATTERNS_1ST:
        try:
            if pattern['condition'](pre_rank, ex_rank, st_rank):
                matched.append(pattern)
        except:
            pass

    # TOP3パターン（PRE1位にも適用）
    for pattern in BEFORE_PATTERNS_TOP3:
        try:
            if pattern['condition'](pre_rank, ex_rank, st_rank):
                matched.append(pattern)
        except:
            pass

    return matched


def check_patterns_new(pre_rank: int, ex_rank: int, st_rank: int) -> List[Dict]:
    """新実装: ポジティブ/ネガティブ分離 + TOP3除外"""
    matched_positive = []
    matched_negative = []

    # 1STパターン（ポジティブ/ネガティブ分離）
    for pattern in BEFORE_PATTERNS_1ST:
        try:
            if pattern['condition'](pre_rank, ex_rank, st_rank):
                if pattern['multiplier'] < 1.0:
                    matched_negative.append(pattern)
                else:
                    matched_positive.append(pattern)
        except:
            pass

    # TOP3パターン（PRE1位には適用しない）
    if pre_rank != 1:
        for pattern in BEFORE_PATTERNS_TOP3:
            try:
                if pattern['condition'](pre_rank, ex_rank, st_rank):
                    if pattern['multiplier'] < 1.0:
                        matched_negative.append(pattern)
                    else:
                        matched_positive.append(pattern)
            except:
                pass

    # ネガティブ優先
    if matched_negative:
        return matched_negative
    else:
        return matched_positive


def calculate_multiplier_old(patterns: List[Dict]) -> float:
    """旧実装: 積算方式"""
    multiplier = 1.0
    for pattern in patterns:
        multiplier *= pattern['multiplier']
    return multiplier


def calculate_multiplier_new(patterns: List[Dict]) -> float:
    """新実装: 最高倍率を採用"""
    if not patterns:
        return 1.0
    return max(p['multiplier'] for p in patterns)


def compare_implementations(races: List[List[Dict]]) -> Dict:
    """旧実装と新実装を比較"""

    # ベースライン（パターンなし）
    baseline = {'total': 0, 'correct': 0}

    # 旧実装（積算 + TOP3全艇適用）
    old_impl = {'total': 0, 'correct': 0}

    # 新実装（分離 + TOP3除外）
    new_impl = {'total': 0, 'correct': 0}

    for race_data in races:
        if len(race_data) < 6:
            continue

        ranks = get_ranks(race_data)

        # 各艇のスコアを計算
        scores_baseline = {}
        scores_old = {}
        scores_new = {}

        for d in race_data:
            pit = d['pit_number']
            base_score = d['total_score']
            pre_rank, ex_rank, st_rank = ranks[pit]

            # ベースライン
            scores_baseline[pit] = base_score

            # 旧実装
            patterns_old = check_patterns_old(pre_rank, ex_rank, st_rank)
            multiplier_old = calculate_multiplier_old(patterns_old)
            scores_old[pit] = base_score * multiplier_old

            # 新実装
            patterns_new = check_patterns_new(pre_rank, ex_rank, st_rank)
            multiplier_new = calculate_multiplier_new(patterns_new)
            scores_new[pit] = base_score * multiplier_new

        # 各実装での1着予測を判定
        actual_1st = [d for d in race_data if d['actual_rank'] == 1]
        if not actual_1st:
            continue

        actual_1st_pit = actual_1st[0]['pit_number']

        # ベースライン
        pred_pit_baseline = max(scores_baseline.keys(), key=lambda p: scores_baseline[p])
        baseline['total'] += 1
        if pred_pit_baseline == actual_1st_pit:
            baseline['correct'] += 1

        # 旧実装
        pred_pit_old = max(scores_old.keys(), key=lambda p: scores_old[p])
        old_impl['total'] += 1
        if pred_pit_old == actual_1st_pit:
            old_impl['correct'] += 1

        # 新実装
        pred_pit_new = max(scores_new.keys(), key=lambda p: scores_new[p])
        new_impl['total'] += 1
        if pred_pit_new == actual_1st_pit:
            new_impl['correct'] += 1

    # 精度計算
    for impl in [baseline, old_impl, new_impl]:
        if impl['total'] > 0:
            impl['accuracy'] = impl['correct'] / impl['total'] * 100
        else:
            impl['accuracy'] = 0.0

    return {
        'baseline': baseline,
        'old': old_impl,
        'new': new_impl,
    }


def main():
    print("=" * 80)
    print("修正版pattern_scorer.pyの効果測定")
    print("=" * 80)
    print()

    # データ読み込み
    print("[DATA] 2024年データ読み込み中...")
    races = load_2024_data()
    print(f"   総レース数: {len(races)}")
    print()

    # 比較実施
    print("=" * 80)
    print("[ANALYSIS] 実装比較")
    print("=" * 80)
    print()

    results = compare_implementations(races)

    baseline_acc = results['baseline']['accuracy']
    old_acc = results['old']['accuracy']
    new_acc = results['new']['accuracy']

    print(f"{'実装':<40} {'レース数':>10} {'的中数':>10} {'精度':>10} {'差分':>10}")
    print("-" * 80)

    implementations = [
        ('ベースライン（パターンなし）', results['baseline'], 0.0),
        ('旧実装（積算 + TOP3全艇適用）', results['old'], old_acc - baseline_acc),
        ('新実装（分離 + TOP3除外）', results['new'], new_acc - baseline_acc),
    ]

    for label, impl, diff in implementations:
        diff_str = f"{diff:+.2f}pt" if diff != 0 else "±0.00pt"
        print(f"{label:<40} {impl['total']:>10} {impl['correct']:>10} "
              f"{impl['accuracy']:>9.2f}% {diff_str:>10}")

    # 改善効果
    improvement = new_acc - old_acc

    print()
    print("=" * 80)
    print("[CONCLUSION] 結論")
    print("=" * 80)
    print()

    print(f"旧実装: {old_acc:.2f}% (ベースライン比 {old_acc - baseline_acc:+.2f}pt)")
    print(f"新実装: {new_acc:.2f}% (ベースライン比 {new_acc - baseline_acc:+.2f}pt)")
    print(f"改善効果: {improvement:+.2f}pt")
    print()

    if improvement >= 2.0:
        print("[SUCCESS] 期待通り大幅改善（+2.0pt以上）")
        print("   -> 本番適用を推奨します")
    elif improvement >= 1.0:
        print("[GOOD] 良好な改善（+1.0pt以上）")
        print("   -> 本番適用を推奨します")
    elif improvement >= 0.5:
        print("[OK] わずかな改善（+0.5pt以上）")
        print("   -> 本番適用を検討してください")
    elif improvement >= 0.0:
        print("[NEUTRAL] 効果は微小（+0.5pt未満）")
        print("   -> 追加検証が必要です")
    else:
        print("[WARNING] 逆効果です")
        print("   -> 実装を見直してください")

    print()
    print("=" * 80)


if __name__ == '__main__':
    main()
