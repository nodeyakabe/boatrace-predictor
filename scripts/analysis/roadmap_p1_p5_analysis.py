"""
ロードマップP1-P5 検証スクリプト
roadmap_p1_p5_analysis.py

P1: 会場フィルター精緻化（直近3年トレンド確認）
P2: 2-1-X逆転パターンのROI試算
P3: オッズ帯細分化（50-65 vs 65-100）
P4: avg_stスコアリング現状確認
P5: B×100-200倍+会場フィルター適用
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
VENUE_11 = [4, 7, 19, 22, 2, 17, 21, 11, 8, 1, 9]
VENUE_NAMES = {
    1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川",
    6: "浜名湖", 7: "蒲郡", 8: "常滑", 9: "津", 10: "三国",
    11: "びわこ", 12: "住之江", 13: "尼崎", 14: "鳴門", 15: "丸亀",
    16: "児島", 17: "宮島", 18: "徳山", 19: "下関", 20: "若松",
    21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村"
}
MONTH_EXCL = [12, 1, 2, 4]
v_str = ",".join(str(v) for v in VENUE_11)
m_str = ",".join(str(m) for m in MONTH_EXCL)

# メインCTE（前予測、rp集約版）
BASE_Q = """
WITH rp AS (
    SELECT race_id,
        MAX(CASE WHEN rank_prediction=1 THEN pit_number END) as p1,
        MAX(CASE WHEN rank_prediction=2 THEN pit_number END) as p2,
        MAX(CASE WHEN rank_prediction=3 THEN pit_number END) as p3,
        MAX(CASE WHEN rank_prediction=4 THEN pit_number END) as p4,
        MAX(CASE WHEN rank_prediction=5 THEN pit_number END) as p5,
        MAX(CASE WHEN rank_prediction=1 THEN confidence END) as confidence,
        MAX(CASE WHEN rank_prediction=1 THEN total_score END) as score1,
        MAX(CASE WHEN rank_prediction=2 THEN total_score END) as score2
    FROM race_predictions
    WHERE prediction_type = 'before'
    GROUP BY race_id
),
actual AS (
    SELECT r1.race_id, r1.pit_number as a1, r2.pit_number as a2, r3.pit_number as a3
    FROM results r1
    JOIN results r2 ON r1.race_id=r2.race_id AND r2.rank='2'
    JOIN results r3 ON r1.race_id=r3.race_id AND r3.rank='3'
    WHERE r1.rank='1' AND r1.is_invalid=0 AND r2.is_invalid=0 AND r3.is_invalid=0
)
"""


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    return conn


# ================================================================
# P1: 会場フィルター精緻化
# ================================================================
def analyze_p1(conn):
    print("=" * 70)
    print("P1: B×50-100帯 全会場成績（月除外なし、全c1_rankを対象）")
    print("=" * 70)

    q = BASE_Q + """
    SELECT r.venue_code,
        CAST(strftime('%Y', r.race_date) AS INT) as year,
        COUNT(*) as total,
        SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN 1 ELSE 0 END) as hits,
        ROUND((SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN t.odds*100 ELSE 0 END)
               - COUNT(*)*100.0) / (COUNT(*)*100.0)*100+100, 1) as roi,
        ROUND(SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN t.odds*100 ELSE -100 END), 0) as pnl
    FROM races r
    JOIN rp ON r.id=rp.race_id
    JOIN actual ON r.id=actual.race_id
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    WHERE rp.confidence='B'
      AND t.odds BETWEEN 50 AND 100
      AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    GROUP BY r.venue_code, year
    ORDER BY r.venue_code, year
    """
    df = pd.read_sql_query(q, conn)

    print(f"\n{'会場':<8} {'採用':^4} {'6年件数':>7} {'6年ROI':>8} {'6年収支':>10} {'23-25件数':>9} {'23-25ROI':>9} {'23-25収支':>10}")
    print("-" * 74)
    new_candidates = []
    dropping_candidates = []

    for vc in sorted(df["venue_code"].unique()):
        vdf = df[df["venue_code"] == vc]
        tot6 = vdf["total"].sum()
        pnl6 = vdf["pnl"].sum()
        roi6 = (pnl6 + tot6 * 100) / (tot6 * 100) * 100 if tot6 > 0 else 0

        recent = vdf[vdf["year"] >= 2023]
        tot3 = recent["total"].sum()
        pnl3 = recent["pnl"].sum()
        roi3 = (pnl3 + tot3 * 100) / (tot3 * 100) * 100 if tot3 > 0 else 0

        adopted = "O" if int(vc) in VENUE_11 else "X"
        vname = VENUE_NAMES.get(int(vc), str(vc))
        flag = ""
        if adopted == "X" and roi6 > 150 and roi3 > 150 and tot6 >= 15:
            flag = " <-- 追加候補"
            new_candidates.append((vname, tot6, roi6, tot3, roi3))
        elif adopted == "O" and roi3 < 100 and tot3 >= 10:
            flag = " <-- 除外検討"
            dropping_candidates.append((vname, tot6, roi6, tot3, roi3))

        print(f"{vname:<8} {adopted:^4} {int(tot6):>7} {roi6:>7.1f}% {pnl6:>+10.0f}"
              f" {int(tot3):>9} {roi3:>8.1f}% {pnl3:>+10.0f}{flag}")

    print()
    if new_candidates:
        print("【追加候補（現在除外・ROI>150%・6年15件以上）】")
        for v, t6, r6, t3, r3 in new_candidates:
            print(f"  {v}: 6年{t6}件/ROI{r6:.1f}%, 直近3年{t3}件/ROI{r3:.1f}%")
    else:
        print("【追加候補】該当なし")

    if dropping_candidates:
        print()
        print("【除外検討（現在採用・直近3年ROI<100%）】")
        for v, t6, r6, t3, r3 in dropping_candidates:
            print(f"  {v}: 6年{t6}件/ROI{r6:.1f}%, 直近3年{t3}件/ROI{r3:.1f}%")


# ================================================================
# P2: 逆転パターン分析
# ================================================================
def analyze_p2(conn):
    print("\n" + "=" * 70)
    print("P2: 2-1-X逆転パターン分析（B×50-100、11会場、月除外）")
    print("=" * 70)

    q = BASE_Q + f"""
    SELECT rp.p1, rp.p2, rp.p3, rp.p4, rp.p5,
        actual.a1, actual.a2, actual.a3,
        t12_3.odds as o_12_3, t12_4.odds as o_12_4, t12_5.odds as o_12_5,
        t21_3.odds as o_21_3, t21_4.odds as o_21_4, t21_5.odds as o_21_5,
        CAST(strftime('%Y', r.race_date) AS INT) as year
    FROM races r
    JOIN rp ON r.id=rp.race_id
    JOIN actual ON r.id=actual.race_id
    LEFT JOIN trifecta_odds t12_3 ON r.id=t12_3.race_id AND t12_3.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    LEFT JOIN trifecta_odds t12_4 ON r.id=t12_4.race_id AND t12_4.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p4 AS TEXT)
    LEFT JOIN trifecta_odds t12_5 ON r.id=t12_5.race_id AND t12_5.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p5 AS TEXT)
    LEFT JOIN trifecta_odds t21_3 ON r.id=t21_3.race_id AND t21_3.combination=CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    LEFT JOIN trifecta_odds t21_4 ON r.id=t21_4.race_id AND t21_4.combination=CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p4 AS TEXT)
    LEFT JOIN trifecta_odds t21_5 ON r.id=t21_5.race_id AND t21_5.combination=CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p5 AS TEXT)
    WHERE r.venue_code IN ({v_str})
      AND CAST(strftime('%m', r.race_date) AS INT) NOT IN ({m_str})
      AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    """
    df = pd.read_sql_query(q, conn)

    # 的中フラグ
    df["h12_3"] = (df["a1"] == df["p1"]) & (df["a2"] == df["p2"]) & (df["a3"] == df["p3"])
    df["h12_4"] = (df["a1"] == df["p1"]) & (df["a2"] == df["p2"]) & (df["a3"] == df["p4"])
    df["h12_5"] = (df["a1"] == df["p1"]) & (df["a2"] == df["p2"]) & (df["a3"] == df["p5"])
    df["h21_3"] = (df["a1"] == df["p2"]) & (df["a2"] == df["p1"]) & (df["a3"] == df["p3"])
    df["h21_4"] = (df["a1"] == df["p2"]) & (df["a2"] == df["p1"]) & (df["a3"] == df["p4"])
    df["h21_5"] = (df["a1"] == df["p2"]) & (df["a2"] == df["p1"]) & (df["a3"] == df["p5"])
    df["rev"] = (df["a1"] == df["p2"]) & (df["a2"] == df["p1"])

    # B×50-100に絞る（p1-p2-p3のオッズ基準）
    df50 = df[(df["o_12_3"] >= 50) & (df["o_12_3"] <= 100)].copy()
    n50 = len(df50)

    print(f"\n全信頼度対象レース: {len(df)}件")
    print(f"逆転（1位2位入替）発生: {df.rev.sum()}件 ({100*df.rev.mean():.1f}%)")
    print(f"B×50-100倍絞り込み: {n50}件")

    def calc(sub, hc, oc):
        s = sub.dropna(subset=[oc])
        h = int(s[hc].sum())
        n = len(s)
        if h > 0:
            ao = s.loc[s[hc], oc].mean()
        else:
            ao = 0
        pnl = s.loc[s[hc], oc].sum() * 100 - n * 100
        roi = (pnl + n * 100) / (n * 100) * 100 if n > 0 else 0
        return h, n, ao, pnl, roi

    print("\n【現行パターンH（p1-p2-X）】")
    p_curr = 0
    for lbl, hc, oc in [("p1-p2-p3", "h12_3", "o_12_3"), ("p1-p2-p4", "h12_4", "o_12_4"), ("p1-p2-p5", "h12_5", "o_12_5")]:
        h, n, ao, pnl, roi = calc(df50, hc, oc)
        hit_str = f"avg{ao:.1f}x" if h > 0 else "N/A"
        print(f"  {lbl}: {n}件 的中{h}件({100*h/n:.2f}%) {hit_str} ROI{roi:.1f}% {pnl:+.0f}円")
        sub = df50.dropna(subset=[oc])
        p_curr += sub.loc[sub[hc], oc].sum() * 100
    inv_curr = n50 * 300
    print(f"  合計（3点300円/R）: ROI {p_curr/inv_curr*100:.1f}%, {p_curr-inv_curr:+.0f}円")

    print("\n【逆転パターン（p2-p1-X）】")
    p_rev = 0
    for lbl, hc, oc in [("p2-p1-p3", "h21_3", "o_21_3"), ("p2-p1-p4", "h21_4", "o_21_4"), ("p2-p1-p5", "h21_5", "o_21_5")]:
        h, n, ao, pnl, roi = calc(df50, hc, oc)
        hit_str = f"avg{ao:.1f}x" if h > 0 else "N/A"
        print(f"  {lbl}: {n}件 的中{h}件({100*h/n:.2f}%) {hit_str} ROI{roi:.1f}% {pnl:+.0f}円")
        sub = df50.dropna(subset=[oc])
        p_rev += sub.loc[sub[hc], oc].sum() * 100
    inv_rev_only = n50 * 300  # 逆転3点のみの場合

    print("\n【ROI比較試算】")
    inv_a = n50 * 600
    pnl_curr = p_curr - inv_curr
    pnl_a = p_curr + p_rev - inv_a
    pnl_rev_only = p_rev - inv_rev_only
    print(f"  現行（3点/300円）: ROI {p_curr/inv_curr*100:.1f}%, {pnl_curr:+.0f}円")
    print(f"  逆転のみ（3点/300円）: ROI {p_rev/inv_rev_only*100:.1f}%, {pnl_rev_only:+.0f}円")
    print(f"  拡張A（6点/600円）: ROI {(p_curr+p_rev)/inv_a*100:.1f}%, {pnl_a:+.0f}円")
    print(f"  逆転追加収入: +{p_rev:.0f}円 / 追加投資: +{inv_a-inv_curr:.0f}円")
    print(f"  差引効果: {pnl_a-pnl_curr:+.0f}円 / ROI変化: {(p_curr+p_rev)/inv_a*100-p_curr/inv_curr*100:+.1f}pt")

    # 年度別安定性
    print("\n【年度別 逆転パターン的中数】")
    for yr in sorted(df50["year"].unique()):
        ydf = df50[df50["year"] == yr]
        h21 = int((ydf["h21_3"] | ydf["h21_4"] | ydf["h21_5"]).sum())
        h12 = int((ydf["h12_3"] | ydf["h12_4"] | ydf["h12_5"]).sum())
        n = len(ydf)
        print(f"  {yr}: {n}件 現行的中{h12}件 逆転的中{h21}件")


# ================================================================
# P3: オッズ帯細分化
# ================================================================
def analyze_p3(conn):
    print("\n" + "=" * 70)
    print("P3: B×50-100帯 オッズ帯細分化（11会場、月除外）")
    print("=" * 70)

    q = BASE_Q + f"""
    SELECT
        CASE
            WHEN t.odds < 60 THEN '50-59x'
            WHEN t.odds < 70 THEN '60-69x'
            WHEN t.odds < 80 THEN '70-79x'
            WHEN t.odds < 90 THEN '80-89x'
            ELSE '90-100x'
        END as odds_band,
        t.odds,
        rp.p1, rp.p2, rp.p3,
        actual.a1, actual.a2, actual.a3,
        CAST(strftime('%Y', r.race_date) AS INT) as year
    FROM races r
    JOIN rp ON r.id=rp.race_id
    JOIN actual ON r.id=actual.race_id
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    WHERE rp.confidence='B'
      AND t.odds BETWEEN 50 AND 100
      AND r.venue_code IN ({v_str})
      AND CAST(strftime('%m', r.race_date) AS INT) NOT IN ({m_str})
      AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    """
    df = pd.read_sql_query(q, conn)
    df["hit"] = (df["a1"] == df["p1"]) & (df["a2"] == df["p2"]) & (df["a3"] == df["p3"])

    print(f"\n{'オッズ帯':<10} {'件数':>6} {'的中':>5} {'的中率':>7} {'平均オッズ':>10} {'ROI':>7} {'収支':>10}")
    print("-" * 60)

    bands = ["50-59x", "60-69x", "70-79x", "80-89x", "90-100x"]
    for band in bands:
        sub = df[df["odds_band"] == band]
        n = len(sub)
        h = int(sub["hit"].sum())
        avg_o = sub["odds"].mean()
        pnl = sub[sub["hit"]]["odds"].sum() * 100 - n * 100
        roi = (pnl + n * 100) / (n * 100) * 100 if n > 0 else 0
        print(f"{band:<10} {n:>6} {h:>5} {100*h/n:>6.2f}% {avg_o:>9.1f}x {roi:>6.1f}% {pnl:>+10.0f}円")

    # 2分割比較
    print()
    print("【50-65 vs 65-100 分割】")
    for lo, hi, lbl in [(50, 65, "50-65x"), (65, 100, "65-100x")]:
        sub = df[(df["odds"] >= lo) & (df["odds"] <= hi)]
        n = len(sub)
        h = int(sub["hit"].sum())
        pnl = sub[sub["hit"]]["odds"].sum() * 100 - n * 100
        roi = (pnl + n * 100) / (n * 100) * 100 if n > 0 else 0
        print(f"  {lbl}: {n}件, 的中{h}件({100*h/n:.2f}%), ROI {roi:.1f}%, {pnl:+.0f}円")


# ================================================================
# P4: avg_stスコアリング現状確認
# ================================================================
def analyze_p4(conn):
    print("\n" + "=" * 70)
    print("P4: avg_st別成績（B×50-100、11会場、月除外）")
    print("ExtendedScorerでの活用状況と最適化余地の確認")
    print("=" * 70)

    q = BASE_Q + f"""
    SELECT e.avg_st as p1_avg_st,
        rp.p1, rp.p2, rp.p3,
        actual.a1, actual.a2, actual.a3,
        t.odds,
        CAST(strftime('%Y', r.race_date) AS INT) as year
    FROM races r
    JOIN rp ON r.id=rp.race_id
    JOIN actual ON r.id=actual.race_id
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    LEFT JOIN entries e ON r.id=e.race_id AND e.pit_number=rp.p1
    WHERE rp.confidence='B'
      AND t.odds BETWEEN 50 AND 100
      AND r.venue_code IN ({v_str})
      AND CAST(strftime('%m', r.race_date) AS INT) NOT IN ({m_str})
      AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    """
    df = pd.read_sql_query(q, conn)
    df["hit"] = (df["a1"] == df["p1"]) & (df["a2"] == df["p2"]) & (df["a3"] == df["p3"])

    print(f"\n対象: {len(df)}件")

    bins = [0, 0.15, 0.17, 0.19, 0.21, 1.0]
    labels = ["<=0.15", "0.15-0.17", "0.17-0.19", "0.19-0.21", "0.21+"]
    df["avg_st_band"] = pd.cut(df["p1_avg_st"].fillna(-1), bins=bins, labels=labels, right=True)

    print(f"\n{'avg_st帯':<12} {'件数':>6} {'的中':>5} {'的中率':>7} {'平均オッズ':>10} {'ROI':>7} {'収支':>10}")
    print("-" * 65)
    for band in labels:
        sub = df[df["avg_st_band"] == band]
        n = len(sub)
        if n == 0:
            continue
        h = int(sub["hit"].sum())
        avg_o = sub["odds"].mean()
        pnl = sub[sub["hit"]]["odds"].sum() * 100 - n * 100
        roi = (pnl + n * 100) / (n * 100) * 100
        print(f"{band:<12} {n:>6} {h:>5} {100*h/n:>6.2f}% {avg_o:>9.1f}x {roi:>6.1f}% {pnl:>+10.0f}円")

    na_n = df[df["p1_avg_st"].isna()].shape[0]
    print(f"avg_stなし     {na_n:>6}件（entries未参照）")


# ================================================================
# P5: B×100-200倍 会場フィルター適用
# ================================================================
def analyze_p5(conn):
    print("\n" + "=" * 70)
    print("P5: B×100-200倍 全会場成績 + 会場フィルター適用検討")
    print("=" * 70)

    # 全会場成績（6年・直近3年）
    q = BASE_Q + """
    SELECT r.venue_code,
        CAST(strftime('%Y', r.race_date) AS INT) as year,
        COUNT(*) as total,
        SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN 1 ELSE 0 END) as hits,
        ROUND((SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN t.odds*100 ELSE 0 END)
               - COUNT(*)*100.0) / (COUNT(*)*100.0)*100+100, 1) as roi,
        ROUND(SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN t.odds*100 ELSE -100 END), 0) as pnl
    FROM races r
    JOIN rp ON r.id=rp.race_id
    JOIN actual ON r.id=actual.race_id
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    WHERE rp.confidence='B'
      AND t.odds BETWEEN 100 AND 200
      AND CAST(strftime('%m', r.race_date) AS INT) NOT IN (12,1,2,4)
      AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    GROUP BY r.venue_code, year
    ORDER BY r.venue_code, year
    """
    df = pd.read_sql_query(q, conn)

    print(f"\n{'会場':<8} {'6年件数':>7} {'6年ROI':>8} {'6年収支':>10} {'23-25件数':>9} {'23-25ROI':>9} {'23-25収支':>10} {'黒字年':>6}")
    print("-" * 74)

    good_venues = []
    for vc in sorted(df["venue_code"].unique()):
        vdf = df[df["venue_code"] == vc]
        tot6 = vdf["total"].sum()
        pnl6 = vdf["pnl"].sum()
        roi6 = (pnl6 + tot6 * 100) / (tot6 * 100) * 100 if tot6 > 0 else 0
        black_yr = sum(1 for _, row in vdf.iterrows() if row["pnl"] > 0)
        total_yr = len(vdf)

        recent = vdf[vdf["year"] >= 2023]
        tot3 = recent["total"].sum()
        pnl3 = recent["pnl"].sum()
        roi3 = (pnl3 + tot3 * 100) / (tot3 * 100) * 100 if tot3 > 0 else 0

        vname = VENUE_NAMES.get(int(vc), str(vc))

        flag = ""
        if roi6 > 150 and tot6 >= 10 and roi3 > 100:
            flag = " <--候補"
            good_venues.append(int(vc))

        print(f"{vname:<8} {int(tot6):>7} {roi6:>7.1f}% {pnl6:>+10.0f}"
              f" {int(tot3):>9} {roi3:>8.1f}% {pnl3:>+10.0f} {black_yr}/{total_yr}年{flag}")

    if good_venues:
        print(f"\n【候補会場でのB×100-200倍 6年成績】")
        gv_str = ",".join(str(v) for v in good_venues)
        q2 = BASE_Q + f"""
        SELECT CAST(strftime('%Y', r.race_date) AS INT) as year,
            COUNT(*) as total,
            SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN 1 ELSE 0 END) as hits,
            ROUND((SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN t.odds*100 ELSE 0 END)
                   - COUNT(*)*100.0) / (COUNT(*)*100.0)*100+100, 1) as roi,
            ROUND(SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN t.odds*100 ELSE -100 END), 0) as pnl
        FROM races r
        JOIN rp ON r.id=rp.race_id
        JOIN actual ON r.id=actual.race_id
        JOIN trifecta_odds t ON r.id=t.race_id
            AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
        WHERE rp.confidence='B'
          AND t.odds BETWEEN 100 AND 200
          AND r.venue_code IN ({gv_str})
          AND CAST(strftime('%m', r.race_date) AS INT) NOT IN (12,1,2,4)
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        GROUP BY year
        ORDER BY year
        """
        df2 = pd.read_sql_query(q2, conn)
        tot = df2["total"].sum()
        pnl_tot = df2["pnl"].sum()
        roi_tot = (pnl_tot + tot * 100) / (tot * 100) * 100 if tot > 0 else 0
        black = sum(1 for _, r in df2.iterrows() if r["pnl"] > 0)

        vnames = [VENUE_NAMES.get(v, str(v)) for v in good_venues]
        print(f"  対象会場: {', '.join(vnames)}")
        print(f"  6年合計: {tot}件, ROI {roi_tot:.1f}%, {pnl_tot:+.0f}円, 黒字{black}/{len(df2)}年")
        print(f"\n  年度別:")
        for _, row in df2.iterrows():
            mark = "○" if row["pnl"] > 0 else "×"
            print(f"    {int(row.year)}: {int(row.total)}件, ROI {row.roi:.1f}%, {row.pnl:+.0f}円 {mark}")

        # Tier1基準確認（2024-2025）
        df24_25 = df2[df2["year"].isin([2024, 2025])]
        t24_25 = df24_25["total"].sum()
        p24_25 = df24_25["pnl"].sum()
        r24_25 = (p24_25 + t24_25 * 100) / (t24_25 * 100) * 100 if t24_25 > 0 else 0
        b24_25 = sum(1 for _, r in df24_25.iterrows() if r["pnl"] > 0)
        print(f"\n  【Tier1基準（2024-2025）】")
        print(f"    件数: {int(t24_25)}件 (基準50件+)")
        print(f"    ROI: {r24_25:.1f}% (基準150%+)")
        print(f"    黒字: {b24_25}/2年 (基準1年+)")
        tier1_pass = r24_25 >= 150 and b24_25 >= 1 and t24_25 >= 50
        print(f"    判定: {'合格' if tier1_pass else '不合格'}")


def main():
    print("=" * 70)
    print("ロードマップP1-P5 検証分析")
    print("対象: B×50-100、11会場フィルター、月除外 2020-2025")
    print("=" * 70)

    conn = get_conn()
    try:
        analyze_p1(conn)
        analyze_p2(conn)
        analyze_p3(conn)
        analyze_p4(conn)
        analyze_p5(conn)
    finally:
        conn.close()

    print("\n" + "=" * 70)
    print("分析完了")
    print("=" * 70)


if __name__ == "__main__":
    main()
