import sqlite3
from datetime import datetime
import sys
import io

# UTF-8出力設定
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# データベース接続
db_path = 'data/boatrace.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 80)
print("データベース状態確認 - 2025年データ")
print("=" * 80)

# テーブル一覧
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = [row[0] for row in cursor.fetchall()]
print(f"\n[TABLE] テーブル数: {len(tables)}")

# レースデータの期間と件数
cursor.execute("""
    SELECT
        MIN(race_date) as min_date,
        MAX(race_date) as max_date,
        COUNT(*) as total_races
    FROM races
    WHERE race_date LIKE '2025%'
""")
race_info = cursor.fetchone()
print(f"\n[RACE] レースデータ（2025年）")
print(f"   期間: {race_info[0]} ～ {race_info[1]}")
print(f"   総レース数: {race_info[2]:,} 件")

# 月別レース数
cursor.execute("""
    SELECT
        SUBSTR(race_date, 1, 7) as month,
        COUNT(*) as race_count
    FROM races
    WHERE race_date LIKE '2025%'
    GROUP BY month
    ORDER BY month
""")
monthly = cursor.fetchall()
print(f"\n[MONTHLY] 月別レース数:")
for month, count in monthly:
    print(f"   {month}: {count:>5,} レース")

# オッズデータの状況（3連単）
cursor.execute("""
    SELECT
        COUNT(DISTINCT race_id) as races_with_odds,
        COUNT(*) as total_odds_records
    FROM trifecta_odds
    WHERE race_id IN (SELECT id FROM races WHERE race_date LIKE '2025%')
""")
odds_info = cursor.fetchone()

cursor.execute("""
    SELECT COUNT(*) FROM races WHERE race_date LIKE '2025%'
""")
total_2025_races = cursor.fetchone()[0]

odds_coverage = (odds_info[0] / total_2025_races * 100) if total_2025_races > 0 else 0

print(f"\n[ODDS] オッズデータ（3連単）")
print(f"   オッズ有りレース: {odds_info[0]:,} / {total_2025_races:,} ({odds_coverage:.1f}%)")
print(f"   オッズレコード数: {odds_info[1]:,} 件")

# 2連単オッズの状況（テーブルが存在する場合のみ）
try:
    cursor.execute("""
        SELECT
            COUNT(DISTINCT race_id) as races_with_exacta,
            COUNT(*) as total_exacta_records
        FROM exacta_odds
        WHERE race_id IN (SELECT id FROM races WHERE race_date LIKE '2025%')
    """)
    exacta_info = cursor.fetchone()
except:
    exacta_info = (0, 0)

exacta_coverage = (exacta_info[0] / total_2025_races * 100) if total_2025_races > 0 else 0

print(f"\n[EXACTA] オッズデータ（2連単）")
print(f"   オッズ有りレース: {exacta_info[0]:,} / {total_2025_races:,} ({exacta_coverage:.1f}%)")
print(f"   オッズレコード数: {exacta_info[1]:,} 件")

# 予想データの状況
cursor.execute("""
    SELECT
        COUNT(DISTINCT race_id) as races_with_prediction,
        SUM(CASE WHEN prediction_type = 'advance' THEN 1 ELSE 0 END) as advance_count,
        SUM(CASE WHEN prediction_type = 'before' THEN 1 ELSE 0 END) as before_count
    FROM race_predictions
    WHERE race_id IN (SELECT id FROM races WHERE race_date LIKE '2025%')
""")
pred_info = cursor.fetchone()
pred_coverage = (pred_info[0] / total_2025_races * 100) if total_2025_races > 0 else 0

print(f"\n[PREDICTION] 予想データ")
print(f"   予想有りレース: {pred_info[0]:,} / {total_2025_races:,} ({pred_coverage:.1f}%)")
print(f"   事前予想: {pred_info[1]:,} 件")
print(f"   直前予想: {pred_info[2]:,} 件")

# 結果データの状況（resultsテーブルを使用）
cursor.execute("""
    SELECT
        COUNT(DISTINCT race_id) as races_with_results
    FROM results
    WHERE race_id IN (SELECT id FROM races WHERE race_date LIKE '2025%')
""")
result_count = cursor.fetchone()[0]
result_coverage = (result_count / total_2025_races * 100) if total_2025_races > 0 else 0

print(f"\n[RESULT] 結果データ")
print(f"   結果有りレース: {result_count:,} / {total_2025_races:,} ({result_coverage:.1f}%)")

# 不足データのサマリー
print(f"\n" + "=" * 80)
print("[SUMMARY] 不足データサマリー")
print("=" * 80)

missing_odds = total_2025_races - odds_info[0]
missing_exacta = total_2025_races - exacta_info[0]
missing_predictions = total_2025_races - pred_info[0]

print(f"   3連単オッズ未取得: {missing_odds:>6,} レース")
print(f"   2連単オッズ未取得: {missing_exacta:>6,} レース")
print(f"   予想データ未生成: {missing_predictions:>6,} レース")

conn.close()

print(f"\n" + "=" * 80)
print(f"確認日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
