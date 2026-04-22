# -*- coding: utf-8 -*-
"""
有望組み合わせの深掘り分析

前段分析で判明した有望組み合わせを会場・信頼度別に詳細分析する

注目対象:
  A. p1-p3-p2 × 50-100倍帯 (OOS ROI 119.8%)
  B. p1-p4-p2 × 100倍〜帯  (OOS ROI 117.6%)
  C. p1-p3-p2 × 30-50倍帯  (IS ROI 103.2%, OOS 93.4%)
  D. 現行条件(B×A1×30-50×8会場)対象レースでの12組み合わせ比較

目的: 会場・信頼度セグメントで更に絞り込めるか確認
     現行条件レース内での最適組み合わせを特定
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

IS_START  = '2020-01-01'
IS_END    = '2022-12-31'
OOS_START = '2023-01-01'
OOS_END   = '2025-12-31'

VENUE_NAMES = {
    1:'桐生', 2:'戸田', 3:'江戸川', 4:'平和島', 5:'多摩川',
    6:'浜名湖', 7:'蒲郡', 8:'常滑', 9:'津', 10:'三国',
    11:'びわこ', 12:'住之江', 13:'尼崎', 14:'鳴門', 15:'丸亀',
    16:'児島', 17:'宮島', 18:'徳山', 19:'下関', 20:'若松',
    21:'芦屋', 22:'福岡', 23:'唐津', 24:'大村',
}

COMBINATIONS = [
    ('p1-p2-p3', 'p2', 'p3'),
    ('p1-p2-p4', 'p2', 'p4'),
    ('p1-p2-p5', 'p2', 'p5'),
    ('p1-p3-p2', 'p3', 'p2'),
    ('p1-p3-p4', 'p3', 'p4'),
    ('p1-p3-p5', 'p3', 'p5'),
    ('p1-p4-p2', 'p4', 'p2'),
    ('p1-p4-p3', 'p4', 'p3'),
    ('p1-p4-p5', 'p4', 'p5'),
    ('p1-p5-p2', 'p5', 'p2'),
    ('p1-p5-p3', 'p5', 'p3'),
    ('p1-p5-p4', 'p5', 'p4'),
]


def load_race_data(conn, start_date, end_date, confidence_list=None):
    conf_filter = ""
    if confidence_list:
        conf_in = ','.join(f"'{c}'" for c in confidence_list)
        conf_filter = f"AND rp1.confidence IN ({conf_in})"

    query = f"""
    SELECT
        r.id          AS race_id,
        r.race_date,
        r.venue_code,
        rp1.pit_number AS p1,
        rp2.pit_number AS p2,
        rp3.pit_number AS p3,
        rp4.pit_number AS p4,
        rp5.pit_number AS p5,
        rp1.confidence AS confidence,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') AS actual_1st,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') AS actual_2nd,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') AS actual_3rd
    FROM races r
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
    WHERE r.race_date >= '{start_date}' AND r.race_date <= '{end_date}'
      {conf_filter}
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') IS NOT NULL
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') IS NOT NULL
    ORDER BY r.race_date
    """
    return pd.read_sql_query(query, conn)


def load_odds(conn, race_ids):
    if len(race_ids) == 0:
        return pd.DataFrame(columns=['race_id', 'combination', 'odds'])
    conn.execute("DROP TABLE IF EXISTS _dd_race_ids")
    conn.execute("CREATE TEMP TABLE _dd_race_ids (race_id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO _dd_race_ids VALUES (?)", [(int(rid),) for rid in race_ids])
    df = pd.read_sql_query(
        "SELECT o.race_id, o.combination, o.odds FROM trifecta_odds o JOIN _dd_race_ids t ON t.race_id = o.race_id WHERE o.odds > 0",
        conn
    )
    return df


def build_combo_df(df_base, df_odds, combo_label, col_2nd, col_3rd):
    df_work = df_base[['race_id', 'venue_code', 'confidence', 'p1', col_2nd, col_3rd,
                         'actual_1st', 'actual_2nd', 'actual_3rd']].copy()
    df_work.columns = ['race_id', 'venue_code', 'confidence', 'p1', 'p_2nd', 'p_3rd',
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
    merged['hit'] = (
        (merged['actual_1st'] == merged['p1']) &
        (merged['actual_2nd'] == merged['p_2nd']) &
        (merged['actual_3rd'] == merged['p_3rd'])
    )
    merged['combo_label'] = combo_label
    return merged


def agg(df):
    if len(df) == 0:
        return {'n': 0, 'hits': 0, 'hit_rate': 0, 'roi': 0, 'profit': 0}
    n = len(df)
    hits = int(df['hit'].sum())
    pay = float((df['hit'] * df['odds'] * 100).sum())
    inv = n * 100
    return {'n': n, 'hits': hits, 'hit_rate': hits/n*100,
            'roi': pay/inv*100 if inv > 0 else 0, 'profit': int(pay - inv)}


def print_venue_breakdown(df_is, df_oos, title, min_n=30):
    """会場別IS/OOS比較"""
    print(f"\n{'='*80}")
    print(f"【{title}】会場別 IS/OOS比較（OOS収支降順, {min_n}件以上）")
    print(f"{'='*80}")
    print(f"  {'会場':<8} | {'IS件数':>5} | {'IS ROI':>7} | {'IS収支':>9} | {'OOS件数':>6} | {'OOS ROI':>8} | {'OOS収支':>9} | 判定")
    print(f"  {'-'*76}")

    rows = []
    for venue_code in sorted(df_is['venue_code'].unique()):
        sub_is  = df_is[df_is['venue_code']  == venue_code]
        sub_oos = df_oos[df_oos['venue_code'] == venue_code]
        a_is  = agg(sub_is)
        a_oos = agg(sub_oos)
        if a_is['n'] < min_n and a_oos['n'] < min_n:
            continue
        rows.append((venue_code, a_is, a_oos))

    rows.sort(key=lambda x: x[2]['profit'], reverse=True)
    for venue_code, a_is, a_oos in rows:
        is_pos  = a_is['roi']  >= 100
        oos_pos = a_oos['roi'] >= 100
        judge = '◎' if (is_pos and oos_pos) else ('○OOS' if oos_pos else ('△IS' if is_pos else '×'))
        mk_is  = '★' if is_pos  else ' '
        mk_oos = '★' if oos_pos else ' '
        vname = VENUE_NAMES.get(venue_code, str(venue_code))
        print(f"  {vname:<8} | {a_is['n']:>5,} | {a_is['roi']:>6.1f}%{mk_is}| {a_is['profit']:>+8,}円 | "
              f"{a_oos['n']:>6,} | {a_oos['roi']:>7.1f}%{mk_oos}| {a_oos['profit']:>+8,}円 | {judge}")


def analyze_combo_in_races(df_base, df_odds, odds_lo, odds_hi, combo_label, col_2nd, col_3rd):
    """指定オッズ帯での組み合わせDFを返す"""
    df_c = build_combo_df(df_base, df_odds, combo_label, col_2nd, col_3rd)
    if len(df_c) == 0:
        return pd.DataFrame()
    return df_c[(df_c['odds'] >= odds_lo) & (df_c['odds'] < odds_hi)].copy()


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("="*80)
    print("有望組み合わせ 深掘り分析")
    print("="*80)

    # データ取得（B以上）
    print("\nIS期間データ取得中（B以上）...")
    df_is  = load_race_data(conn, IS_START, IS_END,  confidence_list=['A','B'])
    odds_is = load_odds(conn, df_is['race_id'].unique())
    print(f"  {len(df_is):,}件")

    print("OOS期間データ取得中（B以上）...")
    df_oos  = load_race_data(conn, OOS_START, OOS_END, confidence_list=['A','B'])
    odds_oos = load_odds(conn, df_oos['race_id'].unique())
    print(f"  {len(df_oos):,}件")

    # ==================================================================
    # Part A: p1-p3-p2 × 50-100倍帯 会場別
    # ==================================================================
    print("\n" + "="*80)
    print("【Part A】p1-p3-p2 × 50-100倍帯 詳細（信頼度B以上）")
    print("前段でOOS ROI 119.8%を記録した組み合わせ")
    print("="*80)

    da_is  = analyze_combo_in_races(df_is,  odds_is,  50, 100, 'p1-p3-p2', 'p3', 'p2')
    da_oos = analyze_combo_in_races(df_oos, odds_oos, 50, 100, 'p1-p3-p2', 'p3', 'p2')
    a_is_total  = agg(da_is)
    a_oos_total = agg(da_oos)
    print(f"  IS通算:  {a_is_total['n']:,}件 / ROI {a_is_total['roi']:.1f}% / {a_is_total['profit']:+,}円")
    print(f"  OOS通算: {a_oos_total['n']:,}件 / ROI {a_oos_total['roi']:.1f}% / {a_oos_total['profit']:+,}円")

    # 信頼度別内訳
    print("\n  信頼度別:")
    for conf in ['A', 'B']:
        sub_is  = da_is[da_is['confidence']  == conf] if len(da_is)  > 0 else pd.DataFrame()
        sub_oos = da_oos[da_oos['confidence'] == conf] if len(da_oos) > 0 else pd.DataFrame()
        ai = agg(sub_is); ao = agg(sub_oos)
        mk = '★' if ao['roi'] >= 100 else ' '
        print(f"    信頼度{conf}: IS {ai['n']:,}件/{ai['roi']:.1f}%/{ai['profit']:+,}円  "
              f"OOS {ao['n']:,}件/{ao['roi']:.1f}%{mk}/{ao['profit']:+,}円")

    print_venue_breakdown(da_is, da_oos, "p1-p3-p2 × 50-100倍帯", min_n=20)

    # ==================================================================
    # Part B: p1-p4-p2 × 100倍〜帯 会場別
    # ==================================================================
    print("\n" + "="*80)
    print("【Part B】p1-p4-p2 × 100倍〜帯 詳細（信頼度B以上）")
    print("前段でOOS ROI 117.6%を記録した組み合わせ")
    print("="*80)

    db_is  = analyze_combo_in_races(df_is,  odds_is,  100, 9999, 'p1-p4-p2', 'p4', 'p2')
    db_oos = analyze_combo_in_races(df_oos, odds_oos, 100, 9999, 'p1-p4-p2', 'p4', 'p2')
    b_is_total  = agg(db_is)
    b_oos_total = agg(db_oos)
    print(f"  IS通算:  {b_is_total['n']:,}件 / ROI {b_is_total['roi']:.1f}% / {b_is_total['profit']:+,}円")
    print(f"  OOS通算: {b_oos_total['n']:,}件 / ROI {b_oos_total['roi']:.1f}% / {b_oos_total['profit']:+,}円")

    # 信頼度別
    print("\n  信頼度別:")
    for conf in ['A', 'B']:
        sub_is  = db_is[db_is['confidence']   == conf] if len(db_is)  > 0 else pd.DataFrame()
        sub_oos = db_oos[db_oos['confidence']  == conf] if len(db_oos) > 0 else pd.DataFrame()
        ai = agg(sub_is); ao = agg(sub_oos)
        mk = '★' if ao['roi'] >= 100 else ' '
        print(f"    信頼度{conf}: IS {ai['n']:,}件/{ai['roi']:.1f}%/{ai['profit']:+,}円  "
              f"OOS {ao['n']:,}件/{ao['roi']:.1f}%{mk}/{ao['profit']:+,}円")

    print_venue_breakdown(db_is, db_oos, "p1-p4-p2 × 100倍〜帯", min_n=20)

    # ==================================================================
    # Part C: 現行条件(B_A1_30_50_8VENUES)レースでの12組み合わせ比較
    # ==================================================================
    print("\n" + "="*80)
    print("【Part C】現行条件(B×A1×30-50×8会場)対象レースでの12組み合わせ比較")
    print("「現行の買い対象レースに対して最良の組み合わせは何か」")
    print("="*80)

    # 現行条件取得
    cond_8v = None
    for c in STANDARD_BET_CONDITIONS:
        if c.get('id') == 'B_A1_30_50_8VENUES':
            cond_8v = c
            break

    if cond_8v is None:
        print("  条件が見つかりません")
    else:
        rids_is  = get_race_ids_for_condition(cursor, cond_8v, IS_START,  IS_END)
        rids_oos = get_race_ids_for_condition(cursor, cond_8v, OOS_START, OOS_END)
        print(f"  現行条件 IS: {len(rids_is)}件 / OOS: {len(rids_oos)}件")

        # 現行条件のレースのみに絞る
        df_is_cond  = df_is[df_is['race_id'].isin(rids_is)]
        df_oos_cond = df_oos[df_oos['race_id'].isin(rids_oos)]
        odds_is_cond  = odds_is[odds_is['race_id'].isin(rids_is)]
        odds_oos_cond = odds_oos[odds_oos['race_id'].isin(rids_oos)]

        print(f"\n  {'組み合わせ':<12} | {'IS件数':>6} | {'IS ROI':>7} | {'IS収支':>9} | {'OOS件数':>6} | {'OOS ROI':>8} | {'OOS収支':>9} | 判定")
        print(f"  {'-'*78}")

        rows_c = []
        for combo_label, col_2nd, col_3rd in COMBINATIONS:
            dc_is  = build_combo_df(df_is_cond,  odds_is_cond,  combo_label, col_2nd, col_3rd)
            dc_oos = build_combo_df(df_oos_cond, odds_oos_cond, combo_label, col_2nd, col_3rd)

            # 30-50倍フィルタ（現行条件のオッズ範囲）
            if len(dc_is)  > 0: dc_is  = dc_is[(dc_is['odds']   >= 30) & (dc_is['odds']   < 50)]
            if len(dc_oos) > 0: dc_oos = dc_oos[(dc_oos['odds'] >= 30) & (dc_oos['odds']  < 50)]

            ai = agg(dc_is); ao = agg(dc_oos)
            rows_c.append((combo_label, ai, ao))

        rows_c.sort(key=lambda x: x[2]['profit'], reverse=True)
        for combo_label, ai, ao in rows_c:
            if ai['n'] < 5 and ao['n'] < 5:
                continue
            is_pos  = ai['roi'] >= 100
            oos_pos = ao['roi'] >= 100
            judge = '◎' if (is_pos and oos_pos) else ('○OOS' if oos_pos else ('△IS' if is_pos else '×'))
            mk_is  = '★' if is_pos  else ' '
            mk_oos = '★' if oos_pos else ' '
            print(f"  {combo_label:<12} | {ai['n']:>6,} | {ai['roi']:>6.1f}%{mk_is}| {ai['profit']:>+8,}円 | "
                  f"{ao['n']:>6,} | {ao['roi']:>7.1f}%{mk_oos}| {ao['profit']:>+8,}円 | {judge}")

    # ==================================================================
    # Part D: p1-p3-p2 × 100倍〜帯（Part Aの高オッズ版）
    # ==================================================================
    print("\n" + "="*80)
    print("【Part D】p1-p3-p2 × 100倍〜帯 詳細（信頼度B以上）")
    print("OOS ROI 142.4%を記録 - サンプル数は少ないが最高ROI")
    print("="*80)

    dd_is  = analyze_combo_in_races(df_is,  odds_is,  100, 9999, 'p1-p3-p2', 'p3', 'p2')
    dd_oos = analyze_combo_in_races(df_oos, odds_oos, 100, 9999, 'p1-p3-p2', 'p3', 'p2')
    d_is_total  = agg(dd_is)
    d_oos_total = agg(dd_oos)
    print(f"  IS通算:  {d_is_total['n']:,}件 / ROI {d_is_total['roi']:.1f}% / {d_is_total['profit']:+,}円")
    print(f"  OOS通算: {d_oos_total['n']:,}件 / ROI {d_oos_total['roi']:.1f}% / {d_oos_total['profit']:+,}円")

    print_venue_breakdown(dd_is, dd_oos, "p1-p3-p2 × 100倍〜帯", min_n=10)

    conn.close()
    print("\n完了")


if __name__ == '__main__':
    main()
