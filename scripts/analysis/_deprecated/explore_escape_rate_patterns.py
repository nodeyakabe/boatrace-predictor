# -*- coding: utf-8 -*-
"""
選手逃げ率データを活用した新規法則探索

B×50-100に限定せず、全条件で使える汎用的なパターンを探索
"""

import sqlite3
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def explore_escape_rate_patterns(db_path: str = 'data/boatrace.db'):
    """逃げ率データを使った新規法則を探索"""

    print("=" * 80)
    print("選手逃げ率データを活用した新規法則探索")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ========================================
    # 1. 全予測データを取得（逃げ率付き）
    # ========================================
    print("\n[1] 全予測データを取得中...")

    query = '''
        WITH predictions AS (
            SELECT
                rp.race_id,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
                MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
                MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.racer_number END) as pred_1st_racer,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.confidence END) as confidence
            FROM race_predictions rp
            WHERE rp.prediction_type = 'before'
            GROUP BY rp.race_id
        ),
        race_results AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank = '1' OR rank = 1 THEN pit_number END) as actual_1st,
                MAX(CASE WHEN rank = '2' OR rank = 2 THEN pit_number END) as actual_2nd,
                MAX(CASE WHEN rank = '3' OR rank = 3 THEN pit_number END) as actual_3rd
            FROM results
            WHERE is_invalid = 0
            GROUP BY race_id
        )
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            p.pred_1st,
            p.pred_2nd,
            p.pred_3rd,
            p.pred_1st_racer,
            p.confidence,
            t.odds,
            rr.actual_1st,
            rr.actual_2nd,
            rr.actual_3rd,
            pes.escape_rate,
            pes.races_1course as escape_sample,
            CASE
                WHEN p.pred_1st = rr.actual_1st
                 AND p.pred_2nd = rr.actual_2nd
                 AND p.pred_3rd = rr.actual_3rd
                THEN 1 ELSE 0
            END as is_hit
        FROM races r
        JOIN predictions p ON r.id = p.race_id
        JOIN race_results rr ON r.id = rr.race_id
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = p.pred_1st || '-' || p.pred_2nd || '-' || p.pred_3rd
        LEFT JOIN player_escape_stats pes
            ON p.pred_1st_racer = pes.player_id AND pes.stadium_id IS NULL
        WHERE r.race_date >= '2020-01-01'
          AND rr.actual_1st IS NOT NULL
          AND t.odds IS NOT NULL
    '''

    cursor.execute(query)
    all_races = list(cursor.fetchall())
    print(f"   全レース数: {len(all_races)}")

    # 逃げ率データあり
    races_with_escape = [r for r in all_races if r['escape_rate'] is not None]
    print(f"   逃げ率データあり: {len(races_with_escape)} ({len(races_with_escape)/len(all_races)*100:.1f}%)")

    # 1コース予測のみ
    c1_races = [r for r in all_races if r['pred_1st'] == 1]
    c1_with_escape = [r for r in c1_races if r['escape_rate'] is not None]
    print(f"   1コース予測: {len(c1_races)}件、うち逃げ率あり: {len(c1_with_escape)} ({len(c1_with_escape)/len(c1_races)*100:.1f}%)")

    # ========================================
    # 2. 基本統計: 逃げ率帯別の成績（1コース予測）
    # ========================================
    print("\n" + "=" * 80)
    print("[2] 1コース予測: 逃げ率帯別の成績")
    print("=" * 80)

    def analyze_group(races_list, name=""):
        """グループの成績を分析"""
        if len(races_list) == 0:
            return None
        total = len(races_list)
        hits = sum(1 for r in races_list if r['is_hit'])
        total_odds = sum(r['odds'] for r in races_list if r['odds'])
        avg_odds = total_odds / total if total > 0 else 0
        roi = (hits * avg_odds * 100) / (total * 100) * 100 if total > 0 else 0

        # 年度別
        yearly = defaultdict(lambda: {'total': 0, 'hits': 0, 'odds': 0})
        for r in races_list:
            year = int(r['race_date'][:4])
            yearly[year]['total'] += 1
            yearly[year]['odds'] += r['odds'] if r['odds'] else 0
            if r['is_hit']:
                yearly[year]['hits'] += 1

        profit_years = 0
        for year in range(2020, 2026):
            y = yearly[year]
            if y['total'] > 0:
                y_avg = y['odds'] / y['total']
                y_roi = (y['hits'] * y_avg * 100) / (y['total'] * 100) * 100
                if y_roi >= 100:
                    profit_years += 1

        return {
            'total': total,
            'hits': hits,
            'hit_rate': hits / total * 100 if total > 0 else 0,
            'roi': roi,
            'profit_years': profit_years,
            'yearly': yearly
        }

    print("\n【1コース予測 + 逃げ率帯別成績】")
    print("-" * 90)
    print(f"{'逃げ率帯':<15s} {'件数':>7s} {'的中':>5s} {'的中率':>7s} {'ROI':>8s} {'黒字年':>6s}")
    print("-" * 90)

    # 逃げ率帯の定義
    escape_bins = [
        (0.00, 0.40, "0-40%（低）"),
        (0.40, 0.50, "40-50%"),
        (0.50, 0.60, "50-60%"),
        (0.60, 0.70, "60-70%"),
        (0.70, 0.80, "70-80%"),
        (0.80, 1.01, "80%以上（高）"),
    ]

    for low, high, label in escape_bins:
        subset = [r for r in c1_with_escape if low <= r['escape_rate'] < high]
        result = analyze_group(subset, label)
        if result:
            status = "O" if result['roi'] >= 100 else "X"
            print(f"   {label:<12s} {result['total']:>7d} {result['hits']:>5d} {result['hit_rate']:>6.2f}% {result['roi']:>7.1f}% {status} {result['profit_years']}/6")

    # ========================================
    # 3. 信頼度×逃げ率の組み合わせ
    # ========================================
    print("\n" + "=" * 80)
    print("[3] 信頼度×逃げ率の組み合わせ（1コース予測）")
    print("=" * 80)

    for conf in ['A', 'B', 'C', 'D']:
        conf_races = [r for r in c1_with_escape if r['confidence'] == conf]
        if len(conf_races) == 0:
            continue

        print(f"\n【信頼度{conf}】 全{len(conf_races)}件")
        print("-" * 90)
        print(f"{'逃げ率条件':<20s} {'件数':>7s} {'的中':>5s} {'的中率':>7s} {'ROI':>8s} {'黒字年':>6s}")
        print("-" * 90)

        # ベースライン
        result = analyze_group(conf_races)
        if result:
            print(f"   {'ベースライン':<17s} {result['total']:>7d} {result['hits']:>5d} {result['hit_rate']:>6.2f}% {result['roi']:>7.1f}% {'O' if result['roi']>=100 else 'X'} {result['profit_years']}/6")

        # 逃げ率フィルター
        for thresh in [0.50, 0.55, 0.60, 0.65, 0.70]:
            filtered = [r for r in conf_races if r['escape_rate'] >= thresh]
            result = analyze_group(filtered)
            if result and result['total'] >= 10:
                status = "O" if result['roi'] >= 100 else "X"
                print(f"   逃げ率>={thresh*100:.0f}%       {result['total']:>7d} {result['hits']:>5d} {result['hit_rate']:>6.2f}% {result['roi']:>7.1f}% {status} {result['profit_years']}/6")

    # ========================================
    # 4. オッズ帯×逃げ率の組み合わせ
    # ========================================
    print("\n" + "=" * 80)
    print("[4] オッズ帯×逃げ率の組み合わせ（1コース予測）")
    print("=" * 80)

    odds_ranges = [
        (1, 10, "1-10倍"),
        (10, 20, "10-20倍"),
        (20, 30, "20-30倍"),
        (30, 50, "30-50倍"),
        (50, 100, "50-100倍"),
        (100, 500, "100-500倍"),
    ]

    for odds_min, odds_max, odds_label in odds_ranges:
        odds_races = [r for r in c1_with_escape if odds_min <= r['odds'] < odds_max]
        if len(odds_races) < 50:
            continue

        print(f"\n【オッズ {odds_label}】 全{len(odds_races)}件")
        print("-" * 90)
        print(f"{'逃げ率条件':<20s} {'件数':>7s} {'的中':>5s} {'的中率':>7s} {'ROI':>8s} {'黒字年':>6s}")
        print("-" * 90)

        # ベースライン
        result = analyze_group(odds_races)
        if result:
            print(f"   {'ベースライン':<17s} {result['total']:>7d} {result['hits']:>5d} {result['hit_rate']:>6.2f}% {result['roi']:>7.1f}% {'O' if result['roi']>=100 else 'X'} {result['profit_years']}/6")

        # 高逃げ率
        for thresh in [0.60, 0.65, 0.70]:
            filtered = [r for r in odds_races if r['escape_rate'] >= thresh]
            result = analyze_group(filtered)
            if result and result['total'] >= 10:
                status = "O" if result['roi'] >= 100 else "X"
                print(f"   逃げ率>={thresh*100:.0f}%       {result['total']:>7d} {result['hits']:>5d} {result['hit_rate']:>6.2f}% {result['roi']:>7.1f}% {status} {result['profit_years']}/6")

        # 低逃げ率除外
        for thresh in [0.40, 0.50]:
            filtered = [r for r in odds_races if r['escape_rate'] >= thresh]
            result = analyze_group(filtered)
            if result and result['total'] >= 10:
                status = "O" if result['roi'] >= 100 else "X"
                print(f"   逃げ率>={thresh*100:.0f}%除外   {result['total']:>7d} {result['hits']:>5d} {result['hit_rate']:>6.2f}% {result['roi']:>7.1f}% {status} {result['profit_years']}/6")

    # ========================================
    # 5. 低逃げ率選手を「避ける」パターン
    # ========================================
    print("\n" + "=" * 80)
    print("[5] 低逃げ率選手除外の効果（1コース予測全体）")
    print("=" * 80)

    print("\n【逃げ率<X%を除外した場合の効果】")
    print("-" * 100)
    print(f"{'除外条件':<18s} {'件数':>7s} {'削減':>6s} {'的中':>5s} {'ROI':>8s} {'黒字年':>6s} | {'2020':>6s} {'2021':>6s} {'2022':>6s} {'2023':>6s} {'2024':>6s} {'2025':>6s}")
    print("-" * 100)

    # ベースライン（1コース予測、逃げ率データあり）
    base_result = analyze_group(c1_with_escape)
    yearly_str = ""
    for year in range(2020, 2026):
        y = base_result['yearly'][year]
        if y['total'] > 0:
            y_avg = y['odds'] / y['total']
            y_roi = (y['hits'] * y_avg * 100) / (y['total'] * 100) * 100
            mark = "O" if y_roi >= 100 else "X"
            yearly_str += f"{y_roi:>5.0f}%{mark}"
        else:
            yearly_str += "    - "
    print(f"   {'ベースライン':<15s} {base_result['total']:>7d}    -  {base_result['hits']:>5d} {base_result['roi']:>7.1f}% {'O' if base_result['roi']>=100 else 'X'} {base_result['profit_years']}/6 | {yearly_str}")

    for thresh in [0.30, 0.35, 0.40, 0.45, 0.50]:
        filtered = [r for r in c1_with_escape if r['escape_rate'] >= thresh]
        result = analyze_group(filtered)
        if result:
            reduction = (base_result['total'] - result['total']) / base_result['total'] * 100
            status = "O" if result['roi'] >= 100 else "X"

            yearly_str = ""
            for year in range(2020, 2026):
                y = result['yearly'][year]
                if y['total'] > 0:
                    y_avg = y['odds'] / y['total']
                    y_roi = (y['hits'] * y_avg * 100) / (y['total'] * 100) * 100
                    mark = "O" if y_roi >= 100 else "X"
                    yearly_str += f"{y_roi:>5.0f}%{mark}"
                else:
                    yearly_str += "    - "

            print(f"   逃げ率<{thresh*100:.0f}%除外   {result['total']:>7d} {reduction:>5.1f}% {result['hits']:>5d} {result['roi']:>7.1f}% {status} {result['profit_years']}/6 | {yearly_str}")

    # ========================================
    # 6. 逃げ率極端（高い/低い）の成績比較
    # ========================================
    print("\n" + "=" * 80)
    print("[6] 逃げ率極端ゾーンの成績比較")
    print("=" * 80)

    extreme_zones = [
        (0.00, 0.35, "超低逃げ率（0-35%）"),
        (0.35, 0.50, "低逃げ率（35-50%）"),
        (0.50, 0.65, "中逃げ率（50-65%）"),
        (0.65, 0.80, "高逃げ率（65-80%）"),
        (0.80, 1.01, "超高逃げ率（80%以上）"),
    ]

    print("\n【1コース予測: 逃げ率ゾーン別成績】")
    print("-" * 100)
    print(f"{'ゾーン':<22s} {'件数':>7s} {'的中':>5s} {'的中率':>7s} {'ROI':>8s} {'黒字年':>6s} | {'2020':>6s} {'2021':>6s} {'2022':>6s} {'2023':>6s} {'2024':>6s} {'2025':>6s}")
    print("-" * 100)

    for low, high, label in extreme_zones:
        subset = [r for r in c1_with_escape if low <= r['escape_rate'] < high]
        result = analyze_group(subset)
        if result and result['total'] >= 50:
            status = "O" if result['roi'] >= 100 else "X"

            yearly_str = ""
            for year in range(2020, 2026):
                y = result['yearly'][year]
                if y['total'] > 0:
                    y_avg = y['odds'] / y['total']
                    y_roi = (y['hits'] * y_avg * 100) / (y['total'] * 100) * 100
                    mark = "O" if y_roi >= 100 else "X"
                    yearly_str += f"{y_roi:>5.0f}%{mark}"
                else:
                    yearly_str += "    - "

            print(f"   {label:<19s} {result['total']:>7d} {result['hits']:>5d} {result['hit_rate']:>6.2f}% {result['roi']:>7.1f}% {status} {result['profit_years']}/6 | {yearly_str}")

    # ========================================
    # 7. サマリー
    # ========================================
    print("\n" + "=" * 80)
    print("[7] サマリー・発見した法則")
    print("=" * 80)

    conn.close()


if __name__ == "__main__":
    explore_escape_rate_patterns()
