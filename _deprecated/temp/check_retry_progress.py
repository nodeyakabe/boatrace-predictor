"""
再試行の進捗確認スクリプト
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import sqlite3
from datetime import datetime

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print('=' * 80)
print(f'2025年レース詳細 再試行進捗確認')
print(f'確認時刻: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 80)
print()

# レース詳細の現在の充足率
cursor.execute('''
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN EXISTS (
            SELECT 1 FROM race_details rd
            WHERE rd.race_id = r.id
            AND rd.st_time IS NOT NULL
            AND rd.actual_course IS NOT NULL
        ) THEN 1 END) as complete
    FROM races r
    WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
''')

total, complete = cursor.fetchone()
missing = total - complete
progress_pct = (complete / total * 100) if total > 0 else 0

print(f'2025年レース詳細:')
print(f'  総数: {total:,}件')
print(f'  完了: {complete:,}件')
print(f'  残り: {missing:,}件')
print(f'  充足率: {progress_pct:.1f}%')
print()

# 前回との比較（前回は15,622件完了）
previous_complete = 15622
improvement = complete - previous_complete

if improvement > 0:
    print(f'✅ 改善: +{improvement:,}件 ({previous_complete:,} → {complete:,})')
elif improvement < 0:
    print(f'⚠️ 減少: {improvement:,}件（何かエラー？）')
else:
    print('変化なし（まだ処理中の可能性）')

print()

# 残りの詳細
if missing > 0:
    cursor.execute('''
        SELECT
            COUNT(CASE WHEN EXISTS (
                SELECT 1 FROM results res WHERE res.race_id = r.id
            ) THEN 1 END) as has_results
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
          AND NOT EXISTS (
              SELECT 1 FROM race_details rd
              WHERE rd.race_id = r.id
              AND rd.st_time IS NOT NULL
              AND rd.actual_course IS NOT NULL
          )
    ''')
    has_results = cursor.fetchone()[0]

    print(f'残り{missing:,}件の内訳:')
    print(f'  結果データあり（再試行可能）: {has_results:,}件')
    print(f'  結果データなし（中止レース）: {missing - has_results:,}件')

conn.close()
