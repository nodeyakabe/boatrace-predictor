# -*- coding: utf-8 -*-
"""
指標条件の組み合わせテスト

条件1: 差し率>=16%
条件2: まくり率>=20% & 差し率>=18%

両方を組み合わせた効果を検証
"""

import sqlite3
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def test_combined_conditions(db_path: str = 'data/boatrace.db'):
    """組み合わせ条件をテスト"""

    print("=" * 80)
    print("指標条件の組み合わせテスト")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # データ取得
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
        ),
        bet_races AS (
            SELECT
                r.id as race_id,
                r.venue_code,
                r.race_date,
                p.confidence,
                p.pred_1st,
                p.pred_2nd,
                p.pred_3rd,
                p.pred_1st_racer,
                t.odds,
                rr.actual_1st,
                rr.actual_2nd,
                rr.actual_3rd
            FROM races r
            JOIN predictions p ON r.id = p.race_id
            JOIN race_results rr ON r.id = rr.race_id
            LEFT JOIN trifecta_odds t ON r.id = t.race_id
                AND t.combination = p.pred_1st || '-' || p.pred_2nd || '-' || p.pred_3rd
            WHERE p.confidence = 'B'
              AND r.race_date >= '2020-01-01'
              AND rr.actual_1st IS NOT NULL
        )
        SELECT
            br.*,
            CASE
                WHEN br.pred_1st = br.actual_1st
                 AND br.pred_2nd = br.actual_2nd
                 AND br.pred_3rd = br.actual_3rd
                THEN 1 ELSE 0
            END as is_hit
        FROM bet_races br
        WHERE br.odds >= 50 AND br.odds <= 100
    '''

    cursor.execute(query)
    races = cursor.fetchall()
    print(f"   対象レース数: {len(races)}")

    # 会場別まくり率・差し率を取得
    cursor.execute('''
        SELECT stadium_id, makuri_rate, sashi_rate
        FROM stadium_attack_stats
        WHERE period_start = '2000-01-01'
    ''')
    stadium_stats = {row['stadium_id']: {
        'makuri_rate': row['makuri_rate'],
        'sashi_rate': row['sashi_rate']
    } for row in cursor.fetchall()}

    # 各レースに指標を付与
    enriched_races = []
    for r in races:
        stats = stadium_stats.get(r['venue_code'], {})
        enriched_races.append({
            'race_id': r['race_id'],
            'venue_code': r['venue_code'],
            'race_date': r['race_date'],
            'pred_1st': r['pred_1st'],
            'odds': r['odds'],
            'is_hit': r['is_hit'],
            'makuri_rate': stats.get('makuri_rate'),
            'sashi_rate': stats.get('sashi_rate'),
            'year': int(r['race_date'][:4])
        })

    # ========================================
    # 条件定義
    # ========================================
    def cond_sashi_16(r):
        """差し率>=16%"""
        return r['sashi_rate'] is not None and r['sashi_rate'] >= 0.16

    def cond_makuri_sashi(r):
        """まくり率>=20% & 差し率>=18%"""
        return (r['makuri_rate'] is not None and r['makuri_rate'] >= 0.20 and
                r['sashi_rate'] is not None and r['sashi_rate'] >= 0.18)

    def cond_either(r):
        """どちらかを満たす（OR条件）"""
        return cond_sashi_16(r) or cond_makuri_sashi(r)

    def cond_both(r):
        """両方を満たす（AND条件）"""
        return cond_sashi_16(r) and cond_makuri_sashi(r)

    conditions = [
        ('ベースライン（フィルターなし）', lambda r: True),
        ('差し率>=16%', cond_sashi_16),
        ('まくり率>=20% & 差し率>=18%', cond_makuri_sashi),
        ('OR条件（どちらか満たす）', cond_either),
        ('AND条件（両方満たす）', cond_both),
    ]

    # ========================================
    # 各条件を評価
    # ========================================
    print("\n" + "=" * 80)
    print("[2] 各条件の評価")
    print("=" * 80)

    results = []

    for name, cond_func in conditions:
        filtered = [r for r in enriched_races if cond_func(r)]

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
            yearly[r['year']]['total'] += 1
            yearly[r['year']]['odds'] += r['odds']
            if r['is_hit']:
                yearly[r['year']]['hits'] += 1

        yearly_roi = {}
        profit_years = 0
        for year in range(2020, 2026):
            y = yearly[year]
            if y['total'] > 0:
                y_avg = y['odds'] / y['total']
                y_roi = (y['hits'] * y_avg * 100) / (y['total'] * 100) * 100
                yearly_roi[year] = y_roi
                if y_roi >= 100:
                    profit_years += 1
            else:
                yearly_roi[year] = None

        results.append({
            'name': name,
            'total': total,
            'hits': hits,
            'hit_rate': hits / total * 100,
            'roi': roi,
            'profit_years': profit_years,
            'yearly_roi': yearly_roi,
            'yearly': yearly
        })

    # 結果表示
    print("\n" + "-" * 100)
    print(f"{'条件':<35s} {'件数':>5s} {'的中':>4s} {'ROI':>7s} {'黒字年':>5s} | {'2020':>6s} {'2021':>6s} {'2022':>6s} {'2023':>6s} {'2024':>6s} {'2025':>6s}")
    print("-" * 100)

    for r in results:
        yearly_str = ""
        for year in range(2020, 2026):
            y_roi = r['yearly_roi'].get(year)
            if y_roi is not None:
                mark = "O" if y_roi >= 100 else "X"
                yearly_str += f"{y_roi:>5.0f}%{mark}"
            else:
                yearly_str += "    - "

        print(f"  {r['name']:<33s} {r['total']:>5d} {r['hits']:>4d} {r['roi']:>6.1f}% {r['profit_years']:>4d}/6 | {yearly_str}")

    # ========================================
    # 詳細比較
    # ========================================
    print("\n" + "=" * 80)
    print("[3] ベースラインとの比較")
    print("=" * 80)

    base = results[0]
    print(f"\n   ベースライン: {base['total']}件, {base['hits']}的中, ROI {base['roi']:.1f}%")

    for r in results[1:]:
        diff_roi = r['roi'] - base['roi']
        diff_count = base['total'] - r['total']
        reduction = diff_count / base['total'] * 100

        print(f"\n   【{r['name']}】")
        print(f"   - 件数: {base['total']}件 -> {r['total']}件 ({-reduction:+.1f}%)")
        print(f"   - ROI: {base['roi']:.1f}% -> {r['roi']:.1f}% ({diff_roi:+.1f}pt)")
        print(f"   - 黒字年: {r['profit_years']}/6年")

    # ========================================
    # 推奨条件
    # ========================================
    print("\n" + "=" * 80)
    print("[4] 推奨条件")
    print("=" * 80)

    # OR条件を推奨
    or_result = results[3]  # OR条件
    print(f"""
   【推奨: OR条件（差し率>=16% または まくり率>=20%&差し率>=18%）】

   理由:
   - 件数維持: 591件 -> {or_result['total']}件（-{(591-or_result['total'])/591*100:.0f}%）
   - ROI向上: 184.1% -> {or_result['roi']:.1f}%（+{or_result['roi']-184.1:.1f}pt）
   - 黒字年: {or_result['profit_years']}/6年
   - 3つの率をすべて活用（差し率、まくり率）

   年度別:
""")
    for year in range(2020, 2026):
        y = or_result['yearly'][year]
        y_roi = or_result['yearly_roi'].get(year)
        if y['total'] > 0:
            status = "[O]" if y_roi >= 100 else "[X]"
            print(f"     {year}: {y['total']:>3d}件, {y['hits']}的中, ROI {y_roi:>6.1f}% {status}")

    # ========================================
    # 実装コード例
    # ========================================
    print("\n" + "=" * 80)
    print("[5] 実装コード例")
    print("=" * 80)

    print("""
   # bet_target_evaluator.py への追加例

   def _check_indicator_filter(self, race_id: str, venue_code: str) -> bool:
       '''指標フィルター: 差し率>=16% OR (まくり率>=20% & 差し率>=18%)'''

       # 会場のまくり率・差し率を取得
       stats = self._get_stadium_attack_stats(venue_code)
       if stats is None:
           return True  # データがない場合はパス

       makuri_rate = stats['makuri_rate']
       sashi_rate = stats['sashi_rate']

       # OR条件: どちらかを満たせばOK
       if sashi_rate >= 0.16:
           return True
       if makuri_rate >= 0.20 and sashi_rate >= 0.18:
           return True

       return False
""")

    conn.close()


if __name__ == "__main__":
    test_combined_conditions()
