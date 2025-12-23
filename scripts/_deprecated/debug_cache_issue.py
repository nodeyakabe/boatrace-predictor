#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
キャッシュ問題のデバッグ
"""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from scripts.fast_prediction_generator import FastPredictionGenerator

gen = FastPredictionGenerator('advance')
analyzer = gen.predictor.racer_analyzer

print("="*80)
print("キャッシュ状態確認")
print("="*80)
print(f"_use_cache: {analyzer._use_cache}")
print(f"batch_loader exists: {analyzer.batch_loader is not None}")

if analyzer.batch_loader:
    print("\n日次データロード中...")
    analyzer.batch_loader.load_daily_data('2024-01-01')
    print(f"データロード完了")
    print(f"is_loaded: {analyzer.batch_loader.is_loaded()}")
    print(f"cache_date: {analyzer.batch_loader.get_cache_date()}")

# race_id=134270のエントリー情報を取得
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT e.pit_number, e.racer_number, rd.actual_course
    FROM entries e
    LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    WHERE e.race_id = 134270
    ORDER BY e.pit_number
    LIMIT 1
""")

row = cursor.fetchone()
conn.close()

pit, racer_num, actual_course = row
course = actual_course if actual_course else pit

print(f"\n1号艇テスト: racer={racer_num}, course={course}")
print("="*80)

# get_racer_course_statsを直接呼び出し
course_stats = analyzer.get_racer_course_stats(racer_num, course)

print(f"返り値の型: {type(course_stats)}")
print(f"返り値: {course_stats}")

if course_stats is None:
    print("❌ Noneが返された!")
elif 'total_races' not in course_stats:
    print(f"❌ 'total_races'キーがない!")
    print(f"利用可能なキー: {list(course_stats.keys())}")
else:
    print(f"✅ OK: total_races = {course_stats['total_races']}")
