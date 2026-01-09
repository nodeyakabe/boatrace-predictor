# -*- coding: utf-8 -*-
"""
選手逃げ率データを活用した新規法則探索 v2

発見された有望パターンの詳細検証
- 50-100倍帯 + 逃げ率>=65%
- 100-500倍帯 + 逃げ率>=65%
"""

import sqlite3
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def explore_escape_rate_patterns_v2(db_path: str = 'data/boatrace.db'):
    """有望パターンの詳細検証"""

    print("=" * 80)
    print("選手逃げ率データ: 有望パターンの詳細検証")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # データ取得
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
          AND p.pred_1st = 1
    '''

    cursor.execute(query)
    all_c1_races = list(cursor.fetchall())
    print(f"\n   1コース予測レース数: {len(all_c1_races)}")

    c1_with_escape = [r for r in all_c1_races if r['escape_rate'] is not None]
    print(f"   逃げ率データあり: {len(c1_with_escape)}")

    def analyze_detailed(races_list, name=""):
        """詳細分析"""
        if len(races_list) == 0:
            return None
        total = len(races_list)
        hits = sum(1 for r in races_list if r['is_hit'])
        total_odds = sum(r['odds'] for r in races_list if r['odds'])
        avg_odds = total_odds / total if total > 0 else 0
        roi = (hits * avg_odds * 100) / (total * 100) * 100 if total > 0 else 0

        yearly = defaultdict(lambda: {'total': 0, 'hits': 0, 'odds': 0})
        for r in races_list:
            year = int(r['race_date'][:4])
            yearly[year]['total'] += 1
            yearly[year]['odds'] += r['odds'] if r['odds'] else 0
            if r['is_hit']:
                yearly[year]['hits'] += 1

        yearly_roi = {}
        profit_years = 0
        for year in range(2020, 2026):
            y = yearly[year]
            if y['total'] > 0:
                y_avg = y['odds'] / y['total']
                y_roi = (y['hits'] * y_avg * 100) / (y['total'] * 100) * 100
                yearly_roi[year] = {'total': y['total'], 'hits': y['hits'], 'roi': y_roi}
                if y_roi >= 100:
                    profit_years += 1
            else:
                yearly_roi[year] = None

        return {
            'total': total,
            'hits': hits,
            'hit_rate': hits / total * 100 if total > 0 else 0,
            'avg_odds': avg_odds,
            'roi': roi,
            'profit_years': profit_years,
            'yearly_roi': yearly_roi
        }

    # ========================================
    # 1. 50-100倍帯 + 逃げ率>=65% の詳細
    # ========================================
    print("\n" + "=" * 80)
    print("[1] 有望パターン: 50-100倍 + 逃げ率>=65%")
    print("=" * 80)

    odds_50_100 = [r for r in c1_with_escape if 50 <= r['odds'] < 100]
    print(f"\n   50-100倍帯（逃げ率あり）: {len(odds_50_100)}件")

    # ベースライン
    base = analyze_detailed(odds_50_100)
    print(f"\n   【ベースライン】")
    print(f"   件数: {base['total']}, 的中: {base['hits']}, 的中率: {base['hit_rate']:.2f}%, ROI: {base['roi']:.1f}%")

    # 逃げ率フィルター詳細
    print("\n   【逃げ率フィルター効果】")
    print("-" * 90)
    print(f"   {'条件':<18s} {'件数':>6s} {'的中':>4s} {'的中率':>7s} {'平均オッズ':>9s} {'ROI':>8s} {'黒字年':>6s}")
    print("-" * 90)

    for thresh in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        filtered = [r for r in odds_50_100 if r['escape_rate'] >= thresh]
        result = analyze_detailed(filtered)
        if result and result['total'] >= 10:
            status = "O" if result['roi'] >= 100 else "X"
            print(f"   逃げ率>={thresh*100:.0f}%     {result['total']:>6d} {result['hits']:>4d} {result['hit_rate']:>6.2f}% {result['avg_odds']:>8.1f}  {result['roi']:>7.1f}% {status} {result['profit_years']}/6")

    # 最有望条件の年度別詳細
    print("\n   【逃げ率>=65%の年度別詳細】")
    print("-" * 80)
    best = [r for r in odds_50_100 if r['escape_rate'] >= 0.65]
    best_result = analyze_detailed(best)
    print(f"   {'年度':<6s} {'件数':>6s} {'的中':>4s} {'平均オッズ':>9s} {'ROI':>8s} {'判定':>4s}")
    print("-" * 80)
    for year in range(2020, 2026):
        y = best_result['yearly_roi'].get(year)
        if y:
            status = "O" if y['roi'] >= 100 else "X"
            # 年度別平均オッズ計算
            year_races = [r for r in best if int(r['race_date'][:4]) == year]
            year_avg_odds = sum(r['odds'] for r in year_races) / len(year_races) if year_races else 0
            print(f"   {year}    {y['total']:>6d} {y['hits']:>4d} {year_avg_odds:>8.1f}  {y['roi']:>7.1f}% {status}")

    # ========================================
    # 2. 100-500倍帯 + 逃げ率>=65% の詳細
    # ========================================
    print("\n" + "=" * 80)
    print("[2] 有望パターン: 100-500倍 + 逃げ率>=65%")
    print("=" * 80)

    odds_100_500 = [r for r in c1_with_escape if 100 <= r['odds'] < 500]
    print(f"\n   100-500倍帯（逃げ率あり）: {len(odds_100_500)}件")

    base = analyze_detailed(odds_100_500)
    print(f"\n   【ベースライン】")
    print(f"   件数: {base['total']}, 的中: {base['hits']}, 的中率: {base['hit_rate']:.2f}%, ROI: {base['roi']:.1f}%")

    print("\n   【逃げ率フィルター効果】")
    print("-" * 90)
    print(f"   {'条件':<18s} {'件数':>6s} {'的中':>4s} {'的中率':>7s} {'平均オッズ':>9s} {'ROI':>8s} {'黒字年':>6s}")
    print("-" * 90)

    for thresh in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        filtered = [r for r in odds_100_500 if r['escape_rate'] >= thresh]
        result = analyze_detailed(filtered)
        if result and result['total'] >= 5:
            status = "O" if result['roi'] >= 100 else "X"
            print(f"   逃げ率>={thresh*100:.0f}%     {result['total']:>6d} {result['hits']:>4d} {result['hit_rate']:>6.2f}% {result['avg_odds']:>8.1f}  {result['roi']:>7.1f}% {status} {result['profit_years']}/6")

    # 年度別詳細
    print("\n   【逃げ率>=65%の年度別詳細】")
    print("-" * 80)
    best = [r for r in odds_100_500 if r['escape_rate'] >= 0.65]
    best_result = analyze_detailed(best)
    if best_result:
        print(f"   {'年度':<6s} {'件数':>6s} {'的中':>4s} {'平均オッズ':>9s} {'ROI':>8s} {'判定':>4s}")
        print("-" * 80)
        for year in range(2020, 2026):
            y = best_result['yearly_roi'].get(year)
            if y:
                status = "O" if y['roi'] >= 100 else "X"
                year_races = [r for r in best if int(r['race_date'][:4]) == year]
                year_avg_odds = sum(r['odds'] for r in year_races) / len(year_races) if year_races else 0
                print(f"   {year}    {y['total']:>6d} {y['hits']:>4d} {year_avg_odds:>8.1f}  {y['roi']:>7.1f}% {status}")

    # ========================================
    # 3. 信頼度別の効果（高オッズ帯）
    # ========================================
    print("\n" + "=" * 80)
    print("[3] 信頼度×逃げ率>=65%（50倍以上）")
    print("=" * 80)

    high_odds = [r for r in c1_with_escape if r['odds'] >= 50]
    print(f"\n   50倍以上（逃げ率あり）: {len(high_odds)}件")

    print("\n   【信頼度別効果】")
    print("-" * 100)
    print(f"   {'信頼度':<8s} {'条件':<15s} {'件数':>6s} {'的中':>4s} {'的中率':>7s} {'ROI':>8s} {'黒字年':>6s} | {'年度別ROI':<50s}")
    print("-" * 100)

    for conf in ['A', 'B', 'C', 'D']:
        conf_races = [r for r in high_odds if r['confidence'] == conf]
        if len(conf_races) < 10:
            continue

        # ベースライン
        base = analyze_detailed(conf_races)
        yearly_str = " ".join([f"{y['roi']:>4.0f}%" if (y := base['yearly_roi'].get(yr)) else "   -" for yr in range(2020, 2026)])
        status = "O" if base['roi'] >= 100 else "X"
        print(f"   {conf:<8s} {'ベースライン':<15s} {base['total']:>6d} {base['hits']:>4d} {base['hit_rate']:>6.2f}% {base['roi']:>7.1f}% {status} {base['profit_years']}/6 | {yearly_str}")

        # 逃げ率>=65%
        filtered = [r for r in conf_races if r['escape_rate'] >= 0.65]
        if len(filtered) >= 5:
            result = analyze_detailed(filtered)
            yearly_str = " ".join([f"{y['roi']:>4.0f}%" if (y := result['yearly_roi'].get(yr)) else "   -" for yr in range(2020, 2026)])
            status = "O" if result['roi'] >= 100 else "X"
            print(f"   {'':<8s} {'逃げ率>=65%':<15s} {result['total']:>6d} {result['hits']:>4d} {result['hit_rate']:>6.2f}% {result['roi']:>7.1f}% {status} {result['profit_years']}/6 | {yearly_str}")

    # ========================================
    # 4. 逃げ率データなしの場合も考慮した全体効果
    # ========================================
    print("\n" + "=" * 80)
    print("[4] 実運用シミュレーション（データなし許容）")
    print("=" * 80)
    print("   ※逃げ率データがない場合は除外しない（パス）")

    # 全1コース予測（50倍以上）
    all_high_odds_c1 = [r for r in all_c1_races if r['odds'] >= 50]
    print(f"\n   50倍以上・1コース予測（全体）: {len(all_high_odds_c1)}件")

    print("\n   【低逃げ率除外（データなしはパス）】")
    print("-" * 100)
    print(f"   {'条件':<25s} {'件数':>7s} {'削減':>6s} {'的中':>4s} {'ROI':>8s} {'黒字年':>6s} | {'2020':>6s} {'2021':>6s} {'2022':>6s} {'2023':>6s} {'2024':>6s} {'2025':>6s}")
    print("-" * 100)

    # ベースライン
    base = analyze_detailed(all_high_odds_c1)
    yearly_str = " ".join([f"{y['roi']:>5.0f}%{'O' if y['roi']>=100 else 'X'}" if (y := base['yearly_roi'].get(yr)) else "    - " for yr in range(2020, 2026)])
    print(f"   {'ベースライン':<25s} {base['total']:>7d}    -  {base['hits']:>4d} {base['roi']:>7.1f}% {'O' if base['roi']>=100 else 'X'} {base['profit_years']}/6 | {yearly_str}")

    for thresh in [0.40, 0.50, 0.60, 0.65]:
        # データなしはパス、データありで閾値未満は除外
        filtered = [r for r in all_high_odds_c1
                   if r['escape_rate'] is None or r['escape_rate'] >= thresh]
        result = analyze_detailed(filtered)
        if result:
            reduction = (base['total'] - result['total']) / base['total'] * 100
            yearly_str = " ".join([f"{y['roi']:>5.0f}%{'O' if y['roi']>=100 else 'X'}" if (y := result['yearly_roi'].get(yr)) else "    - " for yr in range(2020, 2026)])
            status = "O" if result['roi'] >= 100 else "X"
            print(f"   逃げ率<{thresh*100:.0f}%除外（なしOK）  {result['total']:>7d} {reduction:>5.1f}% {result['hits']:>4d} {result['roi']:>7.1f}% {status} {result['profit_years']}/6 | {yearly_str}")

    # ========================================
    # 5. サマリー
    # ========================================
    print("\n" + "=" * 80)
    print("[5] サマリー・結論")
    print("=" * 80)

    print("""
   【発見した有望パターン】

   1. 50-100倍帯 + 1コース予測 + 逃げ率>=65%
      - 件数: 1,221件、的中: 24件、ROI: 129.9%、黒字年: 4/6
      - 効果: ベースライン(96.6%)から+33.3pt改善

   2. 100-500倍帯 + 1コース予測 + 逃げ率>=65%
      - 件数: 347件、的中: 7件、ROI: 324.1%、黒字年: 3/6
      - 効果: ベースライン(133.6%)から+190.5pt改善

   【課題】
   - 逃げ率データのカバレッジが約20%
   - 年度によるバラツキが大きい
   - サンプル数が少ない条件は信頼性低

   【実装検討】
   - 高オッズ帯（50倍以上）で1コース予測の場合
   - 逃げ率データがあり、かつ<50%なら除外
   - 逃げ率データがない場合はパス（除外しない）
""")

    conn.close()


if __name__ == "__main__":
    explore_escape_rate_patterns_v2()
