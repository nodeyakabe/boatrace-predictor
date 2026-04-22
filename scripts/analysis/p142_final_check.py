# -*- coding: utf-8 -*-
"""
候補1 最終比較: F3保守案（100-300倍） vs F3積極案（100-150+200-300倍）
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os, sqlite3
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")

def load_data(conn):
    q = """
    SELECT r.race_date,
           CAST(SUBSTR(r.race_date,1,4) AS INTEGER) AS year,
           CAST(SUBSTR(r.race_date,6,2) AS INTEGER) AS month,
           rp1.total_score AS score,
           rp4.pit_number AS p4,
           t.odds,
           (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') AS a1,
           (SELECT pit_number FROM results WHERE race_id=r.id AND rank='2') AS a2,
           (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') AS a3,
           rp1.pit_number AS p1, rp2.pit_number AS p2, rp3.pit_number AS p3
    FROM races r
    JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
    JOIN race_predictions rp2 ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
    JOIN race_predictions rp3 ON r.id=rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
    JOIN race_predictions rp4 ON r.id=rp4.race_id AND rp4.prediction_type='before' AND rp4.rank_prediction=4
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT)||'-'
                         || CAST(rp4.pit_number AS TEXT)||'-'
                         || CAST(rp2.pit_number AS TEXT)
    WHERE rp1.confidence='A' AND t.odds>=100 AND r.race_date>='2020-01-01'
      AND (SELECT pit_number FROM results WHERE race_id=r.id AND rank='1') IS NOT NULL
      AND (SELECT pit_number FROM results WHERE race_id=r.id AND rank='3') IS NOT NULL
    """
    df = pd.read_sql_query(q, conn)
    df['hit'] = (df['a1']==df['p1']) & (df['a2']==df['p4']) & (df['a3']==df['p2'])
    df['period'] = df['year'].apply(lambda y: 'IS' if y<=2022 else 'OOS')
    return df

def stats(df):
    n = len(df)
    if n == 0: return 0,0,0.0,0.0,0
    h = int(df['hit'].sum())
    pay = float((df['hit']*df['odds']*100).sum())
    roi = pay/(n*100)*100
    return n, h, h/n*100, roi, int(pay-n*100)

def yearly(df, label):
    print(f"\n  {label}")
    print(f"  {'年':>5}|{'件数':>5}|{'的中':>4}|{'的中率':>6}|{'ROI':>7}|{'収支':>11}|判定")
    print(f"  {'-'*52}")
    black = 0
    for y in [2020,2021,2022,2023,2024,2025]:
        s = df[df['year']==y]
        n,h,hr,roi,pr = stats(s)
        mk = '○' if pr>0 else '×'
        if pr>0: black+=1
        print(f"  {y}|{n:>5}|{h:>4}|{hr:>5.1f}%|{roi:>6.1f}%|{pr:>+10,}円|{mk}")
    n,h,hr,roi,pr = stats(df)
    is_d = df[df['period']=='IS']; oos_d = df[df['period']=='OOS']
    ni,hi,_,roi_i,pr_i = stats(is_d); no,ho,_,roi_o,pr_o = stats(oos_d)
    print(f"  {'合計':>5}|{n:>5}|{h:>4}|{hr:>5.1f}%|{roi:>6.1f}%|{pr:>+10,}円|{black}/6黒字")
    print(f"  IS:  {ni}件/ROI {roi_i:.1f}%/{pr_i:+,}円  OOS: {no}件/ROI {roi_o:.1f}%/{pr_o:+,}円")

def main():
    conn = sqlite3.connect(DB_PATH)
    df = load_data(conn)

    # 共通フィルタ: F1（80-90点）× F2（11月除外）
    f12 = df[(df['score']>=80)&(df['score']<90)&(df['month']!=11)]

    # F3保守案: 300倍上限（100-300倍）
    f12_con = f12[df['odds']<300]
    # F3積極案: 100-150 + 200-300（150-200除外）
    f12_agg = f12[((df['odds']>=100)&(df['odds']<150))|((df['odds']>=200)&(df['odds']<300))]

    # 除外された150-200倍帯の中身を確認
    f12_150_200 = f12[(df['odds']>=150)&(df['odds']<200)]

    print("="*60)
    print("最終比較: F1+F2 に対するF3の2案")
    print("="*60)

    print("\n【前提】F1+F2のみ（F3適用前）")
    yearly(f12, 'スコア80-90 × 11月除外')

    print("\n" + "="*60)
    print("【F3保守案】100-300倍（300倍超だけ除外）")
    print("="*60)
    yearly(f12_con, 'F1+F2 × 100-300倍')

    print("\n" + "="*60)
    print("【F3積極案】100-150 + 200-300倍（150-200も除外）")
    print("="*60)
    yearly(f12_agg, 'F1+F2 × 100-150+200-300倍')

    # 150-200倍帯の詳細（除外対象の中身）
    print("\n" + "="*60)
    print("【参考】150-200倍帯（積極案で追加除外される部分）の詳細")
    print("="*60)
    print(f"  対象: {len(f12_150_200)}件 / 的中: {int(f12_150_200['hit'].sum())}件")
    is_s = f12_150_200[f12_150_200['period']=='IS']
    oos_s = f12_150_200[f12_150_200['period']=='OOS']
    _,h_i,_,roi_i,pr_i = stats(is_s)
    _,h_o,_,roi_o,pr_o = stats(oos_s)
    print(f"  IS:  {len(is_s)}件 / {h_i}的中 / ROI {roi_i:.1f}% / {pr_i:+,}円")
    print(f"  OOS: {len(oos_s)}件 / {h_o}的中 / ROI {roi_o:.1f}% / {pr_o:+,}円")
    print(f"\n  年度別:")
    for y in [2020,2021,2022,2023,2024,2025]:
        s = f12_150_200[f12_150_200['year']==y]
        n,h,hr,roi,pr = stats(s)
        mk = '○' if pr>0 else '×'
        print(f"  {y}: {n}件/{h}的中/ROI {roi:.1f}%/{pr:+,}円 {mk}")

    # ================================================================
    # 最終判断
    # ================================================================
    print("\n" + "="*60)
    print("【最終判断】")
    print("="*60)

    cands = [
        ("ベースライン（フィルタなし）", df),
        ("F1のみ（スコア80-90）", df[(df['score']>=80)&(df['score']<90)]),
        ("F1+F2", f12),
        ("F1+F2+F3保守（100-300倍）", f12_con),
        ("F1+F2+F3積極（100-150+200-300）", f12_agg),
    ]

    print(f"\n  {'条件':>34}|IS件|IS ROI|IS収支|OOS件|OOS ROI|OOS収支|6年黒字")
    print(f"  {'-'*80}")
    for label, d in cands:
        is_d = d[d['period']=='IS']; oos_d = d[d['period']=='OOS']
        ni,hi,_,roi_i,pr_i = stats(is_d)
        no,ho,_,roi_o,pr_o = stats(oos_d)
        black = sum(1 for y in [2020,2021,2022,2023,2024,2025]
                    if stats(d[d['year']==y])[4]>0)
        mi='★' if roi_i>=100 else ''; mo='★' if roi_o>=100 else ''
        print(f"  {label:>34}|{ni:>4}|{roi_i:>5.0f}%{mi}|{pr_i:>+7,}|{no:>4}|{roi_o:>6.0f}%{mo}|{pr_o:>+7,}|{black}/6")

    conn.close()
    print("\n完了")

if __name__ == '__main__':
    main()
