"""
複数日付での的中率検証
会場補正の効果を複数データで確認
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH

print("=" * 80)
print("結果データがある日付の抽出")
print("=" * 80)

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

# 結果データがある日付を取得（レース数が多い順）
cursor.execute("""
    SELECT
        r.race_date,
        COUNT(DISTINCT r.id) as race_count,
        COUNT(DISTINCT r.venue_code) as venue_count
    FROM results res
    JOIN races r ON res.race_id = r.id
    WHERE CAST(res.rank AS INTEGER) = 1
    GROUP BY r.race_date
    HAVING race_count >= 100
    ORDER BY race_count DESC
    LIMIT 20
""")

dates = cursor.fetchall()

print("\n結果データがある日付（レース数100以上、上位20日）:")
print("-" * 80)
print("日付       | レース数 | 会場数")
print("-" * 80)

for date, race_count, venue_count in dates:
    print(f"{date} |   {race_count:3d}   |  {venue_count:2d}")

conn.close()

print("\n" + "=" * 80)
print("推奨テスト日付")
print("=" * 80)

if len(dates) >= 5:
    test_dates = [dates[i][0] for i in range(5)]
    print("\n以下の5日分でテストすることを推奨:")
    for i, date in enumerate(test_dates, 1):
        race_count = dates[i-1][1]
        venue_count = dates[i-1][2]
        print(f"  {i}. {date} ({race_count}レース, {venue_count}会場)")
else:
    print("\n十分なデータがある日付が5日未満です")

print("\n" + "=" * 80)
print("完了")
print("=" * 80)
