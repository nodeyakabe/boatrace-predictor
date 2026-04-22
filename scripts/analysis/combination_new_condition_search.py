# -*- coding: utf-8 -*-
"""
新条件候補の絞り込み分析

最強候補「p1-p4-p2 × 100倍〜 × 信頼度A」の詳細探索
- 会場フィルタで収益を改善できるか
- c1ランク条件を加えると効果があるか
- オッズ上限を絞ると安定するか

また「現行条件内でのp1-p4-p2 vs p1-p2-p4の重複確認」も実施
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

IS_START  = '2020-01-01'; IS_END    = '2022-12-31'
OOS_START = '2023-01-01'; OOS_END   = '2025-12-31'
YEARS     = [2020, 2021, 2022, 2023, 2024, 2025]

VENUE_NAMES = {
    1:'桐生', 2:'戸田', 3:'江戸川', 4:'平和島', 5:'多摩川',
    6:'浜名湖', 7:'蒲郡', 8:'常滑', 9:'津', 10:'三国',
    11:'びわこ', 12:'住之江', 13:'尼崎', 14:'鳴門', 15:'丸亀',
    16:'児島', 17:'宮島', 18:'徳山', 19:'下関', 20:'若松',
    21:'芦屋', 22:'福岡', 23:'唐津', 24:'大村',
}


def load_full_data(conn, start_date, end_date):
    query = f"""
    SELECT
        r.id AS race_id, r.race_date, r.venue_code,
        rp1.pit_number AS p1, rp2.pit_number AS p2,
        rp3.pit_number AS p3, rp4.pit_number AS p4, rp5.pit_number AS p5,
        rp1.confidence AS confidence,
        e1.racer_rank AS c1_rank,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') AS actual_1st,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') AS actual_2nd,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') AS actual_3rd
    FROM races r
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
    LEFT JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE r.race_date >= '{start_date}' AND r.race_date <= '{end_date}'
      AND rp1.confidence IN ('A', 'B')
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') IS NOT NULL
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') IS NOT NULL
    """
    return pd.read_sql_query(query, conn)


def load_odds(conn, race_ids):
    if len(race_ids) == 0:
        return pd.DataFrame(columns=['race_id', 'combination', 'odds'])
    conn.execute("DROP TABLE IF EXISTS _ncs_race_ids")
    conn.execute("CREATE TEMP TABLE _ncs_race_ids (race_id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO _ncs_race_ids VALUES (?)", [(int(rid),) for rid in race_ids])
    return pd.read_sql_query(
        "SELECT o.race_id, o.combination, o.odds FROM trifecta_odds o JOIN _ncs_race_ids t ON t.race_id = o.race_id WHERE o.odds > 0",
        conn
    )


def build_combo(df_base, df_odds, col_2nd, col_3rd, odds_lo, odds_hi):
    df_work = df_base[['race_id', 'race_date', 'venue_code', 'confidence', 'c1_rank',
                         'p1', col_2nd, col_3rd,
                         'actual_1st', 'actual_2nd', 'actual_3rd']].copy()
    df_work.columns = ['race_id', 'race_date', 'venue_code', 'confidence', 'c1_rank',
                        'p1', 'p_2nd', 'p_3rd',
                        'actual_1st', 'actual_2nd', 'actual_3rd']
    df_work['combination'] = (
        df_work['p1'].astype(str) + '-' +
        df_work['p_2nd'].astype(str) + '-' +
        df_work['p_3rd'].astype(str)
    )
    merged = df_work.merge(df_odds[['race_id', 'combination', 'odds']],
                            on=['race_id', 'combination'], how='inner')
    if len(merged) == 0:
        return pd.DataFrame()
    merged = merged[(merged['odds'] >= odds_lo) & (merged['odds'] < odds_hi)].copy()
    merged['hit'] = (
        (merged['actual_1st'] == merged['p1']) &
        (merged['actual_2nd'] == merged['p_2nd']) &
        (merged['actual_3rd'] == merged['p_3rd'])
    )
    merged['year'] = merged['race_date'].str[:4].astype(int)
    return merged


def agg(df):
    if len(df) == 0: return {'n':0,'hits':0,'hit_rate':0,'roi':0,'profit':0}
    n=len(df); hits=int(df['hit'].sum())
    pay=float((df['hit']*df['odds']*100).sum()); inv=n*100
    return {'n':n,'hits':hits,'hit_rate':hits/n*100,'roi':pay/inv*100 if inv>0 else 0,'profit':int(pay-inv)}


def agg_yearly(df):
    rows = []
    for year in YEARS:
        sub = df[df['year']==year]
        a = agg(sub)
        a['year'] = year
        rows.append(a)
    return rows


def summary_line(a_is, a_oos, label):
    mk_is  = '★' if a_is['roi']  >= 100 else ' '
    mk_oos = '★' if a_oos['roi'] >= 100 else ' '
    judge  = '◎' if a_is['roi']>=100 and a_oos['roi']>=100 else \
             ('○OOS' if a_oos['roi']>=100 else ('△IS' if a_is['roi']>=100 else '×'))
    return (f"  {label:<35} | IS {a_is['n']:>5,}件/{a_is['roi']:>5.1f}%{mk_is}/{a_is['profit']:>+8,}円 | "
            f"OOS {a_oos['n']:>5,}件/{a_oos['roi']:>5.1f}%{mk_oos}/{a_oos['profit']:>+8,}円 | {judge}")


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("="*90)
    print("新条件候補の絞り込み分析")
    print("対象: p1-p4-p2 × 100倍〜 を中心とした探索")
    print("="*90)

    print("\nIS期間データ取得中...")
    df_is  = load_full_data(conn, IS_START, IS_END)
    odds_is = load_odds(conn, df_is['race_id'].unique())
    print(f"  {len(df_is):,}件")

    print("OOS期間データ取得中...")
    df_oos  = load_full_data(conn, OOS_START, OOS_END)
    odds_oos = load_odds(conn, df_oos['race_id'].unique())
    print(f"  {len(df_oos):,}件")

    # ==================================================================
    # Part 1: p1-p4-p2 × 100倍〜 の絞り込み探索（信頼度・c1ランク・オッズ上限）
    # ==================================================================
    print("\n" + "="*90)
    print("【Part 1】p1-p4-p2 × 100倍〜 の絞り込み（信頼度・c1ランク・オッズ上限）")
    print("="*90)
    print(f"  {'条件':<35} | {'IS':>30} | {'OOS':>30} | 判定")
    print(f"  {'-'*85}")

    combos_to_test = [
        # (label, 信頼度フィルタ, c1_rank_filter, odds_lo, odds_hi)
        ('A+B × 100倍〜',        ['A','B'],  None,   100, 9999),
        ('A   × 100倍〜',        ['A'],      None,   100, 9999),
        ('B   × 100倍〜',        ['B'],      None,   100, 9999),
        ('A × A1 × 100倍〜',     ['A'],      ['A1'], 100, 9999),
        ('A × A1+A2 × 100倍〜',  ['A'],      ['A1','A2'], 100, 9999),
        ('A × non-A1 × 100倍〜', ['A'],      'non_a1', 100, 9999),
        ('A × 100-200倍',        ['A'],      None,   100, 200),
        ('A × 200倍〜',          ['A'],      None,   200, 9999),
        ('A × 50-100倍',         ['A'],      None,   50,  100),
        ('A+B × 50-200倍',       ['A','B'],  None,   50,  200),
    ]

    for label, conf_list, c1_filter, odds_lo, odds_hi in combos_to_test:
        df_is_f  = df_is[df_is['confidence'].isin(conf_list)]
        df_oos_f = df_oos[df_oos['confidence'].isin(conf_list)]

        if c1_filter == 'non_a1':
            df_is_f  = df_is_f[~df_is_f['c1_rank'].isin(['A1'])]
            df_oos_f = df_oos_f[~df_oos_f['c1_rank'].isin(['A1'])]
        elif c1_filter:
            df_is_f  = df_is_f[df_is_f['c1_rank'].isin(c1_filter)]
            df_oos_f = df_oos_f[df_oos_f['c1_rank'].isin(c1_filter)]

        odds_is_f  = odds_is[odds_is['race_id'].isin(df_is_f['race_id'])]
        odds_oos_f = odds_oos[odds_oos['race_id'].isin(df_oos_f['race_id'])]

        dc_is  = build_combo(df_is_f,  odds_is_f,  'p4', 'p2', odds_lo, odds_hi)
        dc_oos = build_combo(df_oos_f, odds_oos_f, 'p4', 'p2', odds_lo, odds_hi)
        print(summary_line(agg(dc_is), agg(dc_oos), label))

    # ==================================================================
    # Part 2: p1-p4-p2 × 100倍〜 × 信頼度A の会場別IS/OOS
    # ==================================================================
    print("\n" + "="*90)
    print("【Part 2】p1-p4-p2 × 100倍〜 × 信頼度A の会場別IS/OOS比較")
    print("="*90)

    df_is_a  = df_is[df_is['confidence'] == 'A']
    df_oos_a = df_oos[df_oos['confidence'] == 'A']
    oids_is_a  = odds_is[odds_is['race_id'].isin(df_is_a['race_id'])]
    oids_oos_a = odds_oos[odds_oos['race_id'].isin(df_oos_a['race_id'])]

    dc_is_a  = build_combo(df_is_a,  oids_is_a,  'p4', 'p2', 100, 9999)
    dc_oos_a = build_combo(df_oos_a, oids_oos_a, 'p4', 'p2', 100, 9999)

    rows_v = []
    for vc in sorted(set(dc_is_a['venue_code'].tolist() + dc_oos_a['venue_code'].tolist())):
        sub_is  = dc_is_a[dc_is_a['venue_code']   == vc]
        sub_oos = dc_oos_a[dc_oos_a['venue_code'] == vc]
        ai = agg(sub_is); ao = agg(sub_oos)
        if ai['n'] < 20 and ao['n'] < 20: continue
        rows_v.append((vc, ai, ao))
    rows_v.sort(key=lambda x: x[2]['profit'], reverse=True)

    print(f"  {'会場':<8} | {'IS件数':>6} | {'IS ROI':>7} | {'IS収支':>9} | {'OOS件数':>7} | {'OOS ROI':>8} | {'OOS収支':>9} | 判定")
    print(f"  {'-'*78}")
    oos_black_venues = []
    for vc, ai, ao in rows_v:
        is_p  = ai['roi'] >= 100; oos_p = ao['roi'] >= 100
        judge = '◎' if (is_p and oos_p) else ('○OOS' if oos_p else ('△IS' if is_p else '×'))
        if oos_p: oos_black_venues.append(vc)
        mk_is  = '★' if is_p  else ' '
        mk_oos = '★' if oos_p else ' '
        vname = VENUE_NAMES.get(vc, str(vc))
        print(f"  {vname:<8} | {ai['n']:>6,} | {ai['roi']:>6.1f}%{mk_is}| {ai['profit']:>+8,}円 | "
              f"{ao['n']:>7,} | {ao['roi']:>7.1f}%{mk_oos}| {ao['profit']:>+8,}円 | {judge}")

    # ==================================================================
    # Part 3: 現行条件内でのp1-p4-p2 vs p1-p2-p4の重複確認
    # ==================================================================
    print("\n" + "="*90)
    print("【Part 3】現行条件(B×A1×30-50×8会場)内の p1-p4-p2 vs p1-p2-p4 重複確認")
    print("「同じレースに両方のオッズが存在するか？ or 別レース？」")
    print("="*90)

    cond_8v = next((c for c in STANDARD_BET_CONDITIONS if c.get('id') == 'B_A1_30_50_8VENUES'), None)
    if cond_8v:
        all_rids = set()
        for year in YEARS:
            rids = get_race_ids_for_condition(cursor, cond_8v,
                f'{year}-01-01', f'{year+1}-01-01')
            all_rids |= rids

        df_8v_all = pd.concat([df_is, df_oos])
        df_8v = df_8v_all[df_8v_all['race_id'].isin(all_rids)]
        odds_8v_all = pd.concat([odds_is, odds_oos])
        odds_8v = odds_8v_all[odds_8v_all['race_id'].isin(all_rids)]

        # p1-p4-p2の30-50倍レース
        dc_p4p2 = build_combo(df_8v, odds_8v, 'p4', 'p2', 30, 50)
        # p1-p2-p4の30-50倍レース
        dc_p2p4 = build_combo(df_8v, odds_8v, 'p2', 'p4', 30, 50)

        rids_p4p2 = set(dc_p4p2['race_id'].unique()) if len(dc_p4p2) > 0 else set()
        rids_p2p4 = set(dc_p2p4['race_id'].unique()) if len(dc_p2p4) > 0 else set()

        overlap = rids_p4p2 & rids_p2p4
        only_p4p2 = rids_p4p2 - rids_p2p4
        only_p2p4 = rids_p2p4 - rids_p4p2

        print(f"\n  p1-p4-p2対象レース: {len(rids_p4p2)}件")
        print(f"  p1-p2-p4対象レース: {len(rids_p2p4)}件")
        print(f"  重複(両方): {len(overlap)}件")
        print(f"  p1-p4-p2のみ: {len(only_p4p2)}件")
        print(f"  p1-p2-p4のみ: {len(only_p2p4)}件")

        # 重複レースでの両者の収益
        if len(overlap) > 0:
            dc_overlap_p4p2 = dc_p4p2[dc_p4p2['race_id'].isin(overlap)]
            dc_overlap_p2p4 = dc_p2p4[dc_p2p4['race_id'].isin(overlap)]
            ao1 = agg(dc_overlap_p4p2); ao2 = agg(dc_overlap_p2p4)
            print(f"\n  重複レース内での比較:")
            print(f"    p1-p4-p2: {ao1['n']}件 / ROI {ao1['roi']:.1f}% / {ao1['profit']:+,}円")
            print(f"    p1-p2-p4: {ao2['n']}件 / ROI {ao2['roi']:.1f}% / {ao2['profit']:+,}円")

    # ==================================================================
    # Part 4: p1-p3-p2 × 50-100倍 × B の年度別 + 会場絞り込み
    # ==================================================================
    print("\n" + "="*90)
    print("【Part 4】候補2: p1-p3-p2 × 50-100倍 × 信頼度B の会場別絞り込み")
    print("="*90)

    df_is_b  = df_is[df_is['confidence'] == 'B']
    df_oos_b = df_oos[df_oos['confidence'] == 'B']
    oids_is_b  = odds_is[odds_is['race_id'].isin(df_is_b['race_id'])]
    oids_oos_b = odds_oos[odds_oos['race_id'].isin(df_oos_b['race_id'])]

    dc_is_b3p2  = build_combo(df_is_b,  oids_is_b,  'p3', 'p2', 50, 100)
    dc_oos_b3p2 = build_combo(df_oos_b, oids_oos_b, 'p3', 'p2', 50, 100)

    rows_v2 = []
    for vc in sorted(set(dc_is_b3p2['venue_code'].tolist() + dc_oos_b3p2['venue_code'].tolist())):
        sub_is  = dc_is_b3p2[dc_is_b3p2['venue_code']   == vc]
        sub_oos = dc_oos_b3p2[dc_oos_b3p2['venue_code'] == vc]
        ai = agg(sub_is); ao = agg(sub_oos)
        if ai['n'] < 20 and ao['n'] < 20: continue
        rows_v2.append((vc, ai, ao))
    rows_v2.sort(key=lambda x: x[2]['profit'], reverse=True)

    print(f"  {'会場':<8} | {'IS件数':>6} | {'IS ROI':>7} | {'IS収支':>9} | {'OOS件数':>7} | {'OOS ROI':>8} | {'OOS収支':>9} | 判定")
    print(f"  {'-'*78}")
    for vc, ai, ao in rows_v2:
        is_p  = ai['roi'] >= 100; oos_p = ao['roi'] >= 100
        judge = '◎' if (is_p and oos_p) else ('○OOS' if oos_p else ('△IS' if is_p else '×'))
        mk_is  = '★' if is_p  else ' '
        mk_oos = '★' if oos_p else ' '
        vname = VENUE_NAMES.get(vc, str(vc))
        print(f"  {vname:<8} | {ai['n']:>6,} | {ai['roi']:>6.1f}%{mk_is}| {ai['profit']:>+8,}円 | "
              f"{ao['n']:>7,} | {ao['roi']:>7.1f}%{mk_oos}| {ao['profit']:>+8,}円 | {judge}")

    conn.close()
    print("\n完了")


if __name__ == '__main__':
    main()
