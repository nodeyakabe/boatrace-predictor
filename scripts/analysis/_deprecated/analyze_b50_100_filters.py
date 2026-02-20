#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B×50-100条件のフィルター案検証スクリプト

検証項目:
- 案A: 赤字5会場を除外（芦屋21, 三国10, 鳴門14, 徳山18, 若松20）
- 案B: 黒字上位7会場に限定
- 案C: 2コース・5コース予測を除外
- 案D: 6コース予測のみ
- 案E: 複合フィルター（会場 + コース）

採用基準: 直近4年で3年以上黒字
"""
import sqlite3
import sys
import io
import os

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: 'びわこ', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

# パターンH: 3点買い×400円
BET_COST = 400  # 3点×100円 + 100円（実際は3連単3点）
# 実際の計算: 的中時は3連単オッズ×100円で払い戻し、投資は400円固定

def analyze_b50_100_with_filter(cursor, year, venue_filter=None, venue_exclude=None, course_filter=None, course_exclude=None):
    """
    B×50-100条件を指定フィルターで分析（パターンH準拠）

    パターンH: 3点買い400円
    - 投資: 3連単3点×100円 + 3連複1点×100円 = 400円
    - 払戻: 3連単的中時はオッズ×100円
    - 3連複はデータがないため、簡略化して3連単3点のみで計算

    簡略化版: 3連単1点×100円で計算（standard_backtest.pyと同様）
    """
    # 基本条件
    confidence = 'B'
    c1_rank = ['A1', 'B1']  # A2除外
    odds_min = 50
    odds_max = 100

    c1_rank_str = "','".join(c1_rank)

    # フィルター構築
    venue_clause = ""
    if venue_filter:
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, venue_filter))})"
    elif venue_exclude:
        venue_clause = f"AND r.venue_code NOT IN ({','.join(map(str, venue_exclude))})"

    course_clause = ""
    if course_filter:
        course_clause = f"AND rp1.pit_number IN ({','.join(map(str, course_filter))})"
    elif course_exclude:
        course_clause = f"AND rp1.pit_number NOT IN ({','.join(map(str, course_exclude))})"

    # standard_backtest.pyと同じシンプルなクエリ（3連単1点のみ）
    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            rp.confidence,
            e1.racer_rank as c1_rank,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{confidence}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year}-01-01'
        AND r.race_date < '{year}-12-01'
        {venue_clause}
        {course_clause}
    ),
    race_bets AS (
        SELECT
            rb.*,
            COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = rb.race_id
                 AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                ), 0
            ) as pred_odds,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                THEN 1 ELSE 0
            END as is_hit,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                THEN COALESCE(
                    (SELECT o.odds FROM trifecta_odds o
                     WHERE o.race_id = rb.race_id
                     AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                    ), 0
                ) * 100
                ELSE 0
            END as payout
        FROM race_base rb
    )
    SELECT
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(payout) as payout
    FROM race_bets
    WHERE pred_odds >= {odds_min} AND pred_odds < {odds_max}
    '''

    cursor.execute(query)
    row = cursor.fetchone()
    bets, hits, payout = row

    if bets and bets > 0:
        cost = bets * 100  # standard_backtest.pyと同様に1点100円
        payout = payout or 0
        roi = 100.0 * payout / cost
        profit = payout - cost
        return {
            'bets': bets,
            'hits': hits or 0,
            'payout': payout,
            'cost': cost,
            'roi': roi,
            'profit': profit
        }
    return {'bets': 0, 'hits': 0, 'payout': 0, 'cost': 0, 'roi': 0, 'profit': 0}


def analyze_filter_yearly(cursor, filter_name, venue_filter=None, venue_exclude=None,
                         course_filter=None, course_exclude=None, years=range(2020, 2026)):
    """年度別にフィルターを分析"""
    results = []
    total_bets = 0
    total_payout = 0
    total_cost = 0
    profitable_years = 0

    for year in years:
        r = analyze_b50_100_with_filter(cursor, year, venue_filter, venue_exclude,
                                        course_filter, course_exclude)
        results.append({
            'year': year,
            **r
        })
        total_bets += r['bets']
        total_payout += r['payout']
        total_cost += r['cost']
        if r['profit'] > 0:
            profitable_years += 1

    total_roi = 100.0 * total_payout / total_cost if total_cost > 0 else 0
    total_profit = total_payout - total_cost

    # 直近4年の黒字年数
    recent_4_years = [r for r in results if r['year'] >= 2022]
    recent_profitable = sum(1 for r in recent_4_years if r['profit'] > 0)

    return {
        'filter_name': filter_name,
        'yearly': results,
        'total': {
            'bets': total_bets,
            'payout': total_payout,
            'cost': total_cost,
            'roi': total_roi,
            'profit': total_profit,
            'profitable_years': profitable_years,
            'recent_4_profitable': recent_profitable
        }
    }


def analyze_by_venue(cursor, year):
    """会場別のB×50-100を分析"""
    results = []
    for venue_code in range(1, 25):
        r = analyze_b50_100_with_filter(cursor, year, venue_filter=[venue_code])
        if r['bets'] > 0:
            results.append({
                'venue_code': venue_code,
                'venue_name': VENUE_NAMES.get(venue_code, str(venue_code)),
                **r
            })
    return sorted(results, key=lambda x: x['roi'], reverse=True)


def analyze_by_course(cursor, year):
    """予測コース別のB×50-100を分析"""
    results = []
    for course in range(1, 7):
        r = analyze_b50_100_with_filter(cursor, year, course_filter=[course])
        if r['bets'] > 0:
            results.append({
                'course': course,
                **r
            })
    return results


def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 100)
    print("B×50-100条件 フィルター案検証")
    print("=" * 100)
    print()

    # ============================================================
    # 現状（フィルターなし）の確認
    # ============================================================
    print("[1] 現状: B×50-100（フィルターなし）")
    print("-" * 100)
    baseline = analyze_filter_yearly(cursor, "現状（フィルターなし）")
    print(f"{'年度':<6} {'件数':>6} {'的中':>6} {'ROI':>8} {'収支':>12} {'状態'}")
    print("-" * 60)
    for r in baseline['yearly']:
        status = "黒字" if r['profit'] > 0 else "赤字"
        print(f"{r['year']:<6} {r['bets']:>6} {r['hits']:>6} {r['roi']:>7.1f}% {r['profit']:>+12,.0f} {status}")
    print("-" * 60)
    t = baseline['total']
    print(f"{'合計':<6} {t['bets']:>6} {'-':>6} {t['roi']:>7.1f}% {t['profit']:>+12,.0f} 黒字{t['profitable_years']}/6年")
    print(f"直近4年黒字: {t['recent_4_profitable']}/4年")
    print()

    # ============================================================
    # 案A: 赤字5会場除外
    # ============================================================
    print("[2] 案A: 赤字5会場除外（芦屋21, 三国10, 鳴門14, 徳山18, 若松20）")
    print("-" * 100)
    venue_exclude_a = [21, 10, 14, 18, 20]
    result_a = analyze_filter_yearly(cursor, "案A: 赤字5会場除外", venue_exclude=venue_exclude_a)
    print(f"{'年度':<6} {'件数':>6} {'的中':>6} {'ROI':>8} {'収支':>12} {'状態'}")
    print("-" * 60)
    for r in result_a['yearly']:
        status = "黒字" if r['profit'] > 0 else "赤字"
        print(f"{r['year']:<6} {r['bets']:>6} {r['hits']:>6} {r['roi']:>7.1f}% {r['profit']:>+12,.0f} {status}")
    print("-" * 60)
    t = result_a['total']
    print(f"{'合計':<6} {t['bets']:>6} {'-':>6} {t['roi']:>7.1f}% {t['profit']:>+12,.0f} 黒字{t['profitable_years']}/6年")
    print(f"直近4年黒字: {t['recent_4_profitable']}/4年")
    print()

    # ============================================================
    # 案B: 黒字上位7会場に限定
    # ============================================================
    print("[3] 案B: 黒字上位7会場に限定（江戸川3, 下関19, 戸田2, 常滑8, びわこ11, 丸亀15, 蒲郡7）")
    print("-" * 100)
    venue_filter_b = [3, 19, 2, 8, 11, 15, 7]
    result_b = analyze_filter_yearly(cursor, "案B: 黒字上位7会場", venue_filter=venue_filter_b)
    print(f"{'年度':<6} {'件数':>6} {'的中':>6} {'ROI':>8} {'収支':>12} {'状態'}")
    print("-" * 60)
    for r in result_b['yearly']:
        status = "黒字" if r['profit'] > 0 else "赤字"
        print(f"{r['year']:<6} {r['bets']:>6} {r['hits']:>6} {r['roi']:>7.1f}% {r['profit']:>+12,.0f} {status}")
    print("-" * 60)
    t = result_b['total']
    print(f"{'合計':<6} {t['bets']:>6} {'-':>6} {t['roi']:>7.1f}% {t['profit']:>+12,.0f} 黒字{t['profitable_years']}/6年")
    print(f"直近4年黒字: {t['recent_4_profitable']}/4年")
    print()

    # ============================================================
    # 案C: 2コース・5コース予測除外
    # ============================================================
    print("[4] 案C: 2コース・5コース予測除外")
    print("-" * 100)
    course_exclude_c = [2, 5]
    result_c = analyze_filter_yearly(cursor, "案C: 2・5コース除外", course_exclude=course_exclude_c)
    print(f"{'年度':<6} {'件数':>6} {'的中':>6} {'ROI':>8} {'収支':>12} {'状態'}")
    print("-" * 60)
    for r in result_c['yearly']:
        status = "黒字" if r['profit'] > 0 else "赤字"
        print(f"{r['year']:<6} {r['bets']:>6} {r['hits']:>6} {r['roi']:>7.1f}% {r['profit']:>+12,.0f} {status}")
    print("-" * 60)
    t = result_c['total']
    print(f"{'合計':<6} {t['bets']:>6} {'-':>6} {t['roi']:>7.1f}% {t['profit']:>+12,.0f} 黒字{t['profitable_years']}/6年")
    print(f"直近4年黒字: {t['recent_4_profitable']}/4年")
    print()

    # ============================================================
    # 案D: 6コース予測のみ
    # ============================================================
    print("[5] 案D: 6コース予測のみ")
    print("-" * 100)
    result_d = analyze_filter_yearly(cursor, "案D: 6コース予測のみ", course_filter=[6])
    print(f"{'年度':<6} {'件数':>6} {'的中':>6} {'ROI':>8} {'収支':>12} {'状態'}")
    print("-" * 60)
    for r in result_d['yearly']:
        status = "黒字" if r['profit'] > 0 else "赤字"
        print(f"{r['year']:<6} {r['bets']:>6} {r['hits']:>6} {r['roi']:>7.1f}% {r['profit']:>+12,.0f} {status}")
    print("-" * 60)
    t = result_d['total']
    print(f"{'合計':<6} {t['bets']:>6} {'-':>6} {t['roi']:>7.1f}% {t['profit']:>+12,.0f} 黒字{t['profitable_years']}/6年")
    print(f"直近4年黒字: {t['recent_4_profitable']}/4年")
    print()

    # ============================================================
    # 案E1: 赤字5会場除外 + 2・5コース除外
    # ============================================================
    print("[6] 案E1: 赤字5会場除外 + 2・5コース予測除外")
    print("-" * 100)
    result_e1 = analyze_filter_yearly(cursor, "案E1: 会場+コース",
                                      venue_exclude=venue_exclude_a, course_exclude=course_exclude_c)
    print(f"{'年度':<6} {'件数':>6} {'的中':>6} {'ROI':>8} {'収支':>12} {'状態'}")
    print("-" * 60)
    for r in result_e1['yearly']:
        status = "黒字" if r['profit'] > 0 else "赤字"
        print(f"{r['year']:<6} {r['bets']:>6} {r['hits']:>6} {r['roi']:>7.1f}% {r['profit']:>+12,.0f} {status}")
    print("-" * 60)
    t = result_e1['total']
    print(f"{'合計':<6} {t['bets']:>6} {'-':>6} {t['roi']:>7.1f}% {t['profit']:>+12,.0f} 黒字{t['profitable_years']}/6年")
    print(f"直近4年黒字: {t['recent_4_profitable']}/4年")
    print()

    # ============================================================
    # 案E2: 黒字上位7会場 + 2・5コース除外
    # ============================================================
    print("[7] 案E2: 黒字上位7会場 + 2・5コース予測除外")
    print("-" * 100)
    result_e2 = analyze_filter_yearly(cursor, "案E2: 上位会場+コース",
                                      venue_filter=venue_filter_b, course_exclude=course_exclude_c)
    print(f"{'年度':<6} {'件数':>6} {'的中':>6} {'ROI':>8} {'収支':>12} {'状態'}")
    print("-" * 60)
    for r in result_e2['yearly']:
        status = "黒字" if r['profit'] > 0 else "赤字"
        print(f"{r['year']:<6} {r['bets']:>6} {r['hits']:>6} {r['roi']:>7.1f}% {r['profit']:>+12,.0f} {status}")
    print("-" * 60)
    t = result_e2['total']
    print(f"{'合計':<6} {t['bets']:>6} {'-':>6} {t['roi']:>7.1f}% {t['profit']:>+12,.0f} 黒字{t['profitable_years']}/6年")
    print(f"直近4年黒字: {t['recent_4_profitable']}/4年")
    print()

    # ============================================================
    # 6年間の会場別詳細（参考情報）
    # ============================================================
    print("[参考] 6年間 会場別ROI")
    print("-" * 100)
    venue_6year = {}
    for year in range(2020, 2026):
        by_venue = analyze_by_venue(cursor, year)
        for v in by_venue:
            code = v['venue_code']
            if code not in venue_6year:
                venue_6year[code] = {'name': v['venue_name'], 'bets': 0, 'payout': 0, 'cost': 0,
                                     'yearly_profits': []}
            venue_6year[code]['bets'] += v['bets']
            venue_6year[code]['payout'] += v['payout']
            venue_6year[code]['cost'] += v['cost']
            venue_6year[code]['yearly_profits'].append(v['profit'])

    venue_list = []
    for code, data in venue_6year.items():
        roi = 100.0 * data['payout'] / data['cost'] if data['cost'] > 0 else 0
        profit = data['payout'] - data['cost']
        profitable_years = sum(1 for p in data['yearly_profits'] if p > 0)
        venue_list.append({
            'code': code,
            'name': data['name'],
            'bets': data['bets'],
            'roi': roi,
            'profit': profit,
            'profitable_years': profitable_years
        })

    venue_list.sort(key=lambda x: x['roi'], reverse=True)
    print(f"{'会場':<8} {'件数':>6} {'ROI':>8} {'収支':>12} {'黒字年'}")
    print("-" * 60)
    for v in venue_list:
        status = f"{v['profitable_years']}/6年"
        print(f"{v['name']:<8} {v['bets']:>6} {v['roi']:>7.1f}% {v['profit']:>+12,.0f} {status}")
    print()

    # ============================================================
    # 6年間のコース別詳細（参考情報）
    # ============================================================
    print("[参考] 6年間 予測コース別ROI")
    print("-" * 100)
    course_6year = {}
    for year in range(2020, 2026):
        by_course = analyze_by_course(cursor, year)
        for c in by_course:
            course = c['course']
            if course not in course_6year:
                course_6year[course] = {'bets': 0, 'payout': 0, 'cost': 0, 'yearly_profits': []}
            course_6year[course]['bets'] += c['bets']
            course_6year[course]['payout'] += c['payout']
            course_6year[course]['cost'] += c['cost']
            course_6year[course]['yearly_profits'].append(c['profit'])

    print(f"{'コース':<8} {'件数':>6} {'ROI':>8} {'収支':>12} {'黒字年'}")
    print("-" * 60)
    for course in sorted(course_6year.keys()):
        data = course_6year[course]
        roi = 100.0 * data['payout'] / data['cost'] if data['cost'] > 0 else 0
        profit = data['payout'] - data['cost']
        profitable_years = sum(1 for p in data['yearly_profits'] if p > 0)
        print(f"{course}コース   {data['bets']:>6} {roi:>7.1f}% {profit:>+12,.0f} {profitable_years}/6年")
    print()

    # ============================================================
    # 採用判定サマリー
    # ============================================================
    print("=" * 100)
    print("採用判定サマリー")
    print("=" * 100)
    print()
    print("採用基準: 直近4年で3年以上黒字")
    print()

    all_results = [
        ('現状（フィルターなし）', baseline),
        ('案A: 赤字5会場除外', result_a),
        ('案B: 黒字上位7会場限定', result_b),
        ('案C: 2・5コース予測除外', result_c),
        ('案D: 6コース予測のみ', result_d),
        ('案E1: 赤字5会場除外+2・5コース除外', result_e1),
        ('案E2: 黒字上位7会場+2・5コース除外', result_e2),
    ]

    print(f"{'案':<35} {'件数':>6} {'ROI':>8} {'収支':>12} {'6年黒字':>8} {'直近4年':>8} {'判定'}")
    print("-" * 100)

    for name, result in all_results:
        t = result['total']
        recent = t['recent_4_profitable']
        meets_criteria = recent >= 3
        judgment = "採用推奨" if meets_criteria and t['bets'] >= 100 else "保留" if meets_criteria else "不採用"
        print(f"{name:<35} {t['bets']:>6} {t['roi']:>7.1f}% {t['profit']:>+12,.0f} {t['profitable_years']}/6年    {recent}/4年   {judgment}")

    print()
    print("-" * 100)
    print("判定基準:")
    print("  採用推奨: 直近4年3年以上黒字 かつ 件数100件以上")
    print("  保留:     直近4年3年以上黒字 だが 件数100件未満")
    print("  不採用:   直近4年3年以上黒字を満たさない")
    print()

    conn.close()


if __name__ == '__main__':
    main()
