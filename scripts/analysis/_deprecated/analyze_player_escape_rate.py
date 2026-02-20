# -*- coding: utf-8 -*-
"""
選手逃げ率データの活用方法探索

B×50-100条件で1着予測選手の逃げ率を使ったフィルターの効果を検証
"""

import sqlite3
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def analyze_player_escape_rate(db_path: str = 'data/boatrace.db'):
    """選手逃げ率の活用方法を探索"""

    print("=" * 80)
    print("選手逃げ率データの活用方法探索")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # player_escape_statsの内容を確認
    print("\n[1] 選手逃げ率データの概要")
    print("-" * 50)

    cursor.execute('''
        SELECT
            CASE WHEN stadium_id IS NULL THEN 'national' ELSE 'local' END as scope,
            COUNT(*) as count,
            AVG(escape_rate) as avg_rate,
            MIN(escape_rate) as min_rate,
            MAX(escape_rate) as max_rate,
            AVG(races_1course) as avg_sample
        FROM player_escape_stats
        GROUP BY CASE WHEN stadium_id IS NULL THEN 'national' ELSE 'local' END
    ''')
    for row in cursor.fetchall():
        print(f"   {row['scope']}: {row['count']}件, "
              f"平均逃げ率={row['avg_rate']*100:.1f}%, "
              f"平均サンプル={row['avg_sample']:.0f}回")

    # B×50-100条件のレースを取得（1着予測選手の逃げ率付き）
    print("\n[2] B×50-100条件 + 選手逃げ率データ取得")
    print("-" * 50)

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
            pes_nat.escape_rate as escape_rate_national,
            pes_nat.races_1course as escape_sample_national,
            pes_local.escape_rate as escape_rate_local,
            pes_local.races_1course as escape_sample_local,
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
        LEFT JOIN player_escape_stats pes_nat
            ON p.pred_1st_racer = pes_nat.player_id AND pes_nat.stadium_id IS NULL
        LEFT JOIN player_escape_stats pes_local
            ON p.pred_1st_racer = pes_local.player_id
            AND r.venue_code = pes_local.stadium_id
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

    # 逃げ率データの付与状況
    with_national = sum(1 for r in races if r['escape_rate_national'] is not None)
    with_local = sum(1 for r in races if r['escape_rate_local'] is not None)
    print(f"   全国逃げ率あり: {with_national}件 ({with_national/len(races)*100:.1f}%)")
    print(f"   会場別逃げ率あり: {with_local}件 ({with_local/len(races)*100:.1f}%)")

    # 逃げ率分布を確認
    print("\n[3] 1着予測選手の全国逃げ率分布")
    print("-" * 50)

    escape_rates = [r['escape_rate_national'] for r in races if r['escape_rate_national'] is not None]

    bins = [(0, 0.30), (0.30, 0.40), (0.40, 0.50), (0.50, 0.60), (0.60, 0.70), (0.70, 1.0)]
    for low, high in bins:
        count = sum(1 for er in escape_rates if low <= er < high)
        print(f"   {low*100:.0f}% - {high*100:.0f}%: {count}件 ({count/len(escape_rates)*100:.1f}%)")

    # 逃げ率別の的中率・ROI
    print("\n[4] 全国逃げ率別の成績")
    print("-" * 70)
    print(f"   {'逃げ率帯':<15s} {'件数':>5s} {'的中':>4s} {'的中率':>6s} {'ROI':>7s} {'黒字年':>5s}")
    print("-" * 70)

    thresholds = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]

    for thresh in thresholds:
        filtered = [r for r in races
                   if r['escape_rate_national'] is not None
                   and r['escape_rate_national'] >= thresh]

        if len(filtered) == 0:
            continue

        total = len(filtered)
        hits = sum(1 for r in filtered if r['is_hit'])
        total_odds = sum(r['odds'] for r in filtered)
        avg_odds = total_odds / total
        roi = (hits * avg_odds * 100) / (total * 100) * 100
        hit_rate = hits / total * 100

        # 年度別黒字年カウント
        yearly = defaultdict(lambda: {'total': 0, 'hits': 0, 'odds': 0})
        for r in filtered:
            year = int(r['race_date'][:4])
            yearly[year]['total'] += 1
            yearly[year]['odds'] += r['odds']
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

        mark = "[O]" if roi >= 100 else "[X]"
        print(f"   >= {thresh*100:.0f}%        {total:>5d} {hits:>4d} {hit_rate:>5.1f}% {roi:>6.1f}% {mark}  {profit_years}/6")

    # 既存の差し率条件と組み合わせ
    print("\n" + "=" * 80)
    print("[5] 差し率>=16%との組み合わせ効果")
    print("=" * 80)

    # ベースライン（差し率>=16%のみ）
    base_filtered = [r for r in races
                    if r['sashi_rate'] is not None and r['sashi_rate'] >= 0.16]
    base_total = len(base_filtered)
    base_hits = sum(1 for r in base_filtered if r['is_hit'])
    base_odds = sum(r['odds'] for r in base_filtered)
    base_avg = base_odds / base_total if base_total > 0 else 0
    base_roi = (base_hits * base_avg * 100) / (base_total * 100) * 100 if base_total > 0 else 0

    print(f"\n   ベースライン（差し率>=16%のみ）: {base_total}件, {base_hits}的中, ROI {base_roi:.1f}%")

    print("\n   【差し率>=16% + 全国逃げ率フィルター】")
    print("-" * 80)
    print(f"   {'逃げ率条件':<18s} {'件数':>5s} {'的中':>4s} {'ROI':>7s} {'ROI変化':>8s} {'黒字年':>5s} | {'2020':>5s} {'2021':>5s} {'2022':>5s} {'2023':>5s} {'2024':>5s} {'2025':>5s}")
    print("-" * 80)

    for thresh in [0.35, 0.40, 0.45, 0.50, 0.55]:
        filtered = [r for r in races
                   if r['sashi_rate'] is not None and r['sashi_rate'] >= 0.16
                   and r['escape_rate_national'] is not None
                   and r['escape_rate_national'] >= thresh]

        if len(filtered) == 0:
            continue

        total = len(filtered)
        hits = sum(1 for r in filtered if r['is_hit'])
        total_odds = sum(r['odds'] for r in filtered)
        avg_odds = total_odds / total
        roi = (hits * avg_odds * 100) / (total * 100) * 100

        # 年度別
        yearly = defaultdict(lambda: {'total': 0, 'hits': 0, 'odds': 0})
        for r in filtered:
            year = int(r['race_date'][:4])
            yearly[year]['total'] += 1
            yearly[year]['odds'] += r['odds']
            if r['is_hit']:
                yearly[year]['hits'] += 1

        profit_years = 0
        yearly_str = ""
        for year in range(2020, 2026):
            y = yearly[year]
            if y['total'] > 0:
                y_avg = y['odds'] / y['total']
                y_roi = (y['hits'] * y_avg * 100) / (y['total'] * 100) * 100
                mark = "O" if y_roi >= 100 else "X"
                yearly_str += f"{y_roi:>4.0f}%{mark}"
                if y_roi >= 100:
                    profit_years += 1
            else:
                yearly_str += "   - "

        diff = roi - base_roi
        diff_str = f"{diff:+.1f}pt"
        print(f"   >= {thresh*100:.0f}%            {total:>5d} {hits:>4d} {roi:>6.1f}% {diff_str:>8s}  {profit_years}/6  | {yearly_str}")

    # 逆に低逃げ率を除外するパターン
    print("\n   【差し率>=16% + 低逃げ率除外】")
    print("-" * 80)

    for thresh in [0.30, 0.35, 0.40]:
        # 逃げ率<thresh を除外（逃げ率データなしは許可）
        filtered = [r for r in races
                   if r['sashi_rate'] is not None and r['sashi_rate'] >= 0.16
                   and (r['escape_rate_national'] is None
                        or r['escape_rate_national'] >= thresh)]

        total = len(filtered)
        hits = sum(1 for r in filtered if r['is_hit'])
        total_odds = sum(r['odds'] for r in filtered)
        avg_odds = total_odds / total if total > 0 else 0
        roi = (hits * avg_odds * 100) / (total * 100) * 100 if total > 0 else 0

        # 年度別
        yearly = defaultdict(lambda: {'total': 0, 'hits': 0, 'odds': 0})
        for r in filtered:
            year = int(r['race_date'][:4])
            yearly[year]['total'] += 1
            yearly[year]['odds'] += r['odds']
            if r['is_hit']:
                yearly[year]['hits'] += 1

        profit_years = 0
        yearly_str = ""
        for year in range(2020, 2026):
            y = yearly[year]
            if y['total'] > 0:
                y_avg = y['odds'] / y['total']
                y_roi = (y['hits'] * y_avg * 100) / (y['total'] * 100) * 100
                mark = "O" if y_roi >= 100 else "X"
                yearly_str += f"{y_roi:>4.0f}%{mark}"
                if y_roi >= 100:
                    profit_years += 1
            else:
                yearly_str += "   - "

        diff = roi - base_roi
        print(f"   除外< {thresh*100:.0f}%         {total:>5d} {hits:>4d} {roi:>6.1f}% {diff:+6.1f}pt  {profit_years}/6  | {yearly_str}")

    # 1着予測が1コースの場合のみ逃げ率を使う
    print("\n" + "=" * 80)
    print("[6] 1コース予測時のみ逃げ率フィルター適用")
    print("=" * 80)

    # 1コース予測のみ
    course1_races = [r for r in races if r['pred_1st'] == 1]
    other_course_races = [r for r in races if r['pred_1st'] != 1]

    print(f"\n   1コース予測: {len(course1_races)}件")
    print(f"   他コース予測: {len(other_course_races)}件")

    # 1コース予測で逃げ率>=50%
    print("\n   【1コース予測 + 逃げ率フィルター】（差し率>=16%併用）")
    print("-" * 80)

    for thresh in [0.45, 0.50, 0.55, 0.60]:
        # 1コース予測: 差し率>=16% AND 逃げ率>=thresh
        # 他コース予測: 差し率>=16%のみ
        filtered_c1 = [r for r in course1_races
                      if r['sashi_rate'] is not None and r['sashi_rate'] >= 0.16
                      and r['escape_rate_national'] is not None
                      and r['escape_rate_national'] >= thresh]
        filtered_other = [r for r in other_course_races
                         if r['sashi_rate'] is not None and r['sashi_rate'] >= 0.16]

        filtered = filtered_c1 + filtered_other

        total = len(filtered)
        hits = sum(1 for r in filtered if r['is_hit'])
        total_odds = sum(r['odds'] for r in filtered)
        avg_odds = total_odds / total if total > 0 else 0
        roi = (hits * avg_odds * 100) / (total * 100) * 100 if total > 0 else 0

        # 年度別
        yearly = defaultdict(lambda: {'total': 0, 'hits': 0, 'odds': 0})
        for r in filtered:
            year = int(r['race_date'][:4])
            yearly[year]['total'] += 1
            yearly[year]['odds'] += r['odds']
            if r['is_hit']:
                yearly[year]['hits'] += 1

        profit_years = 0
        yearly_str = ""
        for year in range(2020, 2026):
            y = yearly[year]
            if y['total'] > 0:
                y_avg = y['odds'] / y['total']
                y_roi = (y['hits'] * y_avg * 100) / (y['total'] * 100) * 100
                mark = "O" if y_roi >= 100 else "X"
                yearly_str += f"{y_roi:>4.0f}%{mark}"
                if y_roi >= 100:
                    profit_years += 1
            else:
                yearly_str += "   - "

        diff = roi - base_roi
        c1_count = len(filtered_c1)
        print(f"   1コース逃げ率>={thresh*100:.0f}% {total:>5d}件(1C:{c1_count:>3d}) {hits:>3d}的中 ROI{roi:>6.1f}% {diff:+6.1f}pt {profit_years}/6 | {yearly_str}")

    # サマリー
    print("\n" + "=" * 80)
    print("[7] サマリー・推奨条件")
    print("=" * 80)

    conn.close()


if __name__ == "__main__":
    analyze_player_escape_rate()
