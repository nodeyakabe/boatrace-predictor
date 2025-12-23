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
print("データベース状態確認 - 2024年データ")
print("=" * 80)

# レースデータの期間と件数
cursor.execute("""
    SELECT
        MIN(race_date) as min_date,
        MAX(race_date) as max_date,
        COUNT(*) as total_races
    FROM races
    WHERE race_date LIKE '2024%'
""")
race_info = cursor.fetchone()
print(f"\n[RACE] レースデータ（2024年）")
if race_info[0]:
    print(f"   期間: {race_info[0]} ～ {race_info[1]}")
    print(f"   総レース数: {race_info[2]:,} 件")
else:
    print("   データなし")

cursor.execute("""
    SELECT COUNT(*) FROM races WHERE race_date LIKE '2024%'
""")
total_2024_races = cursor.fetchone()[0]

if total_2024_races > 0:
    # 月別レース数
    cursor.execute("""
        SELECT
            SUBSTR(race_date, 1, 7) as month,
            COUNT(*) as race_count
        FROM races
        WHERE race_date LIKE '2024%'
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
        WHERE race_id IN (SELECT id FROM races WHERE race_date LIKE '2024%')
    """)
    odds_info = cursor.fetchone()
    odds_coverage = (odds_info[0] / total_2024_races * 100) if total_2024_races > 0 else 0

    print(f"\n[ODDS] オッズデータ（3連単）")
    print(f"   オッズ有りレース: {odds_info[0]:,} / {total_2024_races:,} ({odds_coverage:.1f}%)")
    print(f"   オッズレコード数: {odds_info[1]:,} 件")

    # 予想データの状況
    cursor.execute("""
        SELECT
            COUNT(DISTINCT race_id) as races_with_prediction,
            SUM(CASE WHEN prediction_type = 'advance' THEN 1 ELSE 0 END) as advance_count,
            SUM(CASE WHEN prediction_type = 'before' THEN 1 ELSE 0 END) as before_count
        FROM race_predictions
        WHERE race_id IN (SELECT id FROM races WHERE race_date LIKE '2024%')
    """)
    pred_info = cursor.fetchone()
    pred_coverage = (pred_info[0] / total_2024_races * 100) if total_2024_races > 0 and pred_info[0] else 0

    print(f"\n[PREDICTION] 予想データ")
    print(f"   予想有りレース: {pred_info[0] or 0:,} / {total_2024_races:,} ({pred_coverage:.1f}%)")
    print(f"   事前予想: {pred_info[1] or 0:,} 件")
    print(f"   直前予想: {pred_info[2] or 0:,} 件")

    # 結果データの状況
    cursor.execute("""
        SELECT
            COUNT(DISTINCT race_id) as races_with_results
        FROM results
        WHERE race_id IN (SELECT id FROM races WHERE race_date LIKE '2024%')
    """)
    result_count = cursor.fetchone()[0]
    result_coverage = (result_count / total_2024_races * 100) if total_2024_races > 0 else 0

    print(f"\n[RESULT] 結果データ")
    print(f"   結果有りレース: {result_count:,} / {total_2024_races:,} ({result_coverage:.1f}%)")

    # 不足データのサマリー
    print(f"\n" + "=" * 80)
    print("[SUMMARY] 不足データサマリー")
    print("=" * 80)

    missing_odds = total_2024_races - odds_info[0]
    missing_predictions = total_2024_races - pred_info[0]

    print(f"   3連単オッズ未取得: {missing_odds:>6,} レース")
    print(f"   予想データ未生成: {missing_predictions:>6,} レース")

conn.close()

print(f"\n" + "=" * 80)
print(f"確認日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
