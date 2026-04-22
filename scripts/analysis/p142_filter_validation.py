# -*- coding: utf-8 -*-
"""
候補1: p1-p4-p2 × 100倍〜 × 信頼度A フィルタ検証
発見した絞り込み条件をIS/OOS別に検証 + 根拠分析付き

検証対象フィルタ:
  F1: スコア帯（80-90点 vs 90+点）
  F2: 11月除外
  F3: オッズ帯（100-150 + 200-300 vs 150-200 + 300+）
  F4: p4=5枠除外
  複合: F1+F2、F1+F2+F3
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


def load_base_data(conn):
    """p1-p4-p2 × 100倍〜 × 信頼度A の全データ"""
    query = """
    SELECT
        r.id AS race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
        r.race_grade,
        CAST(SUBSTR(r.race_date, 1, 4) AS INTEGER) AS year,
        CAST(SUBSTR(r.race_date, 6, 2) AS INTEGER) AS month,
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
    WHERE rp1.confidence = 'A'
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


def print_filter_result(label, df_yes, df_no, title):
    """フィルタあり vs なしの IS/OOS比較"""
    print(f"\n{'='*72}")
    print(f"【{title}】")
    print(f"{'='*72}")
    print(f"  {'条件':>16} | {'IS件数':>6} | {'IS ROI':>7} | {'IS収支':>10} | {'OOS件数':>7} | {'OOS ROI':>8} | {'OOS収支':>10}")
    print(f"  {'-'*78}")

    for lbl, df in [(label + '（対象）', df_yes), ('除外レース', df_no)]:
        is_ = df[df['period'] == 'IS']
        oos = df[df['period'] == 'OOS']
        ni, hi, hri, roi_i, pr_i = calc_stats(is_)
        no, ho, hro, roi_o, pr_o = calc_stats(oos)
        mi = '★' if roi_i >= 100 else ''
        mo = '★' if roi_o >= 100 else ''
        print(f"  {lbl:>16} | {ni:>6} | {roi_i:>6.1f}%{mi} | {pr_i:>+10,} | {no:>7} | {roi_o:>7.1f}%{mo} | {pr_o:>+10,}")

    # 全体も表示
    df_all = pd.concat([df_yes, df_no])
    is_ = df_all[df_all['period'] == 'IS']
    oos = df_all[df_all['period'] == 'OOS']
    ni, _, _, roi_i, pr_i = calc_stats(is_)
    no, _, _, roi_o, pr_o = calc_stats(oos)
    print(f"  {'[フィルタ前全体]':>16} | {ni:>6} | {roi_i:>6.1f}% | {pr_i:>+10,} | {no:>7} | {roi_o:>7.1f}% | {pr_o:>+10,}")


def print_year_breakdown(label, df):
    """年度別詳細"""
    print(f"\n  {label} 年度別:")
    print(f"  {'年':>5} | {'件数':>5} | {'的中':>4} | {'ROI':>7} | {'収支':>10}")
    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        sub = df[df['year'] == year]
        n, h, hr, roi, pr = calc_stats(sub)
        mark = '○' if pr > 0 else '×'
        print(f"  {year} | {n:>5} | {h:>4} | {roi:>6.1f}% | {pr:>+10,}円 | {mark}")
    total_n, total_h, _, total_roi, total_pr = calc_stats(df)
    by_year = sum(1 for y in [2020,2021,2022,2023,2024,2025]
                  if calc_stats(df[df['year']==y])[4] > 0)
    print(f"  {'合計':>5} | {total_n:>5} | {total_h:>4} | {total_roi:>6.1f}% | {total_pr:>+10,}円 | {by_year}/6年黒字")


