# -*- coding: utf-8 -*-
"""P124 2021年の乖離原因追跡 + 残りの検証項目"""
import sys, io, sqlite3, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=" * 75)
print("C_P124 詳細検証（続き）")
print("=" * 75)

# ==========================================================================
# 3. バックテスト版: 2021年の詳細（standard_backtest CTE模倣）
# ==========================================================================
print("\n【3. バックテスト版CTE: 2021年詳細】")
# standard_backtest.py のP124クエリを2021年に絞って実行
q_bt_2021 = """
WITH race_base AS (
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        rp.confidence,
        e1.racer_rank as c1_rank,
        rp1.pit_number as p1,
        rp2.pit_number as p2,
        rp4.pit_number as p4,
        rp1.total_score as score
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp.rank_prediction = 1
    AND rp.confidence = 'C'
    AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    AND r.race_date >= '2021-01-01'
    AND r.race_date < '2022-01-01'
    AND rp1.total_score >= 90
    AND rp1.total_score < 98
),
race_bets AS (
    SELECT
        rb.*,
        COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                  AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) as odds_124,
        (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
        (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
        (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
    FROM race_base rb
),
race_payouts AS (
    SELECT
        rb.*,
        CASE WHEN odds_124 >= 150 AND odds_124 < 200 THEN 100 ELSE 0 END as bet_amount,
        CASE
            WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                 AND odds_124 >= 150 AND odds_124 < 200
            THEN odds_124 * 100 ELSE 0
        END as payout,
        CASE
            WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                 AND odds_124 >= 150 AND odds_124 < 200
            THEN 1 ELSE 0
        END as is_hit
    FROM race_bets rb
)
SELECT
    COUNT(*) as total_races,
    SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
    SUM(is_hit) as hits,
    SUM(payout) - SUM(bet_amount) as profit
FROM race_payouts
WHERE bet_amount > 0
"""
cur.execute(q_bt_2021)
r = cur.fetchone()
print(f"  標準バックテスト版 2021年: 賭け={r[1]}件, 的中={r[2]}件, 収支={int(r[3]):+,}円")

# ==========================================================================
# 4. 乖離原因特定: 2021年のDirect JOIN vs COALESCE比較
# ==========================================================================
print("\n【4. 2021年 JOIN vs COALESCE 詳細比較】")
# JOIN版で取れるレースを列挙
q_join_2021 = """
SELECT
    r.race_date,
    r.venue_code,
    r.race_number,
    rp1.pit_number as p1,
    rp2.pit_number as p2,
    rp4.pit_number as p4,
    CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT) as combo,
    CAST(t.odds AS REAL) as odds_join,
    rp1.total_score,
    -- 結果
    (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as a1,
    (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as a2,
    (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as a3
FROM races r
JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)
JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
JOIN results rs1 ON r.id = rs1.race_id AND rs1.rank = '1'
JOIN results rs2 ON r.id = rs2.race_id AND rs2.rank = '2'
JOIN results rs3 ON r.id = rs3.race_id AND rs3.rank = '3'
WHERE r.race_date >= '2021-01-01' AND r.race_date < '2022-01-01'
    AND rp1.confidence = 'C'
    AND CAST(t.odds AS REAL) >= 150 AND CAST(t.odds AS REAL) < 200
    AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    AND rp1.total_score >= 90 AND rp1.total_score < 98
    AND rs1.pit_number = rp1.pit_number
    AND rs2.pit_number = rp2.pit_number
    AND rs3.pit_number = rp4.pit_number
ORDER BY r.race_date
"""
cur.execute(q_join_2021)
join_hits_2021 = cur.fetchall()
print(f"  JOIN版 2021年的中: {len(join_hits_2021)}件")
for r in join_hits_2021:
    print(f"  日付:{r[0]}, 会場:{r[1]}, R:{r[2]}, combo:{r[6]}, オッズ:{r[7]:.1f}倍, スコア:{r[8]:.1f}")
    print(f"    結果: {r[9]}-{r[10]}-{r[11]} (予測: {r[3]}-{r[4]}-{r[5]}) → 的中✓")

    # このrace_idのtrifecta_oddsをCOALESCEで確認
    cur.execute("""
        SELECT COUNT(*), MIN(CAST(odds AS REAL)), MAX(CAST(odds AS REAL))
        FROM trifecta_odds
        WHERE race_id = (
            SELECT id FROM races WHERE race_date=? AND venue_code=? AND race_number=?
        ) AND combination = ?
    """, (r[0], r[1], r[2], r[6]))
    odds_check = cur.fetchone()
    print(f"    trifecta_odds確認: {odds_check[0]}行, オッズ範囲 {odds_check[1]}-{odds_check[2]}")

