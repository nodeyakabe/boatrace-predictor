"""
クイック状況確認 - 改善版スクリプトの動作状況
"""

import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print("="*80)
print("Quick Status Check - Improved Scraper")
print("="*80)

# 最近10分間の活動
cursor.execute("""
    SELECT COUNT(*), MIN(created_at), MAX(created_at)
    FROM race_details
    WHERE created_at > datetime('now', '-10 minutes')
""")
count, min_time, max_time = cursor.fetchone()
print(f"\nLast 10 minutes:")
print(f"  Records created: {count}")
print(f"  Time range: {min_time} to {max_time}")

# Flying/Late検出
cursor.execute("SELECT COUNT(*) FROM race_details WHERE st_time = -0.01")
flying = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM race_details WHERE st_time = -0.02")
late = cursor.fetchone()[0]

print(f"\nF/L Detection (all time):")
print(f"  Flying (F): {flying}")
print(f"  Late (L): {late}")

if flying > 0 or late > 0:
    print("  [OK] Improved scraper is WORKING!")
else:
    print("  [INFO] No F/L detected yet")

# 最新5件
cursor.execute("""
    SELECT r.venue_code, r.race_date, r.race_number, rd.pit_number, rd.st_time, rd.created_at
    FROM race_details rd
    INNER JOIN races r ON rd.race_id = r.id
    ORDER BY rd.created_at DESC
    LIMIT 5
""")

print(f"\nLatest 5 records:")
for row in cursor.fetchall():
    venue, date, race, pit, st, created = row
    st_status = ""
    if st == -0.01:
        st_status = " [F]"
    elif st == -0.02:
        st_status = " [L]"
    st_str = f"{st:.2f}" if st else "None"
    print(f"  {venue} {date} R{race} Pit{pit}: ST={st_str}{st_status} ({created})")

# 進捗状況
cursor.execute("""
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
      AND (
        SELECT COUNT(*)
        FROM race_details rd
        WHERE rd.race_id = r.id
          AND rd.st_time IS NOT NULL
      ) = 6
""")
complete = cursor.fetchone()[0]

cursor.execute("""
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
""")
total = cursor.fetchone()[0]

print(f"\nProgress (2015-2021):")
print(f"  Complete (6/6 ST): {complete:,} / {total:,} ({complete/total*100:.2f}%)")
print(f"  Remaining: {total - complete:,}")

# 収集速度の推定
if count > 0:
    # 10分間でcountレース分のデータ
    # 1レースあたり6pit = count * 6 records
    races_per_10min = count / 6
    races_per_hour = races_per_10min * 6
    remaining = total - complete
    hours_remaining = remaining / races_per_hour if races_per_hour > 0 else 0

    print(f"\nSpeed estimate:")
    print(f"  {races_per_hour:.1f} races/hour")
    print(f"  Estimated time remaining: {hours_remaining:.1f} hours ({hours_remaining/24:.1f} days)")

conn.close()

print("\n" + "="*80)
