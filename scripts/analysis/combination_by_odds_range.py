# -*- coding: utf-8 -*-
"""
組み合わせ × オッズ帯 × 信頼度 クロス分析

「全組み合わせ赤字」という結果を受けて、
どのオッズ帯・信頼度セグメントで各組み合わせがROI > 100%になるかを探す

目的: 現行条件（30-50倍帯）以外にも有望なポケットがあるか確認
     特にp1-p3-p2等の非標準組み合わせが光るオッズ帯を特定する
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import sqlite3
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")

IS_START  = '2020-01-01'
IS_END    = '2022-12-31'
OOS_START = '2023-01-01'
OOS_END   = '2025-12-31'

# 分析対象の組み合わせ（全12通り）
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

# オッズ帯定義
ODDS_BINS = [
    ( 0,  10, '〜10倍'),
    (10,  20, '10-20倍'),
    (20,  30, '20-30倍'),
    (30,  50, '30-50倍'),
    (50, 100, '50-100倍'),
    (100, 9999, '100倍〜'),
]


def load_race_data(conn, start_date, end_date):
    """全信頼度のレースデータを取得"""
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
    WHERE r.race_date >= '{start_date}'
      AND r.race_date <= '{end_date}'
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') IS NOT NULL
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') IS NOT NULL
    ORDER BY r.race_date
    """
    return pd.read_sql_query(query, conn)


def load_odds(conn, race_ids):
    if len(race_ids) == 0:
        return pd.DataFrame(columns=['race_id', 'combination', 'odds'])
    conn.execute("DROP TABLE IF EXISTS _cbor_race_ids")
    conn.execute("CREATE TEMP TABLE _cbor_race_ids (race_id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO _cbor_race_ids VALUES (?)", [(int(rid),) for rid in race_ids])
    query = """
    SELECT o.race_id, o.combination, o.odds
    FROM trifecta_odds o
    JOIN _cbor_race_ids t ON t.race_id = o.race_id
    WHERE o.odds > 0
    """
    return pd.read_sql_query(query, conn)