# ==========================================================================
# 5. バックテスト版CTE 2021年 全個別レース（bet_amount>0のもの）
# ==========================================================================
print("\n【5. バックテスト版CTE 2021年 的中候補レース確認】")
q_bt_detail = """
WITH race_base AS (
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
        rp.confidence,
        rp1.pit_number as p1,
        rp2.pit_number as p2,
        rp4.pit_number as p4,
        rp1.total_score
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp.rank_prediction = 1
    AND rp.confidence = 'C'
    AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    AND r.race_date >= '2021-01-01'
    AND r.race_date < '2022-01-01'
    AND rp1.total_score >= 90
    AND rp1.total_score < 98
)
SELECT
    rb.race_date, rb.venue_code, rb.race_number,
    rb.p1, rb.p2, rb.p4, rb.total_score,
    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
              AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) as odds_124,
    (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as a1,
    (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as a2,
    (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as a3
FROM race_base rb
WHERE
    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
              AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) >= 150
    AND
    COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
              AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) < 200
    AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
    AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
    AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p4
"""
cur.execute(q_bt_detail)
bt_hits = cur.fetchall()
print(f"  バックテスト版 2021年 的中: {len(bt_hits)}件")
for r in bt_hits:
    print(f"  日付:{r[0]}, 会場:{r[1]}, R:{r[2]}, combo:{r[3]}-{r[4]}-{r[5]}, オッズ:{float(r[7]):.1f}倍")

# ==========================================================================
# 6. 乖離の根本原因: race_predictions のduplicate問題
# ==========================================================================
print("\n【6. JOIN重複問題チェック（1レースにrp1が複数存在するか）】")
q_dup_check = """
SELECT r.race_date, r.venue_code, r.race_number,
       COUNT(DISTINCT rp1.id) as rp1_count,
       COUNT(DISTINCT rp2.id) as rp2_count,
       COUNT(DISTINCT rp4.id) as rp4_count
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)
WHERE rp.rank_prediction = 1
    AND rp.confidence = 'C'
    AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    AND r.race_date >= '2021-01-01' AND r.race_date < '2022-01-01'
    AND rp1.total_score >= 90 AND rp1.total_score < 98
    AND CAST(t.odds AS REAL) >= 150 AND CAST(t.odds AS REAL) < 200
GROUP BY r.race_date, r.venue_code, r.race_number
HAVING COUNT(DISTINCT rp1.id) > 1 OR COUNT(DISTINCT rp2.id) > 1 OR COUNT(DISTINCT rp4.id) > 1
"""
cur.execute(q_dup_check)
dup_rows = cur.fetchall()
if dup_rows:
    print(f"  ⚠️ 重複あり: {len(dup_rows)}件")
    for r in dup_rows:
        print(f"  {r[0]}, {r[1]}, {r[2]}R: rp1={r[3]}件, rp2={r[4]}件, rp4={r[5]}件")
else:
    print("  重複なし ✓")

# ==========================================================================
# 7. 的中レース詳細（全期間・全4件）
# ==========================================================================
print("\n【7. 的中レース詳細（全期間・Direct SQL版）】")
q_all_hits = """
SELECT
    r.race_date,
    r.venue_code,
    r.race_number,
    rp1.pit_number as p1,
    rp2.pit_number as p2,
    rp4.pit_number as p4,
    CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT) as combo,
    CAST(t.odds AS REAL) as odds,
    rp1.total_score,
    rp1.confidence
FROM races r
JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)
JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
JOIN results rs1 ON r.id = rs1.race_id AND rs1.rank = '1'
JOIN results rs2 ON r.id = rs2.race_id AND rs2.rank = '2'
JOIN results rs3 ON r.id = rs3.race_id AND rs3.rank = '3'
WHERE r.race_date >= '2020-01-01' AND r.race_date <= '2025-12-31'
    AND rp1.confidence = 'C'
    AND CAST(t.odds AS REAL) >= 150 AND CAST(t.odds AS REAL) < 200
    AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    AND rp1.total_score >= 90 AND rp1.total_score < 98
    AND rs1.pit_number = rp1.pit_number
    AND rs2.pit_number = rp2.pit_number
    AND rs3.pit_number = rp4.pit_number
ORDER BY r.race_date
"""
cur.execute(q_all_hits)
all_hits = cur.fetchall()
print(f"  合計的中: {len(all_hits)}件")
for r in all_hits:
    payout = float(r[7]) * 100
    print(f"  {r[0]} | 会場:{r[1]} | {r[2]}R | {r[6]} | {float(r[7]):.1f}倍 | 払戻:{int(payout):,}円 | スコア:{r[8]:.1f} | {r[9]}")

