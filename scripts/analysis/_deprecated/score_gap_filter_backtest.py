# -*- coding: utf-8 -*-
"""
案C: スコア差フィルタ バックテスト
B×A1×30-50×8会場条件（元のH2: p3:200円+p4:100円）に
スコア差閾値フィルタを適用した場合の収支を比較する

戦略バリエーション:
  現行H2     : p3(200) + p4(100) = 300円/レース（常時）
  閾値X_A    : 差<X → p3(200)+p4(100) / 差>=X → p3(200)のみ（100円節約）
  閾値X_B    : 差<X → p3(200)+p4(100) / 差>=X → p3(300)（100円をp3に移動）
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

DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")

# 元のH2条件パラメータ（use_pattern_h=Trueの状態）
ORIGINAL_H2_COND = {
    'id': 'B_A1_30_50_8VENUES_H2',
    'confidence': 'B',
    'c1_rank': ['A1'],
    'odds_min': 30,
    'odds_max': 50,
    'venue_filter': [2, 3, 6, 8, 12, 9, 17, 19],
    'month_exclude': [4],
    'use_pattern_h': True,
    'advance_before_match': True,
}

YEARS = [2020, 2021, 2022, 2023, 2024, 2025]


def load_race_data(conn, race_ids, cond):
    """対象レースのスコア・オッズ・結果を取得"""
    if not race_ids:
        return pd.DataFrame()

    conn.execute("DROP TABLE IF EXISTS _sgf_race_ids")
    conn.execute("CREATE TEMP TABLE _sgf_race_ids (race_id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO _sgf_race_ids VALUES (?)", [(rid,) for rid in race_ids])

    odds_min = cond['odds_min']
    odds_max = cond['odds_max']

    query = f"""
    SELECT
        r.id AS race_id,
        r.race_date,
        rp3.pit_number AS p3_pit,
        rp4.pit_number AS p4_pit,
        rp3.total_score AS p3_score,
        rp4.total_score AS p4_score,
        (rp3.total_score - rp4.total_score) AS score_diff,
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
        -- p1/p2のpit番号（的中判定に必要）
        rp1.pit_number AS p1_pit,
        rp2.pit_number AS p2_pit,
        -- 実際の着順
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') AS actual_1st,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') AS actual_2nd,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') AS actual_3rd
    FROM races r
    JOIN _sgf_race_ids bt ON bt.race_id = r.id
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    """
    df = pd.read_sql_query(query, conn)

    # オッズフィルタ（p3 OR p4がオッズ範囲内）
    df['p3_in_range'] = (df['odds_p3'] >= odds_min) & (df['odds_p3'] < odds_max)
    df['p4_in_range'] = (df['odds_p4'] >= odds_min) & (df['odds_p4'] < odds_max)
    df = df[df['p3_in_range'] | df['p4_in_range']].copy()

    # 的中フラグ（三連単: p1-p2-p3 or p1-p2-p4 が全て一致した場合のみ）
    df['p12_hit'] = (df['actual_1st'] == df['p1_pit']) & (df['actual_2nd'] == df['p2_pit'])
    df['p3_is_3rd'] = df['p12_hit'] & (df['actual_3rd'] == df['p3_pit']) & df['p3_in_range']
    df['p4_is_3rd'] = df['p12_hit'] & (df['actual_3rd'] == df['p4_pit']) & df['p4_in_range']

    return df


def calc_strategy(df, threshold, mode, label):
    """
    mode='save'    : 差>=閾値 → p4をスキップ（100円節約）
    mode='redirect': 差>=閾値 → p3に300円（100円をp3に移動）
    """
    rows = []
    for _, row in df.iterrows():
        gap_large = row['score_diff'] >= threshold

        # p3の購入
        p3_bet = 200
        if mode == 'redirect' and gap_large:
            p3_bet = 300

        # p4の購入
        p4_bet = 0 if gap_large else 100

        inv_p3 = p3_bet if row['p3_in_range'] else 0
        inv_p4 = p4_bet if row['p4_in_range'] else 0
        investment = inv_p3 + inv_p4
        if investment == 0:
            continue

        pay_p3 = row['odds_p3'] * p3_bet if row['p3_is_3rd'] else 0
        pay_p4 = row['odds_p4'] * p4_bet if row['p4_is_3rd'] else 0
        payout = pay_p3 + pay_p4

        rows.append({
            'race_date': row['race_date'],
            'investment': investment,
            'payout': payout,
            'hit': (row['p3_is_3rd'] or row['p4_is_3rd']),
        })

    if not rows:
        return None
    sub = pd.DataFrame(rows)
    inv = sub['investment'].sum()
    pay = sub['payout'].sum()
    hits = sub['hit'].sum()
    bets = len(sub)
    roi = pay / inv * 100 if inv > 0 else 0
    profit = pay - inv
    hit_rate = hits / bets * 100 if bets > 0 else 0
    return {'label': label, 'bets': bets, 'hits': int(hits),
            'hit_rate': hit_rate, 'investment': int(inv),
            'payout': int(pay), 'roi': roi, 'profit': int(profit)}


def calc_baseline_h2(df):
    """現行H2: p3(200)+p4(100) 常時"""
    inv_p3 = df['p3_in_range'].astype(int) * 200
    inv_p4 = df['p4_in_range'].astype(int) * 100
    investment = (inv_p3 + inv_p4).sum()
    pay_p3 = (df['p3_is_3rd'] * df['odds_p3'] * 200).sum()
    pay_p4 = (df['p4_is_3rd'] * df['odds_p4'] * 100).sum()
    payout = pay_p3 + pay_p4
    bet_mask = (inv_p3 + inv_p4) > 0
    bets = bet_mask.sum()
    hits = (df['p3_is_3rd'] | df['p4_is_3rd']).sum()
    roi = payout / investment * 100 if investment > 0 else 0
    profit = payout - investment
    return {'label': '現行H2(200/100)', 'bets': int(bets), 'hits': int(hits),
            'hit_rate': hits / bets * 100 if bets > 0 else 0,
            'investment': int(investment), 'payout': int(payout),
            'roi': roi, 'profit': int(profit)}


def print_result(res):
    if res is None:
        return
    print(f"  {res['label']:<30} | {res['bets']:>5}件 | {res['roi']:>6.1f}% | {res['profit']:>+10,}円 | 的中率{res['hit_rate']:.1f}%")


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 70)
    print("案C スコア差フィルタ バックテスト")
    print("B×A1×30-50×8会場 元H2条件 (2020-2025)")
    print("=" * 70)

    # 年度別レースID取得
    race_ids_by_year = {}
    all_race_ids = set()
    for year in YEARS:
        rids = get_race_ids_for_condition(
            cursor, ORIGINAL_H2_COND,
            start_date=f'{year}-01-01',
            end_date=f'{year+1}-01-01'
        )
        race_ids_by_year[year] = rids
        all_race_ids |= rids
        print(f"  {year}年: {len(rids)}件")
    print(f"  合計: {len(all_race_ids)}件")

    # 全データ取得
    print("\nデータ取得中...")
    df_all = load_race_data(conn, all_race_ids, ORIGINAL_H2_COND)
    df_all['year'] = df_all['race_date'].str[:4].astype(int)
    print(f"  投資対象レース: {len(df_all)}件")

    # スコア差の分布確認
    print(f"\n  スコア差の分布（p3_score - p4_score）:")
    for lo, hi, lb in [(-999,5,'<5'),(5,10,'5-10'),(10,15,'10-15'),(15,999,'15+')]:
        n = ((df_all['score_diff'] >= lo) & (df_all['score_diff'] < hi)).sum()
        print(f"    差{lb}: {n}件 ({n/len(df_all)*100:.1f}%)")

    # ============================================================
    # 6年間通算 比較
    # ============================================================
    print("\n" + "=" * 70)
    print("【6年間通算比較（2020-2025）】")
    print("=" * 70)
    print(f"  {'戦略':<30} | {'件数':>5} | {'ROI':>6} | {'収支':>10} | 的中率")
    print("  " + "-" * 65)

    baseline = calc_baseline_h2(df_all)
    print_result(baseline)

    thresholds = [5, 10, 15, 20]
    for th in thresholds:
        for mode, mode_label in [('save', '節約'), ('redirect', 'p3移動')]:
            label = f"差<{th:2d}→H2 / 差>={th:2d}→p3({mode_label})"
            res = calc_strategy(df_all, th, mode, label)
            print_result(res)

    # ============================================================
    # 年度別比較（閾値10点、saveモードのみ詳細）
    # ============================================================
    print("\n" + "=" * 70)
    print("【年度別比較】")
    print("=" * 70)

    for mode, mode_label in [('save', '節約'), ('redirect', 'p3移動')]:
        label = f"差< 5→H2 / 差>= 5→({mode_label})"
        print(f"\n戦略: {label}")
        print(f"  {'年度'} | {'H2件数':>6} | {'H2 ROI':>7} | {'H2収支':>9} | {'filter件数':>8} | {'filter ROI':>9} | {'filter収支':>9} | {'差分':>8}")
        print("  " + "-" * 80)

        total_profit_h2 = 0
        total_profit_f = 0
        for year in YEARS:
            df_y = df_all[df_all['year'] == year].copy()
            if len(df_y) == 0:
                continue
            h2 = calc_baseline_h2(df_y)
            flt = calc_strategy(df_y, 5, mode, '')
            diff = flt['profit'] - h2['profit'] if flt else 0
            total_profit_h2 += h2['profit']
            total_profit_f += flt['profit'] if flt else 0
            mark_h2 = '○' if h2['profit'] > 0 else '×'
            mark_f  = '○' if flt and flt['profit'] > 0 else '×'
            print(f"  {year} | {h2['bets']:>5}{mark_h2} | {h2['roi']:>6.1f}% | {h2['profit']:>+8,}円 | "
                  f"{flt['bets'] if flt else 0:>6} {mark_f} | {flt['roi'] if flt else 0:>8.1f}% | "
                  f"{flt['profit'] if flt else 0:>+8,}円 | {diff:>+7,}円")
        print(f"  合計: H2={total_profit_h2:+,}円 / filter={total_profit_f:+,}円 / 差={total_profit_f-total_profit_h2:+,}円")

    # ============================================================
    # スコア差閾値別 p4の貢献分析
    # ============================================================
    print("\n" + "=" * 70)
    print("【スコア差閾値別 p4貢献分析（スキップ対象の収益インパクト）】")
    print("=" * 70)
    print(f"  {'閾値':>4} | {'スキップ件数':>8} | {'p4率':>6} | {'p4 ROI':>7} | {'スキップによる収益影響':>16}")
    print("  " + "-" * 60)
    for th in thresholds:
        skip = df_all[df_all['score_diff'] >= th]
        n = skip['p4_in_range'].sum()  # p4が範囲内の件数
        if n == 0:
            continue
        p4_sub = skip[skip['p4_in_range']]
        hits = p4_sub['p4_is_3rd'].sum()
        inv = int(n * 100)
        pay = int((p4_sub['p4_is_3rd'] * p4_sub['odds_p4'] * 100).sum())
        roi = pay / inv * 100 if inv > 0 else 0
        impact = pay - inv  # スキップすることで失う利益（正なら損失）
        print(f"  {th:>4} | {n:>8} | {hits/n*100:>5.1f}% | {roi:>6.1f}% | {impact:>+16,}円")

    conn.close()
    print("\n完了")


if __name__ == '__main__':
    main()
