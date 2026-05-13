"""
荒れパターン分析スクリプト
upset_pattern_analysis.py

目的: 高配当的中が出やすい「荒れレース」の条件・パターンを特定し、
     荒れ専用購入条件の設計材料を得る。

背景:
- TJ-3/4検証で「高avg_st・低スコア差 = 荒れやすい = 高配当源泉」の構造が明確に
- 既存条件（B×50-100倍）では高avg_stレースがROI 397%と収益の中核
- 荒れ専用条件（信頼度C/D × 高オッズ帯）の設計に向けた詳細分析が必要

分析対象: 2020-2025年 全予測レース（before予測）

分析軸:
1. [基礎] 信頼度別 × オッズ帯別の的中率・ROI・平均配当
2. [avg_st] 予測1位選手のavg_st × 的中率 × 平均配当（荒れ構造の確認）
3. [スコア差] 予測スコア差 × 荒れ頻度（接戦ほど荒れるか）
4. [会場] 会場別荒れやすさ（高配当的中率・平均配当）
5. [月別] 季節・月別の荒れ頻度
6. [複合] 高配当的中が集中する条件の組み合わせ特定

荒れの定義: 三連単オッズ 50倍以上を「荒れ」とする
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

VENUE_NAMES = {
    1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川",
    6: "浜名湖", 7: "蒲郡", 8: "常滑", 9: "津", 10: "三国",
    11: "びわこ", 12: "住之江", 13: "尼崎", 14: "鳴門", 15: "丸亀",
    16: "児島", 17: "宮島", 18: "徳山", 19: "下関", 20: "若松",
    21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村"
}


def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ===================================================================
# メインCTE: before予測 + 結果 + オッズ + avg_st + スコア差
# ===================================================================
MAIN_CTE = """
WITH rp1 AS (
    SELECT race_id, pit_number, total_score, confidence
    FROM race_predictions
    WHERE prediction_type = 'before' AND rank_prediction = 1
),
rp2 AS (
    SELECT race_id, pit_number, total_score
    FROM race_predictions
    WHERE prediction_type = 'before' AND rank_prediction = 2
),
rp3 AS (
    SELECT race_id, pit_number
    FROM race_predictions
    WHERE prediction_type = 'before' AND rank_prediction = 3
),
actual AS (
    SELECT r1.race_id,
           r1.pit_number as rank1,
           r2.pit_number as rank2,
           r3.pit_number as rank3
    FROM results r1
    JOIN results r2 ON r1.race_id = r2.race_id AND r2.rank = '2'
    JOIN results r3 ON r1.race_id = r3.race_id AND r3.rank = '3'
    WHERE r1.rank = '1'
      AND r1.is_invalid = 0
      AND r2.is_invalid = 0
      AND r3.is_invalid = 0
),
base AS (
    SELECT
        r.id as race_id,
        r.venue_code,
        r.race_date,
        CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
        CAST(strftime('%m', r.race_date) AS INTEGER) as month,
        rp1.confidence,
        rp1.pit_number as p1,
        rp2.pit_number as p2,
        rp3.pit_number as p3,
        rp1.total_score as score1,
        rp2.total_score as score2,
        (rp1.total_score - rp2.total_score) as score_gap,
        actual.rank1, actual.rank2, actual.rank3,
        CASE WHEN rp1.pit_number = actual.rank1
              AND rp2.pit_number = actual.rank2
              AND rp3.pit_number = actual.rank3
         THEN 1 ELSE 0 END as is_hit,
        t.odds,
        e.avg_st as p1_avg_st
    FROM races r
    JOIN rp1 ON r.id = rp1.race_id
    JOIN rp2 ON r.id = rp2.race_id
    JOIN rp3 ON r.id = rp3.race_id
    JOIN actual ON r.id = actual.race_id
    LEFT JOIN trifecta_odds t ON r.id = t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                         || CAST(rp2.pit_number AS TEXT) || '-'
                         || CAST(rp3.pit_number AS TEXT)
    LEFT JOIN entries e ON r.id = e.race_id AND e.pit_number = rp1.pit_number
    WHERE r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
)
"""

# ===================================================================
# Step 1: 基礎集計 - 信頼度別 × オッズ帯別
# ===================================================================

def analyze_by_confidence_odds(conn):
    print("=" * 70)
    print("Step 1: 信頼度別 × オッズ帯別 的中率・ROI")
    print("=" * 70)

    query = MAIN_CTE + """
    SELECT
        confidence,
        CASE
            WHEN odds IS NULL OR odds = 0 THEN 'オッズなし'
            WHEN odds < 10 THEN '1-9倍'
            WHEN odds < 20 THEN '10-19倍'
            WHEN odds < 30 THEN '20-29倍'
            WHEN odds < 50 THEN '30-49倍'
            WHEN odds < 100 THEN '50-99倍'
            WHEN odds < 200 THEN '100-199倍'
            ELSE '200倍+'
        END as odds_range,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(
            CASE WHEN SUM(is_hit) > 0
                 THEN AVG(CASE WHEN is_hit = 1 THEN odds END)
                 ELSE 0
            END, 1) as avg_odds_on_hit,
        ROUND(
            (SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - COUNT(*) * 100.0)
            / (COUNT(*) * 100.0) * 100 + 100, 1) as roi
    FROM base
    WHERE confidence IN ('A', 'B', 'C', 'D')
    GROUP BY confidence, odds_range
    ORDER BY confidence,
        CASE odds_range
            WHEN '1-9倍' THEN 1
            WHEN '10-19倍' THEN 2
            WHEN '20-29倍' THEN 3
            WHEN '30-49倍' THEN 4
            WHEN '50-99倍' THEN 5
            WHEN '100-199倍' THEN 6
            WHEN '200倍+' THEN 7
            ELSE 8
        END
    """

    df = pd.read_sql_query(query, conn)
    if df.empty:
        print("データなし")
        return

    for conf in ['A', 'B', 'C', 'D']:
        sub = df[df['confidence'] == conf]
        if sub.empty:
            continue
        print(f"\n【信頼度 {conf}】")
        print(f"{'オッズ帯':<12} {'件数':>6} {'的中':>5} {'的中率':>7} {'的中時平均オッズ':>16} {'ROI':>7}")
        print("-" * 65)
        for _, row in sub.iterrows():
            hit_info = f"{row['avg_odds_on_hit']:>10.1f}倍" if row['hits'] > 0 else "       N/A"
            print(f"{row['odds_range']:<12} {row['total']:>6} {row['hits']:>5} {row['hit_rate']:>6.2f}%"
                  f" {hit_info}  {row['roi']:>6.1f}%")


# ===================================================================
# Step 2: B条件でのavg_st別分析（荒れ構造の確認）
# ===================================================================

def analyze_avgst_in_b_condition(conn):
    print("\n" + "=" * 70)
    print("Step 2: B条件 × avg_st × オッズ帯別 的中率・ROI")
    print("（TJ-3の教訓：高avg_st＝荒れやすい＝高オッズ帯の利益源泉）")
    print("=" * 70)

    query = MAIN_CTE + """
    SELECT
        CASE
            WHEN p1_avg_st IS NULL THEN 'avg_stなし'
            WHEN p1_avg_st <= 0.15 THEN '<=0.15（超安定）'
            WHEN p1_avg_st <= 0.17 THEN '0.15-0.17（安定）'
            WHEN p1_avg_st <= 0.19 THEN '0.17-0.19（普通）'
            WHEN p1_avg_st <= 0.21 THEN '0.19-0.21（やや不安定）'
            ELSE '0.21+（不安定）'
        END as avg_st_range,
        CASE
            WHEN odds IS NULL OR odds = 0 THEN 'オッズなし'
            WHEN odds < 30 THEN '1-29倍'
            WHEN odds < 50 THEN '30-49倍'
            WHEN odds < 100 THEN '50-99倍'
            WHEN odds < 200 THEN '100-199倍'
            ELSE '200倍+'
        END as odds_range,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(
            (SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - COUNT(*) * 100.0)
            / (COUNT(*) * 100.0) * 100 + 100, 1) as roi
    FROM base
    WHERE confidence = 'B'
    GROUP BY avg_st_range, odds_range
    ORDER BY
        CASE avg_st_range
            WHEN '<=0.15（超安定）' THEN 1
            WHEN '0.15-0.17（安定）' THEN 2
            WHEN '0.17-0.19（普通）' THEN 3
            WHEN '0.19-0.21（やや不安定）' THEN 4
            WHEN '0.21+（不安定）' THEN 5
            ELSE 6
        END,
        CASE odds_range
            WHEN '1-29倍' THEN 1
            WHEN '30-49倍' THEN 2
            WHEN '50-99倍' THEN 3
            WHEN '100-199倍' THEN 4
            WHEN '200倍+' THEN 5
            ELSE 6
        END
    """

    df = pd.read_sql_query(query, conn)
    if df.empty:
        print("データなし")
        return

    print(f"\n{'avg_st帯':<22} {'オッズ帯':<12} {'件数':>6} {'的中':>5} {'的中率':>7} {'ROI':>7}")
    print("-" * 65)
    prev_avg_st = None
    for _, row in df.iterrows():
        if row['avg_st_range'] != prev_avg_st:
            if prev_avg_st is not None:
                print()
            prev_avg_st = row['avg_st_range']
        print(f"{row['avg_st_range']:<22} {row['odds_range']:<12} {row['total']:>6} "
              f"{row['hits']:>5} {row['hit_rate']:>6.2f}% {row['roi']:>6.1f}%")

    # avg_st帯別サマリー（B条件全体）
    print("\n【B条件 avg_st帯別サマリー（全オッズ帯合計）】")
    summary_query = MAIN_CTE + """
    SELECT
        CASE
            WHEN p1_avg_st IS NULL THEN 'avg_stなし'
            WHEN p1_avg_st <= 0.15 THEN '<=0.15（超安定）'
            WHEN p1_avg_st <= 0.17 THEN '0.15-0.17（安定）'
            WHEN p1_avg_st <= 0.19 THEN '0.17-0.19（普通）'
            WHEN p1_avg_st <= 0.21 THEN '0.19-0.21（やや不安定）'
            ELSE '0.21+（不安定）'
        END as avg_st_range,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(AVG(odds), 1) as avg_odds,
        ROUND(
            (SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - COUNT(*) * 100.0)
            / (COUNT(*) * 100.0) * 100 + 100, 1) as roi,
        ROUND(
            SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE -100 END), 0) as pnl
    FROM base
    WHERE confidence = 'B'
      AND odds IS NOT NULL AND odds > 0
    GROUP BY avg_st_range
    ORDER BY
        CASE avg_st_range
            WHEN '<=0.15（超安定）' THEN 1
            WHEN '0.15-0.17（安定）' THEN 2
            WHEN '0.17-0.19（普通）' THEN 3
            WHEN '0.19-0.21（やや不安定）' THEN 4
            WHEN '0.21+（不安定）' THEN 5
            ELSE 6
        END
    """
    df2 = pd.read_sql_query(summary_query, conn)
    print(f"\n{'avg_st帯':<22} {'件数':>6} {'的中':>5} {'的中率':>7} {'平均オッズ':>10} {'ROI':>7} {'収支':>10}")
    print("-" * 75)
    for _, row in df2.iterrows():
        print(f"{row['avg_st_range']:<22} {row['total']:>6} {row['hits']:>5} "
              f"{row['hit_rate']:>6.2f}% {row['avg_odds']:>9.1f}倍 "
              f"{row['roi']:>6.1f}% {row['pnl']:>+10.0f}円")


# ===================================================================
# Step 3: スコア差別分析（接戦ほど荒れるか）
# ===================================================================

def analyze_by_score_gap(conn):
    print("\n" + "=" * 70)
    print("Step 3: 予測スコア差 × オッズ帯別 的中率・ROI")
    print("（スコア差が小さい = 実力拮抗 = 荒れやすい仮説の検証）")
    print("=" * 70)

    query = MAIN_CTE + """
    SELECT
        CASE
            WHEN score_gap IS NULL THEN 'スコアなし'
            WHEN score_gap <= 5 THEN '<=5pt（超接戦）'
            WHEN score_gap <= 10 THEN '5-10pt（接戦）'
            WHEN score_gap <= 15 THEN '10-15pt（やや差あり）'
            WHEN score_gap <= 20 THEN '15-20pt（差あり）'
            ELSE '20pt+（大差）'
        END as gap_range,
        confidence,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(AVG(CASE WHEN is_hit = 1 THEN odds END), 1) as avg_hit_odds,
        ROUND(
            (SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - COUNT(*) * 100.0)
            / (COUNT(*) * 100.0) * 100 + 100, 1) as roi
    FROM base
    WHERE confidence IN ('B', 'C', 'D')
      AND odds IS NOT NULL AND odds > 0
    GROUP BY gap_range, confidence
    ORDER BY
        CASE gap_range
            WHEN '<=5pt（超接戦）' THEN 1
            WHEN '5-10pt（接戦）' THEN 2
            WHEN '10-15pt（やや差あり）' THEN 3
            WHEN '15-20pt（差あり）' THEN 4
            WHEN '20pt+（大差）' THEN 5
            ELSE 6
        END, confidence
    """

    df = pd.read_sql_query(query, conn)
    if df.empty:
        print("データなし")
        return

    print(f"\n{'スコア差帯':<18} {'信頼度':>5} {'件数':>6} {'的中':>5} {'的中率':>7} {'的中時平均オッズ':>16} {'ROI':>7}")
    print("-" * 70)
    prev_gap = None
    for _, row in df.iterrows():
        if row['gap_range'] != prev_gap:
            if prev_gap is not None:
                print()
            prev_gap = row['gap_range']
        hit_odds = f"{row['avg_hit_odds']:.1f}倍" if pd.notna(row['avg_hit_odds']) else "  N/A"
        print(f"{row['gap_range']:<18} {row['confidence']:>5} {row['total']:>6} "
              f"{row['hits']:>5} {row['hit_rate']:>6.2f}% {hit_odds:>13}  {row['roi']:>6.1f}%")


# ===================================================================
# Step 4: 会場別荒れやすさ分析
# ===================================================================

def analyze_by_venue(conn):
    print("\n" + "=" * 70)
    print("Step 4: 会場別荒れやすさ（B条件、50倍+的中率・平均配当）")
    print("=" * 70)

    query = MAIN_CTE + """
    SELECT
        venue_code,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        SUM(CASE WHEN odds >= 50 AND is_hit = 1 THEN 1 ELSE 0 END) as upset_hits,
        ROUND(
            100.0 * SUM(CASE WHEN odds >= 50 AND is_hit = 1 THEN 1 ELSE 0 END)
            / COUNT(*), 2) as upset_rate,
        ROUND(AVG(CASE WHEN odds >= 50 AND is_hit = 1 THEN odds END), 1) as avg_upset_odds,
        ROUND(
            (SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - COUNT(*) * 100.0)
            / (COUNT(*) * 100.0) * 100 + 100, 1) as roi
    FROM base
    WHERE confidence = 'B'
      AND odds IS NOT NULL AND odds > 0
    GROUP BY venue_code
    HAVING COUNT(*) >= 50
    ORDER BY upset_rate DESC
    """

    df = pd.read_sql_query(query, conn)
    if df.empty:
        print("データなし")
        return

    print(f"\n{'会場':<10} {'件数':>6} {'的中率':>7} {'荒れ的中数':>10} {'荒れ率':>7} {'荒れ平均オッズ':>14} {'ROI':>7}")
    print("-" * 70)
    for _, row in df.iterrows():
        vname = VENUE_NAMES.get(int(row['venue_code']), f"会場{row['venue_code']}")
        avg_upset = f"{row['avg_upset_odds']:.1f}倍" if pd.notna(row['avg_upset_odds']) else "  N/A"
        print(f"{vname:<10} {row['total']:>6} {row['hit_rate']:>6.2f}% "
              f"{row['upset_hits']:>9} {row['upset_rate']:>6.2f}% "
              f"{avg_upset:>12}  {row['roi']:>6.1f}%")


# ===================================================================
# Step 5: 月別・季節別の荒れ傾向
# ===================================================================

def analyze_by_month(conn):
    print("\n" + "=" * 70)
    print("Step 5: 月別 荒れ傾向（B条件、50倍+的中率）")
    print("=" * 70)

    query = MAIN_CTE + """
    SELECT
        month,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        SUM(CASE WHEN odds >= 50 AND is_hit = 1 THEN 1 ELSE 0 END) as upset_hits,
        ROUND(
            100.0 * SUM(CASE WHEN odds >= 50 AND is_hit = 1 THEN 1 ELSE 0 END)
            / COUNT(*), 2) as upset_rate,
        ROUND(
            (SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - COUNT(*) * 100.0)
            / (COUNT(*) * 100.0) * 100 + 100, 1) as roi
    FROM base
    WHERE confidence = 'B'
      AND odds IS NOT NULL AND odds > 0
    GROUP BY month
    ORDER BY month
    """

    df = pd.read_sql_query(query, conn)
    if df.empty:
        print("データなし")
        return

    month_names = {1:"1月", 2:"2月", 3:"3月", 4:"4月", 5:"5月", 6:"6月",
                   7:"7月", 8:"8月", 9:"9月", 10:"10月", 11:"11月", 12:"12月"}

    print(f"\n{'月':<6} {'件数':>6} {'的中率':>7} {'荒れ的中数':>10} {'荒れ率':>7} {'ROI':>7}")
    print("-" * 50)
    for _, row in df.iterrows():
        mname = month_names.get(int(row['month']), f"{row['month']}月")
        print(f"{mname:<6} {row['total']:>6} {row['hit_rate']:>6.2f}% "
              f"{row['upset_hits']:>9} {row['upset_rate']:>6.2f}% "
              f"{row['roi']:>6.1f}%")


# ===================================================================
# Step 6: C/D条件の詳細分析（荒れ専用条件候補の探索）
# ===================================================================

def analyze_cd_conditions(conn):
    print("\n" + "=" * 70)
    print("Step 6: C/D条件の詳細分析（荒れ専用条件候補の探索）")
    print("=" * 70)

    # C/D条件 × オッズ帯別
    query = MAIN_CTE + """
    SELECT
        confidence,
        CASE
            WHEN odds < 50 THEN '50倍未満'
            WHEN odds < 100 THEN '50-99倍'
            WHEN odds < 200 THEN '100-199倍'
            WHEN odds < 300 THEN '200-299倍'
            ELSE '300倍+'
        END as odds_range,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(AVG(CASE WHEN is_hit = 1 THEN odds END), 1) as avg_hit_odds,
        ROUND(
            (SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - COUNT(*) * 100.0)
            / (COUNT(*) * 100.0) * 100 + 100, 1) as roi,
        ROUND(
            SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE -100 END), 0) as pnl
    FROM base
    WHERE confidence IN ('C', 'D')
      AND odds IS NOT NULL AND odds > 0
    GROUP BY confidence, odds_range
    ORDER BY confidence,
        CASE odds_range
            WHEN '50倍未満' THEN 1
            WHEN '50-99倍' THEN 2
            WHEN '100-199倍' THEN 3
            WHEN '200-299倍' THEN 4
            WHEN '300倍+' THEN 5
        END
    """

    df = pd.read_sql_query(query, conn)
    if df.empty:
        print("データなし")
        return

    print(f"\n{'信頼度':>5} {'オッズ帯':<12} {'件数':>6} {'的中':>5} {'的中率':>7} {'的中時平均オッズ':>16} {'ROI':>7} {'収支':>10}")
    print("-" * 75)
    prev_conf = None
    for _, row in df.iterrows():
        if row['confidence'] != prev_conf:
            if prev_conf is not None:
                print()
            prev_conf = row['confidence']
        hit_odds = f"{row['avg_hit_odds']:.1f}倍" if pd.notna(row['avg_hit_odds']) else "  N/A"
        print(f"{row['confidence']:>5} {row['odds_range']:<12} {row['total']:>6} "
              f"{row['hits']:>5} {row['hit_rate']:>6.2f}% {hit_odds:>13}  "
              f"{row['roi']:>6.1f}% {row['pnl']:>+10.0f}円")


# ===================================================================
# Step 7: 複合条件分析（荒れ条件の特定）
# ===================================================================

def analyze_complex_conditions(conn):
    print("\n" + "=" * 70)
    print("Step 7: 複合条件分析（荒れ専用条件の候補探索）")
    print("B条件 × avg_st>=0.17 × スコア差別 ROI分析")
    print("=" * 70)

    query = MAIN_CTE + """
    SELECT
        CASE
            WHEN p1_avg_st >= 0.21 THEN '0.21+（超不安定）'
            WHEN p1_avg_st >= 0.19 THEN '0.19-0.21（不安定）'
            WHEN p1_avg_st >= 0.17 THEN '0.17-0.19（普通）'
            WHEN p1_avg_st >= 0.15 THEN '0.15-0.17（安定）'
            ELSE '<=0.15（超安定）'
        END as avg_st_group,
        CASE
            WHEN score_gap <= 10 THEN 'スコア差<=10（接戦）'
            WHEN score_gap <= 20 THEN 'スコア差10-20（やや差）'
            ELSE 'スコア差20+（大差）'
        END as score_gap_group,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(AVG(odds), 1) as avg_odds,
        ROUND(AVG(CASE WHEN is_hit = 1 THEN odds END), 1) as avg_hit_odds,
        ROUND(
            (SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - COUNT(*) * 100.0)
            / (COUNT(*) * 100.0) * 100 + 100, 1) as roi,
        ROUND(
            SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE -100 END), 0) as pnl
    FROM base
    WHERE confidence = 'B'
      AND odds BETWEEN 50 AND 200
      AND p1_avg_st IS NOT NULL
      AND odds IS NOT NULL AND odds > 0
    GROUP BY avg_st_group, score_gap_group
    HAVING COUNT(*) >= 20
    ORDER BY
        CASE avg_st_group
            WHEN '<=0.15（超安定）' THEN 1
            WHEN '0.15-0.17（安定）' THEN 2
            WHEN '0.17-0.19（普通）' THEN 3
            WHEN '0.19-0.21（不安定）' THEN 4
            WHEN '0.21+（超不安定）' THEN 5
        END,
        CASE score_gap_group
            WHEN 'スコア差<=10（接戦）' THEN 1
            WHEN 'スコア差10-20（やや差）' THEN 2
            WHEN 'スコア差20+（大差）' THEN 3
        END
    """

    df = pd.read_sql_query(query, conn)
    if df.empty:
        print("データなし")
        return

    print(f"\n{'avg_st帯':<22} {'スコア差帯':<20} {'件数':>5} {'的中':>5} {'的中率':>7} {'平均オッズ':>10} {'ROI':>7} {'収支':>10}")
    print("-" * 90)
    prev_avg_st = None
    for _, row in df.iterrows():
        if row['avg_st_group'] != prev_avg_st:
            if prev_avg_st is not None:
                print()
            prev_avg_st = row['avg_st_group']
        print(f"{row['avg_st_group']:<22} {row['score_gap_group']:<20} {row['total']:>5} "
              f"{row['hits']:>5} {row['hit_rate']:>6.2f}% {row['avg_odds']:>9.1f}倍 "
              f"{row['roi']:>6.1f}% {row['pnl']:>+10.0f}円")


# ===================================================================
# Step 8: 年度別安定性チェック（有望条件の安定性確認）
# ===================================================================

def analyze_yearly_stability(conn):
    print("\n" + "=" * 70)
    print("Step 8: B条件 年度別安定性（高avg_st帯の年度別ROI）")
    print("荒れ専用条件の設計前に安定性を確認")
    print("=" * 70)

    query = MAIN_CTE + """
    SELECT
        year,
        CASE
            WHEN p1_avg_st IS NULL THEN 'avg_stなし'
            WHEN p1_avg_st <= 0.17 THEN '<=0.17（低）'
            ELSE '0.17+（高）'
        END as avg_st_group,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(
            (SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - COUNT(*) * 100.0)
            / (COUNT(*) * 100.0) * 100 + 100, 1) as roi,
        ROUND(
            SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE -100 END), 0) as pnl
    FROM base
    WHERE confidence = 'B'
      AND odds BETWEEN 50 AND 100
      AND odds IS NOT NULL AND odds > 0
    GROUP BY year, avg_st_group
    ORDER BY year, avg_st_group
    """

    df = pd.read_sql_query(query, conn)
    if df.empty:
        print("データなし")
        return

    print(f"\n（B条件 × オッズ50-100倍帯での年度別ROI）")
    print(f"\n{'年度':>4} {'avg_st帯':<15} {'件数':>6} {'的中':>5} {'的中率':>7} {'ROI':>7} {'収支':>10}")
    print("-" * 60)
    prev_year = None
    for _, row in df.iterrows():
        if row['year'] != prev_year:
            if prev_year is not None:
                print()
            prev_year = row['year']
        pnl_sign = "+" if row['pnl'] >= 0 else ""
        print(f"{row['year']:>4} {row['avg_st_group']:<15} {row['total']:>6} "
              f"{row['hits']:>5} {row['hit_rate']:>6.2f}% "
              f"{row['roi']:>6.1f}% {pnl_sign}{row['pnl']:>9.0f}円")


# ===================================================================
# Step 9: 荒れレース候補条件のまとめ
# ===================================================================

def summarize_upset_candidates(conn):
    print("\n" + "=" * 70)
    print("Step 9: 荒れ専用条件候補のサマリー（ROI > 150%, 件数>=30の条件）")
    print("=" * 70)

    # 試行する条件候補
    candidates = [
        {
            "name": "C×100-200倍",
            "where": "confidence = 'C' AND odds BETWEEN 100 AND 200",
        },
        {
            "name": "C×50-100倍",
            "where": "confidence = 'C' AND odds BETWEEN 50 AND 100",
        },
        {
            "name": "D×100-200倍",
            "where": "confidence = 'D' AND odds BETWEEN 100 AND 200",
        },
        {
            "name": "D×50-100倍",
            "where": "confidence = 'D' AND odds BETWEEN 50 AND 100",
        },
        {
            "name": "B×100-200倍 高avg_st",
            "where": "confidence = 'B' AND odds BETWEEN 100 AND 200 AND p1_avg_st >= 0.17",
        },
        {
            "name": "B×50-100倍 高avg_st",
            "where": "confidence = 'B' AND odds BETWEEN 50 AND 100 AND p1_avg_st >= 0.17",
        },
        {
            "name": "B×50-100倍 接戦(スコア差<=15)",
            "where": "confidence = 'B' AND odds BETWEEN 50 AND 100 AND score_gap <= 15",
        },
        {
            "name": "C×50-200倍 高avg_st",
            "where": "confidence = 'C' AND odds BETWEEN 50 AND 200 AND p1_avg_st >= 0.17",
        },
    ]

    print(f"\n{'条件名':<30} {'件数':>6} {'的中':>5} {'的中率':>7} {'ROI':>7} {'収支':>10} {'黒字年数':>8}")
    print("-" * 80)

    for cand in candidates:
        # 全体集計
        query = MAIN_CTE + f"""
        SELECT
            COUNT(*) as total,
            SUM(is_hit) as hits,
            ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
            ROUND(
                (SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - COUNT(*) * 100.0)
                / (COUNT(*) * 100.0) * 100 + 100, 1) as roi,
            ROUND(
                SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE -100 END), 0) as pnl
        FROM base
        WHERE {cand['where']}
          AND odds IS NOT NULL AND odds > 0
        """
        row = pd.read_sql_query(query, conn).iloc[0]

        # 年度別黒字数
        year_query = MAIN_CTE + f"""
        SELECT year,
            SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE -100 END) as pnl
        FROM base
        WHERE {cand['where']}
          AND odds IS NOT NULL AND odds > 0
        GROUP BY year
        """
        year_df = pd.read_sql_query(year_query, conn)
        black_years = (year_df['pnl'] > 0).sum() if not year_df.empty else 0
        total_years = len(year_df)

        if row['total'] < 30:
            print(f"{cand['name']:<30} {row['total']:>6}  ※件数不足")
            continue

        pnl = row['pnl']
        pnl_sign = "+" if pnl >= 0 else ""
        print(f"{cand['name']:<30} {row['total']:>6} {row['hits']:>5} "
              f"{row['hit_rate']:>6.2f}% {row['roi']:>6.1f}% "
              f"{pnl_sign}{pnl:>9.0f}円 {black_years}/{total_years}年")


# ===================================================================
# メイン実行
# ===================================================================

def main():
    print("=" * 70)
    print("荒れパターン分析スクリプト")
    print("目的: 高配当的中が出やすい「荒れレース」の条件・パターンを特定")
    print("分析対象: 2020-2025年 before予測 全レース")
    print("=" * 70)

    conn = get_connection()
    try:
        # まずデータ量確認
        check_query = MAIN_CTE + """
        SELECT
            COUNT(*) as total,
            SUM(is_hit) as hits,
            ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
            SUM(CASE WHEN odds >= 50 THEN 1 ELSE 0 END) as high_odds_races,
            SUM(CASE WHEN odds >= 50 AND is_hit = 1 THEN 1 ELSE 0 END) as high_odds_hits
        FROM base
        WHERE odds IS NOT NULL AND odds > 0
        """
        row = pd.read_sql_query(check_query, conn).iloc[0]
        print(f"\n【データ確認】")
        print(f"  全レース数: {row['total']:,}件（オッズデータあり）")
        print(f"  三連単的中数: {row['hits']:,}件（的中率 {row['hit_rate']:.2f}%）")
        print(f"  オッズ50倍+レース数: {row['high_odds_races']:,}件")
        print(f"  オッズ50倍+的中数: {row['high_odds_hits']:,}件")

        analyze_by_confidence_odds(conn)
        analyze_avgst_in_b_condition(conn)
        analyze_by_score_gap(conn)
        analyze_by_venue(conn)
        analyze_by_month(conn)
        analyze_cd_conditions(conn)
        analyze_complex_conditions(conn)
        analyze_yearly_stability(conn)
        summarize_upset_candidates(conn)

        print("\n" + "=" * 70)
        print("分析完了")
        print("=" * 70)
        print("\n【次のアクション】")
        print("1. Step 9のROI > 150% かつ 黒字年数 4/6年以上の条件をTier 1テストへ")
        print("2. Tier 1テスト: python scripts/backtest/quick_condition_test.py")
        print("3. 合格条件はTier 2（standard_backtest_unique.py）で本採用判定")
        print("4. 詳細: docs/guides/VALIDATION_WORKFLOW.md")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
