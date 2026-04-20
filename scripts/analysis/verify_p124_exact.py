# -*- coding: utf-8 -*-
"""standard_backtest.pyのP124クエリを直接実行して乖離原因を確認"""
import sys, io, sqlite3, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=" * 75)
print("standard_backtest.py P124クエリ 直接実行検証")
print("=" * 75)

# standard_backtest.pyのanalyze_conditionを呼び出し
import sys
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'scripts', 'backtest'))
sys.path.insert(0, PROJECT_ROOT)

from standard_backtest import analyze_condition, analyze_condition_yearly

cond = {
    'id': 'C_P124_150_200_S90_98',
    'priority': 29,
    'name': 'C×p1-p2-p4×150-200倍×スコア90-98',
    'confidence': 'C',
    'c1_rank': ['A1', 'A2', 'B1', 'B2'],
    'odds_min': 150,
    'odds_max': 200,
    'score_min': 90,
    'score_max': 98,
    'use_pattern_h': False,
    'use_pattern_p124': True,
    'description': 'C信頼度×p1-p2-p4×150-200倍×スコア90-98点',
    'method': '1点',
    'bet_amount': 100,
    'expected_roi': 157.9,
}

print("\n【全6年間 analyze_condition 実行】")
result = analyze_condition(cur, cond, '2020-01-01', '2026-01-01')
print(f"  bets: {result['bets']}, hits: {result['hits']}, ROI: {result.get('roi', 0):.1f}%, profit: {result.get('profit', 0):+,.0f}円")

print("\n【年度別 analyze_condition_yearly 実行】")
yearly = analyze_condition_yearly(cur, cond, [2020, 2021, 2022, 2023, 2024, 2025])
for y in yearly:
    mark = '○' if y.get('profit', 0) > 0 else '×'
    print(f"  {y['year']}: bets={y['bets']}, hits={y['hits']}, ROI={y.get('roi', 0):.1f}%, profit={y.get('profit', 0):+,.0f}円 | {mark}")

# ==========================================================================
# 2021年のみのクエリを直接実行（standard_backtest.pyのP124 SQL）
# ==========================================================================
print("\n【2021年のみ: standard_backtestのP124 CTEクエリ直接実行】")

# コードから読み取ったP124クエリ
confidence_clause = "AND rp.confidence = 'C'"
c1_rank_str = "A1','A2','B1','B2"
date_start = "2021-01-01"
date_end = "2022-01-01"
score_clause = "AND rp1.total_score >= 90 AND rp1.total_score < 98 "
odds_min = 150
odds_max = 200

# その他クローズは空（この条件には設定なし）
escape_rate_join = ""
bias_join = ""
motor_rate_join = ""
wave_height_join = ""
venue_clause = ""
motor_clause = ""
race_exclude_clause = ""
venue_exclude_clause = ""
predicted_course_clause = ""
c1_second_rate_clause = ""
month_exclude_clause = ""
venue_month_exclude_clause = ""
escape_rate_clause = ""
bias_clause = ""
motor_rate_clause = ""
wave_height_clause = ""
predicted_rank_class_clause = ""

query = f'''
WITH race_base AS (
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        rp.confidence,
        e1.racer_rank as c1_rank,
        rp1.pit_number as p1,
        rp2.pit_number as p2,
        rp4.pit_number as p4
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp.rank_prediction = 1
    {confidence_clause}
    AND e1.racer_rank IN ('{c1_rank_str}')
    AND r.race_date >= '{date_start}'
    AND r.race_date < '{date_end}'
    {score_clause}
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
        CASE WHEN odds_124 >= {odds_min} AND odds_124 < {odds_max} THEN 100 ELSE 0 END as bet_amount,
        CASE
            WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                 AND odds_124 >= {odds_min} AND odds_124 < {odds_max}
            THEN odds_124 * 100 ELSE 0
        END as payout,
        CASE
            WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                 AND odds_124 >= {odds_min} AND odds_124 < {odds_max}
            THEN 1 ELSE 0
        END as is_hit
    FROM race_bets rb
)
SELECT
    COUNT(*) as races,
    SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
    SUM(is_hit) as hits,
    SUM(bet_amount) as total_investment,
    SUM(payout) as total_payout
FROM race_payouts
WHERE bet_amount > 0
'''

