"""
展示タイム 活用可能性 分析スクリプト
Opus調査計画に基づく4段階分析

Step 1: 基礎統計（全体相関・会場別）
Step 2: 6艇間のタイム差×1着率（最優先）
Step 3: 展示vs本番の乖離パターン（会場別×枠番別）
Step 4: 風条件との組み合わせ
"""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def print_header(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)

def print_section(title):
    print()
    print(f"--- {title} ---")

# ============================================================
# Step 1: 基礎統計
# ============================================================
def step1_basic_stats():
    print_header("Step 1: 基礎統計")
    conn = get_conn()
    c = conn.cursor()

    # 全体: 展示タイム1位の艇が1着になる率
    print_section("展示タイム1位の艇の1着率（全体）")
    c.execute("""
        WITH exh_rank AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                rd.exhibition_time,
                RANK() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) AS exh_rank
            FROM race_details rd
            WHERE rd.exhibition_time IS NOT NULL
        ),
        valid_races AS (
            SELECT race_id
            FROM exh_rank
            GROUP BY race_id
            HAVING COUNT(*) = 6
        )
        SELECT
            COUNT(*) AS total_races,
            SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) AS wins,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_rate,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) / COUNT(*), 1) AS top3_rate
        FROM exh_rank er
        JOIN valid_races vr ON er.race_id = vr.race_id
        JOIN results res ON er.race_id = res.race_id AND er.pit_number = res.pit_number
        WHERE er.exh_rank = 1
          AND res.is_invalid = 0
          AND res.rank NOT IN ('F', 'L', 'K', 'S', 'E', '')
          AND CAST(res.rank AS INTEGER) > 0
    """)
    row = c.fetchone()
    if row:
        print(f"  レース数: {row['total_races']:,}")
        print(f"  1着率: {row['win_rate']}%  (ランダム期待値: 16.7%)")
        print(f"  3着以内率: {row['top3_rate']}%  (ランダム期待値: 50.0%)")

    # 展示タイム順位別の1着率
    print_section("展示タイム順位別 1着率")
    c.execute("""
        WITH exh_rank AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                rd.exhibition_time,
                RANK() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) AS exh_rank
            FROM race_details rd
            WHERE rd.exhibition_time IS NOT NULL
        ),
        valid_races AS (
            SELECT race_id FROM exh_rank GROUP BY race_id HAVING COUNT(*) = 6
        )
        SELECT
            er.exh_rank,
            COUNT(*) AS cnt,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_rate,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) / COUNT(*), 1) AS top3_rate
        FROM exh_rank er
        JOIN valid_races vr ON er.race_id = vr.race_id
        JOIN results res ON er.race_id = res.race_id AND er.pit_number = res.pit_number
        WHERE res.is_invalid = 0
          AND res.rank NOT IN ('F', 'L', 'K', 'S', 'E', '')
          AND CAST(res.rank AS INTEGER) > 0
        GROUP BY er.exh_rank
        ORDER BY er.exh_rank
    """)
    rows = c.fetchall()
    print(f"  {'展示順位':>6}  {'件数':>8}  {'1着率':>7}  {'3着率':>7}")
    for row in rows:
        print(f"  {row['exh_rank']:>6}位  {row['cnt']:>8,}  {row['win_rate']:>6.1f}%  {row['top3_rate']:>6.1f}%")

    conn.close()


