# -*- coding: utf-8 -*-
"""
パターンH 配分比較バックテスト

現行条件（B_A1_30_50_8VENUES）に対して、4つの配分パターンを比較する。

パターン①: 現行 H2  — p3:200円 / p4:100円（合計300円）
パターン②: 均等     — p3:150円 / p4:150円（合計300円）
パターン③: 逆傾斜   — p3:100円 / p4:200円（合計300円）
パターン④: p4廃止   — p3:300円 / p4:なし  （合計300円）

・投資総額は全パターン300円/レースで揃える（ROI比較を公平に）
・バックテストと同じget_race_ids_for_conditionを使用
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import sqlite3
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from scripts.backtest.backtest_helpers import get_race_ids_for_condition
from config.bet_conditions import STANDARD_BET_CONDITIONS

DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")


def get_condition():
    for cond in STANDARD_BET_CONDITIONS:
        if cond.get('id') == 'B_A1_30_50_8VENUES':
            return cond
    raise ValueError("B_A1_30_50_8VENUES 条件が見つかりません")


def load_race_data(conn, race_ids, cond):
    """対象レースの予測・オッズ・結果を取得"""
    if not race_ids:
        return pd.DataFrame()

    conn.execute("DROP TABLE IF EXISTS _bt_race_ids")
    conn.execute("CREATE TEMP TABLE _bt_race_ids (race_id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO _bt_race_ids VALUES (?)", [(rid,) for rid in race_ids])

    odds_min = cond['odds_min']
    odds_max = cond['odds_max']

    query = f"""
    SELECT
        r.id AS race_id,
        r.race_date,
        r.venue_code,
        rp1.pit_number AS p1,
        rp2.pit_number AS p2,
        rp3.pit_number AS p3,
        rp4.pit_number AS p4,
        -- p3軸オッズ
        COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
            AND o.combination = CAST(rp1.pit_number AS TEXT) || '-'
                             || CAST(rp2.pit_number AS TEXT) || '-'
                             || CAST(rp3.pit_number AS TEXT)), 0) AS odds_p3,
        -- p4軸オッズ
        COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
            AND o.combination = CAST(rp1.pit_number AS TEXT) || '-'
                             || CAST(rp2.pit_number AS TEXT) || '-'
                             || CAST(rp4.pit_number AS TEXT)), 0) AS odds_p4,
        -- 実際の着順
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') AS actual_1st,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') AS actual_2nd,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') AS actual_3rd
    FROM races r
    JOIN _bt_race_ids bt ON bt.race_id = r.id
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    """
    df = pd.read_sql_query(query, conn)

    # オッズフィルタ（バックテストと同じ: p3 OR p4 が範囲内）
    odds_min = cond['odds_min']
    odds_max = cond['odds_max']
    df['p3_in_range'] = (df['odds_p3'] >= odds_min) & (df['odds_p3'] < odds_max)
    df['p4_in_range'] = (df['odds_p4'] >= odds_min) & (df['odds_p4'] < odds_max)
    df = df[df['p3_in_range'] | df['p4_in_range']].copy()

    # 的中フラグ
    df['p12_hit']    = (df['actual_1st'] == df['p1']) & (df['actual_2nd'] == df['p2'])
    df['p3_is_3rd'] = (df['p12_hit']) & (df['actual_3rd'] == df['p3']) & df['p3_in_range']
    df['p4_is_3rd'] = (df['p12_hit']) & (df['actual_3rd'] == df['p4']) & df['p4_in_range']

    return df


def calc_pattern(df, bet_p3, bet_p4, label):
    """指定配分でのバックテスト結果を計算"""
    # 投資額
    inv_p3 = df['p3_in_range'].astype(int) * bet_p3
    inv_p4 = df['p4_in_range'].astype(int) * bet_p4
    investment = (inv_p3 + inv_p4).sum()

    # 払戻
    pay_p3 = (df['p3_is_3rd'] * df['odds_p3'] * bet_p3).sum()
    pay_p4 = (df['p4_is_3rd'] * df['odds_p4'] * bet_p4).sum()
    payout = pay_p3 + pay_p4

    # 購入レース数（少なくとも1点以上買うレース）
    bet_mask = (inv_p3 + inv_p4) > 0
    bets = bet_mask.sum()

    hits = (df['p3_is_3rd'] | df['p4_is_3rd']).sum()
    roi = payout / investment * 100 if investment > 0 else 0
    profit = payout - investment
    hit_rate = hits / bets * 100 if bets > 0 else 0

    return {
        'label': label,
        'bets': int(bets),
        'hits': int(hits),
        'hit_rate': hit_rate,
        'investment': int(investment),
        'payout': int(payout),
        'roi': roi,
        'profit': int(profit),
        'p3_hits': int(df['p3_is_3rd'].sum()),
        'p4_hits': int(df['p4_is_3rd'].sum()),
    }


def run_yearly(conn, race_ids_by_year, cond):
    """年度別結果を返す"""
    patterns = [
        ('現行H2  (200/100)', 200, 100),
        ('均等    (150/150)', 150, 150),
        ('逆傾斜  (100/200)', 100, 200),
        ('p4廃止  (300/  0)', 300,   0),
    ]

    yearly = {p[0]: {} for p in patterns}

    for year, rids in sorted(race_ids_by_year.items()):
        df = load_race_data(conn, rids, cond)
        for label, bp3, bp4 in patterns:
            res = calc_pattern(df, bp3, bp4, label)
            yearly[label][year] = res

    return yearly


def print_results(results_6yr, yearly):
    print("\n" + "="*70)
    print("【6年間通算比較（2020-2025）】")
    print("="*70)
    print(f"{'配分パターン':<22} | {'件数':>5} | {'的中':>4} | {'的中率':>7} | {'ROI':>7} | {'収支':>10}")
    print("-" * 70)
    for label, res in results_6yr.items():
        print(f"{label:<22} | {res['bets']:>5} | {res['hits']:>4} | "
              f"{res['hit_rate']:>6.1f}% | {res['roi']:>6.1f}% | {res['profit']:>+10,}円")

    print("\n" + "="*70)
    print("【年度別収支比較】")
    print("="*70)

    for label in yearly:
        print(f"\n{label}")
        print(f"  {'年度':>4} | {'件数':>5} | {'ROI':>7} | {'収支':>10} | {'p3的中':>6} | {'p4的中':>6}")
        print(f"  {'-'*55}")
        total_profit = 0
        black_years = 0
        for year in sorted(yearly[label].keys()):
            res = yearly[label][year]
            total_profit += res['profit']
            if res['profit'] > 0:
                black_years += 1
            mark = "○" if res['profit'] > 0 else "×"
            print(f"  {year} | {res['bets']:>5} | {res['roi']:>6.1f}% | {res['profit']:>+10,}円 | "
                  f"{res['p3_hits']:>6} | {res['p4_hits']:>6} | {mark}")
        print(f"  合計: {total_profit:+,}円  黒字年: {black_years}/6年")


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("="*70)
    print("パターンH 配分比較バックテスト")
    print("B×A1×30-50×8会場（2020-2025）")
    print("全パターン投資総額300円/レースで統一")
    print("="*70)

    cond = get_condition()

    # 年度別にレースIDを取得
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    race_ids_by_year = {}
    all_race_ids = set()

    for year in years:
        rids = get_race_ids_for_condition(
            cursor, cond,
            start_date=f'{year}-01-01',
            end_date=f'{year+1}-01-01'
        )
        race_ids_by_year[year] = rids
        all_race_ids |= rids
        print(f"  {year}年: {len(rids)}件")

    print(f"  合計: {len(all_race_ids)}件")

    # 6年間通算
    print("\n6年間通算データ取得中...")
    df_all = load_race_data(conn, all_race_ids, cond)
    print(f"  投資対象レース: {len(df_all)}件")

    patterns = [
        ('現行H2  (200/100)', 200, 100),
        ('均等    (150/150)', 150, 150),
        ('逆傾斜  (100/200)', 100, 200),
        ('p4廃止  (300/  0)', 300,   0),
    ]

    results_6yr = {}
    for label, bp3, bp4 in patterns:
        results_6yr[label] = calc_pattern(df_all, bp3, bp4, label)

    # 年度別
    print("年度別計算中...")
    yearly = {}
    for label, bp3, bp4 in patterns:
        yearly[label] = {}
        for year, rids in sorted(race_ids_by_year.items()):
            df_y = df_all[df_all['race_date'].str.startswith(str(year))].copy()
            yearly[label][year] = calc_pattern(df_y, bp3, bp4, label)

    # 結果表示
    print_results(results_6yr, yearly)

    # p3/p4各軸の単独成績
    print("\n" + "="*70)
    print("【参考】p3軸・p4軸の単独成績（現行条件のオッズ範囲内のみ）")
    print("="*70)
    p3_sub = df_all[df_all['p3_in_range']]
    p4_sub = df_all[df_all['p4_in_range']]

    for label, sub, hit_col in [('p3軸（1-2-3）', p3_sub, 'p3_is_3rd'), ('p4軸（1-2-4）', p4_sub, 'p4_is_3rd')]:
        n = len(sub)
        hits = sub[hit_col].sum()
        hr = hits / n * 100 if n > 0 else 0
        odds_col = 'odds_p3' if 'p3' in hit_col else 'odds_p4'
        bet_amt = 200 if 'p3' in hit_col else 100
        inv = n * bet_amt
        pay = (sub[hit_col] * sub[odds_col] * bet_amt).sum()
        roi = pay / inv * 100 if inv > 0 else 0
        profit = pay - inv
        print(f"  {label}: {n}件 / 的中{hits}件({hr:.1f}%) / ROI {roi:.1f}% / {profit:+,}円")

    conn.close()
    print("\n完了")


if __name__ == '__main__':
    main()
