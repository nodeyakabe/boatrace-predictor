"""
BEFORE_PATTERNS_TOP3が1着予測に与える影響を検証

仮説: TOP3パターンがPRE1位に適用されることで、
      他の艇との相対的なスコア差が縮小し、
      1着予測精度が低下している可能性がある

検証方法:
1. TOP3パターンをPRE1位に適用した場合の精度
2. TOP3パターンをPRE1位に適用しない場合の精度
3. 差分を計算
"""

import sqlite3
from collections import defaultdict
from typing import Dict, List, Tuple

# ==================================================
# パターン定義
# ==================================================

BEFORE_PATTERNS_TOP3 = [
    {
        'name': 'st1_2_ex1_2_double_top',
        'description': 'ST1-2位 & 展示1-2位（両方上位）',
        'multiplier': 1.193,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: st_rank <= 2 and ex_rank <= 2,
    },
    {
        'name': 'pre1_3_st1',
        'description': 'PRE1-3位 & ST1位（強力）',
        'multiplier': 1.23,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 3 and st_rank == 1,
    },
    {
        'name': 'st5_6_ex5_6_double_bottom',
        'description': 'ST5-6位 & 展示5-6位（両方下位、大幅ペナルティ）',
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
        'multiplier': 1.0,  # 無効化済み
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 4 and ex_rank <= 2,
    },
    {
        'name': 'ex_rank_1_2',
        'description': '展示1-2位',
        'multiplier': 1.0,  # 無効化済み
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


def check_top3_patterns(pre_rank: int, ex_rank: int, st_rank: int) -> List[Dict]:
    """TOP3パターンにマッチするか判定"""
    matched = []
    for pattern in BEFORE_PATTERNS_TOP3:
        try:
            if pattern['condition'](pre_rank, ex_rank, st_rank):
                matched.append(pattern)
        except:
            pass
    return matched


def calculate_multiplier(patterns: List[Dict]) -> float:
    """複数パターンの倍率を計算（積算）"""
    multiplier = 1.0
    for pattern in patterns:
        multiplier *= pattern['multiplier']
    return multiplier


def compare_scenarios(races: List[List[Dict]]) -> Dict:
    """TOP3パターンを適用した場合としない場合を比較"""

    # シナリオ1: TOP3パターンを全艇に適用（現状）
    scenario_with_top3 = {
        'total': 0,
        'correct': 0,
    }

    # シナリオ2: TOP3パターンをPRE1位には適用しない
    scenario_without_top3_for_pre1 = {
        'total': 0,
        'correct': 0,
    }

    # シナリオ3: TOP3パターンを誰にも適用しない（ベースライン）
    scenario_baseline = {
        'total': 0,
        'correct': 0,
    }

    # 詳細分析用
    pre1_with_top3_pattern_count = 0
    pre1_top3_patterns_detail = defaultdict(int)

    for race_data in races:
        if len(race_data) < 6:
            continue

        ranks = get_ranks(race_data)

        # 各艇のスコアを計算（TOP3パターン適用）
        scores_with_top3 = {}
        scores_without_top3_for_pre1 = {}
        scores_baseline = {}

        for d in race_data:
            pit = d['pit_number']
            base_score = d['total_score']
            pre_rank, ex_rank, st_rank = ranks[pit]

            # TOP3パターンマッチ判定
            top3_patterns = check_top3_patterns(pre_rank, ex_rank, st_rank)
            top3_multiplier = calculate_multiplier(top3_patterns)

            # シナリオ1: 全艇にTOP3適用
            scores_with_top3[pit] = base_score * top3_multiplier

            # シナリオ2: PRE1位以外にTOP3適用
            if pre_rank == 1:
                scores_without_top3_for_pre1[pit] = base_score  # TOP3適用しない
                if top3_patterns:
                    pre1_with_top3_pattern_count += 1
                    for p in top3_patterns:
                        pre1_top3_patterns_detail[p['name']] += 1
            else:
                scores_without_top3_for_pre1[pit] = base_score * top3_multiplier

            # シナリオ3: 誰にもTOP3適用しない
            scores_baseline[pit] = base_score

        # 各シナリオでの1着予測を判定
        # シナリオ1
        pred_pit_with_top3 = max(scores_with_top3.keys(), key=lambda p: scores_with_top3[p])
        actual_1st = [d for d in race_data if d['actual_rank'] == 1]
        if actual_1st:
            scenario_with_top3['total'] += 1
            if pred_pit_with_top3 == actual_1st[0]['pit_number']:
                scenario_with_top3['correct'] += 1

        # シナリオ2
        pred_pit_without_top3_for_pre1 = max(scores_without_top3_for_pre1.keys(), key=lambda p: scores_without_top3_for_pre1[p])
        if actual_1st:
            scenario_without_top3_for_pre1['total'] += 1
            if pred_pit_without_top3_for_pre1 == actual_1st[0]['pit_number']:
                scenario_without_top3_for_pre1['correct'] += 1

        # シナリオ3
        pred_pit_baseline = max(scores_baseline.keys(), key=lambda p: scores_baseline[p])
        if actual_1st:
            scenario_baseline['total'] += 1
            if pred_pit_baseline == actual_1st[0]['pit_number']:
                scenario_baseline['correct'] += 1

    # 精度計算
    for scenario in [scenario_with_top3, scenario_without_top3_for_pre1, scenario_baseline]:
        if scenario['total'] > 0:
            scenario['accuracy'] = scenario['correct'] / scenario['total'] * 100
        else:
            scenario['accuracy'] = 0.0

    return {
        'with_top3': scenario_with_top3,
        'without_top3_for_pre1': scenario_without_top3_for_pre1,
        'baseline': scenario_baseline,
        'pre1_with_top3_pattern_count': pre1_with_top3_pattern_count,
        'pre1_top3_patterns_detail': dict(pre1_top3_patterns_detail),
    }


def main():
    print("=" * 80)
    print("BEFORE_PATTERNS_TOP3が1着予測に与える影響の検証")
    print("=" * 80)
    print()

    # データ読み込み
    print("[DATA] 2024年データ読み込み中...")
    races = load_2024_data()
    print(f"   総レース数: {len(races)}")
    print()

    # シナリオ比較
    print("=" * 80)
    print("[ANALYSIS] シナリオ比較")
    print("=" * 80)

    results = compare_scenarios(races)

    baseline_acc = results['baseline']['accuracy']

    print(f"\n{'シナリオ':<40} {'レース数':>10} {'的中数':>10} {'精度':>10} {'差分':>10}")
    print("-" * 80)

    scenarios = [
        ('ベースライン（TOP3パターンなし）', results['baseline']),
        ('現状（全艇にTOP3適用）', results['with_top3']),
        ('改善案（PRE1位のみTOP3除外）', results['without_top3_for_pre1']),
    ]

    for label, scenario in scenarios:
        diff = scenario['accuracy'] - baseline_acc
        diff_str = f"{diff:+.2f}pt" if diff != 0 else "±0.00pt"
        print(f"{label:<40} {scenario['total']:>10} {scenario['correct']:>10} "
              f"{scenario['accuracy']:>9.2f}% {diff_str:>10}")

    # 詳細分析
    print("\n" + "=" * 80)
    print("[DETAIL] PRE1位へのTOP3パターン適用詳細")
    print("=" * 80)

    total_pre1_races = results['baseline']['total']
    pattern_count = results['pre1_with_top3_pattern_count']
    pattern_ratio = pattern_count / total_pre1_races * 100 if total_pre1_races > 0 else 0

    print(f"\nPRE1位の総レース数: {total_pre1_races}")
    print(f"TOP3パターンに該当したPRE1位: {pattern_count}レース ({pattern_ratio:.1f}%)")
    print()
    print("PRE1位に適用されたTOP3パターンの内訳:")
    print("-" * 80)

    for pattern_name, count in sorted(results['pre1_top3_patterns_detail'].items(), key=lambda x: x[1], reverse=True):
        ratio = count / total_pre1_races * 100 if total_pre1_races > 0 else 0
        print(f"  {pattern_name:<35} {count:>6}回 ({ratio:>5.1f}%)")

    # 結論
    print("\n" + "=" * 80)
    print("[CONCLUSION] 結論")
    print("=" * 80)

    diff_with_top3 = results['with_top3']['accuracy'] - baseline_acc
    diff_without_top3_for_pre1 = results['without_top3_for_pre1']['accuracy'] - baseline_acc

    improvement = diff_without_top3_for_pre1 - diff_with_top3

    print(f"\n1. TOP3パターンを全艇に適用した場合: {diff_with_top3:+.2f}pt")
    print(f"2. PRE1位のみTOP3除外した場合: {diff_without_top3_for_pre1:+.2f}pt")
    print(f"3. 改善効果: {improvement:+.2f}pt")
    print()

    if improvement > 0.5:
        print("[RECOMMEND] PRE1位へのTOP3パターン適用除外を推奨します")
        print(f"   期待される精度改善: {improvement:.2f}pt")
    elif improvement < -0.5:
        print("[NOT RECOMMEND] PRE1位へのTOP3パターン適用除外は逆効果です")
        print(f"   精度悪化: {improvement:.2f}pt")
    else:
        print("[NEUTRAL] PRE1位へのTOP3パターン適用除外の効果は微小です")
        print(f"   効果: {improvement:.2f}pt")

    print("\n" + "=" * 80)


if __name__ == '__main__':
    main()