# ============================================================
# Step 2: 6艇間のタイム差×1着率
# ============================================================
def step2_time_gap():
    print_header("Step 2: タイム差（トップ差）と1着率の関係")
    conn = get_conn()
    c = conn.cursor()

    # 各レースの最速タイムと2番目タイムをサブクエリで計算
    print_section("トップ差（1位-2位のタイム差）別 展示1位の1着率")
    c.execute("""
        WITH per_race AS (
            SELECT
                race_id,
                MIN(exhibition_time) AS min_time,
                -- 2番目: min を除いた最小
                (SELECT MIN(b.exhibition_time)
                 FROM race_details b
                 WHERE b.race_id = rd.race_id
                   AND b.exhibition_time > MIN(rd.exhibition_time)
                ) AS second_time
            FROM race_details rd
            WHERE exhibition_time IS NOT NULL
            GROUP BY race_id
            HAVING COUNT(*) = 6
        ),
        race_top_boat AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                ROUND(pr.second_time - pr.min_time, 3) AS top_gap
            FROM race_details rd
            JOIN per_race pr ON rd.race_id = pr.race_id
            WHERE rd.exhibition_time = pr.min_time
              AND pr.second_time IS NOT NULL
              AND pr.second_time > pr.min_time
        )
        SELECT
            CASE
                WHEN top_gap < 0.03 THEN '0.00-0.02'
                WHEN top_gap < 0.05 THEN '0.03-0.04'
                WHEN top_gap < 0.07 THEN '0.05-0.06'
                WHEN top_gap < 0.10 THEN '0.07-0.09'
                WHEN top_gap < 0.15 THEN '0.10-0.14'
                WHEN top_gap < 0.20 THEN '0.15-0.19'
                ELSE '0.20+'
            END AS gap_range,
            CASE
                WHEN top_gap < 0.03 THEN 0
                WHEN top_gap < 0.05 THEN 1
                WHEN top_gap < 0.07 THEN 2
                WHEN top_gap < 0.10 THEN 3
                WHEN top_gap < 0.15 THEN 4
                WHEN top_gap < 0.20 THEN 5
                ELSE 6
            END AS sort_key,
            COUNT(*) AS races,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_rate,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) / COUNT(*), 1) AS top3_rate
        FROM race_top_boat rtb
        JOIN results res ON rtb.race_id = res.race_id AND rtb.pit_number = res.pit_number
        WHERE res.is_invalid = 0
          AND res.rank NOT IN ('F', 'L', 'K', 'S', 'E', '')
          AND CAST(res.rank AS INTEGER) > 0
        GROUP BY gap_range, sort_key
        ORDER BY sort_key
    """)
    rows = c.fetchall()
    print(f"  {'タイム差(秒)':>12}  {'レース数':>8}  {'展示1位->1着率':>13}  {'展示1位->3着率':>13}")
    for row in rows:
        print(f"  {row['gap_range']:>12}  {row['races']:>8,}  {row['win_rate']:>12.1f}%  {row['top3_rate']:>12.1f}%")

    # 大差（0.1秒以上）のレースで展示順位別1着率
    print_section("タイム差 >= 0.10秒のレースでの展示順位別1着率（全体と比較）")
    c.execute("""
        WITH per_race AS (
            SELECT
                race_id,
                MIN(exhibition_time) AS min_time,
                (SELECT MIN(b.exhibition_time)
                 FROM race_details b
                 WHERE b.race_id = rd.race_id
                   AND b.exhibition_time > MIN(rd.exhibition_time)
                ) AS second_time
            FROM race_details rd
            WHERE exhibition_time IS NOT NULL
            GROUP BY race_id
            HAVING COUNT(*) = 6
        ),
        large_gap_races AS (
            SELECT race_id, min_time, second_time
            FROM per_race
            WHERE second_time - min_time >= 0.10
              AND second_time IS NOT NULL
        ),
        exh_rank_data AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                RANK() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) AS exh_rank
            FROM race_details rd
            JOIN large_gap_races lr ON rd.race_id = lr.race_id
            WHERE rd.exhibition_time IS NOT NULL
        )
        SELECT
            er.exh_rank,
            COUNT(*) AS cnt,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_rate,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) / COUNT(*), 1) AS top3_rate
        FROM exh_rank_data er
        JOIN results res ON er.race_id = res.race_id AND er.pit_number = res.pit_number
        WHERE res.is_invalid = 0
          AND res.rank NOT IN ('F', 'L', 'K', 'S', 'E', '')
          AND CAST(res.rank AS INTEGER) > 0
        GROUP BY er.exh_rank
        ORDER BY er.exh_rank
    """)
    rows = c.fetchall()
    print(f"  {'展示順位':>6}  {'件数':>8}  {'1着率':>7}  {'3着率':>7}")
    for row in rows:
        print(f"  {row['exh_rank']:>6}位  {row['cnt']:>8,}  {row['win_rate']:>6.1f}%  {row['top3_rate']:>6.1f}%")

    conn.close()


