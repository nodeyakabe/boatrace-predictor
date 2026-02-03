#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不採用案再検証テンプレート

データ補完後に不採用案を正しく再評価するためのテンプレート。
正しいオッズ取得・的中判定ロジックを組み込み済み。

作成日: 2026-01-30
参照: scripts/backtest/standard_backtest.py

重要な設計原則:
- オッズは「予測組み合わせ」に対して取得する（1-2-3固定ではない）
- 的中判定は「予測組み合わせ == 実際の結果組み合わせ」で判定

使い方:
    # 基本的な使用例
    python scripts/templates/rejected_idea_review_template.py \
        --confidence B \
        --odds-min 50 \
        --odds-max 100

    # 1コース級別指定
    python scripts/templates/rejected_idea_review_template.py \
        --confidence B \
        --odds-min 30 \
        --odds-max 50 \
        --c1-rank B1

    # モーター2連対率フィルター追加
    python scripts/templates/rejected_idea_review_template.py \
        --confidence A \
        --odds-min 10 \
        --odds-max 30 \
        --motor-second-rate-min 40

    # 会場フィルター（会場コードで指定）
    python scripts/templates/rejected_idea_review_template.py \
        --confidence C \
        --odds-min 20 \
        --odds-max 30 \
        --venue-filter 6 7 8 10  # 浜名湖,蒲郡,常滑,三国

    # 冬季除外（12月, 1月, 2月）
    python scripts/templates/rejected_idea_review_template.py \
        --confidence B \
        --odds-min 50 \
        --odds-max 100 \
        --month-exclude 12 1 2

出力:
    - 6年間の年度別ROI、収支、的中率、サンプル数
    - 黒字年数判定
    - 採用基準の自動判定
    - standard_backtest.pyでの検証コマンド
