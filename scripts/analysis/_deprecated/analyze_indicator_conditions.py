# -*- coding: utf-8 -*-
"""
指標データ（逃げ率・まくり率・差し率）を使った条件探索

目的: B信頼度×50-100倍条件で年度安定性のあるフィルター条件を発見
"""

import sqlite3
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def analyze_conditions(db_path: str = 'data/boatrace.db'):
    """指標を使った条件を網羅的に探索"""

    print("=" * 80)
    print("指標データを使った条件探索（年度安定性重視）")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ========================================
    # 1. データ取得
    # ========================================
    print("\n[1] データ取得中...")

    # B×50-100条件のレースを取得
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

    # 選手別逃げ率を取得（全国）
    cursor.execute('''
        SELECT player_id, escape_rate
        FROM player_escape_stats
        WHERE stadium_id IS NULL AND period_start = '2000-01-01'
        AND escape_rate IS NOT NULL
    ''')
    player_escape = {row['player_id']: row['escape_rate'] for row in cursor.fetchall()}

    print(f"   会場まくり率データ: {len(stadium_stats)}件")
    print(f"   選手逃げ率データ: {len(player_escape)}件")

    # ========================================
    # 2. 各レースに指標を付与
    # ========================================
    print("\n[2] 各レースに指標を付与中...")

    enriched_races = []
    for r in races:
        stats = stadium_stats.get(r['venue_code'], {})
        escape_rate = player_escape.get(r['pred_1st_racer'])

        enriched_races.append({
            'race_id': r['race_id'],
            'venue_code': r['venue_code'],
            'race_date': r['race_date'],
            'pred_1st': r['pred_1st'],
            'pred_1st_racer': r['pred_1st_racer'],
            'odds': r['odds'],
            'is_hit': r['is_hit'],
            'makuri_rate': stats.get('makuri_rate'),
            'sashi_rate': stats.get('sashi_rate'),
            'escape_rate': escape_rate,
            'year': int(r['race_date'][:4])
        })

    # ========================================
    # 3. 条件の網羅的探索
    # ========================================
    print("\n[3] 条件の網羅的探索...")

    # 条件定義
    conditions = []

    # まくり率の閾値
    makuri_thresholds = [0.18, 0.20, 0.22, 0.24, 0.26]
    # 差し率の閾値
    sashi_thresholds = [0.16, 0.18, 0.20, 0.22, 0.24]
    # 逃げ率の閾値（1C予測時のみ）
    escape_thresholds = [0.50, 0.55, 0.60, 0.65, 0.70]

    # 単一条件
    for th in makuri_thresholds:
        conditions.append({
            'name': f'makuri<{int(th*100)}%',
            'filter': lambda r, th=th: r['makuri_rate'] is not None and r['makuri_rate'] < th
        })
        conditions.append({
            'name': f'makuri>={int(th*100)}%',
            'filter': lambda r, th=th: r['makuri_rate'] is not None and r['makuri_rate'] >= th
        })

    for th in sashi_thresholds:
        conditions.append({
            'name': f'sashi<{int(th*100)}%',
            'filter': lambda r, th=th: r['sashi_rate'] is not None and r['sashi_rate'] < th
        })
        conditions.append({
            'name': f'sashi>={int(th*100)}%',
            'filter': lambda r, th=th: r['sashi_rate'] is not None and r['sashi_rate'] >= th
        })

    for th in escape_thresholds:
        conditions.append({
            'name': f'1C&escape>={int(th*100)}%',
            'filter': lambda r, th=th: r['pred_1st'] == 1 and r['escape_rate'] is not None and r['escape_rate'] >= th
        })

    # 複合条件: まくり率 + 差し率
    for m_th in [0.20, 0.22, 0.24]:
        for s_th in [0.18, 0.20, 0.22]:
            conditions.append({
                'name': f'makuri<{int(m_th*100)}%&sashi<{int(s_th*100)}%',
                'filter': lambda r, m=m_th, s=s_th: (
                    r['makuri_rate'] is not None and r['makuri_rate'] < m and
                    r['sashi_rate'] is not None and r['sashi_rate'] < s
                )
            })
            conditions.append({
                'name': f'makuri>={int(m_th*100)}%&sashi>={int(s_th*100)}%',
                'filter': lambda r, m=m_th, s=s_th: (
                    r['makuri_rate'] is not None and r['makuri_rate'] >= m and
                    r['sashi_rate'] is not None and r['sashi_rate'] >= s
                )
            })

    # 複合条件: まくり率 + 逃げ率
    for m_th in [0.20, 0.22, 0.24]:
        for e_th in [0.50, 0.55, 0.60]:
            conditions.append({
                'name': f'makuri<{int(m_th*100)}%&1C&escape>={int(e_th*100)}%',
                'filter': lambda r, m=m_th, e=e_th: (
                    r['makuri_rate'] is not None and r['makuri_rate'] < m and
                    r['pred_1st'] == 1 and
                    r['escape_rate'] is not None and r['escape_rate'] >= e
                )
            })
            conditions.append({
                'name': f'makuri>={int(m_th*100)}%&1C&escape>={int(e_th*100)}%',
                'filter': lambda r, m=m_th, e=e_th: (
                    r['makuri_rate'] is not None and r['makuri_rate'] >= m and
                    r['pred_1st'] == 1 and
                    r['escape_rate'] is not None and r['escape_rate'] >= e
                )
            })

    # 複合条件: 差し率 + 逃げ率
    for s_th in [0.18, 0.20, 0.22]:
        for e_th in [0.50, 0.55, 0.60]:
            conditions.append({
                'name': f'sashi<{int(s_th*100)}%&1C&escape>={int(e_th*100)}%',
                'filter': lambda r, s=s_th, e=e_th: (
                    r['sashi_rate'] is not None and r['sashi_rate'] < s and
                    r['pred_1st'] == 1 and
                    r['escape_rate'] is not None and r['escape_rate'] >= e
                )
            })

    # 3条件複合: まくり率 + 差し率 + 逃げ率
    for m_th in [0.20, 0.22]:
        for s_th in [0.18, 0.20]:
            for e_th in [0.50, 0.55]:
                conditions.append({
                    'name': f'makuri<{int(m_th*100)}%&sashi<{int(s_th*100)}%&1C&escape>={int(e_th*100)}%',
                    'filter': lambda r, m=m_th, s=s_th, e=e_th: (
                        r['makuri_rate'] is not None and r['makuri_rate'] < m and
                        r['sashi_rate'] is not None and r['sashi_rate'] < s and
                        r['pred_1st'] == 1 and
                        r['escape_rate'] is not None and r['escape_rate'] >= e
                    )
                })

    # 逆パターン: 荒れる会場で逃げ率高い選手
    for m_th in [0.24, 0.26]:
        for e_th in [0.60, 0.65, 0.70]:
            conditions.append({
                'name': f'makuri>={int(m_th*100)}%&1C&escape>={int(e_th*100)}%',
                'filter': lambda r, m=m_th, e=e_th: (
                    r['makuri_rate'] is not None and r['makuri_rate'] >= m and
                    r['pred_1st'] == 1 and
                    r['escape_rate'] is not None and r['escape_rate'] >= e
                )
            })

    print(f"   探索条件数: {len(conditions)}")

    # ========================================
    # 4. 各条件を評価
    # ========================================
    print("\n[4] 各条件を評価中...")

    results = []

    for cond in conditions:
        # 条件に合致するレースを抽出
        filtered = [r for r in enriched_races if cond['filter'](r)]

        if len(filtered) < 30:  # 最低30件
            continue

        # 全体成績
        total = len(filtered)
        hits = sum(1 for r in filtered if r['is_hit'])
        total_odds = sum(r['odds'] for r in filtered)
        avg_odds = total_odds / total if total > 0 else 0
        roi = (hits * avg_odds * 100) / (total * 100) * 100 if total > 0 else 0

        # 年度別成績
        yearly = defaultdict(lambda: {'total': 0, 'hits': 0, 'odds': 0})
        for r in filtered:
            yearly[r['year']]['total'] += 1
            yearly[r['year']]['odds'] += r['odds']
            if r['is_hit']:
                yearly[r['year']]['hits'] += 1

        # 年度別ROI計算
        yearly_roi = {}
        profit_years = 0
        for year in range(2020, 2026):
            y = yearly[year]
            if y['total'] > 0:
                y_avg_odds = y['odds'] / y['total']
                y_roi = (y['hits'] * y_avg_odds * 100) / (y['total'] * 100) * 100
                yearly_roi[year] = y_roi
                if y_roi >= 100:
                    profit_years += 1
            else:
                yearly_roi[year] = None

        results.append({
            'name': cond['name'],
            'total': total,
            'hits': hits,
            'hit_rate': hits / total * 100 if total > 0 else 0,
            'roi': roi,
            'profit_years': profit_years,
            'yearly_roi': yearly_roi,
            'yearly': yearly
        })

    # ========================================
    # 5. 結果をソート・表示
    # ========================================
    print("\n" + "=" * 80)
    print("[5] 有望条件（ROI 150%以上 & 黒字年3年以上）")
    print("=" * 80)

    # フィルタリング: ROI 150%以上、黒字年3年以上
    promising = [r for r in results if r['roi'] >= 150 and r['profit_years'] >= 3]
    promising.sort(key=lambda x: (-x['profit_years'], -x['roi']))

    print(f"\n   該当条件数: {len(promising)}")

    if promising:
        print("\n" + "-" * 100)
        print(f"{'条件':<45s} {'件数':>5s} {'的中':>4s} {'ROI':>7s} {'黒字年':>5s} | {'2020':>6s} {'2021':>6s} {'2022':>6s} {'2023':>6s} {'2024':>6s} {'2025':>6s}")
        print("-" * 100)

        for r in promising[:30]:
            yearly_str = ""
            for year in range(2020, 2026):
                y_roi = r['yearly_roi'].get(year)
                if y_roi is not None:
                    mark = "O" if y_roi >= 100 else "X"
                    yearly_str += f"{y_roi:>5.0f}%{mark}"
                else:
                    yearly_str += "    - "

            print(f"  {r['name']:<43s} {r['total']:>5d} {r['hits']:>4d} {r['roi']:>6.1f}% {r['profit_years']:>4d}/6 | {yearly_str}")

    # ========================================
    # 6. 年度安定性重視の条件
    # ========================================
    print("\n" + "=" * 80)
    print("[6] 年度安定性重視（黒字年4年以上）")
    print("=" * 80)

    stable = [r for r in results if r['profit_years'] >= 4 and r['roi'] >= 120]
    stable.sort(key=lambda x: (-x['profit_years'], -x['roi']))

    print(f"\n   該当条件数: {len(stable)}")

    if stable:
        print("\n" + "-" * 100)
        print(f"{'条件':<45s} {'件数':>5s} {'的中':>4s} {'ROI':>7s} {'黒字年':>5s} | {'2020':>6s} {'2021':>6s} {'2022':>6s} {'2023':>6s} {'2024':>6s} {'2025':>6s}")
        print("-" * 100)

        for r in stable[:20]:
            yearly_str = ""
            for year in range(2020, 2026):
                y_roi = r['yearly_roi'].get(year)
                if y_roi is not None:
                    mark = "O" if y_roi >= 100 else "X"
                    yearly_str += f"{y_roi:>5.0f}%{mark}"
                else:
                    yearly_str += "    - "

            print(f"  {r['name']:<43s} {r['total']:>5d} {r['hits']:>4d} {r['roi']:>6.1f}% {r['profit_years']:>4d}/6 | {yearly_str}")

    # ========================================
    # 7. ベースラインとの比較
    # ========================================
    print("\n" + "=" * 80)
    print("[7] ベースラインとの比較")
    print("=" * 80)

    # ベースライン計算
    base_total = len(enriched_races)
    base_hits = sum(1 for r in enriched_races if r['is_hit'])
    base_odds = sum(r['odds'] for r in enriched_races)
    base_avg = base_odds / base_total
    base_roi = (base_hits * base_avg * 100) / (base_total * 100) * 100

    print(f"\n   ベースライン: {base_total}件, {base_hits}的中, ROI {base_roi:.1f}%")

    # 上位条件との比較
    if promising:
        print("\n   【上位条件との比較】")
        for r in promising[:5]:
            diff_roi = r['roi'] - base_roi
            diff_count = base_total - r['total']
            reduction = diff_count / base_total * 100
            print(f"   - {r['name']}")
            print(f"     件数: {base_total}→{r['total']} (-{reduction:.0f}%), ROI: {base_roi:.1f}%→{r['roi']:.1f}% (+{diff_roi:.1f}pt)")

    # ========================================
    # 8. 推奨条件
    # ========================================
    print("\n" + "=" * 80)
    print("[8] 推奨条件")
    print("=" * 80)

    # 推奨基準: 黒字年4年以上、ROI 150%以上、件数50件以上
    recommended = [r for r in results
                   if r['profit_years'] >= 4 and r['roi'] >= 150 and r['total'] >= 50]
    recommended.sort(key=lambda x: (-x['profit_years'], -x['roi']))

    if recommended:
        print("\n   【採用推奨条件】")
        for r in recommended[:5]:
            print(f"\n   {r['name']}")
            print(f"   - 6年間: {r['total']}件, {r['hits']}的中, ROI {r['roi']:.1f}%")
            print(f"   - 黒字年: {r['profit_years']}/6年")
            print("   - 年度別:")
            for year in range(2020, 2026):
                y = r['yearly'][year]
                y_roi = r['yearly_roi'].get(year)
                if y['total'] > 0:
                    status = "[O]" if y_roi >= 100 else "[X]"
                    print(f"     {year}: {y['total']:>3d}件, {y['hits']}的中, ROI {y_roi:>6.1f}% {status}")
    else:
        print("\n   推奨基準（黒字年4年以上、ROI150%以上、50件以上）を満たす条件なし")
        print("\n   【次点候補】")
        next_best = [r for r in results
                     if r['profit_years'] >= 3 and r['roi'] >= 140 and r['total'] >= 40]
        next_best.sort(key=lambda x: (-x['profit_years'], -x['roi']))
        for r in next_best[:5]:
            print(f"\n   {r['name']}")
            print(f"   - 6年間: {r['total']}件, {r['hits']}的中, ROI {r['roi']:.1f}%")
            print(f"   - 黒字年: {r['profit_years']}/6年")

    conn.close()


if __name__ == "__main__":
    analyze_conditions()
