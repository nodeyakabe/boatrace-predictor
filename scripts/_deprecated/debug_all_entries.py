#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys, os
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from scripts.fast_prediction_generator import FastPredictionGenerator
import sqlite3

gen = FastPredictionGenerator('advance')
analyzer = gen.predictor.racer_analyzer

if analyzer.batch_loader:
    analyzer.batch_loader.load_daily_data('2024-01-01')

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT e.pit_number, e.racer_number, rd.actual_course
    FROM entries e
    LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    WHERE e.race_id = 134270
    ORDER BY e.pit_number
""")

print("race_id=134270 全エントリーチェック")
print("="*80)

for row in cursor.fetchall():
    pit, racer_num, actual_course = row
    course = actual_course if actual_course else pit

    try:
        course_stats = analyzer.get_racer_course_stats(racer_num, course)

        if course_stats is None:
            print(f"{pit}号艇 (racer={racer_num}, course={course}): ❌ None")
        elif 'total_races' not in course_stats:
            print(f"{pit}号艇 (racer={racer_num}, course={course}): ❌ KeyError - keys={list(course_stats.keys())}")
        else:
            print(f"{pit}号艇 (racer={racer_num}, course={course}): ✅ total_races={course_stats['total_races']}")
    except Exception as e:
        print(f"{pit}号艇 (racer={racer_num}, course={course}): ❌ Exception: {e}")

conn.close()
