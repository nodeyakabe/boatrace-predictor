"""
夜間データ収集計画スクリプト

現在の収集状況を確認し、夜間に実行すべき収集タスクを提案します。
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from datetime import datetime

print("=" * 80)
print("夜間データ収集計画")
print(f"確認時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
print()

conn = sqlite3.connect("data/boatrace.db")
cursor = conn.cursor()

# 1. 2025年データの状況確認
print("【2025年データ収集状況】")
print("-" * 80)

cursor.execute("""
    SELECT COUNT(*) FROM races
    WHERE race_date >= '2025-01-01' AND race_date < '2026-01-01'
""")
total_races_2025 = cursor.fetchone()[0]
print(f"2025年 総レース数: {total_races_2025:,}件")
print()

# 決まり手
cursor.execute("""
    SELECT COUNT(*)
    FROM races r
    JOIN results res ON r.id = res.race_id
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
      AND res.rank = '1'
      AND res.is_invalid = 0
      AND res.kimarite IS NULL
""")
kimarite_missing_2025 = cursor.fetchone()[0]

# 払戻金
cursor.execute("""
    SELECT COUNT(*)
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
      AND NOT EXISTS (
          SELECT 1 FROM payouts p WHERE p.race_id = r.id
      )
""")
payout_missing_2025 = cursor.fetchone()[0]

# レース詳細（ST time & actual_course）
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
details_missing_2025 = cursor.fetchone()[0]

# 直前情報（展示タイムで確認）
cursor.execute("""
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
      AND NOT EXISTS (
          SELECT 1 FROM race_details rd
          WHERE rd.race_id = r.id
          AND rd.exhibition_time IS NOT NULL
      )
""")
beforeinfo_missing_2025 = cursor.fetchone()[0]

print("2025年データ不足状況:")
print(f"  決まり手: {kimarite_missing_2025:,}件")
print(f"  払戻金: {payout_missing_2025:,}件")
print(f"  レース詳細: {details_missing_2025:,}件")
print(f"  直前情報: {beforeinfo_missing_2025:,}件")
print()

# 2. 全期間データの状況確認
print("【全期間データ収集状況】")
print("-" * 80)

cursor.execute("SELECT COUNT(*) FROM races")
total_races = cursor.fetchone()[0]
print(f"全期間 総レース数: {total_races:,}件")
print()

# 決まり手
cursor.execute("""
    SELECT COUNT(*)
    FROM races r
    JOIN results res ON r.id = res.race_id
    WHERE res.rank = '1'
      AND res.is_invalid = 0
      AND res.kimarite IS NULL
""")
kimarite_missing_all = cursor.fetchone()[0]

# 払戻金
cursor.execute("""
    SELECT COUNT(*)
    FROM races r
    WHERE NOT EXISTS (
        SELECT 1 FROM payouts p WHERE p.race_id = r.id
    )
""")
payout_missing_all = cursor.fetchone()[0]

# レース詳細
cursor.execute("""
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    WHERE EXISTS (
        SELECT 1 FROM race_details rd
        WHERE rd.race_id = r.id
        AND (rd.st_time IS NULL OR rd.actual_course IS NULL)
    )
""")
details_missing_all = cursor.fetchone()[0]

print("全期間データ不足状況:")
print(f"  決まり手: {kimarite_missing_all:,}件")
print(f"  払戻金: {payout_missing_all:,}件")
print(f"  レース詳細: {details_missing_all:,}件")
print()

conn.close()

# 3. 夜間収集計画の提案
print("=" * 80)
print("【夜間収集計画の提案】")
print("=" * 80)
print()

tasks = []

if details_missing_2025 > 0:
    tasks.append({
        'priority': 1,
        'name': '2025年レース詳細補完',
        'count': details_missing_2025,
        'command': 'python 補完_レース詳細データ_軽量版.py --start-date 2025-01-01 --end-date 2025-12-31',
        'estimated_hours': details_missing_2025 / (2.5 * 3600)  # 2.5件/秒想定
    })

if kimarite_missing_2025 > 0:
    tasks.append({
        'priority': 2,
        'name': '2025年決まり手補完',
        'count': kimarite_missing_2025,
        'command': 'python 補完_決まり手データ_改善版.py --start-date 2025-01-01 --end-date 2025-12-31',
        'estimated_hours': kimarite_missing_2025 / (10 * 3600)  # 10件/秒想定
    })

if payout_missing_2025 > 0:
    tasks.append({
        'priority': 3,
        'name': '2025年払戻金補完',
        'count': payout_missing_2025,
        'command': 'python scripts/bulk_missing_data_fetch_12h.py --start-date 2025-01-01 --end-date 2025-12-31',
        'estimated_hours': payout_missing_2025 / (5 * 3600)  # 5件/秒想定
    })

if beforeinfo_missing_2025 > 0:
    tasks.append({
        'priority': 4,
        'name': '2025年直前情報補完',
        'count': beforeinfo_missing_2025,
        'command': 'python scripts/bulk_missing_data_fetch_12h.py --start-date 2025-01-01 --end-date 2025-12-31',
        'estimated_hours': beforeinfo_missing_2025 / (2 * 3600)  # 2件/秒想定
    })

if tasks:
    print("優先順位順のタスク:")
    print()
    for i, task in enumerate(sorted(tasks, key=lambda x: x['priority']), 1):
        print(f"{i}. {task['name']}")
        print(f"   対象: {task['count']:,}件")
        print(f"   推定時間: {task['estimated_hours']:.1f}時間")
        print(f"   コマンド: {task['command']}")
        print()

    total_hours = sum(t['estimated_hours'] for t in tasks)
    print(f"合計推定時間: {total_hours:.1f}時間")
    print()

    print("【推奨実行順序】")
    print("-" * 80)
    print("1. 現在実行中のレース詳細補完が完了するまで待つ")
    print("2. 完了後、残りのタスクを順次実行")
    print()
    print("【夜間自動実行の設定方法】")
    print("-" * 80)
    print("以下のコマンドをバックグラウンドで順次実行:")
    for i, task in enumerate(sorted(tasks, key=lambda x: x['priority']), 1):
        print(f"{i}. {task['command']}")
else:
    print("✅ 2025年のデータ収集は完了しています！")
    print()
    if kimarite_missing_all > 0 or payout_missing_all > 0 or details_missing_all > 0:
        print("全期間では以下のデータが不足しています:")
        if kimarite_missing_all > 0:
            print(f"  - 決まり手: {kimarite_missing_all:,}件")
        if payout_missing_all > 0:
            print(f"  - 払戻金: {payout_missing_all:,}件")
        if details_missing_all > 0:
            print(f"  - レース詳細: {details_missing_all:,}件")

print()
print("=" * 80)
