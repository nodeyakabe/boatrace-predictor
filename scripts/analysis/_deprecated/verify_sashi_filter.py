# -*- coding: utf-8 -*-
"""
差し率フィルター実装効果の検証

B×50-100条件で差し率>=16%フィルターの効果を確認
"""

import sqlite3
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def verify_filter(db_path: str = 'data/boatrace.db'):
    """フィルター効果を検証"""

    print("=" * 80)
    print("差し率フィルター実装効果の検証")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 会場別差し率を取得
    cursor.execute('''
        SELECT stadium_id, sashi_rate
        FROM stadium_attack_stats
        WHERE period_start = '2000-01-01'
    ''')
    sashi_rates = {row['stadium_id']: row['sashi_rate'] for row in cursor.fetchall()}

    print("\n[1] 会場別差し率")
    print("-" * 50)

    # 差し率16%以上の会場
    high_sashi = [(k, v) for k, v in sashi_rates.items() if v >= 0.16]
    low_sashi = [(k, v) for k, v in sashi_rates.items() if v < 0.16]

    print(f"   差し率>=16%の会場: {len(high_sashi)}会場")
    print(f"   差し率<16%の会場: {len(low_sashi)}会場")

    # 会場名を取得
    cursor.execute('SELECT venue_code, venue_name FROM venue_data')
    venue_names = {row['venue_code']: row['venue_name'] for row in cursor.fetchall()}

    print("\n   【差し率<16%の会場（除外対象）】")
    for vc, sr in sorted(low_sashi, key=lambda x: x[1]):
        name = venue_names.get(vc, vc)
        print(f"     {name}: {sr*100:.1f}%")

    print("\n   【差し率>=16%の会場（購入対象）】")
    for vc, sr in sorted(high_sashi, key=lambda x: -x[1])[:10]:
        name = venue_names.get(vc, vc)
        print(f"     {name}: {sr*100:.1f}%")

    # B×50-100条件のレースを取得
    print("\n[2] B×50-100条件の効果検証")
    print("-" * 50)

    query = '''
        WITH predictions AS (
            SELECT
                rp.race_id,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
                MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
                MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd,
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
            t.odds,
            rr.actual_1st,
            rr.actual_2nd,
            rr.actual_3rd,
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
        WHERE p.confidence = 'B'
          AND r.race_date >= '2020-01-01'
          AND rr.actual_1st IS NOT NULL
          AND t.odds >= 50 AND t.odds <= 100
    '''

    cursor.execute(query)
    races = cursor.fetchall()

    # フィルターなし
    total_all = len(races)
    hits_all = sum(1 for r in races if r['is_hit'])
    odds_all = sum(r['odds'] for r in races)
    roi_all = (hits_all * (odds_all / total_all) * 100) / (total_all * 100) * 100 if total_all > 0 else 0

    # 差し率>=16%フィルター
    filtered = [r for r in races if sashi_rates.get(r['venue_code'], 0) >= 0.16]
    total_filtered = len(filtered)
    hits_filtered = sum(1 for r in filtered if r['is_hit'])
    odds_filtered = sum(r['odds'] for r in filtered)
    roi_filtered = (hits_filtered * (odds_filtered / total_filtered) * 100) / (total_filtered * 100) * 100 if total_filtered > 0 else 0

    print(f"\n   【フィルターなし】")
    print(f"   件数: {total_all}, 的中: {hits_all}, ROI: {roi_all:.1f}%")

    print(f"\n   【差し率>=16%フィルター後】")
    print(f"   件数: {total_filtered}, 的中: {hits_filtered}, ROI: {roi_filtered:.1f}%")
    print(f"   削減率: {(total_all - total_filtered) / total_all * 100:.1f}%")
    print(f"   ROI変化: {roi_filtered - roi_all:+.1f}pt")

    # 年度別比較
    print("\n[3] 年度別比較")
    print("-" * 70)
    print(f"{'年度':<6s} {'フィルターなし':>20s} {'差し率>=16%':>20s} {'差分':>10s}")
    print("-" * 70)

    for year in range(2020, 2026):
        year_start = f'{year}-01-01'
        year_end = f'{year}-12-31'

        # フィルターなし
        year_all = [r for r in races if year_start <= r['race_date'] <= year_end]
        t_all = len(year_all)
        h_all = sum(1 for r in year_all if r['is_hit'])
        o_all = sum(r['odds'] for r in year_all)
        r_all = (h_all * (o_all / t_all) * 100) / (t_all * 100) * 100 if t_all > 0 else 0

        # フィルター後
        year_flt = [r for r in filtered if year_start <= r['race_date'] <= year_end]
        t_flt = len(year_flt)
        h_flt = sum(1 for r in year_flt if r['is_hit'])
        o_flt = sum(r['odds'] for r in year_flt)
        r_flt = (h_flt * (o_flt / t_flt) * 100) / (t_flt * 100) * 100 if t_flt > 0 else 0

        diff = r_flt - r_all
        mark_all = "[O]" if r_all >= 100 else "[X]"
        mark_flt = "[O]" if r_flt >= 100 else "[X]"

        print(f"  {year}   {t_all:>4d}件 {h_all:>2d}的中 ROI{r_all:>5.0f}%{mark_all}   {t_flt:>4d}件 {h_flt:>2d}的中 ROI{r_flt:>5.0f}%{mark_flt}   {diff:>+.0f}pt")

    conn.close()


if __name__ == "__main__":
    verify_filter()
