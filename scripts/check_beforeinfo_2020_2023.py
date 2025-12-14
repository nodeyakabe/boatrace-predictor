#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2020-2023年の直前情報データ可用性チェック
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
db_path = ROOT / "data" / "boatrace.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 100)
print("2020-2023年の直前情報データ可用性チェック")
print("=" * 100)
print()

# 年別の直前情報データ可用性
for year in [2020, 2021, 2022, 2023]:
    cursor.execute(f"""
        SELECT
            COUNT(DISTINCT r.id) as total_races,
            COUNT(DISTINCT CASE WHEN ed.id IS NOT NULL THEN r.id END) as has_exhibition,
            COUNT(DISTINCT CASE WHEN ac.race_id IS NOT NULL THEN r.id END) as has_approach,
            COUNT(DISTINCT CASE WHEN rc.id IS NOT NULL THEN r.id END) as has_weather
        FROM races r
        LEFT JOIN exhibition_data ed ON r.id = ed.race_id
        LEFT JOIN actual_courses ac ON r.id = ac.race_id
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date >= '{year}-01-01' AND r.race_date < '{year + 1}-01-01'
    """)

    total, exhibition, approach, weather = cursor.fetchone()

    print(f"{year}年:")
    print(f"  総レース数: {total:,}件")
    print(f"  展示データ: {exhibition:,}件 ({exhibition/total*100:.1f}%)")
    print(f"  進入コース: {approach:,}件 ({approach/total*100:.1f}%)")
    print(f"  天候情報: {weather:,}件 ({weather/total*100:.1f}%)")
    print()

# 全体サマリー
cursor.execute("""
    SELECT
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT CASE WHEN ed.id IS NOT NULL THEN r.id END) as has_exhibition,
        COUNT(DISTINCT CASE WHEN ac.race_id IS NOT NULL THEN r.id END) as has_approach,
        COUNT(DISTINCT CASE WHEN rc.id IS NOT NULL THEN r.id END) as has_weather
    FROM races r
    LEFT JOIN exhibition_data ed ON r.id = ed.race_id
    LEFT JOIN actual_courses ac ON r.id = ac.race_id
    LEFT JOIN race_conditions rc ON r.id = rc.race_id
    WHERE r.race_date >= '2020-01-01' AND r.race_date < '2024-01-01'
""")

total, exhibition, approach, weather = cursor.fetchone()

print("=" * 100)
print("全体サマリー（2020-2023年）")
print("=" * 100)
print(f"総レース数: {total:,}件")
print()
print(f"展示データ: {exhibition:,}件 ({exhibition/total*100:.1f}%)")
print(f"進入コース: {approach:,}件 ({approach/total*100:.1f}%)")
print(f"天候情報: {weather:,}件 ({weather/total*100:.1f}%)")
print()

# 結論
print("=" * 100)
print("結論")
print("=" * 100)

if exhibition == 0 and approach == 0:
    print("✗ 展示データ・進入コースが存在しないため、before予測は生成不要")
    print("  → advance予測のみで十分")
elif exhibition < total * 0.1 and approach < total * 0.1:
    print("△ 直前情報が10%未満のため、before予測の効果は限定的")
    print("  → advance予測を優先、before予測は将来的に検討")
else:
    print("○ 直前情報が存在するため、before予測も生成すべき")
    print(f"  → advance予測に加えて、before予測も生成推奨")

conn.close()
print()
print("=" * 100)
