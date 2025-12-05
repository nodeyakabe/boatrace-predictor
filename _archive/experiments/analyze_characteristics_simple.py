"""
競艇場（会場）と選手の簡易特性分析

利用可能なテーブルのみで統計分析
"""

import sys
sys.path.append('.')

import sqlite3
import pandas as pd
from datetime import datetime

print("=" * 70)
print("競艇場・選手 簡易特性分析")
print("=" * 70)

conn = sqlite3.connect("data/boatrace.db")
start_date = "2024-04-01"
end_date = "2024-06-30"
print(f"分析期間: {start_date} 〜 {end_date}\n")

# ==================== 1. 会場特性分析 ====================
print("【1】会場特性分析")
print("-" * 70)

query_venue = """
SELECT
    r.venue_code,
    COUNT(DISTINCT r.id) as total_races,

    -- 枠番別勝率
    SUM(CASE WHEN e.pit_number = 1 AND res.rank = '1' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(SUM(CASE WHEN e.pit_number = 1 THEN 1 ELSE 0 END), 0) as pit1_win_rate,
    SUM(CASE WHEN e.pit_number = 2 AND res.rank = '1' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(SUM(CASE WHEN e.pit_number = 2 THEN 1 ELSE 0 END), 0) as pit2_win_rate,
    SUM(CASE WHEN e.pit_number = 3 AND res.rank = '1' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(SUM(CASE WHEN e.pit_number = 3 THEN 1 ELSE 0 END), 0) as pit3_win_rate,

    -- 平均モーター2連対率
    AVG(e.second_rate) as avg_motor_2rate

FROM races r
LEFT JOIN entries e ON r.id = e.race_id
LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
WHERE r.race_date BETWEEN ? AND ?
GROUP BY r.venue_code
ORDER BY total_races DESC
"""

df_venue = pd.read_sql_query(query_venue, conn, params=(start_date, end_date))
print(f"会場数: {len(df_venue)}\n")
print(df_venue.to_string(index=False))

# ==================== 2. 級別分析 ====================
print("\n【2】級別別パフォーマンス")
print("-" * 70)

query_rank = """
SELECT
    e.racer_rank as grade,
    COUNT(*) as total_races,
    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate,
    AVG(CAST(res.rank AS REAL)) as avg_rank,
    AVG(e.win_rate) as avg_racer_win_rate

FROM entries e
JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
JOIN races r ON e.race_id = r.id
WHERE r.race_date BETWEEN ? AND ?
  AND res.rank IN ('1', '2', '3', '4', '5', '6')
  AND e.racer_rank IS NOT NULL
GROUP BY e.racer_rank
ORDER BY e.racer_rank
"""

df_rank = pd.read_sql_query(query_rank, conn, params=(start_date, end_date))
print(df_rank.to_string(index=False))

# ==================== 3. 枠番別勝率 ====================
print("\n【3】枠番別勝率（全会場平均）")
print("-" * 70)

query_pit = """
SELECT
    e.pit_number,
    COUNT(*) as total_races,
    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate,
    SUM(CASE WHEN res.rank IN ('1', '2') THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as place2_rate

FROM entries e
JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
JOIN races r ON e.race_id = r.id
WHERE r.race_date BETWEEN ? AND ?
  AND res.rank IN ('1', '2', '3', '4', '5', '6')
GROUP BY e.pit_number
ORDER BY e.pit_number
"""

df_pit = pd.read_sql_query(query_pit, conn, params=(start_date, end_date))
print(df_pit.to_string(index=False))

# ==================== 4. トップ選手 ====================
print("\n【4】トップ選手（出走50回以上）")
print("-" * 70)

query_racer = """
SELECT
    e.racer_number,
    e.racer_name,
    e.racer_rank as grade,
    COUNT(*) as total_races,
    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate,
    AVG(CAST(res.rank AS REAL)) as avg_rank,
    AVG(e.win_rate) as avg_racer_win_rate

FROM entries e
JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
JOIN races r ON e.race_id = r.id
WHERE r.race_date BETWEEN ? AND ?
  AND res.rank IN ('1', '2', '3', '4', '5', '6')
GROUP BY e.racer_number, e.racer_name, e.racer_rank
HAVING COUNT(*) >= 50
ORDER BY win_rate DESC
LIMIT 20
"""

df_racer = pd.read_sql_query(query_racer, conn, params=(start_date, end_date))
print(df_racer.to_string(index=False))

# ==================== 5. 勝率ヒートマップデータ ====================
print("\n【5】会場×級別の勝率マトリックス")
print("-" * 70)

query_matrix = """
SELECT
    r.venue_code,
    e.racer_rank as grade,
    COUNT(*) as races,
    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate

FROM entries e
JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
JOIN races r ON e.race_id = r.id
WHERE r.race_date BETWEEN ? AND ?
  AND res.rank IN ('1', '2', '3', '4', '5', '6')
  AND e.racer_rank IS NOT NULL
GROUP BY r.venue_code, e.racer_rank
HAVING COUNT(*) >= 20
ORDER BY r.venue_code, e.racer_rank
"""

df_matrix = pd.read_sql_query(query_matrix, conn, params=(start_date, end_date))

# ピボットテーブル化
pivot = df_matrix.pivot(index='venue_code', columns='grade', values='win_rate')
print(pivot.to_string())

conn.close()

print(f"\n完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
