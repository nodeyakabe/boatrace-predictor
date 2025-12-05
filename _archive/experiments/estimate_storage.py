"""
1年分のデータ容量見積もり
"""
import sqlite3

# 現在のデータ状況
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 現在のレコード数
cursor.execute('SELECT COUNT(*) FROM races')
race_count = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM entries')
entry_count = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM results WHERE is_invalid = 0')
result_count = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(DISTINCT race_date) FROM races')
day_count = cursor.fetchone()[0]

conn.close()

# DBサイズ
import os
db_size = os.path.getsize('data/boatrace.db')
db_size_mb = db_size / 1024 / 1024

print("="*70)
print("データ容量見積もり")
print("="*70)

print(f"\n【現在のデータ】")
print(f"  DBサイズ: {db_size_mb:.2f} MB ({db_size:,} bytes)")
print(f"  レース数: {race_count}")
print(f"  出走表: {entry_count}")
print(f"  結果: {result_count}")
print(f"  日数: {day_count}日")

# 1日あたりの平均
if day_count > 0:
    races_per_day = race_count / day_count
    entries_per_day = entry_count / day_count
    results_per_day = result_count / day_count
    mb_per_day = db_size_mb / day_count

    print(f"\n【1日あたりの平均】")
    print(f"  レース数: {races_per_day:.1f}")
    print(f"  出走表: {entries_per_day:.1f}")
    print(f"  結果: {results_per_day:.1f}")
    print(f"  DBサイズ増加: {mb_per_day:.3f} MB")

    # 1年分の見積もり（365日）
    print(f"\n【1年分の見積もり（365日）】")

    # 1競艇場のみ
    year_races_1 = races_per_day * 365
    year_entries_1 = entries_per_day * 365
    year_results_1 = results_per_day * 365
    year_size_1 = mb_per_day * 365

    print(f"  1競艇場のみ:")
    print(f"    レース数: {year_races_1:,.0f}")
    print(f"    出走表: {year_entries_1:,.0f}")
    print(f"    結果: {year_results_1:,.0f}")
    print(f"    DBサイズ: {year_size_1:.2f} MB")

    # 全24競艇場
    year_size_24 = year_size_1 * 24

    print(f"\n  全24競艇場:")
    print(f"    レース数: {year_races_1 * 24:,.0f}")
    print(f"    出走表: {year_entries_1 * 24:,.0f}")
    print(f"    結果: {year_results_1 * 24:,.0f}")
    print(f"    DBサイズ: {year_size_24:.2f} MB ({year_size_24/1024:.2f} GB)")

    print(f"\n【推奨事項】")
    if year_size_24 < 100:
        print(f"  OK: {year_size_24:.0f}MBは問題なし")
    elif year_size_24 < 1024:
        print(f"  OK: {year_size_24:.0f}MBは許容範囲")
    else:
        print(f"  注意: {year_size_24/1024:.1f}GBになる可能性")

    print(f"\n  - SQLiteの最大DB容量: 140TB（実質無制限）")
    print(f"  - ディスク容量に注意")
    print(f"  - 定期的なVACUUM推奨")

print(f"\n{'='*70}")
