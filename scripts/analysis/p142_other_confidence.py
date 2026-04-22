# -*- coding: utf-8 -*-
"""
p1-p4-p2 × B/C/D信頼度 調査スクリプト
A信頼度では A_P142_100_300 が採用済み（v2.49.0）。
B/C/Dで同じ買い目に有効な信頼度・フィルタがあるか調査する。

調査方針:
  1. B/C/D それぞれのベースライン（フィルタなし・100倍〜）
  2. 信頼度別のスコア帯ブレークダウン（低信頼度はスコア分布が異なる）
  3. オッズ帯別の IS/OOS 安定性確認（100-300倍 vs 他帯域）
  4. 4月除外・11月除外の効果確認
  5. 有望な組み合わせに対して年度別詳細を出力
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

def load_data(conn, confidence):
    """指定信頼度の p1-p4-p2 × 100倍〜 全データ"""
    query = f"""
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
        rp4.pit_number AS p4,
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
    JOIN race_predictions rp4 ON r.id = rp4.race_id
        AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN trifecta_odds t ON r.id = t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                         || CAST(rp4.pit_number AS TEXT) || '-'
                         || CAST(rp2.pit_number AS TEXT)
    WHERE rp1.confidence = '{confidence}'
      AND t.odds >= 100
      AND r.race_date >= '2020-01-01'
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') IS NOT NULL
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') IS NOT NULL
    ORDER BY r.race_date
    """
    df = pd.read_sql_query(query, conn)
    df['hit'] = (
        (df['actual_1st'] == df['p1']) &
        (df['actual_2nd'] == df['p4']) &
        (df['actual_3rd'] == df['p2'])
    )
    df['period'] = df['year'].apply(lambda y: 'IS' if y <= 2022 else 'OOS')
    return df


# ============================================================
# 統計関数
# ============================================================

def calc_stats(sub):
    n = len(sub)
    if n == 0:
        return 0, 0, 0.0, 0.0, 0
    h = int(sub['hit'].sum())
    pay = float((sub['hit'] * sub['odds'] * 100).sum())
    inv = n * 100
    roi = pay / inv * 100
    profit = int(pay - inv)
    return n, h, h / n * 100, roi, profit


def print_year_breakdown(label, df):
    n_all, h_all, _, roi_all, pr_all = calc_stats(df)
    by_year = sum(1 for y in range(2020, 2026)
                  if calc_stats(df[df['year'] == y])[4] > 0)
    print(f"\n  ▼ {label}  （合計: {n_all}件 / {h_all}的中 / ROI {roi_all:.1f}% / {pr_all:+,}円 / {by_year}/6年黒字）")
    print(f"  {'年':>5} | {'件数':>5} | {'的中':>4} | {'ROI':>7} | {'収支':>10}")
    for year in range(2020, 2026):
        sub = df[df['year'] == year]
        n, h, hr, roi, pr = calc_stats(sub)
        mark = '○' if pr > 0 else ('×' if n > 0 else '-')
        print(f"  {year} | {n:>5} | {h:>4} | {roi:>6.1f}% | {pr:>+10,}円 | {mark}")


def print_is_oos(label, df, indent=2):
    sp = ' ' * indent
    is_d  = df[df['period'] == 'IS']
    oos_d = df[df['period'] == 'OOS']
    ni, hi, _, roi_i, pr_i = calc_stats(is_d)
    no, ho, _, roi_o, pr_o = calc_stats(oos_d)
    mi = '★' if roi_i >= 100 else ' '
    mo = '★' if roi_o >= 100 else ' '
    print(f"{sp}{label:>30}  IS: {ni:>5}件 ROI {roi_i:>6.1f}%{mi} {pr_i:>+9,}  "
          f"OOS: {no:>5}件 ROI {roi_o:>6.1f}%{mo} {pr_o:>+9,}")


# ============================================================
# メイン分析
# ============================================================

def analyze_confidence(conn, conf):
    sep = '=' * 76
    print(f"\n{sep}")
    print(f"  信頼度 {conf}  p1-p4-p2 × 100倍〜  全体像")
    print(sep)

    df = load_data(conn, conf)
    if len(df) == 0:
        print("  データなし")
        return

    n_all, h_all, hr_all, roi_all, pr_all = calc_stats(df)
    print(f"\n  総件数: {n_all:,}件 / 的中: {h_all}件 ({hr_all:.2f}%) / "
          f"ROI: {roi_all:.1f}% / 収支: {pr_all:+,}円")
    print(f"  スコア分布: min={df['p1_score'].min():.0f} / "
          f"中央値={df['p1_score'].median():.0f} / max={df['p1_score'].max():.0f}")

    # ── IS/OOS 全体 ──
    print()
    print_is_oos('100倍〜 フィルタなし', df)

    # ── オッズ帯別 ──
    print(f"\n  【オッズ帯別 IS/OOS】")
    for lo, hi_v in [(100, 150), (150, 200), (200, 300), (300, 500), (500, 9999)]:
        hi_label = f"{hi_v}" if hi_v < 9000 else "+"
        sub = df[(df['odds'] >= lo) & (df['odds'] < hi_v)]
        if len(sub) == 0:
            continue
        print_is_oos(f"  オッズ {lo}-{hi_v if hi_v < 9000 else ''}倍", sub)

    # ── A条件と同じ 100-300倍帯 ──
    df_100_300 = df[(df['odds'] >= 100) & (df['odds'] < 300)]
    print(f"\n  【A条件と同じ 100-300倍帯 IS/OOS】")
    print_is_oos(f'100-300倍（合計）', df_100_300)

    # ── スコア帯別（100-300倍の中で） ──
    print(f"\n  【100-300倍 × スコア帯別 IS/OOS】")
    score_min = int(df_100_300['p1_score'].min()) if len(df_100_300) > 0 else 0
    # 信頼度によってスコア分布が異なるので動的にバンドを設定
    bands = []
    for lo in range(40, 100, 10):
        hi_v = lo + 10
        sub = df_100_300[(df_100_300['p1_score'] >= lo) & (df_100_300['p1_score'] < hi_v)]
        if len(sub) >= 20:
            bands.append((lo, hi_v, f'スコア{lo}-{hi_v}'))
    # 90+
    sub90 = df_100_300[df_100_300['p1_score'] >= 90]
    if len(sub90) >= 20:
        bands.append((90, 999, 'スコア90+'))

    for lo, hi_v, label in bands:
        sub = df_100_300[(df_100_300['p1_score'] >= lo) & (df_100_300['p1_score'] < hi_v)]
        print_is_oos(f'  {label}', sub)

    # ── 月別除外（4月・11月）+ 100-300倍 ──
    print(f"\n  【100-300倍 × 月除外テスト】")
    print_is_oos('100-300倍（除外なし）', df_100_300)
    print_is_oos('100-300倍 × 4月除外', df_100_300[df_100_300['month'] != 4])
    print_is_oos('100-300倍 × 11月除外', df_100_300[df_100_300['month'] != 11])
    print_is_oos('100-300倍 × 4+11月除外', df_100_300[~df_100_300['month'].isin([4, 11])])

    # ── 有望な組み合わせの年度別詳細 ──
    # 「100-300倍 × ROIが高そうなスコア帯」を探して年度別出力
    print(f"\n  【有望候補 年度別詳細】")

    # スコア帯 × 100-300倍 × 4月除外 で IS ROI が高いもの上位3つ
    candidates = []
    for lo in range(40, 100, 10):
        hi_v = lo + 10
        sub = df_100_300[
            (df_100_300['p1_score'] >= lo) & (df_100_300['p1_score'] < hi_v) &
            (~df_100_300['month'].isin([4]))
        ]
        if len(sub) < 30:
            continue
        is_sub = sub[sub['period'] == 'IS']
        oos_sub = sub[sub['period'] == 'OOS']
        ni, _, _, roi_i, pr_i = calc_stats(is_sub)
        no, _, _, roi_o, pr_o = calc_stats(oos_sub)
        if ni < 20 or no < 20:
            continue
        candidates.append((lo, hi_v, sub, roi_i, roi_o, pr_i + pr_o))

    # ROI IS+OOS平均 で降順ソート
    candidates.sort(key=lambda x: (x[3] + x[4]) / 2, reverse=True)

    shown = 0
    for lo, hi_v, sub, roi_i, roi_o, total_pr in candidates[:3]:
        if roi_i < 80 and roi_o < 80:
            continue
        label = f"信頼度{conf} × スコア{lo}-{hi_v} × 100-300倍 × 4月除外"
        print_year_breakdown(label, sub)
        shown += 1

    if shown == 0:
        # 条件を緩めて出力（件数≥20 + 最高ROIのもの）
        all_cands = []
        for lo in range(40, 100, 10):
            hi_v = lo + 10
            sub = df_100_300[
                (df_100_300['p1_score'] >= lo) & (df_100_300['p1_score'] < hi_v)
            ]
            if len(sub) < 20:
                continue
            _, _, _, roi_all2, pr_all2 = calc_stats(sub)
            all_cands.append((lo, hi_v, sub, roi_all2, pr_all2))
        all_cands.sort(key=lambda x: x[3], reverse=True)
        for lo, hi_v, sub, roi_all2, pr_all2 in all_cands[:2]:
            label = f"信頼度{conf} × スコア{lo}-{hi_v} × 100-300倍"
            print_year_breakdown(label, sub)

    # ── フィルタなし 100-300倍 年度別（参考） ──
    print_year_breakdown(f"信頼度{conf} × 100-300倍（フィルタなし・参考）", df_100_300)


def main():
    conn = sqlite3.connect(DB_PATH)

    print("=" * 76)
    print("  p1-p4-p2 × B/C/D信頼度 調査")
    print("  ※ A信頼度は v2.49.0 で A_P142_100_300 として採用済み")
    print("  ※ IS=2020-2022 / OOS=2023-2025")
    print("=" * 76)

    # A信頼度のベースライン（比較用）
    print("\n【比較: A信頼度 ベースライン（採用済み条件）】")
    df_a = load_data(conn, 'A')
    df_a_adopted = df_a[
        (df_a['p1_score'] >= 80) & (df_a['p1_score'] < 90) &
        (df_a['month'] != 11) &
        (df_a['odds'] >= 100) & (df_a['odds'] < 300)
    ]
    print_is_oos('A × スコア80-90 × 11月除外 × 100-300倍', df_a_adopted)
    n_a, h_a, _, roi_a, pr_a = calc_stats(df_a_adopted)
    print(f"  → 合計: {n_a}件 / {h_a}的中 / ROI {roi_a:.1f}% / {pr_a:+,}円")

    # B/C/D を順に調査
    for conf in ['B', 'C', 'D', 'E']:
        analyze_confidence(conn, conf)

    conn.close()
    print("\n\n完了")


if __name__ == '__main__':
    main()