"""

import sqlite3
import sys
import io
import os
import argparse
from typing import List, Optional, Dict
from datetime import datetime

# Windows環境でのUTF-8出力対応
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# 会場名マッピング
VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

# 採用基準
ADOPTION_CRITERIA = {
    'black_years_min': 4,       # 黒字年数: 4/6年以上
    'total_profit_min': 0,      # 累計収支: プラス
    'roi_min': 100.0,           # ROI: 100%以上
    'sample_min': 100,          # サンプル数: 100件以上
}


def build_analysis_query(
    confidence: str,
    odds_min: float,
    odds_max: float,
    c1_rank: Optional[List[str]] = None,
    motor_second_rate_min: Optional[float] = None,
    venue_filter: Optional[List[int]] = None,
    month_exclude: Optional[List[int]] = None,
    date_start: str = '2020-01-01',
    date_end: str = '2026-01-01'
) -> str:
    """
    正しいオッズ取得・的中判定ロジックを含むSQLクエリを構築

    ポイント:
    - オッズは予測組み合わせ（p1-p2-p3）に対して取得
    - 的中判定は予測組み合わせ == 実際の結果組み合わせで判定
    """

    # 1コース級別フィルター
    c1_rank_clause = ""
    if c1_rank:
        c1_rank_str = "','".join(c1_rank)
        c1_rank_clause = f"AND e1.racer_rank IN ('{c1_rank_str}')"
    else:
        c1_rank_clause = "AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')"

    # 会場フィルター
    venue_clause = ""
    if venue_filter:
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, venue_filter))})"

    # モーター2連対率フィルター（1着予測選手のモーター）
    motor_join = ""
    motor_clause = ""
    if motor_second_rate_min is not None:
        motor_join = """
        LEFT JOIN entries e_motor ON r.id = e_motor.race_id AND e_motor.pit_number = rp1.pit_number
        """
        motor_clause = f"AND e_motor.motor_second_rate >= {motor_second_rate_min}"

    # 月除外フィルター
    month_exclude_clause = ""
    if month_exclude:
        months = ','.join(map(str, month_exclude))
        month_exclude_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({months})"

    query = f'''
    WITH prediction_combos AS (
        -- 予測組み合わせを取得（予測1着-予測2着-予測3着）
        SELECT
            rp1.race_id,
            r.race_date,
            r.venue_code,
            rp1.confidence,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races r ON rp1.race_id = r.id
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        {motor_join}
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND rp1.confidence = '{confidence}'
          AND r.race_date >= '{date_start}'
          AND r.race_date < '{date_end}'
          {c1_rank_clause}
          {venue_clause}
          {motor_clause}
          {month_exclude_clause}
    ),
    actual_combos AS (
        -- 実際の結果組み合わせを取得（実際1着-実際2着-実際3着）
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    race_with_odds AS (
        SELECT
            pc.race_id,
            pc.race_date,
            pc.venue_code,
            pc.pred_combo,
            -- 予測組み合わせのオッズを取得（これが重要！）
            COALESCE(t.odds, 0) as odds,
            -- 的中判定（予測 == 実際）
            CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END as is_hit
        FROM prediction_combos pc
        JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
        JOIN actual_combos ac ON pc.race_id = ac.race_id
    )
    SELECT
        strftime('%Y', race_date) as year,
        COUNT(*) as total_bets,
        SUM(CASE WHEN odds >= {odds_min} AND odds < {odds_max} THEN 1 ELSE 0 END) as filtered_bets,
        SUM(CASE WHEN odds >= {odds_min} AND odds < {odds_max} AND is_hit = 1 THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN odds >= {odds_min} AND odds < {odds_max} THEN 100 ELSE 0 END) as investment,
        SUM(CASE WHEN odds >= {odds_min} AND odds < {odds_max} AND is_hit = 1 THEN odds * 100 ELSE 0 END) as payout
    FROM race_with_odds
    GROUP BY strftime('%Y', race_date)
    ORDER BY year
    '''
    return query


def analyze_condition(
    confidence: str,
    odds_min: float,
    odds_max: float,
    c1_rank: Optional[List[str]] = None,
    motor_second_rate_min: Optional[float] = None,
    venue_filter: Optional[List[int]] = None,
    month_exclude: Optional[List[int]] = None
) -> Dict:
    """
    購入条件の分析

    Returns:
        dict: {
            'yearly_results': [...],  # 年度別成績リスト
            'total': {...},           # 合計成績
            'adoption_check': {...},  # 採用基準チェック結果
            'params': {...},          # 入力パラメータ
        }
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # クエリ構築・実行
    query = build_analysis_query(
        confidence=confidence,
        odds_min=odds_min,
        odds_max=odds_max,
        c1_rank=c1_rank,
        motor_second_rate_min=motor_second_rate_min,
        venue_filter=venue_filter,
        month_exclude=month_exclude
    )

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    # 年度別結果の整形
    yearly_results = []
    total_bets = 0
    total_hits = 0
    total_investment = 0
    total_payout = 0

    for row in rows:
        year, _, filtered_bets, hits, investment, payout = row
        if filtered_bets and filtered_bets > 0:
            hits = hits or 0
            investment = investment or 0
            payout = payout or 0
            roi = 100.0 * payout / investment if investment > 0 else 0
            profit = payout - investment
            hit_rate = 100.0 * hits / filtered_bets if filtered_bets > 0 else 0

            yearly_results.append({
                'year': int(year),
                'bets': filtered_bets,
                'hits': hits,
                'hit_rate': hit_rate,
                'investment': investment,
                'payout': payout,
                'roi': roi,
                'profit': profit,
            })

            total_bets += filtered_bets
            total_hits += hits
            total_investment += investment
            total_payout += payout

    # 合計成績
    total_roi = 100.0 * total_payout / total_investment if total_investment > 0 else 0
    total_profit = total_payout - total_investment
    total_hit_rate = 100.0 * total_hits / total_bets if total_bets > 0 else 0

    total_result = {
        'bets': total_bets,
        'hits': total_hits,
        'hit_rate': total_hit_rate,
        'investment': total_investment,
        'payout': total_payout,
        'roi': total_roi,
        'profit': total_profit,
    }

    # 採用基準チェック
    black_years = sum(1 for y in yearly_results if y['profit'] > 0)
    adoption_check = {
        'black_years': black_years,
        'black_years_pass': black_years >= ADOPTION_CRITERIA['black_years_min'],
        'profit_pass': total_profit > ADOPTION_CRITERIA['total_profit_min'],
        'roi_pass': total_roi >= ADOPTION_CRITERIA['roi_min'],
        'sample_pass': total_bets >= ADOPTION_CRITERIA['sample_min'],
    }
    adoption_check['all_pass'] = all([
        adoption_check['black_years_pass'],
        adoption_check['profit_pass'],
        adoption_check['roi_pass'],
        adoption_check['sample_pass'],
    ])

    return {
        'yearly_results': yearly_results,
        'total': total_result,
        'adoption_check': adoption_check,
        'params': {
            'confidence': confidence,
            'odds_min': odds_min,
            'odds_max': odds_max,
            'c1_rank': c1_rank,
            'motor_second_rate_min': motor_second_rate_min,
            'venue_filter': venue_filter,
            'month_exclude': month_exclude,
        }
    }


