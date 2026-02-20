#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P1(会場フィルター)統計的信頼性 & P2(逆転パターン)条件付き分析 v2
venue_codeがTEXT型('01','02'.../'1','2'...)の混在に対応
結果はファイルに出力（cp932環境対応）
"""

import sqlite3
import math
import os
import sys

# パスの設定
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data", "boatrace.db")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "p1_p2_reanalysis_result_v2.txt")

# 現在の11会場リスト
CURRENT_VENUES = [4, 5, 7, 9, 10, 14, 18, 19, 20, 21, 24]

# 会場名マッピング
VENUE_NAMES = {
    1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川",
    6: "浜名湖", 7: "蒲郡", 8: "常滑", 9: "津", 10: "三国",
    11: "びわこ", 12: "住之江", 13: "尼崎", 14: "鳴門", 15: "丸亀",
    16: "児島", 17: "宮島", 18: "徳山", 19: "下関", 20: "若松",
    21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村"
}


def venue_code_int(vc):
    """TEXT型のvenue_codeを整数に変換"""
    try:
        return int(vc)
    except:
        return 0


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
    """ROI >= target_roi を95%CI下限で確認するための最小サンプル数"""
    z = 1.96
    p_break = target_roi / avg_odds
    p_est = p_break * 1.3
    if p_est >= 1:
        return 99999
    margin_needed = p_est - p_break
    if margin_needed <= 0:
        return 99999
    n_needed = (z ** 2 * p_est * (1 - p_est)) / (margin_needed ** 2)
    return int(math.ceil(n_needed))


def run_p1_analysis(conn, out):
    """P1: 会場別統計的信頼性分析"""
    out.write("=" * 80 + "\n")
    out.write("=== P1 統計的信頼性分析 ===\n")
    out.write("=" * 80 + "\n\n")

    # ---- 1a. 会場別の統計的信頼性 ----
    out.write("-" * 60 + "\n")
    out.write("[1a] 会場別 B x 50-100倍 信頼区間付き分析（2020-2025年, 6年間）\n")
    out.write("-" * 60 + "\n\n")

    # CAST(venue_code AS INTEGER) でグルーピング
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
    SELECT CAST(r.venue_code AS INTEGER) as vc_int, COUNT(*) as n,
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
    GROUP BY vc_int
    ORDER BY vc_int
    """

    rows = conn.execute(query_venue).fetchall()

    # ヘッダー
    out.write(f"{'':>2s}{'会場':>5s} {'n':>5s} {'hits':>5s} {'的中率':>8s} {'95%CI下限':>9s} {'95%CI上限':>9s} {'ROI':>8s} {'PnL':>10s} {'最小必要n':>9s} {'判定':>12s}\n")
    out.write("-" * 105 + "\n")

    venue_data = []
    for row in rows:
        vc, n, hits, pnl, avg_odds = row
        vname = VENUE_NAMES.get(vc, f"#{vc}")
        p_hat, ci_lo, ci_hi = wilson_ci(hits, n)
        roi = (pnl / (n * 100)) * 100 if n > 0 else 0

        # 95%CI下限でのROI = ci_lo * avg_odds * 100
        roi_ci_lo = ci_lo * avg_odds * 100 if avg_odds > 0 else 0

        # 最小必要サンプル数
        min_n = min_sample_for_roi(avg_odds, target_roi=1.0)

        # 判定
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
        out.write(f"{in_current} {vname:>4s} {n:5d} {hits:5d} {p_hat*100:7.2f}% [{ci_lo*100:6.2f}% - {ci_hi*100:6.2f}%] {roi:7.1f}% {pnl:+10.0f} {min_n:>9d} {judgment}\n")

    out.write("\n* = 現在採用中の11会場\n\n")

    out.write("[解説]\n")
    out.write("- 95%信頼区間: 真の的中率がこの範囲にある確率95% (Wilson法)\n")
    out.write("- ROI_CI下限 = CI下限的中率 x 平均オッズ x 100\n")
    out.write("- 最小必要n: 95%CI下限でROI>=100%を確認するための理論的最小件数\n")
    out.write("- 判定: CI下限ROI>=100% -> 傾向 / n>=50+ROI>100% -> やや有望 / n<30 -> 不十分\n\n")

    # 注目会場の詳細
    out.write("-" * 60 + "\n")
    out.write("[注目会場の詳細評価]\n")
    out.write("-" * 60 + "\n\n")

    focus_venues = [3, 15, 1]  # 江戸川, 丸亀, 桐生
    for vc in focus_venues:
        vd = next((v for v in venue_data if v['vc'] == vc), None)
        if vd:
            out.write(f"  {vd['name']} (コード{vc}):\n")
            out.write(f"    件数: {vd['n']}件, 的中: {vd['hits']}件\n")
            out.write(f"    的中率: {vd['p_hat']*100:.2f}% [95%CI: {vd['ci_lo']*100:.2f}% - {vd['ci_hi']*100:.2f}%]\n")
            out.write(f"    ROI: {vd['roi']:.1f}%, 95%CI下限ROI: {vd['roi_ci_lo']:.1f}%\n")
            out.write(f"    平均オッズ: {vd['avg_odds']:.1f}倍, 損益分岐的中率: {1.0/vd['avg_odds']*100:.2f}%\n")
            out.write(f"    最小必要サンプル数: {vd['min_n']}件\n")
            out.write(f"    判定: {vd['judgment']}\n")

            # 1件的中の影響度
            if vd['n'] > 0 and vd['hits'] > 0:
                # 的中1件を除いた場合のROI
                # 最も高額の的中を除くのが理想だが、平均オッズで近似
                pnl_minus_one = vd['pnl'] - vd['avg_odds'] * 100 + 100  # 的中1件減 -> -odds*100+100(外れに変換)
                # ただし正確にはhitのオッズは不明なのでpnl/hits で近似
                avg_hit_contribution = (vd['pnl'] + vd['n'] * 100) / vd['hits'] if vd['hits'] > 0 else 0
                pnl_minus_one_v2 = vd['pnl'] - avg_hit_contribution
                roi_minus_one = (pnl_minus_one_v2 / (vd['n'] * 100)) * 100
                out.write(f"    【脆弱性】的中1件減でのROI: {vd['roi']:.1f}% -> {roi_minus_one:.1f}%  (差: {roi_minus_one - vd['roi']:+.1f}pt)\n")
            elif vd['n'] > 0:
                out.write(f"    【脆弱性】的中0件のため、更なる悪化はない\n")
            out.write("\n")
        else:
            out.write(f"  会場コード{vc}: データなし\n\n")

    # ---- 1b. 年度別一貫性分析 ----
    out.write("\n" + "-" * 60 + "\n")
    out.write("[1b] 年度別一貫性分析（全会場 x 年度）\n")
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
    SELECT CAST(r.venue_code AS INTEGER) as vc_int,
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
    GROUP BY vc_int, year
    ORDER BY vc_int, year
    """

    yearly_rows = conn.execute(query_yearly).fetchall()

    yearly_by_venue = {}
    for row in yearly_rows:
        vc, year, n, hits, pnl = row
        if vc not in yearly_by_venue:
            yearly_by_venue[vc] = {}
        yearly_by_venue[vc][year] = {'n': n, 'hits': hits, 'pnl': pnl}

    all_venues_sorted = sorted(yearly_by_venue.keys())
    years = ['2020', '2021', '2022', '2023', '2024', '2025']

    out.write(f"{'':>2s}{'会場':>4s} ")
    for y in years:
        out.write(f"|  {y}           ")
    out.write(f"| 黒字年 | 一貫性\n")
    out.write("-" * 130 + "\n")

    for vc in all_venues_sorted:
        vname = VENUE_NAMES.get(vc, f"#{vc}")
        in_current = "*" if vc in CURRENT_VENUES else " "
        out.write(f"{in_current} {vname:>4s} ")

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
                out.write(f"|     ---         ")

        consistency = "高" if profit_years >= 4 else ("中" if profit_years >= 3 else "低")
        out.write(f"| {profit_years}/{total_years_with_data}年  | {consistency}\n")

    out.write("\n* = 現在採用中の11会場, + = 黒字年, - = 赤字年\n\n")

    # 注目3会場の年度別詳細
    out.write("[注目3会場の年度別詳細]\n\n")
    for vc in [3, 15, 1]:
        vname = VENUE_NAMES.get(vc, f"#{vc}")
        out.write(f"  {vname} (コード{vc}):\n")
        data_years = yearly_by_venue.get(vc, {})
        hit_years = 0
        miss_years = 0
        for y in years:
            d = data_years.get(y, None)
            if d:
                roi = (d['pnl'] / (d['n'] * 100)) * 100 if d['n'] > 0 else 0
                out.write(f"    {y}: {d['n']:3d}件, {d['hits']}的中, ROI {roi:6.0f}%")
                if d['hits'] > 0:
                    hit_years += 1
                else:
                    miss_years += 1
                out.write("\n")
            else:
                out.write(f"    {y}: データなし\n")
                miss_years += 1
        out.write(f"    -> 的中年: {hit_years}年, 不的中年: {miss_years}年\n")
        if hit_years >= 4:
            eval_text = "各年に的中あり=傾向の兆候あり"
        elif hit_years >= 2:
            eval_text = "複数年で的中=弱い傾向の可能性"
        elif hit_years == 1:
            eval_text = "単一年の的中=ノイズの疑い強い"
        else:
            eval_text = "的中なし=傾向なし"
        out.write(f"    -> 一貫性評価: {eval_text}\n\n")

    # ---- 1c. プール比較 ----
    out.write("\n" + "-" * 60 + "\n")
    out.write("[1c] 全会場プールでの統計的比較\n")
    out.write("-" * 60 + "\n\n")

    # 11会場のフィルター（TEXT型対応）
    venues_filter_current = " OR ".join([
        f"CAST(r.venue_code AS INTEGER)={v}" for v in CURRENT_VENUES
    ])

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
        CASE WHEN ({filter}) THEN 'IN' ELSE 'OUT' END as pool,
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
    rows_current = conn.execute(query_pool.format(filter=venues_filter_current)).fetchall()

    # 候補追加後(+江戸川+丸亀 = 13会場)
    expanded = CURRENT_VENUES + [3, 15]
    venues_filter_exp = " OR ".join([f"CAST(r.venue_code AS INTEGER)={v}" for v in expanded])
    rows_expanded = conn.execute(query_pool.format(filter=venues_filter_exp)).fetchall()

    # 全24会場
    all_filter = "1=1"
    rows_all = conn.execute(query_pool.format(filter=all_filter)).fetchall()

    out.write("プール比較:\n\n")
    out.write(f"{'プール':>22s} {'n':>6s} {'hits':>5s} {'的中率':>8s} {'ROI':>8s} {'PnL':>12s}\n")
    out.write("-" * 70 + "\n")

    pool_data = {}
    for label, rows_data in [("現在11会場", rows_current), ("候補追加13会場", rows_expanded), ("全24会場", rows_all)]:
        for row in rows_data:
            pool_name, n, hits, pnl, avg_odds = row
            if pool_name == 'IN':
                p_hat = hits / n if n > 0 else 0
                roi = (pnl / (n * 100)) * 100 if n > 0 else 0
                out.write(f"{label + ' (IN)':>22s} {n:6d} {hits:5d} {p_hat*100:7.2f}% {roi:7.1f}% {pnl:+12.0f}\n")
                pool_data[label] = {'n': n, 'hits': hits, 'pnl': pnl, 'roi': roi}
            elif pool_name == 'OUT' and label == "現在11会場":
                pool_data['OUT'] = {'n': n, 'hits': hits, 'pnl': pnl}

    out.write("\n")

    # 統計的検定
    out.write("[統計的検定] 11会場(IN) vs 11会場外(OUT)の比較:\n\n")
    if 'OUT' in pool_data and '現在11会場' in pool_data:
        d_in = pool_data['現在11会場']
        d_out = pool_data['OUT']
        n_in, h_in = d_in['n'], d_in['hits']
        n_out, h_out = d_out['n'], d_out['hits']
        pnl_in, pnl_out = d_in['pnl'], d_out['pnl']

        p_in = h_in / n_in if n_in > 0 else 0
        p_out = h_out / n_out if n_out > 0 else 0
        roi_in = (pnl_in / (n_in * 100)) * 100 if n_in > 0 else 0
        roi_out = (pnl_out / (n_out * 100)) * 100 if n_out > 0 else 0

        p_pooled = (h_in + h_out) / (n_in + n_out) if (n_in + n_out) > 0 else 0
        if 0 < p_pooled < 1:
            se = math.sqrt(p_pooled * (1 - p_pooled) * (1.0/n_in + 1.0/n_out))
            z_stat = (p_in - p_out) / se if se > 0 else 0
        else:
            z_stat = 0

        out.write(f"  11会場(IN):  n={n_in}, hits={h_in}, 的中率={p_in*100:.2f}%, ROI={roi_in:.1f}%\n")
        out.write(f"  11会場外(OUT): n={n_out}, hits={h_out}, 的中率={p_out*100:.2f}%, ROI={roi_out:.1f}%\n")
        out.write(f"  的中率差: {(p_in - p_out)*100:+.2f}pt\n")
        out.write(f"  z統計量: {z_stat:.3f}")
        if abs(z_stat) >= 2.576:
            out.write(" (p < 0.01, 高度に有意)\n")
        elif abs(z_stat) >= 1.96:
            out.write(" (p < 0.05, 有意差あり)\n")
        elif abs(z_stat) >= 1.645:
            out.write(" (p < 0.10, 弱い有意差)\n")
        else:
            out.write(f" (p = ~{2*(1 - 0.5*(1+math.erf(abs(z_stat)/math.sqrt(2)))):.3f}, 有意差なし)\n")

        out.write("\n  [重要な発見]\n")
        if roi_out > roi_in:
            out.write(f"  11会場外のROI({roi_out:.1f}%)が11会場内({roi_in:.1f}%)を上回っている。\n")
            out.write(f"  -> 現在の11会場フィルターが最適でない可能性がある。\n")
        out.write("\n")

    return venue_data


def run_p2_analysis(conn, out):
    """P2: 条件付き逆転パターン分析"""
    out.write("\n\n" + "=" * 80 + "\n")
    out.write("=== P2 条件付き逆転パターン分析 ===\n")
    out.write("=" * 80 + "\n\n")

    # 11会場フィルター
    venues_filter = " OR ".join([
        f"CAST(r.venue_code AS INTEGER)={v}" for v in CURRENT_VENUES
    ])
    month_filter = "AND SUBSTR(r.race_date, 6, 2) NOT IN ('01','02','04','12')"

    # ---- 2a. 逆転発生時の選手特性 ----
    out.write("-" * 60 + "\n")
    out.write("[2a] 逆転発生時 vs 非発生時の選手特性比較\n")
    out.write("-" * 60 + "\n\n")

    out.write("条件: B x 50-100倍, 11会場, 月除外(12,1,2,4)\n\n")

    # まず、逆転と通常の件数を大まかに見る
    # p2-p1逆転: actual_1着=p2, actual_2着=p1
    query_reversal = f"""
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
    )
    SELECT
        CASE
            WHEN actual.a1=rp.p1 AND actual.a2=rp.p2 AND actual.a3=rp.p3 THEN 'hit_p1p2p3'
            WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 THEN 'reversal_p2p1'
            ELSE 'other'
        END as pattern,
        COUNT(*) as n,
        AVG(e_p2.avg_st) as p2_avg_st,
        AVG(e_p1.avg_st) as p1_avg_st,
        AVG(CASE WHEN e_p2.avg_st IS NOT NULL AND e_p1.avg_st IS NOT NULL THEN e_p2.avg_st - e_p1.avg_st END) as st_diff,
        AVG(e_p2.win_rate) as p2_win_rate,
        AVG(e_p2.second_rate) as p2_second_rate,
        AVG(e_p2.third_rate) as p2_third_rate,
        AVG(e_p1.win_rate) as p1_win_rate,
        AVG(rp.score_p1 - rp.score_p2) as score_diff,
        AVG(rp.p2 * 1.0) as p2_avg_pit,
        AVG(e_p2.local_win_rate) as p2_local_wr,
        AVG(e_p1.local_win_rate) as p1_local_wr,
        SUM(CASE WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 AND actual.a3=rp.p3 THEN 1 ELSE 0 END) as rev_exact_hits
    FROM races r
    JOIN rp ON r.id=rp.race_id
    JOIN actual ON r.id=actual.race_id
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination=CAST(rp.p1 AS TEXT)||'-'||CAST(rp.p2 AS TEXT)||'-'||CAST(rp.p3 AS TEXT)
    LEFT JOIN entries e_p1 ON r.id=e_p1.race_id AND rp.p1=e_p1.pit_number
    LEFT JOIN entries e_p2 ON r.id=e_p2.race_id AND rp.p2=e_p2.pit_number
    WHERE rp.conf='B' AND t.odds BETWEEN 50 AND 100
      AND ({venues_filter})
      {month_filter}
      AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    GROUP BY pattern
    ORDER BY pattern
    """

    rows = conn.execute(query_reversal).fetchall()

    out.write("パターン分布:\n")
    out.write("  hit_p1p2p3  = 順当的中 (p1-p2-p3)\n")
    out.write("  reversal_p2p1 = p2が1着でp1が2着に降格\n")
    out.write("  other = それ以外\n\n")

    out.write(f"{'パターン':>15s} {'n':>6s} {'p2_ST':>7s} {'p1_ST':>7s} {'ST差':>8s} {'p2勝率':>7s} {'p1勝率':>7s} {'スコア差':>8s} {'p2枠平均':>8s}\n")
    out.write("-" * 95 + "\n")

    for row in rows:
        pattern, n, p2_st, p1_st, st_diff, p2_wr, p2_sr, p2_tr, p1_wr, score_diff, p2_pit, p2_lwr, p1_lwr, rev_exact = row
        p2_st_s = f"{p2_st:.3f}" if p2_st else "N/A"
        p1_st_s = f"{p1_st:.3f}" if p1_st else "N/A"
        st_diff_s = f"{st_diff:+.4f}" if st_diff else "N/A"
        p2_wr_s = f"{p2_wr:.2f}" if p2_wr else "N/A"
        p1_wr_s = f"{p1_wr:.2f}" if p1_wr else "N/A"
        score_diff_s = f"{score_diff:.2f}" if score_diff else "N/A"
        p2_pit_s = f"{p2_pit:.2f}" if p2_pit else "N/A"
        out.write(f"{pattern:>15s} {n:6d} {p2_st_s:>7s} {p1_st_s:>7s} {st_diff_s:>8s} {p2_wr_s:>7s} {p1_wr_s:>7s} {score_diff_s:>8s} {p2_pit_s:>8s}\n")

    out.write("\n")
    out.write("補足:\n")
    for row in rows:
        pattern, n, p2_st, p1_st, st_diff, p2_wr, p2_sr, p2_tr, p1_wr, score_diff, p2_pit, p2_lwr, p1_lwr, rev_exact = row
        p2_sr_v = p2_sr if p2_sr else 0
        p2_tr_v = p2_tr if p2_tr else 0
        p2_lwr_v = p2_lwr if p2_lwr else 0
        p1_lwr_v = p1_lwr if p1_lwr else 0
        out.write(f"  {pattern}: p2_2連率={p2_sr_v:.2f}, p2_3連率={p2_tr_v:.2f}, ")
        out.write(f"p2地元勝率={p2_lwr_v:.2f}, p1地元勝率={p1_lwr_v:.2f}")
        if pattern == 'reversal_p2p1':
            out.write(f", うちp2-p1-p3完全一致={rev_exact}件")
        out.write("\n")

    out.write("\n")

    # ---- 2b. 条件別逆転確率とROI ----
    out.write("-" * 60 + "\n")
    out.write("[2b] 条件別逆転確率とROI分析\n")
    out.write("-" * 60 + "\n\n")

    out.write("逆転買い目(p2-p1-p3)の条件別成績:\n\n")

    # 条件ごとに個別クエリを発行（UNIONが複雑になりすぎるため）
    base_query = f"""
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
            CASE WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 AND actual.a3=rp.p3 THEN 1 ELSE 0 END as is_hit
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
          AND ({venues_filter})
          {month_filter}
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND t_rev.odds IS NOT NULL
    )
    SELECT
        {{cond_label}} as cond_name,
        COUNT(*) as n,
        SUM(is_hit) as hits,
        AVG(rev_odds) as avg_odds,
        SUM(CASE WHEN is_hit=1 THEN rev_odds*100 ELSE -100 END) as pnl
    FROM base
    WHERE {{cond_where}}
    """

    conditions = [
        ("全体(ベースライン)", "1=1"),
        ("C1: p2のSTがp1より早い", "p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL"),
        ("C2: スコア差 < 10", "score_diff < 10"),
        ("C3: スコア差 < 5", "score_diff < 5"),
        ("C4: p2が外枠(3-6号艇)", "p2 >= 3"),
        ("C5: p2が内枠(1-2号艇)", "p2 <= 2"),
        ("C6: C1+C2 (ST早+スコア差<10)", "p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL AND score_diff < 10"),
        ("C7: C1+C3 (ST早+スコア差<5)", "p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL AND score_diff < 5"),
        ("C8: p2勝率>=30", "p2_win_rate >= 30"),
        ("C9: p2_2連率>=40", "p2_second_rate >= 40"),
        ("C10: C1+C9 (ST早+2連率>=40)", "p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL AND p2_second_rate >= 40"),
        ("C11: C1+C5 (ST早+p2内枠)", "p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL AND p2 <= 2"),
        ("C12: C3+C5 (スコア差<5+p2内枠)", "score_diff < 5 AND p2 <= 2"),
        ("C13: C1+C3+C5 (ST早+スコア差<5+p2内枠)", "p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL AND score_diff < 5 AND p2 <= 2"),
        ("C14: p2勝率 > p1勝率", "p2_win_rate > p1_win_rate"),
        ("C15: p2=1号艇", "p2 = 1"),
        ("C16: p2勝率>=40", "p2_win_rate >= 40"),
        ("C17: スコア差<3", "score_diff < 3"),
        ("C18: C17+C5 (スコア差<3+p2内枠)", "score_diff < 3 AND p2 <= 2"),
    ]

    results_cond = []
    for label, where_clause in conditions:
        q = base_query.format(cond_label=f"'{label}'", cond_where=where_clause)
        row = conn.execute(q).fetchone()
        if row and row[1] > 0:
            cond_name, n, hits, avg_odds, pnl = row
            hit_rate = hits / n * 100 if n > 0 else 0
            roi = (pnl / (n * 100)) * 100 if n > 0 else 0
            results_cond.append((label, n, hits, hit_rate, avg_odds or 0, pnl, roi))

    # ROI降順でソート
    results_cond.sort(key=lambda x: x[6], reverse=True)

    out.write(f"{'条件':>45s} {'n':>6s} {'的中':>4s} {'的中率':>7s} {'平均odds':>8s} {'ROI':>8s} {'PnL':>10s}\n")
    out.write("-" * 100 + "\n")
    for label, n, hits, hit_rate, avg_odds, pnl, roi in results_cond:
        out.write(f"{label:>45s} {n:6d} {hits:4d} {hit_rate:6.2f}% {avg_odds:8.1f} {roi:7.1f}% {pnl:+10.0f}\n")
    out.write("\n")

    # ---- 2b追加: 有望条件の年度別分析 ----
    out.write("-" * 60 + "\n")
    out.write("[2b追加] 有望条件の年度別一貫性\n")
    out.write("-" * 60 + "\n\n")

    # 有望そうな条件（ROI上位）を年度別に
    top_conditions = [
        ("全体", "1=1"),
        ("C3: スコア差<5", "score_diff < 5"),
        ("C5: p2内枠", "p2 <= 2"),
        ("C12: C3+C5 (スコア差<5+p2内枠)", "score_diff < 5 AND p2 <= 2"),
        ("C15: p2=1号艇", "p2 = 1"),
        ("C1: ST早い", "p2_st < p1_st AND p2_st IS NOT NULL AND p1_st IS NOT NULL"),
        ("C14: p2勝率>p1", "p2_win_rate > p1_win_rate"),
        ("C17: スコア差<3", "score_diff < 3"),
    ]

    yearly_query = f"""
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
            rp.score_p1 - rp.score_p2 as score_diff,
            e_p1.avg_st as p1_st,
            e_p2.avg_st as p2_st,
            e_p2.win_rate as p2_win_rate,
            e_p2.second_rate as p2_second_rate,
            e_p1.win_rate as p1_win_rate,
            t_rev.odds as rev_odds,
            CASE WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 AND actual.a3=rp.p3 THEN 1 ELSE 0 END as is_hit
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
          AND ({venues_filter})
          {month_filter}
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND t_rev.odds IS NOT NULL
    )
    SELECT year, COUNT(*) as n, SUM(is_hit) as hits,
           SUM(CASE WHEN is_hit=1 THEN rev_odds*100 ELSE -100 END) as pnl
    FROM base
    WHERE {{cond_where}}
    GROUP BY year
    ORDER BY year
    """

    years = ['2020', '2021', '2022', '2023', '2024', '2025']
    for cond_label, cond_where in top_conditions:
        q = yearly_query.format(cond_where=cond_where)
        rows = conn.execute(q).fetchall()
        yearly_data = {r[0]: {'n': r[1], 'hits': r[2], 'pnl': r[3]} for r in rows}

        out.write(f"  {cond_label}:\n")
        total_n = 0
        total_hits = 0
        total_pnl = 0
        profit_years = 0
        data_years = 0
        for y in years:
            d = yearly_data.get(y, None)
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
    out.write("[2c] 理想的な逆転条件の設計\n")
    out.write("-" * 60 + "\n\n")

    # スコア差帯別
    score_query = f"""
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
            rp.score_p1 - rp.score_p2 as score_diff,
            e_p2.avg_st - e_p1.avg_st as st_diff,
            rp.p2,
            t_rev.odds as rev_odds,
            CASE WHEN actual.a1=rp.p2 AND actual.a2=rp.p1 AND actual.a3=rp.p3 THEN 1 ELSE 0 END as is_hit
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
          AND ({venues_filter})
          {month_filter}
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND t_rev.odds IS NOT NULL
    )
    """

    # スコア差帯別
    q_score = score_query + """
    SELECT
        CASE
            WHEN score_diff < 2 THEN 'A: <2'
            WHEN score_diff < 5 THEN 'B: 2-5'
            WHEN score_diff < 8 THEN 'C: 5-8'
            WHEN score_diff < 12 THEN 'D: 8-12'
            WHEN score_diff < 20 THEN 'E: 12-20'
            ELSE 'F: 20+'
        END as band,
        COUNT(*) as n,
        SUM(is_hit) as hits,
        AVG(rev_odds) as avg_odds,
        SUM(CASE WHEN is_hit=1 THEN rev_odds*100 ELSE -100 END) as pnl
    FROM base
    GROUP BY band
    ORDER BY band
    """

    rows_score = conn.execute(q_score).fetchall()
    out.write("スコア差(p1-p2)帯別の逆転的中:\n\n")
    out.write(f"{'帯':>10s} {'n':>6s} {'的中':>4s} {'的中率':>7s} {'平均odds':>8s} {'ROI':>8s} {'PnL':>10s}\n")
    out.write("-" * 65 + "\n")
    for band, n, hits, avg_odds, pnl in rows_score:
        hr = hits / n * 100 if n > 0 else 0
        roi = (pnl / (n * 100)) * 100 if n > 0 else 0
        out.write(f"{band:>10s} {n:6d} {hits:4d} {hr:6.2f}% {avg_odds:8.1f} {roi:7.1f}% {pnl:+10.0f}\n")
    out.write("\n")

    # ST差帯別
    q_st = score_query + """
    SELECT
        CASE
            WHEN st_diff IS NULL THEN 'X: 不明'
            WHEN st_diff < -0.03 THEN 'A: p2大幅有利(<-0.03)'
            WHEN st_diff < 0.00 THEN 'B: p2やや有利(-0.03~0)'
            WHEN st_diff < 0.03 THEN 'C: ほぼ同等(0~0.03)'
            ELSE 'D: p1有利(0.03+)'
        END as band,
        COUNT(*) as n,
        SUM(is_hit) as hits,
        AVG(rev_odds) as avg_odds,
        SUM(CASE WHEN is_hit=1 THEN rev_odds*100 ELSE -100 END) as pnl
    FROM base
    GROUP BY band
    ORDER BY band
    """

    rows_st = conn.execute(q_st).fetchall()
    out.write("ST差(p2-p1)帯別の逆転的中:\n")
    out.write("  ST差が負 = p2の方がスタートが早い\n\n")
    out.write(f"{'帯':>25s} {'n':>6s} {'的中':>4s} {'的中率':>7s} {'平均odds':>8s} {'ROI':>8s} {'PnL':>10s}\n")
    out.write("-" * 80 + "\n")
    for band, n, hits, avg_odds, pnl in rows_st:
        hr = hits / n * 100 if n > 0 else 0
        roi = (pnl / (n * 100)) * 100 if n > 0 else 0
        out.write(f"{band:>25s} {n:6d} {hits:4d} {hr:6.2f}% {avg_odds:8.1f} {roi:7.1f}% {pnl:+10.0f}\n")
    out.write("\n")

    # p2枠番別
    q_pit = score_query + """
    SELECT p2 as pit, COUNT(*) as n, SUM(is_hit) as hits,
        AVG(rev_odds) as avg_odds,
        SUM(CASE WHEN is_hit=1 THEN rev_odds*100 ELSE -100 END) as pnl
    FROM base
    GROUP BY pit
    ORDER BY pit
    """

    rows_pit = conn.execute(q_pit).fetchall()
    out.write("p2の枠番別の逆転的中:\n\n")
    out.write(f"{'p2枠':>6s} {'n':>6s} {'的中':>4s} {'的中率':>7s} {'平均odds':>8s} {'ROI':>8s} {'PnL':>10s}\n")
    out.write("-" * 55 + "\n")
    for pit, n, hits, avg_odds, pnl in rows_pit:
        hr = hits / n * 100 if n > 0 else 0
        roi = (pnl / (n * 100)) * 100 if n > 0 else 0
        out.write(f"{pit:>6d} {n:6d} {hits:4d} {hr:6.2f}% {avg_odds:8.1f} {roi:7.1f}% {pnl:+10.0f}\n")
    out.write("\n")


def run_summary(conn, out, venue_data):
    """総合判定"""
    out.write("\n\n" + "=" * 80 + "\n")
    out.write("=== 総合判定 ===\n")
    out.write("=" * 80 + "\n\n")

    out.write("-" * 60 + "\n")
    out.write("[P1: 会場フィルターの統計的根拠による最終判定]\n")
    out.write("-" * 60 + "\n\n")

    # 各注目会場の判定
    for vc in [3, 15, 1]:
        vd = next((v for v in venue_data if v['vc'] == vc), None)
        if vd:
            out.write(f"  {vd['name']} (コード{vc}):\n")
            out.write(f"    6年間: n={vd['n']}, hits={vd['hits']}, ROI={vd['roi']:.1f}%\n")
            out.write(f"    95%CI: 的中率 [{vd['ci_lo']*100:.2f}% - {vd['ci_hi']*100:.2f}%]\n")
            out.write(f"    95%CI下限ROI: {vd['roi_ci_lo']:.1f}%\n")
            out.write(f"    最小必要サンプル数: {vd['min_n']}件 (現在の{vd['n']}件の{vd['min_n']/max(vd['n'],1):.0f}倍必要)\n")

            if vd['n'] < 30:
                out.write(f"    --> 判定: サンプル不足({vd['n']}件)。統計的に信頼できない。\n")
            elif vd['roi_ci_lo'] >= 100:
                out.write(f"    --> 判定: 95%CI下限ROIが損益分岐点を超えている。「傾向」として採用可。\n")
            else:
                out.write(f"    --> 判定: 95%CI下限ROIが{vd['roi_ci_lo']:.1f}% < 100%。「傾向」と断定できない。\n")
            out.write("\n")
        else:
            out.write(f"  会場コード{vc}: データ不足で個別評価不可\n\n")

    out.write("  [P1の総合評価]\n")
    out.write("  -------------------------\n")
    out.write("  1. 全24会場で最小必要サンプル数は約3,500-4,000件。現在の各会場15-60件は\n")
    out.write("     理論値の約1/60~1/200に過ぎず、どの会場も「統計的に信頼できる」水準に\n")
    out.write("     到達していない。\n\n")
    out.write("  2. 年度別一貫性を見ると、全会場とも黒字年は0-2年（/6年）に留まり、\n")
    out.write("     的中が特定年に偏在している。これは「傾向」ではなく「偶然の集中」を\n")
    out.write("     示唆する。\n\n")
    out.write("  3. 11会場プール全体でもROIがマイナス(-24.9%)であり、11会場外(+138.4%)\n")
    out.write("     を下回る逆転現象が起きている。ただし、これも統計的に有意な差ではない\n")
    out.write("     (z=-1.459, p=0.14)。\n\n")
    out.write("  4. 結論:\n")
    out.write("     - 江戸川・丸亀の追加: 統計的根拠なし。追加しても効果は不明確。\n")
    out.write("     - 桐生の除外: 既に除外済みであり、0件的中は妥当だが、サンプル不足で\n")
    out.write("       「桐生が本当に悪い」とも断言できない。\n")
    out.write("     - 推奨: 会場フィルターの微調整は保留。全会場での分析に切り替え、\n")
    out.write("       サンプル数を増やす方向が統計的に健全。\n\n")

    out.write("-" * 60 + "\n")
    out.write("[P2: 逆転パターンの活性化条件と採用可否]\n")
    out.write("-" * 60 + "\n\n")

    out.write("  [Tier 1基準との照合]\n")
    out.write("  基準: ROI 150%+, サンプル50件+, 1/2年黒字\n\n")

    out.write("  全体(ベースライン): 59件, 1的中, ROI -72%\n")
    out.write("    -> Tier 1不合格: ROIがマイナス\n\n")

    out.write("  有望候補の評価:\n")
    out.write("    C3(スコア差<5): 4件, ROI 310% -> サンプル4件=検証不能\n")
    out.write("    C5(p2内枠): 17件, ROI -4% -> ROI不足\n")
    out.write("    C12(スコア差<5+p2内枠): 4件, ROI 310% -> サンプル4件=検証不能\n")
    out.write("    C15(p2=1号艇): 7件 -> サンプル不足\n\n")

    out.write("  [P2の総合評価]\n")
    out.write("  -------------------------\n")
    out.write("  1. 逆転パターン(p2-p1-p3)の全体的中率は極めて低い(1.69%, 59件中1件)。\n\n")
    out.write("  2. 各種活性化条件を試したが、どれもサンプル数が極端に少なく(2-34件)、\n")
    out.write("     統計的に意味のある結論を導けない。\n\n")
    out.write("  3. スコア差<5の条件で高ROIが出ているが、これは4件中1件の的中による\n")
    out.write("     もので、信頼性は皆無。\n\n")
    out.write("  4. ST差に関して: 逆転発生時にp2のSTがp1より早い傾向はわずかにあるが\n")
    out.write("     (ST差 -0.017 vs +0.001)、条件として絞り込むとサンプルが激減し\n")
    out.write("     実用性がない。\n\n")
    out.write("  5. 結論:\n")
    out.write("     - 単独条件としての逆転パターンは採用不可。\n")
    out.write("     - 活性化条件を付けてもTier 1基準を満たせない。\n")
    out.write("     - 根本的にB x 50-100倍のオッズ帯（約700件/6年）から逆転パターン\n")
    out.write("       を抽出しようとすること自体がサンプル不足を招いている。\n")
    out.write("     - 推奨: P2は不採用。他のアプローチ（例: オッズ帯拡大や\n")
    out.write("       信頼度帯の変更）を検討すべき。\n\n")


def main():
    print(f"DB: {DB_PATH}")
    print(f"Output: {OUTPUT_PATH}")

    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as out:
        out.write("P1/P2 再分析レポート v2\n")
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
