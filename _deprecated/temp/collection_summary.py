"""データ収集の実績と残対象サマリー"""
import sqlite3

conn = sqlite3.connect("data/boatrace.db")
cursor = conn.cursor()

print("=" * 80)
print("データ収集実績サマリー")
print("=" * 80)
print()

# 総レース数
cursor.execute("SELECT COUNT(*) FROM races")
total_races = cursor.fetchone()[0]
print(f"総レース数: {total_races:,}件")
print()

# 1. 決まり手データ
print("■ 決まり手データ")
cursor.execute("""
    SELECT
        COUNT(CASE WHEN kimarite IS NOT NULL THEN 1 END) as with_data,
        COUNT(CASE WHEN kimarite IS NULL THEN 1 END) as missing
    FROM results
    WHERE rank = '1' AND is_invalid = 0
""")
kimarite_with, kimarite_missing = cursor.fetchone()
print(f"  収集済み: {kimarite_with:,}件")
print(f"  欠損: {kimarite_missing:,}件")
print(f"  充足率: {kimarite_with/(kimarite_with+kimarite_missing)*100:.1f}%")
print()

# 2. 払戻金データ
print("■ 払戻金データ")
cursor.execute("""
    SELECT COUNT(DISTINCT race_id) FROM payouts
""")
payout_with = cursor.fetchone()[0]
payout_missing = total_races - payout_with
print(f"  収集済み: {payout_with:,}件")
print(f"  欠損: {payout_missing:,}件")
print(f"  充足率: {payout_with/total_races*100:.1f}%")
print()

# 3. レース詳細データ（ST時間・実際のコース）
print("■ レース詳細データ（ST時間）")
cursor.execute("""
    SELECT COUNT(DISTINCT race_id)
    FROM race_details
    WHERE st_time IS NOT NULL
""")
st_with = cursor.fetchone()[0]
st_missing = total_races - st_with
print(f"  収集済み: {st_with:,}件")
print(f"  欠損: {st_missing:,}件")
print(f"  充足率: {st_with/total_races*100:.1f}%")
print()

print("■ レース詳細データ（実際のコース）")
cursor.execute("""
    SELECT COUNT(DISTINCT race_id)
    FROM race_details
    WHERE actual_course IS NOT NULL
""")
course_with = cursor.fetchone()[0]
course_missing = total_races - course_with
print(f"  収集済み: {course_with:,}件")
print(f"  欠損: {course_missing:,}件")
print(f"  充足率: {course_with/total_races*100:.1f}%")
print()

# 4. 直前情報データ（テーブルが存在するか確認）
cursor.execute("""
    SELECT name FROM sqlite_master WHERE type='table' AND name='beforeinfo'
""")
has_beforeinfo = cursor.fetchone() is not None

if has_beforeinfo:
    print("■ 直前情報データ（beforeinfo）")
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) FROM beforeinfo
    """)
    beforeinfo_with = cursor.fetchone()[0]
    beforeinfo_missing = total_races - beforeinfo_with
    print(f"  収集済み: {beforeinfo_with:,}件")
    print(f"  欠損: {beforeinfo_missing:,}件")
    print(f"  充足率: {beforeinfo_with/total_races*100:.1f}%")
    print()
else:
    print("■ 直前情報データ（beforeinfo）")
    print("  ※テーブル未作成（データ未収集）")
    print()
    beforeinfo_missing = total_races

# 今回のバッチ収集実績
print("=" * 80)
print("今回のバッチ収集実績（12月2日夜～12月3日）")
print("=" * 80)
print()
print("[完了] 決まり手補完")
print("  - 対象: 8,771件")
print("  - 成功: 8,259件 (94.2%)")
print("  - 処理時間: 129分")
print()
print("[完了] 払戻金補完")
print("  - 対象: 1,221件")
print("  - 成功: 1,221件 (100%)")
print("  - 処理時間: 27.6分")
print()
print("[進行中] レース詳細補完")
print("  - 対象: 40,494件")
print(f"  - 現在進捗: {course_with:,}件収集済み ({course_with/total_races*100:.1f}%)")
print(f"  - 残り: {course_missing:,}件")
print("  - 処理速度: 1.6件/秒")
print("  - 完了予想: 今夜21時頃")
print()

conn.close()

print("=" * 80)
print("残対象データ")
print("=" * 80)
print(f"1. 決まり手: {kimarite_missing:,}件")
print(f"2. 払戻金: {payout_missing:,}件")
print(f"3. レース詳細（実際のコース）: {course_missing:,}件 ← 現在処理中")
print(f"4. 直前情報: {beforeinfo_missing:,}件")
print("=" * 80)
