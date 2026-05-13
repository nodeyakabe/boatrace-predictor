#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析1: motor_scoreが高いレースのROI分析

現行7条件で絞られた1,610件レースを対象に、
P1選手のmotor_scoreとtotal_scoreでバンド分けし、ROI・的中率を確認する。
"""

import sqlite3
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.backtest_helpers import get_race_ids_for_condition

YEARS = range(2020, 2026)

def get_all_assigned_race_ids():
    """現行7条件のユニーク割当レースID一覧を取得（standard_backtest_unique同等）"""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        all_race_ids = set()
        race_to_condition = {}

        sorted_conditions = sorted(
            STANDARD_BET_CONDITIONS,
            key=lambda x: (x.get('priority', 999), STANDARD_BET_CONDITIONS.index(x))
        )

        for cond in sorted_conditions:
            race_ids = get_race_ids_for_condition(
                cursor, cond, '2020-01-01', '2026-01-01', require_odds=True
            )
            for race_id in race_ids:
                if race_id not in all_race_ids:
                    all_race_ids.add(race_id)
                    race_to_condition[race_id] = cond['id']

    print(f"ユニーク割当レース数: {len(all_race_ids):,}", flush=True)
    return list(all_race_ids), race_to_condition


def analyze_motor_score(all_race_ids, race_to_condition):
    """motor_scoreバンド別のROI分析"""

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        print("P1選手のmotor_score・total_score取得中...", flush=True)

        # P1（rank_prediction=1）のmotor_score, total_score取得
        race_ids = list(all_race_ids)
        motor_data = {}  # race_id -> (motor_score, total_score, year, month)

        for i in range(0, len(race_ids), 2000):
            batch = race_ids[i:i+2000]
            ph = ','.join(['?'] * len(batch))
            cursor.execute(f'''
                SELECT rp.race_id, rp.motor_score, rp.total_score,
                       CAST(strftime('%Y', r.race_date) AS INTEGER),
                       CAST(strftime('%m', r.race_date) AS INTEGER)
                FROM race_predictions rp
                JOIN races r ON rp.race_id = r.id
                WHERE rp.race_id IN ({ph})
                AND rp.prediction_type = 'before'
                AND rp.rank_prediction = 1
                AND rp.motor_score IS NOT NULL
                AND rp.total_score IS NOT NULL
            ''', batch)
            for rid, ms, ts, yr, mo in cursor.fetchall():
                motor_data[rid] = (ms, ts, yr, mo)

        print(f"motor_scoreあり: {len(motor_data):,}件", flush=True)

        # オッズ・結果取得（買い目: P1-P2-P3）
        print("オッズ・結果取得中...", flush=True)
        odds_map = {}
        result_map = {}

        for i in range(0, len(race_ids), 2000):
            batch = race_ids[i:i+2000]
            ph = ','.join(['?'] * len(batch))

            # P1-P2-P3コンビネーション取得
            cursor.execute(f'''
                SELECT race_id, pit_number, rank_prediction
                FROM race_predictions
                WHERE race_id IN ({ph})
                AND prediction_type = 'before'
                AND rank_prediction <= 3
            ''', batch)
            pred_map = {}
            for rid, pit, rp in cursor.fetchall():
                if rid not in pred_map:
                    pred_map[rid] = {}
                pred_map[rid][rp] = pit

        # 全レースのP1-P2-P3コンビネーションを構築してオッズ・結果取得
        combo_map = {}
        for rid in race_ids:
            pm = pred_map.get(rid, {})
            p1 = pm.get(1)
            p2 = pm.get(2)
            p3 = pm.get(3)
            if p1 and p2 and p3:
                combo_map[rid] = f"{p1}-{p2}-{p3}"

        # オッズ取得
        for i in range(0, len(race_ids), 2000):
            batch = race_ids[i:i+2000]
            ph = ','.join(['?'] * len(batch))
            cursor.execute(f'''
                SELECT race_id, combination, odds FROM trifecta_odds
                WHERE race_id IN ({ph})
            ''', batch)
            for rid, combo, odds in cursor.fetchall():
                if rid not in odds_map:
                    odds_map[rid] = {}
                odds_map[rid][combo] = odds

        # 結果取得
        for i in range(0, len(race_ids), 2000):
            batch = race_ids[i:i+2000]
            ph = ','.join(['?'] * len(batch))
            cursor.execute(f'''
                SELECT race_id, pit_number, rank FROM results
                WHERE race_id IN ({ph})
                AND is_invalid=0 AND rank IN ('1','2','3')
            ''', batch)
            for rid, pit, rank in cursor.fetchall():
                if rid not in result_map:
                    result_map[rid] = {}
                result_map[rid][rank] = pit

    # 各レースの勝敗・オッズ・motor_scoreを収集
    race_results = []
    for rid in race_ids:
        md = motor_data.get(rid)
        combo = combo_map.get(rid)
        res = result_map.get(rid)
        if not md or not combo or not res:
            continue
        if '1' not in res or '2' not in res or '3' not in res:
            continue

        motor_score, total_score, year, month = md
        actual = f"{res['1']}-{res['2']}-{res['3']}"
        hit = 1 if combo == actual else 0

        odds_data = odds_map.get(rid, {})
        odds = odds_data.get(combo)
        if not odds:
            continue

        motor_ratio = motor_score / total_score if total_score > 0 else 0
        race_results.append({
            'race_id': rid,
            'motor_score': motor_score,
            'total_score': total_score,
            'motor_ratio': motor_ratio,
            'year': year,
            'hit': hit,
            'odds': odds,
            'invest': 100,
            'payout': odds * 100 if hit else 0,
        })

    print(f"分析対象レース数: {len(race_results):,}", flush=True)

    if not race_results:
        print("分析対象なし")
        return

    # motor_scoreのパーセンタイルでバンド分け
    motor_scores = [r['motor_score'] for r in race_results]
    motor_scores_sorted = sorted(motor_scores)
    n = len(motor_scores_sorted)

    pct25 = motor_scores_sorted[int(n * 0.25)]
    pct50 = motor_scores_sorted[int(n * 0.50)]
    pct75 = motor_scores_sorted[int(n * 0.75)]

    print(f"\nmotor_score分布: 25th={pct25:.2f}, 50th={pct50:.2f}, 75th={pct75:.2f}")

    def get_band(ms):
        if ms < pct25:
            return f"Q1(<{pct25:.1f})"
        elif ms < pct50:
            return f"Q2({pct25:.1f}-{pct50:.1f})"
        elif ms < pct75:
            return f"Q3({pct50:.1f}-{pct75:.1f})"
        else:
            return f"Q4(>={pct75:.1f})"

    def get_ratio_band(ratio):
        if ratio < 0.20:
            return "比率<20%"
        elif ratio < 0.25:
            return "比率20-25%"
        elif ratio < 0.30:
            return "比率25-30%"
        elif ratio < 0.35:
            return "比率30-35%"
        else:
            return "比率>=35%"

    # バンド別集計
    band_stats = {}
    for r in race_results:
        band = get_band(r['motor_score'])
        if band not in band_stats:
            band_stats[band] = {'n': 0, 'hits': 0, 'invest': 0, 'payout': 0.0,
                                'years': {yr: {'n':0,'hits':0,'invest':0,'payout':0.0} for yr in YEARS}}
        band_stats[band]['n'] += 1
        band_stats[band]['hits'] += r['hit']
        band_stats[band]['invest'] += r['invest']
        band_stats[band]['payout'] += r['payout']
        yr = r['year']
        if yr in band_stats[band]['years']:
            band_stats[band]['years'][yr]['n'] += 1
            band_stats[band]['years'][yr]['hits'] += r['hit']
            band_stats[band]['years'][yr]['invest'] += r['invest']
            band_stats[band]['years'][yr]['payout'] += r['payout']

    # motor_ratio バンド別集計
    ratio_stats = {}
    for r in race_results:
        band = get_ratio_band(r['motor_ratio'])
        if band not in ratio_stats:
            ratio_stats[band] = {'n': 0, 'hits': 0, 'invest': 0, 'payout': 0.0,
                                 'years': {yr: {'n':0,'hits':0,'invest':0,'payout':0.0} for yr in YEARS}}
        ratio_stats[band]['n'] += 1
        ratio_stats[band]['hits'] += r['hit']
        ratio_stats[band]['invest'] += r['invest']
        ratio_stats[band]['payout'] += r['payout']
        yr = r['year']
        if yr in ratio_stats[band]['years']:
            ratio_stats[band]['years'][yr]['n'] += 1
            ratio_stats[band]['years'][yr]['hits'] += r['hit']
            ratio_stats[band]['years'][yr]['invest'] += r['invest']
            ratio_stats[band]['years'][yr]['payout'] += r['payout']

    # 出力
    print(f"\n{'='*100}")
    print("=== 分析1: motor_score乖離（現行7条件1,610件対象） ===")
    print(f"{'='*100}")

    print(f"\n【A】motor_score四分位バンド別ROI（絶対値）")
    print(f"  {'バンド':<25} {'件数':>5} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>10}  {'IS黒字(20-23)':>13} {'OOS黒字(24-25)':>14}")
    print("-" * 100)

    for band in [f"Q1(<{pct25:.1f})", f"Q2({pct25:.1f}-{pct50:.1f})", f"Q3({pct50:.1f}-{pct75:.1f})", f"Q4(>={pct75:.1f})"]:
        s = band_stats.get(band)
        if not s:
            continue
        roi = s['payout'] / s['invest'] * 100 if s['invest'] > 0 else 0
        profit = s['payout'] - s['invest']
        hit_rate = s['hits'] / s['n'] * 100 if s['n'] > 0 else 0

        is_black = sum(1 for yr in [2020,2021,2022,2023]
                       if (s['years'][yr]['payout'] - s['years'][yr]['invest']) > 0)
        oos_black = sum(1 for yr in [2024,2025]
                        if (s['years'][yr]['payout'] - s['years'][yr]['invest']) > 0)

        yr_str = '  '.join(
            f"{'○' if (s['years'][yr]['payout']-s['years'][yr]['invest'])>0 else '×'}"
            for yr in YEARS if s['years'][yr]['n'] > 0
        )

        print(f"  {band:<25} {s['n']:>5} {s['hits']:>4} {hit_rate:>6.1f}%  {roi:>7.1f}%  {profit:>+10,.0f}  IS:{is_black}/4年  OOS:{oos_black}/2年  {yr_str}")

    print(f"\n【B】motor_score/total_score比率バンド別ROI")
    print(f"  {'バンド':<15} {'件数':>5} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>10}  {'IS黒字(20-23)':>13} {'OOS黒字(24-25)':>14}")
    print("-" * 100)

    ratio_order = ["比率<20%", "比率20-25%", "比率25-30%", "比率30-35%", "比率>=35%"]
    for band in ratio_order:
        s = ratio_stats.get(band)
        if not s or s['n'] < 10:
            continue
        roi = s['payout'] / s['invest'] * 100 if s['invest'] > 0 else 0
        profit = s['payout'] - s['invest']
        hit_rate = s['hits'] / s['n'] * 100 if s['n'] > 0 else 0

        is_black = sum(1 for yr in [2020,2021,2022,2023]
                       if (s['years'][yr]['payout'] - s['years'][yr]['invest']) > 0)
        oos_black = sum(1 for yr in [2024,2025]
                        if (s['years'][yr]['payout'] - s['years'][yr]['invest']) > 0)

        yr_str = '  '.join(
            f"{'○' if (s['years'][yr]['payout']-s['years'][yr]['invest'])>0 else '×'}"
            for yr in YEARS if s['years'][yr]['n'] > 0
        )

        print(f"  {band:<15} {s['n']:>5} {s['hits']:>4} {hit_rate:>6.1f}%  {roi:>7.1f}%  {profit:>+10,.0f}  IS:{is_black}/4年  OOS:{oos_black}/2年  {yr_str}")

    # 全体ベースライン
    total_n = len(race_results)
    total_hits = sum(r['hit'] for r in race_results)
    total_invest = sum(r['invest'] for r in race_results)
    total_payout = sum(r['payout'] for r in race_results)
    total_roi = total_payout / total_invest * 100 if total_invest > 0 else 0
    total_profit = total_payout - total_invest
    print(f"\n  【全体ベースライン】{total_n}件  {total_hits}的中  {total_hits/total_n*100:.1f}%  ROI {total_roi:.1f}%  {total_profit:+,.0f}円")

    # 発見サマリー
    print(f"\n{'='*80}")
    print("  【発見サマリー】")
    threshold_roi = 160.0
    threshold_n = 50
    has_signal = False
    for band in [f"Q1(<{pct25:.1f})", f"Q2({pct25:.1f}-{pct50:.1f})", f"Q3({pct50:.1f}-{pct75:.1f})", f"Q4(>={pct75:.1f})"]:
        s = band_stats.get(band)
        if not s:
            continue
        roi = s['payout'] / s['invest'] * 100 if s['invest'] > 0 else 0
        is_black = sum(1 for yr in [2020,2021,2022,2023]
                       if (s['years'][yr]['payout'] - s['years'][yr]['invest']) > 0)
        oos_black = sum(1 for yr in [2024,2025]
                        if (s['years'][yr]['payout'] - s['years'][yr]['invest']) > 0)
        if roi >= threshold_roi and s['n'] >= threshold_n and (is_black >= 3 or oos_black >= 2):
            print(f"  ★有望: {band} ROI={roi:.1f}% n={s['n']}件 IS:{is_black}/4年 OOS:{oos_black}/2年")
            has_signal = True

    for band in ratio_order:
        s = ratio_stats.get(band)
        if not s or s['n'] < threshold_n:
            continue
        roi = s['payout'] / s['invest'] * 100 if s['invest'] > 0 else 0
        is_black = sum(1 for yr in [2020,2021,2022,2023]
                       if (s['years'][yr]['payout'] - s['years'][yr]['invest']) > 0)
        oos_black = sum(1 for yr in [2024,2025]
                        if (s['years'][yr]['payout'] - s['years'][yr]['invest']) > 0)
        if roi >= threshold_roi and (is_black >= 3 or oos_black >= 2):
            print(f"  ★有望(比率): {band} ROI={roi:.1f}% n={s['n']}件 IS:{is_black}/4年 OOS:{oos_black}/2年")
            has_signal = True

    if not has_signal:
        print("  シグナルなし（motor_scoreバンドに有意なROI差は見られない）")


if __name__ == '__main__':
    print("=== 分析1: motor_score乖離分析 ===")
    race_ids, race_to_cond = get_all_assigned_race_ids()
    analyze_motor_score(race_ids, race_to_cond)
