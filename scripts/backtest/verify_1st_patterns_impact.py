"""
BEFORE_PATTERNS_1ST（1着用パターン）の効果検証

目的: ベースライン差-1.31ptの原因が1着用パターンにあるか検証する

検証項目:
1. 各1着用パターンの個別効果
2. ポジティブパターンのみ適用時の精度
3. ネガティブパターンのみ適用時の精度
4. 全パターンなし vs 全パターンあり
"""

import sqlite3
from collections import defaultdict
from typing import Dict, List, Tuple

# ==================================================
# パターン定義（pattern_scorer.pyから抽出）
# ==================================================

BEFORE_PATTERNS_1ST = [
    {
        'name': 'pre1_st1_ex1',
        'description': 'PRE1位 & ST1位 & 展示1位（最強複合）',
        'multiplier': 1.50,
        'target_rank': 1,
        'is_positive': True,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 1 and ex_rank == 1,
    },
    {
        'name': 'pre1_st1',
        'description': 'PRE1位 & ST1位',
        'multiplier': 1.411,
        'target_rank': 1,
        'is_positive': True,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 1 and ex_rank != 1,
    },
    {
        'name': 'pre1_st6',
        'description': 'PRE1位 & ST6位（大幅ペナルティ）',
        'multiplier': 0.53,
        'target_rank': 1,
        'is_positive': False,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 6,
    },
    {
        'name': 'pre1_st5_6',
        'description': 'PRE1位 & ST5-6位（ペナルティ緩和）',
        'multiplier': 0.80,
        'target_rank': 1,
        'is_positive': False,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank >= 5 and st_rank != 6,
    },
    {
        'name': 'pre1_st4_6',
        'description': 'PRE1位 & ST4-6位（無効化）',
        'multiplier': 1.0,
        'target_rank': 1,
        'is_positive': False,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank >= 4 and st_rank not in [5, 6],
    },
    {
        'name': 'pre1_ex1',
        'description': 'PRE1位 & 展示1位',
        'multiplier': 1.286,
        'target_rank': 1,
        'is_positive': True,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and ex_rank == 1,
    },
    {
        'name': 'pre1_ex1_3_st1_3',
        'description': 'PRE1位 & 展示1-3位 & ST1-3位',
        'multiplier': 1.328,
        'target_rank': 1,
        'is_positive': True,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and ex_rank <= 3 and st_rank <= 3,
    },
    {
        'name': 'pre1_st1_3',
        'description': 'PRE1位 & ST1-3位',
        'multiplier': 1.310,
        'target_rank': 1,
        'is_positive': True,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank <= 3,
    },
]


