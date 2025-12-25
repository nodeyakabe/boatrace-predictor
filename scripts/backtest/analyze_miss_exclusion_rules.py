#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不的中パターンから除外ルールを発見するスクリプト

目的:
    現在の購入条件は維持したまま、不的中パターンの法則性を見つけて
    特定のパターンのみを除外することで収支を改善する

分析対象:
    - 会場別の不的中パターン
    - レース番号別の不的中パターン
    - 1着予測外し vs 2着/3着予測外し
    - オッズ帯別の不的中パターン
    - 曜日別の不的中パターン
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
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

# 現在の購入条件
CONDITIONS = [
    {'name': 'A×A1×10-12', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12, 'venue_filter': None, 'motor_min': None},
    {'name': 'A×A1×14-16', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 14, 'odds_max': 16, 'venue_filter': None, 'motor_min': None},
    {'name': 'A×B1×Motor40%+', 'confidence': 'A', 'c1_rank': ['B1'], 'odds_min': 10, 'odds_max': 100, 'venue_filter': None, 'motor_min': 40},
    {'name': 'B×50-100', 'confidence': 'B', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 50, 'odds_max': 100, 'venue_filter': None, 'motor_min': None},
    {'name': 'B×30-50×B1+会場', 'confidence': 'B', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50,
     'venue_filter': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8], 'motor_min': None},
    {'name': 'C×20-30×B1+会場', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30,
     'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17], 'motor_min': None},
    {'name': '鳴門×C×A2×30-80', 'confidence': 'C', 'c1_rank': ['A2'], 'odds_min': 30, 'odds_max': 80,
     'venue_filter': [14], 'motor_min': None},
    {'name': 'D×40-50×B1', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50, 'venue_filter': None, 'motor_min': None},
    {'name': 'D×30-60', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 30, 'odds_max': 60, 'venue_filter': None, 'motor_min': None},
]


def get_all_bets(year_start=2025, year_end=2025):
    """全購入データを取得"""
    all_bets = []

    for cond in CONDITIONS:
        c1_rank_str = "','".join(cond['c1_rank'])
        venue_clause = ""
        if cond.get('venue_filter'):
            venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"
        motor_clause = ""
        if cond.get('motor_min'):
            motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

        query = f'''
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_number,
            r.race_date,
            e1.racer_rank as c1_rank,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd,
            COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
                ), 0
            ) as pred_odds
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end}-12-01'
        {venue_clause}
        {motor_clause}
        '''
        cursor.execute(query)
        rows = cursor.fetchall()

        for row in rows:
            race_id, venue_code, race_number, race_date, c1_rank, p1, p2, p3, a1, a2, a3, pred_odds = row
            if pred_odds >= cond['odds_min'] and pred_odds < cond['odds_max']:
                is_hit = (p1 == a1 and p2 == a2 and p3 == a3)
                payout = pred_odds * 100 if is_hit else 0

                # 外しパターンの分類
                if is_hit:
                    miss_type = 'HIT'
                elif p1 != a1:
                    miss_type = '1着外し'
                elif p2 != a2:
                    miss_type = '2着外し'
                else:
                    miss_type = '3着外し'

                all_bets.append({
                    'condition': cond['name'],
                    'confidence': cond['confidence'],
                    'venue_code': venue_code,
                    'race_number': race_number,
                    'race_date': race_date,
                    'c1_rank': c1_rank,
                    'pred': f"{p1}-{p2}-{p3}",
                    'actual': f"{a1}-{a2}-{a3}",
                    'odds': pred_odds,
                    'is_hit': is_hit,
                    'payout': payout,
                    'profit': payout - 100,
                    'miss_type': miss_type,
                })

    return all_bets


def analyze_by_dimension(bets, dimension_key, dimension_name, top_n=10):
    """特定の次元で分析"""
    stats = {}

    for bet in bets:
        key = bet[dimension_key]
        if key not in stats:
            stats[key] = {'bets': 0, 'hits': 0, 'payout': 0}
        stats[key]['bets'] += 1
        stats[key]['hits'] += 1 if bet['is_hit'] else 0
        stats[key]['payout'] += bet['payout']

    results = []
    for key, s in stats.items():
        if s['bets'] > 0:
            roi = 100.0 * s['payout'] / (s['bets'] * 100)
            profit = s['payout'] - (s['bets'] * 100)
            results.append({
                'key': key,
                'bets': s['bets'],
                'hits': s['hits'],
                'roi': roi,
                'profit': profit,
            })

    return sorted(results, key=lambda x: x['profit'])


