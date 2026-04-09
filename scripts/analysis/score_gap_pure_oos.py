#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
純粋OOS検証: ISのみで閾値決定 → OOSに適用

【問題点（Opusの指摘）】
  前回の score_gap_bet_analysis.py は全6年データで閾値を最適化してから
  IS/OOS分割で確認していた。これはルックアヘッドバイアスを含む。

【正しい手順】
  Step 1: IS(2020-2023)のみで スコア差閾値を探索・決定
  Step 2: OOS(2024-2025)に、そのまま適用して効果を確認
  Step 3: 年度別安定性（上位>下位が6年中何年？）
  Step 4: 的中件数ベースの信頼区間（Opusの指摘：件数明示）
"""

import sqlite3
import math
import sys
import os
import numpy as np
from scipy import stats as scipy_stats

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.standard_backtest_unique import assign_races_to_conditions


def get_all_records():
    """全期間のレースデータを取得"""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        assigned = assign_races_to_conditions(
            cursor, STANDARD_BET_CONDITIONS, '2020-01-01', '2026-01-01'
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
        score_gap = s1 - s2

        records.append({
            'race_id': rid,
            'race_date': race_date,
            'year': int(race_date[:4]) if race_date else 0,
            'odds': odds_main,
            'hit': hit,
            'score_gap': score_gap,
        })

    return records


def calc_stats(recs):
    """基本統計計算"""
    if not recs:
        return None
    n = len(recs)
    hits = sum(r['hit'] for r in recs)
    invest = n * 100
    payout = sum(r['odds'] * 100 for r in recs if r['hit'])
    roi = payout / invest * 100 if invest > 0 else 0
    profit = payout - invest
    hit_rate = hits / n * 100 if n > 0 else 0
    return {'n': n, 'hits': hits, 'invest': invest, 'payout': payout,
            'roi': roi, 'profit': profit, 'hit_rate': hit_rate}


def bootstrap_roi_diff(hi_recs, lo_recs, n_boot=2000, seed=42):
    """上位/下位のROI差のブートストラップ信頼区間"""
    rng = np.random.default_rng(seed)
    hi_hits = np.array([r['hit'] for r in hi_recs])
    hi_odds = np.array([r['odds'] for r in hi_recs])
    lo_hits = np.array([r['hit'] for r in lo_recs])
    lo_odds = np.array([r['odds'] for r in lo_recs])

    diffs = []
    for _ in range(n_boot):
        idx_hi = rng.integers(0, len(hi_recs), len(hi_recs))
        idx_lo = rng.integers(0, len(lo_recs), len(lo_recs))
        roi_hi = hi_hits[idx_hi].dot(hi_odds[idx_hi]) * 100 / (len(hi_recs) * 100) * 100
        roi_lo = lo_hits[idx_lo].dot(lo_odds[idx_lo]) * 100 / (len(lo_recs) * 100) * 100
        diffs.append(roi_hi - roi_lo)

    diffs = np.array(diffs)
    ci_lo = np.percentile(diffs, 2.5)
    ci_hi = np.percentile(diffs, 97.5)
    p_positive = (diffs > 0).mean()
    return float(diffs.mean()), float(ci_lo), float(ci_hi), float(p_positive)


def find_best_threshold_is_only(is_records):
    """ISデータのみで最適閾値を探索"""
    print("=== Step 1: IS(2020-2023)のみで閾値探索 ===")
    print(f"  ISデータ: {len(is_records)}件")
    print()

    gaps = np.array([r['score_gap'] for r in is_records])

    # 探索する閾値候補（IS分位点 + 整数値）
    candidates = sorted(set(
        list(range(5, 50, 5)) +
        [float(np.percentile(gaps, p)) for p in range(20, 81, 5)]
    ))

    print(f"  {'閾値':>7} {'上位件数':>7} {'上位的中':>7} {'上位ROI':>8} {'下位件数':>7} {'下位的中':>7} {'下位ROI':>8} {'ROI差':>8}")
    print("-" * 78)

    results = []
    for t in candidates:
        hi = [r for r in is_records if r['score_gap'] >= t]
        lo = [r for r in is_records if r['score_gap'] < t]
        if len(hi) < 30 or len(lo) < 30:
            continue
        s_hi = calc_stats(hi)
        s_lo = calc_stats(lo)
        diff = s_hi['roi'] - s_lo['roi']
        results.append((diff, t, s_hi, s_lo))
        marker = ''
        print(f"  {t:>7.1f}  {s_hi['n']:>6}  {s_hi['hits']:>6}的中  {s_hi['roi']:>7.1f}%  "
              f"{s_lo['n']:>6}  {s_lo['hits']:>6}的中  {s_lo['roi']:>7.1f}%  {diff:>+7.1f}%{marker}")

    results.sort(reverse=True)
    best_diff, best_thresh, best_hi, best_lo = results[0]
    print(f"\n  → IS最適閾値: {best_thresh:.1f}  (ROI差 {best_diff:+.1f}%,  "
          f"上位{best_hi['n']}件/{best_hi['hits']}的中,  下位{best_lo['n']}件/{best_lo['hits']}的中)")

    # ブートストラップ
    hi_recs = [r for r in is_records if r['score_gap'] >= best_thresh]
    lo_recs = [r for r in is_records if r['score_gap'] < best_thresh]
    mean_diff, ci_lo, ci_hi, p_pos = bootstrap_roi_diff(hi_recs, lo_recs)
    print(f"  ブートストラップ(2000回): 差の平均{mean_diff:+.1f}%  95%CI [{ci_lo:+.1f}%, {ci_hi:+.1f}%]  "
          f"P(差>0) = {p_pos:.3f}")
    if ci_lo > 0:
        print("  → 95%CIが0以上 = 統計的に有意なシグナルあり")
    else:
        print("  → 95%CIが0を含む = IS内でも統計的有意差なし（ノイズ）")

    return best_thresh


def apply_threshold_oos(oos_records, threshold):
    """OOSデータにISで決定した閾値を適用（純粋OOS）"""
    print(f"\n=== Step 2: OOS(2024-2025)に閾値{threshold:.1f}を適用（純粋OOS） ===")
    print(f"  OOSデータ: {len(oos_records)}件")
    print()

    hi = [r for r in oos_records if r['score_gap'] >= threshold]
    lo = [r for r in oos_records if r['score_gap'] < threshold]
    s_all = calc_stats(oos_records)
    s_hi = calc_stats(hi)
    s_lo = calc_stats(lo)

    print(f"  全体:              {s_all['n']:>4}件  {s_all['hits']:>3}的中({s_all['hit_rate']:.2f}%)  "
          f"ROI {s_all['roi']:>6.1f}%  収支 {s_all['profit']:>+8,.0f}円")
    print(f"  上位(gap>={threshold:.0f}): {s_hi['n']:>4}件  {s_hi['hits']:>3}的中({s_hi['hit_rate']:.2f}%)  "
          f"ROI {s_hi['roi']:>6.1f}%  収支 {s_hi['profit']:>+8,.0f}円")
    print(f"  下位(gap< {threshold:.0f}):  {s_lo['n']:>4}件  {s_lo['hits']:>3}的中({s_lo['hit_rate']:.2f}%)  "
          f"ROI {s_lo['roi']:>6.1f}%  収支 {s_lo['profit']:>+8,.0f}円")
    print(f"  上下ROI差: {s_hi['roi'] - s_lo['roi']:+.1f}%")

    if len(hi) >= 10 and len(lo) >= 10:
        mean_diff, ci_lo, ci_hi, p_pos = bootstrap_roi_diff(hi, lo)
        print(f"\n  ブートストラップ(2000回): 差の平均{mean_diff:+.1f}%  95%CI [{ci_lo:+.1f}%, {ci_hi:+.1f}%]  "
              f"P(差>0) = {p_pos:.3f}")
        if ci_lo > 0:
            print("  → OOSでも95%CIが0以上 = 有効なシグナル ✓")
        elif p_pos > 0.7:
            print(f"  → OOSで70%+の確率で上位>下位だが、統計的有意差なし（参考程度）")
        else:
            print("  → OOSでは有意差なし = ISの閾値はOOSに汎化しない")

    # 2段階ベット OOS
    print(f"\n  --- 2段階ベット(200/100) OOS試算 ---")
    invest_flat = len(oos_records) * 100
    payout_flat = sum(r['odds'] * 100 for r in oos_records if r['hit'])
    invest_2tier = sum(200 if r['score_gap'] >= threshold else 100 for r in oos_records)
    payout_2tier = sum(
        (200 if r['score_gap'] >= threshold else 100) * r['odds']
        for r in oos_records if r['hit']
    )
    roi_flat = payout_flat / invest_flat * 100 if invest_flat > 0 else 0
    roi_2tier = payout_2tier / invest_2tier * 100 if invest_2tier > 0 else 0

    print(f"  現行(全100円):   投資{invest_flat:>7,}円  収支{payout_flat-invest_flat:>+8,.0f}円  ROI {roi_flat:>6.1f}%")
    print(f"  2段階(200/100): 投資{invest_2tier:>7,}円  収支{payout_2tier-invest_2tier:>+8,.0f}円  ROI {roi_2tier:>6.1f}%")
    print(f"  ROI改善: {roi_2tier - roi_flat:+.1f}%  収支改善: {(payout_2tier-invest_2tier)-(payout_flat-invest_flat):+,.0f}円")

    return s_hi, s_lo


def yearly_stability(all_records, threshold):
    """年度別安定性: 上位>下位が6年中何年？"""
    print(f"\n=== Step 3: 年度別安定性（閾値{threshold:.1f}） ===")
    print(f"  {'年度':>5} {'上位件数':>7} {'上位的中':>7} {'上位ROI':>8} {'下位件数':>7} {'下位的中':>7} {'下位ROI':>8} {'上位>下位':>8}")
    print("-" * 78)

    wins = 0
    total_years = 0
    for year in range(2020, 2026):
        yr_recs = [r for r in all_records if r['year'] == year]
        hi = [r for r in yr_recs if r['score_gap'] >= threshold]
        lo = [r for r in yr_recs if r['score_gap'] < threshold]
        if len(yr_recs) < 10 or len(hi) < 5 or len(lo) < 5:
            continue
        s_hi = calc_stats(hi)
        s_lo = calc_stats(lo)
        won = s_hi['roi'] > s_lo['roi']
        wins += int(won)
        total_years += 1
        marker = '○' if won else '×'
        print(f"  {year}年  {s_hi['n']:>6}  {s_hi['hits']:>6}的中  {s_hi['roi']:>7.1f}%  "
              f"{s_lo['n']:>6}  {s_lo['hits']:>6}的中  {s_lo['roi']:>7.1f}%  {marker}")

    print(f"\n  上位>下位: {wins}/{total_years}年  "
          f"{'安定（4/6以上）' if wins >= 4 else '不安定（3/6以下）'}")


def hit_count_sensitivity(oos_records, threshold):
    """的中件数感度分析: あと1件の的中/不的中でROIがどれだけ変わるか"""
    print(f"\n=== Step 4: 的中件数の感度分析（OOS下位群） ===")
    lo = [r for r in oos_records if r['score_gap'] < threshold]
    if not lo:
        return
    s_lo = calc_stats(lo)
    avg_odds = sum(r['odds'] for r in lo) / len(lo)

    print(f"  下位群: {s_lo['n']}件  {s_lo['hits']}的中  ROI {s_lo['roi']:.1f}%")
    print(f"  平均オッズ: {avg_odds:.1f}倍")
    print()
    for delta in [-2, -1, 0, +1, +2]:
        fake_hits = s_lo['hits'] + delta
        if fake_hits < 0:
            continue
        fake_payout = fake_hits * avg_odds * 100
        fake_roi = fake_payout / s_lo['invest'] * 100 if s_lo['invest'] > 0 else 0
        print(f"  的中 {s_lo['hits']}{'+' if delta >= 0 else ''}{delta}={fake_hits}件 → ROI {fake_roi:.1f}%")

    print(f"\n  → 1件の違いでROIが約{avg_odds*100/s_lo['invest']*100:.0f}%変動する。"
          f"現在{s_lo['hits']}件的中のROI {s_lo['roi']:.1f}%は信頼性{"低い（件数不足）" if s_lo['hits'] < 10 else "ある程度ある"}。")


def main():
    print("純粋OOS検証: ISのみで閾値決定 → OOS適用")
    print("データ取得中...", flush=True)

    all_records = get_all_records()
    print(f"有効レース合計: {len(all_records):,}件\n")

    is_records = [r for r in all_records if r['year'] <= 2023]
    oos_records = [r for r in all_records if r['year'] >= 2024]
    print(f"IS (2020-2023): {len(is_records)}件  OOS (2024-2025): {len(oos_records)}件\n")

    # Step 1: ISのみで閾値決定
    best_thresh = find_best_threshold_is_only(is_records)

    # Step 2: OOSに適用（純粋OOS）
    s_hi_oos, s_lo_oos = apply_threshold_oos(oos_records, best_thresh)

    # Step 3: 年度別安定性
    yearly_stability(all_records, best_thresh)

    # Step 4: 感度分析
    hit_count_sensitivity(oos_records, best_thresh)

    # 総合判定
    print(f"\n{'='*60}")
    print("=== 総合判定 ===")
    oos_diff = s_hi_oos['roi'] - s_lo_oos['roi'] if s_hi_oos and s_lo_oos else 0
    if s_hi_oos and s_lo_oos:
        print(f"  IS最適閾値 {best_thresh:.1f} をOOSに適用した結果:")
        print(f"  OOS上位ROI: {s_hi_oos['roi']:.1f}%  OOS下位ROI: {s_lo_oos['roi']:.1f}%  差: {oos_diff:+.1f}%")
        if oos_diff > 20:
            print("  → OOSでも有意な差あり。スコア差は汎化するシグナルの可能性あり")
        elif oos_diff > 0:
            print("  → OOSで正の差はあるが小さい。実装コスト対比で検討が必要")
        else:
            print("  → OOSで差がなし/逆転。ISの閾値はOOSに汎化しない → 採用非推奨")


if __name__ == '__main__':
    main()
