#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ベット額最適化分析: スコア差 vs 的中率・ROI の相関確認

【目的】
  現行1,610件レースに対して:
  - P1スコア - P2スコア の差（スコア差）と的中率の相関を確認
  - スコア差が大きい = P1の優位性が明確 → 的中率高い？
  - 2段階ベット（スコア差大: 200円, 小: 100円）でROI改善を試算

【設計】
  STEP 1: スコア差の分布確認 + 各バンドでの的中率/ROI
  STEP 2: 最適2分割閾値の探索（分位点別）
  STEP 3: IS(2020-2023) / OOS(2024-2025) 安定性確認
  STEP 4: 2段階ベット（200/100）シミュレーション
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


def get_race_data(start_date: str, end_date: str):
    """現行7条件で選ばれたレースのスコア・オッズ・結果を取得"""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        assigned = assign_races_to_conditions(
            cursor, STANDARD_BET_CONDITIONS, start_date, end_date
        )
        cond_map = {}
        for cond in STANDARD_BET_CONDITIONS:
            cid = cond['id']
            for rid in assigned.get(cid, []):
                if rid not in cond_map:
                    cond_map[rid] = cond
        all_race_ids = list(cond_map.keys())

        if not all_race_ids:
            return []

        placeholders = ','.join(['?'] * len(all_race_ids))

        # スコア・予測順位
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

        # オッズ
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

        # 実際の結果
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

        # レース日付取得
        cursor.execute(f'''
            SELECT id, race_date FROM races WHERE id IN ({placeholders})
        ''', all_race_ids)
        date_map = {rid: d for rid, d in cursor.fetchall()}

    records = []
    for rid in all_race_ids:
        scores = score_map.get(rid)
        odds_data = odds_map.get(rid)
        res = result_map.get(rid)
        cond = cond_map[rid]
        race_date = date_map.get(rid, '')

        if not scores or not odds_data or not res:
            continue
        if '1' not in res or '2' not in res or '3' not in res:
            continue
        pits = list(scores.keys())
        if len(pits) < 4:
            continue

        rm = rank_map.get(rid, {})
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
        hit = 1 if combo_123 == actual else 0

        s1 = scores.get(p1, 0)
        s2 = scores.get(p2, 0)
        s3 = scores.get(p3, 0)
        score_gap_12 = s1 - s2  # P1 vs P2 差
        score_gap_23 = s2 - s3  # P2 vs P3 差
        score_gap_top2 = s1 - sorted(scores.values())[-2] if len(scores) > 1 else 0

        records.append({
            'race_id': rid,
            'race_date': race_date,
            'combo': combo_123,
            'odds': odds_main,
            'hit': hit,
            'score_gap_12': score_gap_12,
            'score_gap_23': score_gap_23,
            's1': s1,
            's2': s2,
            's3': s3,
        })

    return records


def analyze_score_gap_distribution(records):
    """STEP 1: スコア差の分布とバンド別的中率"""
    gaps = np.array([r['score_gap_12'] for r in records])
    hits = np.array([r['hit'] for r in records])
    odds_arr = np.array([r['odds'] for r in records])

    print("=== STEP 1: スコア差（P1-P2）の分布 ===")
    print(f"  件数: {len(gaps):,}")
    print(f"  平均: {gaps.mean():.1f}  中央値: {np.median(gaps):.1f}")
    print(f"  最小: {gaps.min():.1f}  最大: {gaps.max():.1f}")
    print(f"  標準偏差: {gaps.std():.1f}")
    print(f"  25%ile: {np.percentile(gaps, 25):.1f}  75%ile: {np.percentile(gaps, 75):.1f}")
    print()

    # バンド別分析
    bins = [
        (None, 0,   '負（P2>P1）'),
        (0,    5,   '0〜5'),
        (5,    10,  '5〜10'),
        (10,   15,  '10〜15'),
        (15,   20,  '15〜20'),
        (20,   30,  '20〜30'),
        (30,   50,  '30〜50'),
        (50,   None,'50以上'),
    ]

    print(f"  {'スコア差帯':>12} {'件数':>6} {'的中率':>8} {'avg Odds':>9} {'ROI':>8} {'収支':>10}")
    print("-" * 70)

    for lo, hi, label in bins:
        if lo is None:
            mask = gaps < hi
        elif hi is None:
            mask = gaps >= lo
        else:
            mask = (gaps >= lo) & (gaps < hi)
        n = int(mask.sum())
        if n < 5:
            continue
        hit_rate = float(hits[mask].mean()) * 100
        avg_odds = float(odds_arr[mask].mean())
        invest = n * 100
        payout = float((hits[mask] * odds_arr[mask] * 100).sum())
        roi = payout / invest * 100 if invest > 0 else 0
        profit = payout - invest
        print(f"  {label:>12}  {n:>5,}  {hit_rate:>7.2f}%  {avg_odds:>8.1f}倍  {roi:>7.1f}%  {profit:>+9,.0f}円")


