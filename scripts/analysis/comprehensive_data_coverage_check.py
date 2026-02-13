"""
全データ種の充足率包括調査

目的：
- データベースの全カラムの充足率を調査
- カラムとして定義されているが中身がスカスカなものを特定
- 補完の優先順位を判断するための基礎データを取得
"""

import sqlite3
import pandas as pd
from pathlib import Path

# DB接続
db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
conn = sqlite3.connect(db_path)

print("=" * 80)
print("全データ種の充足率包括調査")
print("=" * 80)

# 調査するテーブルとカラムの定義
tables_to_check = {
    'races': [
        'race_grade', 'race_name', 'race_type', 'distance',
        'wind_direction', 'wind_speed', 'wave_height', 'water_temp', 'weather'
    ],
    'race_conditions': [
        'weather', 'wind_direction', 'wind_speed', 'wave_height',
        'water_temp', 'air_temp'
    ],
    'race_details': [
        'exhibition_time', 'st_time', 'chikusen_time', 'actual_course',
        'prev_race_rank', 'weight'
    ],
    'results': [
        'rank', 'race_time', 'kimarite', 'start_timing'
    ],
    'entries': [
        'racer_name', 'racer_number', 'win_rate', 'second_rate',
        'motor_number', 'motor_second_rate', 'boat_number', 'boat_second_rate',
        'local_win_rate', 'f_count', 'l_count', 'avg_st', 'nation_win_rate'
    ],
    'trifecta_odds': [
        'combination', 'odds'
    ],
    'exhibition_data': [
        'pit_number', 'exhibition_time', 'tilt_angle',
        'tenji_course', 'tenji_st'
    ]
}

# 総レース数を取得
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM races')
total_races = c.fetchone()[0]

print(f"\n総レース数: {total_races:,}\n")
print("=" * 80)

# 各テーブル・カラムの充足率を調査
all_results = []

for table_name, columns in tables_to_check.items():
    print(f"\n### {table_name} テーブル ###\n")

    # テーブルの総行数を取得
    c.execute(f'SELECT COUNT(*) FROM {table_name}')
    total_rows = c.fetchone()[0]

    for column in columns:
        try:
            # NULL以外のデータ数を取得
            query = f'''
                SELECT COUNT(*)
                FROM {table_name}
                WHERE {column} IS NOT NULL AND {column} != ""
            '''
            c.execute(query)
            non_null_count = c.fetchone()[0]

            coverage = (non_null_count / total_rows * 100) if total_rows > 0 else 0

            # 結果を表示
            status = "[OK]" if coverage >= 95 else "[!!]" if coverage >= 50 else "[NG]"
            print(f"{status} {column:25s}: {non_null_count:>10,} / {total_rows:>10,} ({coverage:6.2f}%)")

            # 結果を保存
            all_results.append({
                'テーブル': table_name,
                'カラム': column,
                'データあり': non_null_count,
                '総行数': total_rows,
                '充足率(%)': round(coverage, 2),
                'ステータス': '充足' if coverage >= 95 else '要補完' if coverage < 50 else '一部欠損'
            })

        except sqlite3.OperationalError as e:
            print(f"[NG] {column:25s}: エラー - {e}")
            all_results.append({
                'テーブル': table_name,
                'カラム': column,
                'データあり': 0,
                '総行数': total_rows,
                '充足率(%)': 0.0,
                'ステータス': 'エラー'
            })

print("\n" + "=" * 80)
print("要補完データの優先順位（充足率50%未満）")
print("=" * 80)

# DataFrameに変換
df = pd.DataFrame(all_results)

# 充足率50%未満を抽出
needs_completion = df[df['充足率(%)'] < 50].sort_values('充足率(%)')

if len(needs_completion) > 0:
    print(f"\n要補完データ: {len(needs_completion)}項目\n")
    for idx, row in needs_completion.iterrows():
        print(f"{row['テーブル']:20s}.{row['カラム']:25s} {row['充足率(%)']:6.2f}% ({row['データあり']:,} / {row['総行数']:,})")
else:
    print("\n[OK] 全てのデータが50%以上の充足率です")

# 年度別の充足率も確認（主要カラムのみ）
print("\n" + "=" * 80)
print("年度別充足率（主要カラム）")
print("=" * 80)

important_columns = [
    ('results', 'kimarite'),
    ('race_conditions', 'weather'),
    ('race_details', 'st_time'),
    ('race_details', 'chikusen_time'),
    ('race_details', 'exhibition_time'),
    ('entries', 'motor_second_rate'),
    ('entries', 'local_win_rate')
]

for table_name, column in important_columns:
    print(f"\n{table_name}.{column}:")

    for year in range(2020, 2026):
        # テーブルに応じてJOIN方法を変える
        if table_name == 'races':
            query = f'''
                SELECT COUNT(DISTINCT r.id) as total,
                       COUNT(DISTINCT CASE WHEN r.{column} IS NOT NULL AND r.{column} != "" THEN r.id END) as has_data
                FROM races r
                WHERE strftime('%Y', r.race_date) = '{year}'
            '''
        elif table_name == 'results':
            query = f'''
                SELECT COUNT(DISTINCT res.race_id) as total,
                       COUNT(DISTINCT CASE WHEN res.{column} IS NOT NULL AND res.{column} != "" THEN res.race_id END) as has_data
                FROM results res
                JOIN races r ON res.race_id = r.id
                WHERE strftime('%Y', r.race_date) = '{year}' AND res.rank = '1'
            '''
        else:
            # その他のテーブル
            query = f'''
                SELECT COUNT(DISTINCT t.race_id) as total,
                       COUNT(DISTINCT CASE WHEN t.{column} IS NOT NULL AND t.{column} != "" THEN t.race_id END) as has_data
                FROM {table_name} t
                JOIN races r ON t.race_id = r.id
                WHERE strftime('%Y', r.race_date) = '{year}'
            '''

        try:
            c.execute(query)
            result = c.fetchone()
            if result and result[0] > 0:
                total, has_data = result
                coverage = has_data / total * 100
                status = "[OK]" if coverage >= 95 else "[!!]" if coverage >= 50 else "[NG]"
                print(f"  {year}年: {status} {has_data:>6,} / {total:>6,} ({coverage:5.1f}%)")
        except sqlite3.OperationalError as e:
            print(f"  {year}年: エラー - {e}")

# 結果をCSVに保存
output_path = Path(__file__).parent.parent.parent / "docs" / "performance" / "DATA_COVERAGE_FULL_REPORT.csv"
df.to_csv(output_path, index=False, encoding='utf-8-sig')
print(f"\n詳細レポート保存: {output_path}")

conn.close()

print("\n" + "=" * 80)
print("調査完了")
print("=" * 80)
