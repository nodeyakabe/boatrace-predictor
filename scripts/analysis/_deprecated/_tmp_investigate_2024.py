#!/usr/bin/env python3
"""2024 advance A率低下の原因調査用スクリプト"""
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 2024 advance 2026-02-25生成: score>=75, conf!=A の例
cursor.execute("""
    SELECT rp.race_id, rp.total_score, rp.confidence, rp.pit_number
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    WHERE rp.prediction_type = 'advance'
    AND strftime('%Y', r.race_date) = '2024'
    AND rp.rank_prediction = 1
    AND SUBSTR(rp.generated_at, 1, 10) = '2026-02-25'
    AND rp.total_score >= 80
    AND rp.confidence = 'C'
    LIMIT 5
""")
races = cursor.fetchall()
print("=== 2024 advance 2026-02-25: score>=80, conf=C ===")
for row in races:
    print(f"race_id={row[0]}, score={row[1]}, conf={row[2]}, pit={row[3]}")

# これらのレースのrank=1,2 のスコアを確認
for race_id, _, _, _ in races:
    cursor.execute("""
        SELECT rp.rank_prediction, rp.total_score, rp.confidence, rp.pit_number
        FROM race_predictions rp
        WHERE rp.race_id = ? AND rp.prediction_type = 'advance'
        AND SUBSTR(rp.generated_at, 1, 10) = '2026-02-25'
        ORDER BY rp.rank_prediction
        LIMIT 3
    """, (race_id,))
    rows = cursor.fetchall()
    if len(rows) >= 2:
        gap = rows[0][1] - rows[1][1]
        print(f"  race {race_id}: rank1={rows[0][1]}({rows[0][2]}) rank2={rows[1][1]}({rows[1][2]}) gap={gap:.1f}")

# 同じrace_idが2025-12-22にも存在するか？（重複）
print("\n=== Check if same race_id has old-code entries ===")
for race_id, _, _, _ in races:
    cursor.execute("""
        SELECT SUBSTR(rp.generated_at, 1, 10) as gen, rp.total_score, rp.confidence
        FROM race_predictions rp
        WHERE rp.race_id = ? AND rp.prediction_type = 'advance'
        AND rp.rank_prediction = 1
        ORDER BY rp.generated_at
    """, (race_id,))
    for row in cursor.fetchall():
        print(f"  race {race_id}: gen={row[0]}, score={row[1]}, conf={row[2]}")

# ON CONFLICT DO UPDATE の確認: 同一 race_id + pit_number + prediction_type で
# UPSERT されるか、それとも複数行が存在するか？
print("\n=== Check for duplicate entries (same race_id, rank=1) ===")
cursor.execute("""
    SELECT race_id, COUNT(*) as cnt
    FROM race_predictions
    WHERE prediction_type = 'advance'
    AND rank_prediction = 1
    AND race_id IN (
        SELECT id FROM races WHERE strftime('%Y', race_date) = '2024'
    )
    GROUP BY race_id
    HAVING cnt > 1
    LIMIT 10
""")
dups = cursor.fetchall()
print(f"Duplicate race_ids: {len(dups)} found")
for row in dups[:5]:
    print(f"  race_id={row[0]}, count={row[1]}")

conn.close()
