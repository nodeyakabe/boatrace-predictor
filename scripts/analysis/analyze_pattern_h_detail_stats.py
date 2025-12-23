#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
パターンH外れレース詳細統計分析

JSONデータから詳細統計を計算して出力
"""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

ROOT_DIR = Path(__file__).parent.parent

MINUS_MONTHS = ['2025-01', '2025-03', '2025-04', '2025-05', '2025-08', '2025-12']
PLUS_MONTHS = ['2025-02', '2025-06', '2025-07', '2025-09', '2025-10', '2025-11']

def load_data():
    with open(ROOT_DIR / 'scripts' / 'pattern_h_analysis.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def calc_stats(races):
    if not races:
        return {'count': 0, 'hits': 0, 'hit_rate': 0, 'investment': 0, 'return': 0, 'roi': 0, 'balance': 0}
    count = len(races)
    hits = sum(1 for r in races if r['is_hit'])
    investment = sum(r['investment'] for r in races)
    ret = sum(r['return'] for r in races)
    return {
        'count': count,
        'hits': hits,
        'hit_rate': hits / count * 100 if count > 0 else 0,
        'investment': investment,
        'return': ret,
        'roi': ret / investment * 100 if investment > 0 else 0,
        'balance': ret - investment
    }

def main():
    data = load_data()

    minus_data = [d for d in data if d['month'] in MINUS_MONTHS]
    plus_data = [d for d in data if d['month'] in PLUS_MONTHS]

    results = {
        'summary': {
            'total': calc_stats(data),
            'minus': calc_stats(minus_data),
            'plus': calc_stats(plus_data)
        },
        'miss_patterns': {},
        'venues': {},
        'confidence': {},
        'c1_rank': {},
        'odds_range': {},
        'race_number': {},
        'wind_speed': {},
        'wave_height': {},
        'weekday': {},
        'day_period': {},
        'kimarite': {}
    }

    # 1. 外れパターン分析
    miss_patterns = ['HIT', '1st_hit_2nd_miss', 'close_miss_swap', 'close_miss_2boats', '1boat_only', 'total_miss']
    for pattern in miss_patterns:
        m_races = [r for r in minus_data if r['miss_pattern'] == pattern]
        p_races = [r for r in plus_data if r['miss_pattern'] == pattern]
        results['miss_patterns'][pattern] = {
            'minus': calc_stats(m_races),
            'plus': calc_stats(p_races)
        }

    # 2. 会場別分析
    venues = set(r['venue_code'] for r in data)
    for v in sorted(venues):
        m_races = [r for r in minus_data if r['venue_code'] == v]
        p_races = [r for r in plus_data if r['venue_code'] == v]
        if m_races or p_races:
            venue_name = m_races[0]['venue_name_jp'] if m_races else p_races[0]['venue_name_jp']
            results['venues'][v] = {
                'name': venue_name,
                'minus': calc_stats(m_races),
                'plus': calc_stats(p_races)
            }

    # 3. 信頼度別分析
    for conf in ['C', 'D']:
        m_races = [r for r in minus_data if r['confidence'] == conf]
        p_races = [r for r in plus_data if r['confidence'] == conf]
        results['confidence'][conf] = {
            'minus': calc_stats(m_races),
            'plus': calc_stats(p_races)
        }

    # 4. 1コース級別分析
    for rank in ['A1', 'A2', 'B1', 'B2']:
        m_races = [r for r in minus_data if r['c1_rank'] == rank]
        p_races = [r for r in plus_data if r['c1_rank'] == rank]
        results['c1_rank'][rank] = {
            'minus': calc_stats(m_races),
            'plus': calc_stats(p_races)
        }

    # 5. オッズレンジ別分析
    def get_odds_range(odds):
        if odds < 20: return '0-20'
        elif odds < 30: return '20-30'
        elif odds < 40: return '30-40'
        elif odds < 50: return '40-50'
        elif odds < 60: return '50-60'
        else: return '60+'

    for odr in ['0-20', '20-30', '30-40', '40-50', '50-60', '60+']:
        m_races = [r for r in minus_data if get_odds_range(r['odds_123']) == odr]
        p_races = [r for r in plus_data if get_odds_range(r['odds_123']) == odr]
        results['odds_range'][odr] = {
            'minus': calc_stats(m_races),
            'plus': calc_stats(p_races)
        }

    # 6. レース番号別分析
    for rn in range(1, 13):
        m_races = [r for r in minus_data if r['race_number'] == rn]
        p_races = [r for r in plus_data if r['race_number'] == rn]
        results['race_number'][str(rn)] = {
            'minus': calc_stats(m_races),
            'plus': calc_stats(p_races)
        }

    # 7. 風速別分析
    def get_wind_range(wind):
        if wind < 2: return '0-2m'
        elif wind < 4: return '2-4m'
        elif wind < 6: return '4-6m'
        else: return '6m+'

    for wr in ['0-2m', '2-4m', '4-6m', '6m+']:
        m_races = [r for r in minus_data if get_wind_range(r['wind_speed']) == wr]
        p_races = [r for r in plus_data if get_wind_range(r['wind_speed']) == wr]
        results['wind_speed'][wr] = {
            'minus': calc_stats(m_races),
            'plus': calc_stats(p_races)
        }

    # 8. 波高別分析
    def get_wave_range(wave):
        if wave <= 2: return '0-2cm'
        elif wave <= 5: return '3-5cm'
        elif wave <= 10: return '6-10cm'
        else: return '10cm+'

    for wave in ['0-2cm', '3-5cm', '6-10cm', '10cm+']:
        m_races = [r for r in minus_data if get_wave_range(r['wave_height']) == wave]
        p_races = [r for r in plus_data if get_wave_range(r['wave_height']) == wave]
        results['wave_height'][wave] = {
            'minus': calc_stats(m_races),
            'plus': calc_stats(p_races)
        }

    # 9. 曜日別分析
    weekday_map = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri', 5: 'Sat', 6: 'Sun'}
    def get_weekday(date_str):
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return weekday_map[dt.weekday()]

    for wd in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']:
        m_races = [r for r in minus_data if get_weekday(r['race_date']) == wd]
        p_races = [r for r in plus_data if get_weekday(r['race_date']) == wd]
        results['weekday'][wd] = {
            'minus': calc_stats(m_races),
            'plus': calc_stats(p_races)
        }

    # 10. 月内時期別分析
    def get_day_period(date_str):
        day = int(date_str.split('-')[2])
        if day <= 10: return 'early'
        elif day <= 20: return 'mid'
        else: return 'late'

    for period in ['early', 'mid', 'late']:
        m_races = [r for r in minus_data if get_day_period(r['race_date']) == period]
        p_races = [r for r in plus_data if get_day_period(r['race_date']) == period]
        results['day_period'][period] = {
            'minus': calc_stats(m_races),
            'plus': calc_stats(p_races)
        }

    # 11. 決まり手別分析
    kimarite_list = set(r['kimarite'] for r in data if r['kimarite'])
    for km in sorted(kimarite_list):
        m_races = [r for r in minus_data if r['kimarite'] == km]
        p_races = [r for r in plus_data if r['kimarite'] == km]
        results['kimarite'][km] = {
            'minus': calc_stats(m_races),
            'plus': calc_stats(p_races)
        }

    # 結果保存
    output_path = ROOT_DIR / 'scripts' / 'pattern_h_detail_stats.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("Detail stats saved to pattern_h_detail_stats.json")

    # 重要な発見を出力
    print("\n" + "=" * 80)
    print("KEY FINDINGS")
    print("=" * 80)

    print("\n[1] MISS PATTERN ANALYSIS")
    print("-" * 60)
    print(f"{'Pattern':<25} {'Minus%':>10} {'Plus%':>10} {'Diff':>10}")
    for pattern, stats in results['miss_patterns'].items():
        m_rate = stats['minus']['count'] / len(minus_data) * 100 if minus_data else 0
        p_rate = stats['plus']['count'] / len(plus_data) * 100 if plus_data else 0
        diff = m_rate - p_rate
        print(f"{pattern:<25} {m_rate:>9.1f}% {p_rate:>9.1f}% {diff:>+9.1f}%")

    print("\n[2] TOP 5 WORST VENUES (Minus Months Only)")
    print("-" * 60)
    venue_list = [(v, s['name'], s['minus']) for v, s in results['venues'].items() if s['minus']['count'] >= 5]
    venue_list.sort(key=lambda x: x[2]['roi'])
    for v, name, s in venue_list[:5]:
        print(f"  {name}({v}): {s['count']} races, {s['hits']} hits, ROI {s['roi']:.1f}%, Balance {s['balance']:+,.0f}")

    print("\n[3] CONFIDENCE COMPARISON")
    print("-" * 60)
    for conf, stats in results['confidence'].items():
        m = stats['minus']
        p = stats['plus']
        print(f"  {conf}: Minus {m['count']} races, {m['hit_rate']:.1f}% hit, ROI {m['roi']:.1f}% | Plus {p['count']} races, {p['hit_rate']:.1f}% hit, ROI {p['roi']:.1f}%")

    print("\n[4] C1 RANK COMPARISON")
    print("-" * 60)
    for rank, stats in results['c1_rank'].items():
        m = stats['minus']
        p = stats['plus']
        if m['count'] > 0 or p['count'] > 0:
            print(f"  {rank}: Minus {m['count']} races, {m['hit_rate']:.1f}% hit, ROI {m['roi']:.1f}% | Plus {p['count']} races, {p['hit_rate']:.1f}% hit, ROI {p['roi']:.1f}%")

    print("\n[5] ODDS RANGE COMPARISON")
    print("-" * 60)
    for odr, stats in sorted(results['odds_range'].items()):
        m = stats['minus']
        p = stats['plus']
        print(f"  {odr}: Minus {m['count']} races, {m['hit_rate']:.1f}% hit, ROI {m['roi']:.1f}% | Plus {p['count']} races, {p['hit_rate']:.1f}% hit, ROI {p['roi']:.1f}%")

    print("\n[6] WIND SPEED COMPARISON")
    print("-" * 60)
    for wr, stats in results['wind_speed'].items():
        m = stats['minus']
        p = stats['plus']
        print(f"  {wr}: Minus {m['count']} races, {m['hit_rate']:.1f}% hit, ROI {m['roi']:.1f}% | Plus {p['count']} races, {p['hit_rate']:.1f}% hit, ROI {p['roi']:.1f}%")

    print("\n[7] RACE NUMBER - WORST IN MINUS MONTHS")
    print("-" * 60)
    rn_list = [(rn, s['minus']) for rn, s in results['race_number'].items() if s['minus']['count'] >= 10]
    rn_list.sort(key=lambda x: x[1]['roi'])
    for rn, s in rn_list[:5]:
        print(f"  R{rn}: {s['count']} races, {s['hits']} hits, ROI {s['roi']:.1f}%, Balance {s['balance']:+,.0f}")

    print("\n[8] WEEKDAY COMPARISON")
    print("-" * 60)
    for wd, stats in results['weekday'].items():
        m = stats['minus']
        p = stats['plus']
        print(f"  {wd}: Minus {m['count']} races, {m['hit_rate']:.1f}% hit, ROI {m['roi']:.1f}% | Plus {p['count']} races, {p['hit_rate']:.1f}% hit, ROI {p['roi']:.1f}%")

    print("\n[9] KIMARITE COMPARISON")
    print("-" * 60)
    for km, stats in results['kimarite'].items():
        m = stats['minus']
        p = stats['plus']
        if m['count'] >= 10 or p['count'] >= 10:
            print(f"  {km}: Minus {m['count']} races, {m['hit_rate']:.1f}% hit | Plus {p['count']} races, {p['hit_rate']:.1f}% hit")

if __name__ == '__main__':
    main()
