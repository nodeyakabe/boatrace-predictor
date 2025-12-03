"""最終状況確認と完了予測"""
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect("data/boatrace.db")
cursor = conn.cursor()

# 総レース数
cursor.execute("SELECT COUNT(*) FROM races")
total_races = cursor.fetchone()[0]

# race_detailsの状況
cursor.execute("""
    SELECT COUNT(DISTINCT race_id)
    FROM race_details
    WHERE actual_course IS NOT NULL
""")
races_with_course = cursor.fetchone()[0]

conn.close()

print("=" * 80)
print("レース詳細補完 - 最新状況")
print("=" * 80)
print(f"総レース数: {total_races:,}")
print(f"実際のコースデータがあるレース: {races_with_course:,} ({races_with_course/total_races*100:.1f}%)")
print()

# 欠損数
missing = total_races - races_with_course
print(f"残り欠損数: {missing:,}件")
print()

# 処理速度（ログから読み取った値）
processing_rate = 1.6  # 件/秒

# 完了予測
remaining_seconds = missing / processing_rate
remaining_minutes = remaining_seconds / 60
remaining_hours = remaining_minutes / 60

print(f"処理速度: {processing_rate}件/秒")
print(f"予想残り時間: {remaining_minutes:.0f}分 ({remaining_hours:.1f}時間)")
print()

completion_time = datetime.now() + timedelta(seconds=remaining_seconds)
print(f"完了予想時刻: {completion_time.strftime('%Y-%m-%d %H:%M')}")
print(f"完了予想日時: {completion_time.strftime('%m月%d日 %H時%M分')}")
print("=" * 80)
