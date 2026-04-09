#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析3: 月別×会場パフォーマンス（現行7条件の弱月を特定）

現行7条件のそれぞれについて月別ROI・的中率を集計し、
構造的に弱い月（除外候補）を発見する。

注意: 月別除外は過去に多数棄却された（bet_conditions.py v2.36.0参照）。
採用基準を厳しく設定し、過学習防止のため件数>=15 + ROI<75%の条件を使用。
"""

import sqlite3
import sys
import os
from collections import defaultdict

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.backtest_helpers import get_race_ids_for_condition

YEARS = range(2020, 2026)
MONTHS = range(1, 13)
MONTH_NAMES = {1:'1月',2:'2月',3:'3月',4:'4月',5:'5月',6:'6月',
               7:'7月',8:'8月',9:'9月',10:'10月',11:'11月',12:'12月'}


def get_race_results_for_condition(cursor, cond, race_ids):
    """
    指定条件・レースIDの各レースの結果（的中・オッズ・月・年）を取得

    Returns: list of (race_id, year, month, hit, odds, invest, payout)
    """
    if not race_ids:
        return []

    race_ids_list = list(race_ids)
    placeholders = ','.join(['?'] * len(race_ids_list))

    use_pattern_h = cond.get('use_pattern_h', False)

    if use_pattern_h:
        # パターンH: 3点買い（200円/100円/100円）
        query = f"""
        WITH race_bets AS (
            SELECT
                r.id as race_id,
                CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
                CAST(strftime('%m', r.race_date) AS INTEGER) as month,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3,
                rp4.pit_number as p4,
                rp5.pit_number as p5,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)), 0) as odds_123,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)), 0) as odds_124,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp5.pit_number AS TEXT)), 0) as odds_125,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
            WHERE r.id IN ({placeholders})
        )
        SELECT
            race_id, year, month,
            CASE
                WHEN odds_123 >= {cond.get('odds_min',0)} AND odds_123 < {cond.get('odds_max',9999)}
                     AND actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p3 THEN 1
                WHEN odds_124 >= {cond.get('odds_min',0)} AND odds_124 < {cond.get('odds_max',9999)}
                     AND actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p4 THEN 1
                WHEN odds_125 >= {cond.get('odds_min',0)} AND odds_125 < {cond.get('odds_max',9999)}
                     AND actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p5 THEN 1
                ELSE 0
            END as hit,
            CASE
                WHEN odds_123 >= {cond.get('odds_min',0)} AND odds_123 < {cond.get('odds_max',9999)} THEN odds_123
                WHEN odds_124 >= {cond.get('odds_min',0)} AND odds_124 < {cond.get('odds_max',9999)} THEN odds_124
                WHEN odds_125 >= {cond.get('odds_min',0)} AND odds_125 < {cond.get('odds_max',9999)} THEN odds_125
                ELSE 0
            END as winning_odds
        FROM race_bets
        WHERE (
            (odds_123 >= {cond.get('odds_min',0)} AND odds_123 < {cond.get('odds_max',9999)}) OR
            (odds_124 >= {cond.get('odds_min',0)} AND odds_124 < {cond.get('odds_max',9999)}) OR
            (odds_125 >= {cond.get('odds_min',0)} AND odds_125 < {cond.get('odds_max',9999)})
        )
        """
    else:
        # 1点買い
        query = f"""
        SELECT
            r.id as race_id,
            CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
            CAST(strftime('%m', r.race_date) AS INTEGER) as month,
            CASE
                WHEN t.odds >= {cond.get('odds_min',0)} AND t.odds < {cond.get('odds_max',9999)}
                     AND res1.pit_number = rp1.pit_number
                     AND res2.pit_number = rp2.pit_number
                     AND res3.pit_number = rp3.pit_number
                THEN 1
                ELSE 0
            END as hit,
            t.odds as winning_odds
        FROM races r
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
            AND t.odds >= {cond.get('odds_min',0)} AND t.odds < {cond.get('odds_max',9999)}
        LEFT JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1' AND res1.is_invalid = 0
        LEFT JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2' AND res2.is_invalid = 0
        LEFT JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3' AND res3.is_invalid = 0
        WHERE r.id IN ({placeholders})
        """

    cursor.execute(query, race_ids_list)
    return cursor.fetchall()


def analyze_monthly(conn_cursor, cond, start_date='2020-01-01', end_date='2026-01-01'):
    """条件の月別パフォーマンスを集計"""
    cursor = conn_cursor

    # 4月は除外済みなので、ここでは全期間のレースIDを取得（月除外なし版で）
    # 実際の月別分析のためにmonth_excludeを一時的に無効化したコピーで取得
    cond_no_month_exclude = dict(cond)
    cond_no_month_exclude['month_exclude'] = []  # 月除外を無効化して全月のデータを取得
    # ただし4月は除外（GLOBAL_MONTH_EXCLUDESは維持されるため自動適用）

    race_ids = get_race_ids_for_condition(cursor, cond_no_month_exclude, start_date, end_date, require_odds=True)

    if not race_ids:
        return {}

    rows = get_race_results_for_condition(cursor, cond, list(race_ids))

    # 月別集計
    monthly_stats = defaultdict(lambda: {'n': 0, 'hits': 0, 'invest': 0, 'payout': 0.0, 'years': defaultdict(lambda: {'n':0,'hits':0,'invest':0,'payout':0.0})})

    invest_per_bet = 400 if cond.get('use_pattern_h') else 100

    for row in rows:
        race_id, year, month, hit, winning_odds = row
        s = monthly_stats[month]
        s['n'] += 1
        s['hits'] += hit
        s['invest'] += invest_per_bet
        if hit:
            payout = winning_odds * invest_per_bet
            s['payout'] += payout
        yr = s['years'][year]
        yr['n'] += 1
        yr['hits'] += hit
        yr['invest'] += invest_per_bet
        if hit:
            yr['payout'] += winning_odds * invest_per_bet

    return monthly_stats


def main():
    print("=== 分析3: 月別パフォーマンス分析 ===", flush=True)

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # 全条件の月別統計を集計
        all_monthly = {}  # cond_id -> monthly_stats
        cond_totals = {}  # cond_id -> total stats

        for cond in STANDARD_BET_CONDITIONS:
            print(f"  {cond['id']} 集計中...", flush=True)
            monthly = analyze_monthly(cursor, cond)
            all_monthly[cond['id']] = monthly

            # 条件全体合計
            total_n = sum(s['n'] for s in monthly.values())
            total_hits = sum(s['hits'] for s in monthly.values())
            total_invest = sum(s['invest'] for s in monthly.values())
            total_payout = sum(s['payout'] for s in monthly.values())
            cond_totals[cond['id']] = {
                'n': total_n,
                'hits': total_hits,
                'invest': total_invest,
                'payout': total_payout,
                'roi': total_payout / total_invest * 100 if total_invest > 0 else 0,
            }

    print(f"\n{'='*120}")
    print("=== 分析3: 月別×条件パフォーマンス ===")
    print(f"{'='*120}")

    # 除外候補リスト（ROI<75% + 件数>=15）
    exclude_candidates = []

    for cond in STANDARD_BET_CONDITIONS:
        cond_id = cond['id']
        monthly = all_monthly.get(cond_id, {})
        ct = cond_totals.get(cond_id, {})

        if not monthly:
            continue

        print(f"\n【{cond_id}】{cond['name']}")
        print(f"  全体: {ct.get('n',0)}件  ROI {ct.get('roi',0):.1f}%  収支{ct.get('payout',0)-ct.get('invest',0):+,.0f}円")
        print(f"  {'月':>4} {'件数':>5} {'的中':>4} {'ROI':>8} {'収支':>10}  年度別  判定")
        print("  " + "-" * 90)

        for month in MONTHS:
            if month == 4:
                continue  # 4月はGLOBAL除外済み
            s = monthly.get(month)
            if not s or s['n'] == 0:
                continue

            roi = s['payout'] / s['invest'] * 100 if s['invest'] > 0 else 0
            profit = s['payout'] - s['invest']
            hit_rate = s['hits'] / s['n'] * 100 if s['n'] > 0 else 0

            # 6年間の黒字年数
            black_years = 0
            yr_details = []
            for yr in YEARS:
                ys = s['years'].get(yr, {'n':0,'hits':0,'invest':0,'payout':0.0})
                yr_p = ys['payout'] - ys['invest']
                if yr_p > 0:
                    black_years += 1
                yr_details.append((yr, ys['n'], yr_p))

            yr_str = '  '.join(
                f"{'○' if p > 0 else ('－' if n == 0 else '×')}"
                for yr, n, p in yr_details
            )

            # 除外候補判定: 件数>=15 + ROI<75% + 黒字年数<=1/6
            is_exclude_candidate = (s['n'] >= 15 and roi < 75.0 and black_years <= 1)
            # 強い除外候補: 件数>=20 + ROI<60% + 黒字年数0/6
            is_strong_candidate = (s['n'] >= 20 and roi < 60.0 and black_years == 0)

            marker = ''
            if is_strong_candidate:
                marker = '[強除外候補]'
                exclude_candidates.append({
                    'cond_id': cond_id,
                    'month': month,
                    'n': s['n'],
                    'roi': roi,
                    'profit': profit,
                    'black_years': black_years,
                    'strength': 'strong',
                })
            elif is_exclude_candidate:
                marker = '△除外候補'
                exclude_candidates.append({
                    'cond_id': cond_id,
                    'month': month,
                    'n': s['n'],
                    'roi': roi,
                    'profit': profit,
                    'black_years': black_years,
                    'strength': 'weak',
                })

            print(f"  {MONTH_NAMES[month]:>4} {s['n']:>5} {s['hits']:>4}  {roi:>7.1f}%  {profit:>+9,.0f}  {yr_str}  {marker}")

    # 除外候補サマリー
    print(f"\n{'='*100}")
    print("=== 除外候補一覧 ===")
    print(f"採用基準（保守的）: 件数>=15 + ROI<75% + 黒字年<=1/6年")
    print(f"強採用基準:         件数>=20 + ROI<60% + 黒字年0/6年（6年連続0的中相当）")
    print("-" * 80)

    # 過去に採用されている除外リスト（参考）
    print("\n【参考: 現行GLOBAL_MONTH_EXCLUDES = [4]（全条件4月除外済み）】")
    print("【参考: GLOBAL_VENUE_MONTH_EXCLUDES = 多摩川×2月/福岡×2月/鳴門×1月/鳴門×2月/宮島×2月】\n")

    if not exclude_candidates:
        print("  除外候補なし（件数>=15 + ROI<75% + 黒字年<=1/6 を満たす月はない）")
    else:
        strong = [c for c in exclude_candidates if c['strength'] == 'strong']
        weak = [c for c in exclude_candidates if c['strength'] == 'weak']

        if strong:
            print("  【強除外候補（件数>=20 + ROI<60% + 黒字年0/6）】")
            for c in sorted(strong, key=lambda x: x['profit']):
                print(f"    {c['cond_id']} × {MONTH_NAMES[c['month']]}: "
                      f"{c['n']}件 ROI {c['roi']:.1f}% {c['profit']:+,.0f}円 {c['black_years']}/6年黒字")
                print(f"      → 除外効果（推定損失回避）: {-c['profit']:+,.0f}円（6年累計）")

        if weak:
            print("\n  【除外候補（件数>=15 + ROI<75% + 黒字年<=1/6）】")
            for c in sorted(weak, key=lambda x: x['profit']):
                print(f"    {c['cond_id']} × {MONTH_NAMES[c['month']]}: "
                      f"{c['n']}件 ROI {c['roi']:.1f}% {c['profit']:+,.0f}円 {c['black_years']}/6年黒字")

    # 全条件合算の月別パフォーマンス
    print(f"\n{'='*80}")
    print("=== 全条件合算 月別パフォーマンス ===")
    print(f"  {'月':>4} {'件数':>5} {'的中':>4} {'ROI':>8} {'収支':>10}  判定")
    print("-" * 60)

    combined_monthly = defaultdict(lambda: {'n':0,'hits':0,'invest':0,'payout':0.0})
    for cond_id, monthly in all_monthly.items():
        for month, s in monthly.items():
            cm = combined_monthly[month]
            cm['n'] += s['n']
            cm['hits'] += s['hits']
            cm['invest'] += s['invest']
            cm['payout'] += s['payout']

    for month in MONTHS:
        if month == 4:
            print(f"  {MONTH_NAMES[month]:>4}   除外済（GLOBAL_MONTH_EXCLUDES）")
            continue
        s = combined_monthly.get(month)
        if not s or s['n'] == 0:
            continue
        roi = s['payout'] / s['invest'] * 100 if s['invest'] > 0 else 0
        profit = s['payout'] - s['invest']
        marker = ''
        if roi < 75 and s['n'] >= 30:
            marker = '← 全体弱月'
        print(f"  {MONTH_NAMES[month]:>4} {s['n']:>5} {s['hits']:>4}  {roi:>7.1f}%  {profit:>+9,.0f}  {marker}")

    # 最終発見サマリー
    print(f"\n{'='*80}")
    print("  【発見サマリー】")
    if not exclude_candidates:
        print("  明確なパターンなし（条件×月の組み合わせで構造的弱さは発見されず）")
        print("  → 全条件の月別パフォーマンスは概ね均一。追加の月除外は不要。")
    else:
        strong = [c for c in exclude_candidates if c['strength'] == 'strong']
        weak = [c for c in exclude_candidates if c['strength'] == 'weak']
        if strong:
            print(f"  強除外候補: {len(strong)}件（件数>=20 + ROI<60% + 6年連続0的中相当）")
            for c in sorted(strong, key=lambda x: x['profit']):
                print(f"    → {c['cond_id']} × {MONTH_NAMES[c['month']]}: "
                      f"ROI {c['roi']:.1f}% {c['profit']:+,.0f}円（除外効果{-c['profit']:+,.0f}円）")
        if weak:
            print(f"  注意: 除外候補{len(weak)}件は件数不足・過学習リスクあり（v2.36.0方針: 50件未満は不採用）")

    print("\n  [注意] 月別除外採用判断: v2.36.0方針「月次サンプル50件未満は根拠薄として不採用」を維持すること")


if __name__ == '__main__':
    main()
