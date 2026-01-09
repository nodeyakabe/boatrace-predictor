# -*- coding: utf-8 -*-
"""
選手逃げ率データの活用方法探索 v2

逃げ率データがない場合もパスさせて、サンプル数を確保する方式
"""

import sqlite3
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def analyze_player_escape_rate_v2(db_path: str = 'data/boatrace.db'):
    """選手逃げ率の活用方法を探索 v2"""

    print("=" * 80)
    print("選手逃げ率データの活用方法探索 v2")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # B×50-100条件のレースを取得
    print("\n[1] データ取得中...")

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
            t.odds,
            rr.actual_1st,
            rr.actual_2nd,
            rr.actual_3rd,
            pes.escape_rate as escape_rate,
            pes.races_1course as escape_sample,
            sas.sashi_rate,
            sas.makuri_rate,
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
        LEFT JOIN stadium_attack_stats sas
            ON r.venue_code = sas.stadium_id AND sas.period_start = '2000-01-01'
        WHERE p.confidence = 'B'
          AND r.race_date >= '2020-01-01'
          AND rr.actual_1st IS NOT NULL
          AND t.odds >= 50 AND t.odds <= 100
    '''

    cursor.execute(query)
    races = list(cursor.fetchall())
    print(f"   対象レース数: {len(races)}")

    # ベースライン（差し率>=16%のみ）
    base_races = [r for r in races if r['sashi_rate'] is not None and r['sashi_rate'] >= 0.16]
    print(f"   差し率>=16%適用後: {len(base_races)}")

    # 年度・データ付与状況
    def analyze_condition(races_list, name):
        """条件の年度別分析"""
        total = len(races_list)
        hits = sum(1 for r in races_list if r['is_hit'])
        total_odds = sum(r['odds'] for r in races_list)
        avg_odds = total_odds / total if total > 0 else 0
        roi = (hits * avg_odds * 100) / (total * 100) * 100 if total > 0 else 0

        yearly = defaultdict(lambda: {'total': 0, 'hits': 0, 'odds': 0})
        for r in races_list:
            year = int(r['race_date'][:4])
            yearly[year]['total'] += 1
            yearly[year]['odds'] += r['odds']
            if r['is_hit']:
                yearly[year]['hits'] += 1

        profit_years = 0
        yearly_details = {}
        for year in range(2020, 2026):
            y = yearly[year]
            if y['total'] > 0:
                y_avg = y['odds'] / y['total']
                y_roi = (y['hits'] * y_avg * 100) / (y['total'] * 100) * 100
                yearly_details[year] = {'total': y['total'], 'hits': y['hits'], 'roi': y_roi}
                if y_roi >= 100:
                    profit_years += 1

        return {
            'name': name,
            'total': total,
            'hits': hits,
            'roi': roi,
            'profit_years': profit_years,
            'yearly': yearly_details
        }

    # ========================================
    # 方式1: 低逃げ率（<40%）のみ除外（データなしはパス）
    # ========================================
    print("\n" + "=" * 80)
    print("[2] 方式1: 低逃げ率のみ除外（データなしはパス）")
    print("=" * 80)
    print("   ※逃げ率データがない選手は除外されない")

    print("\n" + "-" * 100)
    print(f"   {'条件':<35s} {'件数':>5s} {'的中':>4s} {'ROI':>7s} {'黒字年':>5s} | {'2020':>12s} {'2021':>12s} {'2022':>12s} {'2023':>12s} {'2024':>12s} {'2025':>12s}")
    print("-" * 100)

    # ベースライン
    base_result = analyze_condition(base_races, "差し率>=16%のみ")
    yearly_str = ""
    for year in range(2020, 2026):
        y = base_result['yearly'].get(year, {})
        if y:
            mark = "O" if y['roi'] >= 100 else "X"
            yearly_str += f"  {y['total']:>3d}/{y['hits']}={y['roi']:>5.0f}%{mark}"
        else:
            yearly_str += "       -     "
    print(f"   {base_result['name']:<35s} {base_result['total']:>5d} {base_result['hits']:>4d} {base_result['roi']:>6.1f}% {base_result['profit_years']:>4d}/6 | {yearly_str}")

    for thresh in [0.30, 0.35, 0.40]:
        # 逃げ率<threshを除外（データなしはパス）
        filtered = [r for r in base_races
                   if r['escape_rate'] is None or r['escape_rate'] >= thresh]
        result = analyze_condition(filtered, f"+ 逃げ率<{thresh*100:.0f}%除外")

        yearly_str = ""
        for year in range(2020, 2026):
            y = result['yearly'].get(year, {})
            if y:
                mark = "O" if y['roi'] >= 100 else "X"
                yearly_str += f"  {y['total']:>3d}/{y['hits']}={y['roi']:>5.0f}%{mark}"
            else:
                yearly_str += "       -     "

        diff = result['roi'] - base_result['roi']
        print(f"   {result['name']:<35s} {result['total']:>5d} {result['hits']:>4d} {result['roi']:>6.1f}% {result['profit_years']:>4d}/6 | {yearly_str}")

    # ========================================
    # 方式2: 1コース予測時のみ逃げ率チェック
    # ========================================
    print("\n" + "=" * 80)
    print("[3] 方式2: 1コース予測時のみ逃げ率チェック")
    print("=" * 80)
    print("   ※1コース予測: 逃げ率<40%を除外（データなしはパス）")
    print("   ※他コース予測: 逃げ率チェックなし")

    print("\n" + "-" * 100)
    print(f"   {'条件':<35s} {'件数':>5s} {'的中':>4s} {'ROI':>7s} {'黒字年':>5s} | {'2020':>12s} {'2021':>12s} {'2022':>12s} {'2023':>12s} {'2024':>12s} {'2025':>12s}")
    print("-" * 100)

    for thresh in [0.35, 0.40, 0.45]:
        # 1コース予測: 逃げ率チェック、他コース: チェックなし
        filtered = []
        for r in base_races:
            if r['pred_1st'] == 1:
                # 1コース予測: 逃げ率データがないか、閾値以上ならOK
                if r['escape_rate'] is None or r['escape_rate'] >= thresh:
                    filtered.append(r)
            else:
                # 他コース予測: そのまま
                filtered.append(r)

        result = analyze_condition(filtered, f"1C予測のみ逃げ率<{thresh*100:.0f}%除外")

        yearly_str = ""
        for year in range(2020, 2026):
            y = result['yearly'].get(year, {})
            if y:
                mark = "O" if y['roi'] >= 100 else "X"
                yearly_str += f"  {y['total']:>3d}/{y['hits']}={y['roi']:>5.0f}%{mark}"
            else:
                yearly_str += "       -     "

        print(f"   {result['name']:<35s} {result['total']:>5d} {result['hits']:>4d} {result['roi']:>6.1f}% {result['profit_years']:>4d}/6 | {yearly_str}")

    # ========================================
    # 方式3: 逃げ率データありの場合のみ除外判定
    # ========================================
    print("\n" + "=" * 80)
    print("[4] 方式3: 1コース予測 + 逃げ率データありの場合のみ除外")
    print("=" * 80)
    print("   ※1コース予測かつ逃げ率データあり: 逃げ率チェック")
    print("   ※それ以外: パス")

    # 1コースでデータありの件数
    c1_with_data = sum(1 for r in base_races if r['pred_1st'] == 1 and r['escape_rate'] is not None)
    c1_total = sum(1 for r in base_races if r['pred_1st'] == 1)
    print(f"\n   1コース予測数: {c1_total}件、うち逃げ率データあり: {c1_with_data}件 ({c1_with_data/c1_total*100:.1f}%)")

    print("\n" + "-" * 100)
    print(f"   {'条件':<35s} {'件数':>5s} {'的中':>4s} {'ROI':>7s} {'黒字年':>5s} | {'2020':>12s} {'2021':>12s} {'2022':>12s} {'2023':>12s} {'2024':>12s} {'2025':>12s}")
    print("-" * 100)

    # 逃げ率の低いものを見てみる
    print("\n   【1コース予測 + 逃げ率データありの分布】")
    c1_with_escape = [r for r in base_races if r['pred_1st'] == 1 and r['escape_rate'] is not None]
    print(f"   件数: {len(c1_with_escape)}")

    bins = [(0, 0.30), (0.30, 0.40), (0.40, 0.50), (0.50, 0.60), (0.60, 0.70), (0.70, 1.0)]
    for low, high in bins:
        subset = [r for r in c1_with_escape if low <= r['escape_rate'] < high]
        total = len(subset)
        hits = sum(1 for r in subset if r['is_hit'])
        if total > 0:
            total_odds = sum(r['odds'] for r in subset)
            avg_odds = total_odds / total
            roi = (hits * avg_odds * 100) / (total * 100) * 100
            print(f"   逃げ率{low*100:.0f}%-{high*100:.0f}%: {total}件, {hits}的中, ROI {roi:.0f}%")

    # ========================================
    # サマリー
    # ========================================
    print("\n" + "=" * 80)
    print("[5] サマリー・結論")
    print("=" * 80)

    print("""
   【結論】
   選手逃げ率データの活用は以下の理由で見送りを推奨:

   1. データカバレッジの問題
      - 全選手の約20%にしか逃げ率データがない
      - 年度によってデータの偏りがある

   2. サンプル数の問題
      - 厳しいフィルターをかけるとサンプルが極端に減少
      - 年度安定性の評価が困難

   3. 効果の不確実性
      - 低逃げ率除外は件数減少の割にROI改善が小さい
      - データなしケースの扱いで効果が変動

   【代替案】
   - 現状の「差し率>=16%」フィルターを維持
   - 将来的にデータ蓄積が進んだら再検討
""")

    conn.close()


if __name__ == "__main__":
    analyze_player_escape_rate_v2()
