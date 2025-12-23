#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2025年 全データ分析（信頼度別）
"""

import sys
sys.path.insert(0, '.')

import warnings
warnings.filterwarnings('ignore')
import logging
logging.disable(logging.WARNING)

import sqlite3
from collections import defaultdict
from datetime import datetime

from src.analysis.race_predictor import RacePredictor

DB_PATH = 'data/boatrace.db'


def main():
    print("=" * 100)
    print("2025年 全データ分析（信頼度別）")
    print("=" * 100)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 2025年全データ取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date
        FROM races r
        INNER JOIN results res ON res.race_id = r.id
        WHERE r.race_date BETWEEN '2025-01-01' AND '2025-12-18'
            AND res.is_invalid = 0
            AND EXISTS (
                SELECT 1 FROM entries e WHERE e.race_id = r.id
                GROUP BY e.race_id HAVING COUNT(*) = 6
            )
        ORDER BY r.race_date, r.id
    ''')
    races = [(row[0], row[1]) for row in cursor.fetchall()]
    print(f"総レース数: {len(races)}")
    print()

    predictor = RacePredictor(db_path=DB_PATH, use_cache=False)
    print("RacePredictor初期化完了")
    print()

    stats = defaultdict(lambda: {
        'total': 0, 'hit_1st': 0, 'hit_2nd': 0, 'hit_3rd': 0,
        'hit_trifecta': 0, 'bet': 0, 'payout': 0
    })

    monthly = defaultdict(lambda: defaultdict(lambda: {
        'total': 0, 'hit_trifecta': 0, 'bet': 0, 'payout': 0
    }))

    errors = 0
    processed = 0

    for i, (race_id, race_date) in enumerate(races):
        if (i + 1) % 1000 == 0:
            print(f"処理中: {i+1}/{len(races)} ({(i+1)/len(races)*100:.1f}%)")

        try:
            predictions = predictor.predict_race(race_id)
            if not predictions or len(predictions) < 3:
                continue

            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank IS NOT NULL
                ORDER BY CAST(rank AS INTEGER)
            ''', (race_id,))
            results = cursor.fetchall()
            if len(results) < 3:
                continue

            actual = [int(r[0]) for r in results[:3]]

            comb = f'{actual[0]}-{actual[1]}-{actual[2]}'
            cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?', (race_id, comb))
            row = cursor.fetchone()
            odds = float(row[0]) if row else 0.0

            processed += 1
            conf = predictions[0].get('confidence', 'D')
            pred = [predictions[j]['pit_number'] for j in range(3)]
            month = race_date[:7]

            stats[conf]['total'] += 1
            stats[conf]['bet'] += 100

            if pred[0] == actual[0]:
                stats[conf]['hit_1st'] += 1
            if pred[1] == actual[1]:
                stats[conf]['hit_2nd'] += 1
            if pred[2] == actual[2]:
                stats[conf]['hit_3rd'] += 1

            if pred == actual:
                stats[conf]['hit_trifecta'] += 1
                stats[conf]['payout'] += odds * 100

            # 月別集計（B+Cのみ）
            if conf in ['B', 'C']:
                monthly[month][conf]['total'] += 1
                monthly[month][conf]['bet'] += 100
                if pred == actual:
                    monthly[month][conf]['hit_trifecta'] += 1
                    monthly[month][conf]['payout'] += odds * 100

        except Exception as e:
            errors += 1
            continue

    print()
    print(f"処理完了: {processed}/{len(races)} レース（エラー: {errors}）")
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 結果表示
    print("=" * 100)
    print("=== 信頼度別成績 ===")
    print("=" * 100)
    print()
    print(f"{'信頼度':<6}|{'レース':>8}|{'1着的中':>12}|{'2着的中':>12}|{'3着的中':>12}|{'3連単':>12}|{'払戻金':>14}|{'ROI':>8}")
    print("-" * 100)

    all_t = {'total': 0, 'hit_1st': 0, 'hit_2nd': 0, 'hit_3rd': 0, 'hit_trifecta': 0, 'bet': 0, 'payout': 0}

    for c in ['A', 'B', 'C', 'D']:
        s = stats[c]
        if s['total'] == 0:
            continue
        for k in all_t:
            all_t[k] += s[k]

        r1 = s['hit_1st'] / s['total'] * 100
        r2 = s['hit_2nd'] / s['total'] * 100
        r3 = s['hit_3rd'] / s['total'] * 100
        rt = s['hit_trifecta'] / s['total'] * 100
        roi = s['payout'] / s['bet'] * 100 if s['bet'] > 0 else 0

        print(f"{c:^6}|{s['total']:>8,}|{r1:>5.1f}%({s['hit_1st']:>5,})|{r2:>5.1f}%({s['hit_2nd']:>5,})|{r3:>5.1f}%({s['hit_3rd']:>5,})|{rt:>5.2f}%({s['hit_trifecta']:>5,})|{s['payout']:>12,.0f}円|{roi:>6.1f}%")

    print("-" * 100)

    if all_t['total'] > 0:
        r1 = all_t['hit_1st'] / all_t['total'] * 100
        r2 = all_t['hit_2nd'] / all_t['total'] * 100
        r3 = all_t['hit_3rd'] / all_t['total'] * 100
        rt = all_t['hit_trifecta'] / all_t['total'] * 100
        roi = all_t['payout'] / all_t['bet'] * 100

        print(f"{'合計':^6}|{all_t['total']:>8,}|{r1:>5.1f}%({all_t['hit_1st']:>5,})|{r2:>5.1f}%({all_t['hit_2nd']:>5,})|{r3:>5.1f}%({all_t['hit_3rd']:>5,})|{rt:>5.2f}%({all_t['hit_trifecta']:>5,})|{all_t['payout']:>12,.0f}円|{roi:>6.1f}%")

    print()

    # 購入対象（B+C）
    print("=" * 100)
    print("=== 購入対象（信頼度B+C）の成績 ===")
    print("=" * 100)
    print()

    bc = {k: stats['B'][k] + stats['C'][k] for k in stats['B']}

    if bc['total'] > 0:
        print(f"レース数:     {bc['total']:,}")
        print(f"1着的中率:    {bc['hit_1st']/bc['total']*100:.1f}% ({bc['hit_1st']:,}件)")
        print(f"2着的中率:    {bc['hit_2nd']/bc['total']*100:.1f}% ({bc['hit_2nd']:,}件)")
        print(f"3着的中率:    {bc['hit_3rd']/bc['total']*100:.1f}% ({bc['hit_3rd']:,}件)")
        print(f"3連単的中率:  {bc['hit_trifecta']/bc['total']*100:.2f}% ({bc['hit_trifecta']:,}件)")
        print(f"総投資額:     {bc['bet']:,}円")
        print(f"総払戻金:     {bc['payout']:,.0f}円")
        print(f"収支:         {bc['payout']-bc['bet']:+,.0f}円")
        print(f"ROI:          {bc['payout']/bc['bet']*100:.1f}%")

    print()

    # 月別推移
    print("=" * 100)
    print("=== 月別推移（信頼度B+C購入時） ===")
    print("=" * 100)
    print()
    print(f"{'月':^8}|{'レース':>8}|{'3連単的中':>12}|{'払戻金':>14}|{'収支':>14}|{'ROI':>8}")
    print("-" * 70)

    cumulative_bet = 0
    cumulative_payout = 0

    for month in sorted(monthly.keys()):
        m_total = monthly[month]['B']['total'] + monthly[month]['C']['total']
        m_hit = monthly[month]['B']['hit_trifecta'] + monthly[month]['C']['hit_trifecta']
        m_bet = monthly[month]['B']['bet'] + monthly[month]['C']['bet']
        m_payout = monthly[month]['B']['payout'] + monthly[month]['C']['payout']

        if m_total == 0:
            continue

        rate = m_hit / m_total * 100
        roi = m_payout / m_bet * 100
        profit = m_payout - m_bet

        cumulative_bet += m_bet
        cumulative_payout += m_payout

        print(f"{month:^8}|{m_total:>8,}|{rate:>5.2f}%({m_hit:>4,})|{m_payout:>12,.0f}円|{profit:>+12,.0f}円|{roi:>6.1f}%")

    print("-" * 70)

    if cumulative_bet > 0:
        cumulative_roi = cumulative_payout / cumulative_bet * 100
        print(f"{'累計':^8}|{'-':>8}|{'-':>12}|{cumulative_payout:>12,.0f}円|{cumulative_payout-cumulative_bet:>+12,.0f}円|{cumulative_roi:>6.1f}%")

    conn.close()
    print()
    print("完了")


if __name__ == '__main__':
    main()
