"""
検証結果の矛盾を調査

前回検証:
- ベースライン: 52.03%
- ポジティブのみ: 55.09% (+3.06pt)
- ネガティブのみ: 38.94% (-13.09pt)
- 全パターン適用: 52.03% (±0.00pt)

今回測定:
- ベースライン: 52.03%
- 旧実装: 51.04% (-0.98pt)
- 新実装: 51.22% (-0.81pt)

疑問:
1. 前回の「全パターン適用」は52.03%だったのに、今回の「旧実装」は51.04%
2. なぜ0.98ptの差があるのか？
3. 新実装も期待ほど改善していない

仮説:
- 前回検証と今回測定でパターン適用方法が異なる
- 特に倍率の計算方法（積算 vs 最高値）
"""

import sqlite3
from collections import defaultdict
from typing import Dict, List, Tuple

BEFORE_PATTERNS_1ST = [
    {
        'name': 'pre1_st1_ex1',
        'multiplier': 1.50,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 1 and ex_rank == 1,
    },
    {
        'name': 'pre1_st1',
        'multiplier': 1.411,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 1 and ex_rank != 1,
    },
    {
        'name': 'pre1_ex1_3_st1_3',
        'multiplier': 1.328,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and ex_rank <= 3 and st_rank <= 3,
    },
    {
        'name': 'pre1_st1_3',
        'multiplier': 1.310,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank <= 3,
    },
    {
        'name': 'pre1_ex1',
        'multiplier': 1.286,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and ex_rank == 1,
    },
    {
        'name': 'pre1_st6',
        'multiplier': 0.53,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 6,
    },
    {
        'name': 'pre1_st5_6',
        'multiplier': 0.80,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank >= 5 and st_rank != 6,
    },
    {
        'name': 'pre1_st4_6',
        'multiplier': 1.0,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank >= 4 and st_rank not in [5, 6],
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

    sorted_by_pre = sorted(race_data, key=lambda x: x['rank_prediction'])
    pre_ranks = {d['pit_number']: i+1 for i, d in enumerate(sorted_by_pre)}

    valid_ex = [d for d in race_data if d['exhibition_time'] is not None]
    sorted_by_ex = sorted(valid_ex, key=lambda x: x['exhibition_time'])
    ex_ranks = {d['pit_number']: i+1 for i, d in enumerate(sorted_by_ex)}

    valid_st = [d for d in race_data if d['st_time'] is not None]
    sorted_by_st = sorted(valid_st, key=lambda x: abs(x['st_time']))
    st_ranks = {d['pit_number']: i+1 for i, d in enumerate(sorted_by_st)}

    for d in race_data:
        pit = d['pit_number']
        ranks[pit] = (
            pre_ranks.get(pit, 99),
            ex_ranks.get(pit, 99),
            st_ranks.get(pit, 99)
        )

    return ranks


def check_1st_patterns(pre_rank: int, ex_rank: int, st_rank: int) -> List[Dict]:
    """1STパターンのみチェック"""
    matched = []
    for pattern in BEFORE_PATTERNS_1ST:
        try:
            if pattern['condition'](pre_rank, ex_rank, st_rank):
                matched.append(pattern)
        except:
            pass
    return matched


def test_multiplier_methods(races: List[List[Dict]]) -> Dict:
    """倍率計算方法を比較"""

    # 方法1: 積算（全パターン掛け算）
    method_product = {'total': 0, 'correct': 0}

    # 方法2: 最高値（最大倍率のみ）
    method_max = {'total': 0, 'correct': 0}

    # 方法3: ポジティブ/ネガティブ分離（前回検証の解釈1）
    method_separation = {'total': 0, 'correct': 0}

    # 統計情報
    pattern_stats = defaultdict(int)
    multiplier_comparison = []

    for race_data in races:
        if len(race_data) < 6:
            continue

        ranks = get_ranks(race_data)

        scores_product = {}
        scores_max = {}
        scores_separation = {}

        for d in race_data:
            pit = d['pit_number']
            base_score = d['total_score']
            pre_rank, ex_rank, st_rank = ranks[pit]

            patterns = check_1st_patterns(pre_rank, ex_rank, st_rank)

            # 方法1: 積算
            multiplier_product = 1.0
            for p in patterns:
                multiplier_product *= p['multiplier']
            scores_product[pit] = base_score * multiplier_product

            # 方法2: 最高値
            if patterns:
                multiplier_max = max(p['multiplier'] for p in patterns)
            else:
                multiplier_max = 1.0
            scores_max[pit] = base_score * multiplier_max

            # 方法3: 分離
            positive = [p for p in patterns if p['multiplier'] >= 1.0]
            negative = [p for p in patterns if p['multiplier'] < 1.0]

            if negative:
                multiplier_separation = max(p['multiplier'] for p in negative)
            elif positive:
                multiplier_separation = max(p['multiplier'] for p in positive)
            else:
                multiplier_separation = 1.0
            scores_separation[pit] = base_score * multiplier_separation

            # PRE1位のパターン統計
            if pre_rank == 1:
                for p in patterns:
                    pattern_stats[p['name']] += 1

                if multiplier_product != multiplier_max:
                    multiplier_comparison.append({
                        'product': multiplier_product,
                        'max': multiplier_max,
                        'separation': multiplier_separation,
                        'patterns': [p['name'] for p in patterns]
                    })

        # 1着予測判定
        actual_1st = [d for d in race_data if d['actual_rank'] == 1]
        if not actual_1st:
            continue

        actual_1st_pit = actual_1st[0]['pit_number']

        # 方法1
        pred_pit_product = max(scores_product.keys(), key=lambda p: scores_product[p])
        method_product['total'] += 1
        if pred_pit_product == actual_1st_pit:
            method_product['correct'] += 1

        # 方法2
        pred_pit_max = max(scores_max.keys(), key=lambda p: scores_max[p])
        method_max['total'] += 1
        if pred_pit_max == actual_1st_pit:
            method_max['correct'] += 1

        # 方法3
        pred_pit_separation = max(scores_separation.keys(), key=lambda p: scores_separation[p])
        method_separation['total'] += 1
        if pred_pit_separation == actual_1st_pit:
            method_separation['correct'] += 1

    # 精度計算
    for method in [method_product, method_max, method_separation]:
        if method['total'] > 0:
            method['accuracy'] = method['correct'] / method['total'] * 100
        else:
            method['accuracy'] = 0.0

    return {
        'product': method_product,
        'max': method_max,
        'separation': method_separation,
        'pattern_stats': dict(pattern_stats),
        'multiplier_comparison': multiplier_comparison,
    }


def main():
    print("=" * 80)
    print("検証結果の矛盾調査")
    print("=" * 80)
    print()

    print("[DATA] 2024年データ読み込み中...")
    races = load_2024_data()
    print(f"   総レース数: {len(races)}")
    print()

    print("=" * 80)
    print("[ANALYSIS] 倍率計算方法の比較")
    print("=" * 80)
    print()

    results = test_multiplier_methods(races)

    baseline_acc = 52.03  # 前回検証のベースライン

    print(f"{'方法':<40} {'レース数':>10} {'的中数':>10} {'精度':>10} {'差分':>10}")
    print("-" * 80)

    methods = [
        ('ベースライン（前回検証）', {'total': results['product']['total'], 'correct': int(results['product']['total'] * 0.5203), 'accuracy': baseline_acc}, 0.0),
        ('方法1: 積算（全パターン掛け算）', results['product'], results['product']['accuracy'] - baseline_acc),
        ('方法2: 最高値（最大倍率のみ）', results['max'], results['max']['accuracy'] - baseline_acc),
        ('方法3: 分離（ネガティブ優先）', results['separation'], results['separation']['accuracy'] - baseline_acc),
    ]

    for label, method, diff in methods:
        diff_str = f"{diff:+.2f}pt" if diff != 0 else "±0.00pt"
        print(f"{label:<40} {method['total']:>10} {method['correct']:>10} "
              f"{method['accuracy']:>9.2f}% {diff_str:>10}")

    # パターン統計
    print()
    print("=" * 80)
    print("[STATS] PRE1位に適用されたパターン統計")
    print("=" * 80)
    print()

    total_pre1_races = results['product']['total']
    for pattern_name, count in sorted(results['pattern_stats'].items(), key=lambda x: x[1], reverse=True):
        ratio = count / total_pre1_races * 100 if total_pre1_races > 0 else 0
        print(f"  {pattern_name:<30} {count:>6}回 ({ratio:>5.1f}%)")

    # 倍率比較サンプル
    print()
    print("=" * 80)
    print("[DETAIL] 倍率計算の違い（最初の10サンプル）")
    print("=" * 80)
    print()

    for i, item in enumerate(results['multiplier_comparison'][:10], 1):
        print(f"サンプル{i}:")
        print(f"  適用パターン: {', '.join(item['patterns'])}")
        print(f"  積算: {item['product']:.3f}")
        print(f"  最高値: {item['max']:.3f}")
        print(f"  分離: {item['separation']:.3f}")
        print()

    # 結論
    print("=" * 80)
    print("[CONCLUSION] 結論")
    print("=" * 80)
    print()

    product_acc = results['product']['accuracy']
    max_acc = results['max']['accuracy']
    separation_acc = results['separation']['accuracy']

    print(f"前回検証の「全パターン適用」は恐らく「最高値方式」だった可能性")
    print(f"  -> 最高値方式: {max_acc:.2f}% (ベースライン比 {max_acc - baseline_acc:+.2f}pt)")
    print()
    print(f"今回測定の「旧実装」は「積算方式」だった")
    print(f"  -> 積算方式: {product_acc:.2f}% (ベースライン比 {product_acc - baseline_acc:+.2f}pt)")
    print()
    print(f"新実装の「分離方式」は:")
    print(f"  -> 分離方式: {separation_acc:.2f}% (ベースライン比 {separation_acc - baseline_acc:+.2f}pt)")
    print()

    improvement_from_product = separation_acc - product_acc
    improvement_from_max = separation_acc - max_acc

    print(f"改善効果:")
    print(f"  積算方式から分離方式: {improvement_from_product:+.2f}pt")
    print(f"  最高値方式から分離方式: {improvement_from_max:+.2f}pt")
    print()

    print("=" * 80)


if __name__ == '__main__':
    main()
