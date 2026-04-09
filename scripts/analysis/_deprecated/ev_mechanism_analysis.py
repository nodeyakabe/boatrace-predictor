#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
検証C: EV方式の動作メカニズム分析

【目的】
  EV方式が「P-Lの精度に基づいて機能している」のか
  「高オッズの宝くじを買うことでたまたま当たっている」のかを区別する。

  具体的に以下を分析:
  1. EV値バケット別の実際ROI（EVが高いほどROIが高いなら機能している）
  2. 的中買い目の特性（どのパターンで当たっているか）
  3. 外れ買い目の特性（高EV外れの分析）

使い方:
  python scripts/analysis/ev_mechanism_analysis.py
  python scripts/analysis/ev_mechanism_analysis.py --years 2020 2021 2022 2023 2024
"""

import sqlite3
import math
import sys
import os
import argparse
import numpy as np

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


def analyze_ev_mechanism(years: list):
    print(f"EV方式メカニズム分析: {years}年")
    print("対象: 7条件通過レース × all120通り × 各買目オッズ取得")

    # データ収集: (ev, odds, pl_prob, hit, pattern, combo_str) のリスト
    records = []

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # 全年の条件通過レースIDを取得
        condition_race_ids = set()
        for year in years:
            assigned = assign_races_to_conditions(
                cursor, STANDARD_BET_CONDITIONS,
                f'{year}-01-01', f'{year+1}-01-01'
            )
            for ids in assigned.values():
                condition_race_ids.update(ids)
        print(f"条件通過レース: {len(condition_race_ids):,}件\n")

        for year in years:
            start = f'{year}-01-01'
            end = f'{year+1}-01-01'
            print(f"  {year}年 処理中...", end='', flush=True)

            # 対象年のレースIDを絞る
            cursor.execute('''
                SELECT id FROM races
                WHERE race_date >= ? AND race_date < ?
            ''', (start, end))
            year_race_ids = {row[0] for row in cursor.fetchall()}
            target_ids = list(condition_race_ids & year_race_ids)
            if not target_ids:
                print(" 0件")
                continue

            # スコア・予測順位取得
            placeholders = ','.join(['?'] * len(target_ids))
            cursor.execute(f'''
                SELECT race_id, pit_number, total_score, rank_prediction
                FROM race_predictions
                WHERE race_id IN ({placeholders})
                AND prediction_type = 'before'
                AND total_score IS NOT NULL
            ''', target_ids)

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
            ''', target_ids)
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
            ''', target_ids)
            result_map = {}
            for rid, pit, rank in cursor.fetchall():
                if rid not in result_map:
                    result_map[rid] = {}
                result_map[rid][rank] = pit

            # 全120通りでEV計算
            count = 0
            for rid in target_ids:
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

                actual = (res['1'], res['2'], res['3'])
                actual_str = f"{actual[0]}-{actual[1]}-{actual[2]}"

                for a in pits:
                    for b in pits:
                        if b == a:
                            continue
                        for c in pits:
                            if c == a or c == b:
                                continue
                            combo_str = f"{a}-{b}-{c}"
                            odds = odds_data.get(combo_str)
                            if odds is None or odds <= 0:
                                continue

                            pl = compute_pl_prob(scores, (a, b, c))
                            if pl <= 0:
                                continue

                            ev = pl * odds
                            hit = 1 if combo_str == actual_str else 0

                            rank_a = rm.get(a, 9)
                            rank_b = rm.get(b, 9)
                            rank_c = rm.get(c, 9)
                            pattern = f"P{rank_a}-P{rank_b}-P{rank_c}"

                            records.append({
                                'ev': ev,
                                'odds': odds,
                                'pl': pl,
                                'hit': hit,
                                'pattern': pattern,
                                'combo': combo_str,
                                'year': year
                            })
                            count += 1

            print(f" {count:,}点")

    if not records:
        print("データなし")
        return

    evs = np.array([r['ev'] for r in records])
    odds_arr = np.array([r['odds'] for r in records])
    pls = np.array([r['pl'] for r in records])
    hits = np.array([r['hit'] for r in records])
    patterns = np.array([r['pattern'] for r in records])

    print(f"\n合計: {len(records):,}点  的中: {hits.sum():.0f}回  的中率: {hits.mean()*100:.3f}%")

    # --- 分析1: EV値バケット別ROI ---
    # 「EVが高い組み合わせほど実際のROIが高い」なら、P-Lが機能している証拠
    print("\n=== 分析1: EV値バケット別 ROI（機能確認） ===")
    print("  EVが高いほどROIが高ければ『P-L精度に基づいて機能』している")
    print(f"  {'EV帯':>10} {'件数':>8} {'投資':>9} {'払戻':>9} {'ROI':>8} {'的中率':>8}")
    print("-" * 65)

    ev_bins = [0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0, float('inf')]
    for lo, hi in zip(ev_bins[:-1], ev_bins[1:]):
        mask = (evs >= lo) & (evs < hi)
        n = int(mask.sum())
        if n < 10:
            continue
        invest = n * 100
        payout = float((hits[mask] * odds_arr[mask] * 100).sum())
        roi = payout / invest * 100
        hit_rate = float(hits[mask].mean()) * 100
        hi_str = f"{hi:.1f}" if hi != float('inf') else "inf"
        print(f"  {lo:.1f}-{hi_str:>6}  {n:>8,}  {invest:>8,}  {payout:>8,.0f}  {roi:>7.1f}%  {hit_rate:>7.3f}%")

    # --- 分析2: EV>=3.0かつオッズ<=50倍フィルター（best案）の内訳 ---
    print("\n=== 分析2: EV>=3.0 + オッズ<=50倍フィルターの内訳 ===")
    best_mask = (evs >= 3.0) & (odds_arr <= 50)
    n_best = int(best_mask.sum())
    print(f"  該当買い目: {n_best:,}点  的中: {hits[best_mask].sum():.0f}回  "
          f"的中率: {hits[best_mask].mean()*100:.3f}%  "
          f"ROI: {(hits[best_mask]*odds_arr[best_mask]*100).sum()/(n_best*100)*100:.1f}%")

    # 的中買い目のパターン分析
    hit_mask = best_mask & (hits == 1)
    miss_mask = best_mask & (hits == 0)
    hit_patterns = patterns[hit_mask]
    hit_odds = odds_arr[hit_mask]
    hit_pls = pls[hit_mask]
    miss_patterns = patterns[miss_mask]
    miss_pls = pls[miss_mask]

    print(f"\n  【的中 {int(hit_mask.sum())}回 の特性】")
    print(f"    オッズ平均: {hit_odds.mean():.1f}倍  中央値: {np.median(hit_odds):.1f}倍  最大: {hit_odds.max():.1f}倍")
    print(f"    P-L確率平均: {hit_pls.mean()*100:.3f}%  中央値: {np.median(hit_pls)*100:.3f}%")
    print(f"    オッズ分布: <20倍: {(hit_odds < 20).sum()}回  20-30倍: {((hit_odds>=20)&(hit_odds<30)).sum()}回  "
          f"30-40倍: {((hit_odds>=30)&(hit_odds<40)).sum()}回  40-50倍: {((hit_odds>=40)&(hit_odds<=50)).sum()}回")

    print(f"\n  【的中パターン（上位）】")
    upats, ucounts = np.unique(hit_patterns, return_counts=True)
    order = np.argsort(-ucounts)
    for i in order[:8]:
        pat = upats[i]
        cnt = ucounts[i]
        pmask = hit_mask & (patterns == pat)
        avg_pl = float(pls[pmask].mean()) * 100 if pmask.sum() > 0 else 0
        avg_odds = float(odds_arr[pmask].mean()) if pmask.sum() > 0 else 0
        print(f"    {pat:>12}: {cnt}回  avg P-L: {avg_pl:.3f}%  avg オッズ: {avg_odds:.1f}倍")

    print(f"\n  【外れ {int(miss_mask.sum())}点 の特性】")
    print(f"    P-L確率平均: {miss_pls.mean()*100:.3f}%  中央値: {np.median(miss_pls)*100:.3f}%")
    miss_upats, miss_ucounts = np.unique(miss_patterns, return_counts=True)
    miss_order = np.argsort(-miss_ucounts)
    print(f"  【外れパターン（上位5）】")
    for i in miss_order[:5]:
        pat = miss_upats[i]
        cnt = miss_ucounts[i]
        print(f"    {pat:>12}: {cnt}点")

    # --- 分析3: 現行1点買い（P1-P2-P3）との比較 ---
    print("\n=== 分析3: 現行1点買い（P1-P2-P3）との比較 ===")
    p123_mask = patterns == 'P1-P2-P3'
    n_p123 = int(p123_mask.sum())
    if n_p123 > 0:
        roi_p123 = (hits[p123_mask] * odds_arr[p123_mask] * 100).sum() / (n_p123 * 100) * 100
        hit_rate_p123 = float(hits[p123_mask].mean()) * 100
        avg_odds_p123 = float(odds_arr[p123_mask].mean())
        print(f"  P1-P2-P3（現行1点買い相当）: {n_p123:,}点  "
              f"的中率: {hit_rate_p123:.3f}%  avg オッズ: {avg_odds_p123:.1f}倍  ROI: {roi_p123:.1f}%")

    # EV>=3.0+50倍フィルターの中のP1-P2-P3
    p123_best_mask = best_mask & p123_mask
    n_p123_best = int(p123_best_mask.sum())
    if n_p123_best > 0:
        roi_p123_best = (hits[p123_best_mask] * odds_arr[p123_best_mask] * 100).sum() / (n_p123_best * 100) * 100
        print(f"  P1-P2-P3 かつ EV>=3.0/50倍: {n_p123_best:,}点  ROI: {roi_p123_best:.1f}%")

    # --- 分析4: 「P1以外が1着」の組み合わせのEV方式での貢献 ---
    print("\n=== 分析4: 1着予測別の EV>=3.0/50倍 内訳 ===")
    for label, mask_fn in [
        ("P1が1着", lambda: np.array([p.startswith('P1-') for p in patterns])),
        ("P2が1着", lambda: np.array([p.startswith('P2-') for p in patterns])),
        ("P3が1着", lambda: np.array([p.startswith('P3-') for p in patterns])),
        ("P4以下が1着", lambda: np.array([not (p.startswith('P1-') or p.startswith('P2-') or p.startswith('P3-')) for p in patterns])),
    ]:
        pat_mask = mask_fn() & best_mask
        n = int(pat_mask.sum())
        if n < 5:
            print(f"  {label:>15}: {n}点（少なすぎてスキップ）")
            continue
        invest = n * 100
        payout = float((hits[pat_mask] * odds_arr[pat_mask] * 100).sum())
        roi = payout / invest * 100
        hit_rate = float(hits[pat_mask].mean()) * 100
        print(f"  {label:>15}: {n:>6,}点  的中率: {hit_rate:.3f}%  ROI: {roi:.1f}%")

    # --- 分析5: 年別の的中傾向（異常値確認） ---
    print("\n=== 分析5: 年別の EV>=3.0/50倍 成績 ===")
    years_arr = np.array([r['year'] for r in records])
    print(f"  {'年':>6} {'点数':>7} {'的中':>6} {'的中率':>8} {'投資':>9} {'払戻':>9} {'ROI':>8}")
    print("-" * 65)
    for year in sorted(set([r['year'] for r in records])):
        ymask = (years_arr == year) & best_mask
        n = int(ymask.sum())
        if n == 0:
            continue
        invest = n * 100
        payout = float((hits[ymask] * odds_arr[ymask] * 100).sum())
        roi = payout / invest * 100
        nhits = int(hits[ymask].sum())
        hit_rate = nhits / n * 100
        print(f"  {year}:  {n:>7,}  {nhits:>6}  {hit_rate:>7.3f}%  {invest:>8,}  {payout:>8,.0f}  {roi:>7.1f}%")

    # --- 総合判定 ---
    print("\n=== 総合判定 ===")
    # EV値とROIの相関（EVが高いほどROIが高いか）
    ev_bins_check = [1.0, 2.0, 3.0, 5.0]
    roi_by_ev = []
    for lo, hi in zip(ev_bins_check[:-1], ev_bins_check[1:]):
        mask = (evs >= lo) & (evs < hi) & (odds_arr <= 50)
        n = int(mask.sum())
        if n < 20:
            continue
        payout = float((hits[mask] * odds_arr[mask] * 100).sum())
        roi = payout / (n * 100) * 100
        roi_by_ev.append((lo, hi, roi, n))

    if len(roi_by_ev) >= 2:
        rois = [x[2] for x in roi_by_ev]
        is_monotone = all(rois[i] <= rois[i+1] for i in range(len(rois)-1))
        print(f"  EV閾値とROIの単調増加: {'Yes（P-Lが機能している）' if is_monotone else 'No（ランダム性が支配）'}")

    # 的中パターンの集中度確認
    hit_in_best = records[0:0]  # empty placeholder
    hit_recs = [r for r in records if r['ev'] >= 3.0 and r['odds'] <= 50 and r['hit'] == 1]
    if hit_recs:
        p1_hits = sum(1 for r in hit_recs if r['pattern'].startswith('P1-'))
        non_p1_hits = len(hit_recs) - p1_hits
        print(f"  的中内訳: P1が1着 {p1_hits}回 / P2以下が1着 {non_p1_hits}回")
        if non_p1_hits > 0:
            print(f"  → P2以下の1着にも的中あり（all120の拡張が機能している）")
        else:
            print(f"  → 全的中がP1-XX-XX（1着固定と変わらない）")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--years', type=int, nargs='+', default=list(range(2020, 2026)))
    args = parser.parse_args()
    analyze_ev_mechanism(args.years)


if __name__ == '__main__':
    main()
