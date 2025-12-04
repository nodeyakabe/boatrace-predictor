"""オッズデータの存在確認"""
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 3連単オッズデータの件数
cursor.execute("SELECT COUNT(*) FROM odds_data WHERE bet_type='3tan'")
count_3tan = cursor.fetchone()[0]
print(f"3連単オッズデータ: {count_3tan}件")

# 最新のオッズデータの日付
cursor.execute("""
    SELECT r.race_date, r.venue_code, r.race_number, od.combination, od.odds
    FROM odds_data od
    JOIN races r ON od.race_id = r.id
    WHERE od.bet_type = '3tan'
    ORDER BY r.race_date DESC
    LIMIT 5
""")
recent_odds = cursor.fetchall()
print("\n最新のオッズデータ（5件）:")
for row in recent_odds:
    print(f"  {row[0]} {row[1]}場{row[2]}R: {row[3]} = {row[4]}倍")

# テスト期間（2025-11-26〜2025-12-02）のオッズデータ
cursor.execute("""
    SELECT COUNT(*)
    FROM odds_data od
    JOIN races r ON od.race_id = r.id
    WHERE r.race_date BETWEEN '2025-11-26' AND '2025-12-02'
    AND od.bet_type = '3tan'
""")
test_period_count = cursor.fetchone()[0]
print(f"\nテスト期間（2025-11-26〜2025-12-02）のオッズデータ: {test_period_count}件")

conn.close()