def find_optimal_threshold(records):
    """STEP 2: 最適2分割閾値の探索"""
    print("\n=== STEP 2: 分位点別2分割 ROI比較 ===")
    print("（上位: 2倍ベット想定、下位: 1倍ベット想定でのROI差）")
    print()

    gaps = np.array([r['score_gap_12'] for r in records])
    hits = np.array([r['hit'] for r in records])
    odds_arr = np.array([r['odds'] for r in records])

    percentiles = [25, 30, 33, 40, 50, 60, 67, 70, 75]
    print(f"  {'閾値':>7} {'上位件数':>8} {'上位的中率':>10} {'上位ROI':>8} {'下位件数':>8} {'下位的中率':>10} {'下位ROI':>8} {'ROI差':>8}")
    print("-" * 80)

    best_diff = -999
    best_thresh = None
    for pct in percentiles:
        thresh = np.percentile(gaps, pct)
        hi_mask = gaps >= thresh
        lo_mask = gaps < thresh
        n_hi = int(hi_mask.sum())
        n_lo = int(lo_mask.sum())
        if n_hi < 10 or n_lo < 10:
            continue

        roi_hi = float((hits[hi_mask] * odds_arr[hi_mask] * 100).sum()) / (n_hi * 100) * 100
        roi_lo = float((hits[lo_mask] * odds_arr[lo_mask] * 100).sum()) / (n_lo * 100) * 100
        hr_hi = float(hits[hi_mask].mean()) * 100
        hr_lo = float(hits[lo_mask].mean()) * 100
        diff = roi_hi - roi_lo

        marker = ' ←最大差' if diff > best_diff else ''
        if diff > best_diff:
            best_diff = diff
            best_thresh = thresh

        print(f"  {pct:3d}%ile ({thresh:5.1f})  {n_hi:>6,}  {hr_hi:>9.2f}%  {roi_hi:>7.1f}%  {n_lo:>6,}  {hr_lo:>9.2f}%  {roi_lo:>7.1f}%  {diff:>+7.1f}%{marker}")

    print(f"\n  → 最大ROI差の閾値: {best_thresh:.1f}（{best_diff:+.1f}%差）")
    return best_thresh


def is_oos_validation(records, threshold):
    """STEP 3: IS/OOS分割 安定性確認"""
    print(f"\n=== STEP 3: IS/OOS分割 安定性確認（閾値: {threshold:.1f}） ===")

    is_records = [r for r in records if r['race_date'] < '2024-01-01']
    oos_records = [r for r in records if r['race_date'] >= '2024-01-01']

    for label, recs in [('IS (2020-2023)', is_records), ('OOS (2024-2025)', oos_records)]:
        if not recs:
            continue
        gaps = np.array([r['score_gap_12'] for r in recs])
        hits = np.array([r['hit'] for r in recs])
        odds_arr = np.array([r['odds'] for r in recs])

        hi_mask = gaps >= threshold
        lo_mask = gaps < threshold
        n_hi = int(hi_mask.sum())
        n_lo = int(lo_mask.sum())
        n_total = len(recs)

        roi_hi = float((hits[hi_mask] * odds_arr[hi_mask] * 100).sum()) / max(n_hi * 100, 1) * 100
        roi_lo = float((hits[lo_mask] * odds_arr[lo_mask] * 100).sum()) / max(n_lo * 100, 1) * 100
        roi_all = float((hits * odds_arr * 100).sum()) / (n_total * 100) * 100
        hr_hi = float(hits[hi_mask].mean()) * 100 if n_hi > 0 else 0
        hr_lo = float(hits[lo_mask].mean()) * 100 if n_lo > 0 else 0

        print(f"\n  {label} (計{n_total}件):")
        print(f"    全体ROI: {roi_all:.1f}%")
        print(f"    上位(gap>={threshold:.0f}): {n_hi}件  的中率{hr_hi:.2f}%  ROI {roi_hi:.1f}%")
        print(f"    下位(gap< {threshold:.0f}): {n_lo}件  的中率{hr_lo:.2f}%  ROI {roi_lo:.1f}%")
        print(f"    ROI差: {roi_hi - roi_lo:+.1f}%")


