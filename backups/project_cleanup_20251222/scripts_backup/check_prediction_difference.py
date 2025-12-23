# -*- coding: utf-8 -*-
"""事前予想と直前予想のスコア差確認"""
import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

db_path = ROOT_DIR / "data" / "boatrace.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 2025年1月のデータで確認
cursor.execute('''
    SELECT
        r.id, r.race_date, r.race_number,
        adv.pit_number, adv.total_score as adv_score, adv.rank_prediction as adv_rank,
        bef.total_score as bef_score, bef.rank_prediction as bef_rank
    FROM races r
    JOIN race_predictions adv ON r.id = adv.race_id AND adv.prediction_type = 'advance'
    JOIN race_predictions bef ON r.id = bef.race_id AND bef.prediction_type = 'before' AND adv.pit_number = bef.pit_number
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2025-01-10'
    ORDER BY r.race_date, r.race_number, adv.pit_number
    LIMIT 50
''')

rows = cursor.fetchall()

print(f"{'race_id':<8} {'date':<12} {'R':<3} {'pit':<4} {'adv_score':<12} {'bef_score':<12} {'diff':<12} {'rank変化'}")
print('-' * 100)

same_count = 0
diff_count = 0

for row in rows:
    diff = row['bef_score'] - row['adv_score']
    rank_change = '' if row['adv_rank'] == row['bef_rank'] else f"{row['adv_rank']}→{row['bef_rank']}"

    if abs(diff) < 0.001:
        same_count += 1
    else:
        diff_count += 1

    print(f"{row['id']:<8} {row['race_date']:<12} {row['race_number']:<3} {row['pit_number']:<4} "
          f"{row['adv_score']:>11.3f} {row['bef_score']:>11.3f} {diff:>+11.3f} {rank_change}")

print(f"\n同一スコア: {same_count}件")
print(f"差分あり: {diff_count}件")

conn.close()
