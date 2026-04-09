#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
検証A: 同一レースでの公平比較（現行1点買い vs EV方式）

【目的】
  Opusの指摘「現行7条件で選ばれた同じ1,610件に対して、
  1点買いとEV方式を公平比較する」を実施する。

  現行ev_backtest.pyは全レースを対象にしていたが、
  このスクリプトは完全に同一の1,610件レースを対象とする。

使い方:
  python scripts/backtest/ev_fair_comparison.py --full
  python scripts/backtest/ev_fair_comparison.py --year 2025
"""

import sqlite3
import math
import sys
import os
import argparse
import itertools
from typing import Dict, List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.standard_backtest_unique import assign_races_to_conditions

PL_SCALE = 20.0


def compute_pl_prob(scores: dict, combo: tuple) -> float:
    a, b, c = combo
    if not all(k in scores for k in [a, b, c]):
        return 0.0
    max_s = max(scores.values())
    exp_s = {k: math.exp((v - max_s) / PL_SCALE) for k, v in scores.items()}
    total = sum(exp_s.values())
    if total == 0:
        return 0.0
    pa = exp_s[a] / total
    denom_b = total - exp_s[a]
    if denom_b <= 0:
        return 0.0
    pb = exp_s[b] / denom_b
    denom_c = denom_b - exp_s[b]
    if denom_c <= 0:
        return 0.0
    pc = exp_s[c] / denom_c
    return pa * pb * pc


def run_fair_comparison(start_date: str, end_date: str):
    """
    同一レース集合に対して:
      (A) 現行: P1-P2-P3 の1点買い
      (B) EVパターン群: all120 × 各EV閾値 × オッズ上限
    を比較する
    """
    results = {}

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # 現行7条件で1,610件を取得
        assigned = assign_races_to_conditions(
            cursor, STANDARD_BET_CONDITIONS, start_date, end_date
        )
        # 条件ごとに割り当てられたレースをフラット化（重複なし）
        # ただし、条件のオッズチェックも必要なので条件情報も保持
        cond_map = {}  # race_id -> condition
        for cond in STANDARD_BET_CONDITIONS:
            cid = cond['id']
            for rid in assigned.get(cid, []):
                if rid not in cond_map:
                    cond_map[rid] = cond
        all_race_ids = list(cond_map.keys())

        if not all_race_ids:
            return {}

        # スコア・予測順位取得
        placeholders = ','.join(['?'] * len(all_race_ids))
        cursor.execute(f'''
            SELECT race_id, pit_number, total_score, rank_prediction
            FROM race_predictions
            WHERE race_id IN ({placeholders})
            AND prediction_type = 'before'
            AND total_score IS NOT NULL
        ''', all_race_ids)

        score_map = {}
        rank_map = {}
        for rid, pit, sc, rp in cursor.fetchall():
            if rid not in score_map:
                score_map[rid] = {}
                rank_map[rid] = {}
            score_map[rid][pit] = sc
            rank_map[rid][pit] = rp

        # オッズ取得
        cursor.execute(f'''
            SELECT race_id, combination, odds
            FROM trifecta_odds
            WHERE race_id IN ({placeholders})
        ''', all_race_ids)
        odds_map = {}
        for rid, combo_str, odds in cursor.fetchall():
            if rid not in odds_map:
                odds_map[rid] = {}
            odds_map[rid][combo_str] = odds

        # 実際の結果取得
        cursor.execute(f'''
            SELECT race_id, pit_number, rank
            FROM results
            WHERE race_id IN ({placeholders})
            AND is_invalid=0 AND rank IN ('1','2','3')
        ''', all_race_ids)
        result_map = {}
        for rid, pit, rank in cursor.fetchall():
            if rid not in result_map:
                result_map[rid] = {}
            result_map[rid][rank] = pit

    # 比較パターン定義
    # (名前, EV閾値, オッズ上限, max_bets)
    patterns = [
        # 現行方式
        ('現行_1点買い', None, None, 1),
        # EV方式（各閾値×オッズ上限）
        ('EV1.0_上限なし', 1.0, None, 9),
        ('EV2.0_上限なし', 2.0, None, 9),
        ('EV3.0_上限なし', 3.0, None, 9),
        ('EV1.0_50倍上限', 1.0, 50, 9),
        ('EV2.0_50倍上限', 2.0, 50, 9),
        ('EV3.0_50倍上限', 3.0, 50, 9),
        ('EV1.5_50倍上限', 1.5, 50, 9),
        ('EV2.5_50倍上限', 2.5, 50, 9),
        # フォールバックなし（EV未達はスキップ）
        ('EV3.0_50倍_fb無', 3.0, 50, 9),
    ]

    # 各パターンの集計器
    stats = {p[0]: {'races': 0, 'bets': 0, 'invest': 0, 'payout': 0.0, 'hits': 0}
             for p in patterns}

    valid_races = 0
    for rid in all_race_ids:
        scores = score_map.get(rid)
        odds_data = odds_map.get(rid)
        res = result_map.get(rid)
        cond = cond_map[rid]

        if not scores or not odds_data or not res:
            continue
        if '1' not in res or '2' not in res or '3' not in res:
            continue
        pits = list(scores.keys())
        if len(pits) < 4:
            continue

        # 予測1-2-3のpit番号
        rm = rank_map.get(rid, {})
        pred_sorted = sorted([(rm.get(p, 9), p) for p in pits])
        pred_ranks = [p for _, p in pred_sorted]

        p1, p2, p3 = pred_ranks[0], pred_ranks[1], pred_ranks[2]
        combo_123 = f"{p1}-{p2}-{p3}"

        # 条件のオッズ帯チェック（現行と同じ）
        odds_main = odds_data.get(combo_123)
        if odds_main is None:
            continue
        odds_min = cond.get('odds_min', 0)
        odds_max_cond = cond.get('odds_max', 9999)
        if not (odds_min <= odds_main < odds_max_cond):
            continue

        actual = f"{res['1']}-{res['2']}-{res['3']}"
        valid_races += 1

        for pattern_name, ev_threshold, odds_cap, max_bets in patterns:
            if pattern_name == '現行_1点買い':
                # 1点買いのみ
                pay = odds_data.get(combo_123, 0) * 100 if combo_123 == actual else 0
                stats[pattern_name]['races'] += 1
                stats[pattern_name]['bets'] += 1
                stats[pattern_name]['invest'] += 100
                stats[pattern_name]['payout'] += pay
                if pay > 0:
                    stats[pattern_name]['hits'] += 1
            else:
                # all120でEV計算
                selected = []
                for a in pits:
                    for b in pits:
                        if b == a:
                            continue
                        for c in pits:
                            if c == a or c == b:
                                continue
                            cs = f"{a}-{b}-{c}"
                            odds = odds_data.get(cs)
                            if odds is None or odds <= 0:
                                continue
                            if odds_cap is not None and odds > odds_cap:
                                continue
                            pl = compute_pl_prob(scores, (a, b, c))
                            ev = pl * odds
                            if ev >= ev_threshold:
                                selected.append((ev, cs, odds))

                # EV降順ソート、max_bets制限
                selected.sort(reverse=True)
                selected = selected[:max_bets]

                if not selected:
                    # EV未達: フォールバックなし（スキップ）
                    continue

                invest = len(selected) * 100
                payout = 0.0
                hit = 0
                for _, cs, odds in selected:
                    if cs == actual:
                        payout = odds * 100
                        hit = 1
                        break

                stats[pattern_name]['races'] += 1
                stats[pattern_name]['bets'] += len(selected)
                stats[pattern_name]['invest'] += invest
                stats[pattern_name]['payout'] += payout
                if hit:
                    stats[pattern_name]['hits'] += 1

    return stats, valid_races


def print_comparison(stats_dict: dict, valid_races: int, label: str = ''):
    if label:
        print(f"\n{'='*75}")
        print(f"  {label}（対象: {valid_races:,}件）")
        print(f"{'='*75}")

    print(f"  {'方式':<22} {'件数':>6} {'avg点':>6} {'投資':>9} {'払戻':>9} {'収支':>10} {'ROI':>7} {'的中率':>7}")
    print("-" * 85)

    baseline_profit = None
    for name, s in stats_dict.items():
        if s['races'] == 0:
            continue
        invest = s['invest']
        payout = s['payout']
        profit = payout - invest
        roi = payout / invest * 100 if invest > 0 else 0
        hit_rate = s['hits'] / s['races'] * 100 if s['races'] > 0 else 0
        avg_bets = s['bets'] / s['races'] if s['races'] > 0 else 0

        if name == '現行_1点買い':
            baseline_profit = profit
            marker = '<-- 現行'
        else:
            diff = profit - baseline_profit if baseline_profit is not None else 0
            marker = f"({'+'  if diff >= 0 else ''}{diff:,.0f}円)"

        print(f"  {name:<22} {s['races']:>6,} {avg_bets:>5.1f}点 {invest:>8,} {payout:>8,.0f} "
              f"{profit:>+9,.0f} {roi:>6.1f}% {hit_rate:>6.2f}% {marker}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int)
    parser.add_argument('--full', action='store_true')
    args = parser.parse_args()

    if args.full:
        print("=== 6年間 年度別 公平比較 ===\n")
        # 年別サマリー
        yearly_totals = {}
        for year in range(2020, 2026):
            s = f'{year}-01-01'
            e = f'{year+1}-01-01'
            result = run_fair_comparison(s, e)
            if not result:
                continue
            stats, valid_races = result
            print(f"\n--- {year}年 ({valid_races}件) ---")
            print(f"  {'方式':<22} {'件数':>5} {'投資':>8} {'収支':>9} {'ROI':>7} {'的中率':>7}")
            print("-" * 65)
            baseline_p = None
            for name, sv in stats.items():
                if sv['races'] == 0:
                    continue
                invest = sv['invest']
                payout = sv['payout']
                profit = payout - invest
                roi = payout / invest * 100 if invest > 0 else 0
                hr = sv['hits'] / sv['races'] * 100 if sv['races'] > 0 else 0
                avg_b = sv['bets'] / sv['races'] if sv['races'] > 0 else 0
                if name == '現行_1点買い':
                    baseline_p = profit
                diff_str = ''
                if baseline_p is not None and name != '現行_1点買い':
                    diff = profit - baseline_p
                    diff_str = f" ({'+' if diff>=0 else ''}{diff:,.0f})"
                print(f"  {name:<22} {sv['races']:>5} {invest:>7,} {profit:>+8,.0f} {roi:>6.1f}% {hr:>6.2f}%{diff_str}")
                if name not in yearly_totals:
                    yearly_totals[name] = {'races': 0, 'invest': 0, 'payout': 0.0, 'hits': 0, 'bets': 0}
                for k in ['races', 'invest', 'bets', 'hits']:
                    yearly_totals[name][k] += sv[k]
                yearly_totals[name]['payout'] += sv['payout']

        # 6年間合計
        print(f"\n{'='*75}")
        print("  6年間合計")
        print(f"{'='*75}")
        print(f"  {'方式':<22} {'件数':>6} {'avg点':>6} {'投資':>9} {'収支':>10} {'ROI':>7} {'的中率':>7}")
        print("-" * 80)
        baseline_p6 = None
        for name, sv in yearly_totals.items():
            if sv['races'] == 0:
                continue
            invest = sv['invest']
            payout = sv['payout']
            profit = payout - invest
            roi = payout / invest * 100 if invest > 0 else 0
            hr = sv['hits'] / sv['races'] * 100 if sv['races'] > 0 else 0
            avg_b = sv['bets'] / sv['races'] if sv['races'] > 0 else 0
            if name == '現行_1点買い':
                baseline_p6 = profit
            diff_str = ''
            if baseline_p6 is not None and name != '現行_1点買い':
                diff = profit - baseline_p6
                diff_str = f" ({'+' if diff>=0 else ''}{diff:,.0f})"
            print(f"  {name:<22} {sv['races']:>6,} {avg_b:>5.1f}点 {invest:>8,} {profit:>+9,.0f} {roi:>6.1f}% {hr:>6.2f}%{diff_str}")

    elif args.year:
        s = f'{args.year}-01-01'
        e = f'{args.year+1}-01-01'
        stats, valid_races = run_fair_comparison(s, e)
        print_comparison(stats, valid_races, f'{args.year}年')
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
