#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
検証B: 時系列OOS検証（過学習検出）

【目的】
  EV閾値とオッズ上限パラメータを
  2020-2023年（In-sample）で選定し、
  2024-2025年（OOS: Out-of-Sample）で検証する。

  「過学習か否か」の最終判断スクリプト。

判断基準:
  OOS ROI >= 120%             → EV方式は機能する（採用検討）
  OOS ROI 100-120%            → 損益分岐点付近（条件付き採用）
  OOS ROI < 100%              → 過学習（不採用）
  OOS vs IS 劣化率 <= 30%     → 過学習は軽微
  OOS vs IS 劣化率 > 50%      → 過学習が支配的

使い方:
  python scripts/backtest/ev_oos_validation.py
"""

import sqlite3
import math
import sys
import os
import argparse
import itertools
from typing import Dict, List

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


def get_data_for_period(cursor, start_date: str, end_date: str):
    """指定期間の条件通過レースデータを取得"""
    assigned = assign_races_to_conditions(
        cursor, STANDARD_BET_CONDITIONS, start_date, end_date
    )
    cond_map = {}
    for cond in STANDARD_BET_CONDITIONS:
        for rid in assigned.get(cond['id'], []):
            if rid not in cond_map:
                cond_map[rid] = cond
    race_ids = list(cond_map.keys())
    if not race_ids:
        return {}, {}, {}, {}

    placeholders = ','.join(['?'] * len(race_ids))

    cursor.execute(f'''
        SELECT race_id, pit_number, total_score, rank_prediction
        FROM race_predictions
        WHERE race_id IN ({placeholders})
        AND prediction_type = 'before' AND total_score IS NOT NULL
    ''', race_ids)
    score_map = {}
    rank_map = {}
    for rid, pit, sc, rp in cursor.fetchall():
        if rid not in score_map:
            score_map[rid] = {}
            rank_map[rid] = {}
        score_map[rid][pit] = sc
        rank_map[rid][pit] = rp

    cursor.execute(f'''
        SELECT race_id, combination, odds FROM trifecta_odds
        WHERE race_id IN ({placeholders})
    ''', race_ids)
    odds_map = {}
    for rid, cs, odds in cursor.fetchall():
        if rid not in odds_map:
            odds_map[rid] = {}
        odds_map[rid][cs] = odds

    cursor.execute(f'''
        SELECT race_id, pit_number, rank FROM results
        WHERE race_id IN ({placeholders})
        AND is_invalid=0 AND rank IN ('1','2','3')
    ''', race_ids)
    result_map = {}
    for rid, pit, rank in cursor.fetchall():
        if rid not in result_map:
            result_map[rid] = {}
        result_map[rid][rank] = pit

    return cond_map, score_map, odds_map, result_map, rank_map


def evaluate_params(cond_map, score_map, odds_map, result_map, rank_map,
                    ev_threshold: float, odds_cap: float):
    """指定パラメータでEV方式の成績を計算"""
    stats = {'races': 0, 'bets': 0, 'invest': 0, 'payout': 0.0, 'hits': 0}

    for rid, cond in cond_map.items():
        scores = score_map.get(rid)
        odds_data = odds_map.get(rid)
        res = result_map.get(rid)
        rm = rank_map.get(rid, {})
        if not scores or not odds_data or not res:
            continue
        if '1' not in res or '2' not in res or '3' not in res:
            continue
        pits = list(scores.keys())
        if len(pits) < 4:
            continue

        pred_sorted = sorted([(rm.get(p, 9), p) for p in pits])
        pred_ranks = [p for _, p in pred_sorted]
        p1, p2, p3 = pred_ranks[0], pred_ranks[1], pred_ranks[2]
        combo_123 = f"{p1}-{p2}-{p3}"
        odds_main = odds_data.get(combo_123)
        if odds_main is None:
            continue
        odds_min = cond.get('odds_min', 0)
        odds_max_cond = cond.get('odds_max', 9999)
        if not (odds_min <= odds_main < odds_max_cond):
            continue

        actual = f"{res['1']}-{res['2']}-{res['3']}"

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

        if not selected:
            continue

        selected.sort(reverse=True)
        invest = len(selected) * 100
        payout = 0.0
        hit = 0
        for _, cs, odds in selected:
            if cs == actual:
                payout = odds * 100
                hit = 1
                break

        stats['races'] += 1
        stats['bets'] += len(selected)
        stats['invest'] += invest
        stats['payout'] += payout
        if hit:
            stats['hits'] += 1

    if stats['invest'] > 0:
        stats['roi'] = stats['payout'] / stats['invest'] * 100
        stats['profit'] = stats['payout'] - stats['invest']
        stats['hit_rate'] = stats['hits'] / stats['races'] * 100 if stats['races'] > 0 else 0
    else:
        stats['roi'] = 0.0
        stats['profit'] = 0.0
        stats['hit_rate'] = 0.0

    return stats


def main():
    # パラメータグリッド
    ev_thresholds = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    odds_caps = [None, 50, 100, 200]

    # 現行1点買いも計算用
    BASELINE_NAME = '現行_1点買い'

    print("=== 時系列OOS検証 ===")
    print("  In-sample  (IS):  2020-2023年（4年間）")
    print("  Out-of-Sample (OOS): 2024-2025年（2年間）")
    print()

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        print("IS期間データ取得中（2020-2023）...", flush=True)
        is_result = get_data_for_period(cursor, '2020-01-01', '2024-01-01')
        if len(is_result) == 5:
            is_cond, is_score, is_odds, is_result_map, is_rank = is_result
        else:
            print("IS データ取得失敗")
            return

        print("OOS期間データ取得中（2024-2025）...", flush=True)
        oos_result = get_data_for_period(cursor, '2024-01-01', '2026-01-01')
        if len(oos_result) == 5:
            oos_cond, oos_score, oos_odds, oos_result_map, oos_rank = oos_result
        else:
            print("OOS データ取得失敗")
            return

    print(f"IS レース数: {len(is_cond):,}件  OOS レース数: {len(oos_cond):,}件\n")

    # --- IS期間での全パラメータグリッドサーチ ---
    print("=== IS（2020-2023）全パラメータ評価 ===")
    print(f"  {'EV閾値':>7} {'上限':>7} {'IS件数':>7} {'IS投資':>9} {'IS収支':>10} {'IS ROI':>8}")
    print("-" * 65)

    is_results = {}
    for ev_th in ev_thresholds:
        for odds_cap in odds_caps:
            key = (ev_th, odds_cap)
            s = evaluate_params(is_cond, is_score, is_odds, is_result_map, is_rank,
                                ev_th, odds_cap)
            is_results[key] = s
            cap_str = f"{odds_cap:.0f}倍" if odds_cap else " なし"
            print(f"  EV>={ev_th:.1f}  {cap_str:>7}  {s['races']:>7,}  "
                  f"{s['invest']:>8,}  {s['profit']:>+9,.0f}  {s['roi']:>7.1f}%")

    # IS期間のベースライン（1点買い）
    is_baseline_s = {'races': 0, 'bets': 0, 'invest': 0, 'payout': 0.0, 'hits': 0}
    for rid, cond in is_cond.items():
        scores = is_score.get(rid)
        odds_data = is_odds.get(rid)
        res = is_result_map.get(rid)
        rm = is_rank.get(rid, {})
        if not scores or not odds_data or not res:
            continue
        if '1' not in res or '2' not in res or '3' not in res:
            continue
        pits = list(scores.keys())
        if len(pits) < 4:
            continue
        pred_sorted = sorted([(rm.get(p, 9), p) for p in pits])
        pred_ranks = [p for _, p in pred_sorted]
        p1, p2, p3 = pred_ranks[0], pred_ranks[1], pred_ranks[2]
        combo_123 = f"{p1}-{p2}-{p3}"
        odds_main = odds_data.get(combo_123)
        if odds_main is None:
            continue
        odds_min = cond.get('odds_min', 0)
        odds_max_cond = cond.get('odds_max', 9999)
        if not (odds_min <= odds_main < odds_max_cond):
            continue
        actual = f"{res['1']}-{res['2']}-{res['3']}"
        pay = odds_data.get(combo_123, 0) * 100 if combo_123 == actual else 0
        is_baseline_s['races'] += 1
        is_baseline_s['bets'] += 1
        is_baseline_s['invest'] += 100
        is_baseline_s['payout'] += pay
        if pay > 0:
            is_baseline_s['hits'] += 1
    is_baseline_s['roi'] = is_baseline_s['payout'] / is_baseline_s['invest'] * 100 if is_baseline_s['invest'] > 0 else 0
    is_baseline_s['profit'] = is_baseline_s['payout'] - is_baseline_s['invest']

    print(f"  現行1点買い  （参考）  {is_baseline_s['races']:>7,}  "
          f"{is_baseline_s['invest']:>8,}  {is_baseline_s['profit']:>+9,.0f}  {is_baseline_s['roi']:>7.1f}%")

    # --- IS上位5パラメータ選定 ---
    print("\n=== IS上位5パラメータ（IS ROI降順） ===")
    sorted_is = sorted(is_results.items(), key=lambda x: x[1]['roi'], reverse=True)
    top5 = [(k, v) for k, v in sorted_is if v['races'] >= 50][:5]  # 最低50件以上
    print(f"  {'EV閾値':>7} {'上限':>7} {'IS件数':>7} {'IS ROI':>8} {'IS収支':>10}")
    print("-" * 55)
    for (ev_th, odds_cap), s in top5:
        cap_str = f"{odds_cap:.0f}倍" if odds_cap else " なし"
        print(f"  EV>={ev_th:.1f}  {cap_str:>7}  {s['races']:>7,}  {s['roi']:>7.1f}%  {s['profit']:>+9,.0f}")

    # --- OOS検証（IS上位5パラメータ + 現行1点買い） ---
    print("\n=== OOS（2024-2025）検証結果 ===")
    print(f"  {'パラメータ':>22} {'OOS件数':>8} {'OOS投資':>9} {'OOS収支':>10} {'OOS ROI':>8} {'IS ROI':>8} {'劣化率':>8} {'判定'}")
    print("-" * 90)

    # OOSベースライン（1点買い）
    oos_baseline_s = {'races': 0, 'bets': 0, 'invest': 0, 'payout': 0.0, 'hits': 0}
    for rid, cond in oos_cond.items():
        scores = oos_score.get(rid)
        odds_data = oos_odds.get(rid)
        res = oos_result_map.get(rid)
        rm = oos_rank.get(rid, {})
        if not scores or not odds_data or not res:
            continue
        if '1' not in res or '2' not in res or '3' not in res:
            continue
        pits = list(scores.keys())
        if len(pits) < 4:
            continue
        pred_sorted = sorted([(rm.get(p, 9), p) for p in pits])
        pred_ranks = [p for _, p in pred_sorted]
        p1, p2, p3 = pred_ranks[0], pred_ranks[1], pred_ranks[2]
        combo_123 = f"{p1}-{p2}-{p3}"
        odds_main = odds_data.get(combo_123)
        if odds_main is None:
            continue
        odds_min = cond.get('odds_min', 0)
        odds_max_cond = cond.get('odds_max', 9999)
        if not (odds_min <= odds_main < odds_max_cond):
            continue
        actual = f"{res['1']}-{res['2']}-{res['3']}"
        pay = odds_data.get(combo_123, 0) * 100 if combo_123 == actual else 0
        oos_baseline_s['races'] += 1
        oos_baseline_s['invest'] += 100
        oos_baseline_s['payout'] += pay
        if pay > 0:
            oos_baseline_s['hits'] += 1
    oos_baseline_s['roi'] = oos_baseline_s['payout'] / oos_baseline_s['invest'] * 100 if oos_baseline_s['invest'] > 0 else 0
    oos_baseline_s['profit'] = oos_baseline_s['payout'] - oos_baseline_s['invest']
    print(f"  {'現行_1点買い（参考）':>22}  {oos_baseline_s['races']:>8,}  "
          f"{oos_baseline_s['invest']:>8,}  {oos_baseline_s['profit']:>+9,.0f}  "
          f"{oos_baseline_s['roi']:>7.1f}%  {'---':>8}  {'---':>8}  ---")

    # 全パラメータのOOS結果
    print()
    oos_results = {}
    for ev_th in ev_thresholds:
        for odds_cap in odds_caps:
            key = (ev_th, odds_cap)
            s = evaluate_params(oos_cond, oos_score, oos_odds, oos_result_map, oos_rank,
                                ev_th, odds_cap)
            oos_results[key] = s
            is_s = is_results[key]
            if s['races'] < 10:
                continue
            if is_s['roi'] > 0:
                degradation = (is_s['roi'] - s['roi']) / is_s['roi'] * 100
            else:
                degradation = float('nan')

            cap_str = f"{odds_cap:.0f}倍" if odds_cap else " なし"
            param_name = f"EV>={ev_th:.1f}/{cap_str}"

            if s['roi'] >= 120:
                verdict = "★採用候補"
            elif s['roi'] >= 100:
                verdict = "△要検討"
            else:
                verdict = "×不採用"

            print(f"  {param_name:>22}  {s['races']:>8,}  {s['invest']:>8,}  {s['profit']:>+9,.0f}  "
                  f"{s['roi']:>7.1f}%  {is_s['roi']:>7.1f}%  "
                  f"{degradation:>7.1f}%  {verdict}")

    # --- 最終判定サマリー ---
    print("\n" + "=" * 90)
    print("=== 最終判定 ===")

    # OOS>=100% のパラメータを抽出
    viable = [(k, oos_results[k]) for k in oos_results
              if oos_results[k].get('races', 0) >= 20
              and oos_results[k].get('roi', 0) >= 100]
    viable.sort(key=lambda x: x[1]['roi'], reverse=True)

    if viable:
        print(f"\n  OOS ROI >= 100% のパラメータ: {len(viable)}個")
        for (ev_th, odds_cap), s in viable[:5]:
            cap_str = f"{odds_cap:.0f}倍" if odds_cap else "なし"
            is_s = is_results[(ev_th, odds_cap)]
            print(f"    EV>={ev_th:.1f} 上限{cap_str}: OOS {s['roi']:.1f}% / IS {is_s['roi']:.1f}% / OOS件数{s['races']}件")

        best_k, best_s = viable[0]
        ev_best, cap_best = best_k
        is_best = is_results[best_k]

        print(f"\n  最有望パラメータ: EV>={ev_best:.1f} / 上限{'なし' if cap_best is None else f'{cap_best}倍'}")
        print(f"    IS ROI: {is_best['roi']:.1f}%  OOS ROI: {best_s['roi']:.1f}%")
        if is_best['roi'] > 0:
            deg = (is_best['roi'] - best_s['roi']) / is_best['roi'] * 100
            print(f"    劣化率: {deg:.1f}%  （30%以内なら過学習は軽微）")

        if best_s['roi'] >= 120:
            print("\n  【最終結論】EV方式は機能する可能性がある -> 本採用を検討")
            print("  ただし: OOS期間2年のみのため、さらなる実運用での検証を推奨")
        elif best_s['roi'] >= 100:
            print("\n  【最終結論】EV方式は損益分岐点付近 -> 条件付き採用")
            print("  絶対収支は現行1点買いより少ないため、ROI重視なら採用検討")
        else:
            print("\n  【最終結論】EV方式は過学習の疑いが強い -> 現行1点買いを維持推奨")
    else:
        print("\n  OOS ROI >= 100% のパラメータなし")
        print("  【最終結論】EV方式は過学習 -> 現行1点買いを維持推奨")

    print(f"\n  【参考】現行1点買いのOOS成績: {oos_baseline_s['roi']:.1f}% / 収支{oos_baseline_s['profit']:+,.0f}円 ({oos_baseline_s['races']}件)")


if __name__ == '__main__':
    main()
