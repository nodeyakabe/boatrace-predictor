"""不足データ検出のテスト"""
import sqlite3
from datetime import datetime, timedelta
from src.analysis.data_coverage_checker import DataCoverageChecker

DATABASE_PATH = 'data/boatrace.db'

# テスト期間: 過去30日間
end_date = datetime.now().date()
start_date = end_date - timedelta(days=30)

print("="*60)
print("不足データ検出テスト")
print("="*60)
print(f"期間: {start_date} 〜 {end_date}")
print()

# DataCoverageCheckerで全体の充足率を確認
checker = DataCoverageChecker(DATABASE_PATH)
report = checker.get_coverage_report()

print("【全体カバレッジ】")
for cat_name, cat_data in report["categories"].items():
    score = cat_data.get('score', 0) * 100
    print(f"  {cat_name}: {score:.1f}%")
print()

# 不足項目（90%未満）を抽出
print("【不足項目（カバレッジ < 90%）】")
missing_count = 0
for cat_name, cat_data in report["categories"].items():
    for item in cat_data["items"]:
        if item["coverage"] < 0.9:
            missing_count += 1
            print(f"  [{cat_name}] {item['name']}: {item['coverage']*100:.1f}%")

print(f"\n不足項目数: {missing_count}件")
print()

# 日付別にレース数をチェック
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

print("【日付別レース数（期間内）】")
current = start_date
dates_with_races = 0
dates_without_races = 0

while current <= end_date:
    date_str = current.strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM races WHERE race_date = ?", (date_str,))
    race_count = cursor.fetchone()[0]

    if race_count > 0:
        dates_with_races += 1
        if dates_with_races <= 5:  # 最初の5日分だけ表示
            print(f"  {date_str}: {race_count}レース")
    else:
        dates_without_races += 1

    current += timedelta(days=1)

print(f"  ...")
print(f"\nレースあり: {dates_with_races}日")
print(f"レースなし: {dates_without_races}日")

conn.close()

print()
print("="*60)
print("結論:")
print("="*60)

if missing_count > 0:
    print(f"✅ {missing_count}件の不足データ項目が検出されました")
    print(f"   これらの項目は全期間で90%未満のカバレッジです")
    print()
    print("💡 注意:")
    print("   現在の検出ロジックは「全体カバレッジ」のみチェックしており、")
    print("   「特定の日付で不足しているデータ」は検出していません。")
    print()
    print("   例: 展示タイムが全体で22.4%しかない場合、")
    print("       全ての日付で「展示タイム不足」と判定されます。")
else:
    print("❌ 不足データが検出されませんでした")
