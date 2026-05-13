#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
advance/before 一致度フィルタ テスト

【仮説】
  advance予測(前日夜)とbefore予測(展示後)の1-2-3位が完全一致したレース
  = 展示情報で順位が変わらなかった = 実力差が明確なレース
  → 市場が取りこぼしている高確度レース

【テスト内容】
  現行7条件の購入対象レースに advance/before 完全一致フィルタを追加
  - 一致グループ vs 不一致グループ vs 全体のROI比較（年度別）
  - IS(2020-2023) / OOS(2024-2025) 分割での安定性確認
  - ジャックナイフ推定（1年除外×6パターン）
"""

import sqlite3
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.standard_backtest_unique import assign_races_to_conditions

YEARS = list(range(2020, 2026))


def load_data(cursor, all_cand_ids):
    ph = ','.join(['?'] * len(all_cand_ids))

    cursor.execute(f'''
        SELECT race_id, pit_number, total_score, rank_prediction
        FROM race_predictions
        WHERE race_id IN ({ph}) AND prediction_type='before' AND total_score IS NOT NULL
    ''', all_cand_ids)
    bef_score, bef_rank = {}, {}
    for rid, pit, sc, rp in cursor.fetchall():
        if rid not in bef_score: bef_score[rid] = {}; bef_rank[rid] = {}
        bef_score[rid][pit] = sc; bef_rank[rid][pit] = rp

    cursor.execute(f'''
        SELECT race_id, pit_number, rank_prediction
        FROM race_predictions
        WHERE race_id IN ({ph}) AND prediction_type='advance' AND rank_prediction IN (1,2,3)
    ''', all_cand_ids)
    adv_rank = {}
    for rid, pit, rp in cursor.fetchall():
        if rid not in adv_rank: adv_rank[rid] = {}
        adv_rank[rid][rp] = pit

    cursor.execute(f'SELECT race_id, combination, odds FROM trifecta_odds WHERE race_id IN ({ph})', all_cand_ids)
    odds_map = {}
    for rid, combo, odds in cursor.fetchall():
        if rid not in odds_map: odds_map[rid] = {}
        odds_map[rid][combo] = odds

    cursor.execute(f'''
        SELECT race_id, pit_number, rank FROM results
        WHERE race_id IN ({ph}) AND is_invalid=0 AND rank IN ('1','2','3')
    ''', all_cand_ids)
    result_map = {}
    for rid, pit, rank in cursor.fetchall():
        if rid not in result_map: result_map[rid] = {}
        result_map[rid][rank] = pit

    cursor.execute(f'SELECT id, race_date FROM races WHERE id IN ({ph})', all_cand_ids)
    date_map = {rid: d for rid, d in cursor.fetchall()}

    return bef_score, bef_rank, adv_rank, odds_map, result_map, date_map


def build_purchase_records(all_cand_ids, cond_map, bef_score, bef_rank, adv_rank, odds_map, result_map, date_map):
    records = []
    for rid in all_cand_ids:
        scores = bef_score.get(rid)
        odds_data = odds_map.get(rid)
        res = result_map.get(rid)
        cond = cond_map[rid]
        if not scores or not odds_data or not res: continue
        if '1' not in res or '2' not in res or '3' not in res: continue
        pits = list(scores.keys())
        if len(pits) < 4: continue
        rm = bef_rank.get(rid, {})
        pred_sorted = sorted([(rm.get(p, 9), p) for p in pits])
        p1, p2, p3 = [p for _, p in pred_sorted[:3]]
        bef_combo = f'{p1}-{p2}-{p3}'
        odds = odds_data.get(bef_combo)
        if odds is None: continue
        if not (cond.get('odds_min', 0) <= odds < cond.get('odds_max', 9999)): continue

        actual = f"{res['1']}-{res['2']}-{res['3']}"
        hit = 1 if bef_combo == actual else 0
        pay = odds * 100 if hit else 0
        year = int(date_map.get(rid, '2000')[:4])

        adv = adv_rank.get(rid)
        if adv and 1 in adv and 2 in adv and 3 in adv:
            adv_combo = f"{adv[1]}-{adv[2]}-{adv[3]}"
            match = (adv_combo == bef_combo)
        else:
            match = None  # advance予測なし

        records.append({
            'rid': rid,
            'hit': hit,
            'pay': pay,
            'year': year,
            'match': match,
            'odds': odds,
            'cond_id': cond['id'],
        })
    return records


def roi_stats(recs):
    if not recs:
        return 0, 0, 0, 0
    n = len(recs)
    hits = sum(r['hit'] for r in recs)
    invest = n * 100
    payout = sum(r['pay'] for r in recs)
    roi = payout / invest * 100
    return n, hits, roi, payout - invest


def print_section(title, recs, label=''):
    n, hits, roi, profit = roi_stats(recs)
    black = sum(1 for yr in YEARS if sum(r['pay'] for r in recs if r['year'] == yr) - sum(100 for r in recs if r['year'] == yr) > 0)
    print(f'\n{title}  ({label})')
    print(f'  合計: {n}件 / 的中: {hits} / ROI: {roi:.1f}% / 収支: {profit:+,.0f}円 / {black}/6年黒字')
    for yr in YEARS:
        yr_recs = [r for r in recs if r['year'] == yr]
        if not yr_recs: continue
        yn, yh, yroi, yprofit = roi_stats(yr_recs)
        mark = 'o' if yprofit > 0 else 'x'
        print(f'    {yr}: {yn}件  ROI {yroi:.1f}%  {mark}{yprofit:+,.0f}円')


def jackknife(recs):
    print('\n  --- ジャックナイフ推定（1年除外） ---')
    for excl in YEARS:
        sub = [r for r in recs if r['year'] != excl]
        n, hits, roi, profit = roi_stats(sub)
        print(f'  {excl}年除外: {n}件 / ROI {roi:.1f}% / {profit:+,.0f}円')


def main():
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        assigned = assign_races_to_conditions(
            cursor, STANDARD_BET_CONDITIONS, '2020-01-01', '2026-01-01'
        )
        cond_map = {}
        for cond in STANDARD_BET_CONDITIONS:
            for rid in assigned.get(cond['id'], []):
                if rid not in cond_map:
                    cond_map[rid] = cond
        all_cand_ids = list(cond_map.keys())

        print(f'候補レース: {len(all_cand_ids):,}件（オッズフィルタ前）')
        print('データ読込中...', flush=True)
        bef_score, bef_rank, adv_rank, odds_map, result_map, date_map = load_data(cursor, all_cand_ids)

    records = build_purchase_records(
        all_cand_ids, cond_map, bef_score, bef_rank, adv_rank, odds_map, result_map, date_map
    )

    all_recs = records
    match_recs = [r for r in records if r['match'] is True]
    mismatch_recs = [r for r in records if r['match'] is False]
    no_adv_recs = [r for r in records if r['match'] is None]

    print(f'\n{"="*70}')
    print('  advance/before 一致度フィルタ テスト結果')
    print(f'{"="*70}')

    print_section('【現行ベースライン（全体）】', all_recs, '7条件・フィルタなし')
    print_section('【一致グループ】', match_recs, 'advance/before完全一致')
    print_section('【不一致グループ】', mismatch_recs, 'advance/before不一致')
    print_section('【advance予測なし】', no_adv_recs, 'advance予測が存在しない')

    # IS / OOS 分割
    print(f'\n{"="*70}')
    print('  IS(2020-2023) / OOS(2024-2025) 分割')
    print(f'{"="*70}')
    for label, yrs in [('IS 2020-2023', [2020,2021,2022,2023]), ('OOS 2024-2025', [2024,2025])]:
        m = [r for r in match_recs if r['year'] in yrs]
        nm = [r for r in mismatch_recs if r['year'] in yrs]
        all_yr = [r for r in all_recs if r['year'] in yrs]
        n_m, _, roi_m, p_m = roi_stats(m)
        n_nm, _, roi_nm, p_nm = roi_stats(nm)
        n_a, _, roi_a, p_a = roi_stats(all_yr)
        print(f'\n  [{label}]')
        print(f'    全体:       {n_a}件 / ROI {roi_a:.1f}% / {p_a:+,.0f}円')
        print(f'    一致グループ: {n_m}件 / ROI {roi_m:.1f}% / {p_m:+,.0f}円')
        print(f'    不一致:     {n_nm}件 / ROI {roi_nm:.1f}% / {p_nm:+,.0f}円')

    # ジャックナイフ
    print(f'\n{"="*70}')
    print('  一致グループ ジャックナイフ推定')
    print(f'{"="*70}')
    jackknife(match_recs)

    # 件数サマリー
    print(f'\n{"="*70}')
    print('  件数・比率サマリー')
    print(f'{"="*70}')
    total = len(all_recs)
    print(f'  現行合計:     {total}件')
    print(f'  一致:         {len(match_recs)}件 ({100.0*len(match_recs)/total:.1f}%)')
    print(f'  不一致:       {len(mismatch_recs)}件 ({100.0*len(mismatch_recs)/total:.1f}%)')
    print(f'  advance無し:  {len(no_adv_recs)}件 ({100.0*len(no_adv_recs)/total:.1f}%)')
    print(f'\n  ★ 一致グループのみ採用した場合: {len(match_recs)}件 / 年平均{len(match_recs)/6:.0f}件')


if __name__ == '__main__':
    main()