def generate_backtest_command(params: Dict) -> str:
    """standard_backtest.py用の条件定義を生成"""
    cond_dict = {
        'name': f"{params['confidence']}x{params['odds_min']}-{params['odds_max']}",
        'confidence': params['confidence'],
        'odds_min': params['odds_min'],
        'odds_max': params['odds_max'],
    }

    if params.get('c1_rank'):
        cond_dict['c1_rank'] = params['c1_rank']
    else:
        cond_dict['c1_rank'] = ['A1', 'A2', 'B1', 'B2']

    if params.get('venue_filter'):
        cond_dict['venue_filter'] = params['venue_filter']
    else:
        cond_dict['venue_filter'] = None

    if params.get('month_exclude'):
        cond_dict['month_exclude'] = params['month_exclude']

    if params.get('motor_second_rate_min'):
        cond_dict['p1_motor_second_rate_min'] = params['motor_second_rate_min']

    # パターンH使用判定（オッズ30倍以上は3点買い推奨）
    use_pattern_h = params['odds_min'] >= 30
    cond_dict['use_pattern_h'] = use_pattern_h
    cond_dict['description'] = f"再検証: {params['confidence']}x{params['odds_min']}-{params['odds_max']}倍"

    return cond_dict


def print_results(results: Dict):
    """結果を整形して出力"""
    params = results['params']
    total = results['total']
    yearly = results['yearly_results']
    check = results['adoption_check']

    print()
    print("=" * 90)
    print("不採用案再検証結果")
    print("=" * 90)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 条件表示
    print("[検証条件]")
    print("-" * 60)
    print(f"  信頼度: {params['confidence']}")
    print(f"  オッズ範囲: {params['odds_min']}倍 - {params['odds_max']}倍")
    if params.get('c1_rank'):
        print(f"  1コース級別: {', '.join(params['c1_rank'])}")
    if params.get('motor_second_rate_min'):
        print(f"  モーター2連対率: {params['motor_second_rate_min']}%以上")
    if params.get('venue_filter'):
        venue_names = [VENUE_NAMES.get(v, str(v)) for v in params['venue_filter']]
        print(f"  会場フィルター: {', '.join(venue_names)}")
    if params.get('month_exclude'):
        print(f"  除外月: {', '.join(map(str, params['month_exclude']))}月")
    print()

    # 年度別成績
    print("[年度別パフォーマンス]")
    print("-" * 80)
    print(f"{'年度':>6} {'件数':>8} {'的中':>5} {'的中率':>8} {'ROI':>9} {'収支':>14} {'判定'}")
    print("-" * 80)

    for y in yearly:
        status = "○黒字" if y['profit'] > 0 else "×赤字"
        print(f"{y['year']:>6} {y['bets']:>8} {y['hits']:>5} {y['hit_rate']:>7.2f}% {y['roi']:>8.1f}% {y['profit']:>+14,.0f} {status}")

    print("-" * 80)
    print(f"{'合計':>6} {total['bets']:>8} {total['hits']:>5} {total['hit_rate']:>7.2f}% {total['roi']:>8.1f}% {total['profit']:>+14,.0f}")
    print()

    # 採用基準チェック
    print("[採用基準チェック]")
    print("-" * 60)
    print(f"  黒字年数: {check['black_years']}/6年 {'PASS' if check['black_years_pass'] else 'FAIL'} (基準: 4/6年以上)")
    print(f"  累計収支: {total['profit']:+,.0f}円 {'PASS' if check['profit_pass'] else 'FAIL'} (基準: プラス)")
    print(f"  ROI: {total['roi']:.1f}% {'PASS' if check['roi_pass'] else 'FAIL'} (基準: 100%以上)")
    print(f"  サンプル数: {total['bets']}件 {'PASS' if check['sample_pass'] else 'FAIL'} (基準: 100件以上)")
    print()

    # 最終判定
    if check['all_pass']:
        print("=" * 60)
        print("  採用推奨")
        print("=" * 60)
        print()
        print("standard_backtest.pyに追加する条件定義:")
        print("-" * 60)
        cond = generate_backtest_command(params)
        print("    {")
        for k, v in cond.items():
            if isinstance(v, str):
                print(f"        '{k}': '{v}',")
            elif isinstance(v, list):
                print(f"        '{k}': {v},")
            elif v is None:
                print(f"        '{k}': None,")
            else:
                print(f"        '{k}': {v},")
        print("    },")
    else:
        print("=" * 60)
        print("  不採用（基準未達）")
        print("=" * 60)
        failed_criteria = []
        if not check['black_years_pass']:
            failed_criteria.append(f"黒字年数{check['black_years']}/6年")
        if not check['profit_pass']:
            failed_criteria.append(f"累計赤字{total['profit']:+,.0f}円")
        if not check['roi_pass']:
            failed_criteria.append(f"ROI{total['roi']:.1f}%")
        if not check['sample_pass']:
            failed_criteria.append(f"サンプル不足{total['bets']}件")
        print(f"  不採用理由: {', '.join(failed_criteria)}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description='不採用案再検証テンプレート',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用例:
  # 基本的な使用例
  python scripts/templates/rejected_idea_review_template.py --confidence B --odds-min 50 --odds-max 100

  # 1コース級別指定（複数指定可）
  python scripts/templates/rejected_idea_review_template.py --confidence B --odds-min 30 --odds-max 50 --c1-rank B1

  # モーター2連対率フィルター追加
  python scripts/templates/rejected_idea_review_template.py --confidence A --odds-min 10 --odds-max 30 --motor-second-rate-min 40

  # 会場フィルター（会場コードで指定）
  python scripts/templates/rejected_idea_review_template.py --confidence C --odds-min 20 --odds-max 30 --venue-filter 6 7 8 10

  # 月除外（複数指定可）
  python scripts/templates/rejected_idea_review_template.py --confidence B --odds-min 50 --odds-max 100 --month-exclude 12 1 2
        '''
    )

    parser.add_argument('--confidence', '-c', required=True, choices=['A', 'B', 'C', 'D'],
                        help='信頼度 (A/B/C/D)')
    parser.add_argument('--odds-min', '-omin', type=float, required=True,
                        help='オッズ下限')
    parser.add_argument('--odds-max', '-omax', type=float, required=True,
                        help='オッズ上限')
    parser.add_argument('--c1-rank', nargs='*', choices=['A1', 'A2', 'B1', 'B2'],
                        help='1コース級別フィルター（複数指定可、省略時は全級別）')
    parser.add_argument('--motor-second-rate-min', type=float,
                        help='モーター2連対率の最小値')
    parser.add_argument('--venue-filter', nargs='*', type=int,
                        help='会場コードフィルター（複数指定可）')
    parser.add_argument('--month-exclude', nargs='*', type=int,
                        help='除外する月（複数指定可）')

    args = parser.parse_args()

    # 分析実行
    results = analyze_condition(
        confidence=args.confidence,
        odds_min=args.odds_min,
        odds_max=args.odds_max,
        c1_rank=args.c1_rank,
        motor_second_rate_min=args.motor_second_rate_min,
        venue_filter=args.venue_filter,
        month_exclude=args.month_exclude
    )

    # 結果出力
    print_results(results)


if __name__ == '__main__':
    main()
