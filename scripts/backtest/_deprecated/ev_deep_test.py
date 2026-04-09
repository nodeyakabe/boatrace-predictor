#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
EV方式 深掘り検証

【ユーザーの洞察】
  フィルタ後の世界でEVを使う = これが答え
  - フィルタで歪みを確保した母集団の中でEVを使う
  - EV閾値を下げてもOK（フィルタが既に歪んでいるから）
  - 市場順位 vs P-L順位のズレを使う

【検証内容】
  A. 低EV閾値（0.8, 0.9, 1.0 + 上位N点固定）
  B. EVソート上位N点固定方式（閾値なし）
  C. 市場順位 vs P-L順位ズレフィルター
  D. 2020-2023 IS / 2024-2025 OOS での安定性確認

使い方:
  python scripts/backtest/ev_deep_test.py --full
  python scripts/backtest/ev_deep_test.py --full --oos
"""

import sqlite3
import math
import sys
import os
import argparse

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


def evaluate_strategy(cond_map, score_map, odds_map, result_map, rank_map, strategy: dict) -> dict:
    """
    strategy keys:
      mode: 'ev_threshold' | 'top_n' | 'rank_gap'
      ev_threshold: float（mode=ev_thresholdのとき）
      odds_cap: float or None
      top_n: int（mode=top_nのとき）
      rank_gap_min: int（mode=rank_gapのとき。市場順位 - P-L順位 >= この値）
      fallback_1pt: bool（EV未達/条件未達時に1点買いへフォールバックするか）
    """
    mode = strategy.get('mode', 'ev_threshold')
    ev_threshold = strategy.get('ev_threshold', 1.0)
    odds_cap = strategy.get('odds_cap', None)
    top_n = strategy.get('top_n', 3)
    rank_gap_min = strategy.get('rank_gap_min', 2)
    fallback_1pt = strategy.get('fallback_1pt', False)

    stats = {'races': 0, 'bets': 0, 'invest': 0, 'payout': 0.0, 'hits': 0, 'skipped': 0}

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

        # --- 全120通りのEV計算 ---
        all_evs = []
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
                        all_evs.append((ev, cs, odds, a, b, c))

        # 修正: インデント修正版
        all_evs = []
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
                    all_evs.append((ev, cs, odds, a, b, c))

        all_evs.sort(reverse=True)  # EV降順

        selected = []

        if mode == 'ev_threshold':
            # EV閾値以上を全部選ぶ（max_bets上限なし）
            for ev, cs, odds, a, b, c in all_evs:
                if ev >= ev_threshold:
                    selected.append((ev, cs, odds))
            if not selected and fallback_1pt:
                cs = combo_123
                odds = odds_data.get(cs, 0)
                selected = [(0, cs, odds)] if odds > 0 else []

        elif mode == 'top_n':
            # EV上位N点を固定で選ぶ（閾値なし）
            selected = [(ev, cs, odds) for ev, cs, odds, _, _, _ in all_evs[:top_n]]

        elif mode == 'fixed_p123':
            # P1-P2-P3固定の1点買い（真の現行方式）
            cs = combo_123
            odds = odds_data.get(cs)
            if odds and odds > 0:
                selected = [(0, cs, odds)]

        elif mode == 'rank_gap':
            # 市場順位 vs P-L順位のズレが rank_gap_min 以上の組み合わせを買う
            # 市場人気順位 = オッズの昇順インデックス（1=最人気）
            market_rank = {}
            all_combos_odds = [(cs, o) for cs, o in odds_data.items() if o > 0]
            all_combos_odds.sort(key=lambda x: x[1])
            for idx, (cs, _) in enumerate(all_combos_odds):
                market_rank[cs] = idx + 1

            # P-L順位 = EV降順のインデックス
            pl_rank = {}
            for idx, (ev, cs, odds, _, _, _) in enumerate(all_evs):
                pl_rank[cs] = idx + 1

            for ev, cs, odds, a, b, c in all_evs:
                m_rank = market_rank.get(cs, 999)
                p_rank = pl_rank.get(cs, 999)
                gap = m_rank - p_rank  # 正 = P-Lがmarketより高く評価（お買い得）
                if gap >= rank_gap_min:
                    if odds_cap is None or odds <= odds_cap:
                        selected.append((ev, cs, odds))
            if not selected and fallback_1pt:
                cs = combo_123
                odds = odds_data.get(cs, 0)
                selected = [(0, cs, odds)] if odds > 0 else []

        if not selected:
            stats['skipped'] += 1
            continue

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
        stats['avg_bets'] = stats['bets'] / stats['races'] if stats['races'] > 0 else 0
    else:
        stats['roi'] = 0.0
        stats['profit'] = 0.0
        stats['hit_rate'] = 0.0
        stats['avg_bets'] = 0.0
    return stats


def get_period_data(cursor, start_date, end_date):
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
        return cond_map, {}, {}, {}, {}

    placeholders = ','.join(['?'] * len(race_ids))
    cursor.execute(f'''
        SELECT race_id, pit_number, total_score, rank_prediction
        FROM race_predictions
        WHERE race_id IN ({placeholders})
        AND prediction_type = 'before' AND total_score IS NOT NULL
    ''', race_ids)
    score_map, rank_map = {}, {}
    for rid, pit, sc, rp in cursor.fetchall():
        if rid not in score_map:
            score_map[rid] = {}
            rank_map[rid] = {}
        score_map[rid][pit] = sc
        rank_map[rid][pit] = rp

    cursor.execute(f'SELECT race_id, combination, odds FROM trifecta_odds WHERE race_id IN ({placeholders})', race_ids)
    odds_map = {}
    for rid, cs, odds in cursor.fetchall():
        if rid not in odds_map:
            odds_map[rid] = {}
        odds_map[rid][cs] = odds

    cursor.execute(f'''
        SELECT race_id, pit_number, rank FROM results
        WHERE race_id IN ({placeholders}) AND is_invalid=0 AND rank IN ('1','2','3')
    ''', race_ids)
    result_map = {}
    for rid, pit, rank in cursor.fetchall():
        if rid not in result_map:
            result_map[rid] = {}
        result_map[rid][rank] = pit

    return cond_map, score_map, odds_map, result_map, rank_map


def run_period(start_date, end_date, show_oos=False):
    strategies = [
        # === 現行ベースライン（P1-P2-P3固定） ===
        {'name': '現行_P1P2P3固定',  'mode': 'fixed_p123', 'odds_cap': None},

        # === A. 低EV閾値（フィルタ内EV、オッズ上限なし） ===
        {'name': 'EV>=0.8_上限なし',  'mode': 'ev_threshold', 'ev_threshold': 0.8,  'odds_cap': None},
        {'name': 'EV>=0.9_上限なし',  'mode': 'ev_threshold', 'ev_threshold': 0.9,  'odds_cap': None},
        {'name': 'EV>=1.0_上限なし',  'mode': 'ev_threshold', 'ev_threshold': 1.0,  'odds_cap': None},
        {'name': 'EV>=1.2_上限なし',  'mode': 'ev_threshold', 'ev_threshold': 1.2,  'odds_cap': None},

        # === A'. 低EV閾値（オッズ上限50倍） ===
        {'name': 'EV>=0.8_50倍',    'mode': 'ev_threshold', 'ev_threshold': 0.8,  'odds_cap': 50},
        {'name': 'EV>=0.9_50倍',    'mode': 'ev_threshold', 'ev_threshold': 0.9,  'odds_cap': 50},
        {'name': 'EV>=1.0_50倍',    'mode': 'ev_threshold', 'ev_threshold': 1.0,  'odds_cap': 50},
        {'name': 'EV>=1.2_50倍',    'mode': 'ev_threshold', 'ev_threshold': 1.2,  'odds_cap': 50},

        # === B. EVソート上位N点固定（閾値なし） ===
        {'name': 'Top1_50倍',       'mode': 'top_n', 'top_n': 1, 'odds_cap': 50},
        {'name': 'Top2_50倍',       'mode': 'top_n', 'top_n': 2, 'odds_cap': 50},
        {'name': 'Top3_50倍',       'mode': 'top_n', 'top_n': 3, 'odds_cap': 50},
        {'name': 'Top5_50倍',       'mode': 'top_n', 'top_n': 5, 'odds_cap': 50},
        {'name': 'Top1_上限なし',   'mode': 'top_n', 'top_n': 1, 'odds_cap': None},
        {'name': 'Top2_上限なし',   'mode': 'top_n', 'top_n': 2, 'odds_cap': None},
        {'name': 'Top3_上限なし',   'mode': 'top_n', 'top_n': 3, 'odds_cap': None},

        # === C. 市場順位 vs P-L順位ズレ ===
        {'name': 'ランクズレ>=2_50倍', 'mode': 'rank_gap', 'rank_gap_min': 2, 'odds_cap': 50},
        {'name': 'ランクズレ>=5_50倍', 'mode': 'rank_gap', 'rank_gap_min': 5, 'odds_cap': 50},
        {'name': 'ランクズレ>=10_50倍', 'mode': 'rank_gap', 'rank_gap_min': 10, 'odds_cap': 50},
        {'name': 'ランクズレ>=20_50倍', 'mode': 'rank_gap', 'rank_gap_min': 20, 'odds_cap': 50},
        {'name': 'ランクズレ>=2_上限なし', 'mode': 'rank_gap', 'rank_gap_min': 2, 'odds_cap': None},
        {'name': 'ランクズレ>=10_上限なし', 'mode': 'rank_gap', 'rank_gap_min': 10, 'odds_cap': None},
    ]

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cond_map, score_map, odds_map, result_map, rank_map = get_period_data(cursor, start_date, end_date)

    print(f"対象レース: {len(cond_map):,}件  ({start_date} - {end_date})")
    print()

    results = {}
    for s in strategies:
        name = s['name']
        st = evaluate_strategy(cond_map, score_map, odds_map, result_map, rank_map, s)
        results[name] = st

    return results


def print_results(all_results: dict, label: str = ''):
    """results = {year: {name: stats}}"""
    if label:
        print(f"\n{'='*85}")
        print(f"  {label}")
        print(f"{'='*85}")

    # 戦略名一覧（最初の年から取得）
    first_year = next(iter(all_results))
    strategy_names = list(all_results[first_year].keys())

    # 6年間合計を計算
    totals = {name: {'races': 0, 'bets': 0, 'invest': 0, 'payout': 0.0, 'hits': 0}
              for name in strategy_names}
    for year, year_res in all_results.items():
        for name, s in year_res.items():
            for k in ['races', 'bets', 'invest', 'hits']:
                totals[name][k] += s[k]
            totals[name]['payout'] += s['payout']

    # 集計
    for name in strategy_names:
        t = totals[name]
        if t['invest'] > 0:
            t['roi'] = t['payout'] / t['invest'] * 100
            t['profit'] = t['payout'] - t['invest']
            t['hit_rate'] = t['hits'] / t['races'] * 100 if t['races'] > 0 else 0
            t['avg_bets'] = t['bets'] / t['races'] if t['races'] > 0 else 0
        else:
            t['roi'] = 0.0
            t['profit'] = 0.0
            t['hit_rate'] = 0.0
            t['avg_bets'] = 0.0

    baseline_profit = totals['現行_P1P2P3固定']['profit']
    baseline_roi = totals['現行_P1P2P3固定']['roi']

    print(f"\n{'方式':<24} {'件数':>6} {'avg点':>5} {'投資':>9} {'収支':>10} {'ROI':>7} {'的中率':>7}  {'現行差'}")
    print("-" * 95)

    section_headers = {
        '現行_P1P2P3固定':       '--- ベースライン（P1-P2-P3固定）---',
        'EV>=0.8_上限なし':      '--- A. 低EV閾値（オッズ上限なし）---',
        'EV>=0.8_50倍':         '--- A\'. 低EV閾値（50倍上限）---',
        'Top1_50倍':            '--- B. EVソート上位N点固定（50倍上限）---',
        'Top1_上限なし':         '--- B\'. EVソート上位N点固定（上限なし）---',
        'ランクズレ>=2_50倍':     '--- C. 市場順位 vs P-L順位ズレ ---',
    }

    for name in strategy_names:
        if name in section_headers:
            print(f"\n  {section_headers[name]}")
        t = totals[name]
        diff = t['profit'] - baseline_profit
        diff_str = f"{'+' if diff>=0 else ''}{diff:,.0f}"
        marker = '<-- 現行' if name == '現行_P1P2P3固定' else diff_str
        print(f"  {name:<24} {t['races']:>6,} {t['avg_bets']:>4.1f}点 {t['invest']:>8,} "
              f"{t['profit']:>+9,.0f} {t['roi']:>6.1f}% {t['hit_rate']:>6.2f}%  {marker}")

    # 黒字年数の表
    print(f"\n{'方式':<24} ", end='')
    for year in sorted(all_results.keys()):
        print(f" {year}", end='')
    print("  黒字年")
    print("-" * 60)
    for name in strategy_names:
        black = 0
        print(f"  {name:<24}", end='')
        for year in sorted(all_results.keys()):
            s = all_results[year].get(name, {})
            profit = s.get('payout', 0) - s.get('invest', 0)
            mark = 'O' if profit > 0 else 'X'
            if profit > 0:
                black += 1
            print(f"  {mark}", end='')
        print(f"  {black}/{len(all_results)}年")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--full', action='store_true', help='6年間（2020-2025）')
    parser.add_argument('--oos', action='store_true', help='IS/OOS分割も表示')
    parser.add_argument('--year', type=int)
    args = parser.parse_args()

    if args.full:
        all_results = {}
        for year in range(2020, 2026):
            print(f"\n--- {year}年 ---")
            res = run_period(f'{year}-01-01', f'{year+1}-01-01')
            all_results[year] = res

        print_results(all_results, '6年間合計')

        if args.oos:
            print("\n\n" + "="*85)
            print("  OOS検証: IS=2020-2023 / OOS=2024-2025")
            print("="*85)

            is_results = {y: all_results[y] for y in range(2020, 2024)}
            oos_results = {y: all_results[y] for y in range(2024, 2026)}

            def summarize(res_dict):
                names = list(next(iter(res_dict.values())).keys())
                totals = {n: {'races': 0, 'bets': 0, 'invest': 0, 'payout': 0.0, 'hits': 0} for n in names}
                for yr, yr_res in res_dict.items():
                    for n, s in yr_res.items():
                        for k in ['races', 'bets', 'invest', 'hits']:
                            totals[n][k] += s[k]
                        totals[n]['payout'] += s['payout']
                for n in names:
                    t = totals[n]
                    t['roi'] = t['payout'] / t['invest'] * 100 if t['invest'] > 0 else 0
                    t['profit'] = t['payout'] - t['invest']
                    t['hit_rate'] = t['hits'] / t['races'] * 100 if t['races'] > 0 else 0
                    t['avg_bets'] = t['bets'] / t['races'] if t['races'] > 0 else 0
                return totals

            is_totals = summarize(is_results)
            oos_totals = summarize(oos_results)

            names = list(is_totals.keys())
            print(f"\n  {'方式':<24} {'IS ROI':>8} {'IS収支':>10} {'OOS ROI':>9} {'OOS収支':>10} {'劣化率':>8}")
            print("-" * 80)
            for name in names:
                is_t = is_totals[name]
                oos_t = oos_totals[name]
                if is_t['invest'] == 0 or oos_t['invest'] == 0:
                    continue
                deg = (is_t['roi'] - oos_t['roi']) / is_t['roi'] * 100 if is_t['roi'] > 0 else float('nan')
                verdict = ''
                if oos_t['roi'] >= 120:
                    verdict = '★'
                elif oos_t['roi'] >= 100:
                    verdict = '△'
                print(f"  {name:<24} {is_t['roi']:>7.1f}% {is_t['profit']:>+9,.0f} "
                      f"{oos_t['roi']:>8.1f}% {oos_t['profit']:>+9,.0f} {deg:>7.1f}% {verdict}")

    elif args.year:
        res = run_period(f'{args.year}-01-01', f'{args.year+1}-01-01')
        all_r = {args.year: res}
        print_results(all_r, f'{args.year}年')
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
