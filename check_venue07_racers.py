"""
会場07の1号艇選手データを確認
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

# 会場07の1号艇選手情報
cursor.execute("""
    SELECT
        r.race_number,
        e.racer_name,
        e.win_rate,
        e.second_rate,
        e.third_rate,
        rp.total_score
    FROM entries e
    JOIN races r ON e.race_id = r.id
    JOIN race_predictions rp ON e.race_id = rp.race_id AND e.pit_number = rp.pit_number
    WHERE r.venue_code = '07'
      AND r.race_date = '2025-11-19'
      AND e.pit_number = 1
      AND rp.rank_prediction = 1
    ORDER BY r.race_number
    LIMIT 12
""")

print('会場07 - 1号艇選手データ:')
print('=' * 80)
print('レース | 選手名     | 勝率  | 2連対率 | 3連対率 | 予測スコア')
print('-' * 80)

for race_num, name, win_rate, place2, place3, score in cursor.fetchall():
    wr = f"{win_rate:.2f}" if win_rate else "N/A"
    p2 = f"{place2:.1f}%" if place2 else "N/A"
    p3 = f"{place3:.1f}%" if place3 else "N/A"
    print(f'{int(race_num):2d}R    | {name:10s} | {wr:5s} | {p2:6s}  | {p3:6s}  | {score:5.1f}')

# 全会場の1号艇選手の平均勝率を計算
print('\n' + '=' * 80)
print('比較: 全会場の1号艇選手平均')
print('=' * 80)

cursor.execute("""
    SELECT
        r.venue_code,
        AVG(e.win_rate) as avg_win_rate,
        COUNT(*) as count
    FROM entries e
    JOIN races r ON e.race_id = r.id
    WHERE r.race_date = '2025-11-19'
      AND e.pit_number = 1
      AND e.win_rate IS NOT NULL
    GROUP BY r.venue_code
    ORDER BY avg_win_rate DESC
""")

print('会場 | 平均勝率 | レース数')
print('-' * 40)
for venue, avg_wr, count in cursor.fetchall():
    print(f'{int(venue):02d}   | {avg_wr:6.3f}  | {count:2d}')

conn.close()