# ==========================================================================
# 8. 月別パフォーマンス（Direct SQL版）
# ==========================================================================
print("\n【8. 月別パフォーマンス（Direct SQL）】")
q_monthly = """
SELECT
    CAST(strftime('%m', r.race_date) AS INT) as mon,
    COUNT(*) AS n,
    SUM(CASE WHEN rs1.pit_number = rp1.pit_number
              AND rs2.pit_number = rp2.pit_number
              AND rs3.pit_number = rp4.pit_number
         THEN 1 ELSE 0 END) AS hits,
    SUM(CASE WHEN rs1.pit_number = rp1.pit_number
              AND rs2.pit_number = rp2.pit_number
              AND rs3.pit_number = rp4.pit_number
         THEN CAST(t.odds AS REAL) * 100 ELSE 0 END) - COUNT(*) * 100 AS profit
FROM races r
JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)
JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
JOIN results rs1 ON r.id = rs1.race_id AND rs1.rank = '1'
JOIN results rs2 ON r.id = rs2.race_id AND rs2.rank = '2'
JOIN results rs3 ON r.id = rs3.race_id AND rs3.rank = '3'
WHERE r.race_date >= '2020-01-01' AND r.race_date <= '2025-12-31'
    AND rp1.confidence = 'C'
    AND CAST(t.odds AS REAL) >= 150 AND CAST(t.odds AS REAL) < 200
    AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    AND rp1.total_score >= 90 AND rp1.total_score < 98
GROUP BY mon ORDER BY mon
"""
cur.execute(q_monthly)
mon_rows = cur.fetchall()
print(f"  {'月':>3} | {'件数':>5} | {'的中':>4} | {'ROI':>7} | {'収支':>10}")
black_mon = 0
for r in mon_rows:
    roi = (r[3] + r[1] * 100) / (r[1] * 100) * 100 if r[1] > 0 else 0
    mark = '○' if r[3] > 0 else '×'
    if r[3] > 0: black_mon += 1
    print(f"  {r[0]:>2}月 | {r[1]:>5} | {r[2]:>4} | {roi:>6.1f}% | {int(r[3]):>+10,}円 | {mark}")
print(f"  黒字月数: {black_mon}/12月")

# ==========================================================================
# 9. 会場別パフォーマンス（Direct SQL版）
# ==========================================================================
print("\n【9. 会場別パフォーマンス（Direct SQL）】")
q_venue = """
SELECT
    r.venue_code,
    COUNT(*) AS n,
    SUM(CASE WHEN rs1.pit_number = rp1.pit_number
              AND rs2.pit_number = rp2.pit_number
              AND rs3.pit_number = rp4.pit_number
         THEN 1 ELSE 0 END) AS hits,
    SUM(CASE WHEN rs1.pit_number = rp1.pit_number
              AND rs2.pit_number = rp2.pit_number
              AND rs3.pit_number = rp4.pit_number
         THEN CAST(t.odds AS REAL) * 100 ELSE 0 END) - COUNT(*) * 100 AS profit
FROM races r
JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)
JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
JOIN results rs1 ON r.id = rs1.race_id AND rs1.rank = '1'
JOIN results rs2 ON r.id = rs2.race_id AND rs2.rank = '2'
JOIN results rs3 ON r.id = rs3.race_id AND rs3.rank = '3'
WHERE r.race_date >= '2020-01-01' AND r.race_date <= '2025-12-31'
    AND rp1.confidence = 'C'
    AND CAST(t.odds AS REAL) >= 150 AND CAST(t.odds AS REAL) < 200
    AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    AND rp1.total_score >= 90 AND rp1.total_score < 98
GROUP BY r.venue_code ORDER BY n DESC
"""
cur.execute(q_venue)
venue_rows = cur.fetchall()
print(f"  {'会場':>4} | {'件数':>5} | {'的中':>4} | {'ROI':>7} | {'収支':>10}")
for r in venue_rows:
    if r[1] < 5: continue
    roi = (r[3] + r[1] * 100) / (r[1] * 100) * 100 if r[1] > 0 else 0
    mark = '★' if r[2] > 0 else ' '
    print(f"  {r[0]:>4} | {r[1]:>5} | {r[2]:>4} | {roi:>6.1f}% | {int(r[3]):>+10,}円 | {mark}")

