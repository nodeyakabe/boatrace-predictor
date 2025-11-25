"""
会場補正のテスト
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.venue_characteristics import get_venue_adjustment, get_venue_name
from src.analysis.race_predictor import RacePredictor
import sqlite3
from config.settings import DATABASE_PATH

print("=" * 80)
print("会場補正機能テスト")
print("=" * 80)

# 会場補正係数の確認
test_venues = ['02', '07', '12', '15', '22', '24']

print("\n会場補正係数:")
print("-" * 80)
print("会場コード | 会場名   | 補正係数")
print("-" * 80)

for venue in test_venues:
    name = get_venue_name(venue)
    adjustment = get_venue_adjustment(venue)
    print(f"    {venue}     | {name:8s} | {adjustment:.2f}")

# 1レースでテスト
print("\n" + "=" * 80)
print("予測テスト（会場補正適用後）")
print("=" * 80)

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

# 各会場から1レースずつ取得
cursor.execute("""
    SELECT id, venue_code, race_number
    FROM races
    WHERE race_date = '2025-11-17'
      AND venue_code IN ('02', '07', '15', '22')
    ORDER BY venue_code
    LIMIT 4
""")

races = cursor.fetchall()
conn.close()

predictor = RacePredictor()

for race_id, venue_code, race_number in races:
    venue_name = get_venue_name(venue_code)
    adjustment = get_venue_adjustment(venue_code)

    print(f"\n【会場{venue_code} - {venue_name}】 (補正係数: {adjustment:.2f})")
    print(f"  {int(race_number)}R")
    print("  " + "-" * 70)

    predictions = predictor.predict_race(race_id)

    print("  号艇 | 選手名     | コース | 総合 | 信頼度 | 予測順位")
    print("  " + "-" * 70)

    for p in predictions[:3]:  # 上位3艇のみ表示
        print(f"  {p['pit_number']}号艇 | {p['racer_name']:10s} | {p['course_score']:5.1f} | {p['total_score']:5.1f} | {p['confidence']:4s}   | {p['rank_prediction']:2d}位")

print("\n" + "=" * 80)
print("テスト完了")
print("=" * 80)
