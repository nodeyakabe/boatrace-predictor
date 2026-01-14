#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
購入条件間の重複分析スクリプト

目的:
    複数の購入条件が同じレースを重複して購入しているかを分析し、
    真の分散効果とリスク集中度を評価する

分析項目:
    1. 重複レース数の分析
    2. 条件ペア別重複数
    3. 重複レースのパフォーマンス比較
    4. 条件間の相関分析
    5. リスク評価

作成日: 2026-01-13
"""
import sqlite3
import sys
import io
import os
from collections import defaultdict
from typing import Dict, List, Any, Set, Tuple

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# 購入条件定義（standard_backtest.py から転記）
CONDITIONS = [
    {
        'name': 'A×A1×10-12+会場+逃げ率',
        'confidence': 'A',
        'c1_rank': ['A1'],
        'odds_min': 10,
        'odds_max': 12,
        'venue_filter': [10, 14, 21, 18, 8, 19, 12],
        'escape_rate_min': 0.70,
        'predicted_course': 1,
        'use_pattern_h': False,
    },
    {
        'name': 'B×50-100×冬除外',
        'confidence': 'B',
        'c1_rank': ['A1', 'B1'],
        'odds_min': 50,
        'odds_max': 100,
        'venue_filter': None,
        'month_exclude': [12, 1, 2],
        'use_pattern_h': True,
    },
    {
        'name': 'B×30-50×B1+会場',
        'confidence': 'B',
        'c1_rank': ['B1'],
        'odds_min': 30,
        'odds_max': 50,
        'venue_filter': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8],
        'use_pattern_h': True,
    },
    {
        'name': 'B×10-30×穴源×会場',
        'confidence': 'B',
        'c1_rank': ['A1', 'A2', 'B1'],
        'odds_min': 10,
        'odds_max': 30,
        'venue_filter': [6, 7, 8, 10, 15, 19],
        'bias_max': -0.3,
        'use_pattern_h': False,
    },
    {
        'name': 'C×20-30×B1+会場',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17],
        'use_pattern_h': False,
    },
    {
        'name': '鳴門×C×A2×30-80',
        'confidence': 'C',
        'c1_rank': ['A2'],
        'odds_min': 30,
        'odds_max': 80,
        'venue_filter': [14],
        'use_pattern_h': True,
    },
    {
        'name': '唐津×C×B1×20-30',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        'venue_filter': [23],
        'use_pattern_h': False,
    },
    {
        'name': '児島×C×B1×30-50',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 30,
        'odds_max': 50,
        'venue_filter': [16],
        'use_pattern_h': True,
    },
    {
        'name': 'D×40-50×B1×2連率20-30%',
        'confidence': 'D',
        'c1_rank': ['B1'],
        'odds_min': 40,
        'odds_max': 50,
        'venue_filter': None,
        'c1_second_rate_min': 20,
        'c1_second_rate_max': 30,
        'use_pattern_h': False,
    },
    {
        'name': 'D×5コース予測',
        'confidence': 'D',
        'c1_rank': ['A1', 'A2', 'B1', 'B2'],
        'odds_min': 10,
        'odds_max': 200,
        'venue_filter': None,
        'predicted_course': 5,
        'use_pattern_h': True,
    },
]

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}


def build_race_query(cond: Dict, date_start: str, date_end: str) -> str:
    """条件に該当するrace_idを取得するクエリを構築"""
    c1_rank_str = "','".join(cond['c1_rank'])

    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    c1_second_rate_clause = ""
    if cond.get('c1_second_rate_min') is not None:
        c1_second_rate_clause += f"AND e1.second_rate >= {cond['c1_second_rate_min']} "
    if cond.get('c1_second_rate_max') is not None:
        c1_second_rate_clause += f"AND e1.second_rate < {cond['c1_second_rate_max']} "

    month_exclude_clause = ""
    if cond.get('month_exclude'):
        months = ','.join(map(str, cond['month_exclude']))
        month_exclude_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({months})"

    escape_rate_join = ""
    escape_rate_clause = ""
    if cond.get('escape_rate_min') is not None:
        escape_rate_join = """
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        LEFT JOIN player_escape_stats pes ON e_pred.racer_number = pes.player_id AND pes.stadium_id IS NULL
        """
        escape_rate_clause = f"AND pes.escape_rate >= {cond['escape_rate_min']} "

    bias_join = ""
    bias_clause = ""
    if cond.get('bias_max') is not None:
        bias_join = """
        LEFT JOIN entries e_bias ON r.id = e_bias.race_id AND e_bias.pit_number = rp1.pit_number
        LEFT JOIN player_bias_stats pbs ON e_bias.racer_number = pbs.player_id AND pbs.stadium_id IS NULL
        """
        bias_clause = f"AND pbs.bias_index IS NOT NULL AND pbs.bias_index < {cond['bias_max']} "

    query = f'''
    SELECT DISTINCT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        rp1.pit_number as p1,
        rp2.pit_number as p2,
        rp3.pit_number as p3,
        COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                  AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)), 0) as odds_123,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    {escape_rate_join}
    {bias_join}
    WHERE rp.rank_prediction = 1
    AND rp.confidence = '{cond["confidence"]}'
    AND e1.racer_rank IN ('{c1_rank_str}')
    AND r.race_date >= '{date_start}'
    AND r.race_date < '{date_end}'
    {venue_clause}
    {predicted_course_clause}
    {c1_second_rate_clause}
    {month_exclude_clause}
    {escape_rate_clause}
    {bias_clause}
    '''

    return query


def get_condition_races(cursor, cond: Dict, date_start: str, date_end: str) -> Dict[int, Dict]:
    """条件に該当するレースを取得（オッズフィルター込み）"""
    query = build_race_query(cond, date_start, date_end)
    cursor.execute(query)
    rows = cursor.fetchall()

    races = {}
    for row in rows:
        race_id, race_date, venue_code, p1, p2, p3, odds, a1, a2, a3 = row
        # オッズフィルター
        if cond['odds_min'] <= odds < cond['odds_max']:
            is_hit = (p1 == a1 and p2 == a2 and p3 == a3)
            races[race_id] = {
                'race_id': race_id,
                'race_date': race_date,
                'venue_code': venue_code,
                'combination': f"{p1}-{p2}-{p3}",
                'odds': odds,
                'is_hit': is_hit,
                'payout': odds * 100 if is_hit else 0,
            }
    return races


def analyze_overlaps(cursor, date_start: str, date_end: str) -> Dict:
    """重複分析を実行"""
    results = {
        'period': f"{date_start} - {date_end}",
        'conditions': [],
        'overlap_matrix': {},
        'overlap_races': {},
        'race_condition_map': defaultdict(list),
    }

    # 各条件のレースを取得
    condition_races = {}
    for cond in CONDITIONS:
        races = get_condition_races(cursor, cond, date_start, date_end)
        condition_races[cond['name']] = races
        results['conditions'].append({
            'name': cond['name'],
            'confidence': cond['confidence'],
            'odds_range': f"{cond['odds_min']}-{cond['odds_max']}",
            'venue_filter': cond.get('venue_filter'),
            'race_count': len(races),
            'hits': sum(1 for r in races.values() if r['is_hit']),
            'total_payout': sum(r['payout'] for r in races.values()),
        })

        # race_id -> condition のマッピング
        for race_id in races:
            results['race_condition_map'][race_id].append(cond['name'])

    # 重複マトリックスを作成
    cond_names = [c['name'] for c in CONDITIONS]
    for i, name1 in enumerate(cond_names):
        for j, name2 in enumerate(cond_names):
            if i < j:
                races1 = set(condition_races[name1].keys())
                races2 = set(condition_races[name2].keys())
                overlap = races1 & races2
                results['overlap_matrix'][(name1, name2)] = {
                    'count': len(overlap),
                    'race_ids': list(overlap),
                }

    # 重複カウント別の集計
    overlap_counts = defaultdict(list)
    for race_id, conds in results['race_condition_map'].items():
        overlap_counts[len(conds)].append(race_id)

    results['overlap_distribution'] = {
        cnt: len(races) for cnt, races in overlap_counts.items()
    }

    # 重複レースの詳細情報を収集
    overlapping_races = []
    for race_id, conds in results['race_condition_map'].items():
        if len(conds) >= 2:
            # いずれかの条件から詳細を取得
            first_cond = conds[0]
            race_info = condition_races[first_cond][race_id]
            race_info['conditions'] = conds
            race_info['condition_count'] = len(conds)
            overlapping_races.append(race_info)

    results['overlapping_races'] = overlapping_races

    return results


def analyze_overlap_performance(results: Dict) -> Dict:
    """重複vs非重複のパフォーマンス比較"""
    overlapping = []
    non_overlapping = []

    for race_id, conds in results['race_condition_map'].items():
        # 該当条件のいずれかから情報を取得（1条件目を使用）
        if race_id in [r['race_id'] for r in results['overlapping_races']]:
            race_info = next(r for r in results['overlapping_races'] if r['race_id'] == race_id)
            overlapping.append(race_info)
        # 非重複は集計が複雑なので別途計算

    overlap_stats = {
        'count': len([r for r in results['race_condition_map'].items() if len(r[1]) >= 2]),
        'hits': sum(1 for r in overlapping if r['is_hit']),
        'investment': len(overlapping) * 100,  # 簡易計算
        'payout': sum(r['payout'] for r in overlapping),
    }
    if overlap_stats['investment'] > 0:
        overlap_stats['roi'] = 100.0 * overlap_stats['payout'] / overlap_stats['investment']
    else:
        overlap_stats['roi'] = 0

    non_overlap_count = len([r for r in results['race_condition_map'].items() if len(r[1]) == 1])
    # 非重複の詳細は集計が複雑なため概算

    return {
        'overlapping': overlap_stats,
        'non_overlapping': {'count': non_overlap_count},
    }


def analyze_venue_correlation(results: Dict, cursor) -> Dict:
    """会場依存の相関分析"""
    venue_stats = defaultdict(lambda: {'conditions': set(), 'race_count': 0})

    for cond_info in results['conditions']:
        if cond_info['venue_filter']:
            for venue in cond_info['venue_filter']:
                venue_stats[venue]['conditions'].add(cond_info['name'])

    # 同じ会場を使う条件ペアを抽出
    venue_overlaps = {}
    for venue, stats in venue_stats.items():
        if len(stats['conditions']) >= 2:
            venue_name = VENUE_NAMES.get(venue, str(venue))
            venue_overlaps[venue_name] = list(stats['conditions'])

    return venue_overlaps


def analyze_confidence_correlation(results: Dict) -> Dict:
    """信頼度依存の相関分析"""
    confidence_groups = defaultdict(list)

    for cond_info in results['conditions']:
        confidence_groups[cond_info['confidence']].append(cond_info['name'])

    return dict(confidence_groups)


def analyze_odds_correlation(results: Dict) -> Dict:
    """オッズ帯依存の相関分析"""
    odds_ranges = defaultdict(list)

    for cond in CONDITIONS:
        odds_range = f"{cond['odds_min']}-{cond['odds_max']}"
        odds_ranges[odds_range].append(cond['name'])

    return dict(odds_ranges)


def analyze_concentration_risk(results: Dict) -> Dict:
    """収益集中リスクの分析"""
    # 大きな払戻があるレースを特定
    high_payout_races = []
    for race in results['overlapping_races']:
        if race['is_hit'] and race['payout'] >= 3000:  # 3000円以上を大きな的中とする
            high_payout_races.append(race)

    # 重複レースでの大きな的中
    overlap_high_payouts = [r for r in high_payout_races if r['condition_count'] >= 2]

    return {
        'high_payout_races': len(high_payout_races),
        'overlap_high_payouts': len(overlap_high_payouts),
        'details': [
            {
                'race_id': r['race_id'],
                'payout': r['payout'],
                'conditions': r['conditions'],
            }
            for r in overlap_high_payouts[:10]  # 上位10件
        ],
    }


def main():
    print("=" * 100)
    print("購入条件間の重複分析")
    print("=" * 100)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 6年間の分析
    date_start = "2020-01-01"
    date_end = "2026-01-01"

    print(f"分析期間: {date_start} - {date_end}")
    print()

    # 重複分析を実行
    results = analyze_overlaps(cursor, date_start, date_end)

    # ============================================================
    # 1. 条件別の件数サマリー
    # ============================================================
    print("[1. 条件別の購入件数]")
    print("-" * 80)
    print(f"{'条件名':<30} {'信頼度':>4} {'オッズ帯':>10} {'件数':>8} {'的中':>5} {'払戻':>10}")
    print("-" * 80)

    total_races = 0
    for cond in results['conditions']:
        venue_str = "あり" if cond['venue_filter'] else "-"
        print(f"{cond['name']:<30} {cond['confidence']:>4} {cond['odds_range']:>10} {cond['race_count']:>8} {cond['hits']:>5} {cond['total_payout']:>10,}")
        total_races += cond['race_count']

    print("-" * 80)
    print(f"{'合計（延べ）':<30} {'':<4} {'':<10} {total_races:>8}")
    print()

    # ============================================================
    # 2. 重複分布
    # ============================================================
    print("[2. 重複分布（同一レースを何条件が購入しているか）]")
    print("-" * 60)
    unique_races = len(results['race_condition_map'])
    print(f"ユニークレース数: {unique_races}件")
    print(f"延べ購入レース数: {total_races}件")
    print(f"重複率: {100.0 * (total_races - unique_races) / total_races:.1f}%")
    print()

    print(f"{'条件数':>8} {'レース数':>10} {'割合':>8}")
    print("-" * 30)
    for cnt in sorted(results['overlap_distribution'].keys()):
        race_count = results['overlap_distribution'][cnt]
        pct = 100.0 * race_count / unique_races
        print(f"{cnt:>8} {race_count:>10} {pct:>7.1f}%")
    print()

    # ============================================================
    # 3. 条件ペア別の重複数
    # ============================================================
    print("[3. 条件ペア別の重複数（上位20件）]")
    print("-" * 80)

    sorted_pairs = sorted(
        results['overlap_matrix'].items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )

    print(f"{'条件1':<25} {'条件2':<25} {'重複数':>10}")
    print("-" * 80)
    for (name1, name2), data in sorted_pairs[:20]:
        if data['count'] > 0:
            print(f"{name1:<25} {name2:<25} {data['count']:>10}")
    print()

    # ============================================================
    # 4. 重複レースのパフォーマンス
    # ============================================================
    print("[4. 重複レースのパフォーマンス]")
    print("-" * 60)

    overlap_perf = analyze_overlap_performance(results)
    overlap = overlap_perf['overlapping']
    print(f"重複レース数（2条件以上）: {overlap['count']}件")
    print(f"  的中数: {overlap['hits']}件")
    print(f"  的中率: {100.0 * overlap['hits'] / overlap['count']:.2f}%" if overlap['count'] > 0 else "  的中率: -")
    print(f"  ROI: {overlap['roi']:.1f}%" if overlap['investment'] > 0 else "  ROI: -")
    print()
    print(f"非重複レース数（1条件のみ）: {overlap_perf['non_overlapping']['count']}件")
    print()

    # ============================================================
    # 5. 会場依存の相関
    # ============================================================
    print("[5. 同じ会場を使う条件ペア]")
    print("-" * 80)

    venue_corr = analyze_venue_correlation(results, cursor)
    if venue_corr:
        for venue, conds in venue_corr.items():
            print(f"  {venue}: {', '.join(conds)}")
    else:
        print("  なし")
    print()

    # ============================================================
    # 6. 信頼度依存の相関
    # ============================================================
    print("[6. 同じ信頼度を使う条件グループ]")
    print("-" * 60)

    conf_corr = analyze_confidence_correlation(results)
    for conf, conds in sorted(conf_corr.items()):
        print(f"  信頼度{conf}: {len(conds)}条件")
        for c in conds:
            print(f"    - {c}")
    print()

    # ============================================================
    # 7. オッズ帯依存の相関
    # ============================================================
    print("[7. 同じオッズ帯を使う条件グループ]")
    print("-" * 60)

    odds_corr = analyze_odds_correlation(results)
    for odds_range, conds in sorted(odds_corr.items()):
        if len(conds) >= 2:
            print(f"  {odds_range}倍: {len(conds)}条件")
            for c in conds:
                print(f"    - {c}")
    print()

    # ============================================================
    # 8. リスク集中分析
    # ============================================================
    print("[8. リスク集中分析（大きな的中が重複で起きているか）]")
    print("-" * 80)

    risk_analysis = analyze_concentration_risk(results)
    print(f"大きな的中（3000円以上）: {risk_analysis['high_payout_races']}件")
    print(f"うち重複レース: {risk_analysis['overlap_high_payouts']}件")
    print()

    if risk_analysis['details']:
        print("重複レースでの大きな的中（上位10件）:")
        for detail in risk_analysis['details']:
            print(f"  race_id={detail['race_id']}: 払戻{detail['payout']:,}円, 条件: {', '.join(detail['conditions'])}")
    print()

    # ============================================================
    # 9. 年度別重複分析
    # ============================================================
    print("[9. 年度別重複分析]")
    print("-" * 70)
    print(f"{'年度':>6} {'ユニーク':>10} {'延べ':>10} {'重複率':>8} {'2条件以上':>10}")
    print("-" * 70)

    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        year_start = f"{year}-01-01"
        year_end = f"{year + 1}-01-01"
        year_results = analyze_overlaps(cursor, year_start, year_end)

        year_total = sum(c['race_count'] for c in year_results['conditions'])
        year_unique = len(year_results['race_condition_map'])
        year_overlap_rate = 100.0 * (year_total - year_unique) / year_total if year_total > 0 else 0
        year_multi = len([r for r in year_results['race_condition_map'].items() if len(r[1]) >= 2])

        print(f"{year:>6} {year_unique:>10} {year_total:>10} {year_overlap_rate:>7.1f}% {year_multi:>10}")

    print()

    # ============================================================
    # サマリーと推奨事項
    # ============================================================
    print("=" * 100)
    print("分析サマリーと推奨事項")
    print("=" * 100)
    print()

    overlap_2plus = len([r for r in results['race_condition_map'].items() if len(r[1]) >= 2])
    overlap_rate = 100.0 * overlap_2plus / unique_races if unique_races > 0 else 0

    print(f"1. 真の分散効果:")
    print(f"   - 10条件による延べ購入数: {total_races}件")
    print(f"   - ユニークレース数: {unique_races}件（実質的な分散）")
    print(f"   - 重複レース数（2条件以上）: {overlap_2plus}件（{overlap_rate:.1f}%）")
    print()

    print(f"2. リスク集中度:")
    if overlap_2plus > 0:
        print(f"   - 重複レースの{overlap_rate:.1f}%で同じレースに複数条件が賭けている")
        print(f"   - 大きな的中{risk_analysis['high_payout_races']}件のうち{risk_analysis['overlap_high_payouts']}件が重複")
    else:
        print(f"   - 重複なし（真の分散）")
    print()

    print(f"3. 条件間の相関:")
    print(f"   - 同一会場を使う条件ペア: {len(venue_corr)}組")
    print(f"   - 同一信頼度の条件グループ: {len(conf_corr)}グループ")
    print()

    print(f"4. 対策案:")
    if overlap_rate > 20:
        print(f"   - 重複率が高い（{overlap_rate:.1f}%）ため、条件の統合または除外を検討")
    else:
        print(f"   - 重複率は許容範囲（{overlap_rate:.1f}%）")

    high_overlap_pairs = [(n1, n2, d['count']) for (n1, n2), d in sorted_pairs if d['count'] > 50]
    if high_overlap_pairs:
        print(f"   - 重複が多い条件ペア:")
        for n1, n2, cnt in high_overlap_pairs[:5]:
            print(f"     * {n1} + {n2}: {cnt}件")
    print()

    conn.close()


if __name__ == '__main__':
    main()
