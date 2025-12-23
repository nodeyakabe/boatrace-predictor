"""2025年データの現状確認スクリプト"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect("data/boatrace.db")
cursor = conn.cursor()

print("=" * 80)
print("2025年データの現状確認")
print("=" * 80)
print()

# 2025年の総レース数
cursor.execute("""
    SELECT COUNT(*) FROM races
    WHERE race_date >= '2025-01-01' AND race_date < '2026-01-01'
""")
total_races_2025 = cursor.fetchone()[0]
print(f"2025年 総レース数: {total_races_2025:,}件")
print()

if total_races_2025 == 0:
    print("2025年のデータが存在しません。")
    conn.close()
    exit()

# 1. 決まり手データ（results.kimarite）
print("■ 1. 決まり手データ（results.kimarite）")
cursor.execute("""
    SELECT
        COUNT(CASE WHEN res.kimarite IS NOT NULL THEN 1 END) as with_kimarite,
        COUNT(CASE WHEN res.kimarite IS NULL THEN 1 END) as missing_kimarite
    FROM races r
    JOIN results res ON r.id = res.race_id
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
      AND res.rank = '1'
      AND res.is_invalid = 0
""")
kimarite_with, kimarite_missing = cursor.fetchone()
print(f"  収集済み: {kimarite_with:,}件")
print(f"  欠損: {kimarite_missing:,}件")
if (kimarite_with + kimarite_missing) > 0:
    print(f"  充足率: {kimarite_with/(kimarite_with+kimarite_missing)*100:.1f}%")
print()

# 2. 払戻金データ（payouts）
print("■ 2. 払戻金データ（payouts）")
cursor.execute("""
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
      AND EXISTS (
          SELECT 1 FROM payouts p WHERE p.race_id = r.id
      )
""")
payout_with = cursor.fetchone()[0]
payout_missing = total_races_2025 - payout_with
print(f"  収集済み: {payout_with:,}件")
print(f"  欠損: {payout_missing:,}件")
if total_races_2025 > 0:
    print(f"  充足率: {payout_with/total_races_2025*100:.1f}%")
print()

# 3. レース詳細データ - ST時間
print("■ 3. レース詳細データ - ST時間（race_details.st_time）")
cursor.execute("""
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
      AND EXISTS (
          SELECT 1 FROM race_details rd
          WHERE rd.race_id = r.id AND rd.st_time IS NOT NULL
      )
""")
st_with = cursor.fetchone()[0]
st_missing = total_races_2025 - st_with
print(f"  収集済み: {st_with:,}件")
print(f"  欠損: {st_missing:,}件")
if total_races_2025 > 0:
    print(f"  充足率: {st_with/total_races_2025*100:.1f}%")
print()

# 4. レース詳細データ - 実際のコース
print("■ 4. レース詳細データ - 実際のコース（race_details.actual_course）")
cursor.execute("""
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
      AND EXISTS (
          SELECT 1 FROM race_details rd
          WHERE rd.race_id = r.id AND rd.actual_course IS NOT NULL
      )
""")
course_with = cursor.fetchone()[0]
course_missing = total_races_2025 - course_with
print(f"  収集済み: {course_with:,}件")
print(f"  欠損: {course_missing:,}件")
if total_races_2025 > 0:
    print(f"  充足率: {course_with/total_races_2025*100:.1f}%")
print()

# 5. 直前情報データ（beforeinfo）
cursor.execute("""
    SELECT name FROM sqlite_master WHERE type='table' AND name='beforeinfo'
""")
has_beforeinfo = cursor.fetchone() is not None

if has_beforeinfo:
    print("■ 5. 直前情報データ（beforeinfo）")
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
          AND EXISTS (
              SELECT 1 FROM beforeinfo b WHERE b.race_id = r.id
          )
    """)
    beforeinfo_with = cursor.fetchone()[0]
    beforeinfo_missing = total_races_2025 - beforeinfo_with
    print(f"  収集済み: {beforeinfo_with:,}件")
    print(f"  欠損: {beforeinfo_missing:,}件")
    if total_races_2025 > 0:
        print(f"  充足率: {beforeinfo_with/total_races_2025*100:.1f}%")
    print()
else:
    print("■ 5. 直前情報データ（beforeinfo）")
    print("  ※テーブル未作成（データ未収集）")
    beforeinfo_missing = total_races_2025
    print()

# サマリー
print("=" * 80)
print("収集が必要なデータ（2025年）")
print("=" * 80)

needs_collection = []

if kimarite_missing > 0:
    needs_collection.append(f"1. 決まり手: {kimarite_missing:,}件")

if payout_missing > 0:
    needs_collection.append(f"2. 払戻金: {payout_missing:,}件")

if st_missing > 0:
    needs_collection.append(f"3. ST時間: {st_missing:,}件")

if course_missing > 0:
    needs_collection.append(f"4. 実際のコース: {course_missing:,}件")

if beforeinfo_missing > 0:
    needs_collection.append(f"5. 直前情報: {beforeinfo_missing:,}件")

if needs_collection:
    for item in needs_collection:
        print(item)
else:
    print("全データ収集完了！")

print("=" * 80)

# ST timeとactual_courseが両方欠けているレース数
cursor.execute("""
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
      AND EXISTS (
          SELECT 1 FROM race_details rd
          WHERE rd.race_id = r.id
          AND (rd.st_time IS NULL OR rd.actual_course IS NULL)
      )
""")
missing_details = cursor.fetchone()[0]

print()
print("【レース詳細補完の詳細】")
print(f"ST時間 または 実際のコース が欠けているレース: {missing_details:,}件")

# ST時間のみ欠けている
cursor.execute("""
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
      AND EXISTS (
          SELECT 1 FROM race_details rd
          WHERE rd.race_id = r.id
          AND rd.st_time IS NULL
          AND rd.actual_course IS NOT NULL
      )
""")
missing_st_only = cursor.fetchone()[0]

# actual_courseのみ欠けている
cursor.execute("""
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
      AND EXISTS (
          SELECT 1 FROM race_details rd
          WHERE rd.race_id = r.id
          AND rd.st_time IS NOT NULL
          AND rd.actual_course IS NULL
      )
""")
missing_course_only = cursor.fetchone()[0]

# 両方欠けている
cursor.execute("""
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
      AND EXISTS (
          SELECT 1 FROM race_details rd
          WHERE rd.race_id = r.id
          AND rd.st_time IS NULL
          AND rd.actual_course IS NULL
      )
""")
missing_both = cursor.fetchone()[0]

print(f"  - ST時間のみ欠損: {missing_st_only:,}件")
print(f"  - 実際のコースのみ欠損: {missing_course_only:,}件")
print(f"  - 両方欠損: {missing_both:,}件")

conn.close()

print()
print("=" * 80)
print("推奨収集順序")
print("=" * 80)
print("1. レース詳細（ST時間 & 実際のコース）: 軽量版スクリプト使用")
print("   → python 補完_レース詳細データ_軽量版.py --start-date 2025-01-01 --end-date 2025-12-31")
if kimarite_missing > 0:
    print("2. 決まり手: 決まり手補完スクリプト使用")
    print("   → python 補完_決まり手データ_改善版.py --start-date 2025-01-01 --end-date 2025-12-31")
if payout_missing > 0:
    print("3. 払戻金: 払戻金補完スクリプト使用")
print("=" * 80)
