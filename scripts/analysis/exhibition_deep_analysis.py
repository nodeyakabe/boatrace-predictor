"""
展示タイム 徹底調査スクリプト
「展示タイム差 = 機力差」の仮説を多角的に検証する

分析項目:
1. タイム差の分布（どのくらいの差がどの頻度で発生するか）
2. タイム差閾値別 × コース別 1着率（最適閾値探索）
3. 会場別 展示タイムの予測力（会場ごとの相関強度）
4. タイム差 × 枠番 最適マトリックス
5. 展示順位ごとのタイム差別1着率（1位だけでなく2位以下も）
6. 「大差レース」での着順分布（機力差が大きい場合のレース展開）
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

VENUE_NAMES = {
    1:"桐生", 2:"戸田", 3:"江戸川", 4:"平和島", 5:"多摩川",
    6:"浜名湖", 7:"蒲郡", 8:"常滑", 9:"津", 10:"三国",
    11:"びわこ", 12:"住之江", 13:"尼崎", 14:"鳴門", 15:"丸亀",
    16:"児島", 17:"宮島", 18:"徳山", 19:"下関", 20:"若松",
    21:"芦屋", 22:"福岡", 23:"唐津", 24:"大村"
}

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def header(s): print(f"\n{'='*72}\n  {s}\n{'='*72}")
def section(s): print(f"\n--- {s} ---")

# ============================================================
# 共通CTE: レースごとの最速・2番目タイムを計算
# ============================================================
RACE_GAP_CTE = """
WITH race_min AS (
    SELECT race_id, MIN(exhibition_time) AS best_time
    FROM race_details
    WHERE exhibition_time IS NOT NULL
    GROUP BY race_id
    HAVING COUNT(*) = 6
),
race_second AS (
    SELECT rm.race_id, rm.best_time,
        MIN(rd2.exhibition_time) AS second_time
    FROM race_min rm
    JOIN race_details rd2 ON rm.race_id = rd2.race_id
        AND rd2.exhibition_time > rm.best_time
    GROUP BY rm.race_id, rm.best_time
),
race_gap_base AS (
    SELECT
        rs.race_id,
        rs.best_time,
        rs.second_time,
        ROUND(rs.second_time - rs.best_time, 3) AS gap
    FROM race_second rs
    WHERE rs.second_time IS NOT NULL AND rs.second_time > rs.best_time
),
top_boat AS (
    SELECT rgb.race_id, rd3.pit_number, rgb.gap
    FROM race_gap_base rgb
    JOIN race_details rd3 ON rgb.race_id = rd3.race_id
        AND rgb.best_time = rd3.exhibition_time
)
"""

def analysis1_gap_distribution():
    """タイム差の全体分布"""
    header("分析1: タイム差の分布（何秒差がどの頻度で発生するか）")
    db = conn()
    c = db.cursor()

    c.execute(f"""
        {RACE_GAP_CTE}
        SELECT
            CASE
                WHEN gap < 0.02 THEN '0.00-0.01'
                WHEN gap < 0.03 THEN '0.02'
                WHEN gap < 0.04 THEN '0.03'
                WHEN gap < 0.05 THEN '0.04'
                WHEN gap < 0.06 THEN '0.05'
                WHEN gap < 0.07 THEN '0.06'
                WHEN gap < 0.08 THEN '0.07'
                WHEN gap < 0.09 THEN '0.08'
                WHEN gap < 0.10 THEN '0.09'
                WHEN gap < 0.12 THEN '0.10-0.11'
                WHEN gap < 0.15 THEN '0.12-0.14'
                WHEN gap < 0.20 THEN '0.15-0.19'
                ELSE '0.20+'
            END AS gap_label,
            CASE
                WHEN gap < 0.02 THEN 0 WHEN gap < 0.03 THEN 1
                WHEN gap < 0.04 THEN 2 WHEN gap < 0.05 THEN 3
                WHEN gap < 0.06 THEN 4 WHEN gap < 0.07 THEN 5
                WHEN gap < 0.08 THEN 6 WHEN gap < 0.09 THEN 7
                WHEN gap < 0.10 THEN 8 WHEN gap < 0.12 THEN 9
                WHEN gap < 0.15 THEN 10 WHEN gap < 0.20 THEN 11
                ELSE 12
            END AS sort_key,
            COUNT(*) AS races
        FROM race_gap_base
        GROUP BY gap_label, sort_key
        ORDER BY sort_key
    """)
    rows = c.fetchall()
    total = sum(r['races'] for r in rows)
    cumulative = 0

    print(f"  {'差(秒)':>10}  {'レース数':>8}  {'割合':>6}  {'累積':>6}  {'バー'}")
    for row in rows:
        pct = 100.0 * row['races'] / total
        cumulative += row['races']
        cum_pct = 100.0 * cumulative / total
        bar = '#' * int(pct * 2)
        print(f"  {row['gap_label']:>10}  {row['races']:>8,}  {pct:>5.1f}%  {cum_pct:>5.1f}%  {bar}")
    print(f"  {'合計':>10}  {total:>8,}")

    # 重要な閾値の出現率
    section("重要閾値の出現率")
    for threshold in [0.03, 0.05, 0.07, 0.10, 0.15]:
        c.execute(f"""
            {RACE_GAP_CTE}
            SELECT COUNT(*) AS cnt FROM race_gap_base WHERE gap >= {threshold}
        """)
        cnt = c.fetchone()['cnt']
        pct = 100.0 * cnt / total
        print(f"  差 >= {threshold:.2f}秒:  {cnt:>7,}件  ({pct:.1f}%)")
    db.close()


def analysis2_threshold_by_course():
    """閾値別 × 枠番別 1着率（最適閾値探索）"""
    header("分析2: タイム差閾値 × 枠番 展示1位の1着率")
    db = conn()
    c = db.cursor()

    thresholds = [0.00, 0.03, 0.05, 0.07, 0.10, 0.15]

    print(f"\n  {'枠番':>5}  {'全体':>7}", end="")
    for t in thresholds[1:]:
        print(f"  {'>={:.2f}s'.format(t):>8}", end="")
    print()

    # 枠番グループ別
    pit_groups = [
        ("枠1", "tb.pit_number = 1"),
        ("枠2", "tb.pit_number = 2"),
        ("枠3", "tb.pit_number = 3"),
        ("枠4", "tb.pit_number = 4"),
        ("枠5", "tb.pit_number = 5"),
        ("枠6", "tb.pit_number = 6"),
        ("枠1-3", "tb.pit_number IN (1,2,3)"),
        ("枠4-6", "tb.pit_number IN (4,5,6)"),
    ]

    for label, where in pit_groups:
        print(f"  {label:>5}", end="")
        for t in thresholds:
            gap_cond = f"AND tb.gap >= {t}" if t > 0 else ""
            c.execute(f"""
                {RACE_GAP_CTE}
                SELECT
                    COUNT(*) AS races,
                    ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END)
                        / COUNT(*), 1) AS win_rate
                FROM top_boat tb
                JOIN results res ON tb.race_id = res.race_id AND tb.pit_number = res.pit_number
                WHERE res.is_invalid = 0
                  AND res.rank NOT IN ('F','L','K','S','E','')
                  AND CAST(res.rank AS INTEGER) > 0
                  AND {where}
                  {gap_cond}
            """)
            row = c.fetchone()
            wr = row['win_rate'] if row['win_rate'] else 0.0
            print(f"  {wr:>7.1f}%", end="")
        print()

    db.close()


def analysis3_venue_prediction_power():
    """会場別 展示タイムの予測力（タイム差0.07秒以上での1着率）"""
    header("分析3: 会場別 展示タイムの予測力")
    db = conn()
    c = db.cursor()

    c.execute(f"""
        {RACE_GAP_CTE}
        SELECT
            ra.venue_code,
            COUNT(*) AS total_races,
            -- 全体での1着率
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END)
                / COUNT(*), 1) AS win_rate_all,
            -- 差0.05秒以上
            SUM(CASE WHEN tb.gap >= 0.05 THEN 1 ELSE 0 END) AS cnt_05,
            ROUND(100.0 * SUM(CASE WHEN tb.gap >= 0.05 AND CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN tb.gap >= 0.05 THEN 1 ELSE 0 END), 0), 1) AS wr_05,
            -- 差0.10秒以上
            SUM(CASE WHEN tb.gap >= 0.10 THEN 1 ELSE 0 END) AS cnt_10,
            ROUND(100.0 * SUM(CASE WHEN tb.gap >= 0.10 AND CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN tb.gap >= 0.10 THEN 1 ELSE 0 END), 0), 1) AS wr_10
        FROM top_boat tb
        JOIN races ra ON tb.race_id = ra.id
        JOIN results res ON tb.race_id = res.race_id AND tb.pit_number = res.pit_number
        WHERE res.is_invalid = 0
          AND res.rank NOT IN ('F','L','K','S','E','')
          AND CAST(res.rank AS INTEGER) > 0
        GROUP BY ra.venue_code
        ORDER BY wr_10 DESC
    """)
    rows = c.fetchall()
    print(f"  {'会場':>6}  {'全件数':>7}  {'全1着率':>7}  {'>=0.05s件':>9}  {'>=0.05s率':>9}  {'>=0.10s件':>9}  {'>=0.10s率':>9}  {'改善幅':>7}")
    for row in rows:
        name = VENUE_NAMES.get(row['venue_code'], f"v{row['venue_code']}")
        improvement = (row['wr_10'] or 0) - row['win_rate_all']
        marker = " **" if improvement >= 10 else (" *" if improvement >= 7 else "")
        print(f"  {name:>6}  {row['total_races']:>7,}  {row['win_rate_all']:>6.1f}%  "
              f"{row['cnt_05']:>9,}  {row['wr_05']:>8.1f}%  "
              f"{row['cnt_10']:>9,}  {row['wr_10']:>8.1f}%  "
              f"{improvement:>+6.1f}pt{marker}")
    db.close()


def analysis4_venue_course_matrix():
    """会場別 × 枠番グループ 最適マトリックス（>=0.07秒）"""
    header("分析4: 会場 × 枠番 タイム差>=0.07秒 展示1位の1着率")
    db = conn()
    c = db.cursor()

    # 枠番グループ別に会場ごとの集計
    for pit_label, pit_cond in [("枠1", "tb.pit_number = 1"),
                                  ("枠2-3", "tb.pit_number IN (2,3)"),
                                  ("枠4-6", "tb.pit_number IN (4,5,6)")]:
        section(f"{pit_label} - タイム差>=0.07秒 会場別1着率（高い順、件数50+）")
        c.execute(f"""
            {RACE_GAP_CTE}
            SELECT
                ra.venue_code,
                COUNT(*) AS total,
                ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END)
                    / COUNT(*), 1) AS wr_all,
                SUM(CASE WHEN tb.gap >= 0.07 THEN 1 ELSE 0 END) AS cnt_gap,
                ROUND(100.0 * SUM(CASE WHEN tb.gap >= 0.07 AND CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END)
                    / NULLIF(SUM(CASE WHEN tb.gap >= 0.07 THEN 1 ELSE 0 END), 0), 1) AS wr_gap
            FROM top_boat tb
            JOIN races ra ON tb.race_id = ra.id
            JOIN results res ON tb.race_id = res.race_id AND tb.pit_number = res.pit_number
            WHERE res.is_invalid = 0
              AND res.rank NOT IN ('F','L','K','S','E','')
              AND CAST(res.rank AS INTEGER) > 0
              AND {pit_cond}
            GROUP BY ra.venue_code
            HAVING cnt_gap >= 50
            ORDER BY wr_gap DESC
        """)
        rows = c.fetchall()
        print(f"  {'会場':>6}  {'全件':>6}  {'全率':>6}  {'>=0.07s件':>9}  {'>=0.07s率':>9}  {'改善':>6}")
        for row in rows:
            name = VENUE_NAMES.get(row['venue_code'], f"v{row['venue_code']}")
            imp = (row['wr_gap'] or 0) - row['wr_all']
            print(f"  {name:>6}  {row['total']:>6,}  {row['wr_all']:>5.1f}%  "
                  f"{row['cnt_gap']:>9,}  {row['wr_gap']:>8.1f}%  {imp:>+5.1f}pt")
    db.close()


def analysis5_rank2_and_below():
    """展示2位以下のタイム差別 1着率（大差をつけられた側の影響）"""
    header("分析5: 展示2位以下のタイム差別 1着率（機力不足艇の着順への影響）")
    db = conn()
    c = db.cursor()

    # 展示2位艇: 1位とのタイム差別に1着率
    section("展示2位艇の（1位との差）別 1着率")
    c.execute(f"""
        {RACE_GAP_CTE}
        -- 展示2位艇を取得
        ,second_boat AS (
            SELECT rgb.race_id, rd3.pit_number, rgb.gap
            FROM race_gap_base rgb
            JOIN race_details rd3 ON rgb.race_id = rd3.race_id
                AND rgb.second_time = rd3.exhibition_time
        )
        SELECT
            CASE
                WHEN sb.gap < 0.03 THEN '差<0.03s(僅差)'
                WHEN sb.gap < 0.05 THEN '差0.03-0.04s'
                WHEN sb.gap < 0.07 THEN '差0.05-0.06s'
                WHEN sb.gap < 0.10 THEN '差0.07-0.09s'
                WHEN sb.gap < 0.15 THEN '差0.10-0.14s'
                ELSE '差0.15s以上'
            END AS gap_range,
            CASE
                WHEN sb.gap < 0.03 THEN 0 WHEN sb.gap < 0.05 THEN 1
                WHEN sb.gap < 0.07 THEN 2 WHEN sb.gap < 0.10 THEN 3
                WHEN sb.gap < 0.15 THEN 4 ELSE 5
            END AS sort_key,
            COUNT(*) AS races,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END)
                / COUNT(*), 1) AS win_rate_1,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END)
                / COUNT(*), 1) AS win_rate_3
        FROM second_boat sb
        JOIN results res ON sb.race_id = res.race_id AND sb.pit_number = res.pit_number
        WHERE res.is_invalid = 0
          AND res.rank NOT IN ('F','L','K','S','E','')
          AND CAST(res.rank AS INTEGER) > 0
        GROUP BY gap_range, sort_key
        ORDER BY sort_key
    """)
    rows = c.fetchall()
    print(f"  {'(1位との差)':>16}  {'件数':>8}  {'1着率':>7}  {'3着率':>7}")
    for row in rows:
        print(f"  {row['gap_range']:>16}  {row['races']:>8,}  {row['win_rate_1']:>6.1f}%  {row['win_rate_3']:>6.1f}%")

    db.close()


def analysis6_large_gap_race_outcome():
    """大差レースの着順分布（機力差が支配的なケース）"""
    header("分析6: タイム差別 レース着順分布（展示1位以外の艇）")
    db = conn()
    c = db.cursor()

    section("タイム差>=0.10秒レースの着順分布（全6艇）")
    c.execute(f"""
        {RACE_GAP_CTE}
        ,large_gap_races AS (
            SELECT race_id FROM race_gap_base WHERE gap >= 0.10
        ),
        exh_rank_all AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                RANK() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) AS exh_rank
            FROM race_details rd
            JOIN large_gap_races lgr ON rd.race_id = lgr.race_id
            WHERE rd.exhibition_time IS NOT NULL
        )
        SELECT
            era.exh_rank,
            COUNT(*) AS total,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS rank1,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 2 THEN 1 ELSE 0 END) / COUNT(*), 1) AS rank2,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 3 THEN 1 ELSE 0 END) / COUNT(*), 1) AS rank3,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) >= 4 THEN 1 ELSE 0 END) / COUNT(*), 1) AS rank456
        FROM exh_rank_all era
        JOIN results res ON era.race_id = res.race_id AND era.pit_number = res.pit_number
        WHERE res.is_invalid = 0
          AND res.rank NOT IN ('F','L','K','S','E','')
          AND CAST(res.rank AS INTEGER) > 0
        GROUP BY era.exh_rank
        ORDER BY era.exh_rank
    """)
    rows = c.fetchall()
    print(f"  {'展示順位':>6}  {'件数':>8}  {'1着%':>6}  {'2着%':>6}  {'3着%':>6}  {'4-6着%':>7}")
    for row in rows:
        print(f"  {row['exh_rank']:>6}位  {row['total']:>8,}  "
              f"{row['rank1']:>5.1f}%  {row['rank2']:>5.1f}%  "
              f"{row['rank3']:>5.1f}%  {row['rank456']:>6.1f}%")

    section("比較: タイム差<0.03秒（僅差）レースの着順分布")
    c.execute(f"""
        {RACE_GAP_CTE}
        ,small_gap_races AS (
            SELECT race_id FROM race_gap_base WHERE gap < 0.03
        ),
        exh_rank_all AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                RANK() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) AS exh_rank
            FROM race_details rd
            JOIN small_gap_races sgr ON rd.race_id = sgr.race_id
            WHERE rd.exhibition_time IS NOT NULL
        )
        SELECT
            era.exh_rank,
            COUNT(*) AS total,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS rank1,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 2 THEN 1 ELSE 0 END) / COUNT(*), 1) AS rank2,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 3 THEN 1 ELSE 0 END) / COUNT(*), 1) AS rank3,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) >= 4 THEN 1 ELSE 0 END) / COUNT(*), 1) AS rank456
        FROM exh_rank_all era
        JOIN results res ON era.race_id = res.race_id AND era.pit_number = res.pit_number
        WHERE res.is_invalid = 0
          AND res.rank NOT IN ('F','L','K','S','E','')
          AND CAST(res.rank AS INTEGER) > 0
        GROUP BY era.exh_rank
        ORDER BY era.exh_rank
    """)
    rows = c.fetchall()
    print(f"  {'展示順位':>6}  {'件数':>8}  {'1着%':>6}  {'2着%':>6}  {'3着%':>6}  {'4-6着%':>7}")
    for row in rows:
        print(f"  {row['exh_rank']:>6}位  {row['total']:>8,}  "
              f"{row['rank1']:>5.1f}%  {row['rank2']:>5.1f}%  "
              f"{row['rank3']:>5.1f}%  {row['rank456']:>6.1f}%")
    db.close()


def analysis7_pit_gap_sweet_spot():
    """枠番 × タイム差 詳細マトリックス（スウィートスポット特定）"""
    header("分析7: 枠番 x タイム差 詳細マトリックス（展示1位の1着率）")
    db = conn()
    c = db.cursor()

    gaps = [0.00, 0.03, 0.05, 0.07, 0.10, 0.15]
    gap_labels = ["全体", ">=0.03", ">=0.05", ">=0.07", ">=0.10", ">=0.15"]

    print(f"\n  {'枠番':>5}  " + "  ".join(f"{l:>8}" for l in gap_labels))
    for pit in range(1, 7):
        print(f"  枠{pit}   ", end="")
        for t in gaps:
            gap_cond = f"AND tb.gap >= {t}" if t > 0 else ""
            c.execute(f"""
                {RACE_GAP_CTE}
                SELECT
                    COUNT(*) AS races,
                    ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END)
                        / COUNT(*), 1) AS win_rate
                FROM top_boat tb
                JOIN results res ON tb.race_id = res.race_id AND tb.pit_number = res.pit_number
                WHERE res.is_invalid = 0
                  AND res.rank NOT IN ('F','L','K','S','E','')
                  AND CAST(res.rank AS INTEGER) > 0
                  AND tb.pit_number = {pit}
                  {gap_cond}
            """)
            row = c.fetchone()
            wr = row['win_rate'] if row and row['win_rate'] else 0.0
            n = row['races'] if row else 0
            print(f"  {wr:>6.1f}%", end="")
        print()

    # 件数も確認
    print(f"\n  件数確認")
    print(f"  {'枠番':>5}  " + "  ".join(f"{l:>8}" for l in gap_labels))
    for pit in range(1, 7):
        print(f"  枠{pit}   ", end="")
        for t in gaps:
            gap_cond = f"AND tb.gap >= {t}" if t > 0 else ""
            c.execute(f"""
                {RACE_GAP_CTE}
                SELECT COUNT(*) AS races
                FROM top_boat tb
                JOIN results res ON tb.race_id = res.race_id AND tb.pit_number = res.pit_number
                WHERE res.is_invalid = 0
                  AND res.rank NOT IN ('F','L','K','S','E','')
                  AND CAST(res.rank AS INTEGER) > 0
                  AND tb.pit_number = {pit}
                  {gap_cond}
            """)
            row = c.fetchone()
            n = row['races'] if row else 0
            print(f"  {n:>7,}", end="")
        print()

    db.close()


def analysis8_top_conditions():
    """有望条件の総まとめ（会場 x 枠番 x タイム差 上位リスト）"""
    header("分析8: 有望条件 総まとめ（会場 x 枠番グループ x タイム差）")
    db = conn()
    c = db.cursor()

    section("タイム差>=0.07秒 かつ 件数>=30件 の条件（1着率高い順）")
    c.execute(f"""
        {RACE_GAP_CTE}
        SELECT
            ra.venue_code,
            CASE
                WHEN tb.pit_number = 1 THEN 'pit1'
                WHEN tb.pit_number IN (2,3) THEN 'pit2-3'
                ELSE 'pit4-6'
            END AS pit_group,
            COUNT(*) AS total_all,
            SUM(CASE WHEN tb.gap >= 0.07 THEN 1 ELSE 0 END) AS cnt_07,
            ROUND(100.0 * SUM(CASE WHEN tb.gap >= 0.07 AND CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN tb.gap >= 0.07 THEN 1 ELSE 0 END), 0), 1) AS wr_07,
            ROUND(100.0 * SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END)
                / COUNT(*), 1) AS wr_all
        FROM top_boat tb
        JOIN races ra ON tb.race_id = ra.id
        JOIN results res ON tb.race_id = res.race_id AND tb.pit_number = res.pit_number
        WHERE res.is_invalid = 0
          AND res.rank NOT IN ('F','L','K','S','E','')
          AND CAST(res.rank AS INTEGER) > 0
        GROUP BY ra.venue_code, pit_group
        HAVING cnt_07 >= 30
        ORDER BY wr_07 DESC
        LIMIT 30
    """)
    rows = c.fetchall()
    print(f"  {'会場':>6}  {'枠グループ':>8}  {'全件':>6}  {'>=0.07s件':>9}  {'>=0.07s率':>9}  {'全体率':>7}  {'改善':>6}")
    for i, row in enumerate(rows):
        name = VENUE_NAMES.get(row['venue_code'], f"v{row['venue_code']}")
        imp = (row['wr_07'] or 0) - row['wr_all']
        print(f"  {name:>6}  {row['pit_group']:>8}  {row['total_all']:>6,}  "
              f"{row['cnt_07']:>9,}  {row['wr_07']:>8.1f}%  {row['wr_all']:>6.1f}%  {imp:>+5.1f}pt")

    db.close()


if __name__ == "__main__":
    import sys
    steps = sys.argv[1:] if len(sys.argv) > 1 else ["1","2","3","4","5","6","7","8"]

    if "1" in steps: analysis1_gap_distribution()
    if "2" in steps: analysis2_threshold_by_course()
    if "3" in steps: analysis3_venue_prediction_power()
    if "4" in steps: analysis4_venue_course_matrix()
    if "5" in steps: analysis5_rank2_and_below()
    if "6" in steps: analysis6_large_gap_race_outcome()
    if "7" in steps: analysis7_pit_gap_sweet_spot()
    if "8" in steps: analysis8_top_conditions()
