# -*- coding: utf-8 -*-
"""
p1-p3-p2 × C信頼度 × 200-300倍 月別0的中（2,3,7,12月）の根拠調査
「なぜこれらの月が0的中なのか」構造的理由を探る

調査項目:
  1. 月別レースグレード分布（SG/G1が多い月 → 予測精度上昇 → 崩れ減少）
  2. 月別オッズ分布（200-300倍帯の出現率に偏りがあるか）
  3. 月別1コース勝率・波乱発生率（荒れやすい月かどうか）
  4. 月別p1-p3-p2の「素の発生率」（的中候補の質自体に差があるか）
  5. 他信頼度・他買い目での同月パターン（C×200-300倍固有か？）
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import sqlite3
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")

TARGET_MONTHS = [2, 3, 7, 12]
OTHER_MONTHS  = [1, 4, 5, 6, 8, 9, 10, 11]


def main():
    conn = sqlite3.connect(DB_PATH)
    sep = '=' * 74

    # ================================================================
    # 調査1: 月別レースグレード分布（全レース vs C信頼度レース）
    # ================================================================
    print(sep)
    print("【調査1】月別レースグレード分布")
    print("  SG/G1が多い月 → 予測精度上昇 → p3が2着に入りにくい？")
    print(sep)

    grade_query = """
    SELECT
        CAST(strftime('%m', r.race_date) AS INTEGER) AS month,
        r.race_grade,
        COUNT(*) AS cnt
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id
        AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        AND rp.confidence = 'C'
    JOIN trifecta_odds t ON r.id = t.race_id
        AND t.combination = CAST(rp.pit_number AS TEXT) || '-'
                         || (SELECT CAST(rp3.pit_number AS TEXT)
                             FROM race_predictions rp3
                             WHERE rp3.race_id = r.id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3) || '-'
                         || (SELECT CAST(rp2.pit_number AS TEXT)
                             FROM race_predictions rp2
                             WHERE rp2.race_id = r.id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2)
        AND t.odds >= 200 AND t.odds < 300
    WHERE r.race_date >= '2020-01-01'
    GROUP BY month, r.race_grade
    ORDER BY month, cnt DESC
    """
    df_grade = pd.read_sql_query(grade_query, conn)

    print(f"\n  {'月':>4} | {'一般戦':>6} | {'SG+G1+G2':>9} | {'SG+G1+G2比率':>11} | 分類")
    print(f"  {'-'*50}")
    for m in range(1, 13):
        sub = df_grade[df_grade['month'] == m]
        general = sub[sub['race_grade'].isin(['一般', '予', '準優', '優勝', 'G3', ''])]['cnt'].sum()
        premium  = sub[sub['race_grade'].isin(['SG', 'G1', 'G2'])]['cnt'].sum()
        total = general + premium
        if total == 0:
            continue
        ratio = premium / total * 100 if total > 0 else 0
        mark = '← 0的中' if m in TARGET_MONTHS else ''
        print(f"  {m:>2}月 | {general:>6} | {premium:>9} | {ratio:>10.1f}% | {mark}")

    # ================================================================
    # 調査2: 月別 平均オッズ・オッズ分布（200-300倍内の偏り）
    # ================================================================
    print(f"\n{sep}")
    print("【調査2】月別 オッズ分布（200-300倍内）")
    print("  オッズが高い月 → 的中しにくい配当 → 0的中になりやすい？")
    print(sep)

    odds_query = """
    SELECT
        CAST(strftime('%m', r.race_date) AS INTEGER) AS month,
        t.odds,
        (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') AS a1,
        (SELECT pit_number FROM results WHERE race_id=r.id AND rank='2') AS a2,
        (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') AS a3,
        rp1.pit_number AS p1, rp2.pit_number AS p2, rp3.pit_number AS p3
    FROM races r
    JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
    JOIN race_predictions rp2 ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
    JOIN race_predictions rp3 ON r.id=rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)
    WHERE rp1.confidence='C' AND t.odds>=200 AND t.odds<300
      AND r.race_date>='2020-01-01'
      AND (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') IS NOT NULL
      AND (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') IS NOT NULL
    """
    df_odds = pd.read_sql_query(odds_query, conn)
    df_odds['hit'] = (
        (df_odds['a1'] == df_odds['p1']) &
        (df_odds['a2'] == df_odds['p3']) &
        (df_odds['a3'] == df_odds['p2'])
    )

    print(f"\n  {'月':>4} | {'件数':>5} | {'平均オッズ':>9} | {'中央値':>7} | {'250倍超率':>9} | {'的中':>4} | 分類")
    print(f"  {'-'*58}")
    for m in range(1, 13):
        sub = df_odds[df_odds['month'] == m]
        if len(sub) == 0:
            continue
        avg_o = sub['odds'].mean()
        med_o = sub['odds'].median()
        hi_rate = (sub['odds'] >= 250).mean() * 100
        hits = int(sub['hit'].sum())
        mark = '← 0的中' if m in TARGET_MONTHS else ''
        print(f"  {m:>2}月 | {len(sub):>5} | {avg_o:>8.1f}倍 | {med_o:>6.1f}倍 | {hi_rate:>8.1f}% | {hits:>4} | {mark}")

    # ================================================================
    # 調査3: 月別 p1-p3-p2の素の発生率（200-300倍帯に限定しない）
    # ================================================================
    print(f"\n{sep}")
    print("【調査3】月別 p1-p3-p2 素の発生率（C信頼度・全オッズ）")
    print("  的中候補の「素の発生率」に月別差があるか確認")
    print(sep)

    raw_query = """
    SELECT
        CAST(strftime('%m', r.race_date) AS INTEGER) AS month,
        COUNT(*) AS total,
        SUM(CASE WHEN
            (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') = rp1.pit_number AND
            (SELECT pit_number FROM results WHERE race_id=r.id AND rank='2') = rp3.pit_number AND
            (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') = rp2.pit_number
            THEN 1 ELSE 0 END) AS p132_hits,
        SUM(CASE WHEN
            (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') = rp1.pit_number
            THEN 1 ELSE 0 END) AS p1_hits
    FROM races r
    JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
    JOIN race_predictions rp2 ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
    JOIN race_predictions rp3 ON r.id=rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
    WHERE rp1.confidence='C'
      AND r.race_date>='2020-01-01'
      AND (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') IS NOT NULL
    GROUP BY month
    ORDER BY month
    """
    df_raw = pd.read_sql_query(raw_query, conn)

    print(f"\n  {'月':>4} | {'総件数':>7} | {'1着的中率':>9} | {'p1p3p2率':>9} | 分類")
    print(f"  {'-'*48}")
    for _, row in df_raw.iterrows():
        m = int(row['month'])
        p1r = row['p1_hits'] / row['total'] * 100
        p132r = row['p132_hits'] / row['total'] * 100
        mark = '← 0的中月' if m in TARGET_MONTHS else ''
        print(f"  {m:>2}月 | {int(row['total']):>7,} | {p1r:>8.1f}% | {p132r:>8.2f}% | {mark}")

    # ================================================================
    # 調査4: 同じ月のパターンが他条件でも出るか（C固有性の確認）
    # ================================================================
    print(f"\n{sep}")
    print("【調査4】月別0的中は C×200-300倍 固有か？（A信頼度との比較）")
    print("  A信頼度×p1-p4-p2×100-300倍でも同月が0的中なら「月の特性」")
    print("  そうでなければ「C×200-300倍の少数サンプルノイズ」")
    print(sep)

    # A×p1-p4-p2×100-300倍の月別
    a_query = """
    SELECT
        CAST(strftime('%m', r.race_date) AS INTEGER) AS month,
        COUNT(*) AS n,
        SUM(CASE WHEN
            (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') = rp1.pit_number AND
            (SELECT pit_number FROM results WHERE race_id=r.id AND rank='2') = rp4.pit_number AND
            (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') = rp2.pit_number
            THEN 1 ELSE 0 END) AS hits
    FROM races r
    JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
    JOIN race_predictions rp2 ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
    JOIN race_predictions rp4 ON r.id=rp4.race_id AND rp4.prediction_type='before' AND rp4.rank_prediction=4
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)
    WHERE rp1.confidence='A' AND rp1.total_score>=80 AND rp1.total_score<90
      AND t.odds>=100 AND t.odds<300
      AND CAST(strftime('%m', r.race_date) AS INTEGER) != 11
      AND r.race_date>='2020-01-01'
      AND (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') IS NOT NULL
      AND (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') IS NOT NULL
    GROUP BY month ORDER BY month
    """
    df_a = pd.read_sql_query(a_query, conn)

    print(f"\n  C×p1-p3-p2×200-300倍 の0的中月: {TARGET_MONTHS}")
    print(f"\n  A×p1-p4-p2×100-300倍（採用済み）月別:")
    print(f"  {'月':>4} | {'件数':>5} | {'的中':>4} | 重複？")
    print(f"  {'-'*30}")
    shared_zero = []
    for _, row in df_a.iterrows():
        m = int(row['month'])
        hits = int(row['hits'])
        overlap = '← C条件とも0的中' if (m in TARGET_MONTHS and hits == 0) else ''
        if m in TARGET_MONTHS and hits == 0:
            shared_zero.append(m)
        print(f"  {m:>2}月 | {int(row['n']):>5} | {hits:>4} | {overlap}")

    print(f"\n  両条件で0的中の月: {shared_zero if shared_zero else 'なし（C条件固有）'}")

    # ================================================================
    # 調査5: 0的中月の件数と偶然確率
    # ================================================================
    print(f"\n{sep}")
    print("【調査5】0的中月が偶然起きる確率（統計的根拠確認）")
    print(sep)

    total_n = len(df_odds)
    total_h = int(df_odds['hit'].sum())
    hit_rate = total_h / total_n

    print(f"\n  全体的中率: {total_n}件中{total_h}的中 = {hit_rate*100:.3f}%")
    print(f"\n  各月が0的中になる確率（二項分布）:")
    print(f"  {'月':>4} | {'件数':>5} | {'期待的中':>8} | {'0的中確率':>9} | 分類")
    print(f"  {'-'*45}")

    import math
    for m in range(1, 13):
        sub = df_odds[df_odds['month'] == m]
        n = len(sub)
        if n == 0:
            continue
        # P(X=0) = (1-p)^n
        p_zero = (1 - hit_rate) ** n
        expected = n * hit_rate
        mark = '← 0的中' if m in TARGET_MONTHS else ''
        print(f"  {m:>2}月 | {n:>5} | {expected:>7.2f}件 | {p_zero*100:>8.1f}% | {mark}")

    # 4ヶ月すべてが0的中になる確率（独立と仮定）
    p_all_zero = 1.0
    for m in TARGET_MONTHS:
        sub = df_odds[df_odds['month'] == m]
        n = len(sub)
        p_all_zero *= (1 - hit_rate) ** n
    print(f"\n  {TARGET_MONTHS}月すべてが0的中になる確率: {p_all_zero*100:.2f}%")
    print(f"  ※ 「どの4ヶ月か」を選ぶ組み合わせ数 C(12,4)={math.comb(12,4)}通り")
    print(f"  ※ 多重比較補正後の有意水準 = {p_all_zero * math.comb(12,4) * 100:.1f}%")

    conn.close()
    print("\n完了")


if __name__ == '__main__':
    main()
