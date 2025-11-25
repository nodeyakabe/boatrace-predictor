import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/boatrace_readonly.db')
cursor = conn.cursor()

# 2025年10月のデータを確認
cursor.execute("""
    SELECT
        race_date,
        COUNT(*) as race_count,
        SUM(CASE WHEN EXISTS (
            SELECT 1 FROM results r WHERE r.race_id = races.id LIMIT 1
        ) THEN 1 ELSE 0 END) as completed_count
    FROM races
    WHERE race_date BETWEEN '2025-10-01' AND '2025-10-30'
    GROUP BY race_date
    ORDER BY race_date
""")

rows = cursor.fetchall()

print("=" * 80)
print("2025年10月 データ収集状況")
print("=" * 80)

total_races = 0
total_completed = 0

for row in rows:
    date = row[0]
    race_count = row[1]
    completed = row[2]
    total_races += race_count
    total_completed += completed

    progress = (completed / race_count * 100) if race_count > 0 else 0
    print(f"{date}: {completed:3d}/{race_count:3d}レース ({progress:5.1f}%)")

print("-" * 80)
print(f"合計: {total_completed}/{total_races}レース")
print(f"進捗率: {total_completed/total_races*100:.1f}%")

# 対象期間の日数
start_date = datetime.strptime('2025-10-01', '%Y-%m-%d')
end_date = datetime.strptime('2025-10-30', '%Y-%m-%d')
total_days = (end_date - start_date).days + 1

collected_days = len(rows)
print(f"収集済み日数: {collected_days}/{total_days}日")

# 1日あたり平均レース数から推定
if collected_days > 0:
    avg_races_per_day = total_races / collected_days
    estimated_total = avg_races_per_day * total_days
    print(f"\n推定総レース数: {estimated_total:.0f}レース")
    print(f"推定完了率: {total_races/estimated_total*100:.1f}%")

    # 残り時間の推定
    if total_completed > 0:
        # 最初のレースIDと最後のレースIDを取得して経過時間を推定
        cursor.execute("""
            SELECT MIN(id), MAX(id)
            FROM races
            WHERE race_date BETWEEN '2025-10-01' AND '2025-10-30'
        """)
        min_id, max_id = cursor.fetchone()

        if min_id and max_id:
            races_collected = max_id - min_id + 1
            remaining_estimated = estimated_total - total_races
            print(f"\n残りレース数（推定）: {remaining_estimated:.0f}レース")

conn.close()

print("=" * 80)