# ============================================================
# Step 3: 展示vs本番の乖離パターン（会場別）
# ============================================================
def step3_deviation_by_venue():
    print_header("Step 3: 展示タイム順位 vs 実着順 乖離パターン（会場別）")
    conn = get_conn()
    c = conn.cursor()

    # 会場ごとの展示1位→1着率
    print_section("会場別 展示タイム1位の1着率（高い順）")
    c.execute("""
        WITH exh_rank AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                RANK() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) AS exh_rank
            FROM race_details rd
            WHERE rd.exhibition_time IS NOT NULL
        ),
        valid_races AS (
            SELECT race_id FROM exh_rank GROUP BY race_id HAVING COUNT(*) = 6
        )
        SELECT
            ra.venue_code,
            COUNT(*) AS races,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_rate,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) / COUNT(*), 1) AS top3_rate
        FROM exh_rank er
        JOIN valid_races vr ON er.race_id = vr.race_id
        JOIN races ra ON er.race_id = ra.id
        JOIN results res ON er.race_id = res.race_id AND er.pit_number = res.pit_number
        WHERE er.exh_rank = 1
          AND res.is_invalid = 0
          AND res.rank NOT IN ('F', 'L', 'K', 'S', 'E', '')
          AND CAST(res.rank AS INTEGER) > 0
        GROUP BY ra.venue_code
        ORDER BY win_rate DESC
    """)
    rows = c.fetchall()
    venue_names = {
        1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川",
        6: "浜名湖", 7: "蒲郡", 8: "常滑", 9: "津", 10: "三国",
        11: "びわこ", 12: "住之江", 13: "尼崎", 14: "鳴門", 15: "丸亀",
        16: "児島", 17: "宮島", 18: "徳山", 19: "下関", 20: "若松",
        21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村"
    }
    print(f"  {'会場':>8}  {'レース数':>8}  {'1着率':>7}  {'3着率':>7}")
    for row in rows:
        name = venue_names.get(row['venue_code'], f"会場{row['venue_code']}")
        print(f"  {name:>8}  {row['races']:>8,}  {row['win_rate']:>6.1f}%  {row['top3_rate']:>6.1f}%")

    conn.close()


# ============================================================
# Step 4: 風条件との組み合わせ
# ============================================================
def step4_wind_combination():
    print_header("Step 4: 風速x展示タイム差の組み合わせ分析")
    conn = get_conn()
    c = conn.cursor()

    # 風速別 展示1位の1着率（タイム差も組み合わせ）
    print_section("風速別 展示タイム1位の1着率（全体 vs タイム差>=0.10秒）")
    c.execute("""
        WITH per_race AS (
            SELECT
                race_id,
                MIN(exhibition_time) AS min_time,
                (SELECT MIN(b.exhibition_time)
                 FROM race_details b
                 WHERE b.race_id = rd.race_id
                   AND b.exhibition_time > MIN(rd.exhibition_time)
                ) AS second_time
            FROM race_details rd
            WHERE exhibition_time IS NOT NULL
            GROUP BY race_id
            HAVING COUNT(*) = 6
        ),
        race_top_boat AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                ROUND(pr.second_time - pr.min_time, 3) AS top_gap
            FROM race_details rd
            JOIN per_race pr ON rd.race_id = pr.race_id
            WHERE rd.exhibition_time = pr.min_time
              AND pr.second_time IS NOT NULL
              AND pr.second_time > pr.min_time
        )
        SELECT
            CASE
                WHEN rc.wind_speed IS NULL THEN '  不明'
                WHEN rc.wind_speed <= 1 THEN '0-1m(微風)'
                WHEN rc.wind_speed <= 3 THEN '2-3m(弱風)'
                WHEN rc.wind_speed <= 5 THEN '4-5m(中風)'
                WHEN rc.wind_speed <= 7 THEN '6-7m(強風)'
                ELSE '8m+(強風)'
            END AS wind_range,
            CASE
                WHEN rc.wind_speed IS NULL THEN 99
                WHEN rc.wind_speed <= 1 THEN 0
                WHEN rc.wind_speed <= 3 THEN 1
                WHEN rc.wind_speed <= 5 THEN 2
                WHEN rc.wind_speed <= 7 THEN 3
                ELSE 4
            END AS sort_key,
            COUNT(*) AS all_races,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_rate_all,
            SUM(CASE WHEN rtb.top_gap >= 0.10 THEN 1 ELSE 0 END) AS large_gap_races,
            ROUND(100.0 * SUM(CASE WHEN rtb.top_gap >= 0.10 AND CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN rtb.top_gap >= 0.10 THEN 1 ELSE 0 END), 0), 1) AS win_rate_large_gap
        FROM race_top_boat rtb
        JOIN results res ON rtb.race_id = res.race_id AND rtb.pit_number = res.pit_number
        LEFT JOIN race_conditions rc ON rtb.race_id = rc.race_id
        WHERE res.is_invalid = 0
          AND res.rank NOT IN ('F', 'L', 'K', 'S', 'E', '')
          AND CAST(res.rank AS INTEGER) > 0
          AND rtb.top_gap >= 0
        GROUP BY wind_range, sort_key
        ORDER BY sort_key
    """)
    rows = c.fetchall()
    print(f"  {'風速':>10}  {'全件数':>8}  {'全1着率':>8}  {'大差件数':>8}  {'大差1着率':>10}")
    for row in rows:
        improvement = (row['win_rate_large_gap'] or 0) - row['win_rate_all']
        print(f"  {row['wind_range']:>10}  {row['all_races']:>8,}  {row['win_rate_all']:>7.1f}%  "
              f"{row['large_gap_races']:>8,}  {row['win_rate_large_gap']:>9.1f}%  "
              f"({improvement:+.1f}pt)")

    conn.close()


