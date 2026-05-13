"""
P2 逆転パターン 差し率（コース2勝率）活性化条件分析
"""
import sqlite3
import pandas as pd
import json
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

SQL = """
WITH rp AS (
    SELECT race_id,
        MAX(CASE WHEN rank_prediction=1 THEN pit_number END) as p1,
        MAX(CASE WHEN rank_prediction=2 THEN pit_number END) as p2,
        MAX(CASE WHEN rank_prediction=3 THEN pit_number END) as p3,
        MAX(CASE WHEN rank_prediction=4 THEN pit_number END) as p4,
        MAX(CASE WHEN rank_prediction=5 THEN pit_number END) as p5,
        MAX(CASE WHEN rank_prediction=1 THEN confidence END) as conf,
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
SELECT rp.conf, rp.score1, rp.score2, (rp.score1-rp.score2) as sc_diff,
    actual.a1, actual.a2, actual.a3, rp.p1, rp.p2, rp.p3, rp.p4, rp.p5,
    t12.odds as o12,
    t21_3.odds as o21_3, t21_4.odds as o21_4, t21_5.odds as o21_5,
    e1.avg_st as p1_st, e2.avg_st as p2_st,
    rap.course_win_rates as p2_cwins,
    r.venue_code,
    CAST(strftime('%Y', r.race_date) AS INT) as year
FROM races r
JOIN rp ON r.id=rp.race_id
JOIN actual ON r.id=actual.race_id
JOIN trifecta_odds t12 ON r.id=t12.race_id
    AND t12.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
LEFT JOIN trifecta_odds t21_3 ON r.id=t21_3.race_id
    AND t21_3.combination=CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
LEFT JOIN trifecta_odds t21_4 ON r.id=t21_4.race_id
    AND t21_4.combination=CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p4 AS TEXT)
LEFT JOIN trifecta_odds t21_5 ON r.id=t21_5.race_id
    AND t21_5.combination=CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p5 AS TEXT)
LEFT JOIN entries e1 ON r.id=e1.race_id AND e1.pit_number=rp.p1
LEFT JOIN entries e2 ON r.id=e2.race_id AND e2.pit_number=rp.p2
LEFT JOIN racer_attack_patterns rap ON CAST(e2.racer_number AS INTEGER)=rap.racer_number
WHERE rp.conf='B'
  AND t12.odds BETWEEN 50 AND 100
  AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
"""


def get_c2(s):
    try:
        return json.loads(s).get("2", None)
    except Exception:
        return None


def roi_rev(sub):
    n = len(sub)
    if n == 0:
        return 0, 0, 0.0, 0.0
    w = 0.0
    w += sub.loc[sub["rev_3"], "o21_3"].dropna().sum() * 100
    w += sub.loc[sub["rev_4"], "o21_4"].dropna().sum() * 100
    w += sub.loc[sub["rev_5"], "o21_5"].dropna().sum() * 100
    inv = n * 300
    pnl = w - inv
    roi = (pnl + inv) / inv * 100
    return n, int(sub["reversal"].sum()), roi, pnl


