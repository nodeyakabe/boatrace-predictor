#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2025年 年間成績分析（信頼度別）
現行システム（RacePredictor）での実際の性能を測定
"""

import sys
sys.path.insert(0, '.')

import warnings
warnings.filterwarnings('ignore')

import sqlite3
from collections import defaultdict
from datetime import datetime

from src.analysis.race_predictor import RacePredictor

DB_PATH = 'data/boatrace.db'


def get_test_races(conn, start_date, end_date):
    """テスト対象レースを取得"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date
        FROM races r
        INNER JOIN results res ON res.race_id = r.id
        WHERE r.race_date BETWEEN ? AND ?
            AND res.is_invalid = 0
            AND EXISTS (
                SELECT 1 FROM entries e WHERE e.race_id = r.id
                GROUP BY e.race_id HAVING COUNT(*) = 6
            )
        ORDER BY r.race_date, r.id
    ''', (start_date, end_date))
    return [(row[0], row[1]) for row in cursor.fetchall()]


def get_race_result(conn, race_id):
    """レース結果を取得"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pit_number, rank
        FROM results
        WHERE race_id = ? AND is_invalid = 0 AND rank IS NOT NULL
        ORDER BY CAST(rank AS INTEGER)
    ''', (race_id,))
    results = cursor.fetchall()
    if len(results) < 3:
        return None

    actual_order = [int(r[0]) for r in results[:3]]

    # 3連単オッズ
    combination = f"{actual_order[0]}-{actual_order[1]}-{actual_order[2]}"
    cursor.execute('''
        SELECT odds FROM trifecta_odds
        WHERE race_id = ? AND combination = ?
    ''', (race_id, combination))
    row = cursor.fetchone()
    odds = float(row[0]) if row else 0.0

    return {
        'actual_1st': actual_order[0],
        'actual_2nd': actual_order[1],
        'actual_3rd': actual_order[2],
        'combination': combination,
        'odds': odds
    }


