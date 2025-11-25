"""
会場07の予測詳細を確認
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

# 会場07の全レース予測を確認（最初の5レース）
cursor.execute("""
    SELECT
        r.race_number,
        rp.pit_number,
        rp.total_score,
        rp.rank_prediction,
        rp.confidence
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    WHERE r.venue_code = '07'
      AND r.race_date = '2025-11-19'
    ORDER BY r.race_number, rp.rank_prediction
    LIMIT 36
""")

print('会場07 - 予測詳細（最初の6レース）:')
print('=' * 60)

results = cursor.fetchall()
current_race = None

for race_num, pit, score, rank, conf in results:
    if race_num != current_race:
        current_race = race_num
        print(f'\n{int(race_num):2d}R:')
        print('  順位 | 枠    | スコア | 信頼度')
        print('  ' + '-' * 40)
    print(f'  {rank}位  | {pit}号艇 | {score:5.1f} | {conf}')

conn.close()
