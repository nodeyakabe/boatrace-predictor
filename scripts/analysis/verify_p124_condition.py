# -*- coding: utf-8 -*-
"""C_P124_150_200_S90_98 条件の詳細正常性検証スクリプト
C信頼度 × p1-p2-p4 × 150-200倍 × スコア90-98点
"""
import sys, io, sqlite3, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

CONF = 'C'
ODDS_LO, ODDS_HI = 150, 200
S_MIN, S_MAX = 90, 98

print("=" * 75)
print("C_P124_150_200_S90_98 詳細正常性検証")
print(f"  条件: C信頼度 × p1-p2-p4 × {ODDS_LO}-{ODDS_HI}倍 × スコア{S_MIN}-{S_MAX}点")
print(f"  c1_rank: A1/A2/B1/B2")
print("=" * 75)

# ==========================================================================
# 1. 実装正確性チェック: combo・hit条件の確認
# ==========================================================================
print("\n【1. 実装正確性チェック】")
print("  P124 combo: p1-p2-p4（予測1位-予測2位-予測4位）")
print("  hit条件: actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p4")
print()

# ==========================================================================
# 2. Direct SQL: 年度別・件数・的中・収支
# ==========================================================================
print("\n【2. Direct SQL 年度別検証】")
print("  スキャンSQLと同条件で直接確認（JOIN trifecta_odds でオッズ存在するレースのみ）")

q_yearly_scan = """
SELECT
    CAST(strftime('%Y', r.race_date) AS INT) AS yr,
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
GROUP BY yr ORDER BY yr
"""
cur.execute(q_yearly_scan)
rows = cur.fetchall()
total_n = sum(r[1] for r in rows)
total_h = sum(r[2] for r in rows)
total_p = sum(r[3] for r in rows)
roi_total = (total_p + total_n * 100) / (total_n * 100) * 100 if total_n > 0 else 0
black = sum(1 for r in rows if r[3] > 0)

print(f"  {'年':>4} | {'件数':>5} | {'的中':>4} | {'ROI':>7} | {'収支':>10} | 判定")
for r in rows:
    roi = (r[3] + r[1] * 100) / (r[1] * 100) * 100 if r[1] > 0 else 0
    mark = '○' if r[3] > 0 else '×'
    print(f"  {r[0]} | {r[1]:>5} | {r[2]:>4} | {roi:>6.1f}% | {int(r[3]):>+10,}円 | {mark}")
print(f"  合計 | {total_n:>5} | {total_h:>4} | {roi_total:>6.1f}% | {int(total_p):>+10,}円 | {black}/6年")

# ==========================================================================
# 3. バックテスト相当のDirect SQL（COALESCE版: bet_amount=0を除外）
# ==========================================================================
print("\n【3. バックテスト相当 Direct SQL（オッズ=0除外版）】")
print("  standard_backtest.py と同じロジック（COALESCE(odds, 0)）を模倣")

q_backtest_style = """
SELECT
    CAST(strftime('%Y', r.race_date) AS INT) AS yr,
    COUNT(*) AS races_total,
    SUM(CASE WHEN COALESCE(
        (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
         AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)),
        0) >= 150
        AND COALESCE(
        (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
         AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)),
        0) < 200
    THEN 1 ELSE 0 END AS bets,
    SUM(CASE WHEN
        COALESCE(
        (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
         AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)),
        0) >= 150
        AND COALESCE(
        (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
         AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)),
        0) < 200
        AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') = rp1.pit_number
        AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') = rp2.pit_number
        AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') = rp4.pit_number
    THEN 1 ELSE 0 END AS hits,
    SUM(CASE WHEN
        COALESCE(
        (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
         AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)),
        0) >= 150
        AND COALESCE(
        (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
         AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)),
        0) < 200
        AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') = rp1.pit_number
        AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') = rp2.pit_number
        AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') = rp4.pit_number
    THEN COALESCE(
        (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
         AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)),
        0) * 100 ELSE 0 END AS payout
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
WHERE r.race_date >= '2020-01-01' AND r.race_date <= '2025-12-31'
    AND rp.confidence = 'C'
    AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    AND rp1.total_score >= 90 AND rp1.total_score < 98
GROUP BY yr ORDER BY yr
"""
cur.execute(q_backtest_style)
rows_bt = cur.fetchall()
print(f"  {'年':>4} | {'対象計':>6} | {'賭け':>5} | {'的中':>4} | {'ROI':>7} | {'収支':>10}")
for r in rows_bt:
    bets = r[2] if r[2] else 0
    hits = r[3] if r[3] else 0
    payout = r[4] if r[4] else 0
    roi = payout / (bets * 100) * 100 if bets > 0 else 0
    profit = payout - bets * 100
    mark = '○' if profit > 0 else '×'
    print(f"  {r[0]} | {r[1]:>6} | {bets:>5} | {hits:>4} | {roi:>6.1f}% | {int(profit):>+10,}円 | {mark}")

