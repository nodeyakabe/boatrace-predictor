#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
詳細パフォーマンスレポート（月別・条件別）

用途:
    年別だけでなく、月別・条件別のパフォーマンスを詳しく分析する

使用方法:
    # 6年間全体（推奨）
    python scripts/analysis/detailed_performance_report.py --full

    # 特定年
    python scripts/analysis/detailed_performance_report.py --year 2024

    # 条件×月クロス表も出力（詳細モード）
    python scripts/analysis/detailed_performance_report.py --full --cross

注意:
    - non-unique版（各条件を独立して集計）
    - unique版の合計とは若干異なる場合がある
"""
import sqlite3
import sys
import os
import argparse
import io
from typing import Dict, List, Set

# Windows CP932環境でのUnicode出力対応
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
elif hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.backtest_helpers import get_race_ids_for_condition
from scripts.backtest.standard_backtest_unique import analyze_assigned_races

BATCH_SIZE = 900


def get_race_date_map(cursor: sqlite3.Cursor, race_ids: Set[int]) -> Dict[int, tuple]:
    """race_id -> (year, month) のマップを返す"""
    if not race_ids:
        return {}
    result = {}
    ids_list = list(race_ids)
    for i in range(0, len(ids_list), BATCH_SIZE):
        batch = ids_list[i:i + BATCH_SIZE]
        placeholders = ','.join(['?'] * len(batch))
        cursor.execute(
            f"SELECT id, CAST(strftime('%Y', race_date) AS INTEGER), CAST(strftime('%m', race_date) AS INTEGER) "
            f"FROM races WHERE id IN ({placeholders})",
            batch
        )
        for row in cursor.fetchall():
            result[row[0]] = (row[1], row[2])
    return result


def calc_stats(investment: int, payout: float, bets: int, hits: int) -> dict:
    roi = 100.0 * payout / investment if investment > 0 else 0.0
    profit = payout - investment
    hit_rate = 100.0 * hits / bets if bets > 0 else 0.0
    return {'bets': bets, 'hits': hits, 'hit_rate': hit_rate,
            'investment': investment, 'payout': payout, 'roi': roi, 'profit': profit}


def run_report(year: int = 2025, full_test: bool = False, show_cross: bool = False):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    if full_test:
        start_date = "2020-01-01"
        end_date = "2026-01-01"
        period_label = "2020-2025（6年間）"
    else:
        start_date = f"{year}-01-01"
        end_date = f"{year + 1}-01-01"
        period_label = f"{year}年"

    print("=" * 100)
    print(f"  詳細パフォーマンスレポート  [{period_label}]  (non-unique)")
    print("=" * 100)

    # ──────────────────────────────────────────
    # 1. 条件別サマリー
    # ──────────────────────────────────────────
    print("\n## 1. 条件別サマリー\n")
    print(f"{'条件ID':<28} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>14}")
    print("-" * 75)

    cond_results = {}
    total_bets = total_hits = total_investment = total_payout = 0

    for cond in STANDARD_BET_CONDITIONS:
        race_ids = get_race_ids_for_condition(cursor, cond, start_date, end_date)
        r = analyze_assigned_races(cursor, cond, list(race_ids))
        cond_results[cond['id']] = {
            'cond': cond,
            'race_ids': race_ids,
            'stats': r,
        }
        total_bets += r['bets']
        total_hits += r['hits']
        total_investment += r['investment']
        total_payout += r['payout']

        marker = ""
        if r['roi'] >= 200:
            marker = " ◎"
        elif r['roi'] >= 150:
            marker = " ○"
        elif r['roi'] < 100 and r['bets'] > 0:
            marker = " ×"
        print(f"{cond['id']:<28} {r['bets']:>6} {r['hits']:>4} "
              f"{r['hit_rate']:>6.1f}% {r['roi']:>7.1f}% {r['profit']:>+14,.0f}{marker}")

    print("-" * 75)
    total_roi = 100.0 * total_payout / total_investment if total_investment > 0 else 0
    total_profit = total_payout - total_investment
    total_hit_rate = 100.0 * total_hits / total_bets if total_bets > 0 else 0
    print(f"{'合計':<28} {total_bets:>6} {total_hits:>4} "
          f"{total_hit_rate:>6.1f}% {total_roi:>7.1f}% {total_profit:>+14,.0f}")

    # ──────────────────────────────────────────
    # 2. 月別サマリー（全条件合計）
    # ──────────────────────────────────────────
    print("\n## 2. 月別サマリー（全条件合計・non-unique）\n")

    # 全条件のrace_ids + 月情報を集約
    month_data: Dict[int, Dict] = {m: {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
                                    for m in range(1, 13)}

    for cond_id, info in cond_results.items():
        cond = info['cond']
        race_ids = info['race_ids']
        date_map = get_race_date_map(cursor, race_ids)

        for month in range(1, 13):
            month_race_ids = [rid for rid, (y, m) in date_map.items() if m == month]
            if not month_race_ids:
                continue
            r = analyze_assigned_races(cursor, cond, month_race_ids)
            month_data[month]['bets'] += r['bets']
            month_data[month]['hits'] += r['hits']
            month_data[month]['investment'] += r['investment']
            month_data[month]['payout'] += r['payout']

    print(f"{'月':>4} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>14}")
    print("-" * 50)
    for m in range(1, 13):
        d = month_data[m]
        if d['bets'] == 0:
            print(f"{m:>3}月 {'---':>6} {'---':>4} {'---':>7} {'---':>8} {'---':>14}")
            continue
        roi = 100.0 * d['payout'] / d['investment'] if d['investment'] > 0 else 0
        profit = d['payout'] - d['investment']
        hr = 100.0 * d['hits'] / d['bets'] if d['bets'] > 0 else 0
        marker = " ◎" if roi >= 200 else (" ○" if roi >= 150 else (" ×" if roi < 100 else ""))
        print(f"{m:>3}月 {d['bets']:>6} {d['hits']:>4} {hr:>6.1f}% {roi:>7.1f}% {profit:>+14,.0f}{marker}")

    # ──────────────────────────────────────────
    # 3. 年別サマリー（全条件合計）
    # ──────────────────────────────────────────
    print("\n## 3. 年別サマリー（全条件合計・non-unique）\n")

    year_data: Dict[int, Dict] = {}
    years_in_scope = list(range(2020, 2026)) if full_test else [year]
    for y in years_in_scope:
        year_data[y] = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}

    for cond_id, info in cond_results.items():
        cond = info['cond']
        race_ids = info['race_ids']
        date_map = get_race_date_map(cursor, race_ids)

        for y in years_in_scope:
            year_race_ids = [rid for rid, (yr, m) in date_map.items() if yr == y]
            if not year_race_ids:
                continue
            r = analyze_assigned_races(cursor, cond, year_race_ids)
            year_data[y]['bets'] += r['bets']
            year_data[y]['hits'] += r['hits']
            year_data[y]['investment'] += r['investment']
            year_data[y]['payout'] += r['payout']

    print(f"{'年度':>6} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>14} {'判定':>4}")
    print("-" * 60)
    for y in years_in_scope:
        d = year_data[y]
        if d['bets'] == 0:
            print(f"{y}年 {'---':>6}")
            continue
        roi = 100.0 * d['payout'] / d['investment'] if d['investment'] > 0 else 0
        profit = d['payout'] - d['investment']
        hr = 100.0 * d['hits'] / d['bets'] if d['bets'] > 0 else 0
        judge = "○" if profit > 0 else "×"
        print(f"{y}年 {d['bets']:>6} {d['hits']:>4} {hr:>6.1f}% {roi:>7.1f}% {profit:>+14,.0f} {judge:>4}")

    # ──────────────────────────────────────────
    # 4. 条件×月 クロス表（--cross オプション）
    # ──────────────────────────────────────────
    if show_cross:
        print("\n## 4. 条件×月 クロス表（収支・円）\n")
        months = list(range(1, 13))
        header = f"{'条件ID':<28}" + "".join(f"{m:>7}月" for m in months) + f"{'合計':>10}"
        print(header)
        print("-" * (28 + 8 * 12 + 10))

        for cond_id, info in cond_results.items():
            cond = info['cond']
            race_ids = info['race_ids']
            date_map = get_race_date_map(cursor, race_ids)

            row = f"{cond_id:<28}"
            row_total_profit = 0
            for m in months:
                month_race_ids = [rid for rid, (y, mo) in date_map.items() if mo == m]
                if not month_race_ids:
                    row += f"{'---':>8}"
                    continue
                r = analyze_assigned_races(cursor, cond, month_race_ids)
                profit = r['profit']
                row_total_profit += profit
                row += f"{profit:>+8,.0f}".replace(",", "") if abs(profit) < 1_000_000 else f"{profit // 1000:>+7}k"
            row += f"{row_total_profit:>+10,.0f}"
            print(row)

        # 月別の合計行
        row = f"{'合計':<28}"
        for m in months:
            d = month_data[m]
            profit = d['payout'] - d['investment']
            row += f"{profit:>+8,.0f}".replace(",", "") if abs(profit) < 1_000_000 else f"{profit // 1000:>+7}k"
        row += f"{total_profit:>+10,.0f}"
        print("-" * (28 + 8 * 12 + 10))
        print(row)

    print("\n" + "=" * 100)
    print(f"  完了  |  対象期間: {period_label}  |  ROI凡例: ◎>=200% ○>=150% ×<100%")
    print("=" * 100)

    conn.close()


def main():
    parser = argparse.ArgumentParser(description='詳細パフォーマンスレポート（月別・条件別）')
    parser.add_argument('--year', type=int, default=2025, help='対象年度（デフォルト: 2025）')
    parser.add_argument('--full', action='store_true', help='6年間全体テスト')
    parser.add_argument('--cross', action='store_true', help='条件×月クロス表も出力')
    args = parser.parse_args()

    run_report(year=args.year, full_test=args.full, show_cross=args.cross)


if __name__ == '__main__':
    main()
