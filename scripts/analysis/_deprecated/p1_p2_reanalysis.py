#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P1(会場フィルター)統計的信頼性 & P2(逆転パターン)条件付き分析
結果はファイルに出力（cp932環境対応）
"""

import sqlite3
import math
import os
import sys

# パスの設定
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data", "boatrace.db")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "p1_p2_reanalysis_result.txt")

# 現在の11会場リスト（bet_conditionsで使用中）
CURRENT_VENUES = [4, 5, 7, 9, 10, 14, 18, 19, 20, 21, 24]

# 会場名マッピング
VENUE_NAMES = {
    1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川",
    6: "浜名湖", 7: "蒲郡", 8: "常滑", 9: "津", 10: "三国",
    11: "びわこ", 12: "住之江", 13: "尼崎", 14: "鳴門", 15: "丸亀",
    16: "児島", 17: "宮島", 18: "徳山", 19: "下関", 20: "若松",
    21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村"
}


def wilson_ci(hits, n, z=1.96):
    """ウィルソン信頼区間を計算"""
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = hits / n
    denom = 1 + z * z / n
    center = (p_hat + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n)) / denom
    lower = max(0, center - margin)
    upper = min(1, center + margin)
    return p_hat, lower, upper


def min_sample_for_roi(avg_odds, target_roi=1.0, confidence=0.95):
    """
    平均オッズavg_oddsで、ROI >= target_roi を95%信頼区間の下限で確認するための最小サンプル数
    二項分布ベースの逆算
    """
    z = 1.96 if confidence == 0.95 else 1.645
    # 損益分岐的中率: 投資100円あたり avg_odds*100円の回収
    # ROI = hit_rate * avg_odds >= target_roi
    # -> hit_rate >= target_roi / avg_odds
    p_break = target_roi / avg_odds

    # ウィルソン信頼区間の下限 >= p_break となる最小n
    # 近似: p_hat = p_break * 1.2 (20%マージン) として必要nを逆算
    # 正確な計算: n = z^2 * p * (1-p) / E^2
    # ここでp = p_breakの推定値、E = p - p_break
    p_est = p_break * 1.3  # 30%マージン（実際に観測されそうな的中率）
    if p_est >= 1:
        return float('inf')
    margin_needed = p_est - p_break
    if margin_needed <= 0:
        return float('inf')
    n_needed = (z ** 2 * p_est * (1 - p_est)) / (margin_needed ** 2)
    return int(math.ceil(n_needed))


def run_p1_analysis(conn, out):
    """P1: 会場別統計的信頼性分析"""
    out.write("=" * 80 + "\n")
    out.write("=== P1 統計的信頼性分析 ===\n")
    out.write("=" * 80 + "\n\n")

    # ---- 1a. 会場別の統計的信頼性 ----
    out.write("-" * 60 + "\n")
    out.write("【1a】会場別 B x 50-100倍 信頼区間付き分析（2020-2025年, 6年間）\n")
    out.write("-" * 60 + "\n\n")

    query_venue = """
    WITH rp AS (
        SELECT race_id,
            MAX(CASE WHEN rank_prediction=1 THEN pit_number END) as p1,
            MAX(CASE WHEN rank_prediction=2 THEN pit_number END) as p2,
            MAX(CASE WHEN rank_prediction=3 THEN pit_number END) as p3,
            MAX(CASE WHEN rank_prediction=1 THEN confidence END) as conf
        FROM race_predictions
        WHERE prediction_type='before'
        GROUP BY race_id
    ),
    actual AS (
        SELECT r1.race_id, r1.pit_number as a1, r2.pit_number as a2, r3.pit_number as a3
        FROM results r1
        JOIN results r2 ON r1.race_id=r2.race_id AND r2.rank='2'
        JOIN results r3 ON r1.race_id=r3.race_id AND r3.rank='3'
        WHERE r1.rank='1' AND r1.is_invalid=0 AND r2.is_invalid=0 AND r3.is_invalid=0
    )
    SELECT r.venue_code, COUNT(*) as n,
        SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN t.odds*100 ELSE -100 END) as pnl,
        AVG(t.odds) as avg_odds
    FROM races r
    JOIN rp ON r.id=rp.race_id
    JOIN actual ON r.id=actual.race_id
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    WHERE rp.conf='B' AND t.odds BETWEEN 50 AND 100
      AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    GROUP BY r.venue_code
    ORDER BY r.venue_code
    """

    rows = conn.execute(query_venue).fetchall()

    # ヘッダー
    out.write(f"{'会場':>6s} {'n':>5s} {'hits':>5s} {'的中率':>8s} {'95%CI下限':>9s} {'95%CI上限':>9s} {'ROI':>8s} {'PnL':>10s} {'最小必要n':>9s} {'判定':>12s}\n")
    out.write("-" * 100 + "\n")

    venue_data = []
    for row in rows:
        vc, n, hits, pnl, avg_odds = row
        vname = VENUE_NAMES.get(vc, f"#{vc}")
        p_hat, ci_lo, ci_hi = wilson_ci(hits, n)
        roi = (pnl / (n * 100)) * 100 if n > 0 else 0  # ROI%

        # 損益分岐的中率
        p_break = 1.0 / avg_odds if avg_odds > 0 else 0

        # 95%CI下限でのROI
        roi_ci_lo = ci_lo * avg_odds * 100 if avg_odds > 0 else 0

        # 最小必要サンプル数
        min_n = min_sample_for_roi(avg_odds, target_roi=1.0)

        # ノイズ vs 傾向判定
        if n >= min_n and roi_ci_lo >= 100:
            judgment = "** 傾向 **"
        elif n >= 50 and roi > 100:
            judgment = "やや有望"
        elif n < 30:
            judgment = "不十分"
        elif roi <= 0:
            judgment = "劣勢"
        else:
            judgment = "ノイズ疑い"

        venue_data.append({
            'vc': vc, 'name': vname, 'n': n, 'hits': hits,
            'p_hat': p_hat, 'ci_lo': ci_lo, 'ci_hi': ci_hi,
            'roi': roi, 'pnl': pnl, 'min_n': min_n,
            'avg_odds': avg_odds, 'judgment': judgment,
            'roi_ci_lo': roi_ci_lo
        })

        in_current = "*" if vc in CURRENT_VENUES else " "
        out.write(f"{in_current}{vname:>5s} {n:5d} {hits:5d} {p_hat*100:7.2f}% [{ci_lo*100:6.2f}% - {ci_hi*100:6.2f}%] {roi:7.1f}% {pnl:+10.0f} {min_n:>9d} {judgment}\n")

    out.write("\n* = 現在採用中の11会場\n\n")

    # 解説
    out.write("【解説】\n")
    out.write("- 95%信頼区間: 真の的中率がこの範囲にある確率95%（ウィルソン法）\n")
    out.write("- 最小必要n: 95%CI下限でROI>=100%を確認するための理論的最小件数\n")
    out.write("- 判定基準: CI下限ROI>=100% → 傾向 / n>=50かつROI>100% → やや有望 / n<30 → 不十分\n\n")

    # 特に注目会場の詳細
    out.write("-" * 60 + "\n")
    out.write("【注目会場の詳細評価】\n")
    out.write("-" * 60 + "\n\n")

    focus_venues = [3, 15, 1]  # 江戸川, 丸亀, 桐生
    for vc in focus_venues:
        vd = next((v for v in venue_data if v['vc'] == vc), None)
        if vd:
            out.write(f"  {vd['name']}（コード{vc}）:\n")
            out.write(f"    件数: {vd['n']}件, 的中: {vd['hits']}件\n")
            out.write(f"    的中率: {vd['p_hat']*100:.2f}% [95%CI: {vd['ci_lo']*100:.2f}% - {vd['ci_hi']*100:.2f}%]\n")
            out.write(f"    ROI: {vd['roi']:.1f}%, 95%CI下限ROI: {vd['roi_ci_lo']:.1f}%\n")
            out.write(f"    平均オッズ: {vd['avg_odds']:.1f}倍, 損益分岐的中率: {1.0/vd['avg_odds']*100:.2f}%\n")
            out.write(f"    最小必要サンプル数: {vd['min_n']}件\n")
            out.write(f"    判定: {vd['judgment']}\n")

            # 1件的中の影響度
            if vd['n'] > 0:
                roi_if_one_less = ((vd['pnl'] - vd['avg_odds']*100 + 100) / (vd['n'] * 100)) * 100 if vd['hits'] > 0 else 0
                out.write(f"    的中1件減でのROI変化: {vd['roi']:.1f}% -> {roi_if_one_less:.1f}% (差: {roi_if_one_less - vd['roi']:+.1f}pt)\n")
            out.write("\n")

    # ---- 1b. 年度別一貫性分析 ----
    out.write("\n" + "-" * 60 + "\n")
    out.write("【1b】年度別一貫性分析（全会場 x 年度）\n")
    out.write("-" * 60 + "\n\n")

    query_yearly = """
    WITH rp AS (
        SELECT race_id,
            MAX(CASE WHEN rank_prediction=1 THEN pit_number END) as p1,
            MAX(CASE WHEN rank_prediction=2 THEN pit_number END) as p2,
            MAX(CASE WHEN rank_prediction=3 THEN pit_number END) as p3,
            MAX(CASE WHEN rank_prediction=1 THEN confidence END) as conf
        FROM race_predictions
        WHERE prediction_type='before'
        GROUP BY race_id
    ),
    actual AS (
        SELECT r1.race_id, r1.pit_number as a1, r2.pit_number as a2, r3.pit_number as a3
        FROM results r1
        JOIN results r2 ON r1.race_id=r2.race_id AND r2.rank='2'
        JOIN results r3 ON r1.race_id=r3.race_id AND r3.rank='3'
        WHERE r1.rank='1' AND r1.is_invalid=0 AND r2.is_invalid=0 AND r3.is_invalid=0
    )
    SELECT r.venue_code,
        SUBSTR(r.race_date, 1, 4) as year,
        COUNT(*) as n,
        SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN t.odds*100 ELSE -100 END) as pnl
    FROM races r
    JOIN rp ON r.id=rp.race_id
    JOIN actual ON r.id=actual.race_id
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    WHERE rp.conf='B' AND t.odds BETWEEN 50 AND 100
      AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    GROUP BY r.venue_code, year
    ORDER BY r.venue_code, year
    """

    yearly_rows = conn.execute(query_yearly).fetchall()

    # 会場ごとに年度別データを整理
    yearly_by_venue = {}
    for row in yearly_rows:
        vc, year, n, hits, pnl = row
        if vc not in yearly_by_venue:
            yearly_by_venue[vc] = {}
        yearly_by_venue[vc][year] = {'n': n, 'hits': hits, 'pnl': pnl}

    # 注目会場 + 全会場
    all_venues_sorted = sorted(yearly_by_venue.keys())
    years = ['2020', '2021', '2022', '2023', '2024', '2025']

    out.write(f"{'会場':>6s} ", )
    for y in years:
        out.write(f"| {y:>13s} ")
    out.write(f"| {'黒字年':>5s} | {'一貫性':>8s}\n")
    out.write("-" * 120 + "\n")

    for vc in all_venues_sorted:
        vname = VENUE_NAMES.get(vc, f"#{vc}")
        in_current = "*" if vc in CURRENT_VENUES else " "
        out.write(f"{in_current}{vname:>5s} ")

        profit_years = 0
        total_years_with_data = 0
        for y in years:
            data = yearly_by_venue[vc].get(y, None)
            if data and data['n'] > 0:
                roi = (data['pnl'] / (data['n'] * 100)) * 100
                mark = "+" if data['pnl'] > 0 else "-"
                out.write(f"| {data['n']:3d}件 {roi:6.0f}%{mark} ")
                if data['pnl'] > 0:
                    profit_years += 1
                total_years_with_data += 1
            else:
                out.write(f"|   {'---':>10s} ")

        consistency = "高" if profit_years >= 4 else ("中" if profit_years >= 3 else "低")
        out.write(f"| {profit_years}/{total_years_with_data}年 | {consistency}\n")

    out.write("\n* = 現在採用中の11会場, + = 黒字年, - = 赤字年\n\n")

    # 注目3会場の年度パターン詳細
    out.write("【注目3会場の年度別詳細】\n\n")
    for vc in [3, 15, 1]:  # 江戸川, 丸亀, 桐生
        vname = VENUE_NAMES.get(vc, f"#{vc}")
        out.write(f"  {vname}:\n")
        data_years = yearly_by_venue.get(vc, {})
        hit_years = 0
        miss_years = 0
        for y in years:
            d = data_years.get(y, None)
            if d:
                roi = (d['pnl'] / (d['n'] * 100)) * 100 if d['n'] > 0 else 0
                out.write(f"    {y}: {d['n']}件, {d['hits']}的中, ROI {roi:.0f}%")
                if d['hits'] > 0:
                    out.write(f" (的中オッズ: 各{d['pnl']/100 + d['n']:.0f}円相当)")
                    hit_years += 1
                else:
                    miss_years += 1
                out.write("\n")
            else:
                out.write(f"    {y}: データなし\n")
        out.write(f"    -> 的中年: {hit_years}年, 不的中年: {miss_years}年\n")
        out.write(f"    -> 一貫性評価: {'各年に的中あり=傾向の兆候あり' if hit_years >= 4 else '的中が偏在=ノイズの疑い強い'}\n\n")

    # ---- 1c. プール比較 ----
    out.write("\n" + "-" * 60 + "\n")
    out.write("【1c】全会場プールでの統計的比較\n")
    out.write("-" * 60 + "\n\n")

    # 現在の11会場 vs 候補追加後
    candidate_add = [3, 15]  # 江戸川、丸亀
    candidate_remove = [1]  # 桐生（除外候補ではなく、桐生は既に11会場外なので確認）

    # まず「現在の11会場」プール成績
    query_pool = """
    WITH rp AS (
        SELECT race_id,
            MAX(CASE WHEN rank_prediction=1 THEN pit_number END) as p1,
            MAX(CASE WHEN rank_prediction=2 THEN pit_number END) as p2,
            MAX(CASE WHEN rank_prediction=3 THEN pit_number END) as p3,
            MAX(CASE WHEN rank_prediction=1 THEN confidence END) as conf
        FROM race_predictions
        WHERE prediction_type='before'
        GROUP BY race_id
    ),
    actual AS (
        SELECT r1.race_id, r1.pit_number as a1, r2.pit_number as a2, r3.pit_number as a3
        FROM results r1
        JOIN results r2 ON r1.race_id=r2.race_id AND r2.rank='2'
        JOIN results r3 ON r1.race_id=r3.race_id AND r3.rank='3'
        WHERE r1.rank='1' AND r1.is_invalid=0 AND r2.is_invalid=0 AND r3.is_invalid=0
    )
    SELECT
        CASE WHEN r.venue_code IN ({venues}) THEN 'IN' ELSE 'OUT' END as pool,
        COUNT(*) as n,
        SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN rp.p1=actual.a1 AND rp.p2=actual.a2 AND rp.p3=actual.a3 THEN t.odds*100 ELSE -100 END) as pnl,
        AVG(t.odds) as avg_odds
    FROM races r
    JOIN rp ON r.id=rp.race_id
    JOIN actual ON r.id=actual.race_id
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    WHERE rp.conf='B' AND t.odds BETWEEN 50 AND 100
      AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    GROUP BY pool
    """

    # 現在の11会場
    venues_str = ','.join(str(v) for v in CURRENT_VENUES)
    rows_current = conn.execute(query_pool.format(venues=venues_str)).fetchall()

    # 候補追加後（11 + 江戸川 + 丸亀 = 13会場）
    expanded_venues = CURRENT_VENUES + candidate_add
    venues_str_exp = ','.join(str(v) for v in expanded_venues)
    rows_expanded = conn.execute(query_pool.format(venues=venues_str_exp)).fetchall()

    out.write("プール比較:\n\n")
    out.write(f"{'プール':>20s} {'n':>6s} {'hits':>5s} {'的中率':>8s} {'ROI':>8s} {'PnL':>12s}\n")
    out.write("-" * 70 + "\n")

    for label, rows_data in [("現在11会場", rows_current), ("候補追加13会場", rows_expanded)]:
        for row in rows_data:
            pool_name, n, hits, pnl, avg_odds = row
            if pool_name == 'IN':
                p_hat = hits / n if n > 0 else 0
                roi = (pnl / (n * 100)) * 100 if n > 0 else 0
                out.write(f"{label + '(IN)':>20s} {n:6d} {hits:5d} {p_hat*100:7.2f}% {roi:7.1f}% {pnl:+12.0f}\n")

    # 全24会場
    all_venues_str = ','.join(str(v) for v in range(1, 25))
    rows_all = conn.execute(query_pool.format(venues=all_venues_str)).fetchall()
    for row in rows_all:
        pool_name, n, hits, pnl, avg_odds = row
        if pool_name == 'IN':
            p_hat = hits / n if n > 0 else 0
            roi = (pnl / (n * 100)) * 100 if n > 0 else 0
            out.write(f"{'全24会場':>20s} {n:6d} {hits:5d} {p_hat*100:7.2f}% {roi:7.1f}% {pnl:+12.0f}\n")

    out.write("\n")

    # 統計的検定: 2群の比較（現在11会場 vs 11会場外）
    out.write("【統計的検定】11会場(IN) vs 11会場外(OUT)の比較:\n\n")
    for row in rows_current:
        pool_name, n, hits, pnl, avg_odds = row
        if pool_name == 'IN':
            n_in, h_in, pnl_in = n, hits, pnl
        else:
            n_out, h_out, pnl_out = n, hits, pnl

    p_in = h_in / n_in if n_in > 0 else 0
    p_out = h_out / n_out if n_out > 0 else 0
    roi_in = (pnl_in / (n_in * 100)) * 100 if n_in > 0 else 0
    roi_out = (pnl_out / (n_out * 100)) * 100 if n_out > 0 else 0

    # 2群の比率の差の検定 (z検定)
    p_pooled = (h_in + h_out) / (n_in + n_out) if (n_in + n_out) > 0 else 0
    if p_pooled > 0 and p_pooled < 1:
        se = math.sqrt(p_pooled * (1 - p_pooled) * (1.0/n_in + 1.0/n_out))
        z_stat = (p_in - p_out) / se if se > 0 else 0
    else:
        z_stat = 0

    out.write(f"  11会場(IN):  n={n_in}, 的中率={p_in*100:.2f}%, ROI={roi_in:.1f}%\n")
    out.write(f"  11会場外(OUT): n={n_out}, 的中率={p_out*100:.2f}%, ROI={roi_out:.1f}%\n")
    out.write(f"  的中率差: {(p_in - p_out)*100:+.2f}pt\n")
    out.write(f"  z統計量: {z_stat:.3f}")
    if abs(z_stat) >= 1.96:
        out.write(" (p < 0.05, 有意差あり)\n")
    elif abs(z_stat) >= 1.645:
        out.write(" (p < 0.10, 弱い有意差)\n")
    else:
        out.write(" (有意差なし)\n")
    out.write("\n")

    return venue_data


def run_p2_analysis(conn, out):
    """P2: 条件付き逆転パターン分析"""
    out.write("\n\n" + "=" * 80 + "\n")
    out.write("=== P2 条件付き逆転パターン分析 ===\n")
    out.write("=" * 80 + "\n\n")

    # ---- 2a. 逆転発生時の選手特性 ----
    out.write("-" * 60 + "\n")
    out.write("【2a】逆転発生時 vs 非発生時の選手特性比較\n")
    out.write("-" * 60 + "\n\n")

    out.write("条件: B x 50-100倍, 11会場, 月除外(12,1,2,4)\n\n")

    # 除外月
    excluded_months = ['01', '02', '04', '12']
    month_filter = " AND SUBSTR(r.race_date, 6, 2) NOT IN ('01','02','04','12')"
    venues_str = ','.join(str(v) for v in CURRENT_VENUES)

    # 逆転: actual_1着=predicted_p2, actual_2着=predicted_p1 (p2-p1-X)
    query_reversal = f"""
    WITH rp AS (
        SELECT race_id,
            MAX(CASE WHEN rank_prediction=1 THEN pit_number END) as p1,
            MAX(CASE WHEN rank_prediction=2 THEN pit_number END) as p2,
            MAX(CASE WHEN rank_prediction=3 THEN pit_number END) as p3,
            MAX(CASE WHEN rank_prediction=1 THEN confidence END) as conf,
            MAX(CASE WHEN rank_prediction=1 THEN total_score END) as score_p1,
            MAX(CASE WHEN rank_prediction=2 THEN total_score END) as score_p2,
            MAX(CASE WHEN rank_prediction=3 THEN total_score END) as score_p3
        FROM race_predictions
        WHERE prediction_type='before'
        GROUP BY race_id
    ),
    actual AS (
        SELECT r1.race_id, r1.pit_number as a1, r2.pit_number as a2, r3.pit_number as a3
        FROM results r1
        JOIN results r2 ON r1.race_id=r2.race_id AND r2.rank='2'
        JOIN results r3 ON r1.race_id=r3.race_id AND r3.rank='3'
        WHERE r1.rank='1' AND r1.is_invalid=0 AND r2.is_invalid=0 AND r3.is_invalid=0
    )
    SELECT
        CASE WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 THEN 'reversal' ELSE 'normal' END as pattern,
        COUNT(*) as n,
        -- p2選手のavg_st
        AVG(e_p2.avg_st) as p2_avg_st,
        -- p1選手のavg_st
        AVG(e_p1.avg_st) as p1_avg_st,
        -- ST差(p2 - p1): 負=p2の方が早い
        AVG(e_p2.avg_st - e_p1.avg_st) as st_diff,
        -- p2の勝率
        AVG(e_p2.win_rate) as p2_win_rate,
        -- p2の2連率
        AVG(e_p2.second_rate) as p2_second_rate,
        -- p2の3連率
        AVG(e_p2.third_rate) as p2_third_rate,
        -- p1の勝率
        AVG(e_p1.win_rate) as p1_win_rate,
        -- score差 (p1 - p2)
        AVG(rp.score_p1 - rp.score_p2) as score_diff,
        -- p2のpit_number平均
        AVG(rp.p2) as p2_avg_pit,
        -- p2のlocal_win_rate
        AVG(e_p2.local_win_rate) as p2_local_win_rate,
        -- p1のlocal_win_rate
        AVG(e_p1.local_win_rate) as p1_local_win_rate,
        -- 的中（p2-p1-p3のパターン）
        SUM(CASE WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 AND actual.a3=rp.p3 THEN 1 ELSE 0 END) as reversal_hits_p2p1p3
    FROM races r
    JOIN rp ON r.id=rp.race_id
    JOIN actual ON r.id=actual.race_id
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    LEFT JOIN entries e_p1 ON r.id=e_p1.race_id AND rp.p1=e_p1.pit_number
    LEFT JOIN entries e_p2 ON r.id=e_p2.race_id AND rp.p2=e_p2.pit_number
    WHERE rp.conf='B' AND t.odds BETWEEN 50 AND 100
      AND r.venue_code IN ({venues_str})
      {month_filter}
      AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    GROUP BY pattern
    """

    rows = conn.execute(query_reversal).fetchall()

    out.write("逆転(p2が1着,p1が2着) vs 通常パターンの選手特性比較:\n\n")
    out.write(f"{'パターン':>10s} {'n':>6s} {'p2_ST':>7s} {'p1_ST':>7s} {'ST差':>7s} {'p2勝率':>7s} {'p1勝率':>7s} {'スコア差':>8s} {'p2平均枠':>8s}\n")
    out.write("-" * 90 + "\n")

    for row in rows:
        pattern, n, p2_st, p1_st, st_diff, p2_wr, p2_sr, p2_tr, p1_wr, score_diff, p2_pit, p2_lwr, p1_lwr, rev_hits = row
        out.write(f"{pattern:>10s} {n:6d} {p2_st:7.3f} {p1_st:7.3f} {st_diff:+7.3f} {p2_wr:7.2f} {p1_wr:7.2f} {score_diff:8.2f} {p2_pit:8.2f}\n")

    out.write("\n")
    out.write("補足カラム:\n")
    for row in rows:
        pattern, n, p2_st, p1_st, st_diff, p2_wr, p2_sr, p2_tr, p1_wr, score_diff, p2_pit, p2_lwr, p1_lwr, rev_hits = row
        out.write(f"  {pattern}: p2_2連率={p2_sr:.2f}, p2_3連率={p2_tr:.2f}, p2_local勝率={p2_lwr:.2f}, p1_local勝率={p1_lwr:.2f}\n")

    out.write("\n")

    # ---- 2b. 条件別逆転確率とROI ----
    out.write("-" * 60 + "\n")
    out.write("【2b】条件別逆転確率とROI分析\n")
    out.write("-" * 60 + "\n\n")

    # 逆転買い目 p2-p1-p3 のオッズと的中を分析
    query_cond = f"""
    WITH rp AS (
        SELECT race_id,
            MAX(CASE WHEN rank_prediction=1 THEN pit_number END) as p1,
            MAX(CASE WHEN rank_prediction=2 THEN pit_number END) as p2,
            MAX(CASE WHEN rank_prediction=3 THEN pit_number END) as p3,
            MAX(CASE WHEN rank_prediction=1 THEN confidence END) as conf,
            MAX(CASE WHEN rank_prediction=1 THEN total_score END) as score_p1,
            MAX(CASE WHEN rank_prediction=2 THEN total_score END) as score_p2
        FROM race_predictions
        WHERE prediction_type='before'
        GROUP BY race_id
    ),
    actual AS (
        SELECT r1.race_id, r1.pit_number as a1, r2.pit_number as a2, r3.pit_number as a3
        FROM results r1
        JOIN results r2 ON r1.race_id=r2.race_id AND r2.rank='2'
        JOIN results r3 ON r1.race_id=r3.race_id AND r3.rank='3'
        WHERE r1.rank='1' AND r1.is_invalid=0 AND r2.is_invalid=0 AND r3.is_invalid=0
    ),
    base AS (
        SELECT
            r.id as race_id,
            r.race_date,
            rp.p1, rp.p2, rp.p3,
            actual.a1, actual.a2, actual.a3,
            rp.score_p1, rp.score_p2,
            e_p1.avg_st as p1_st,
            e_p2.avg_st as p2_st,
            e_p2.win_rate as p2_win_rate,
            e_p2.second_rate as p2_second_rate,
            e_p1.win_rate as p1_win_rate,
            t_rev.odds as rev_odds,
            CASE WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 AND actual.a3=rp.p3 THEN 1 ELSE 0 END as is_reversal_hit
        FROM races r
        JOIN rp ON r.id=rp.race_id
        JOIN actual ON r.id=actual.race_id
        JOIN trifecta_odds t ON r.id=t.race_id
            AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
        LEFT JOIN trifecta_odds t_rev ON r.id=t_rev.race_id
            AND t_rev.combination=CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
        LEFT JOIN entries e_p1 ON r.id=e_p1.race_id AND rp.p1=e_p1.pit_number
        LEFT JOIN entries e_p2 ON r.id=e_p2.race_id AND rp.p2=e_p2.pit_number
        WHERE rp.conf='B' AND t.odds BETWEEN 50 AND 100
          AND r.venue_code IN ({venues_str})
          {month_filter}
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    )
    SELECT
        -- 条件カテゴリ
        cond_name,
        COUNT(*) as n,
        SUM(is_reversal_hit) as hits,
        ROUND(100.0 * SUM(is_reversal_hit) / COUNT(*), 2) as hit_rate,
        AVG(rev_odds) as avg_rev_odds,
        SUM(CASE WHEN is_reversal_hit=1 THEN rev_odds*100 ELSE -100 END) as pnl,
        ROUND(SUM(CASE WHEN is_reversal_hit=1 THEN rev_odds*100 ELSE -100 END) * 100.0 / (COUNT(*) * 100), 1) as roi
    FROM (
        SELECT *,
            '全体(ベースライン)' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL

        UNION ALL

        SELECT *,
            'C1: p2のSTがp1より早い' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL

        UNION ALL

        SELECT *,
            'C2: スコア差(p1-p2) < 10' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND (score_p1 - score_p2) < 10

        UNION ALL

        SELECT *,
            'C3: スコア差(p1-p2) < 5' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND (score_p1 - score_p2) < 5

        UNION ALL

        SELECT *,
            'C4: p2が外枠(3-6号艇)' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND p2 >= 3

        UNION ALL

        SELECT *,
            'C5: p2が内枠(1-2号艇)' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND p2 <= 2

        UNION ALL

        SELECT *,
            'C6: C1+C2 (ST早い+スコア差<10)' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL
          AND (score_p1 - score_p2) < 10

        UNION ALL

        SELECT *,
            'C7: C1+C3 (ST早い+スコア差<5)' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL
          AND (score_p1 - score_p2) < 5

        UNION ALL

        SELECT *,
            'C8: p2勝率>=30' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND p2_win_rate >= 30

        UNION ALL

        SELECT *,
            'C9: p2の2連率>=40' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND p2_second_rate >= 40

        UNION ALL

        SELECT *,
            'C10: C1+C9 (ST早い+2連率>=40)' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL
          AND p2_second_rate >= 40

        UNION ALL

        SELECT *,
            'C11: C1+C5 (ST早い+p2内枠)' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL
          AND p2 <= 2

        UNION ALL

        SELECT *,
            'C12: C3+C5 (スコア差<5+p2内枠)' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND (score_p1 - score_p2) < 5
          AND p2 <= 2

        UNION ALL

        SELECT *,
            'C13: C1+C3+C5 (ST早+スコア差<5+p2内枠)' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL
          AND (score_p1 - score_p2) < 5
          AND p2 <= 2

        UNION ALL

        SELECT *,
            'C14: p2勝率 > p1勝率' as cond_name
        FROM base
        WHERE rev_odds IS NOT NULL
          AND p2_win_rate > p1_win_rate
    )
    GROUP BY cond_name
    ORDER BY roi DESC
    """

    rows_cond = conn.execute(query_cond).fetchall()

    out.write("逆転買い目(p2-p1-p3)の条件別成績:\n\n")
    out.write(f"{'条件':>42s} {'n':>6s} {'的中':>4s} {'的中率':>7s} {'平均odds':>8s} {'ROI':>8s} {'PnL':>10s}\n")
    out.write("-" * 100 + "\n")

    for row in rows_cond:
        cond_name, n, hits, hit_rate, avg_odds, pnl, roi = row
        avg_odds_val = avg_odds if avg_odds else 0
        out.write(f"{cond_name:>42s} {n:6d} {hits:4d} {hit_rate:6.2f}% {avg_odds_val:8.1f} {roi:7.1f}% {pnl:+10.0f}\n")

    out.write("\n")

    # ---- 2b追加: 有望条件の年度別分析 ----
    out.write("-" * 60 + "\n")
    out.write("【2b追加】有望条件の年度別一貫性\n")
    out.write("-" * 60 + "\n\n")

    # 上位条件の年度別をチェック
    query_yearly_cond = f"""
    WITH rp AS (
        SELECT race_id,
            MAX(CASE WHEN rank_prediction=1 THEN pit_number END) as p1,
            MAX(CASE WHEN rank_prediction=2 THEN pit_number END) as p2,
            MAX(CASE WHEN rank_prediction=3 THEN pit_number END) as p3,
            MAX(CASE WHEN rank_prediction=1 THEN confidence END) as conf,
            MAX(CASE WHEN rank_prediction=1 THEN total_score END) as score_p1,
            MAX(CASE WHEN rank_prediction=2 THEN total_score END) as score_p2
        FROM race_predictions
        WHERE prediction_type='before'
        GROUP BY race_id
    ),
    actual AS (
        SELECT r1.race_id, r1.pit_number as a1, r2.pit_number as a2, r3.pit_number as a3
        FROM results r1
        JOIN results r2 ON r1.race_id=r2.race_id AND r2.rank='2'
        JOIN results r3 ON r1.race_id=r3.race_id AND r3.rank='3'
        WHERE r1.rank='1' AND r1.is_invalid=0 AND r2.is_invalid=0 AND r3.is_invalid=0
    ),
    base AS (
        SELECT
            r.id as race_id,
            SUBSTR(r.race_date, 1, 4) as year,
            rp.p1, rp.p2, rp.p3,
            actual.a1, actual.a2, actual.a3,
            rp.score_p1, rp.score_p2,
            e_p1.avg_st as p1_st,
            e_p2.avg_st as p2_st,
            e_p2.win_rate as p2_win_rate,
            e_p2.second_rate as p2_second_rate,
            e_p1.win_rate as p1_win_rate,
            t_rev.odds as rev_odds,
            CASE WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 AND actual.a3=rp.p3 THEN 1 ELSE 0 END as is_reversal_hit
        FROM races r
        JOIN rp ON r.id=rp.race_id
        JOIN actual ON r.id=actual.race_id
        JOIN trifecta_odds t ON r.id=t.race_id
            AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
        LEFT JOIN trifecta_odds t_rev ON r.id=t_rev.race_id
            AND t_rev.combination=CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
        LEFT JOIN entries e_p1 ON r.id=e_p1.race_id AND rp.p1=e_p1.pit_number
        LEFT JOIN entries e_p2 ON r.id=e_p2.race_id AND rp.p2=e_p2.pit_number
        WHERE rp.conf='B' AND t.odds BETWEEN 50 AND 100
          AND r.venue_code IN ({venues_str})
          {month_filter}
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND t_rev.odds IS NOT NULL
    )
    SELECT cond_name, year, COUNT(*) as n, SUM(is_reversal_hit) as hits,
           SUM(CASE WHEN is_reversal_hit=1 THEN rev_odds*100 ELSE -100 END) as pnl
    FROM (
        SELECT *, '全体' as cond_name FROM base
        UNION ALL
        SELECT *, 'C1: ST早い' as cond_name FROM base WHERE p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL
        UNION ALL
        SELECT *, 'C3: スコア差<5' as cond_name FROM base WHERE (score_p1 - score_p2) < 5
        UNION ALL
        SELECT *, 'C5: p2内枠' as cond_name FROM base WHERE p2 <= 2
        UNION ALL
        SELECT *, 'C7: ST早+スコア差<5' as cond_name FROM base WHERE p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL AND (score_p1 - score_p2) < 5
        UNION ALL
        SELECT *, 'C13: ST早+スコア差<5+内枠' as cond_name FROM base WHERE p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL AND (score_p1 - score_p2) < 5 AND p2 <= 2
        UNION ALL
        SELECT *, 'C14: p2勝率>p1勝率' as cond_name FROM base WHERE p2_win_rate > p1_win_rate
    )
    GROUP BY cond_name, year
    ORDER BY cond_name, year
    """

    yearly_cond_rows = conn.execute(query_yearly_cond).fetchall()

    # 整理
    yearly_cond_data = {}
    for row in yearly_cond_rows:
        cond, year, n, hits, pnl = row
        if cond not in yearly_cond_data:
            yearly_cond_data[cond] = {}
        yearly_cond_data[cond][year] = {'n': n, 'hits': hits, 'pnl': pnl}

    years = ['2020', '2021', '2022', '2023', '2024', '2025']
    for cond in sorted(yearly_cond_data.keys()):
        out.write(f"  {cond}:\n")
        total_n = 0
        total_hits = 0
        total_pnl = 0
        profit_years = 0
        data_years = 0
        for y in years:
            d = yearly_cond_data[cond].get(y, None)
            if d and d['n'] > 0:
                roi = (d['pnl'] / (d['n'] * 100)) * 100
                mark = "+" if d['pnl'] > 0 else "-"
                out.write(f"    {y}: {d['n']:4d}件, {d['hits']}的中, ROI {roi:6.0f}% {mark}\n")
                total_n += d['n']
                total_hits += d['hits']
                total_pnl += d['pnl']
                if d['pnl'] > 0:
                    profit_years += 1
                data_years += 1
            else:
                out.write(f"    {y}: ---\n")

        total_roi = (total_pnl / (total_n * 100)) * 100 if total_n > 0 else 0
        out.write(f"    合計: {total_n}件, {total_hits}的中, ROI {total_roi:.0f}%, 黒字 {profit_years}/{data_years}年\n\n")

    # ---- 2c. 理想的な逆転条件の設計 ----
    out.write("-" * 60 + "\n")
    out.write("【2c】理想的な逆転条件の設計\n")
    out.write("-" * 60 + "\n\n")

    # より細かいスコア差の分析
    query_score_detail = f"""
    WITH rp AS (
        SELECT race_id,
            MAX(CASE WHEN rank_prediction=1 THEN pit_number END) as p1,
            MAX(CASE WHEN rank_prediction=2 THEN pit_number END) as p2,
            MAX(CASE WHEN rank_prediction=3 THEN pit_number END) as p3,
            MAX(CASE WHEN rank_prediction=1 THEN confidence END) as conf,
            MAX(CASE WHEN rank_prediction=1 THEN total_score END) as score_p1,
            MAX(CASE WHEN rank_prediction=2 THEN total_score END) as score_p2
        FROM race_predictions
        WHERE prediction_type='before'
        GROUP BY race_id
    ),
    actual AS (
        SELECT r1.race_id, r1.pit_number as a1, r2.pit_number as a2, r3.pit_number as a3
        FROM results r1
        JOIN results r2 ON r1.race_id=r2.race_id AND r2.rank='2'
        JOIN results r3 ON r1.race_id=r3.race_id AND r3.rank='3'
        WHERE r1.rank='1' AND r1.is_invalid=0 AND r2.is_invalid=0 AND r3.is_invalid=0
    ),
    base AS (
        SELECT
            r.id as race_id,
            SUBSTR(r.race_date, 1, 4) as year,
            rp.p1, rp.p2, rp.p3,
            actual.a1, actual.a2, actual.a3,
            rp.score_p1, rp.score_p2,
            rp.score_p1 - rp.score_p2 as score_diff,
            e_p1.avg_st as p1_st,
            e_p2.avg_st as p2_st,
            e_p2.win_rate as p2_win_rate,
            e_p2.second_rate as p2_second_rate,
            e_p1.win_rate as p1_win_rate,
            t_rev.odds as rev_odds,
            CASE WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 AND actual.a3=rp.p3 THEN 1 ELSE 0 END as is_reversal_hit
        FROM races r
        JOIN rp ON r.id=rp.race_id
        JOIN actual ON r.id=actual.race_id
        JOIN trifecta_odds t ON r.id=t.race_id
            AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
        LEFT JOIN trifecta_odds t_rev ON r.id=t_rev.race_id
            AND t_rev.combination=CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
        LEFT JOIN entries e_p1 ON r.id=e_p1.race_id AND rp.p1=e_p1.pit_number
        LEFT JOIN entries e_p2 ON r.id=e_p2.race_id AND rp.p2=e_p2.pit_number
        WHERE rp.conf='B' AND t.odds BETWEEN 50 AND 100
          AND r.venue_code IN ({venues_str})
          {month_filter}
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND t_rev.odds IS NOT NULL
    )
    SELECT
        CASE
            WHEN score_diff < 2 THEN 'A: <2'
            WHEN score_diff < 5 THEN 'B: 2-5'
            WHEN score_diff < 10 THEN 'C: 5-10'
            WHEN score_diff < 15 THEN 'D: 10-15'
            ELSE 'E: 15+'
        END as score_band,
        COUNT(*) as n,
        SUM(is_reversal_hit) as hits,
        ROUND(100.0 * SUM(is_reversal_hit) / COUNT(*), 2) as hit_rate,
        AVG(rev_odds) as avg_odds,
        SUM(CASE WHEN is_reversal_hit=1 THEN rev_odds*100 ELSE -100 END) as pnl,
        ROUND(SUM(CASE WHEN is_reversal_hit=1 THEN rev_odds*100 ELSE -100 END) * 100.0 / (COUNT(*) * 100), 1) as roi
    FROM base
    GROUP BY score_band
    ORDER BY score_band
    """

    rows_score = conn.execute(query_score_detail).fetchall()

    out.write("スコア差(p1-p2)帯別の逆転的中率とROI:\n\n")
    out.write(f"{'スコア差帯':>12s} {'n':>6s} {'的中':>4s} {'的中率':>7s} {'平均odds':>8s} {'ROI':>8s} {'PnL':>10s}\n")
    out.write("-" * 70 + "\n")
    for row in rows_score:
        band, n, hits, hit_rate, avg_odds, pnl, roi = row
        out.write(f"{band:>12s} {n:6d} {hits:4d} {hit_rate:6.2f}% {avg_odds:8.1f} {roi:7.1f}% {pnl:+10.0f}\n")

    out.write("\n")

    # ST差帯別
    query_st_detail = f"""
    WITH rp AS (
        SELECT race_id,
            MAX(CASE WHEN rank_prediction=1 THEN pit_number END) as p1,
            MAX(CASE WHEN rank_prediction=2 THEN pit_number END) as p2,
            MAX(CASE WHEN rank_prediction=3 THEN pit_number END) as p3,
            MAX(CASE WHEN rank_prediction=1 THEN confidence END) as conf,
            MAX(CASE WHEN rank_prediction=1 THEN total_score END) as score_p1,
            MAX(CASE WHEN rank_prediction=2 THEN total_score END) as score_p2
        FROM race_predictions
        WHERE prediction_type='before'
        GROUP BY race_id
    ),
    actual AS (
        SELECT r1.race_id, r1.pit_number as a1, r2.pit_number as a2, r3.pit_number as a3
        FROM results r1
        JOIN results r2 ON r1.race_id=r2.race_id AND r2.rank='2'
        JOIN results r3 ON r1.race_id=r3.race_id AND r3.rank='3'
        WHERE r1.rank='1' AND r1.is_invalid=0 AND r2.is_invalid=0 AND r3.is_invalid=0
    ),
    base AS (
        SELECT
            r.id as race_id,
            rp.p1, rp.p2, rp.p3,
            actual.a1, actual.a2, actual.a3,
            e_p1.avg_st as p1_st,
            e_p2.avg_st as p2_st,
            e_p2.avg_st - e_p1.avg_st as st_diff,
            t_rev.odds as rev_odds,
            CASE WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 AND actual.a3=rp.p3 THEN 1 ELSE 0 END as is_reversal_hit
        FROM races r
        JOIN rp ON r.id=rp.race_id
        JOIN actual ON r.id=actual.race_id
        JOIN trifecta_odds t ON r.id=t.race_id
            AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
        LEFT JOIN trifecta_odds t_rev ON r.id=t_rev.race_id
            AND t_rev.combination=CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
        LEFT JOIN entries e_p1 ON r.id=e_p1.race_id AND rp.p1=e_p1.pit_number
        LEFT JOIN entries e_p2 ON r.id=e_p2.race_id AND rp.p2=e_p2.pit_number
        WHERE rp.conf='B' AND t.odds BETWEEN 50 AND 100
          AND r.venue_code IN ({venues_str})
          {month_filter}
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND t_rev.odds IS NOT NULL
          AND e_p1.avg_st IS NOT NULL AND e_p2.avg_st IS NOT NULL
    )
    SELECT
        CASE
            WHEN st_diff < -0.05 THEN 'A: p2 >> p1 (差<-0.05)'
            WHEN st_diff < -0.02 THEN 'B: p2 > p1 (-0.05~-0.02)'
            WHEN st_diff < 0.00  THEN 'C: p2 >= p1 (-0.02~0.00)'
            WHEN st_diff < 0.02  THEN 'D: ほぼ同じ (0.00~0.02)'
            WHEN st_diff < 0.05  THEN 'E: p1 > p2 (0.02~0.05)'
            ELSE 'F: p1 >> p2 (0.05+)'
        END as st_band,
        COUNT(*) as n,
        SUM(is_reversal_hit) as hits,
        ROUND(100.0 * SUM(is_reversal_hit) / COUNT(*), 2) as hit_rate,
        AVG(rev_odds) as avg_odds,
        SUM(CASE WHEN is_reversal_hit=1 THEN rev_odds*100 ELSE -100 END) as pnl,
        ROUND(SUM(CASE WHEN is_reversal_hit=1 THEN rev_odds*100 ELSE -100 END) * 100.0 / (COUNT(*) * 100), 1) as roi
    FROM base
    GROUP BY st_band
    ORDER BY st_band
    """

    rows_st = conn.execute(query_st_detail).fetchall()

    out.write("ST差(p2-p1)帯別の逆転的中率とROI:\n")
    out.write("  ST差が負 = p2の方がスタートが早い\n\n")
    out.write(f"{'ST差帯':>30s} {'n':>6s} {'的中':>4s} {'的中率':>7s} {'平均odds':>8s} {'ROI':>8s} {'PnL':>10s}\n")
    out.write("-" * 85 + "\n")
    for row in rows_st:
        band, n, hits, hit_rate, avg_odds, pnl, roi = row
        out.write(f"{band:>30s} {n:6d} {hits:4d} {hit_rate:6.2f}% {avg_odds:8.1f} {roi:7.1f}% {pnl:+10.0f}\n")

    out.write("\n")

    # p2のpit_number別
    query_pit = f"""
    WITH rp AS (
        SELECT race_id,
            MAX(CASE WHEN rank_prediction=1 THEN pit_number END) as p1,
            MAX(CASE WHEN rank_prediction=2 THEN pit_number END) as p2,
            MAX(CASE WHEN rank_prediction=3 THEN pit_number END) as p3,
            MAX(CASE WHEN rank_prediction=1 THEN confidence END) as conf
        FROM race_predictions
        WHERE prediction_type='before'
        GROUP BY race_id
    ),
    actual AS (
        SELECT r1.race_id, r1.pit_number as a1, r2.pit_number as a2, r3.pit_number as a3
        FROM results r1
        JOIN results r2 ON r1.race_id=r2.race_id AND r2.rank='2'
        JOIN results r3 ON r1.race_id=r3.race_id AND r3.rank='3'
        WHERE r1.rank='1' AND r1.is_invalid=0 AND r2.is_invalid=0 AND r3.is_invalid=0
    )
    SELECT
        rp.p2 as p2_pit,
        COUNT(*) as n,
        SUM(CASE WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 AND actual.a3=rp.p3 THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 AND actual.a3=rp.p3 THEN t_rev.odds*100 ELSE -100 END) as pnl
    FROM races r
    JOIN rp ON r.id=rp.race_id
    JOIN actual ON r.id=actual.race_id
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    LEFT JOIN trifecta_odds t_rev ON r.id=t_rev.race_id
        AND t_rev.combination=CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    WHERE rp.conf='B' AND t.odds BETWEEN 50 AND 100
      AND r.venue_code IN ({venues_str})
      {month_filter}
      AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
      AND t_rev.odds IS NOT NULL
    GROUP BY rp.p2
    ORDER BY rp.p2
    """

    rows_pit = conn.execute(query_pit).fetchall()

    out.write("p2のpit_number(枠番)別の逆転的中:\n\n")
    out.write(f"{'p2枠番':>7s} {'n':>6s} {'的中':>4s} {'的中率':>7s} {'ROI':>8s} {'PnL':>10s}\n")
    out.write("-" * 50 + "\n")
    for row in rows_pit:
        pit, n, hits, pnl = row
        hit_rate = hits / n * 100 if n > 0 else 0
        roi = (pnl / (n * 100)) * 100 if n > 0 else 0
        out.write(f"{pit:>7d} {n:6d} {hits:4d} {hit_rate:6.2f}% {roi:7.1f}% {pnl:+10.0f}\n")

    out.write("\n")


def run_summary(conn, out, venue_data):
    """総合判定"""
    out.write("\n\n" + "=" * 80 + "\n")
    out.write("=== 総合判定 ===\n")
    out.write("=" * 80 + "\n\n")

    out.write("-" * 60 + "\n")
    out.write("【P1: 会場フィルターの統計的根拠による最終判定】\n")
    out.write("-" * 60 + "\n\n")

    # 各会場の判定
    for vc in [3, 15, 1]:
        vd = next((v for v in venue_data if v['vc'] == vc), None)
        if vd:
            out.write(f"  {vd['name']}（コード{vc}）:\n")
            out.write(f"    6年間: n={vd['n']}, ROI={vd['roi']:.1f}%, 95%CI下限ROI={vd['roi_ci_lo']:.1f}%\n")

            if vd['n'] < 30:
                out.write(f"    判定: サンプル不足（{vd['n']}件 < 最低30件）。統計的に信頼できない。\n")
                out.write(f"    理由: 1件の的中/不的中でROIが大幅に変動する（脆弱性が高い）\n")
            elif vd['roi_ci_lo'] < 100:
                out.write(f"    判定: 95%信頼区間の下限ROIが{vd['roi_ci_lo']:.1f}%で損益分岐点100%を下回る。\n")
                out.write(f"    理由: 観測されたROIは統計的揺らぎの範囲内であり「傾向」と断定できない。\n")
            else:
                out.write(f"    判定: 95%信頼区間の下限ROIが{vd['roi_ci_lo']:.1f}%で損益分岐点を上回る。「傾向」として採用可。\n")
            out.write("\n")

    out.write("  全体的なP1の評価:\n")
    out.write("    - 会場別15-60件程度のサンプルでは、個別会場の追加・除外の統計的根拠は弱い\n")
    out.write("    - 「11会場プール」のレベルでの信頼性を重視すべき\n")
    out.write("    - 個別会場の微調整よりも、プール全体のROIが安定しているかを監視する方が実用的\n\n")

    out.write("-" * 60 + "\n")
    out.write("【P2: 逆転パターンの採用可否判定】\n")
    out.write("-" * 60 + "\n\n")

    out.write("  Tier 1基準との照合:\n")
    out.write("    - ROI 150%以上: [上記条件別分析の結果を参照]\n")
    out.write("    - サンプル数 50件以上: [上記条件別分析の結果を参照]\n")
    out.write("    - 1/2年黒字: [上記年度別分析の結果を参照]\n\n")

    out.write("  判定基準:\n")
    out.write("    (1) 条件なし逆転買いは分散が大きく採用困難\n")
    out.write("    (2) 活性化条件を付けた場合にTier1基準を満たすかが鍵\n")
    out.write("    (3) 年度別一貫性が低い場合は「たまたま」の可能性が高い\n\n")


def main():
    print(f"DB: {DB_PATH}")
    print(f"Output: {OUTPUT_PATH}")

    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as out:
        out.write("P1/P2 再分析レポート\n")
        out.write(f"生成日: 2026-02-19\n")
        out.write(f"DB: {DB_PATH}\n")
        out.write(f"対象期間: 2020-01-01 ~ 2025-12-31\n\n")

        # P1分析
        venue_data = run_p1_analysis(conn, out)

        # P2分析
        run_p2_analysis(conn, out)

        # 総合判定
        run_summary(conn, out, venue_data)

    conn.close()
    print(f"\nDone. Results written to: {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
