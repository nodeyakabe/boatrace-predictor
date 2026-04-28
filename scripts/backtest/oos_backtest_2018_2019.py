#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2018-2019年 過去OOSバックテスト

目的:
    現行16条件（2020-2025で開発・チューニング済み）を
    2018-2019年の未使用データで検証する過去OOS（Out-of-Sample）レポート。

解釈の注意:
    - 条件はすべて2020-2025データで開発したため、2018-2019は統計的に真のOOS
    - ただし「過去OOS」（コロナ前・異なる市場環境）であり、未来OOS（2026年）の代替にはならない
    - サンプル数が小さい（2018:~440件・2019:~245件）ため、ROIブレが大きい
      三連単的中率1-2%では数百件のサンプルで±30%程度の分散は統計的に正常
    - 赤字でも直ちに「条件が機能しない」とは言えない

使用方法:
    python scripts/backtest/oos_backtest_2018_2019.py
    python scripts/backtest/oos_backtest_2018_2019.py --save-json data/oos_2018_2019.json
    python scripts/backtest/oos_backtest_2018_2019.py --year 2018   # 単年のみ
"""
import sqlite3
import sys
import os
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.standard_backtest_unique import (
    assign_races_to_conditions,
    analyze_assigned_races,
)

OOS_YEARS = [2018, 2019]


def run_oos_single_year(cursor: sqlite3.Cursor, year: int) -> Dict:
    """単年OOSバックテストを実行"""
    year_start = f"{year}-01-01"
    year_end = f"{year + 1}-01-01"

    condition_to_races = assign_races_to_conditions(
        cursor, STANDARD_BET_CONDITIONS, year_start, year_end
    )

    total_bets = total_hits = total_investment = total_payout = 0
    conditions = []

    for cond in STANDARD_BET_CONDITIONS:
        assigned_races = condition_to_races.get(cond['id'], [])
        result = analyze_assigned_races(cursor, cond, assigned_races)
        conditions.append(result)
        total_bets += result['bets']
        total_hits += result['hits']
        total_investment += result['investment']
        total_payout += result['payout']

    total = {
        'bets': total_bets,
        'hits': total_hits,
        'hit_rate': 100.0 * total_hits / total_bets if total_bets > 0 else 0,
        'investment': total_investment,
        'payout': total_payout,
        'roi': 100.0 * total_payout / total_investment if total_investment > 0 else 0,
        'profit': total_payout - total_investment,
    }

    return {'year': year, 'conditions': conditions, 'total': total}


def run_oos_combined(cursor: sqlite3.Cursor, years: List[int]) -> Dict:
    """複数年を一括でOOSバックテスト（重複除外はyears全体で行う）"""
    year_start = f"{min(years)}-01-01"
    year_end = f"{max(years) + 1}-01-01"

    condition_to_races = assign_races_to_conditions(
        cursor, STANDARD_BET_CONDITIONS, year_start, year_end
    )

    total_bets = total_hits = total_investment = total_payout = 0
    conditions = []

    for cond in STANDARD_BET_CONDITIONS:
        assigned_races = condition_to_races.get(cond['id'], [])
        result = analyze_assigned_races(cursor, cond, assigned_races)
        conditions.append(result)
        total_bets += result['bets']
        total_hits += result['hits']
        total_investment += result['investment']
        total_payout += result['payout']

    total = {
        'bets': total_bets,
        'hits': total_hits,
        'hit_rate': 100.0 * total_hits / total_bets if total_bets > 0 else 0,
        'investment': total_investment,
        'payout': total_payout,
        'roi': 100.0 * total_payout / total_investment if total_investment > 0 else 0,
        'profit': total_payout - total_investment,
    }

    return {'years': years, 'conditions': conditions, 'total': total}


def print_year_summary(label: str, total: Dict):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  件数 (unique):    {total['bets']:,} 件")
    print(f"  的中数:           {total['hits']:,} 件")
    print(f"  的中率:           {total['hit_rate']:.2f}%")
    print(f"  投資額:           {total['investment']:,} 円")
    print(f"  払戻額:           {total['payout']:,.0f} 円")
    print(f"  ROI:              {total['roi']:.1f}%")
    print(f"  収支:             {total['profit']:+,.0f} 円")


def print_condition_table(conditions: List[Dict]):
    print(f"\n  {'条件':<30} {'件数':>5} {'的中':>4} {'ROI':>8} {'収支':>12}")
    print(f"  {'-'*30} {'-'*5} {'-'*4} {'-'*8} {'-'*12}")
    for r in conditions:
        if r['bets'] > 0:
            print(f"  {r['name']:<30} {r['bets']:>5} {r['hits']:>4} "
                  f"{r['roi']:>7.1f}% {r['profit']:>+12,.0f}")


def main():
    parser = argparse.ArgumentParser(
        description='2018-2019年 過去OOSバックテスト（IS=2020-2025の条件を未使用期間で検証）'
    )
    parser.add_argument('--year', type=int, choices=OOS_YEARS,
                        help='単年のみ実行（2018 または 2019）')
    parser.add_argument('--save-json', type=str,
                        help='結果をJSONに保存（例: data/oos_2018_2019.json）')
    args = parser.parse_args()

    print()
    print("=" * 70)
    print("  2018-2019年 過去OOS バックテスト")
    print("  ※ IS期間（2020-2025）で開発した条件を未使用期間で検証")
    print("=" * 70)
    print(f"  実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("  【統計的注意】")
    print("  2018年~440件・2019年~245件のサンプルでは三連単ROIの分散が大きい。")
    print("  赤字=条件破綻 ではなく、まず誤検知確率を確認してから解釈すること。")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    output = {
        'generated_at': datetime.now().isoformat(),
        'description': '2018-2019 過去OOS（IS=2020-2025で開発した条件を未使用期間で検証）',
        'years': {},
        'combined': None,
    }

    target_years = [args.year] if args.year else OOS_YEARS

    # 単年別
    year_totals = {}
    for year in target_years:
        print(f"\n{'─'*70}")
        print(f"  【{year}年 OOS】")
        year_result = run_oos_single_year(cursor, year)
        print_year_summary(f"{year}年 OOS サマリー", year_result['total'])
        print_condition_table(year_result['conditions'])
        year_totals[year] = year_result['total']
        output['years'][str(year)] = year_result

    # 2018-2019合算（両年指定の場合のみ）
    if not args.year:
        print(f"\n{'─'*70}")
        print("  【2018-2019年 合算OOS（重複除外）】")
        combined = run_oos_combined(cursor, OOS_YEARS)
        print_year_summary("2018-2019年 合算OOS サマリー", combined['total'])
        print_condition_table(combined['conditions'])
        output['combined'] = combined

        # IS（2020-2025）との比較サマリー表示
        print("\n" + "=" * 70)
        print("  【IS vs OOS 比較サマリー】")
        print("  ※ IS(2020-2025)の数値はHANDOVER.md参照（v2.56.0ベースライン）")
        print(f"  {'期間':<20} {'件数':>6} {'ROI':>8} {'収支':>14}")
        print(f"  {'-'*20} {'-'*6} {'-'*8} {'-'*14}")
        for year in OOS_YEARS:
            t = year_totals[year]
            print(f"  {str(year)+'年 OOS':<20} {t['bets']:>6,} {t['roi']:>7.1f}% {t['profit']:>+14,.0f}")
        ct = combined['total']
        print(f"  {'2018-2019合算OOS':<20} {ct['bets']:>6,} {ct['roi']:>7.1f}% {ct['profit']:>+14,.0f}")
        print(f"  {'2020-2025 IS(参考)':<20} {'5,252':>6} {'245.7%':>8} {'+802,200':>14}")

    conn.close()

    if args.save_json:
        save_path = args.save_json
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] 結果を保存しました: {save_path}")

    print()


if __name__ == '__main__':
    main()