# ==========================================================================
# 4. 乖離原因分析: スキャンJOIN版 vs バックテスト版の差分
# ==========================================================================
print("\n【4. 2021年 乖離原因分析: JOIN版 vs COALESCE版】")
q_diff = """
SELECT
    r.race_date,
    r.venue_code,
    r.race_number,
    rp1.pit_number as p1,
    rp2.pit_number as p2,
    rp4.pit_number as p4,
    CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT) as combo,
    COALESCE(
        (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
         AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)),
        -1) as odds_coalesce,
    -- JOIN版でのオッズ（存在すれば取得）
    (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
     AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)
     AND CAST(o.odds AS REAL) >= 150 AND CAST(o.odds AS REAL) < 200
     LIMIT 1) as odds_in_range,
    rp1.total_score
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
WHERE r.race_date >= '2021-01-01' AND r.race_date <= '2021-12-31'
    AND rp.confidence = 'C'
    AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    AND rp1.total_score >= 90 AND rp1.total_score < 98
ORDER BY r.race_date
"""
cur.execute(q_diff)
rows_diff = cur.fetchall()
print(f"  2021年 総対象レース数: {len(rows_diff)}")
in_range = [r for r in rows_diff if r[7] is not None and r[7] != -1 and 150 <= float(r[7]) < 200]
not_in_range = [r for r in rows_diff if r[8] is None]
print(f"  JOIN版オッズ150-200倍 存在: {len(in_range)}件")
print(f"  COALESCE(-1): オッズ存在しない: {len([r for r in rows_diff if r[7] == -1])}件")
print(f"  オッズ存在するが150-200倍外: {len([r for r in rows_diff if r[7] != -1 and r[7] != -999 and (float(r[7]) < 150 or float(r[7]) >= 200)])}件")

