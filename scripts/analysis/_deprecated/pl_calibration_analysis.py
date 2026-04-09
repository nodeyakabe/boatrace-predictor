#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
検証D: P-L確率の精度分析（全120通り）

【目的】
  P-Lモデルが全120通りの組み合わせに対して
  実際の的中率とどれだけ一致しているかを検証する。
  特にEV方式で重要な低確率帯（0.1-2%）の精度を確認する。

【判断基準】
  低確率帯の推定/実際比率 <= 2.0x -> EV方式の検証続行
  低確率帯の推定/実際比率 >= 3.0x -> EV方式は機能しない可能性が高い

使い方:
  python scripts/analysis/pl_calibration_analysis.py
  python scripts/analysis/pl_calibration_analysis.py --years 2020 2021 2022 2023 2024
  python scripts/analysis/pl_calibration_analysis.py --use-conditions
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


def analyze_pl_accuracy(years: list, use_conditions: bool = False):
    print(f"分析: {years}年 | フィルター: {'7条件通過レースのみ' if use_conditions else '全レース'}")

    all_probs = []
    all_hits = []
    all_patterns = []  # P1-P2-P3 形式の予測順位パターン

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        condition_race_ids_all = set()
        if use_conditions:
            from config.bet_conditions import STANDARD_BET_CONDITIONS
            from scripts.backtest.standard_backtest_unique import assign_races_to_conditions
            for year in years:
                assigned = assign_races_to_conditions(
                    cursor, STANDARD_BET_CONDITIONS,
                    f'{year}-01-01', f'{year+1}-01-01'
                )
                for ids in assigned.values():
                    condition_race_ids_all.update(ids)
            print(f"  条件通過レース合計: {len(condition_race_ids_all):,}件")

        for year in years:
            start = f'{year}-01-01'
            end = f'{year+1}-01-01'
            print(f"  {year}年 処理中...", end='', flush=True)

            # スコア・予測順位取得
            cursor.execute('''
                SELECT rp.race_id, rp.pit_number, rp.total_score, rp.rank_prediction
                FROM race_predictions rp
                JOIN races r ON rp.race_id = r.id
                WHERE r.race_date >= ? AND r.race_date < ?
                AND rp.prediction_type = 'before'
                AND rp.total_score IS NOT NULL
            ''', (start, end))

            score_map = {}
            rank_map = {}
            for rid, pit, sc, rp in cursor.fetchall():
                if use_conditions and rid not in condition_race_ids_all:
                    continue
                if rid not in score_map:
                    score_map[rid] = {}
                    rank_map[rid] = {}
                score_map[rid][pit] = sc
                rank_map[rid][pit] = rp

            race_ids = list(score_map.keys())
            if not race_ids:
                print(" 0件")
                continue

            # 実際の結果取得
            result_map = {}
            for i in range(0, len(race_ids), 5000):
                batch = race_ids[i:i+5000]
                placeholders = ','.join(['?'] * len(batch))
                cursor.execute(f'''
                    SELECT race_id, pit_number, rank
                    FROM results
                    WHERE race_id IN ({placeholders})
                    AND is_invalid=0 AND rank IN ('1','2','3')
                ''', batch)
                for rid, pit, rank in cursor.fetchall():
                    if rid not in result_map:
                        result_map[rid] = {}
                    result_map[rid][rank] = pit

            # 全120通り計算
            count = 0
            for rid, scores in score_map.items():
                if rid not in result_map:
                    continue
                pits = list(scores.keys())
                if len(pits) < 4:
                    continue
                res = result_map[rid]
                if '1' not in res or '2' not in res or '3' not in res:
                    continue
                actual = (res['1'], res['2'], res['3'])
                rm = rank_map.get(rid, {})

                for a in pits:
                    for b in pits:
                        if b == a:
                            continue
                        for c in pits:
                            if c == a or c == b:
                                continue
                            pl = compute_pl_prob(scores, (a, b, c))
                            if pl <= 0:
                                continue
                            hit = 1 if (a == actual[0] and b == actual[1] and c == actual[2]) else 0
                            rank_a = rm.get(a, 9)
                            rank_b = rm.get(b, 9)
                            rank_c = rm.get(c, 9)
                            pattern = f"P{rank_a}-P{rank_b}-P{rank_c}"

                            all_probs.append(pl)
                            all_hits.append(hit)
                            all_patterns.append(pattern)
                            count += 1

            print(f" {count:,}点（レース{len(score_map):,}件）")

    probs = np.array(all_probs)
    hits = np.array(all_hits)
    patterns = np.array(all_patterns)

    total_hit_rate = hits.mean() * 100
    total_pl_mean = probs.mean() * 100
    print(f"\n合計: {len(probs):,}点  実際の的中率: {total_hit_rate:.4f}%  P-L平均: {total_pl_mean:.4f}%")
    print(f"全120通りの均等的中率: {100/120:.4f}%（参考）\n")

    # --- バケット別分析 ---
    print("=== バケット別 P-L推定 vs 実際的中率 ===")
    print(f"  {'確率帯':>15} {'件数':>9} {'P-L推定':>9} {'実際':>9} {'比率':>7} {'判定'}")
    print("-" * 70)

    bins = [0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.20, 1.0]
    worst_ratio = 0.0
    low_prob_ratio = None

    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi)
        n = int(mask.sum())
        if n < 20:
            continue
        avg_pl = float(probs[mask].mean())
        actual_rate = float(hits[mask].mean())
        ratio = avg_pl / actual_rate if actual_rate > 0 else float('inf')

        if lo < 0.02:
            low_prob_ratio = ratio if low_prob_ratio is None else max(low_prob_ratio, ratio)
        worst_ratio = max(worst_ratio, ratio) if ratio != float('inf') else worst_ratio

        if ratio <= 1.5:
            verdict = "妥当"
        elif ratio <= 2.0:
            verdict = "やや過大"
        elif ratio <= 3.0:
            verdict = "過大評価"
        else:
            verdict = "壊滅的"

        print(f"  {lo*100:5.2f}%-{hi*100:6.2f}%  {n:>9,}  {avg_pl*100:>8.4f}%  {actual_rate*100:>8.4f}%  {ratio:>6.2f}x  {verdict}")

    # --- 予測順位パターン別分析 ---
    print("\n=== 予測順位パターン別（全件数上位10パターン） ===")
    print(f"  {'パターン':>12} {'件数':>9} {'P-L推定':>9} {'実際':>9} {'比率':>7}")
    print("-" * 60)

    # パターンをカウントして上位を表示
    unique_patterns, counts = np.unique(patterns, return_counts=True)
    order = np.argsort(-counts)
    shown = 0
    for idx in order:
        pat = unique_patterns[idx]
        mask = patterns == pat
        n = int(mask.sum())
        if n < 100:
            break
        avg_pl = float(probs[mask].mean())
        actual_rate = float(hits[mask].mean())
        ratio = avg_pl / actual_rate if actual_rate > 0 else float('inf')
        print(f"  {pat:>12}  {n:>9,}  {avg_pl*100:>8.4f}%  {actual_rate*100:>8.4f}%  {ratio:>6.2f}x")
        shown += 1
        if shown >= 10:
            break

    # --- P1が1着 vs 非P1が1着 ---
    print("\n=== 1着予測別の精度 ===")
    print(f"  {'カテゴリ':>18} {'件数':>9} {'P-L推定':>9} {'実際':>9} {'比率':>7}")
    print("-" * 60)

    for label, pat_prefix in [
        ("P1が1着", "P1-"),
        ("P2が1着", "P2-"),
        ("P3が1着", "P3-"),
        ("P4以下が1着", None),
    ]:
        if pat_prefix:
            mask = np.array([p.startswith(pat_prefix) for p in patterns])
        else:
            mask = np.array([not (p.startswith("P1-") or p.startswith("P2-") or p.startswith("P3-")) for p in patterns])
        n = int(mask.sum())
        if n < 10:
            continue
        avg_pl = float(probs[mask].mean())
        actual_rate = float(hits[mask].mean())
        ratio = avg_pl / actual_rate if actual_rate > 0 else float('inf')
        print(f"  {label:>18}  {n:>9,}  {avg_pl*100:>8.4f}%  {actual_rate*100:>8.4f}%  {ratio:>6.2f}x")

    # --- EV>=3.0・オッズ上限50倍帯域の精度シミュレート ---
    print("\n=== EV>=3.0 + オッズ上限50倍帯域の精度シミュレート ===")
    print("（P-L >= 6% の組み合わせ = EV>=3.0/オッズ50倍に相当）")
    ev_min_probs = [0.04, 0.06, 0.08, 0.10]  # 対応オッズ: 3.0/prob
    for threshold in ev_min_probs:
        mask = probs >= threshold
        n = int(mask.sum())
        if n < 10:
            continue
        avg_pl = float(probs[mask].mean())
        actual_rate = float(hits[mask].mean())
        ratio = avg_pl / actual_rate if actual_rate > 0 else float('inf')
        implied_odds = 3.0 / threshold
        print(f"  P-L >= {threshold*100:.0f}%（≒EV>=3.0/オッズ{implied_odds:.0f}倍相当）: "
              f"{n:,}点  P-L: {avg_pl*100:.4f}%  実際: {actual_rate*100:.4f}%  比率: {ratio:.2f}x")

    # --- 総合判定 ---
    print("\n" + "=" * 70)
    print("=== 総合判定 ===")
    low_mask = probs < 0.02
    mid_mask = (probs >= 0.02) & (probs < 0.06)
    high_mask = probs >= 0.06

    final_verdict = "OK"
    for label, mask in [("低確率帯 (<2%)", low_mask), ("中確率帯 (2-6%)", mid_mask), ("高確率帯 (>=6%)", high_mask)]:
        n = int(mask.sum())
        if n < 10:
            continue
        avg_pl = float(probs[mask].mean())
        actual = float(hits[mask].mean())
        ratio = avg_pl / actual if actual > 0 else float('inf')
        if ratio <= 1.5:
            judge = "OK（妥当）"
        elif ratio <= 2.0:
            judge = "要注意（やや過大）"
        elif ratio <= 3.0:
            judge = "警告（過大評価）"
            if label == "低確率帯 (<2%)":
                final_verdict = "WARNING"
        else:
            judge = "NG（壊滅的）"
            if label == "低確率帯 (<2%)":
                final_verdict = "NG"
        print(f"  {label}: {n:,}点  P-L: {avg_pl*100:.4f}%  実際: {actual*100:.4f}%  比率: {ratio:.2f}x  -> {judge}")

    print()
    if final_verdict == "OK":
        print("  【結論】P-L低確率帯の精度は妥当 -> EV方式の検証続行 (Step2/3/4へ)")
    elif final_verdict == "WARNING":
        print("  【結論】P-L低確率帯に過大評価あり -> EV方式の信頼性に注意が必要")
    else:
        print("  【結論】P-L低確率帯の精度が壊滅的 -> EV方式の前提が崩壊している可能性")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--years', type=int, nargs='+', default=list(range(2020, 2026)))
    parser.add_argument('--use-conditions', action='store_true',
                        help='現行7条件を通過したレースのみ対象')
    args = parser.parse_args()
    analyze_pl_accuracy(args.years, args.use_conditions)


if __name__ == '__main__':
    main()
