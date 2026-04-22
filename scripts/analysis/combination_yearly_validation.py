# -*- coding: utf-8 -*-
"""
有望組み合わせの年度別収支検証

深掘り分析で判明した有望候補を年度別(2020-2025)に検証する

対象:
  1. p1-p4-p2 × 100倍〜 × 信頼度A  (OOS ROI 140.2%, 1472件)
  2. p1-p3-p2 × 50-100倍 × 信頼度B (OOS ROI 125.8%, 1752件)
  3. p1-p3-p2 × 50-100倍 × 信頼度A (OOS ROI 110.2%, 1099件)
  4. 現行条件p1-p4-p2(IS 107.8%/OOS 108.7%)の年度別確認
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

YEARS = [2020, 2021, 2022, 2023, 2024, 2025]


def load_race_data(conn, start_date, end_date, confidence_list=None):
    conf_filter = ""
    if confidence_list:
        conf_in = ','.join(f"'{c}'" for c in confidence_list)
        conf_filter = f"AND rp1.confidence IN ({conf_in})"
    query = f"""
    SELECT
        r.id AS race_id, r.race_date, r.venue_code,
        rp1.pit_number AS p1, rp2.pit_number AS p2,
        rp3.pit_number AS p3, rp4.pit_number AS p4, rp5.pit_number AS p5,
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
    """
    return pd.read_sql_query(query, conn)


def load_odds(conn, race_ids):
    if len(race_ids) == 0:
        return pd.DataFrame(columns=['race_id', 'combination', 'odds'])
    conn.execute("DROP TABLE IF EXISTS _yv_race_ids")
    conn.execute("CREATE TEMP TABLE _yv_race_ids (race_id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO _yv_race_ids VALUES (?)", [(int(rid),) for rid in race_ids])
    return pd.read_sql_query(
        "SELECT o.race_id, o.combination, o.odds FROM trifecta_odds o JOIN _yv_race_ids t ON t.race_id = o.race_id WHERE o.odds > 0",
        conn
    )


def build_and_filter(df_base, df_odds, col_2nd, col_3rd, odds_lo, odds_hi):
    """組み合わせDF作成 + オッズ帯フィルタ"""
    df_work = df_base[['race_id', 'race_date', 'venue_code', 'confidence',
                         'p1', col_2nd, col_3rd,
                         'actual_1st', 'actual_2nd', 'actual_3rd']].copy()
    df_work.columns = ['race_id', 'race_date', 'venue_code', 'confidence',
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


def print_yearly(df, title):
    """年度別収支表示"""
    print(f"\n{'='*70}")
    print(f"【{title}】年度別収支")
    print(f"{'='*70}")
    print(f"  {'年度'} | {'件数':>5} | {'的中':>4} | {'的中率':>6} | {'ROI':>7} | {'収支':>10} | 判定")
    print(f"  {'-'*58}")

    total_inv = 0; total_pay = 0; black = 0
    for year in YEARS:
        sub = df[df['year'] == year]
        if len(sub) == 0:
            print(f"  {year} |     0 |    0 |    0.0% |    0.0% |          0円 |   ")
            continue
        n = len(sub)
        hits = int(sub['hit'].sum())
        pay = float((sub['hit'] * sub['odds'] * 100).sum())
        inv = n * 100
        roi = pay / inv * 100 if inv > 0 else 0
        profit = int(pay - inv)
        mark = '○' if profit > 0 else '×'
        if profit > 0:
            black += 1
        total_inv += inv; total_pay += pay
        print(f"  {year} | {n:>5} | {hits:>4} | {hits/n*100:>5.1f}% | {roi:>6.1f}% | {profit:>+10,}円 | {mark}")

    total_profit = int(total_pay - total_inv)
    total_roi = total_pay / total_inv * 100 if total_inv > 0 else 0
    print(f"  {'合計':<4} | {total_inv//100:>5} | - | -     | {total_roi:>6.1f}% | {total_profit:>+10,}円 | {black}/6年黒字")


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("="*70)
    print("有望組み合わせ 年度別収支検証（2020-2025）")
    print("="*70)

    # 6年分データ一括取得
    print("\n全期間データ取得中...")
    df_all = load_race_data(conn, '2020-01-01', '2025-12-31')
    odds_all = load_odds(conn, df_all['race_id'].unique())
    print(f"  {len(df_all):,}件")

    # ==================================================================
    # 候補1: p1-p4-p2 × 100倍〜 × 信頼度A
    # ==================================================================
    df_a = df_all[df_all['confidence'] == 'A']
    odds_a = odds_all[odds_all['race_id'].isin(df_a['race_id'])]

    df_c1 = build_and_filter(df_a, odds_a, 'p4', 'p2', 100, 9999)
    print_yearly(df_c1, "候補1: p1-p4-p2 × 100倍〜 × 信頼度A")
    if len(df_c1) > 0:
        n = len(df_c1); hits = int(df_c1['hit'].sum())
        pay = float((df_c1['hit'] * df_c1['odds'] * 100).sum()); inv = n * 100
        print(f"  ※ 6年総計: {n:,}件 / ROI {pay/inv*100:.1f}% / {int(pay-inv):+,}円 / 黒字年-/6年")

    # ==================================================================
    # 候補2: p1-p3-p2 × 50-100倍 × 信頼度B
    # ==================================================================
    df_b = df_all[df_all['confidence'] == 'B']
    odds_b = odds_all[odds_all['race_id'].isin(df_b['race_id'])]

    df_c2 = build_and_filter(df_b, odds_b, 'p3', 'p2', 50, 100)
    print_yearly(df_c2, "候補2: p1-p3-p2 × 50-100倍 × 信頼度B")

    # ==================================================================
    # 候補3: p1-p3-p2 × 50-100倍 × 信頼度A
    # ==================================================================
    df_c3 = build_and_filter(df_a, odds_a, 'p3', 'p2', 50, 100)
    print_yearly(df_c3, "候補3: p1-p3-p2 × 50-100倍 × 信頼度A")

    # ==================================================================
    # 候補4: p1-p3-p2 × 50-100倍 × 信頼度A+B合算
    # ==================================================================
    df_ab = df_all[df_all['confidence'].isin(['A', 'B'])]
    odds_ab = odds_all[odds_all['race_id'].isin(df_ab['race_id'])]

    df_c4 = build_and_filter(df_ab, odds_ab, 'p3', 'p2', 50, 100)
    print_yearly(df_c4, "候補4: p1-p3-p2 × 50-100倍 × 信頼度A+B（IS/OOS通算確認）")

    # ==================================================================
    # 候補5: 現行条件(B×A1×30-50×8会場) × p1-p4-p2（年度別）
    # ==================================================================
    cond_8v = next((c for c in STANDARD_BET_CONDITIONS if c.get('id') == 'B_A1_30_50_8VENUES'), None)
    if cond_8v:
        all_rids = set()
        yearly_rids = {}
        for year in YEARS:
            rids = get_race_ids_for_condition(
                cursor, cond_8v,
                start_date=f'{year}-01-01',
                end_date=f'{year+1}-01-01'
            )
            yearly_rids[year] = rids
            all_rids |= rids

        df_8v = df_all[df_all['race_id'].isin(all_rids)]
        odds_8v = odds_all[odds_all['race_id'].isin(all_rids)]

        print(f"\n{'='*70}")
        print("【現行条件 B×A1×30-50×8会場 内での各組み合わせ 年度別】")
        print(f"{'='*70}")

        for combo_label, col_2nd, col_3rd in [
            ('p1-p2-p3', 'p2', 'p3'),  # 現行メイン
            ('p1-p4-p2', 'p4', 'p2'),  # 新候補
            ('p1-p5-p2', 'p5', 'p2'),  # 新候補OOS正
            ('p1-p2-p4', 'p2', 'p4'),  # 現行サブ（現状）
        ]:
            df_combo = build_and_filter(df_8v, odds_8v, col_2nd, col_3rd, 30, 50)
            if len(df_combo) == 0:
                continue
            print_yearly(df_combo, f"現行条件 × {combo_label}")

    conn.close()
    print("\n完了")


if __name__ == '__main__':
    main()
