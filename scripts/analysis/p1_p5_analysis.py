"""P1-P5 改善ロードマップ検証スクリプト"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'boatrace.db')
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

VENUE_NAMES = {
    '1':'桐生','2':'戸田','3':'江戸川','4':'平和島','5':'多摩川','6':'浜名湖',
    '7':'蒲郡','8':'常滑','9':'津','10':'三国','11':'びわこ','12':'住之江',
    '13':'尼崎','14':'鳴門','15':'丸亀','16':'児島','17':'宮島','18':'徳山',
    '19':'下関','20':'若松','21':'芦屋','22':'福岡','23':'唐津','24':'大村'
}
ADOPTED_VENUES = ['4', '7', '19', '22', '2', '17', '21', '11', '8', '1', '9']

COMMON_CTE = '''
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
rp4 AS (
    SELECT race_id, pit_number
    FROM race_predictions
    WHERE prediction_type = 'before' AND rank_prediction = 4
),
rp5 AS (
    SELECT race_id, pit_number
    FROM race_predictions
    WHERE prediction_type = 'before' AND rank_prediction = 5
),
actual AS (
    SELECT r1.race_id,
           r1.pit_number as rank1,
           r2.pit_number as rank2,
           r3.pit_number as rank3
    FROM results r1
    JOIN results r2 ON r1.race_id = r2.race_id AND r2.rank = '2'
    JOIN results r3 ON r1.race_id = r3.race_id AND r3.rank = '3'
    WHERE r1.rank = '1' AND r1.is_invalid = 0 AND r2.is_invalid = 0 AND r3.is_invalid = 0
)
'''

def run_p1a():
    print("=" * 80)
    print("P1-a: B x 50-100帯、全24会場の年度別ROI (2020-2025)")
    print("=" * 80)

    query = COMMON_CTE + '''
    , base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
            t.odds,
            CASE WHEN a.rank1 = rp1.pit_number AND a.rank2 = rp2.pit_number
                 AND a.rank3 IN (rp3.pit_number, rp4.pit_number, rp5.pit_number)
                 THEN 1 ELSE 0 END as hit_ph
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    )
    SELECT
        venue_code,
        COUNT(*) as total,
        SUM(hit_ph) as hits_ph,
        ROUND(SUM(hit_ph) * 100.0 / COUNT(*), 1) as hit_rate_ph,
        ROUND(SUM(CASE WHEN hit_ph = 1 THEN odds * 100 ELSE 0 END) / (COUNT(*) * 300.0) * 100, 1) as roi_ph,
        CAST(SUM(CASE WHEN hit_ph = 1 THEN odds * 100 ELSE 0 END) - COUNT(*) * 300 AS INTEGER) as profit_ph,
        SUM(CASE WHEN year >= 2023 THEN 1 ELSE 0 END) as total_recent,
        ROUND(CASE WHEN SUM(CASE WHEN year >= 2023 THEN 1 ELSE 0 END) > 0
              THEN SUM(CASE WHEN year >= 2023 AND hit_ph = 1 THEN odds * 100 ELSE 0 END) / (SUM(CASE WHEN year >= 2023 THEN 1 ELSE 0 END) * 300.0) * 100
              ELSE 0 END, 1) as roi_recent,
        CAST(SUM(CASE WHEN year >= 2023 AND hit_ph = 1 THEN odds * 100 ELSE 0 END) - SUM(CASE WHEN year >= 2023 THEN 1 ELSE 0 END) * 300 AS INTEGER) as profit_recent,
        ROUND(CASE WHEN SUM(CASE WHEN year = 2020 THEN 1 ELSE 0 END) > 0 THEN SUM(CASE WHEN year = 2020 AND hit_ph = 1 THEN odds*100 ELSE 0 END)*1.0 / (SUM(CASE WHEN year = 2020 THEN 1 ELSE 0 END)*300.0)*100 ELSE 0 END, 1),
        ROUND(CASE WHEN SUM(CASE WHEN year = 2021 THEN 1 ELSE 0 END) > 0 THEN SUM(CASE WHEN year = 2021 AND hit_ph = 1 THEN odds*100 ELSE 0 END)*1.0 / (SUM(CASE WHEN year = 2021 THEN 1 ELSE 0 END)*300.0)*100 ELSE 0 END, 1),
        ROUND(CASE WHEN SUM(CASE WHEN year = 2022 THEN 1 ELSE 0 END) > 0 THEN SUM(CASE WHEN year = 2022 AND hit_ph = 1 THEN odds*100 ELSE 0 END)*1.0 / (SUM(CASE WHEN year = 2022 THEN 1 ELSE 0 END)*300.0)*100 ELSE 0 END, 1),
        ROUND(CASE WHEN SUM(CASE WHEN year = 2023 THEN 1 ELSE 0 END) > 0 THEN SUM(CASE WHEN year = 2023 AND hit_ph = 1 THEN odds*100 ELSE 0 END)*1.0 / (SUM(CASE WHEN year = 2023 THEN 1 ELSE 0 END)*300.0)*100 ELSE 0 END, 1),
        ROUND(CASE WHEN SUM(CASE WHEN year = 2024 THEN 1 ELSE 0 END) > 0 THEN SUM(CASE WHEN year = 2024 AND hit_ph = 1 THEN odds*100 ELSE 0 END)*1.0 / (SUM(CASE WHEN year = 2024 THEN 1 ELSE 0 END)*300.0)*100 ELSE 0 END, 1),
        ROUND(CASE WHEN SUM(CASE WHEN year = 2025 THEN 1 ELSE 0 END) > 0 THEN SUM(CASE WHEN year = 2025 AND hit_ph = 1 THEN odds*100 ELSE 0 END)*1.0 / (SUM(CASE WHEN year = 2025 THEN 1 ELSE 0 END)*300.0)*100 ELSE 0 END, 1)
    FROM base
    GROUP BY venue_code
    ORDER BY roi_ph DESC
    '''

    rows = cursor.execute(query).fetchall()

    print(f"{'会場':<8} {'採用':<3} | {'6Y件数':>6} {'的中':>4} {'率%':>5} {'ROI%':>7} {'収支':>9} {'黒字':>4} | {'3Y件':>4} {'3YROI':>7} {'3Y収支':>8} {'3Y黒':>4} | {'20':>6} {'21':>6} {'22':>6} {'23':>6} {'24':>6} {'25':>6}")
    print("-" * 140)

    for row in rows:
        vc = str(row[0])
        name = VENUE_NAMES.get(vc, f'?{vc}')
        adopted = 'O' if vc in ADOPTED_VENUES else 'X'
        rois = [row[9], row[10], row[11], row[12], row[13], row[14]]
        black6 = sum(1 for r in rois if r and r > 100)
        black3 = sum(1 for r in rois[3:] if r and r > 100)

        r_strs = [f"{r:6.1f}" if r else "   N/A" for r in rois]
        print(f"{name}({vc:>2})  {adopted:<3} | {row[1]:>6} {row[2]:>4} {row[3]:>5} {row[4]:>7.1f} {row[5]:>+9} {black6:>2}/6 | {row[6]:>4} {row[7]:>7.1f} {row[8]:>+8} {black3:>2}/3 | {r_strs[0]} {r_strs[1]} {r_strs[2]} {r_strs[3]} {r_strs[4]} {r_strs[5]}")

    # 除外会場で直近3年黒字転換したものを特定
    print()
    print("--- 分析: 現在除外の13会場で直近3年黒字転換したもの ---")
    for row in rows:
        vc = str(row[0])
        if vc not in ADOPTED_VENUES:
            name = VENUE_NAMES.get(vc, f'?{vc}')
            rois = [row[9], row[10], row[11], row[12], row[13], row[14]]
            black3 = sum(1 for r in rois[3:] if r and r > 100)
            if black3 >= 2:
                print(f"  {name}({vc}): 直近3年黒字={black3}/3, 直近3年ROI={row[7]:.1f}%, 直近3年収支={row[8]:+}")

    print()
    print("--- 分析: 現在採用の11会場で直近3年赤字のもの ---")
    for row in rows:
        vc = str(row[0])
        if vc in ADOPTED_VENUES:
            name = VENUE_NAMES.get(vc, f'?{vc}')
            rois = [row[9], row[10], row[11], row[12], row[13], row[14]]
            black3 = sum(1 for r in rois[3:] if r and r > 100)
            if row[7] < 100:
                print(f"  {name}({vc}): 直近3年黒字={black3}/3, 直近3年ROI={row[7]:.1f}%, 直近3年収支={row[8]:+}")


def run_p1b():
    print()
    print("=" * 80)
    print("P1-b: GLOBAL_VENUE_MONTH_EXCLUDES追加候補検索")
    print("=" * 80)

    query = COMMON_CTE + '''
    , base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
            CAST(strftime('%m', r.race_date) AS INTEGER) as month,
            t.odds,
            CASE WHEN a.rank1 = rp1.pit_number AND a.rank2 = rp2.pit_number
                 AND a.rank3 IN (rp3.pit_number, rp4.pit_number, rp5.pit_number)
                 THEN 1 ELSE 0 END as hit_ph
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    )
    SELECT
        venue_code,
        month,
        COUNT(*) as total,
        SUM(hit_ph) as hits,
        ROUND(SUM(CASE WHEN hit_ph = 1 THEN odds * 100 ELSE 0 END) / (COUNT(*) * 300.0) * 100, 1) as roi,
        CAST(SUM(CASE WHEN hit_ph = 1 THEN odds * 100 ELSE 0 END) - COUNT(*) * 300 AS INTEGER) as profit,
        CAST(SUM(CASE WHEN year=2020 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2020 THEN 300 ELSE 0 END) AS INTEGER) as p2020,
        CAST(SUM(CASE WHEN year=2021 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2021 THEN 300 ELSE 0 END) AS INTEGER) as p2021,
        CAST(SUM(CASE WHEN year=2022 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2022 THEN 300 ELSE 0 END) AS INTEGER) as p2022,
        CAST(SUM(CASE WHEN year=2023 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2023 THEN 300 ELSE 0 END) AS INTEGER) as p2023,
        CAST(SUM(CASE WHEN year=2024 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2024 THEN 300 ELSE 0 END) AS INTEGER) as p2024,
        CAST(SUM(CASE WHEN year=2025 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2025 THEN 300 ELSE 0 END) AS INTEGER) as p2025
    FROM base
    GROUP BY venue_code, month
    HAVING COUNT(*) >= 10
    ORDER BY roi ASC
    '''

    rows = cursor.execute(query).fetchall()
    existing_excludes = [('5',2),('22',2),('14',1),('14',2),('17',2)]

    print("--- ROI < 60% & 件数>=10 の会場x月 ---")
    print(f"{'会場':<10} {'月':>2} {'件数':>5} {'的中':>4} {'ROI%':>7} {'収支':>9} {'黒字':>4} {'既除外':>6} | {'2020':>8} {'2021':>8} {'2022':>8} {'2023':>8} {'2024':>8} {'2025':>8}")
    print("-" * 120)

    candidates = []
    for row in rows:
        vc = str(row[0])
        mo = row[1]
        total, hits, roi, profit = row[2], row[3], row[4], row[5]
        yearly_profits = [row[6], row[7], row[8], row[9], row[10], row[11]]
        black_years = sum(1 for p in yearly_profits if p and p > 0)

        if roi < 60:
            name = VENUE_NAMES.get(vc, f'?{vc}')
            existing = 'EXIST' if (vc, mo) in existing_excludes else ''
            print(f"{name}({vc:>2}) {mo:>3}月 {total:>5} {hits:>4} {roi:>7.1f} {profit:>+9} {black_years:>2}/6 {existing:>6} | {row[6]:>+8} {row[7]:>+8} {row[8]:>+8} {row[9]:>+8} {row[10]:>+8} {row[11]:>+8}")
            if black_years <= 1 and (vc, mo) not in existing_excludes:
                candidates.append((vc, mo, name, total, roi, profit, black_years))

    print()
    print("--- 追加候補: ROI<60%, 件数>=10, 黒字<=1/6 (既存除外以外) ---")
    for c in candidates:
        print(f"  ({c[0]}, {c[1]}),  # {c[2]}x{c[1]}月 (ROI {c[4]:.1f}%, {c[6]}/6年黒字, {c[5]:+}円)")

    # ワイドに ROI < 80% も
    print()
    print("--- 参考: ROI<80% & 件数>=10 & 黒字<=1/6 の全リスト ---")
    for row in rows:
        vc = str(row[0])
        mo = row[1]
        roi = row[4]
        profit = row[5]
        yearly_profits = [row[6], row[7], row[8], row[9], row[10], row[11]]
        black_years = sum(1 for p in yearly_profits if p and p > 0)
        if roi < 80 and black_years <= 1:
            name = VENUE_NAMES.get(vc, f'?{vc}')
            existing = 'EXIST' if (vc, mo) in existing_excludes else ''
            print(f"  {name}({vc:>2}) {mo:>2}月 件数={row[2]:>3} ROI={roi:>5.1f}% 収支={profit:>+8} 黒字={black_years}/6 {existing}")


def run_p2():
    print()
    print("=" * 80)
    print("P2: 2-1-X逆転パターンの検証")
    print("=" * 80)

    # まず通常パターンHの内訳
    query = COMMON_CTE + '''
    , base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
            rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
            rp4.pit_number as p4, rp5.pit_number as p5,
            a.rank1, a.rank2, a.rank3,
            rp1.confidence
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    )
    SELECT
        COUNT(*) as total_races,
        -- 通常パターンH的中
        SUM(CASE WHEN rank1=p1 AND rank2=p2 AND rank3 IN (p3,p4,p5) THEN 1 ELSE 0 END) as hit_ph,
        SUM(CASE WHEN rank1=p1 AND rank2=p2 AND rank3=p3 THEN 1 ELSE 0 END) as hit_123,
        SUM(CASE WHEN rank1=p1 AND rank2=p2 AND rank3=p4 THEN 1 ELSE 0 END) as hit_124,
        SUM(CASE WHEN rank1=p1 AND rank2=p2 AND rank3=p5 THEN 1 ELSE 0 END) as hit_125,
        -- 逆転パターン: rank1=p2, rank2=p1
        SUM(CASE WHEN rank1=p2 AND rank2=p1 THEN 1 ELSE 0 END) as reverse_12,
        SUM(CASE WHEN rank1=p2 AND rank2=p1 AND rank3 IN (p3,p4,p5) THEN 1 ELSE 0 END) as reverse_hit,
        SUM(CASE WHEN rank1=p2 AND rank2=p1 AND rank3=p3 THEN 1 ELSE 0 END) as reverse_hit_3,
        SUM(CASE WHEN rank1=p2 AND rank2=p1 AND rank3=p4 THEN 1 ELSE 0 END) as reverse_hit_4,
        SUM(CASE WHEN rank1=p2 AND rank2=p1 AND rank3=p5 THEN 1 ELSE 0 END) as reverse_hit_5
    FROM base
    '''

    row = cursor.execute(query).fetchone()
    total = row[0]
    hit_ph = row[1]
    hit_123, hit_124, hit_125 = row[2], row[3], row[4]
    reverse_12 = row[5]
    reverse_hit = row[6]
    reverse_hit_3, reverse_hit_4, reverse_hit_5 = row[7], row[8], row[9]

    print(f"\n全B x 50-100帯レース数: {total}")
    print(f"\n--- 1. 現行パターンH的中の内訳 ---")
    print(f"  PH的中合計:       {hit_ph}件 ({hit_ph/total*100:.2f}%)")
    print(f"    p1-p2-p3 正解:  {hit_123}件 ({hit_123/total*100:.2f}%)  ({hit_123/max(hit_ph,1)*100:.1f}%)")
    print(f"    p1-p2-p4 正解:  {hit_124}件 ({hit_124/total*100:.2f}%)  ({hit_124/max(hit_ph,1)*100:.1f}%)")
    print(f"    p1-p2-p5 正解:  {hit_125}件 ({hit_125/total*100:.2f}%)  ({hit_125/max(hit_ph,1)*100:.1f}%)")

    print(f"\n--- 2. 逆転パターン (2-1-X) ---")
    print(f"  rank1=p2, rank2=p1:             {reverse_12}件 ({reverse_12/total*100:.2f}%)")
    print(f"  うちrank3がp3/p4/p5のいずれか:  {reverse_hit}件 ({reverse_hit/total*100:.2f}%)")
    print(f"    p2-p1-p3: {reverse_hit_3}件")
    print(f"    p2-p1-p4: {reverse_hit_4}件")
    print(f"    p2-p1-p5: {reverse_hit_5}件")

    # 逆転パターンの平均払戻
    print(f"\n--- 逆転パターンの払戻額 ---")

    # 通常パターンHの平均払戻
    q_normal = COMMON_CTE + '''
    , base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
            rp4.pit_number as p4, rp5.pit_number as p5,
            a.rank1, a.rank2, a.rank3,
            rp1.confidence
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    hit_races AS (
        SELECT race_id, p1, p2, p3, p4, p5, rank1, rank2, rank3
        FROM base
        WHERE rank1 = p1 AND rank2 = p2 AND rank3 IN (p3, p4, p5)
    )
    SELECT
        COUNT(*) as cnt,
        ROUND(AVG(t.odds), 1) as avg_odds,
        ROUND(AVG(t.odds * 100), 0) as avg_payout
    FROM hit_races h
    JOIN trifecta_odds t ON h.race_id = t.race_id
        AND t.combination = CAST(h.rank1 AS TEXT) || '-' || CAST(h.rank2 AS TEXT) || '-' || CAST(h.rank3 AS TEXT)
    '''
    normal_row = cursor.execute(q_normal).fetchone()
    print(f"  通常PH的中時: {normal_row[0]}件, 平均オッズ={normal_row[1]}, 平均払戻={normal_row[2]:.0f}円")

    # 逆転パターンの払戻
    q_reverse = COMMON_CTE + '''
    , base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
            rp4.pit_number as p4, rp5.pit_number as p5,
            a.rank1, a.rank2, a.rank3,
            rp1.confidence
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    reverse_races AS (
        SELECT race_id, p1, p2, p3, p4, p5, rank1, rank2, rank3
        FROM base
        WHERE rank1 = p2 AND rank2 = p1 AND rank3 IN (p3, p4, p5)
    )
    SELECT
        COUNT(*) as cnt,
        ROUND(AVG(t.odds), 1) as avg_odds,
        ROUND(AVG(t.odds * 100), 0) as avg_payout,
        ROUND(MIN(t.odds), 1) as min_odds,
        ROUND(MAX(t.odds), 1) as max_odds
    FROM reverse_races h
    JOIN trifecta_odds t ON h.race_id = t.race_id
        AND t.combination = CAST(h.rank1 AS TEXT) || '-' || CAST(h.rank2 AS TEXT) || '-' || CAST(h.rank3 AS TEXT)
    '''
    rev_row = cursor.execute(q_reverse).fetchone()
    print(f"  逆転PH的中時: {rev_row[0]}件, 平均オッズ={rev_row[1]}, 平均払戻={rev_row[2]:.0f}円, min={rev_row[3]}, max={rev_row[4]}")

    # ROI比較試算
    print(f"\n--- 3. ROI比較試算 ---")

    # 通常PH: 3点買い x 100円 = 300円投資
    normal_payout_total_q = COMMON_CTE + '''
    , base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
            rp4.pit_number as p4, rp5.pit_number as p5,
            a.rank1, a.rank2, a.rank3
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    )
    SELECT
        COUNT(*) as total,
        -- 通常PH的中 -> 払戻合計
        CAST(SUM(CASE WHEN rank1=p1 AND rank2=p2 AND rank3 IN (p3,p4,p5) THEN 1 ELSE 0 END) AS INTEGER) as normal_hits,
        -- 通常の総払戻
        CAST(COALESCE((
            SELECT SUM(t2.odds * 100)
            FROM base b2
            JOIN trifecta_odds t2 ON b2.race_id = t2.race_id
                AND t2.combination = CAST(b2.rank1 AS TEXT) || '-' || CAST(b2.rank2 AS TEXT) || '-' || CAST(b2.rank3 AS TEXT)
            WHERE b2.rank1=b2.p1 AND b2.rank2=b2.p2 AND b2.rank3 IN (b2.p3,b2.p4,b2.p5)
        ), 0) AS INTEGER) as normal_payout,
        -- 逆転的中件数
        CAST(SUM(CASE WHEN rank1=p2 AND rank2=p1 AND rank3 IN (p3,p4,p5) THEN 1 ELSE 0 END) AS INTEGER) as reverse_hits
    FROM base
    '''

    summary = cursor.execute(normal_payout_total_q).fetchone()
    total_races = summary[0]
    normal_hits = summary[1]
    normal_payout = summary[2]
    reverse_hits_count = summary[3]

    # 逆転パターンの払戻合計
    q_rev_total = COMMON_CTE + '''
    , base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
            rp4.pit_number as p4, rp5.pit_number as p5,
            a.rank1, a.rank2, a.rank3
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    reverse_races AS (
        SELECT race_id, p1, p2, p3, p4, p5, rank1, rank2, rank3
        FROM base
        WHERE rank1 = p2 AND rank2 = p1 AND rank3 IN (p3, p4, p5)
    )
    SELECT COALESCE(SUM(t.odds * 100), 0) as total_payout
    FROM reverse_races h
    JOIN trifecta_odds t ON h.race_id = t.race_id
        AND t.combination = CAST(h.rank1 AS TEXT) || '-' || CAST(h.rank2 AS TEXT) || '-' || CAST(h.rank3 AS TEXT)
    '''
    reverse_payout = cursor.execute(q_rev_total).fetchone()[0]

    # 試算
    # 現行: 3点 x 100円 = 300円/レース
    cost_current = total_races * 300
    roi_current = normal_payout / cost_current * 100
    profit_current = normal_payout - cost_current

    # 拡張A: 6点 x 100円 = 600円/レース
    cost_a = total_races * 600
    payout_a = normal_payout + reverse_payout
    roi_a = payout_a / cost_a * 100
    profit_a = payout_a - cost_a

    # 拡張B: 3点(通常)+1点(逆転最有力)=400円/レース -> ここでは全3点逆転を1点ずつ追加 = 6点で近似
    # 正確には p2-p1-p3 の1点だけ追加 = 4点
    # p2-p1-p3の払戻を別途計算
    q_rev_p3_only = COMMON_CTE + '''
    , base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
            rp4.pit_number as p4, rp5.pit_number as p5,
            a.rank1, a.rank2, a.rank3
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    rev_p3 AS (
        SELECT race_id, p1, p2, p3, rank1, rank2, rank3
        FROM base
        WHERE rank1 = p2 AND rank2 = p1 AND rank3 = p3
    )
    SELECT
        COUNT(*) as cnt,
        COALESCE(SUM(t.odds * 100), 0) as total_payout
    FROM rev_p3 h
    JOIN trifecta_odds t ON h.race_id = t.race_id
        AND t.combination = CAST(h.rank1 AS TEXT) || '-' || CAST(h.rank2 AS TEXT) || '-' || CAST(h.rank3 AS TEXT)
    '''
    rev_p3_row = cursor.execute(q_rev_p3_only).fetchone()
    rev_p3_payout = rev_p3_row[1]

    cost_b = total_races * 400  # 4点
    payout_b = normal_payout + rev_p3_payout
    roi_b = payout_b / cost_b * 100
    profit_b = payout_b - cost_b

    print(f"\n  レース数: {total_races}")
    print(f"  通常PH払戻合計: {normal_payout:,}円 (的中{normal_hits}件)")
    print(f"  逆転PH払戻合計: {reverse_payout:,.0f}円 (的中{reverse_hits_count}件)")
    print(f"  逆転p2-p1-p3のみ払戻: {rev_p3_payout:,.0f}円 (的中{rev_p3_row[0]}件)")
    print()
    print(f"  【現行】 p1-p2-X 3点 @300円: 投資{cost_current:,}円 払戻{normal_payout:,}円 ROI={roi_current:.1f}% 収支={profit_current:+,}円")
    print(f"  【案A】  p1-p2-X+p2-p1-X 6点 @600円: 投資{cost_a:,}円 払戻{payout_a:,.0f}円 ROI={roi_a:.1f}% 収支={profit_a:+,.0f}円")
    print(f"  【案B】  p1-p2-X+p2-p1-p3 4点 @400円: 投資{cost_b:,}円 払戻{payout_b:,.0f}円 ROI={roi_b:.1f}% 収支={profit_b:+,.0f}円")


def run_p3():
    print()
    print("=" * 80)
    print("P3: オッズ帯細分化 (50-65 vs 65-100)")
    print("=" * 80)

    # B x 50-100帯（月除外[12,1,2,4]、11会場フィルター）
    venues = "('4','7','19','22','2','17','21','11','8','1','9')"

    query = COMMON_CTE + f'''
    , base AS (
        SELECT
            r.id as race_id,
            CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
            t.odds,
            CASE WHEN a.rank1 = rp1.pit_number AND a.rank2 = rp2.pit_number
                 AND a.rank3 IN (rp3.pit_number, rp4.pit_number, rp5.pit_number)
                 THEN 1 ELSE 0 END as hit_ph
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND r.venue_code IN {venues}
          AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN (12, 1, 2, 4)
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    )
    SELECT
        CASE
            WHEN odds BETWEEN 50 AND 54.99 THEN '50-55'
            WHEN odds BETWEEN 55 AND 59.99 THEN '55-60'
            WHEN odds BETWEEN 60 AND 64.99 THEN '60-65'
            WHEN odds BETWEEN 65 AND 69.99 THEN '65-70'
            WHEN odds BETWEEN 70 AND 74.99 THEN '70-75'
            WHEN odds BETWEEN 75 AND 79.99 THEN '75-80'
            WHEN odds BETWEEN 80 AND 84.99 THEN '80-85'
            WHEN odds BETWEEN 85 AND 89.99 THEN '85-90'
            WHEN odds BETWEEN 90 AND 94.99 THEN '90-95'
            WHEN odds BETWEEN 95 AND 100 THEN '95-100'
        END as odds_band,
        COUNT(*) as total,
        SUM(hit_ph) as hits,
        ROUND(SUM(hit_ph)*100.0/COUNT(*), 2) as hit_rate,
        ROUND(SUM(CASE WHEN hit_ph=1 THEN odds*100 ELSE 0 END)/(COUNT(*)*300.0)*100, 1) as roi,
        CAST(SUM(CASE WHEN hit_ph=1 THEN odds*100 ELSE 0 END) - COUNT(*)*300 AS INTEGER) as profit,
        -- 年度別黒字
        SUM(CASE WHEN year=2020 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2020 THEN 300 ELSE 0 END) as p2020,
        SUM(CASE WHEN year=2021 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2021 THEN 300 ELSE 0 END) as p2021,
        SUM(CASE WHEN year=2022 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2022 THEN 300 ELSE 0 END) as p2022,
        SUM(CASE WHEN year=2023 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2023 THEN 300 ELSE 0 END) as p2023,
        SUM(CASE WHEN year=2024 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2024 THEN 300 ELSE 0 END) as p2024,
        SUM(CASE WHEN year=2025 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2025 THEN 300 ELSE 0 END) as p2025
    FROM base
    GROUP BY odds_band
    ORDER BY odds_band
    '''

    rows = cursor.execute(query).fetchall()

    print(f"\n{'オッズ帯':<8} {'件数':>5} {'的中':>4} {'率%':>6} {'ROI%':>7} {'収支':>9} {'黒字':>4} | {'2020':>8} {'2021':>8} {'2022':>8} {'2023':>8} {'2024':>8} {'2025':>8}")
    print("-" * 110)

    for row in rows:
        if row[0]:
            yearly = [row[6], row[7], row[8], row[9], row[10], row[11]]
            black = sum(1 for p in yearly if p and p > 0)
            print(f"{row[0]:<8} {row[1]:>5} {row[2]:>4} {row[3]:>6.2f} {row[4]:>7.1f} {row[5]:>+9} {black:>2}/6 | {row[6]:>+8} {row[7]:>+8} {row[8]:>+8} {row[9]:>+8} {row[10]:>+8} {row[11]:>+8}")

    # 2分割の集計
    print("\n--- 50-65 vs 65-100 ---")
    q2 = COMMON_CTE + f'''
    , base AS (
        SELECT
            r.id as race_id,
            CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
            t.odds,
            CASE WHEN a.rank1 = rp1.pit_number AND a.rank2 = rp2.pit_number
                 AND a.rank3 IN (rp3.pit_number, rp4.pit_number, rp5.pit_number)
                 THEN 1 ELSE 0 END as hit_ph
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND r.venue_code IN {venues}
          AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN (12, 1, 2, 4)
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    )
    SELECT
        CASE WHEN odds < 65 THEN '50-65' ELSE '65-100' END as band,
        COUNT(*) as total,
        SUM(hit_ph) as hits,
        ROUND(SUM(hit_ph)*100.0/COUNT(*), 2) as hit_rate,
        ROUND(SUM(CASE WHEN hit_ph=1 THEN odds*100 ELSE 0 END)/(COUNT(*)*300.0)*100, 1) as roi,
        CAST(SUM(CASE WHEN hit_ph=1 THEN odds*100 ELSE 0 END) - COUNT(*)*300 AS INTEGER) as profit,
        SUM(CASE WHEN year=2020 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2020 THEN 300 ELSE 0 END),
        SUM(CASE WHEN year=2021 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2021 THEN 300 ELSE 0 END),
        SUM(CASE WHEN year=2022 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2022 THEN 300 ELSE 0 END),
        SUM(CASE WHEN year=2023 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2023 THEN 300 ELSE 0 END),
        SUM(CASE WHEN year=2024 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2024 THEN 300 ELSE 0 END),
        SUM(CASE WHEN year=2025 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2025 THEN 300 ELSE 0 END)
    FROM base
    GROUP BY band
    ORDER BY band
    '''

    rows2 = cursor.execute(q2).fetchall()
    for row in rows2:
        yearly = [row[6], row[7], row[8], row[9], row[10], row[11]]
        black = sum(1 for p in yearly if p and p > 0)
        print(f"  {row[0]:<8} {row[1]:>5}件 的中{row[2]:>3} 率{row[3]:>5.2f}% ROI={row[4]:>6.1f}% 収支={row[5]:>+8} 黒字={black}/6")
        print(f"           20:{row[6]:>+8} 21:{row[7]:>+8} 22:{row[8]:>+8} 23:{row[9]:>+8} 24:{row[10]:>+8} 25:{row[11]:>+8}")


def run_p4():
    print()
    print("=" * 80)
    print("P4: avg_stのExtendedScorer活用状況確認")
    print("=" * 80)

    venues = "('4','7','19','22','2','17','21','11','8','1','9')"

    # avg_stはentriesテーブルから取得
    query = COMMON_CTE + f'''
    , base AS (
        SELECT
            r.id as race_id,
            CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
            t.odds,
            e.avg_st,
            CASE WHEN a.rank1 = rp1.pit_number AND a.rank2 = rp2.pit_number
                 AND a.rank3 IN (rp3.pit_number, rp4.pit_number, rp5.pit_number)
                 THEN 1 ELSE 0 END as hit_ph
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN entries e ON r.id = e.race_id AND e.pit_number = rp1.pit_number
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND r.venue_code IN {venues}
          AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN (12, 1, 2, 4)
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    )
    SELECT
        CASE
            WHEN avg_st IS NULL THEN 'NULL'
            WHEN avg_st < 0.15 THEN '<0.15'
            WHEN avg_st < 0.17 THEN '0.15-0.17'
            WHEN avg_st < 0.19 THEN '0.17-0.19'
            ELSE '0.19+'
        END as st_band,
        COUNT(*) as total,
        SUM(hit_ph) as hits,
        ROUND(SUM(hit_ph)*100.0/COUNT(*), 2) as hit_rate,
        ROUND(SUM(CASE WHEN hit_ph=1 THEN odds*100 ELSE 0 END)/(COUNT(*)*300.0)*100, 1) as roi,
        CAST(SUM(CASE WHEN hit_ph=1 THEN odds*100 ELSE 0 END) - COUNT(*)*300 AS INTEGER) as profit,
        SUM(CASE WHEN year=2020 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2020 THEN 300 ELSE 0 END),
        SUM(CASE WHEN year=2021 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2021 THEN 300 ELSE 0 END),
        SUM(CASE WHEN year=2022 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2022 THEN 300 ELSE 0 END),
        SUM(CASE WHEN year=2023 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2023 THEN 300 ELSE 0 END),
        SUM(CASE WHEN year=2024 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2024 THEN 300 ELSE 0 END),
        SUM(CASE WHEN year=2025 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2025 THEN 300 ELSE 0 END)
    FROM base
    GROUP BY st_band
    ORDER BY st_band
    '''

    rows = cursor.execute(query).fetchall()

    print(f"\n現在のスコアリングカーブ (extended_scorer.py):")
    print(f"  ST 0.00-0.10: 0.7倍 (Fリスク)")
    print(f"  ST 0.10-0.15: 1.0倍 (最適)")
    print(f"  ST 0.15-0.18: 0.8倍 (良好)")
    print(f"  ST 0.18-0.20: 0.6倍 (やや遅い)")
    print(f"  ST 0.20+:     0.4倍 (遅い)")
    print()

    print(f"{'ST帯':<12} {'件数':>5} {'的中':>4} {'率%':>6} {'ROI%':>7} {'収支':>9} {'黒字':>4} | {'2020':>8} {'2021':>8} {'2022':>8} {'2023':>8} {'2024':>8} {'2025':>8}")
    print("-" * 110)

    for row in rows:
        yearly = [row[6], row[7], row[8], row[9], row[10], row[11]]
        black = sum(1 for p in yearly if p and p > 0)
        print(f"{row[0]:<12} {row[1]:>5} {row[2]:>4} {row[3]:>6.2f} {row[4]:>7.1f} {row[5]:>+9} {black:>2}/6 | {row[6]:>+8} {row[7]:>+8} {row[8]:>+8} {row[9]:>+8} {row[10]:>+8} {row[11]:>+8}")

    # さらに細かく
    print("\n--- 細分化版 ---")
    query2 = COMMON_CTE + f'''
    , base AS (
        SELECT
            r.id as race_id,
            t.odds, e.avg_st,
            CASE WHEN a.rank1 = rp1.pit_number AND a.rank2 = rp2.pit_number
                 AND a.rank3 IN (rp3.pit_number, rp4.pit_number, rp5.pit_number)
                 THEN 1 ELSE 0 END as hit_ph
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN entries e ON r.id = e.race_id AND e.pit_number = rp1.pit_number
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND r.venue_code IN {venues}
          AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN (12, 1, 2, 4)
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND e.avg_st IS NOT NULL
    )
    SELECT
        CASE
            WHEN avg_st < 0.12 THEN '<0.12'
            WHEN avg_st < 0.14 THEN '0.12-0.14'
            WHEN avg_st < 0.15 THEN '0.14-0.15'
            WHEN avg_st < 0.16 THEN '0.15-0.16'
            WHEN avg_st < 0.17 THEN '0.16-0.17'
            WHEN avg_st < 0.18 THEN '0.17-0.18'
            WHEN avg_st < 0.19 THEN '0.18-0.19'
            WHEN avg_st < 0.20 THEN '0.19-0.20'
            ELSE '0.20+'
        END as st_band,
        COUNT(*) as total,
        SUM(hit_ph) as hits,
        ROUND(SUM(hit_ph)*100.0/COUNT(*), 2) as hit_rate,
        ROUND(SUM(CASE WHEN hit_ph=1 THEN odds*100 ELSE 0 END)/(COUNT(*)*300.0)*100, 1) as roi,
        CAST(SUM(CASE WHEN hit_ph=1 THEN odds*100 ELSE 0 END) - COUNT(*)*300 AS INTEGER) as profit
    FROM base
    GROUP BY st_band
    ORDER BY st_band
    '''
    rows2 = cursor.execute(query2).fetchall()
    for row in rows2:
        print(f"  {row[0]:<12} {row[1]:>5}件 的中{row[2]:>3} 率{row[3]:>5.2f}% ROI={row[4]:>7.1f}% 収支={row[5]:>+9}")


def run_p5():
    print()
    print("=" * 80)
    print("P5: B x 100-200倍帯への会場フィルター適用")
    print("=" * 80)

    query = COMMON_CTE + '''
    , base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
            t.odds,
            CASE WHEN a.rank1 = rp1.pit_number AND a.rank2 = rp2.pit_number
                 AND a.rank3 IN (rp3.pit_number, rp4.pit_number, rp5.pit_number)
                 THEN 1 ELSE 0 END as hit_ph
        FROM races r
        JOIN rp1 ON r.id = rp1.race_id
        JOIN rp2 ON r.id = rp2.race_id
        JOIN rp3 ON r.id = rp3.race_id
        JOIN rp4 ON r.id = rp4.race_id
        JOIN rp5 ON r.id = rp5.race_id
        JOIN actual a ON r.id = a.race_id
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.confidence = 'B'
          AND t.odds BETWEEN 100 AND 200
          AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN (12, 1, 2, 4)
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    )
    SELECT
        venue_code,
        COUNT(*) as total,
        SUM(hit_ph) as hits,
        ROUND(SUM(hit_ph)*100.0/COUNT(*), 2) as hit_rate,
        ROUND(SUM(CASE WHEN hit_ph=1 THEN odds*100 ELSE 0 END)/(COUNT(*)*300.0)*100, 1) as roi,
        CAST(SUM(CASE WHEN hit_ph=1 THEN odds*100 ELSE 0 END) - COUNT(*)*300 AS INTEGER) as profit,
        -- 直近3年
        SUM(CASE WHEN year >= 2023 THEN 1 ELSE 0 END) as total_recent,
        ROUND(CASE WHEN SUM(CASE WHEN year >= 2023 THEN 1 ELSE 0 END) > 0
              THEN SUM(CASE WHEN year >= 2023 AND hit_ph = 1 THEN odds * 100 ELSE 0 END) / (SUM(CASE WHEN year >= 2023 THEN 1 ELSE 0 END) * 300.0) * 100
              ELSE 0 END, 1) as roi_recent,
        CAST(SUM(CASE WHEN year >= 2023 AND hit_ph = 1 THEN odds * 100 ELSE 0 END) - SUM(CASE WHEN year >= 2023 THEN 1 ELSE 0 END) * 300 AS INTEGER) as profit_recent,
        -- 年度別
        CAST(SUM(CASE WHEN year=2020 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2020 THEN 300 ELSE 0 END) AS INTEGER),
        CAST(SUM(CASE WHEN year=2021 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2021 THEN 300 ELSE 0 END) AS INTEGER),
        CAST(SUM(CASE WHEN year=2022 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2022 THEN 300 ELSE 0 END) AS INTEGER),
        CAST(SUM(CASE WHEN year=2023 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2023 THEN 300 ELSE 0 END) AS INTEGER),
        CAST(SUM(CASE WHEN year=2024 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2024 THEN 300 ELSE 0 END) AS INTEGER),
        CAST(SUM(CASE WHEN year=2025 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2025 THEN 300 ELSE 0 END) AS INTEGER)
    FROM base
    GROUP BY venue_code
    ORDER BY roi DESC
    '''

    rows = cursor.execute(query).fetchall()

    print(f"\n全24会場 (B x 100-200倍帯、月除外[12,1,2,4])")
    print(f"{'会場':<8} {'件数':>5} {'的中':>4} {'率%':>6} {'ROI%':>7} {'収支':>9} {'黒字':>4} | {'3Y件':>4} {'3YROI':>7} {'3Y収支':>8} | {'2020':>8} {'2021':>8} {'2022':>8} {'2023':>8} {'2024':>8} {'2025':>8}")
    print("-" * 140)

    candidates = []
    for row in rows:
        vc = str(row[0])
        name = VENUE_NAMES.get(vc, f'?{vc}')
        yearly = [row[9], row[10], row[11], row[12], row[13], row[14]]
        black6 = sum(1 for p in yearly if p and p > 0)
        black3 = sum(1 for p in yearly[3:] if p and p > 0)

        marker = ''
        if row[4] >= 150 and row[1] >= 10:
            marker = ' ***'
            candidates.append((vc, name, row[1], row[4], row[5], black6, row[6], row[7], row[8]))

        print(f"{name}({vc:>2}) {row[1]:>5} {row[2]:>4} {row[3]:>6.2f} {row[4]:>7.1f} {row[5]:>+9} {black6:>2}/6 | {row[6]:>4} {row[7]:>7.1f} {row[8]:>+8} | {row[9]:>+8} {row[10]:>+8} {row[11]:>+8} {row[12]:>+8} {row[13]:>+8} {row[14]:>+8}{marker}")

    print()
    print(f"--- ROI>=150% & 件数>=10 の会場 ---")
    for c in candidates:
        print(f"  {c[1]}({c[0]}): {c[2]}件, ROI={c[3]:.1f}%, 収支={c[4]:+}, 黒字={c[5]}/6, 直近3Y: {c[6]}件 ROI={c[7]:.1f}% 収支={c[8]:+}")

    if candidates:
        venue_list = ",".join([f"'{c[0]}'" for c in candidates])
        # 候補会場で絞り込んだ場合の集計
        q_filtered = COMMON_CTE + f'''
        , base AS (
            SELECT
                r.id as race_id,
                CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
                t.odds,
                CASE WHEN a.rank1 = rp1.pit_number AND a.rank2 = rp2.pit_number
                     AND a.rank3 IN (rp3.pit_number, rp4.pit_number, rp5.pit_number)
                     THEN 1 ELSE 0 END as hit_ph
            FROM races r
            JOIN rp1 ON r.id = rp1.race_id
            JOIN rp2 ON r.id = rp2.race_id
            JOIN rp3 ON r.id = rp3.race_id
            JOIN rp4 ON r.id = rp4.race_id
            JOIN rp5 ON r.id = rp5.race_id
            JOIN actual a ON r.id = a.race_id
            JOIN trifecta_odds t ON r.id = t.race_id
                AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
            WHERE rp1.confidence = 'B'
              AND t.odds BETWEEN 100 AND 200
              AND r.venue_code IN ({venue_list})
              AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN (12, 1, 2, 4)
              AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        )
        SELECT
            COUNT(*) as total,
            SUM(hit_ph) as hits,
            ROUND(SUM(hit_ph)*100.0/COUNT(*), 2) as hit_rate,
            ROUND(SUM(CASE WHEN hit_ph=1 THEN odds*100 ELSE 0 END)/(COUNT(*)*300.0)*100, 1) as roi,
            CAST(SUM(CASE WHEN hit_ph=1 THEN odds*100 ELSE 0 END) - COUNT(*)*300 AS INTEGER) as profit,
            CAST(SUM(CASE WHEN year=2020 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2020 THEN 300 ELSE 0 END) AS INTEGER),
            CAST(SUM(CASE WHEN year=2021 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2021 THEN 300 ELSE 0 END) AS INTEGER),
            CAST(SUM(CASE WHEN year=2022 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2022 THEN 300 ELSE 0 END) AS INTEGER),
            CAST(SUM(CASE WHEN year=2023 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2023 THEN 300 ELSE 0 END) AS INTEGER),
            CAST(SUM(CASE WHEN year=2024 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2024 THEN 300 ELSE 0 END) AS INTEGER),
            CAST(SUM(CASE WHEN year=2025 AND hit_ph=1 THEN odds*100 ELSE 0 END) - SUM(CASE WHEN year=2025 THEN 300 ELSE 0 END) AS INTEGER)
        FROM base
        '''

        frow = cursor.execute(q_filtered).fetchone()
        yearly = [frow[5], frow[6], frow[7], frow[8], frow[9], frow[10]]
        black6 = sum(1 for p in yearly if p and p > 0)
        # Tier 1: 2024-2025のどちらかが黒字
        tier1_ok = (frow[9] > 0 or frow[10] > 0) if frow[9] is not None and frow[10] is not None else False

        print(f"\n--- 候補会場で絞り込んだ場合 ---")
        vn = "+".join([c[1] for c in candidates])
        print(f"  会場: {vn}")
        print(f"  件数={frow[0]}, 的中={frow[1]}, 率={frow[2]:.2f}%, ROI={frow[3]:.1f}%, 収支={frow[4]:+}")
        print(f"  黒字年数={black6}/6: 20:{frow[5]:+} 21:{frow[6]:+} 22:{frow[7]:+} 23:{frow[8]:+} 24:{frow[9]:+} 25:{frow[10]:+}")
        print(f"  Tier 1基準(ROI150%+, 1/2年黒字): ROI={'OK' if frow[3] >= 150 else 'NG'}({frow[3]:.1f}%), 黒字={'OK' if tier1_ok else 'NG'}")


if __name__ == '__main__':
    run_p1a()
    run_p1b()
    run_p2()
    run_p3()
    run_p4()
    run_p5()
    conn.close()
    print("\n\n=== 分析完了 ===")
