"""VenueAnalyzerの修正をテスト"""
import sys
sys.path.append('src')

from analysis.venue_analyzer import VenueAnalyzer
from config.settings import DATABASE_PATH

print("="*70)
print("VenueAnalyzer修正版のテスト")
print("="*70)

analyzer = VenueAnalyzer(DATABASE_PATH)

# テスト1: コース別統計（桐生、過去90日）
print("\n【テスト1】コース別統計 - 桐生（過去90日）")
print("-"*70)
course_stats = analyzer.get_venue_course_stats('01', days_back=90)

if not course_stats.empty:
    print(f"取得成功: {len(course_stats)}コース分のデータ")
    print("\nコース別1着率:")
    for _, row in course_stats.iterrows():
        course = int(row['course'])
        win_rate = row['win_rate']
        total = row['total_races']
        wins = row['win_count']
        print(f"  {course}コース: {win_rate:.1f}% ({wins}勝/{total}レース)")
else:
    print("✗ データなし")

# テスト2: 決まり手パターン（桐生、過去90日、1コース）
print("\n【テスト2】決まり手パターン - 桐生（過去90日）")
print("-"*70)
kimarite_data = analyzer.get_venue_kimarite_pattern('01', days_back=90)

if kimarite_data:
    print(f"取得成功: {len(kimarite_data)}コース分のデータ")

    # 1コースの決まり手を詳細表示
    if '1' in kimarite_data:
        print("\n1コースの決まり手分布:")
        total = sum(kimarite_data['1'].values())
        for kimarite, count in sorted(kimarite_data['1'].items(), key=lambda x: x[1], reverse=True):
            pct = count * 100.0 / total
            print(f"  {kimarite}: {count}回 ({pct:.1f}%)")

    # 全コースのサマリー
    print("\n全コースの決まり手種類数:")
    for course in sorted(kimarite_data.keys(), key=lambda x: int(x)):
        kinds = len(kimarite_data[course])
        total_count = sum(kimarite_data[course].values())
        print(f"  {course}コース: {kinds}種類 (合計{total_count}回)")
else:
    print("✗ データなし")

# テスト3: 季節別パフォーマンス（桐生）
print("\n【テスト3】季節別パフォーマンス - 桐生")
print("-"*70)
seasonal_data = analyzer.get_seasonal_performance('01')

if seasonal_data:
    print(f"取得成功: {len(seasonal_data)}季節分のデータ")

    season_names = {
        'spring': '春(3-5月)',
        'summer': '夏(6-8月)',
        'autumn': '秋(9-11月)',
        'winter': '冬(12-2月)'
    }

    for season_key, season_name in season_names.items():
        if season_key in seasonal_data:
            df = seasonal_data[season_key]
            if not df.empty:
                print(f"\n{season_name}:")
                # 1コースだけ表示
                course1 = df[df['course'] == 1]
                if not course1.empty:
                    row = course1.iloc[0]
                    print(f"  1コース: {row['win_rate']:.1f}% ({row['win_count']}勝/{row['total_races']}レース)")
else:
    print("✗ データなし")

# テスト4: 別の会場でも確認（浜名湖=17）
print("\n【テスト4】別会場テスト - 浜名湖（過去90日）")
print("-"*70)
course_stats_17 = analyzer.get_venue_course_stats('17', days_back=90)

if not course_stats_17.empty:
    print(f"取得成功: {len(course_stats_17)}コース分のデータ")
    print("\nコース別1着率:")
    for _, row in course_stats_17.iterrows():
        course = int(row['course'])
        win_rate = row['win_rate']
        print(f"  {course}コース: {win_rate:.1f}%")
else:
    print("✗ データなし")

print("\n" + "="*70)
print("テスト完了")
print("="*70)