cur.execute(query)
r = cur.fetchone()
if r:
    races, bets, hits, inv, pay = r
    profit = (pay or 0) - (inv or 0)
    roi = (pay or 0) / (inv or 0) * 100 if inv and inv > 0 else 0
    print(f"  races={races}, bets={bets}, hits={hits}, ROI={roi:.1f}%, profit={profit:+,.0f}円")

# 的中行を詳細に出力
print("\n  的中行の詳細（bet_amount>0 AND is_hit=1）:")
query_detail = f'''
WITH race_base AS (
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
        rp.confidence,
        e1.racer_rank as c1_rank,
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
    {confidence_clause}
    AND e1.racer_rank IN ('{c1_rank_str}')
    AND r.race_date >= '{date_start}'
    AND r.race_date < '{date_end}'
    {score_clause}
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
    SELECT rb.race_date, rb.venue_code, rb.race_number,
           rb.p1, rb.p2, rb.p4, rb.odds_124, rb.total_score,
           rb.actual_1st, rb.actual_2nd, rb.actual_3rd,
        CASE WHEN odds_124 >= {odds_min} AND odds_124 < {odds_max} THEN 100 ELSE 0 END as bet_amount,
        CASE
            WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                 AND odds_124 >= {odds_min} AND odds_124 < {odds_max}
            THEN 1 ELSE 0
        END as is_hit
    FROM race_bets rb
)
SELECT * FROM race_payouts
WHERE bet_amount > 0 AND is_hit = 1
'''
cur.execute(query_detail)
detail_rows = cur.fetchall()
if detail_rows:
    for r in detail_rows:
        print(f"  日付:{r[0]}, 会場:{r[1]}, R:{r[2]}, 予測:{r[3]}-{r[4]}-{r[5]}, オッズ:{float(r[6]):.1f}倍, スコア:{r[7]:.1f}")
        print(f"    実際: {r[8]}-{r[9]}-{r[10]}")
else:
    print("  的中なし")

# race_baseのカウントも確認
print("\n  race_base件数確認:")
query_base_count = f'''
SELECT COUNT(*) FROM (
    SELECT r.id
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp.rank_prediction = 1
    {confidence_clause}
    AND e1.racer_rank IN ('{c1_rank_str}')
    AND r.race_date >= '{date_start}'
    AND r.race_date < '{date_end}'
    {score_clause}
)
'''
cur.execute(query_base_count)
r = cur.fetchone()
print(f"  race_base件数（2021年）: {r[0]}")

# 的中候補: 2021-01-20の確認
print("\n  2021-01-20 会場14 11R の各段階確認:")
cur.execute("""
    SELECT r.id, r.race_date, r.venue_code, r.race_number
    FROM races r WHERE r.race_date = '2021-01-20' AND r.venue_code = '14' AND r.race_number = 11
""")
race_row = cur.fetchone()
if race_row:
    race_id = race_row[0]
    print(f"  race_id: {race_id}")

    # trifecta_odds確認
    cur.execute("""
        SELECT combination, odds FROM trifecta_odds
        WHERE race_id = ? AND combination = '5-3-1'
    """, (race_id,))
    odds_row = cur.fetchone()
    if odds_row:
        print(f"  trifecta_odds 5-3-1: {odds_row[1]}倍 ✓")
    else:
        print("  trifecta_odds 5-3-1: 存在しない ⚠️")

    # COALESCE確認
    cur.execute("""
        SELECT COALESCE(
            (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = ? AND o.combination = '5-3-1'),
            0)
    """, (race_id,))
    r = cur.fetchone()
    print(f"  COALESCE(odds, 0): {float(r[0])}")
    if 150 <= float(r[0]) < 200:
        print(f"  → bet_amount=100円 ✓（150以上200未満）")
    else:
        print(f"  → bet_amount=0円（範囲外）⚠️")

    # race_base参加確認
    cur.execute(f"""
        SELECT r.id, rp.rank_prediction, rp.confidence, rp1.pit_number, rp2.pit_number, rp4.pit_number,
               e1.racer_rank, rp1.total_score
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE r.id = ? AND rp.rank_prediction = 1
        {confidence_clause}
        AND e1.racer_rank IN ('{c1_rank_str}')
        {score_clause}
    """, (race_id,))
    r = cur.fetchone()
    if r:
        print(f"  race_base参加: ✓ p1={r[3]}, p2={r[4]}, p4={r[5]}, c1_rank={r[6]}, score={float(r[7]):.1f}")
    else:
        print("  race_base参加: なし ⚠️")

conn.close()
print("\n完了")