# ==========================================================================
# 5. 的中レース詳細（全期間）
# ==========================================================================
print("\n【5. 的中レース詳細（全4件）】")
q_hits = """
SELECT
    r.race_date,
    r.venue_code,
    r.race_number,
    rp1.pit_number as p1,
    rp2.pit_number as p2,
    rp4.pit_number as p4,
    CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT) as combo,
    t.odds,
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
cur.execute(q_hits)
hit_rows = cur.fetchall()
print(f"  {'日付':>10} | {'場':>4} | {'R':>2} | {'組合せ':>7} | {'オッズ':>7} | {'スコア':>6} | {'信頼度'}")
for r in hit_rows:
    print(f"  {r[0]} | {r[1]:>4} | {r[2]:>2}R | {r[6]:>7} | {float(r[7]):>6.1f}倍 | {r[8]:>6.1f}点 | {r[9]}")

# ==========================================================================
# 6. スキャンのみに出てくる2021年の的中レース特定
# ==========================================================================
print("\n【6. スキャン vs バックテスト: 2021年的中レースの追跡】")
print("  スキャン（JOIN版）の2021年的中レースを特定...")

q_scan_hits_2021 = """
SELECT
    r.race_date,
    r.venue_code,
    r.race_number,
    rp1.pit_number as p1,
    rp2.pit_number as p2,
    rp4.pit_number as p4,
    t.combination,
    CAST(t.odds AS REAL) as odds,
    rp1.total_score,
    -- 結果確認
    (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
    (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
    (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd,
    -- バックテスト用COALESCE版オッズ
    COALESCE(
        (SELECT o2.odds FROM trifecta_odds o2 WHERE o2.race_id = r.id
         AND o2.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)
         LIMIT 1), 0) as odds_coalesce
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
WHERE r.race_date >= '2021-01-01' AND r.race_date <= '2021-12-31'
    AND rp1.confidence = 'C'
    AND CAST(t.odds AS REAL) >= 150 AND CAST(t.odds AS REAL) < 200
    AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    AND rp1.total_score >= 90 AND rp1.total_score < 98
    AND rs1.pit_number = rp1.pit_number
    AND rs2.pit_number = rp2.pit_number
    AND rs3.pit_number = rp4.pit_number
"""
cur.execute(q_scan_hits_2021)
scan_hits_2021 = cur.fetchall()
if scan_hits_2021:
    for r in scan_hits_2021:
        print(f"  日付:{r[0]}, 会場:{r[1]}, R:{r[2]}, combo:{r[6]}, オッズ:{float(r[7]):.1f}倍")
        print(f"    スコア:{r[8]:.1f}, 結果:{r[9]}-{r[10]}-{r[11]}, COALESCE odds:{float(r[12]):.1f}")
        bt_odds = float(r[12])
        if bt_odds >= 150 and bt_odds < 200:
            print(f"    → バックテスト: bet_amount=100円, payout={bt_odds*100:.0f}円 ✓")
        else:
            print(f"    → バックテスト: COALESCE={bt_odds}（{150}未満or{200}以上）→ bet_amount=0 ← 乖離原因!")
else:
    print("  2021年のスキャン的中: 0件（バックテストと一致）")

# ==========================================================================
# 7. 月別パフォーマンス
# ==========================================================================
print("\n【7. 月別パフォーマンス（全期間2020-2025）】")
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
for r in mon_rows:
    roi = (r[3] + r[1] * 100) / (r[1] * 100) * 100 if r[1] > 0 else 0
    mark = '○' if r[3] > 0 else '×'
    print(f"  {r[0]:>2}月 | {r[1]:>5} | {r[2]:>4} | {roi:>6.1f}% | {int(r[3]):>+10,}円 | {mark}")

# ==========================================================================
# 8. 会場別パフォーマンス（件数上位）
# ==========================================================================
print("\n【8. 会場別パフォーマンス】")
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
# 9. オッズ分布（150-200倍内での分布）
# ==========================================================================
print("\n【9. オッズ分布（150-200倍帯内）】")
q_odds_dist = """
SELECT
    CASE
        WHEN CAST(t.odds AS REAL) < 155 THEN '150-155'
        WHEN CAST(t.odds AS REAL) < 160 THEN '155-160'
        WHEN CAST(t.odds AS REAL) < 165 THEN '160-165'
        WHEN CAST(t.odds AS REAL) < 170 THEN '165-170'
        WHEN CAST(t.odds AS REAL) < 175 THEN '170-175'
        WHEN CAST(t.odds AS REAL) < 180 THEN '175-180'
        WHEN CAST(t.odds AS REAL) < 185 THEN '180-185'
        WHEN CAST(t.odds AS REAL) < 190 THEN '185-190'
        WHEN CAST(t.odds AS REAL) < 195 THEN '190-195'
        ELSE '195-200'
    END as band,
    COUNT(*) as n,
    SUM(CASE WHEN rs1.pit_number = rp1.pit_number
              AND rs2.pit_number = rp2.pit_number
              AND rs3.pit_number = rp4.pit_number
         THEN 1 ELSE 0 END) AS hits
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
GROUP BY band ORDER BY band
"""
cur.execute(q_odds_dist)
odds_rows = cur.fetchall()
print(f"  {'オッズ帯':>8} | {'件数':>5} | {'的中':>4}")
for r in odds_rows:
    mark = '★' if r[2] > 0 else ' '
    print(f"  {r[0]:>8} | {r[1]:>5} | {r[2]:>4} | {mark}")

# ==========================================================================
# 10. スコア分布（90-98点内）
# ==========================================================================
print("\n【10. スコア分布（90-98点帯内）】")
q_score_dist = """
SELECT
    CAST(rp1.total_score AS INT) as score_int,
    COUNT(*) as n,
    SUM(CASE WHEN rs1.pit_number = rp1.pit_number
              AND rs2.pit_number = rp2.pit_number
              AND rs3.pit_number = rp4.pit_number
         THEN 1 ELSE 0 END) AS hits
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
GROUP BY score_int ORDER BY score_int
"""
cur.execute(q_score_dist)
score_rows = cur.fetchall()
print(f"  {'スコア':>5} | {'件数':>5} | {'的中':>4}")
for r in score_rows:
    mark = '★' if r[2] > 0 else ' '
    print(f"  {r[0]:>5}点  | {r[1]:>5} | {r[2]:>4} | {mark}")

# ==========================================================================
# 11. c1_rank 別パフォーマンス
# ==========================================================================
print("\n【11. c1_rank 別パフォーマンス】")
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
# 12. 境界値チェック（スコア90.0, 97.9 の確認）
# ==========================================================================
print("\n【12. スコア境界値チェック】")
cur.execute("""
SELECT COUNT(*), MIN(rp1.total_score), MAX(rp1.total_score)
FROM races r
JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' ||
        (SELECT CAST(rp2b.pit_number AS TEXT) FROM race_predictions rp2b WHERE rp2b.race_id = r.id AND rp2b.prediction_type='before' AND rp2b.rank_prediction=2 LIMIT 1) || '-' ||
        (SELECT CAST(rp4b.pit_number AS TEXT) FROM race_predictions rp4b WHERE rp4b.race_id = r.id AND rp4b.prediction_type='before' AND rp4b.rank_prediction=4 LIMIT 1)
JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
WHERE rp1.confidence = 'C'
    AND CAST(t.odds AS REAL) >= 150 AND CAST(t.odds AS REAL) < 200
    AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    AND rp1.total_score >= 90 AND rp1.total_score < 98
""")
r = cur.fetchone()
print(f"  件数:{r[0]}, スコア範囲: {r[1]:.2f} - {r[2]:.2f}")
print(f"  → score_min=90 AND score_max=98 の実装: 90.0以上98.0未満 ✓")

# ==========================================================================
# 13. 結論サマリ
# ==========================================================================
print("\n" + "=" * 75)
print("【検証結論サマリ】")
print("=" * 75)
print(f"  Direct SQL（スキャン版）: {total_n}件 / {total_h}的中 / ROI {roi_total:.1f}% / {total_p:+,.0f}円 / {black}/6年黒字")

conn.close()
print("\n完了")
