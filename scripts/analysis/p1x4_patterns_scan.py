# -*- coding: utf-8 -*-
"""
p1-p2-p4 / p1-p4-p3 / p1-p3-p4 パターン × 全信頼度 × 全オッズ帯 スキャン

p132/p142の採用後、まだ未調査の「崩れ展開」パターンを網羅調査。
IS=2020-2022 / OOS=2023-2025 で全組み合わせを一覧表示。

【パターン定義】
  p1-p2-p4 (p124): 1着=p1, 2着=p2, 3着=p4  ← 教科書崩れ(4位が3着)
  p1-p4-p3 (p143): 1着=p1, 2着=p4, 3着=p3  ← p142の2-3着入替版
  p1-p3-p4 (p134): 1着=p1, 2着=p3, 3着=p4  ← p132の3着違いバージョン

【除外パターン(根拠あり)】
  p1-p5-p2, p1-p5-p3: p5軸はROI 72.4%で廃止実績あり → 除外
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import sqlite3
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")

IS_START  = '2020-01-01'; IS_END  = '2022-12-31'
OOS_START = '2023-01-01'; OOS_END = '2025-12-31'


def load_data(conn, pattern_name):
    """
    パターン別データを一括取得。
    pattern_name: 'p124' / 'p143' / 'p134'
    """
    # パターン別のcombo・hit条件を定義
    if pattern_name == 'p124':
        combo_expr = ("CAST(rp1.pit_number AS TEXT) || '-' || "
                      "CAST(rp2.pit_number AS TEXT) || '-' || "
                      "CAST(rp4.pit_number AS TEXT)")
        hit_expr = ("(actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4)")
        label = "p1-p2-p4（教科書崩れ・4位3着）"
    elif pattern_name == 'p143':
        combo_expr = ("CAST(rp1.pit_number AS TEXT) || '-' || "
                      "CAST(rp4.pit_number AS TEXT) || '-' || "
                      "CAST(rp3.pit_number AS TEXT)")
        hit_expr = ("(actual_1st = p1 AND actual_2nd = p4 AND actual_3rd = p3)")
        label = "p1-p4-p3（p142の2-3着入替・4位2着+3位3着）"
    elif pattern_name == 'p134':
        combo_expr = ("CAST(rp1.pit_number AS TEXT) || '-' || "
                      "CAST(rp3.pit_number AS TEXT) || '-' || "
                      "CAST(rp4.pit_number AS TEXT)")
        hit_expr = ("(actual_1st = p1 AND actual_2nd = p3 AND actual_3rd = p4)")
        label = "p1-p3-p4（p132の3着違い・3位2着+4位3着）"
    else:
        raise ValueError(f"Unknown pattern: {pattern_name}")

    query = f"""
    SELECT
        r.id AS race_id,
        r.race_date,
        CAST(strftime('%Y', r.race_date) AS INTEGER) AS year,
        CAST(strftime('%m', r.race_date) AS INTEGER) AS month,
        rp1.confidence AS confidence,
        rp1.total_score AS p1_score,
        rp1.pit_number AS p1,
        rp2.pit_number AS p2,
        rp3.pit_number AS p3,
        rp4.pit_number AS p4,
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
        AND t.combination = {combo_expr}
    WHERE r.race_date >= '2020-01-01'
      AND t.odds >= 30
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') IS NOT NULL
      AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') IS NOT NULL
    ORDER BY r.race_date
    """
    df = pd.read_sql_query(query, conn)

    # 的中フラグ
    if pattern_name == 'p124':
        df['hit'] = (
            (df['actual_1st'] == df['p1']) &
            (df['actual_2nd'] == df['p2']) &
            (df['actual_3rd'] == df['p4'])
        )
    elif pattern_name == 'p143':
        df['hit'] = (
            (df['actual_1st'] == df['p1']) &
            (df['actual_2nd'] == df['p4']) &
            (df['actual_3rd'] == df['p3'])
        )
    elif pattern_name == 'p134':
        df['hit'] = (
            (df['actual_1st'] == df['p1']) &
            (df['actual_2nd'] == df['p3']) &
            (df['actual_3rd'] == df['p4'])
        )

    df['period'] = df['year'].apply(lambda y: 'IS' if y <= 2022 else 'OOS')
    return df, label


def calc(sub):
    n = len(sub)
    if n == 0:
        return 0, 0, 0.0, 0
    h = int(sub['hit'].sum())
    pay = float((sub['hit'] * sub['odds'] * 100).sum())
    roi = pay / (n * 100) * 100
    profit = int(pay - n * 100)
    return n, h, roi, profit


def print_year_breakdown(label, df):
    n_all, h_all, roi_all, pr_all = calc(df)
    by_year = sum(1 for y in range(2020, 2026) if calc(df[df['year'] == y])[3] > 0)
    print(f"\n  ▼ {label}")
    print(f"    合計: {n_all}件 / {h_all}的中 / ROI {roi_all:.1f}% / {pr_all:+,}円 / {by_year}/6年黒字")
    print(f"  {'年':>5} | {'件数':>5} | {'的中':>4} | {'ROI':>7} | {'収支':>10}")
    for year in range(2020, 2026):
        sub = df[df['year'] == year]
        n, h, roi, pr = calc(sub)
        mark = '○' if pr > 0 else ('×' if n > 0 else '-')
        print(f"  {year} | {n:>5} | {h:>4} | {roi:>6.1f}% | {pr:>+10,}円 | {mark}")


def scan_pattern(conn, pattern_name):
    sep = '=' * 80
    df, label = load_data(conn, pattern_name)

    print(f"\n{sep}")
    print(f"  パターン: {label}")
    print(f"  総件数: {len(df):,}件 / 的中: {df['hit'].sum()}件")
    print(sep)

    # オッズ帯定義
    odds_bands = [
        (30,  50,  '30-50倍'),
        (50,  100, '50-100倍'),
        (100, 150, '100-150倍'),
        (150, 200, '150-200倍'),
        (200, 300, '200-300倍'),
        (300, 500, '300-500倍'),
        (100, 300, '100-300倍(合算)'),
        (50,  300, '50-300倍(合算)'),
    ]
    confidences = ['A', 'B', 'C', 'D', 'E']

    print(f"\n{'='*80}")
    print(f"【全組み合わせ IS/OOS スキャン】")
    print(f"  ★ = ROI 100%超  ◎ = IS/OOS両方★（有望候補）")
    print(f"{'='*80}")
    print(f"  {'信頼度':>4} | {'オッズ帯':>12} | "
          f"{'IS件':>6} | {'IS ROI':>7} | {'IS収支':>9} | "
          f"{'OOS件':>6} | {'OOS ROI':>8} | {'OOS収支':>9} | 判定")
    print(f"  {'-'*82}")

    promising = []

    for conf in confidences:
        df_c = df[df['confidence'] == conf]
        if len(df_c) == 0:
            continue
        for lo, hi, lbl in odds_bands:
            sub = df_c[(df_c['odds'] >= lo) & (df_c['odds'] < hi)]
            if len(sub) < 30:
                continue
            is_sub  = sub[sub['period'] == 'IS']
            oos_sub = sub[sub['period'] == 'OOS']
            ni, hi_c, roi_i, pr_i = calc(is_sub)
            no, ho_c, roi_o, pr_o = calc(oos_sub)
            if ni < 20 or no < 20:
                continue

            mi = '★' if roi_i >= 100 else ' '
            mo = '★' if roi_o >= 100 else ' '
            both = '◎' if roi_i >= 100 and roi_o >= 100 else ' '

            print(f"  {conf:>4} | {lbl:>12} | "
                  f"{ni:>6} | {roi_i:>6.1f}%{mi} | {pr_i:>+9,} | "
                  f"{no:>6} | {roi_o:>7.1f}%{mo} | {pr_o:>+9,} | {both}")

            if roi_i >= 100 and roi_o >= 100 and ni + no >= 80:
                promising.append((conf, lo, hi, lbl, sub, roi_i, roi_o, pr_i + pr_o))

        print(f"  {'-'*82}")

    # 有望候補の年度別詳細
    if promising:
        print(f"\n{'='*80}")
        print(f"【有望候補 年度別詳細】（IS/OOS両方ROI 100%超・合計80件以上）")
        print(f"{'='*80}")
        promising.sort(key=lambda x: (x[5] + x[6]) / 2, reverse=True)
        for conf, lo, hi, lbl, sub, roi_i, roi_o, total_pr in promising:
            print_year_breakdown(f"信頼度{conf} × {lbl}", sub)
    else:
        print(f"\n有望候補（IS/OOS両方ROI 100%超・合計80件以上）: なし")

    return promising


def main():
    conn = sqlite3.connect(DB_PATH)

    print("=" * 80)
    print("  崩れ展開パターン × 全信頼度 × 全オッズ帯 スキャン")
    print("  対象: p1-p2-p4 / p1-p4-p3 / p1-p3-p4")
    print("  IS=2020-2022 / OOS=2023-2025")
    print("=" * 80)

    all_promising = {}
    for pattern in ['p124', 'p143', 'p134']:
        promising = scan_pattern(conn, pattern)
        all_promising[pattern] = promising

    # 全パターン横断サマリー
    print(f"\n{'='*80}")
    print("【全パターン横断サマリー（◎候補一覧）】")
    print(f"{'='*80}")
    found_any = False
    for pattern, candidates in all_promising.items():
        for conf, lo, hi, lbl, sub, roi_i, roi_o, total_pr in candidates:
            found_any = True
            n_total = len(sub)
            h_total = int(sub['hit'].sum())
            avg_roi = (roi_i + roi_o) / 2
            print(f"  {pattern.upper()} | 信頼度{conf} | {lbl} | "
                  f"IS {roi_i:.1f}%★ / OOS {roi_o:.1f}%★ | "
                  f"{n_total}件/{h_total}的中 | IS+OOS平均ROI {avg_roi:.1f}%")
    if not found_any:
        print("  候補なし（全パターンでIS/OOS両方ROI 100%超は検出されず）")

    # 比較参考: 採用済みパターン
    print(f"\n{'='*80}")
    print("【参考: 採用済みパターン（比較用）】")
    print(f"{'='*80}")
    print("  C_P132_200_300 (p132): IS 210.4% / OOS 321.7% / 5/6年黒字")
    print("  A_P142_100_300 (p142): IS 143.6% / OOS 230.4% / 6/6年黒字")

    conn.close()
    print("\n完了")


if __name__ == '__main__':
    main()