def load_2024_data() -> List[Dict]:
    """2024年のBEFORE予測データを読み込む"""
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    query = """
    SELECT
        r.id as race_id,
        r.venue_code,
        r.race_date,
        r.race_number,
        rp.pit_number,
        rp.rank_prediction,
        rp.total_score,
        rd.exhibition_time,
        rd.st_time,
        res.rank as actual_rank
    FROM races r
    INNER JOIN race_predictions rp ON r.id = rp.race_id
    LEFT JOIN race_details rd ON r.id = rd.race_id AND rp.pit_number = rd.pit_number
    LEFT JOIN results res ON r.id = res.race_id AND rp.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
        AND rp.prediction_type = 'before'
        AND res.is_invalid = 0
        AND res.rank IS NOT NULL
    ORDER BY r.race_date, r.venue_code, r.race_number, rp.pit_number
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    # レースごとにグループ化
    races = defaultdict(list)
    for row in rows:
        race_id = row[0]
        # actual_rankをintに変換（SQLiteは文字列で返す可能性がある）
        try:
            actual_rank = int(row[9]) if row[9] is not None else None
        except (ValueError, TypeError):
            actual_rank = None

        if actual_rank is None:
            continue  # actual_rankがNoneの場合はスキップ

        races[race_id].append({
            'race_id': row[0],
            'venue_code': row[1],
            'race_date': row[2],
            'race_number': row[3],
            'pit_number': row[4],
            'rank_prediction': row[5],
            'total_score': row[6],
            'exhibition_time': row[7],
            'st_time': row[8],
            'actual_rank': actual_rank,
        })

    return list(races.values())


def get_ranks(race_data: List[Dict]) -> Dict[int, Tuple[int, int, int]]:
    """各艇のPRE順位、展示順位、ST順位を計算"""
    ranks = {}

    # PRE順位（rank_prediction基準）
    sorted_by_pre = sorted(race_data, key=lambda x: x['rank_prediction'])
    pre_ranks = {d['pit_number']: i+1 for i, d in enumerate(sorted_by_pre)}

    # 展示順位（exhibition_time基準、小さい方が良い）
    valid_ex = [d for d in race_data if d['exhibition_time'] is not None]
    sorted_by_ex = sorted(valid_ex, key=lambda x: x['exhibition_time'])
    ex_ranks = {d['pit_number']: i+1 for i, d in enumerate(sorted_by_ex)}

    # ST順位（st_time基準、0に近い方が良い）
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


def check_pattern_match(pre_rank: int, ex_rank: int, st_rank: int, pattern: Dict) -> bool:
    """パターンにマッチするか判定"""
    try:
        return pattern['condition'](pre_rank, ex_rank, st_rank)
    except:
        return False


def analyze_pattern_impact(races: List[List[Dict]], patterns: List[Dict]) -> Dict:
    """各パターンの個別効果を分析"""
    results = {}

    for pattern in patterns:
        matched_total = 0
        matched_correct = 0

        for race_data in races:
            ranks = get_ranks(race_data)

            # PRE1位を予測した艇を取得
            pre1_data = [d for d in race_data if d['rank_prediction'] == 1]
            if not pre1_data:
                continue

            pre1 = pre1_data[0]
            pit = pre1['pit_number']
            pre_rank, ex_rank, st_rank = ranks[pit]

            # パターンマッチ判定
            if check_pattern_match(pre_rank, ex_rank, st_rank, pattern):
                matched_total += 1
                if pre1['actual_rank'] == 1:
                    matched_correct += 1

        if matched_total > 0:
            accuracy = matched_correct / matched_total * 100
            results[pattern['name']] = {
                'description': pattern['description'],
                'multiplier': pattern['multiplier'],
                'is_positive': pattern['is_positive'],
                'matched_total': matched_total,
                'matched_correct': matched_correct,
                'accuracy': accuracy,
            }

    return results


def compare_scenarios(races: List[List[Dict]]) -> Dict:
    """複数のシナリオを比較"""
    scenarios = {}

    # シナリオ1: パターンなし（ベースライン）
    baseline_total = 0
    baseline_correct = 0

    # シナリオ2: ポジティブパターンのみ
    positive_total = 0
    positive_correct = 0

    # シナリオ3: ネガティブパターンのみ
    negative_total = 0
    negative_correct = 0

    # シナリオ4: 全パターン
    all_total = 0
    all_correct = 0

    positive_patterns = [p for p in BEFORE_PATTERNS_1ST if p['is_positive']]
    negative_patterns = [p for p in BEFORE_PATTERNS_1ST if not p['is_positive']]

    for race_data in races:
        ranks = get_ranks(race_data)

        # PRE1位を予測した艇を取得
        pre1_data = [d for d in race_data if d['rank_prediction'] == 1]
        if not pre1_data:
            continue

        pre1 = pre1_data[0]
        pit = pre1['pit_number']
        pre_rank, ex_rank, st_rank = ranks[pit]
        actual_rank = pre1['actual_rank']

        # ベースライン（常にカウント）
        baseline_total += 1
        if actual_rank == 1:
            baseline_correct += 1

        # ポジティブパターン該当チェック
        has_positive = any(check_pattern_match(pre_rank, ex_rank, st_rank, p) for p in positive_patterns)
        if has_positive:
            positive_total += 1
            if actual_rank == 1:
                positive_correct += 1

        # ネガティブパターン該当チェック
        has_negative = any(check_pattern_match(pre_rank, ex_rank, st_rank, p) for p in negative_patterns)
        if has_negative:
            negative_total += 1
            if actual_rank == 1:
                negative_correct += 1

        # 全パターン（ポジティブまたはネガティブに該当）
        if has_positive or has_negative:
            all_total += 1
            if actual_rank == 1:
                all_correct += 1

    # 精度計算
    scenarios['baseline'] = {
        'total': baseline_total,
        'correct': baseline_correct,
        'accuracy': baseline_correct / baseline_total * 100 if baseline_total > 0 else 0,
    }
    scenarios['positive_only'] = {
        'total': positive_total,
        'correct': positive_correct,
        'accuracy': positive_correct / positive_total * 100 if positive_total > 0 else 0,
    }
    scenarios['negative_only'] = {
        'total': negative_total,
        'correct': negative_correct,
        'accuracy': negative_correct / negative_total * 100 if negative_total > 0 else 0,
    }
    scenarios['all_patterns'] = {
        'total': all_total,
        'correct': all_correct,
        'accuracy': all_correct / all_total * 100 if all_total > 0 else 0,
    }

    return scenarios


def main():
    print("=" * 80)
    print("BEFORE_PATTERNS_1ST（1着用パターン）効果検証")
    print("=" * 80)
    print()

    # データ読み込み
    print("[DATA] 2024年データ読み込み中...")
    races = load_2024_data()
    print(f"   総レース数: {len(races)}")
    print()

    # 各パターンの個別効果分析
    print("=" * 80)
    print("[ANALYSIS] 各パターンの個別効果")
    print("=" * 80)

    pattern_results = analyze_pattern_impact(races, BEFORE_PATTERNS_1ST)

    # ポジティブパターン
    print("\n[POSITIVE] ポジティブパターン:")
    print("-" * 80)
    print(f"{'パターン名':<25} {'倍率':>7} {'該当数':>7} {'的中数':>7} {'精度':>8}")
    print("-" * 80)

    for name, result in sorted(pattern_results.items(), key=lambda x: x[1]['accuracy'], reverse=True):
        if result['is_positive']:
            print(f"{name:<25} {result['multiplier']:>7.2f} {result['matched_total']:>7} "
                  f"{result['matched_correct']:>7} {result['accuracy']:>7.2f}%")

    # ネガティブパターン
    print("\n[NEGATIVE] ネガティブパターン:")
    print("-" * 80)
    print(f"{'パターン名':<25} {'倍率':>7} {'該当数':>7} {'的中数':>7} {'精度':>8}")
    print("-" * 80)

    for name, result in sorted(pattern_results.items(), key=lambda x: x[1]['accuracy']):
        if not result['is_positive']:
            print(f"{name:<25} {result['multiplier']:>7.2f} {result['matched_total']:>7} "
                  f"{result['matched_correct']:>7} {result['accuracy']:>7.2f}%")

    # シナリオ比較
    print("\n" + "=" * 80)
    print("[SCENARIO] シナリオ比較")
    print("=" * 80)

    scenarios = compare_scenarios(races)

    baseline_acc = scenarios['baseline']['accuracy']

    print(f"\n{'シナリオ':<25} {'レース数':>10} {'的中数':>10} {'精度':>10} {'ベースライン差':>15}")
    print("-" * 80)

    for name, result in scenarios.items():
        diff = result['accuracy'] - baseline_acc
        diff_str = f"{diff:+.2f}pt"

        label = {
            'baseline': 'ベースライン（パターンなし）',
            'positive_only': 'ポジティブパターンのみ',
            'negative_only': 'ネガティブパターンのみ',
            'all_patterns': '全パターン適用',
        }[name]

        print(f"{label:<25} {result['total']:>10} {result['correct']:>10} "
              f"{result['accuracy']:>9.2f}% {diff_str:>15}")

    # 重要な発見のサマリー
    print("\n" + "=" * 80)
    print("[FINDINGS] 重要な発見")
    print("=" * 80)

    positive_diff = scenarios['positive_only']['accuracy'] - baseline_acc
    negative_diff = scenarios['negative_only']['accuracy'] - baseline_acc
    all_diff = scenarios['all_patterns']['accuracy'] - baseline_acc

    print(f"\n1. ポジティブパターンの効果: {positive_diff:+.2f}pt")
    if positive_diff > 0:
        print("   [OK] ポジティブパターンは有効に機能している")
    else:
        print("   [NG] ポジティブパターンは効果なし、または悪影響")

    print(f"\n2. ネガティブパターンの効果: {negative_diff:+.2f}pt")
    if negative_diff < 0:
        print("   [OK] ネガティブパターンは正しくペナルティとして機能している")
    else:
        print("   [NG] ネガティブパターンは誤ブロックを起こしている")

    print(f"\n3. 全パターン適用の効果: {all_diff:+.2f}pt")
    if all_diff > 0:
        print("   [OK] 全体として改善効果あり")
    elif all_diff < -1.0:
        print("   [NG] 全体として悪影響（-1.0pt以上の悪化）")
    else:
        print("   [WARN] 効果は微小（±1.0pt以内）")

    # 結論
    print("\n" + "=" * 80)
    print("[CONCLUSION] 結論")
    print("=" * 80)

    if all_diff < -1.0:
        print("\n[WARN] BEFORE_PATTERNS_1STはベースラインを悪化させています")
        print(f"   悪化幅: {all_diff:.2f}pt")
        print("\n推奨アクション:")
        if positive_diff < 0:
            print("   1. ポジティブパターンの無効化または再設計")
        if negative_diff > 0:
            print("   2. ネガティブパターンの無効化または緩和")
    elif all_diff > 1.0:
        print("\n[OK] BEFORE_PATTERNS_1STは有効に機能しています")
        print(f"   改善幅: {all_diff:.2f}pt")
    else:
        print("\n[WARN] BEFORE_PATTERNS_1STの効果は限定的です")
        print(f"   効果: {all_diff:.2f}pt")
        print("\n追加調査が必要な可能性があります")

    print("\n" + "=" * 80)


if __name__ == '__main__':
    main()
