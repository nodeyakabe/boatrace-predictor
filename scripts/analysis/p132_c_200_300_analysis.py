# -*- coding: utf-8 -*-
"""
p1-p3-p2 × C信頼度 × 200-300倍 深掘り分析
A_P142_100_300採用時と同じ手順で根拠を確認する

検証フィルタ:
  F1: スコア帯（C信頼度のスコア分布に合わせて動的確認）
  F2: 月別除外（的中0件の月があるか）
  F3: オッズ帯精細化（200-250倍 vs 250-300倍）
  複合: 有望フィルタの組み合わせ
  根拠分析: 教科書展開率（p1-p2-p3）との比較
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import sqlite3
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")


# ============================================================
# データ取得
# ============================================================

def load_base(conn):
    """p1-p3-p2 × C信頼度 × 200-300倍 全データ"""
    query = """
    SELECT
        r.id AS race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
        CAST(strftime('%Y', r.race_date) AS INTEGER) AS year,
        CAST(strftime('%m', r.race_date) AS INTEGER) AS month,
        rp1.pit_number AS p1,
        rp2.pit_number AS p2,
        rp3.pit_number AS p3,
        rp1.total_score AS p1_score,
        t.odds AS odds,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') AS actual_1st,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') AS actual_2nd,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') AS actual_3rd
    FROM races r
    JOIN race_predictions rp1 ON r.id = rp1.race_id
        AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id
        AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id
        AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN trifecta_odds t ON r.id = t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                         || CAST(rp3.pit_number AS TEXT) || '-'
                         || CAST(rp2.pit_number AS TEXT)
    WHERE rp1.confidence = 'C'
      AND t.odds >= 200 AND t.odds < 300
      AND r.race_date >= '2020-01-01'
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') IS NOT NULL
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') IS NOT NULL
    ORDER BY r.race_date
    """
    df = pd.read_sql_query(query, conn)
    df['hit'] = (
        (df['actual_1st'] == df['p1']) &
        (df['actual_2nd'] == df['p3']) &
        (df['actual_3rd'] == df['p2'])
    )
    df['period'] = df['year'].apply(lambda y: 'IS' if y <= 2022 else 'OOS')
    return df


def calc(sub):
    n = len(sub)
    if n == 0:
        return 0, 0, 0.0, 0
    h = int(sub['hit'].sum())
    pay = float((sub['hit'] * sub['odds'] * 100).sum())
    roi = pay / (n * 100) * 100
    profit = int(pay - n * 100)
    return n, h, roi, profit


def print_is_oos(label, df, indent=4):
    sp = ' ' * indent
    is_d  = df[df['period'] == 'IS']
    oos_d = df[df['period'] == 'OOS']
    ni, hi, roi_i, pr_i = calc(is_d)
    no, ho, roi_o, pr_o = calc(oos_d)
    mi = '★' if roi_i >= 100 else ' '
    mo = '★' if roi_o >= 100 else ' '
    print(f"{sp}{label:>30}  IS:{ni:>5}件 ROI{roi_i:>6.1f}%{mi} {pr_i:>+9,}  "
          f"OOS:{no:>5}件 ROI{roi_o:>6.1f}%{mo} {pr_o:>+9,}")


def print_year_breakdown(label, df, indent=4):
    sp = ' ' * indent
    n_all, h_all, roi_all, pr_all = calc(df)
    by_year = sum(1 for y in range(2020, 2026) if calc(df[df['year'] == y])[3] > 0)
    print(f"\n{sp}▼ {label}")
    print(f"{sp}  合計: {n_all}件 / {h_all}的中 / ROI {roi_all:.1f}% / {pr_all:+,}円 / {by_year}/6年黒字")
    print(f"{sp}  {'年':>5} | {'件数':>5} | {'的中':>4} | {'ROI':>7} | {'収支':>10}")
    for year in range(2020, 2026):
        sub = df[df['year'] == year]
        n, h, roi, pr = calc(sub)
        mark = '○' if pr > 0 else ('×' if n > 0 else '-')
        print(f"{sp}  {year} | {n:>5} | {h:>4} | {roi:>6.1f}% | {pr:>+10,}円 | {mark}")


def main():
    conn = sqlite3.connect(DB_PATH)
    sep = '=' * 74

    print(sep)
    print("  p1-p3-p2 × C信頼度 × 200-300倍  深掘り分析")
    print("  IS=2020-2022 / OOS=2023-2025")
    print(sep)

    df = load_base(conn)
    n_all, h_all, roi_all, pr_all = calc(df)
    print(f"\nベースデータ: {n_all:,}件 / {h_all}的中 / ROI {roi_all:.1f}% / {pr_all:+,}円")
    print(f"スコア分布: min={df['p1_score'].min():.0f} / 中央値={df['p1_score'].median():.0f} / max={df['p1_score'].max():.0f}")
    print()
    print_is_oos('ベースライン（フィルタなし）', df)

    # ================================================================
    # 根拠分析1: C信頼度での教科書展開率（p1-p2-p3）とスコア帯の関係
    # ================================================================
    print(f"\n{sep}")
    print("【根拠分析1】C信頼度 スコア帯別 教科書展開率（p1-p2-p3の実現率）")
    print("  ※ 教科書率が低い → p3が2着に入る余地が多い → p1-p3-p2の的中余地あり")
    print(sep)

    score_query = """
    SELECT
        rp1.total_score AS score,
        CAST(strftime('%Y', r.race_date) AS INTEGER) AS year,
        rp1.pit_number AS p1, rp2.pit_number AS p2, rp3.pit_number AS p3,
        (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') AS a1,
        (SELECT pit_number FROM results WHERE race_id=r.id AND rank='2') AS a2,
        (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') AS a3
    FROM races r
    JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
    JOIN race_predictions rp2 ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
    JOIN race_predictions rp3 ON r.id=rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
    WHERE rp1.confidence = 'C'
      AND r.race_date >= '2020-01-01'
      AND (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') IS NOT NULL
    """
    df_score = pd.read_sql_query(score_query, conn)
    df_score['p1_hit']   = (df_score['a1'] == df_score['p1'])
    df_score['p123_hit'] = ((df_score['a1'] == df_score['p1']) &
                            (df_score['a2'] == df_score['p2']) &
                            (df_score['a3'] == df_score['p3']))
    df_score['p132_hit'] = ((df_score['a1'] == df_score['p1']) &
                            (df_score['a2'] == df_score['p3']) &  # p3が2着
                            (df_score['a3'] == df_score['p2']))   # p2が3着
    df_score['period'] = df_score['year'].apply(lambda y: 'IS' if y <= 2022 else 'OOS')

    print(f"  {'スコア帯':>10} | {'件数':>7} | {'1着的中率':>8} | {'教科書率p1p2p3':>13} | {'p1p3p2率':>9} | {'IS 教科書':>9} | {'OOS 教科書':>10}")
    print(f"  {'-'*75}")
    for lo in range(44, 111, 10):
        hi = lo + 10
        sub = df_score[(df_score['score'] >= lo) & (df_score['score'] < hi)]
        if len(sub) < 100:
            continue
        p1r   = sub['p1_hit'].mean() * 100
        p123r = sub['p123_hit'].mean() * 100
        p132r = sub['p132_hit'].mean() * 100
        is_r  = sub[sub['period']=='IS']['p123_hit'].mean() * 100
        oos_r = sub[sub['period']=='OOS']['p123_hit'].mean() * 100
        print(f"  {lo:>3}-{hi:<3}点   | {len(sub):>7,} | {p1r:>7.1f}% | {p123r:>12.1f}% | {p132r:>8.2f}% | {is_r:>8.1f}% | {oos_r:>9.1f}%")

    # ================================================================
    # F1: スコア帯フィルタ（200-300倍 × C信頼度）
    # ================================================================
    print(f"\n{sep}")
    print("【F1】スコア帯別 IS/OOS（200-300倍 × C信頼度）")
    print(sep)
    for lo in range(44, 111, 10):
        hi = lo + 10
        sub = df[(df['p1_score'] >= lo) & (df['p1_score'] < hi)]
        if len(sub) < 30:
            continue
        print_is_oos(f'スコア{lo}-{hi}点', sub)

    # 有望スコア帯の年度別
    print(f"\n  【F1 有望スコア帯 年度別詳細】")
    candidates_score = []
    for lo in range(44, 111, 10):
        hi = lo + 10
        sub = df[(df['p1_score'] >= lo) & (df['p1_score'] < hi)]
        if len(sub) < 30:
            continue
        is_s = sub[sub['period']=='IS']; oos_s = sub[sub['period']=='OOS']
        ni, _, roi_i, _ = calc(is_s); no, _, roi_o, _ = calc(oos_s)
        if ni >= 20 and no >= 20 and roi_i >= 100 and roi_o >= 100:
            candidates_score.append((lo, hi, sub))
    for lo, hi, sub in candidates_score:
        print_year_breakdown(f'スコア{lo}-{hi}点 × 200-300倍', sub)
    if not candidates_score:
        # IS/OOS片方だけでも高いもの上位3つ
        tops = []
        for lo in range(44, 111, 10):
            hi = lo + 10
            sub = df[(df['p1_score'] >= lo) & (df['p1_score'] < hi)]
            if len(sub) < 30:
                continue
            ni, _, roi_i, _ = calc(sub[sub['period']=='IS'])
            no, _, roi_o, _ = calc(sub[sub['period']=='OOS'])
            if ni >= 15 and no >= 15:
                tops.append((lo, hi, sub, (roi_i+roi_o)/2))
        tops.sort(key=lambda x: x[3], reverse=True)
        for lo, hi, sub, _ in tops[:3]:
            print_year_breakdown(f'スコア{lo}-{hi}点 × 200-300倍（参考）', sub)

    # ================================================================
    # F2: 月別除外
    # ================================================================
    print(f"\n{sep}")
    print("【F2】月別 的中・収益 分布（除外候補を探す）")
    print(sep)
    print(f"  {'月':>4} | {'件数':>5} | {'的中':>4} | {'的中率':>6} | {'ROI':>7} | {'収支':>10} | IS/OOS判定")
    print(f"  {'-'*60}")
    for month in range(1, 13):
        sub = df[df['month'] == month]
        n, h, roi, pr = calc(sub)
        if n == 0:
            continue
        is_sub  = sub[sub['period'] == 'IS']
        oos_sub = sub[sub['period'] == 'OOS']
        ni, _, roi_i, _ = calc(is_sub)
        no, _, roi_o, _ = calc(oos_sub)
        mark = '←除外候補' if h == 0 else ''
        print(f"  {month:>2}月 | {n:>5} | {h:>4} | {h/n*100:>5.1f}% | {roi:>6.1f}% | {pr:>+10,}円 | IS:{roi_i:.0f}%/OOS:{roi_o:.0f}% {mark}")

    # 除外候補の評価
    zero_months = [m for m in range(1, 13) if calc(df[df['month'] == m])[1] == 0 and calc(df[df['month'] == m])[0] >= 30]
    low_months  = [m for m in range(1, 13) if calc(df[df['month'] == m])[0] >= 30 and calc(df[df['month'] == m])[2] < 50]

    print(f"\n  0的中月（件数≥30）: {zero_months if zero_months else 'なし'}")
    print(f"  低ROI月（ROI<50%・件数≥30）: {low_months if low_months else 'なし'}")

    # 月除外テスト
    print(f"\n  【月除外テスト】")
    print_is_oos('除外なし（ベースライン）', df)
    if zero_months:
        df_excl = df[~df['month'].isin(zero_months)]
        print_is_oos(f'{zero_months}月除外', df_excl)
    if low_months:
        df_excl2 = df[~df['month'].isin(low_months)]
        print_is_oos(f'低ROI月除外', df_excl2)
    # 4月除外
    print_is_oos('4月除外', df[df['month'] != 4])
    # 4+11月除外
    print_is_oos('4+11月除外', df[~df['month'].isin([4, 11])])

    # ================================================================
    # F3: オッズ帯精細化（200-250 vs 250-300）
    # ================================================================
    print(f"\n{sep}")
    print("【F3】オッズ帯精細化（200-300倍の中の構造）")
    print(sep)
    for lo, hi in [(200, 225), (225, 250), (250, 275), (275, 300)]:
        sub = df[(df['odds'] >= lo) & (df['odds'] < hi)]
        if len(sub) < 20:
            continue
        print_is_oos(f'{lo}-{hi}倍', sub)
    print()
    print_is_oos('200-250倍（前半）', df[(df['odds'] >= 200) & (df['odds'] < 250)])
    print_is_oos('250-300倍（後半）', df[(df['odds'] >= 250) & (df['odds'] < 300)])

    # ================================================================
    # 4月除外後の年度別 + Tier1相当（2024-2025直近2年）
    # ================================================================
    print(f"\n{sep}")
    print("【Tier1相当チェック】2024-2025年（直近OOS）のROI・黒字確認")
    print(sep)
    df_t1 = df[df['year'].isin([2024, 2025])]
    n_t1, h_t1, roi_t1, pr_t1 = calc(df_t1)
    print(f"\n  ベースライン（フィルタなし）2024-2025: {n_t1}件 / {h_t1}的中 / ROI {roi_t1:.1f}% / {pr_t1:+,}円")
    for year in [2024, 2025]:
        sub = df[df['year'] == year]
        n, h, roi, pr = calc(sub)
        mark = '○' if pr > 0 else '×'
        print(f"    {year}: {n}件 / {h}的中 / ROI {roi:.1f}% / {pr:+,}円 | {mark}")

    # ================================================================
    # 複合フィルタ比較サマリー
    # ================================================================
    print(f"\n{sep}")
    print("【複合フィルタ比較サマリー】")
    print(sep)

    # 有望スコア帯を自動選択
    best_score_range = None
    best_avg = 0
    for lo in range(44, 111, 10):
        hi = lo + 10
        sub = df[(df['p1_score'] >= lo) & (df['p1_score'] < hi)]
        if len(sub) < 30:
            continue
        ni, _, roi_i, _ = calc(sub[sub['period']=='IS'])
        no, _, roi_o, _ = calc(sub[sub['period']=='OOS'])
        if ni >= 15 and no >= 15:
            avg = (roi_i + roi_o) / 2
            if avg > best_avg:
                best_avg = avg
                best_score_range = (lo, hi)

    scenarios = [('ベースライン（フィルタなし）', df)]
    if zero_months:
        scenarios.append((f'{zero_months}月除外', df[~df['month'].isin(zero_months)]))
    scenarios.append(('4月除外', df[df['month'] != 4]))
    scenarios.append(('4+11月除外', df[~df['month'].isin([4, 11])]))
    if best_score_range:
        lo_s, hi_s = best_score_range
        scenarios.append((f'スコア{lo_s}-{hi_s}点', df[(df['p1_score'] >= lo_s) & (df['p1_score'] < hi_s)]))
        scenarios.append((f'スコア{lo_s}-{hi_s} + 4月除外',
                          df[(df['p1_score'] >= lo_s) & (df['p1_score'] < hi_s) & (df['month'] != 4)]))
        if zero_months:
            scenarios.append((f'スコア{lo_s}-{hi_s} + {zero_months}除外',
                              df[(df['p1_score'] >= lo_s) & (df['p1_score'] < hi_s) &
                                 (~df['month'].isin(zero_months))]))

    print(f"  {'条件':>34} | {'IS件':>5} | {'IS ROI':>7} | {'IS収支':>9} | {'OOS件':>5} | {'OOS ROI':>8} | {'OOS収支':>9}")
    print(f"  {'-'*86}")
    for label, d in scenarios:
        is_d  = d[d['period'] == 'IS']
        oos_d = d[d['period'] == 'OOS']
        ni, _, roi_i, pr_i = calc(is_d)
        no, _, roi_o, pr_o = calc(oos_d)
        mi = '★' if roi_i >= 100 else ' '
        mo = '★' if roi_o >= 100 else ' '
        print(f"  {label:>34} | {ni:>5} | {roi_i:>6.1f}%{mi} | {pr_i:>+9,} | {no:>5} | {roi_o:>7.1f}%{mo} | {pr_o:>+9,}")

    # ================================================================
    # 年度別詳細（ベースライン + 最有望フィルタ）
    # ================================================================
    print(f"\n{sep}")
    print("【年度別詳細】")
    print(sep)
    print_year_breakdown('ベースライン（フィルタなし）C × 200-300倍', df)

    if zero_months:
        df_excl_z = df[~df['month'].isin(zero_months)]
        print_year_breakdown(f'{zero_months}月除外', df_excl_z)

    conn.close()
    print("\n完了")


if __name__ == '__main__':
    main()
