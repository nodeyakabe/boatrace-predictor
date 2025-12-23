#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
race_id=133452の詳細デバッグ
"""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

# モジュールを強制的にリロード
import importlib
if 'src.analysis.racer_analyzer' in sys.modules:
    del sys.modules['src.analysis.racer_analyzer']
if 'src.analysis.race_predictor' in sys.modules:
    del sys.modules['src.analysis.race_predictor']

from scripts.fast_prediction_generator import FastPredictionGenerator
import sqlite3

print("="*80)
print("race_id=133452 詳細デバッグ")
print("="*80)

# advance予測を生成
gen = FastPredictionGenerator('advance')

# データロード
if gen.predictor.batch_loader:
    print("\n日次データロード中...")
    gen.predictor.batch_loader.load_daily_data('2024-01-01')
    print("データロード完了")

# race_id=133452のエントリー情報を取得
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT
        e.pit_number,
        e.racer_number,
        e.racer_name,
        rd.actual_course
    FROM entries e
    LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    WHERE e.race_id = 133452
    ORDER BY e.pit_number
""")

print("\nエントリー情報:")
for row in cursor.fetchall():
    pit, racer_num, name, actual = row
    print(f"  {pit}号艇: {racer_num} {name} (実際のコース: {actual})")

conn.close()

# RacerAnalyzerを直接テスト
from src.analysis.racer_analyzer import RacerAnalyzer

analyzer = gen.predictor.racer_analyzer
venue_code = '01'  # 桐生

print("\n" + "="*80)
print("各選手のcourse_statsをチェック")
print("="*80)

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT
        e.pit_number,
        e.racer_number,
        rd.actual_course
    FROM entries e
    LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    WHERE e.race_id = 133452
    ORDER BY e.pit_number
""")

for row in cursor.fetchall():
    pit, racer_num, actual_course = row

    # 実際のコースまたは枠番を使用
    course = actual_course if actual_course else pit

    print(f"\n{pit}号艇 (racer={racer_num}, course={course}):")

    # course_statsを取得
    course_stats = analyzer.get_racer_course_stats(racer_num, course)

    print(f"  course_stats type: {type(course_stats)}")
    print(f"  course_stats value: {course_stats}")

    if course_stats is None:
        print(f"  ❌ course_statsがNone!")
    elif 'total_races' not in course_stats:
        print(f"  ❌ 'total_races'キーがない!")
        print(f"  利用可能なキー: {list(course_stats.keys())}")
    else:
        print(f"  ✅ total_races: {course_stats['total_races']}")

conn.close()

print("\n" + "="*80)
print("デバッグ完了")
print("="*80)