# ============================================================
# Step 5: 会場別 + タイム差 の組み合わせ（購入条件候補）
# ============================================================
def step5_venue_gap_filter():
    print_header("Step 5: タイム差フィルタ効果（購入条件候補探索）")
    conn = get_conn()
    c = conn.cursor()

    # タイム差 >= 0.10秒 の会場別1着率 vs 全体1着率の比較
    print_section("タイム差 >= 0.10秒 フィルタ時の会場別1着率（高い順）")
    c.execute("""
        WITH per_race AS (
            SELECT
                race_id,
                MIN(exhibition_time) AS min_time,
                (SELECT MIN(b.exhibition_time)
                 FROM race_details b
                 WHERE b.race_id = rd.race_id
                   AND b.exhibition_time > MIN(rd.exhibition_time)
                ) AS second_time
            FROM race_details rd
            WHERE exhibition_time IS NOT NULL
            GROUP BY race_id
            HAVING COUNT(*) = 6
        ),
        race_top_boat AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                ROUND(pr.second_time - pr.min_time, 3) AS top_gap
            FROM race_details rd
            JOIN per_race pr ON rd.race_id = pr.race_id
            WHERE rd.exhibition_time = pr.min_time
              AND pr.second_time IS NOT NULL
              AND pr.second_time > pr.min_time
        )
        SELECT
            ra.venue_code,
            COUNT(*) AS total_races,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_rate_all,
            SUM(CASE WHEN rtb.top_gap >= 0.10 THEN 1 ELSE 0 END) AS filtered_races,
            ROUND(100.0 * SUM(CASE WHEN rtb.top_gap >= 0.10 AND CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN rtb.top_gap >= 0.10 THEN 1 ELSE 0 END), 0), 1) AS win_rate_filtered
        FROM race_top_boat rtb
        JOIN races ra ON rtb.race_id = ra.id
        JOIN results res ON rtb.race_id = res.race_id AND rtb.pit_number = res.pit_number
        WHERE res.is_invalid = 0
          AND res.rank NOT IN ('F', 'L', 'K', 'S', 'E', '')
          AND CAST(res.rank AS INTEGER) > 0
          AND rtb.top_gap >= 0
        GROUP BY ra.venue_code
        HAVING filtered_races >= 100
        ORDER BY win_rate_filtered DESC
    """)
    rows = c.fetchall()
    venue_names = {
        1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川",
        6: "浜名湖", 7: "蒲郡", 8: "常滑", 9: "津", 10: "三国",
        11: "びわこ", 12: "住之江", 13: "尼崎", 14: "鳴門", 15: "丸亀",
        16: "児島", 17: "宮島", 18: "徳山", 19: "下関", 20: "若松",
        21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村"
    }
    print(f"  {'会場':>6}  {'全件数':>7}  {'全1着率':>8}  {'フィルタ件数':>12}  {'フィルタ1着率':>13}  {'改善':>7}")
    for row in rows:
        name = venue_names.get(row['venue_code'], f"会場{row['venue_code']}")
        improvement = (row['win_rate_filtered'] or 0) - row['win_rate_all']
        marker = " ★" if improvement >= 2.0 else ""
        print(f"  {name:>6}  {row['total_races']:>7,}  {row['win_rate_all']:>7.1f}%  "
              f"{row['filtered_races']:>12,}  {row['win_rate_filtered']:>12.1f}%  "
              f"{improvement:>+6.1f}pt{marker}")

    conn.close()


if __name__ == "__main__":
    import sys

    steps = sys.argv[1:] if len(sys.argv) > 1 else ["1", "2", "3", "4", "5"]

    if "1" in steps:
        step1_basic_stats()
    if "2" in steps:
        step2_time_gap()
    if "3" in steps:
        step3_deviation_by_venue()
    if "4" in steps:
        step4_wind_combination()
    if "5" in steps:
        step5_venue_gap_filter()
