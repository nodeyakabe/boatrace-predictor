"""データベーススキーマを詳細確認（ASCII版）"""
import sys
sys.path.append('src')
import sqlite3
from config.settings import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

print("="*70)
print("Database Schema Check")
print("="*70)

# race_details に finish_position と kimarite があるか確認
print("\nrace_details columns:")
cursor.execute("PRAGMA table_info(race_details)")
rd_columns = {col[1]: col[2] for col in cursor.fetchall()}
for name, type_ in rd_columns.items():
    print(f"  {name:25s} {type_:15s}")

has_finish = 'finish_position' in rd_columns
has_kimarite_rd = 'kimarite' in rd_columns

print(f"\n[CHECK] finish_position in race_details: {has_finish}")
print(f"[CHECK] kimarite in race_details: {has_kimarite_rd}")

if has_finish:
    cursor.execute("SELECT COUNT(*) FROM race_details WHERE finish_position IS NOT NULL")
    count = cursor.fetchone()[0]
    print(f"  -> finish_position data count: {count:,}")

if has_kimarite_rd:
    cursor.execute("SELECT COUNT(*) FROM race_details WHERE kimarite IS NOT NULL")
    count = cursor.fetchone()[0]
    print(f"  -> kimarite data count: {count:,}")

# results に kimarite があるか確認
print("\n" + "-"*70)
print("results columns:")
cursor.execute("PRAGMA table_info(results)")
results_columns = {col[1]: col[2] for col in cursor.fetchall()}
for name, type_ in results_columns.items():
    print(f"  {name:25s} {type_:15s}")

has_kimarite_r = 'kimarite' in results_columns

print(f"\n[CHECK] kimarite in results: {has_kimarite_r}")

if has_kimarite_r:
    cursor.execute("SELECT COUNT(*) FROM results WHERE kimarite IS NOT NULL")
    count = cursor.fetchone()[0]
    print(f"  -> kimarite data count: {count:,}")

    # 決まり手の種類を確認
    cursor.execute("SELECT DISTINCT kimarite FROM results WHERE kimarite IS NOT NULL LIMIT 10")
    kimarite_types = [row[0] for row in cursor.fetchall()]
    print(f"  -> kimarite types (sample): {', '.join(kimarite_types)}")

# race_results テーブルの確認
print("\n" + "-"*70)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='race_results'")
race_results_exists = cursor.fetchone() is not None

print(f"[CHECK] race_results table exists: {race_results_exists}")

if race_results_exists:
    print("\nrace_results columns:")
    cursor.execute("PRAGMA table_info(race_results)")
    rr_columns = {col[1]: col[2] for col in cursor.fetchall()}
    for name, type_ in rr_columns.items():
        print(f"  {name:25s} {type_:15s}")

    cursor.execute("SELECT COUNT(*) FROM race_results")
    count = cursor.fetchone()[0]
    print(f"  -> record count: {count:,}")

# データ整合性チェック
print("\n" + "="*70)
print("Data Consistency Check")
print("="*70)

# race_details と results の pit_number 整合性
cursor.execute("""
    SELECT COUNT(*)
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    LEFT JOIN results r2 ON r.id = r2.race_id AND rd.pit_number = r2.pit_number
    WHERE r2.rank IS NULL AND r.race_date >= '2024-01-01'
""")
missing_results = cursor.fetchone()[0]
print(f"\n[CHECK] race_details without results (2024+): {missing_results:,}")

# actual_course のデータ充足率
cursor.execute("SELECT COUNT(*) FROM race_details WHERE actual_course IS NOT NULL")
has_course = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM race_details")
total_rd = cursor.fetchone()[0]
course_rate = has_course / total_rd * 100 if total_rd > 0 else 0
print(f"[CHECK] actual_course fill rate: {course_rate:.1f}% ({has_course:,}/{total_rd:,})")

# rank のデータ充足率
cursor.execute("SELECT COUNT(*) FROM results WHERE rank IS NOT NULL AND rank != ''")
has_rank = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM results")
total_r = cursor.fetchone()[0]
rank_rate = has_rank / total_r * 100 if total_r > 0 else 0
print(f"[CHECK] rank fill rate: {rank_rate:.1f}% ({has_rank:,}/{total_r:,})")

# kimarite のデータ充足率（1着のみ）
cursor.execute("""
    SELECT COUNT(*)
    FROM results
    WHERE rank = '1' AND kimarite IS NOT NULL AND kimarite != ''
""")
has_kimarite = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM results WHERE rank = '1'")
total_first = cursor.fetchone()[0]
kimarite_rate = has_kimarite / total_first * 100 if total_first > 0 else 0
print(f"[CHECK] kimarite fill rate (1st place): {kimarite_rate:.1f}% ({has_kimarite:,}/{total_first:,})")

conn.close()

print("\n" + "="*70)
print("Check Complete")
print("="*70)