def find_exclusion_rules(bets, conditions_to_analyze=None):
    """除外ルールを発見"""
    if conditions_to_analyze is None:
        conditions_to_analyze = set(b['condition'] for b in bets)

    exclusion_candidates = []

    for cond_name in conditions_to_analyze:
        cond_bets = [b for b in bets if b['condition'] == cond_name]
        if len(cond_bets) < 10:
            continue

        print(f"\n{'='*80}")
        print(f"【{cond_name}】の除外ルール分析")
        print(f"{'='*80}")

        total_bets = len(cond_bets)
        total_profit = sum(b['profit'] for b in cond_bets)
        total_roi = 100.0 * (total_profit + total_bets * 100) / (total_bets * 100)
        print(f"現状: {total_bets}件, ROI {total_roi:.1f}%, 収支 {total_profit:+,.0f}円")

        # 会場別分析
        print(f"\n[会場別]")
        venue_stats = analyze_by_dimension(cond_bets, 'venue_code', '会場')
        for r in venue_stats[:5]:  # ワースト5
            venue_name = VENUE_NAMES.get(r['key'], str(r['key']))
            if r['profit'] < 0 and r['bets'] >= 5:
                print(f"  {venue_name}: {r['bets']}件, ROI {r['roi']:.1f}%, 収支 {r['profit']:+,.0f}円 ← 除外候補")
                # この会場を除外した場合の改善効果
                new_profit = total_profit - r['profit']
                new_bets = total_bets - r['bets']
                if new_bets > 0:
                    new_roi = 100.0 * (new_profit + new_bets * 100) / (new_bets * 100)
                    exclusion_candidates.append({
                        'condition': cond_name,
                        'rule': f'会場除外: {venue_name}',
                        'venue_code': r['key'],
                        'removed_bets': r['bets'],
                        'removed_loss': -r['profit'],
                        'new_bets': new_bets,
                        'new_roi': new_roi,
                        'new_profit': new_profit,
                        'improvement': new_profit - total_profit,
                    })

        # レース番号別分析
        print(f"\n[レース番号別]")
        race_stats = analyze_by_dimension(cond_bets, 'race_number', 'レース番号')
        for r in race_stats[:5]:  # ワースト5
            if r['profit'] < 0 and r['bets'] >= 5:
                print(f"  {r['key']}R: {r['bets']}件, ROI {r['roi']:.1f}%, 収支 {r['profit']:+,.0f}円 ← 除外候補")
                new_profit = total_profit - r['profit']
                new_bets = total_bets - r['bets']
                if new_bets > 0:
                    new_roi = 100.0 * (new_profit + new_bets * 100) / (new_bets * 100)
                    exclusion_candidates.append({
                        'condition': cond_name,
                        'rule': f'レース番号除外: {r["key"]}R',
                        'race_number': r['key'],
                        'removed_bets': r['bets'],
                        'removed_loss': -r['profit'],
                        'new_bets': new_bets,
                        'new_roi': new_roi,
                        'new_profit': new_profit,
                        'improvement': new_profit - total_profit,
                    })

        # 1コース級別分析
        print(f"\n[1コース級別]")
        rank_stats = analyze_by_dimension(cond_bets, 'c1_rank', '級別')
        for r in rank_stats:
            status = "← 除外候補" if r['profit'] < 0 and r['bets'] >= 5 else ""
            print(f"  {r['key']}: {r['bets']}件, ROI {r['roi']:.1f}%, 収支 {r['profit']:+,.0f}円 {status}")
            if r['profit'] < 0 and r['bets'] >= 5:
                new_profit = total_profit - r['profit']
                new_bets = total_bets - r['bets']
                if new_bets > 0:
                    new_roi = 100.0 * (new_profit + new_bets * 100) / (new_bets * 100)
                    exclusion_candidates.append({
                        'condition': cond_name,
                        'rule': f'級別除外: {r["key"]}',
                        'c1_rank': r['key'],
                        'removed_bets': r['bets'],
                        'removed_loss': -r['profit'],
                        'new_bets': new_bets,
                        'new_roi': new_roi,
                        'new_profit': new_profit,
                        'improvement': new_profit - total_profit,
                    })

        # オッズ帯分析（5倍刻み）
        print(f"\n[オッズ帯別（5倍刻み）]")
        for b in cond_bets:
            b['odds_band'] = int(b['odds'] // 5) * 5
        odds_stats = analyze_by_dimension(cond_bets, 'odds_band', 'オッズ帯')
        for r in odds_stats[:5]:  # ワースト5
            if r['profit'] < 0 and r['bets'] >= 5:
                print(f"  {r['key']}-{r['key']+5}倍: {r['bets']}件, ROI {r['roi']:.1f}%, 収支 {r['profit']:+,.0f}円 ← 除外候補")
                new_profit = total_profit - r['profit']
                new_bets = total_bets - r['bets']
                if new_bets > 0:
                    new_roi = 100.0 * (new_profit + new_bets * 100) / (new_bets * 100)
                    exclusion_candidates.append({
                        'condition': cond_name,
                        'rule': f'オッズ帯除外: {r["key"]}-{r["key"]+5}倍',
                        'odds_min': r['key'],
                        'odds_max': r['key'] + 5,
                        'removed_bets': r['bets'],
                        'removed_loss': -r['profit'],
                        'new_bets': new_bets,
                        'new_roi': new_roi,
                        'new_profit': new_profit,
                        'improvement': new_profit - total_profit,
                    })

    return exclusion_candidates


def main():
    print("=" * 80)
    print("不的中パターンからの除外ルール発見")
    print("対象期間: 2025年1-11月")
    print("=" * 80)

    # 全購入データを取得
    bets = get_all_bets(2025, 2025)
    print(f"\n総件数: {len(bets)}件")
    print(f"的中: {sum(1 for b in bets if b['is_hit'])}件")
    print(f"不的中: {sum(1 for b in bets if not b['is_hit'])}件")

    # 除外ルールを発見
    candidates = find_exclusion_rules(bets)

    # 除外候補をソート（改善効果順）
    print("\n" + "=" * 80)
    print("【除外ルール候補（改善効果順）】")
    print("=" * 80)
    candidates_sorted = sorted(candidates, key=lambda x: x['improvement'], reverse=True)

    print(f"\n{'条件':<25} {'除外ルール':<25} {'削減件数':>8} {'改善額':>12} {'新ROI':>8}")
    print("-" * 85)

    for c in candidates_sorted[:20]:
        if c['improvement'] > 0:
            print(f"{c['condition']:<25} {c['rule']:<25} {c['removed_bets']:>8} {c['improvement']:>+12,.0f} {c['new_roi']:>7.1f}%")

    # 複合除外ルールの検証
    print("\n" + "=" * 80)
    print("【複合除外ルールの検証】")
    print("=" * 80)

    # 最も効果的な除外ルールを適用した場合のシミュレーション
    total_improvement = 0
    applied_rules = []
    remaining_bets = bets.copy()

    for c in candidates_sorted:
        if c['improvement'] <= 0:
            continue

        # このルールを適用
        if 'venue_code' in c:
            new_remaining = [b for b in remaining_bets if not (b['condition'] == c['condition'] and b['venue_code'] == c['venue_code'])]
        elif 'race_number' in c:
            new_remaining = [b for b in remaining_bets if not (b['condition'] == c['condition'] and b['race_number'] == c['race_number'])]
        elif 'c1_rank' in c:
            new_remaining = [b for b in remaining_bets if not (b['condition'] == c['condition'] and b['c1_rank'] == c['c1_rank'])]
        elif 'odds_min' in c:
            new_remaining = [b for b in remaining_bets if not (b['condition'] == c['condition'] and c['odds_min'] <= b['odds'] < c['odds_max'])]
        else:
            continue

        # 改善効果を再計算
        old_profit = sum(b['profit'] for b in remaining_bets)
        new_profit = sum(b['profit'] for b in new_remaining)
        actual_improvement = new_profit - old_profit

        if actual_improvement > 0:
            total_improvement += actual_improvement
            applied_rules.append({**c, 'actual_improvement': actual_improvement})
            remaining_bets = new_remaining

    print(f"\n適用可能な除外ルール: {len(applied_rules)}件")
    print(f"累積改善額: {total_improvement:+,.0f}円")
    print(f"除外後の件数: {len(remaining_bets)}件")

    if remaining_bets:
        final_profit = sum(b['profit'] for b in remaining_bets)
        final_roi = 100.0 * (final_profit + len(remaining_bets) * 100) / (len(remaining_bets) * 100)
        print(f"除外後のROI: {final_roi:.1f}%")
        print(f"除外後の収支: {final_profit:+,.0f}円")

    print("\n[適用した除外ルール]")
    for i, r in enumerate(applied_rules, 1):
        print(f"  {i}. {r['condition']} - {r['rule']} (改善: {r['actual_improvement']:+,.0f}円)")

    conn.close()


if __name__ == '__main__':
    main()
