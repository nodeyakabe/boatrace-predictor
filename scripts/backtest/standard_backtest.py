#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
標準バックテストスクリプト

目的:
    購入条件の変更前後で同一条件のテストを実行し、結果を比較する

使用方法:
    python scripts/backtest/standard_backtest.py
    python scripts/backtest/standard_backtest.py --year 2024
    python scripts/backtest/standard_backtest.py --save-baseline
    python scripts/backtest/standard_backtest.py --compare

出力:
    - コンソールに詳細結果を表示
    - --save-baseline: data/backtest_baseline.json に保存
    - --compare: 前回ベースラインとの比較を表示
"""
import sqlite3
import sys
import io
import os
import json
import argparse
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# ============================================================
# 購入条件定義（bet_target_evaluator.py と同期）
# ============================================================
# 変更時は bet_target_evaluator.py も合わせて変更すること

CONDITIONS = [
    # A条件: A1級 × 黒字オッズ帯のみ
    {'name': 'A×A1×10-12', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12, 'venue_filter': None},
    {'name': 'A×A1×14-16', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 14, 'odds_max': 16, 'venue_filter': None},
    # A条件: B1級 × モーター40%+（2025-12-24追加）
    {'name': 'A×B1×Motor40%+', 'confidence': 'A', 'c1_rank': ['B1'], 'odds_min': 10, 'odds_max': 100, 'venue_filter': None, 'motor_min': 40},

    # B条件: 50-100倍（A2級除外 - 6年間+5,900円改善）+ 30-50倍×B1+会場フィルター
    {'name': 'B×50-100', 'confidence': 'B', 'c1_rank': ['A1', 'B1'], 'odds_min': 50, 'odds_max': 100, 'venue_filter': None},  # A2除外
    {'name': 'B×30-50×B1+会場', 'confidence': 'B', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50,
     'venue_filter': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8]},  # 三国,浜名湖,児島,芦屋,津,尼崎,若松,大村,蒲郡,常滑

    # C条件: 20-30倍×B1+会場フィルター
    {'name': 'C×20-30×B1+会場', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30,
     'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]},  # 唐津,徳山,多摩川,平和島,津,丸亀,常滑,大村,若松,宮島

    # C条件: 鳴門×A2×30-80倍（2025-12-25追加）
    {'name': '鳴門×C×A2×30-80', 'confidence': 'C', 'c1_rank': ['A2'], 'odds_min': 30, 'odds_max': 80,
     'venue_filter': [14]},  # 鳴門のみ

    # D条件: 40-50倍×B1
    {'name': 'D×40-50×B1', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50, 'venue_filter': None},
    # D条件: 35-60倍（30-35倍除外で+29,950円改善）+ 9R除外 + 三国除外
    # ※ 9R除外と三国除外はanalyze_conditionで処理
    {'name': 'D×35-60', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 35, 'odds_max': 60, 'venue_filter': None,
     'race_exclude': [9], 'venue_exclude': [10]},  # 9R除外, 三国除外
]

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}


def analyze_condition(cursor, cond, year_start, year_end):
    """条件別のROIを計算"""
    c1_rank_str = "','".join(cond['c1_rank'])
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"

    # モーター条件
    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

    # レース番号除外条件（2025-12-25追加）
    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    # 会場除外条件（2025-12-25追加）
    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(map(str, cond['venue_exclude']))})"

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
        AND rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end}-12-01'
        {venue_clause}
        {motor_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
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
    WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
    '''
    cursor.execute(query)
    row = cursor.fetchone()
    bets, hits, payout = row
    if bets and bets > 0:
        roi = 100.0 * payout / (bets * 100)
        profit = payout - (bets * 100)
        return {'name': cond['name'], 'bets': bets, 'hits': hits, 'roi': roi, 'profit': profit}
    return {'name': cond['name'], 'bets': 0, 'hits': 0, 'roi': 0, 'profit': 0}


def run_backtest(year=2025):
    """バックテストを実行"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    results = []
    total_bets = 0
    total_profit = 0

    for cond in CONDITIONS:
        result = analyze_condition(cursor, cond, year, year)
        results.append(result)
        total_bets += result['bets']
        total_profit += result['profit']

    conn.close()

    total_roi = 100.0 * (total_profit + total_bets * 100) / (total_bets * 100) if total_bets > 0 else 0

    return {
        'year': year,
        'date': datetime.now().isoformat(),
        'conditions': results,
        'total': {
            'bets': total_bets,
            'roi': total_roi,
            'profit': total_profit
        }
    }


def print_results(data):
    """結果を表示"""
    print("=" * 80)
    print(f"標準バックテスト結果")
    print(f"対象期間: {data['year']}年1-11月")
    print(f"実行日時: {data['date'][:10]}")
    print("=" * 80)
    print()

    print("[条件別パフォーマンス]")
    print("-" * 80)
    print(f"{'条件':<25} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12}")
    print("-" * 80)

    for cond in data['conditions']:
        print(f"{cond['name']:<25} {cond['bets']:>6} {cond['hits']:>4} {cond['roi']:>7.1f}% {cond['profit']:>+12,.0f}")

    print("-" * 80)
    total = data['total']
    print(f"{'合計':<25} {total['bets']:>6} {'-':>4} {total['roi']:>7.1f}% {total['profit']:>+12,.0f}")
    print()


def save_baseline(data):
    """ベースラインを保存"""
    baseline_path = os.path.join(PROJECT_ROOT, 'data', 'backtest_baseline.json')
    os.makedirs(os.path.dirname(baseline_path), exist_ok=True)
    with open(baseline_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"ベースラインを保存しました: {baseline_path}")


def compare_with_baseline(current):
    """ベースラインと比較"""
    baseline_path = os.path.join(PROJECT_ROOT, 'data', 'backtest_baseline.json')
    if not os.path.exists(baseline_path):
        print("ベースラインが見つかりません。--save-baseline で保存してください。")
        return

    with open(baseline_path, 'r', encoding='utf-8') as f:
        baseline = json.load(f)

    print()
    print("=" * 80)
    print("ベースラインとの比較")
    print("=" * 80)
    print()
    print(f"ベースライン日時: {baseline['date'][:10]}")
    print(f"現在: {current['date'][:10]}")
    print()

    print(f"{'指標':<15} {'ベースライン':>15} {'現在':>15} {'差分':>12}")
    print("-" * 60)

    b_total = baseline['total']
    c_total = current['total']

    print(f"{'件数':<15} {b_total['bets']:>15,} {c_total['bets']:>15,} {c_total['bets'] - b_total['bets']:>+12,}")
    print(f"{'ROI':<15} {b_total['roi']:>14.1f}% {c_total['roi']:>14.1f}% {c_total['roi'] - b_total['roi']:>+11.1f}pt")
    print(f"{'収支':<15} {b_total['profit']:>+14,.0f} {c_total['profit']:>+14,.0f} {c_total['profit'] - b_total['profit']:>+11,.0f}")
    print()


def main():
    parser = argparse.ArgumentParser(description='標準バックテストスクリプト')
    parser.add_argument('--year', type=int, default=2025, help='対象年度（デフォルト: 2025）')
    parser.add_argument('--save-baseline', action='store_true', help='結果をベースラインとして保存')
    parser.add_argument('--compare', action='store_true', help='ベースラインと比較')
    args = parser.parse_args()

    data = run_backtest(args.year)
    print_results(data)

    if args.save_baseline:
        save_baseline(data)

    if args.compare:
        compare_with_baseline(data)


if __name__ == '__main__':
    main()