def build_combo_df(df_base, df_odds, combo_label, col_2nd, col_3rd):
    """1つの組み合わせについてオッズ・的中フラグを付与したDFを返す"""
    df_work = df_base[['race_id', 'confidence', 'p1', col_2nd, col_3rd,
                         'actual_1st', 'actual_2nd', 'actual_3rd']].copy()
    df_work.columns = ['race_id', 'confidence', 'p1', 'p_2nd', 'p_3rd',
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


def aggregate(df):
    """的中フラグ+オッズDFから収支サマリーを返す"""
    if len(df) == 0:
        return {'n': 0, 'hits': 0, 'hit_rate': 0, 'roi': 0, 'profit': 0}
    n    = len(df)
    hits = int(df['hit'].sum())
    pay  = float((df['hit'] * df['odds'] * 100).sum())
    inv  = n * 100
    return {
        'n':        n,
        'hits':     hits,
        'hit_rate': hits / n * 100,
        'roi':      pay / inv * 100 if inv > 0 else 0,
        'profit':   int(pay - inv),
    }


def main():
    conn = sqlite3.connect(DB_PATH)

    print("="*80)
    print("組み合わせ × オッズ帯 × 信頼度 クロス分析")
    print("IS=2020-2022 / OOS=2023-2025 / 全信頼度 / 100円固定")
    print("="*80)

    print("\nIS期間データ取得中...")
    df_is = load_race_data(conn, IS_START, IS_END)
    odds_is = load_odds(conn, df_is['race_id'].unique())
    print(f"  {len(df_is):,}件")

    print("OOS期間データ取得中...")
    df_oos = load_race_data(conn, OOS_START, OOS_END)
    odds_oos = load_odds(conn, df_oos['race_id'].unique())
    print(f"  {len(df_oos):,}件")

    # ==================================================================
    # Part 1: オッズ帯 × 組み合わせ（信頼度B以上に絞る）
    # ==================================================================
    print("\n" + "="*80)
    print("【Part 1】オッズ帯 × 組み合わせ（信頼度B以上）- IS/OOS比較")
    print("ROI >= 100% の場合 ★ を表示")
    print("="*80)

    df_is_b  = df_is[df_is['confidence'].isin(['A', 'B'])]
    df_oos_b = df_oos[df_oos['confidence'].isin(['A', 'B'])]
    oids_is_b  = odds_is[odds_is['race_id'].isin(df_is_b['race_id'])]
    oids_oos_b = odds_oos[odds_oos['race_id'].isin(df_oos_b['race_id'])]

    for odds_lo, odds_hi, odds_label in ODDS_BINS:
        print(f"\n--- オッズ帯: {odds_label} ---")
        print(f"  {'組み合わせ':<12} | {'IS件数':>6} | {'IS ROI':>7} | {'IS収支':>10} | {'OOS件数':>7} | {'OOS ROI':>8} | {'OOS収支':>10} | 判定")
        print(f"  {'-'*82}")

        rows = []
        for combo_label, col_2nd, col_3rd in COMBINATIONS:
            df_c_is  = build_combo_df(df_is_b,  oids_is_b,  combo_label, col_2nd, col_3rd)
            df_c_oos = build_combo_df(df_oos_b, oids_oos_b, combo_label, col_2nd, col_3rd)

            # オッズ帯フィルタ
            if len(df_c_is) > 0:
                df_c_is = df_c_is[(df_c_is['odds'] >= odds_lo) & (df_c_is['odds'] < odds_hi)]
            if len(df_c_oos) > 0:
                df_c_oos = df_c_oos[(df_c_oos['odds'] >= odds_lo) & (df_c_oos['odds'] < odds_hi)]

            agg_is  = aggregate(df_c_is)
            agg_oos = aggregate(df_c_oos)

            if agg_is['n'] < 30 and agg_oos['n'] < 30:
                continue  # サンプル少なすぎは省略

            rows.append((combo_label, agg_is, agg_oos))

        # OOS ROI降順でソート
        rows.sort(key=lambda x: x[2]['roi'], reverse=True)

        for combo_label, agg_is, agg_oos in rows:
            is_pos  = agg_is['roi']  >= 100
            oos_pos = agg_oos['roi'] >= 100
            if is_pos and oos_pos:
                judge = '◎'
            elif oos_pos:
                judge = '○OOS'
            elif is_pos:
                judge = '△IS'
            else:
                judge = '×'
            mk_is  = '★' if is_pos  else ' '
            mk_oos = '★' if oos_pos else ' '
            print(f"  {combo_label:<12} | {agg_is['n']:>6,} | {agg_is['roi']:>6.1f}%{mk_is}| {agg_is['profit']:>+9,}円 | "
                  f"{agg_oos['n']:>7,} | {agg_oos['roi']:>7.1f}%{mk_oos}| {agg_oos['profit']:>+9,}円 | {judge}")

    # ==================================================================
    # Part 2: 信頼度 × 組み合わせ（オッズ帯 30-50固定）
    # ==================================================================
    print("\n" + "="*80)
    print("【Part 2】信頼度 × 組み合わせ（オッズ帯30-50倍固定）- IS/OOS比較")
    print("現行条件（B×A1×30-50）のオッズ帯で信頼度別に見る")
    print("="*80)

    for conf in ['A', 'B', 'C', 'D']:
        df_is_c  = df_is[df_is['confidence'] == conf]
        df_oos_c = df_oos[df_oos['confidence'] == conf]
        oids_is_c  = odds_is[odds_is['race_id'].isin(df_is_c['race_id'])]
        oids_oos_c = odds_oos[odds_oos['race_id'].isin(df_oos_c['race_id'])]

        print(f"\n--- 信頼度{conf}（IS:{len(df_is_c):,}件 / OOS:{len(df_oos_c):,}件） ---")
        print(f"  {'組み合わせ':<12} | {'IS件数':>6} | {'IS ROI':>7} | {'IS収支':>9} | {'OOS件数':>7} | {'OOS ROI':>8} | {'OOS収支':>9} | 判定")
        print(f"  {'-'*80}")

        rows = []
        for combo_label, col_2nd, col_3rd in COMBINATIONS:
            df_c_is  = build_combo_df(df_is_c,  oids_is_c,  combo_label, col_2nd, col_3rd)
            df_c_oos = build_combo_df(df_oos_c, oids_oos_c, combo_label, col_2nd, col_3rd)

            # 30-50倍フィルタ
            if len(df_c_is) > 0:
                df_c_is = df_c_is[(df_c_is['odds'] >= 30) & (df_c_is['odds'] < 50)]
            if len(df_c_oos) > 0:
                df_c_oos = df_c_oos[(df_c_oos['odds'] >= 30) & (df_c_oos['odds'] < 50)]

            agg_is  = aggregate(df_c_is)
            agg_oos = aggregate(df_c_oos)
            rows.append((combo_label, agg_is, agg_oos))

        rows.sort(key=lambda x: x[2]['roi'], reverse=True)

        for combo_label, agg_is, agg_oos in rows:
            if agg_is['n'] < 10 and agg_oos['n'] < 10:
                continue
            is_pos  = agg_is['roi']  >= 100
            oos_pos = agg_oos['roi'] >= 100
            judge = '◎' if (is_pos and oos_pos) else ('○OOS' if oos_pos else ('△IS' if is_pos else '×'))
            mk_is  = '★' if is_pos  else ' '
            mk_oos = '★' if oos_pos else ' '
            print(f"  {combo_label:<12} | {agg_is['n']:>6,} | {agg_is['roi']:>6.1f}%{mk_is}| {agg_is['profit']:>+8,}円 | "
                  f"{agg_oos['n']:>7,} | {agg_oos['roi']:>7.1f}%{mk_oos}| {agg_oos['profit']:>+8,}円 | {judge}")

    conn.close()
    print("\n完了")


if __name__ == '__main__':
    main()
