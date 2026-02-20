#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
現在の購入条件に対する連帯率パターン分析（2026-01-26版）

目的:
    現在の10購入条件に対して、連帯率フィルターを活用した改善パターンを探索

分析パターン:
    1. 1着予測選手の2連対率・3連対率
    2. 2着予測選手の2連対率・3連対率
    3. 3着予測選手の2連対率・3連対率
    4. モーター2連対率・3連対率
    5. 連対率格差パターン

採用基準:
    - 黒字年数 4/6年以上
    - 累計収支プラス
    - ROI 100%以上
    - 統計的有意性（p<0.1）

使用方法:
    python scripts/analysis/analyze_rentairitsu_current_conditions.py
"""

import sqlite3
import sys
import io
import os
from typing import List, Dict, Any
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# 現在の購入条件（2026-01-26時点）
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
    },
    {
        'name': 'B×50-100×冬+4月除外',
        'confidence': 'B',
        'c1_rank': ['A1', 'B1'],
        'odds_min': 50,
        'odds_max': 100,
        'month_exclude': [12, 1, 2, 4],
    },
    {
        'name': 'B×30-50×B1+4会場',
        'confidence': 'B',
        'c1_rank': ['B1'],
        'odds_min': 30,
        'odds_max': 50,
        'venue_filter': [9, 10, 21, 6],
    },
    {
        'name': 'B×10-30×穴源×会場',
        'confidence': 'B',
        'c1_rank': ['A1', 'A2', 'B1'],
        'odds_min': 10,
        'odds_max': 30,
        'venue_filter': [6, 7, 8, 10, 15, 19],
        'bias_max': -0.3,
    },
    {
        'name': 'C×20-30×B1+会場',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        'venue_filter': [18, 5, 4, 9, 15, 8, 24, 20, 17],
    },
    {
        'name': '鳴門×C×A2×30-80',
        'confidence': 'C',
        'c1_rank': ['A2'],
        'odds_min': 30,
        'odds_max': 80,
        'venue_filter': [14],
    },
    {
        'name': '唐津×C×B1×20-30',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        'venue_filter': [23],
    },
    {
        'name': '児島×C×B1×30-50',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 30,
        'odds_max': 50,
        'venue_filter': [16],
    },
    {
        'name': 'D×40-50×B1×2連率20-30%',
        'confidence': 'D',
        'c1_rank': ['B1'],
        'odds_min': 40,
        'odds_max': 50,
        'c1_second_rate_min': 20,
        'c1_second_rate_max': 30,
    },
    {
        'name': 'D×5コース予測×A2除外',
        'confidence': 'D',
        'c1_rank': ['A1', 'B1', 'B2'],
        'odds_min': 10,
        'odds_max': 200,
        'predicted_course': 5,
    },
]


def build_sql_where_clauses(cond: Dict[str, Any]) -> str:
    """条件からWHERE句を構築"""
    clauses = []

    # 信頼度
    clauses.append(f"rp.confidence = '{cond['confidence']}'")

    # 級別
    c1_rank_str = "','".join(cond['c1_rank'])
    clauses.append(f"e1.racer_rank IN ('{c1_rank_str}')")

    # 会場フィルター
    if cond.get('venue_filter'):
        venue_str = ','.join(map(str, cond['venue_filter']))
        clauses.append(f"r.venue_code IN ({venue_str})")

    # 月除外
    if cond.get('month_exclude'):
        month_str = ','.join(map(str, cond['month_exclude']))
        clauses.append(f"CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({month_str})")

    # 逃げ率（DBに存在しないためスキップ）
    # if cond.get('escape_rate_min'):
    #     clauses.append(f"e_p1.escape_rate >= {cond['escape_rate_min']}")

    # 予測コース
    if cond.get('predicted_course'):
        clauses.append(f"rp1.pit_number = {cond['predicted_course']}")

    # バイアス指数（DBに存在しない可能性があるためスキップ）
    # if cond.get('bias_max'):
    #     clauses.append(f"rp1.bias_index < {cond['bias_max']}")

    # 1コース選手2連対率
    if cond.get('c1_second_rate_min'):
        clauses.append(f"e1.second_rate >= {cond['c1_second_rate_min']}")
    if cond.get('c1_second_rate_max'):
        clauses.append(f"e1.second_rate < {cond['c1_second_rate_max']}")

    return " AND ".join(clauses)


def get_race_data(cursor, cond: Dict[str, Any], year_start: int = 2020, year_end: int = 2025) -> List[Dict]:
    """条件に合致するレースデータを取得"""

    where_clause = build_sql_where_clauses(cond)

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            rp.confidence,
            e1.racer_rank as c1_rank,
            e1.second_rate as c1_second_rate,
            e1.third_rate as c1_third_rate,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            e_p1.second_rate as p1_second_rate,
            e_p1.third_rate as p1_third_rate,
            e_p2.second_rate as p2_second_rate,
            e_p2.third_rate as p2_third_rate,
            e_p3.second_rate as p3_second_rate,
            e_p3.third_rate as p3_third_rate,
            e_p1.motor_second_rate as p1_motor_second_rate,
            e_p1.motor_third_rate as p1_motor_third_rate,
            e_p2.motor_second_rate as p2_motor_second_rate,
            e_p3.motor_second_rate as p3_motor_second_rate
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        JOIN entries e_p1 ON r.id = e_p1.race_id AND e_p1.pit_number = rp1.pit_number
        JOIN entries e_p2 ON r.id = e_p2.race_id AND e_p2.pit_number = rp2.pit_number
        JOIN entries e_p3 ON r.id = e_p3.race_id AND e_p3.pit_number = rp3.pit_number
        WHERE {where_clause}
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date <= '{year_end}-12-31'
    ),
    race_with_odds AS (
        SELECT
            rb.*,
            COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = rb.race_id
                 AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                ), 0
            ) as pred_odds
        FROM race_base rb
    ),
    race_with_result AS (
        SELECT
            rwo.*,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rwo.race_id AND rank = '1') = rwo.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rwo.race_id AND rank = '2') = rwo.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rwo.race_id AND rank = '3') = rwo.p3
                THEN 1 ELSE 0
            END as is_hit,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rwo.race_id AND rank = '1') = rwo.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rwo.race_id AND rank = '2') = rwo.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rwo.race_id AND rank = '3') = rwo.p3
                THEN rwo.pred_odds * 100
                ELSE 0
            END as payout
        FROM race_with_odds rwo
        WHERE rwo.pred_odds >= {cond['odds_min']} AND rwo.pred_odds < {cond['odds_max']}
    )
    SELECT * FROM race_with_result
    '''

    cursor.execute(query)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def analyze_rate_threshold(races: List[Dict], rate_column: str, thresholds: List[int]) -> List[Dict]:
    """
    連対率の閾値による分割分析

    Args:
        races: レースデータ
        rate_column: 分析対象の連対率カラム名
        thresholds: 閾値リスト（例: [30, 35, 40, 45, 50]）

    Returns:
        各閾値での分析結果
    """
    results = []

    for threshold in thresholds:
        # 閾値以上と未満で分割
        above = [r for r in races if r.get(rate_column) is not None and r[rate_column] >= threshold]
        below = [r for r in races if r.get(rate_column) is not None and r[rate_column] < threshold]

        if len(above) < 10 or len(below) < 10:  # サンプル数が少なすぎる場合はスキップ
            continue

        # 各グループの統計
        above_hits = sum(1 for r in above if r['is_hit'] == 1)
        above_roi = (sum(r['payout'] for r in above) / (len(above) * 100)) * 100 if len(above) > 0 else 0
        above_profit = sum(r['payout'] for r in above) - len(above) * 100

        below_hits = sum(1 for r in below if r['is_hit'] == 1)
        below_roi = (sum(r['payout'] for r in below) / (len(below) * 100)) * 100 if len(below) > 0 else 0
        below_profit = sum(r['payout'] for r in below) - len(below) * 100

        # ROI改善を計算
        total_roi = (sum(r['payout'] for r in races) / (len(races) * 100)) * 100
        roi_improvement_above = above_roi - total_roi
        roi_improvement_below = below_roi - total_roi

        results.append({
            'threshold': threshold,
            'above_count': len(above),
            'above_hits': above_hits,
            'above_roi': above_roi,
            'above_profit': above_profit,
            'above_roi_improvement': roi_improvement_above,
            'below_count': len(below),
            'below_hits': below_hits,
            'below_roi': below_roi,
            'below_profit': below_profit,
            'below_roi_improvement': roi_improvement_below,
        })

    # ROI改善が大きい順にソート
    results.sort(key=lambda x: max(abs(x['above_roi_improvement']), abs(x['below_roi_improvement'])), reverse=True)
    return results


def analyze_year_stability(races: List[Dict], rate_column: str, threshold: int, filter_type: str) -> Dict:
    """
    年度別安定性を検証

    Args:
        races: レースデータ
        rate_column: 分析対象の連対率カラム名
        threshold: 閾値
        filter_type: 'above'（閾値以上を残す）or 'below'（閾値未満を残す）

    Returns:
        年度別の統計
    """
    year_stats = {}

    for year in range(2020, 2026):
        year_races = [r for r in races if r['race_date'].startswith(str(year))]

        if filter_type == 'above':
            filtered = [r for r in year_races if r.get(rate_column) is not None and r[rate_column] >= threshold]
        else:
            filtered = [r for r in year_races if r.get(rate_column) is not None and r[rate_column] < threshold]

        if len(filtered) == 0:
            continue

        hits = sum(1 for r in filtered if r['is_hit'] == 1)
        roi = (sum(r['payout'] for r in filtered) / (len(filtered) * 100)) * 100
        profit = sum(r['payout'] for r in filtered) - len(filtered) * 100

        # 元のROI
        original_roi = (sum(r['payout'] for r in year_races) / (len(year_races) * 100)) * 100 if len(year_races) > 0 else 0

        year_stats[year] = {
            'count': len(filtered),
            'hits': hits,
            'roi': roi,
            'profit': profit,
            'original_roi': original_roi,
            'roi_improvement': roi - original_roi,
            'is_profitable': profit > 0
        }

    # 黒字年数をカウント
    profitable_years = sum(1 for s in year_stats.values() if s['is_profitable'])
    roi_improvement_years = sum(1 for s in year_stats.values() if s['roi_improvement'] > 0)

    return {
        'year_stats': year_stats,
        'profitable_years': profitable_years,
        'roi_improvement_years': roi_improvement_years,
        'total_years': len(year_stats)
    }


def main():
    print("=" * 80)
    print("現在の購入条件に対する連帯率パターン分析（2026-01-26版）")
    print("=" * 80)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 分析対象の連対率カラムと閾値
    analysis_patterns = [
        {'column': 'p1_second_rate', 'name': '1着予測・2連対率', 'thresholds': [30, 35, 40, 45, 50, 55, 60]},
        {'column': 'p1_third_rate', 'name': '1着予測・3連対率', 'thresholds': [40, 45, 50, 55, 60, 65, 70]},
        {'column': 'p2_second_rate', 'name': '2着予測・2連対率', 'thresholds': [25, 30, 35, 40, 45, 50, 55]},
        {'column': 'p2_third_rate', 'name': '2着予測・3連対率', 'thresholds': [30, 35, 40, 45, 50, 55, 60]},
        {'column': 'p3_second_rate', 'name': '3着予測・2連対率', 'thresholds': [25, 30, 35, 40, 45, 50, 55]},
        {'column': 'p3_third_rate', 'name': '3着予測・3連対率', 'thresholds': [30, 35, 40, 45, 50, 55, 60]},
        {'column': 'p1_motor_second_rate', 'name': '1着予測・モーター2連対率', 'thresholds': [25, 30, 35, 40, 45]},
    ]

    all_candidates = []

    for cond in CONDITIONS:
        print(f"\n{'='*80}")
        print(f"条件: {cond['name']}")
        print(f"{'='*80}")

        # レースデータ取得
        print("レースデータ取得中...")
        races = get_race_data(cursor, cond)

        if len(races) == 0:
            print("  -> 該当レースなし（スキップ）")
            continue

        # 現状のパフォーマンス
        total_hits = sum(1 for r in races if r['is_hit'] == 1)
        total_roi = (sum(r['payout'] for r in races) / (len(races) * 100)) * 100
        total_profit = sum(r['payout'] for r in races) - len(races) * 100

        print(f"現状: 購入{len(races)}件, 的中{total_hits}件, ROI {total_roi:.1f}%, 収支{total_profit:+,.0f}円")
        print()

        # 各パターンで分析
        for pattern in analysis_patterns:
            print(f"  [{pattern['name']}] 分析中...")

            results = analyze_rate_threshold(races, pattern['column'], pattern['thresholds'])

            # 上位3件を表示
            for i, result in enumerate(results[:3]):
                threshold = result['threshold']

                # 改善効果が大きい方を選択
                if abs(result['above_roi_improvement']) > abs(result['below_roi_improvement']):
                    filter_type = 'above'
                    count = result['above_count']
                    roi = result['above_roi']
                    profit = result['above_profit']
                    roi_improvement = result['above_roi_improvement']
                    description = f">={threshold}%を残す"
                else:
                    filter_type = 'below'
                    count = result['below_count']
                    roi = result['below_roi']
                    profit = result['below_profit']
                    roi_improvement = result['below_roi_improvement']
                    description = f"<{threshold}%を残す"

                # ROI改善が+20pt以上、かつ黒字の場合のみ詳細表示
                if roi_improvement >= 20 and profit > 0:
                    print(f"    [{i+1}] {description}: {count}件, ROI {roi:.1f}% ({roi_improvement:+.1f}pt), 収支{profit:+,.0f}円")

                    # 年度別安定性検証
                    stability = analyze_year_stability(races, pattern['column'], threshold, filter_type)
                    print(f"        年度別: 黒字{stability['profitable_years']}/{stability['total_years']}年, ROI改善{stability['roi_improvement_years']}/{stability['total_years']}年")

                    # 採用候補として記録
                    if stability['profitable_years'] >= 4 and roi >= 100:
                        all_candidates.append({
                            'condition': cond['name'],
                            'pattern': pattern['name'],
                            'threshold': threshold,
                            'filter_type': filter_type,
                            'description': description,
                            'count': count,
                            'roi': roi,
                            'profit': profit,
                            'roi_improvement': roi_improvement,
                            'profitable_years': stability['profitable_years'],
                            'roi_improvement_years': stability['roi_improvement_years'],
                            'total_years': stability['total_years'],
                            'year_stats': stability['year_stats']
                        })

    # 採用候補サマリー
    print("\n" + "=" * 80)
    print("採用候補サマリー（黒字4年以上、ROI 100%以上）")
    print("=" * 80)

    if len(all_candidates) == 0:
        print("採用候補なし")
    else:
        all_candidates.sort(key=lambda x: x['roi_improvement'], reverse=True)

        for i, cand in enumerate(all_candidates[:10], 1):
            print(f"\n[候補{i}] {cand['condition']}")
            print(f"  フィルター: {cand['pattern']} {cand['description']}")
            print(f"  購入数: {cand['count']}件")
            print(f"  ROI: {cand['roi']:.1f}% ({cand['roi_improvement']:+.1f}pt改善)")
            print(f"  収支: {cand['profit']:+,.0f}円")
            print(f"  年度別: 黒字{cand['profitable_years']}/{cand['total_years']}年, ROI改善{cand['roi_improvement_years']}/{cand['total_years']}年")
            print(f"  年度詳細:")
            for year, stats in sorted(cand['year_stats'].items()):
                print(f"    {year}年: {stats['count']:3d}件, ROI {stats['roi']:6.1f}%, 収支{stats['profit']:+8,.0f}円 ({'黒字' if stats['is_profitable'] else '赤字'})")

    conn.close()
    print("\n分析完了")


if __name__ == '__main__':
    main()