def simulate_two_tier_betting(records, threshold):
    """STEP 4: 2段階ベット（200円/100円）シミュレーション"""
    print(f"\n=== STEP 4: 2段階ベットシミュレーション（閾値: {threshold:.1f}） ===")
    print("  上位(gap>=閾値): 200円  下位: 100円")
    print()

    is_records = [r for r in records if r['race_date'] < '2024-01-01']
    oos_records = [r for r in records if r['race_date'] >= '2024-01-01']
    all_sets = [
        ('全期間 (2020-2025)', records),
        ('IS (2020-2023)', is_records),
        ('OOS (2024-2025)', oos_records),
    ]

    for label, recs in all_sets:
        if not recs:
            continue

        # 現行（全100円）
        invest_flat = len(recs) * 100
        payout_flat = sum(r['odds'] * 100 if r['hit'] else 0 for r in recs)
        roi_flat = payout_flat / invest_flat * 100 if invest_flat > 0 else 0
        profit_flat = payout_flat - invest_flat

        # 2段階ベット
        invest_2tier = 0
        payout_2tier = 0.0
        for r in recs:
            bet = 200 if r['score_gap_12'] >= threshold else 100
            invest_2tier += bet
            if r['hit']:
                payout_2tier += r['odds'] * bet

        roi_2tier = payout_2tier / invest_2tier * 100 if invest_2tier > 0 else 0
        profit_2tier = payout_2tier - invest_2tier

        # 上位2倍
        n_hi = sum(1 for r in recs if r['score_gap_12'] >= threshold)
        n_lo = len(recs) - n_hi
        ratio_hi = n_hi / len(recs) * 100

        print(f"  {label} ({len(recs)}件, 上位{n_hi}件={ratio_hi:.0f}%):")
        print(f"    現行(全100円):   投資{invest_flat:>7,}円  収支{profit_flat:>+8,.0f}円  ROI {roi_flat:>6.1f}%")
        print(f"    2段階(200/100):  投資{int(invest_2tier):>7,}円  収支{profit_2tier:>+8,.0f}円  ROI {roi_2tier:>6.1f}%")
        print(f"    収支差: {profit_2tier - profit_flat:+,.0f}円  ROI差: {roi_2tier - roi_flat:+.1f}%")
        print()

    # 複数閾値の比較
    print("  === 閾値別 2段階ベット比較（全期間） ===")
    thresholds_to_try = sorted(set(
        [int(np.percentile([r['score_gap_12'] for r in records], p)) for p in [25, 33, 40, 50, 60, 67, 75]]
        + [5, 10, 15, 20, 25, 30]
    ))

    gaps_all = np.array([r['score_gap_12'] for r in records])
    hits_all = np.array([r['hit'] for r in records])
    odds_all = np.array([r['odds'] for r in records])

    invest_base = len(records) * 100
    payout_base = float((hits_all * odds_all * 100).sum())
    profit_base = payout_base - invest_base
    roi_base = payout_base / invest_base * 100

    print(f"  {'閾値':>6} {'上位%':>6} {'投資':>9} {'収支':>10} {'ROI':>8} {'収支改善':>10}")
    print("-" * 60)

    for t in thresholds_to_try:
        hi_mask = gaps_all >= t
        lo_mask = gaps_all < t
        n_hi = int(hi_mask.sum())
        n_lo = int(lo_mask.sum())
        if n_hi < 20 or n_lo < 20:
            continue

        invest = n_hi * 200 + n_lo * 100
        payout = float((hits_all[hi_mask] * odds_all[hi_mask] * 200).sum() +
                        (hits_all[lo_mask] * odds_all[lo_mask] * 100).sum())
        profit = payout - invest
        roi = payout / invest * 100 if invest > 0 else 0
        improvement = profit - profit_base

        print(f"  {t:>6.0f}  {n_hi/len(records)*100:>5.0f}%  {invest:>8,}  {profit:>+9,.0f}  {roi:>7.1f}%  {improvement:>+9,.0f}円")

    print(f"\n  基準(全100円): 投資{invest_base:,}円  収支{profit_base:+,.0f}円  ROI {roi_base:.1f}%")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2020-01-01')
    parser.add_argument('--end', default='2026-01-01')
    parser.add_argument('--threshold', type=float, default=None,
                        help='手動で閾値を指定（省略時は自動探索）')
    args = parser.parse_args()

    print(f"スコア差ベット最適化分析 ({args.start} 〜 {args.end})")
    print("データ取得中...", flush=True)

    records = get_race_data(args.start, args.end)
    print(f"有効レース: {len(records):,}件\n")

    if not records:
        print("データなし")
        return

    # STEP 1
    analyze_score_gap_distribution(records)

    # STEP 2
    best_thresh = find_optimal_threshold(records)
    threshold = args.threshold if args.threshold is not None else best_thresh

    # STEP 3
    is_oos_validation(records, threshold)

    # STEP 4
    simulate_two_tier_betting(records, threshold)


if __name__ == '__main__':
    main()