def main():
    print("=" * 80)
    print("2025年 年間成績分析（信頼度別）")
    print("現行システム（RacePredictor）での実際の性能")
    print("=" * 80)
    print()

    conn = sqlite3.connect(DB_PATH)

    # 2025年全データ
    start_date = '2025-01-01'
    end_date = '2025-12-18'

    races = get_test_races(conn, start_date, end_date)
    print(f"期間: {start_date} ~ {end_date}")
    print(f"総レース数: {len(races)}")
    print()

    # RacePredictor初期化
    predictor = RacePredictor(db_path=DB_PATH, use_cache=False)
    print("RacePredictor初期化完了")
    print()

    # 信頼度別に集計
    stats = defaultdict(lambda: {
        'total': 0,
        'hit_1st': 0,
        'hit_2nd': 0,
        'hit_3rd': 0,
        'hit_trifecta': 0,
        'total_bet': 0,
        'total_payout': 0,
        'payouts': []
    })

    errors = 0
    processed = 0

    for i, (race_id, race_date) in enumerate(races):
        if (i + 1) % 1000 == 0:
            print(f"処理中: {i+1}/{len(races)} ({(i+1)/len(races)*100:.1f}%)")

        try:
            # 予測
            predictions = predictor.predict_race(race_id)
            if not predictions or len(predictions) < 3:
                continue

            # 結果取得
            actual = get_race_result(conn, race_id)
            if actual is None:
                continue

            processed += 1

            # 信頼度
            confidence = predictions[0].get('confidence', 'D')

            pred_1st = predictions[0]['pit_number']
            pred_2nd = predictions[1]['pit_number']
            pred_3rd = predictions[2]['pit_number']

            stats[confidence]['total'] += 1
            stats[confidence]['total_bet'] += 100

            # 的中判定
            if pred_1st == actual['actual_1st']:
                stats[confidence]['hit_1st'] += 1
            if pred_2nd == actual['actual_2nd']:
                stats[confidence]['hit_2nd'] += 1
            if pred_3rd == actual['actual_3rd']:
                stats[confidence]['hit_3rd'] += 1

            if (pred_1st == actual['actual_1st'] and
                pred_2nd == actual['actual_2nd'] and
                pred_3rd == actual['actual_3rd']):
                stats[confidence]['hit_trifecta'] += 1
                payout = actual['odds'] * 100
                stats[confidence]['total_payout'] += payout
                stats[confidence]['payouts'].append(payout)

        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  エラー: {e}")
            continue

    print()
    print(f"処理完了: {processed}/{len(races)} レース")
    print()

    # 結果表示
    print("=" * 80)
    print("=== 信頼度別成績 ===")
    print("=" * 80)
    print()

    print(f"{'信頼度':^6} | {'レース数':^8} | {'1着的中':^10} | {'2着的中':^10} | {'3着的中':^10} | {'3連単':^10} | {'払戻金':^12} | {'ROI':^8}")
    print("-" * 95)

    total_all = {'total': 0, 'hit_1st': 0, 'hit_2nd': 0, 'hit_3rd': 0,
                 'hit_trifecta': 0, 'total_bet': 0, 'total_payout': 0}

    for conf in ['A', 'B', 'C', 'D']:
        s = stats[conf]
        if s['total'] == 0:
            continue

        rate_1st = s['hit_1st'] / s['total'] * 100
        rate_2nd = s['hit_2nd'] / s['total'] * 100
        rate_3rd = s['hit_3rd'] / s['total'] * 100
        rate_tri = s['hit_trifecta'] / s['total'] * 100
        roi = s['total_payout'] / s['total_bet'] * 100 if s['total_bet'] > 0 else 0

        print(f"  {conf:^4} | {s['total']:^8} | {rate_1st:>5.1f}% ({s['hit_1st']:>4}) | {rate_2nd:>5.1f}% ({s['hit_2nd']:>4}) | {rate_3rd:>5.1f}% ({s['hit_3rd']:>4}) | {rate_tri:>5.2f}% ({s['hit_trifecta']:>3}) | {s['total_payout']:>10,.0f}円 | {roi:>6.1f}%")

        for k in total_all:
            total_all[k] += s[k]

    print("-" * 95)

    # 合計
    if total_all['total'] > 0:
        rate_1st = total_all['hit_1st'] / total_all['total'] * 100
        rate_2nd = total_all['hit_2nd'] / total_all['total'] * 100
        rate_3rd = total_all['hit_3rd'] / total_all['total'] * 100
        rate_tri = total_all['hit_trifecta'] / total_all['total'] * 100
        roi = total_all['total_payout'] / total_all['total_bet'] * 100

        print(f" {'合計':^4} | {total_all['total']:^8} | {rate_1st:>5.1f}% ({total_all['hit_1st']:>4}) | {rate_2nd:>5.1f}% ({total_all['hit_2nd']:>4}) | {rate_3rd:>5.1f}% ({total_all['hit_3rd']:>4}) | {rate_tri:>5.2f}% ({total_all['hit_trifecta']:>3}) | {total_all['total_payout']:>10,.0f}円 | {roi:>6.1f}%")

    print()

    # B+C（購入対象）の集計
    print("=" * 80)
    print("=== 購入対象（信頼度B+C）の成績 ===")
    print("=" * 80)
    print()

    bc_stats = {'total': 0, 'hit_1st': 0, 'hit_2nd': 0, 'hit_3rd': 0,
                'hit_trifecta': 0, 'total_bet': 0, 'total_payout': 0}

    for conf in ['B', 'C']:
        for k in bc_stats:
            bc_stats[k] += stats[conf][k]

    if bc_stats['total'] > 0:
        rate_1st = bc_stats['hit_1st'] / bc_stats['total'] * 100
        rate_2nd = bc_stats['hit_2nd'] / bc_stats['total'] * 100
        rate_3rd = bc_stats['hit_3rd'] / bc_stats['total'] * 100
        rate_tri = bc_stats['hit_trifecta'] / bc_stats['total'] * 100
        roi = bc_stats['total_payout'] / bc_stats['total_bet'] * 100

        print(f"レース数:     {bc_stats['total']:,}")
        print(f"1着的中率:    {rate_1st:.1f}% ({bc_stats['hit_1st']:,}件)")
        print(f"2着的中率:    {rate_2nd:.1f}% ({bc_stats['hit_2nd']:,}件)")
        print(f"3着的中率:    {rate_3rd:.1f}% ({bc_stats['hit_3rd']:,}件)")
        print(f"3連単的中率:  {rate_tri:.2f}% ({bc_stats['hit_trifecta']:,}件)")
        print(f"総投資額:     {bc_stats['total_bet']:,}円")
        print(f"総払戻金:     {bc_stats['total_payout']:,.0f}円")
        print(f"収支:         {bc_stats['total_payout'] - bc_stats['total_bet']:+,.0f}円")
        print(f"ROI:          {roi:.1f}%")

    print()

    # 月別推移（B+Cのみ）
    print("=" * 80)
    print("=== 月別推移（信頼度B+C購入時） ===")
    print("=" * 80)
    print()

    # 月別に再集計するため、もう一度処理
    monthly = defaultdict(lambda: {
        'total': 0, 'hit_trifecta': 0, 'total_bet': 0, 'total_payout': 0
    })

    for i, (race_id, race_date) in enumerate(races):
        try:
            predictions = predictor.predict_race(race_id)
            if not predictions or len(predictions) < 3:
                continue

            actual = get_race_result(conn, race_id)
            if actual is None:
                continue

            confidence = predictions[0].get('confidence', 'D')
            if confidence not in ['B', 'C']:
                continue

            month = race_date[:7]  # YYYY-MM
            monthly[month]['total'] += 1
            monthly[month]['total_bet'] += 100

            pred_1st = predictions[0]['pit_number']
            pred_2nd = predictions[1]['pit_number']
            pred_3rd = predictions[2]['pit_number']

            if (pred_1st == actual['actual_1st'] and
                pred_2nd == actual['actual_2nd'] and
                pred_3rd == actual['actual_3rd']):
                monthly[month]['hit_trifecta'] += 1
                monthly[month]['total_payout'] += actual['odds'] * 100

        except:
            continue

    print(f"{'月':^8} | {'レース数':^8} | {'3連単的中':^10} | {'払戻金':^12} | {'収支':^12} | {'ROI':^8}")
    print("-" * 70)

    cumulative_bet = 0
    cumulative_payout = 0

    for month in sorted(monthly.keys()):
        m = monthly[month]
        if m['total'] == 0:
            continue

        rate = m['hit_trifecta'] / m['total'] * 100
        roi = m['total_payout'] / m['total_bet'] * 100
        profit = m['total_payout'] - m['total_bet']

        cumulative_bet += m['total_bet']
        cumulative_payout += m['total_payout']

        print(f" {month} | {m['total']:^8} | {rate:>5.2f}% ({m['hit_trifecta']:>3}) | {m['total_payout']:>10,.0f}円 | {profit:>+10,.0f}円 | {roi:>6.1f}%")

    print("-" * 70)
    cumulative_roi = cumulative_payout / cumulative_bet * 100 if cumulative_bet > 0 else 0
    print(f" {'累計':^6} | {'-':^8} | {'-':^10} | {cumulative_payout:>10,.0f}円 | {cumulative_payout-cumulative_bet:>+10,.0f}円 | {cumulative_roi:>6.1f}%")

    conn.close()
    print()
    print("完了")


if __name__ == '__main__':
    main()
