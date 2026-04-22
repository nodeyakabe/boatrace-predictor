# -*- coding: utf-8 -*-
"""
買い目点数検討 - 4案分析スクリプト
案C → 案A → 案D → 案B の順で分析

探索母集団:
  案A/B/C: 信頼度B以上（confidence IN ('A','B')）× p1-p2が実際に1-2着
  案D: 全レース × p1-p2が実際に1-2着 × 会場別
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import sqlite3
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")

VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
    '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
    '09': '津', '10': '三国', '11': '琵琶湖', '12': '住之江',
    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
    '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村',
}


def load_base_data(conn, confidence_filter=True):
    """探索用基本データを取得"""
    conf_clause = "AND rp1.confidence IN ('A', 'B')" if confidence_filter else ""

    query = f"""
    SELECT
        r.id AS race_id,
        r.race_date,
        r.venue_code,
        CAST(SUBSTR(r.race_date, 1, 4) AS INTEGER) AS year,
        rp1.pit_number AS p1_pit,
        rp2.pit_number AS p2_pit,
        rp3.pit_number AS p3_pit,
        rp4.pit_number AS p4_pit,
        rp3.total_score AS p3_score,
        rp4.total_score AS p4_score,
        (rp3.total_score - rp4.total_score) AS score_diff,
        res3.pit_number AS actual_3rd,
        CASE WHEN res3.pit_number = rp3.pit_number THEN 1 ELSE 0 END AS p3_is_3rd,
        CASE WHEN res3.pit_number = rp4.pit_number THEN 1 ELSE 0 END AS p4_is_3rd,
        COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
            AND o.combination = CAST(rp1.pit_number AS TEXT) || '-'
                             || CAST(rp2.pit_number AS TEXT) || '-'
                             || CAST(rp3.pit_number AS TEXT)), 0) AS odds_p3,
        COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
            AND o.combination = CAST(rp1.pit_number AS TEXT) || '-'
                             || CAST(rp2.pit_number AS TEXT) || '-'
                             || CAST(rp4.pit_number AS TEXT)), 0) AS odds_p4
    FROM races r
    JOIN race_predictions rp1 ON r.id = rp1.race_id
        AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id
        AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id
        AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN race_predictions rp4 ON r.id = rp4.race_id
        AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN results res1 ON res1.race_id = r.id AND res1.rank = '1'
        AND res1.pit_number = rp1.pit_number AND res1.is_invalid = 0
    JOIN results res2 ON res2.race_id = r.id AND res2.rank = '2'
        AND res2.pit_number = rp2.pit_number AND res2.is_invalid = 0
    JOIN results res3 ON res3.race_id = r.id AND res3.rank = '3'
        AND res3.is_invalid = 0
    WHERE r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
    {conf_clause}
    """
    return pd.read_sql_query(query, conn)


def run_case_c(df):
    """案C: スコア差フィルタ"""
    print("\n" + "="*70)
    print("【案C】スコア差フィルタ分析")
    print("p3-p4スコア差と「p4が3着に来る確率」の関係")
    print("="*70)

    total = len(df)
    print(f"母集団: {total}件（信頼度B以上 x p1-p2が実際に1-2着）")
    print(f"全体: p3的中率={df['p3_is_3rd'].mean()*100:.1f}% / p4的中率={df['p4_is_3rd'].mean()*100:.1f}%")

    bins = [(-999, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 999)]
    bin_labels = ['<5', '5-10', '10-15', '15-20', '20-30', '30+']

    print(f"\n{'スコア差':>8} | {'件数':>6} | {'p3率':>7} | {'p4率':>7} | {'p4/p3比':>8} | {'構成比':>6}")
    print("-" * 58)
    for (lo, hi), label in zip(bins, bin_labels):
        sub = df[(df['score_diff'] >= lo) & (df['score_diff'] < hi)]
        n = len(sub)
        if n == 0:
            continue
        p3r = sub['p3_is_3rd'].mean() * 100
        p4r = sub['p4_is_3rd'].mean() * 100
        ratio = p4r / p3r if p3r > 0 else 0
        pct = n / total * 100
        print(f"{label:>8} | {n:>6} | {p3r:>6.1f}% | {p4r:>6.1f}% | {ratio:>7.2f}x | {pct:>5.1f}%")

    print("\n【IS(2020-22) / OOS(2023-25) 比較】")
    for period, years in [('IS(2020-22)', [2020,2021,2022]), ('OOS(2023-25)', [2023,2024,2025])]:
        sub = df[df['year'].isin(years)]
        n = len(sub)
        p4r = sub['p4_is_3rd'].mean() * 100
        p3r = sub['p3_is_3rd'].mean() * 100
        print(f"  {period}: {n}件 / p3: {p3r:.1f}% / p4: {p4r:.1f}%")
        for (lo, hi), label in zip(bins, bin_labels):
            s = sub[(sub['score_diff'] >= lo) & (sub['score_diff'] < hi)]
            if len(s) < 5:
                continue
            print(f"    差{label}: {len(s)}件 / p4率 {s['p4_is_3rd'].mean()*100:.1f}%")

    print("\n【仮説閾値検証】")
    for threshold in [5, 10, 15, 20]:
        buy = df[df['score_diff'] < threshold]
        skip = df[df['score_diff'] >= threshold]
        b_rate = buy['p4_is_3rd'].mean() * 100 if len(buy) > 0 else 0
        s_rate = skip['p4_is_3rd'].mean() * 100 if len(skip) > 0 else 0
        diff = b_rate - s_rate
        print(f"  閾値{threshold:2d}点: 買い{len(buy):4d}件/p4率{b_rate:.1f}%  スキップ{len(skip):4d}件/p4率{s_rate:.1f}%  差={diff:+.1f}pt")


def run_case_a(df):
    """案A: 3着出現パターン分析"""
    print("\n" + "="*70)
    print("【案A】3着出現パターン分析")
    print("p1-p2が1-2着に来たとき、3着は誰か？（会場別）")
    print("="*70)

    total = len(df)
    p3_total = df['p3_is_3rd'].sum()
    p4_total = df['p4_is_3rd'].sum()
    other = total - p3_total - p4_total

    print(f"母集団: {total}件")
    print(f"\n【全体の3着分布】")
    print(f"  予測p3が3着: {int(p3_total)}件 ({p3_total/total*100:.1f}%)")
    print(f"  予測p4が3着: {int(p4_total)}件 ({p4_total/total*100:.1f}%)")
    print(f"  その他が3着: {other}件 ({other/total*100:.1f}%)")

    print(f"\n【3着pit番号の分布（全体）】")
    pit_counts = df['actual_3rd'].value_counts().sort_index()
    for pit, cnt in pit_counts.items():
        print(f"  {int(pit)}番pit: {cnt}件 ({cnt/total*100:.1f}%)")

    print(f"\n【会場別（件数20件以上）p3/p4/その他率】")
    print(f"{'会場':<8} | {'件数':>5} | {'p3率':>6} | {'p4率':>6} | {'その他':>6} | 特記")
    print("-" * 55)
    venue_stats = []
    for vc, vdf in df.groupby('venue_code'):
        n = len(vdf)
        if n < 20:
            continue
        p3r = vdf['p3_is_3rd'].mean() * 100
        p4r = vdf['p4_is_3rd'].mean() * 100
        venue_stats.append({'venue': VENUE_NAMES.get(vc, vc), 'n': n, 'p3': p3r, 'p4': p4r})
    venue_stats.sort(key=lambda x: -x['n'])
    for v in venue_stats:
        other_r = 100 - v['p3'] - v['p4']
        mark = "p4有望" if v['p4'] > v['p3'] * 0.6 else ("p3支配" if v['p3'] > 30 else "")
        print(f"{v['venue']:<8} | {v['n']:>5} | {v['p3']:>5.1f}% | {v['p4']:>5.1f}% | {other_r:>5.1f}% | {mark}")


def run_case_d(df_all):
    """案D: コース固定法則（全レース×会場別）"""
    print("\n" + "="*70)
    print("【案D】コース固定法則分析（全レース・会場別）")
    print("p1-p2が実際に1-2着のとき、3着のpit番号分布")
    print("="*70)

    total = len(df_all)
    print(f"母集団: {total}件（信頼度フィルタなし・全レース）")

    df_p1_1 = df_all[df_all['p1_pit'] == 1]
    df_p1_not1 = df_all[df_all['p1_pit'] != 1]
    print(f"p1=1番(インコース): {len(df_p1_1)}件 / p1 != 1番: {len(df_p1_not1)}件")

    print(f"\n【p1=1番コース時の3着pit番号分布（全会場合計）】")
    n = len(df_p1_1)
    pit_counts = df_p1_1['actual_3rd'].value_counts().sort_index()
    for pit, cnt in pit_counts.items():
        bar = '|' * int(cnt / n * 100)
        print(f"  {int(pit)}番: {cnt}件 ({cnt/n*100:.1f}%) {bar}")

    print(f"\n【会場別（p1=1番コース時、件数50件以上）】")
    print(f"{'会場':<8} | {'件数':>5} | {'p3率':>6} | {'p4率':>6} | {'最多3着pit':>8} | {'2位3着pit':>8}")
    print("-" * 60)
    venue_rows = []
    for vc, vdf in df_p1_1.groupby('venue_code'):
        n = len(vdf)
        if n < 50:
            continue
        p3r = vdf['p3_is_3rd'].mean() * 100
        p4r = vdf['p4_is_3rd'].mean() * 100
        pit_dist = vdf['actual_3rd'].value_counts()
        top1 = int(pit_dist.index[0]) if len(pit_dist) > 0 else '-'
        top2 = int(pit_dist.index[1]) if len(pit_dist) > 1 else '-'
        venue_rows.append({'venue': VENUE_NAMES.get(vc, vc), 'n': n, 'p3': p3r, 'p4': p4r, 'top1': top1, 'top2': top2})
    venue_rows.sort(key=lambda x: -x['p4'])
    for v in venue_rows:
        print(f"{v['venue']:<8} | {v['n']:>5} | {v['p3']:>5.1f}% | {v['p4']:>5.1f}% | {str(v['top1'])+'番':>8} | {str(v['top2'])+'番':>8}")


def run_case_b(df):
    """案B: EV比較分析"""
    print("\n" + "="*70)
    print("【案B】期待値（EV）比較分析")
    print("EV = 推定的中確率 x オッズ の比較")
    print("="*70)

    df_b = df[(df['odds_p3'] > 0) | (df['odds_p4'] > 0)].copy()
    total = len(df_b)
    print(f"母集団（オッズあり）: {total}件")

    odds_tiers = [
        (0, 20, '~20倍'),
        (20, 30, '20-30倍'),
        (30, 40, '30-40倍'),
        (40, 50, '40-50倍'),
        (50, 70, '50-70倍'),
        (70, 999, '70倍超'),
    ]

    for axis, hit_col, odds_col in [('p3軸', 'p3_is_3rd', 'odds_p3'), ('p4軸', 'p4_is_3rd', 'odds_p4')]:
        print(f"\n【{axis} オッズ帯別 的中率・EV】")
        print(f"{'オッズ帯':<10} | {'件数':>5} | {'的中率':>6} | {'avg odds':>8} | {'EV':>6}")
        print("-" * 46)
        for lo, hi, label in odds_tiers:
            sub = df_b[(df_b[odds_col] >= lo) & (df_b[odds_col] < hi) & (df_b[odds_col] > 0)]
            n = len(sub)
            if n < 10:
                continue
            hr = sub[hit_col].mean()
            avg_odds = sub[odds_col].mean()
            ev = hr * avg_odds
            flag = " ★" if ev > 1.5 else (" ◎" if ev > 1.0 else " ×")
            print(f"{label:<10} | {n:>5} | {hr*100:>5.1f}% | {avg_odds:>8.1f} | {ev:>6.2f}{flag}")

    # Pattern H相当（30-50倍）でのEV比較
    print(f"\n【Pattern H相当（30-50倍帯）でのEV比較】")
    p3_sub = df_b[(df_b['odds_p3'] >= 30) & (df_b['odds_p3'] < 50)]
    p4_sub = df_b[(df_b['odds_p4'] >= 30) & (df_b['odds_p4'] < 50)]
    for label, sub, hit_col, odds_col in [
        ('p3（30-50倍）', p3_sub, 'p3_is_3rd', 'odds_p3'),
        ('p4（30-50倍）', p4_sub, 'p4_is_3rd', 'odds_p4'),
    ]:
        n = len(sub)
        if n == 0:
            continue
        hr = sub[hit_col].mean()
        avg_odds = sub[odds_col].mean()
        ev = hr * avg_odds
        print(f"  {label}: {n}件 / 的中率{hr*100:.1f}% / avg_odds {avg_odds:.1f} / EV {ev:.2f}")

    # 案Bと案Cで判断が分かれるケースの実証
    df_both = df_b[(df_b['odds_p3'] > 0) & (df_b['odds_p4'] > 0)].copy()
    if len(df_both) > 0:
        p3_base = df_both['p3_is_3rd'].mean()
        p4_base = df_both['p4_is_3rd'].mean()
        df_both['ev_p3'] = p3_base * df_both['odds_p3']
        df_both['ev_p4'] = p4_base * df_both['odds_p4']
        df_both['b_buy_p4'] = df_both['ev_p4'] > df_both['ev_p3']
        df_both['c_buy_p4'] = df_both['score_diff'] < 10

        n_both = len(df_both)
        n_b_buy = df_both['b_buy_p4'].sum()
        print(f"\n【案BとCの判断比較（両軸オッズあり: {n_both}件）】")
        print(f"  案B「p4買い」件数: {n_b_buy}件 ({n_b_buy/n_both*100:.1f}%)")

        agree_buy = df_both[df_both['b_buy_p4'] & df_both['c_buy_p4']]
        b_yes_c_no = df_both[df_both['b_buy_p4'] & ~df_both['c_buy_p4']]
        b_no_c_yes = df_both[~df_both['b_buy_p4'] & df_both['c_buy_p4']]
        agree_skip = df_both[~df_both['b_buy_p4'] & ~df_both['c_buy_p4']]

        for label, sub in [
            ('B=買い C=買い（一致）', agree_buy),
            ('B=買い C=スキップ（B固有）', b_yes_c_no),
            ('B=スキップ C=買い（C固有）', b_no_c_yes),
            ('B=スキップ C=スキップ（一致）', agree_skip),
        ]:
            n = len(sub)
            if n == 0:
                continue
            p4r = sub['p4_is_3rd'].mean() * 100
            print(f"  {label}: {n}件 / p4実際の的中率 {p4r:.1f}%")


def main():
    conn = sqlite3.connect(DB_PATH)

    print("=" * 70)
    print("買い目点数検討 - 4案分析（案C→A→D→B）")
    print("=" * 70)

    print("\n[データ取得中] 信頼度B以上（案A/B/C用）...")
    df = load_base_data(conn, confidence_filter=True)
    df['year'] = df['race_date'].str[:4].astype(int)
    print(f"  -> {len(df)}件取得")

    print("[データ取得中] 全レース（案D用）...")
    df_all = load_base_data(conn, confidence_filter=False)
    df_all['year'] = df_all['race_date'].str[:4].astype(int)
    print(f"  -> {len(df_all)}件取得")

    run_case_c(df)
    run_case_a(df)
    run_case_d(df_all)
    run_case_b(df)

    conn.close()
    print("\n\n完了")


if __name__ == '__main__':
    main()