def main():
    conn = sqlite3.connect(DB_PATH)

    print("="*72)
    print("候補1: p1-p4-p2 × 100倍〜 × 信頼度A  フィルタ検証（根拠分析付き）")
    print("="*72)

    df = load_base_data(conn)
    print(f"\nベースデータ: {len(df):,}件 / 的中{df['hit'].sum()}件 / IS:{(df['period']=='IS').sum()}件 / OOS:{(df['period']=='OOS').sum()}件")

    # ================================================================
    # F1: スコア帯フィルタ（80-90点 vs 90+点）
    # ================================================================
    df_s8090 = df[(df['p1_score'] >= 80) & (df['p1_score'] < 90)]
    df_s90p  = df[df['p1_score'] >= 90]
    df_s_other = df[df['p1_score'] < 80]

    print_filter_result('スコア80-90点', df_s8090, pd.concat([df_s90p, df_s_other]), 'F1: スコア帯フィルタ')
    print_year_breakdown('スコア80-90点', df_s8090)
    print_year_breakdown('スコア90+点', df_s90p)

    # 根拠分析: スコア別の「予測通り展開」率
    print(f"\n  【F1 根拠分析】スコア帯別 p1-p2-p3（予測通り展開）の実現率")
    print(f"  信頼度A × 100倍〜 対象レースで「1着=p1 かつ 2着=p2 かつ 3着=p3」が何%起きているか")
    print(f"  （p4が2着に来るにはこの「教科書展開」が崩れる必要がある）")

    # Load additional data: p1-p2-p3 actual hit rate for each score band
    score_query = """
    SELECT
        rp1.total_score AS score,
        CAST(SUBSTR(r.race_date, 1, 4) AS INTEGER) AS year,
        rp1.pit_number AS p1, rp2.pit_number AS p2, rp3.pit_number AS p3,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank='1') AS a1,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank='2') AS a2,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank='3') AS a3
    FROM races r
    JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
    JOIN race_predictions rp2 ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
    JOIN race_predictions rp3 ON r.id=rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
    WHERE rp1.confidence = 'A'
      AND r.race_date >= '2020-01-01'
      AND (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') IS NOT NULL
    """
    df_score = pd.read_sql_query(score_query, conn)
    df_score['p123_hit'] = (
        (df_score['a1'] == df_score['p1']) &
        (df_score['a2'] == df_score['p2']) &
        (df_score['a3'] == df_score['p3'])
    )
    df_score['p1_hit'] = (df_score['a1'] == df_score['p1'])
    df_score['period'] = df_score['year'].apply(lambda y: 'IS' if y <= 2022 else 'OOS')

    for band_label, lo, hi in [('70-80点', 70, 80), ('80-90点', 80, 90), ('90+点', 90, 200)]:
        sub = df_score[(df_score['score'] >= lo) & (df_score['score'] < hi)]
        if len(sub) == 0:
            continue
        p1_rate = sub['p1_hit'].mean() * 100
        p123_rate = sub['p123_hit'].mean() * 100
        sub_is = sub[sub['period'] == 'IS']
        sub_oos = sub[sub['period'] == 'OOS']
        p123_is = sub_is['p123_hit'].mean() * 100 if len(sub_is) > 0 else 0
        p123_oos = sub_oos['p123_hit'].mean() * 100 if len(sub_oos) > 0 else 0
        print(f"  {band_label}: {len(sub):>7,}件 / 1着的中率{p1_rate:>5.1f}% / "
              f"3連単教科書率{p123_rate:>4.1f}% (IS:{p123_is:.1f}% OOS:{p123_oos:.1f}%)")

    print(f"\n  ※ 「教科書率」が高いほど p4が2着に来る余地が少ない → p1-p4-p2が的中しにくい")

    # ================================================================
    # F2: 11月除外
    # ================================================================
    df_no11  = df[df['month'] != 11]
    df_nov   = df[df['month'] == 11]

    print_filter_result('11月以外', df_no11, df_nov, 'F2: 11月除外フィルタ')
    print_year_breakdown('11月以外', df_no11)

    # 根拠分析: 11月のレース特性
    print(f"\n  【F2 根拠分析】11月のレースグレード分布（信頼度A・全レース）")
    grade_query = """
    SELECT r.race_grade,
           CAST(SUBSTR(r.race_date, 6, 2) AS INTEGER) AS month,
           COUNT(*) AS cnt
    FROM races r
    JOIN race_predictions rp ON r.id=rp.race_id
        AND rp.prediction_type='before' AND rp.rank_prediction=1 AND rp.confidence='A'
    WHERE r.race_date >= '2020-01-01'
    GROUP BY r.race_grade, month
    ORDER BY month, cnt DESC
    """
    df_grade = pd.read_sql_query(grade_query, conn)
    for month_val, label in [(4, '4月'), (7, '7月'), (11, '11月'), (12, '12月')]:
        sub = df_grade[df_grade['month'] == month_val].head(5)
        grade_str = ', '.join(f"{row['race_grade']}({row['cnt']}件)"
                              for _, row in sub.iterrows() if row['race_grade'])
        total = df_grade[df_grade['month'] == month_val]['cnt'].sum()
        print(f"  {label}（計{total}件）: {grade_str}")

    print(f"\n  【F2 根拠分析】11月のレースのオッズ分布（信頼度A 100倍〜）")
    nov_sub = df[df['month'] == 11]
    other_sub = df[df['month'] != 11]
    print(f"  11月: 平均オッズ {nov_sub['odds'].mean():.1f}倍 / 中央値 {nov_sub['odds'].median():.1f}倍 ({len(nov_sub)}件)")
    print(f"  他月: 平均オッズ {other_sub['odds'].mean():.1f}倍 / 中央値 {other_sub['odds'].median():.1f}倍 ({len(other_sub)}件)")

    # ================================================================
    # F3: オッズ帯フィルタ（100-150 + 200-300のみ）
    # ================================================================
    df_valid_odds = df[((df['odds'] >= 100) & (df['odds'] < 150)) |
                       ((df['odds'] >= 200) & (df['odds'] < 300))]
    df_excl_odds  = df[~(((df['odds'] >= 100) & (df['odds'] < 150)) |
                         ((df['odds'] >= 200) & (df['odds'] < 300)))]

    print_filter_result('100-150+200-300倍', df_valid_odds, df_excl_odds,
                        'F3: オッズ帯フィルタ（150-200倍・300倍超 除外）')

    # 根拠分析: オッズ帯別の「p4実際の2着率」（全信頼度）
    print(f"\n  【F3 根拠分析】オッズ帯別の実情（IS/OOSで安定しているか？）")
    print(f"  150-200倍帯: IS/OOS分割")
    for period in ['IS', 'OOS']:
        sub = df_excl_odds[(df_excl_odds['period'] == period) &
                           (df_excl_odds['odds'] >= 150) & (df_excl_odds['odds'] < 200)]
        n, h, hr, roi, pr = calc_stats(sub)
        mark = '★' if roi >= 100 else ''
        print(f"    {period}: {n}件 / {h}的中 / ROI {roi:.1f}%{mark} / {pr:+,}円")
    print(f"  300-500倍帯: IS/OOS分割")
    for period in ['IS', 'OOS']:
        sub = df_excl_odds[(df_excl_odds['period'] == period) &
                           (df_excl_odds['odds'] >= 300) & (df_excl_odds['odds'] < 500)]
        n, h, hr, roi, pr = calc_stats(sub)
        print(f"    {period}: {n}件 / {h}的中 / ROI {roi:.1f}% / {pr:+,}円")
    print(f"  ※ 両期間で一貫して赤字なら「構造的な理由がある」可能性、")
    print(f"     片方だけなら「サンプルノイズ」の可能性が高い")

    # ================================================================
    # F4: p4=5枠除外
    # ================================================================
    df_no_p4_5 = df[df['p4'] != 5]
    df_p4_5    = df[df['p4'] == 5]

    print_filter_result('p4≠5枠', df_no_p4_5, df_p4_5, 'F4: p4=5枠除外フィルタ')

    # 根拠分析: 5コース艇の2着率（一般）
    print(f"\n  【F4 根拠分析】5コース艇が2着に入る確率（信頼度A・全オッズ）")
    course_query = """
    SELECT
        rp1.pit_number AS p1_pit,
        rp4.pit_number AS p4_pit,
        COUNT(*) AS total,
        SUM(CASE WHEN
            (SELECT pit_number FROM results WHERE race_id=r.id AND rank='2') = rp4.pit_number
            THEN 1 ELSE 0 END) AS p4_2nd_hits
    FROM races r
    JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
    JOIN race_predictions rp4 ON r.id=rp4.race_id AND rp4.prediction_type='before' AND rp4.rank_prediction=4
    WHERE rp1.confidence='A'
      AND r.race_date >= '2020-01-01'
      AND (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') = rp1.pit_number
    GROUP BY rp4.pit_number
    ORDER BY rp4.pit_number
    """
    df_course = pd.read_sql_query(course_query, conn)
    print(f"  （「1着=p1が的中したレース」でp4の枠番が2着に来た確率）")
    for _, row in df_course.iterrows():
        rate = row['p4_2nd_hits'] / row['total'] * 100 if row['total'] > 0 else 0
        print(f"  p4枠={int(row['p4_pit'])}: {int(row['total']):>6}件中 {int(row['p4_2nd_hits'])}回 = {rate:.2f}%")

    # ================================================================
    # 複合: F1 + F2（スコア80-90 × 11月除外）
    # ================================================================
    df_f1f2 = df[(df['p1_score'] >= 80) & (df['p1_score'] < 90) & (df['month'] != 11)]
    df_f1f2_excl = df[~((df['p1_score'] >= 80) & (df['p1_score'] < 90) & (df['month'] != 11))]

    print(f"\n{'='*72}")
    print(f"【複合A: F1+F2（スコア80-90 × 11月除外）】")
    print(f"{'='*72}")
    print_year_breakdown('スコア80-90 × 11月除外', df_f1f2)

    # ================================================================
    # 複合: F1 + F2 + F3（スコア80-90 × 11月除外 × 有効オッズ帯）
    # ================================================================
    df_f1f2f3 = df[
        (df['p1_score'] >= 80) & (df['p1_score'] < 90) &
        (df['month'] != 11) &
        (((df['odds'] >= 100) & (df['odds'] < 150)) |
         ((df['odds'] >= 200) & (df['odds'] < 300)))
    ]

    print(f"\n{'='*72}")
    print(f"【複合B: F1+F2+F3（スコア80-90 × 11月除外 × 100-150+200-300倍）】")
    print(f"{'='*72}")
    print_year_breakdown('F1+F2+F3複合', df_f1f2f3)

    # ================================================================
    # 複合: F1 + F2 + F3 + F4 （全フィルタ）
    # ================================================================
    df_all_filters = df[
        (df['p1_score'] >= 80) & (df['p1_score'] < 90) &
        (df['month'] != 11) &
        (((df['odds'] >= 100) & (df['odds'] < 150)) |
         ((df['odds'] >= 200) & (df['odds'] < 300))) &
        (df['p4'] != 5)
    ]

    print(f"\n{'='*72}")
    print(f"【複合C: 全フィルタ（F1+F2+F3+F4）】")
    print(f"{'='*72}")
    print_year_breakdown('全フィルタ複合', df_all_filters)

    # ================================================================
    # 最終比較サマリー
    # ================================================================
    print(f"\n{'='*72}")
    print(f"【最終比較サマリー】各フィルタのIS/OOS")
    print(f"{'='*72}")
    print(f"  {'条件':>28} | {'IS件数':>6} | {'IS ROI':>7} | {'IS収支':>10} | {'OOS件数':>7} | {'OOS ROI':>8} | {'OOS収支':>10}")
    print(f"  {'-'*90}")

    scenarios = [
        ('ベースライン（フィルタなし）', df),
        ('F1: スコア80-90点のみ', df_s8090),
        ('F2: 11月除外', df_no11),
        ('F3: オッズ100-150+200-300', df_valid_odds),
        ('F4: p4≠5枠', df_no_p4_5),
        ('複合A: F1+F2', df_f1f2),
        ('複合B: F1+F2+F3', df_f1f2f3),
        ('複合C: F1+F2+F3+F4', df_all_filters),
    ]

    for label, d in scenarios:
        is_d = d[d['period'] == 'IS']
        oos_d = d[d['period'] == 'OOS']
        ni, hi, _, roi_i, pr_i = calc_stats(is_d)
        no, ho, _, roi_o, pr_o = calc_stats(oos_d)
        mi = '★' if roi_i >= 100 else ''
        mo = '★' if roi_o >= 100 else ''
        print(f"  {label:>28} | {ni:>6} | {roi_i:>6.1f}%{mi} | {pr_i:>+10,} | {no:>7} | {roi_o:>7.1f}%{mo} | {pr_o:>+10,}")

    conn.close()
    print("\n完了")


if __name__ == '__main__':
    main()