# ==========================================================================
# 10. c1_rank別
# ==========================================================================
print("\n【10. c1_rank 別パフォーマンス（Direct SQL）】")
q_c1rank = """
SELECT
    e1.racer_rank,
    COUNT(*) AS n,
    SUM(CASE WHEN rs1.pit_number = rp1.pit_number
              AND rs2.pit_number = rp2.pit_number
              AND rs3.pit_number = rp4.pit_number
         THEN 1 ELSE 0 END) AS hits,
    SUM(CASE WHEN rs1.pit_number = rp1.pit_number
              AND rs2.pit_number = rp2.pit_number
              AND rs3.pit_number = rp4.pit_number
         THEN CAST(t.odds AS REAL) * 100 ELSE 0 END) - COUNT(*) * 100 AS profit
FROM races r
JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)
JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
JOIN results rs1 ON r.id = rs1.race_id AND rs1.rank = '1'
JOIN results rs2 ON r.id = rs2.race_id AND rs2.rank = '2'
JOIN results rs3 ON r.id = rs3.race_id AND rs3.rank = '3'
WHERE r.race_date >= '2020-01-01' AND r.race_date <= '2025-12-31'
    AND rp1.confidence = 'C'
    AND CAST(t.odds AS REAL) >= 150 AND CAST(t.odds AS REAL) < 200
    AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    AND rp1.total_score >= 90 AND rp1.total_score < 98
GROUP BY e1.racer_rank ORDER BY e1.racer_rank
"""
cur.execute(q_c1rank)
c1_rows = cur.fetchall()
print(f"  {'c1_rank':>8} | {'件数':>5} | {'的中':>4} | {'ROI':>7} | {'収支':>10}")
for r in c1_rows:
    roi = (r[3] + r[1] * 100) / (r[1] * 100) * 100 if r[1] > 0 else 0
    mark = '★' if r[2] > 0 else ' '
    print(f"  {r[0]:>8} | {r[1]:>5} | {r[2]:>4} | {roi:>6.1f}% | {int(r[3]):>+10,}円 | {mark}")

# ==========================================================================
# 11. IS/OOS 詳細検証
# ==========================================================================
print("\n【11. IS/OOS 検証（IS=2020-2022 / OOS=2023-2025）】")
for period, start, end, label in [
    ("IS", "2020-01-01", "2023-01-01", "IS(2020-2022)"),
    ("OOS", "2023-01-01", "2026-01-01", "OOS(2023-2025)"),
]:
    cur.execute(f"""
    SELECT COUNT(*) AS n,
           SUM(CASE WHEN rs1.pit_number = rp1.pit_number
                     AND rs2.pit_number = rp2.pit_number
                     AND rs3.pit_number = rp4.pit_number
                THEN 1 ELSE 0 END) AS hits,
           SUM(CASE WHEN rs1.pit_number = rp1.pit_number
                     AND rs2.pit_number = rp2.pit_number
                     AND rs3.pit_number = rp4.pit_number
                THEN CAST(t.odds AS REAL) * 100 ELSE 0 END) - COUNT(*) * 100 AS profit
    FROM races r
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN trifecta_odds t ON r.id = t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    JOIN results rs1 ON r.id = rs1.race_id AND rs1.rank = '1'
    JOIN results rs2 ON r.id = rs2.race_id AND rs2.rank = '2'
    JOIN results rs3 ON r.id = rs3.race_id AND rs3.rank = '3'
    WHERE r.race_date >= '{start}' AND r.race_date < '{end}'
        AND rp1.confidence = 'C'
        AND CAST(t.odds AS REAL) >= 150 AND CAST(t.odds AS REAL) < 200
        AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
        AND rp1.total_score >= 90 AND rp1.total_score < 98
    """)
    r = cur.fetchone()
    n, h, p = r[0], r[1], r[2]
    roi = (p + n * 100) / (n * 100) * 100 if n > 0 else 0
    print(f"  {label}: {n}件 / {h}的中 / ROI {roi:.1f}% / {int(p):+,}円")

# ==========================================================================
# 12. 結論サマリ
# ==========================================================================
print("\n" + "=" * 75)
print("【検証結論サマリ】")
print("=" * 75)

conn.close()
print("\n完了")