def main():
    conn = sqlite3.connect(str(DB_PATH))
    df = pd.read_sql_query(SQL, conn)
    conn.close()

    df["p2_c2"] = df["p2_cwins"].apply(get_c2)
    df["rev_3"] = (df["a1"] == df["p2"]) & (df["a2"] == df["p1"]) & (df["a3"] == df["p3"])
    df["rev_4"] = (df["a1"] == df["p2"]) & (df["a2"] == df["p1"]) & (df["a3"] == df["p4"])
    df["rev_5"] = (df["a1"] == df["p2"]) & (df["a2"] == df["p1"]) & (df["a3"] == df["p5"])
    df["reversal"] = df["rev_3"] | df["rev_4"] | df["rev_5"]
    df["st_diff"] = df["p2_st"] - df["p1_st"]

    lines = []
    lines.append(f"B x50-100 all venues all months: {len(df)} races")
    lines.append(f"p2_c2 available: {df.p2_c2.notna().sum()}")
    lines.append(f"Reversals: {df.reversal.sum()} ({100*df.reversal.mean():.1f}%)")

    # --- コース2勝率帯別 逆転率 ---
    lines.append("")
    lines.append("--- p2 Course2 WinRate (sashi proxy) bands ---")
    lines.append(f"{'Band':<12} {'N':>5} {'Rev':>5} {'RevRate':>8}  {'AvgC2':>7}")
    df_v = df[df.p2_c2.notna()].copy()
    df_v["c2b"] = pd.cut(
        df_v["p2_c2"], bins=[-0.001, 0.05, 0.10, 0.15, 0.20, 1.0],
        labels=["0-5%", "5-10%", "10-15%", "15-20%", "20%+"]
    )
    for band in ["0-5%", "5-10%", "10-15%", "15-20%", "20%+"]:
        sub = df_v[df_v["c2b"] == band]
        ns = len(sub)
        rv = int(sub["reversal"].sum()) if ns > 0 else 0
        rr = 100 * rv / ns if ns > 0 else 0
        ac = sub["p2_c2"].mean() if ns > 0 else 0
        lines.append(f"{band:<12} {ns:>5} {rv:>5} {rr:>7.1f}%  {ac:>7.3f}")

    # --- スコア差帯別 逆転率 ---
    lines.append("")
    lines.append("--- Score gap (p1-p2) bands ---")
    lines.append(f"{'Band':<14} {'N':>5} {'Rev':>5} {'RevRate':>8}")
    df["sc_band"] = pd.cut(
        df["sc_diff"], bins=[-200, 0, 10, 20, 30, 50, 500],
        labels=["p2_better", "0-10", "10-20", "20-30", "30-50", "50+"]
    )
    for band in ["p2_better", "0-10", "10-20", "20-30", "30-50", "50+"]:
        sub = df[df["sc_band"] == band]
        ns = len(sub)
        rv = int(sub["reversal"].sum()) if ns > 0 else 0
        rr = 100 * rv / ns if ns > 0 else 0
        lines.append(f"{band:<14} {ns:>5} {rv:>5} {rr:>7.1f}%")

    # --- 活性化条件組み合わせ ROI ---
    lines.append("")
    lines.append("--- Activation conditions ROI analysis (reversal 3pts/300yen per race) ---")
    lines.append(f"{'Condition':<35} {'N':>5} {'Hits':>5} {'RevRate':>8} {'ROI':>8} {'PnL':>12}")
    lines.append("-" * 78)

    cond_sc20 = df["sc_diff"] < 20
    cond_sc30 = df["sc_diff"] < 30
    cond_c2_15 = df["p2_c2"] >= 0.15
    cond_c2_20 = df["p2_c2"] >= 0.20
    cond_st = df["st_diff"] < 0

    cond_list = [
        ("ALL_baseline", pd.Series(True, index=df.index)),
        ("sc_diff<20", cond_sc20),
        ("sc_diff<30", cond_sc30),
        ("c2>=15pct", cond_c2_15),
        ("c2>=20pct", cond_c2_20),
        ("st_diff<0(p2_faster)", cond_st),
        ("sc<20+c2>=15", cond_sc20 & cond_c2_15),
        ("sc<20+c2>=20", cond_sc20 & cond_c2_20),
        ("sc<20+st<0", cond_sc20 & cond_st),
        ("sc<20+c2>=15+st<0", cond_sc20 & cond_c2_15 & cond_st),
        ("sc<30+c2>=15", cond_sc30 & cond_c2_15),
        ("sc<30+c2>=20", cond_sc30 & cond_c2_20),
        ("sc<30+st<0", cond_sc30 & cond_st),
        ("sc<30+c2>=15+st<0", cond_sc30 & cond_c2_15 & cond_st),
    ]

    for name, cond in cond_list:
        n, h, roi, pnl = roi_rev(df[cond])
        rr = 100 * h / n if n > 0 else 0
        lines.append(f"{name:<35} {n:>5} {h:>5} {rr:>7.1f}% {roi:>7.1f}% {pnl:>+12.0f}")

    # --- 最有望条件の年度別確認 (sc<20) ---
    lines.append("")
    lines.append("--- Year-by-year: sc_diff<20 ---")
    sub20 = df[cond_sc20]
    for yr in sorted(df["year"].unique()):
        ydf = sub20[sub20["year"] == yr]
        n, h, roi, pnl = roi_rev(ydf)
        lines.append(f"  {int(yr)}: {n}bets {h}hits ROI:{roi:.1f}% {pnl:+.0f}")

    # --- sc<20 + c2>=15 の年度別 ---
    lines.append("")
    lines.append("--- Year-by-year: sc<20+c2>=15 ---")
    sub_best = df[cond_sc20 & cond_c2_15]
    for yr in sorted(df["year"].unique()):
        ydf = sub_best[sub_best["year"] == yr]
        n, h, roi, pnl = roi_rev(ydf)
        lines.append(f"  {int(yr)}: {n}bets {h}hits ROI:{roi:.1f}% {pnl:+.0f}")

    # --- 11会場フィルター + 月除外 でのsc<20 ---
    VENUE_11 = [4, 7, 19, 22, 2, 17, 21, 11, 8, 1, 9]
    MONTH_EX = [12, 1, 2, 4]
    # venue_code を数値化してフィルター（文字列対応）
    df["vc_int"] = df["venue_code"].apply(lambda x: int(x) if pd.notna(x) else -1)
    cond_11v = df["vc_int"].isin(VENUE_11)
    cond_month = ~df["year"].isin([])  # monthは元クエリにないので近似スキップ

    lines.append("")
    lines.append("--- 11 venues filtered: sc<20 ---")
    sub_11v = df[cond_11v & cond_sc20]
    for yr in sorted(df["year"].unique()):
        ydf = sub_11v[sub_11v["year"] == yr]
        n, h, roi, pnl = roi_rev(ydf)
        lines.append(f"  {int(yr)}: {n}bets {h}hits ROI:{roi:.1f}% {pnl:+.0f}")
    n_tot, h_tot, roi_tot, pnl_tot = roi_rev(sub_11v)
    lines.append(f"  TOTAL: {n_tot}bets {h_tot}hits ROI:{roi_tot:.1f}% {pnl_tot:+.0f}")

    # 出力
    out = "\n".join(lines)
    out_path = Path(__file__).parent.parent.parent / "data" / "p2_sashi_result.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Written to {out_path}")
    print(out)


if __name__ == "__main__":
    main()
