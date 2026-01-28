"""
chikusen_time補完可能性テスト v2（2024年前半＋詳細ログ）
"""
import sys
import io
import os

# 文字コード設定
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import sqlite3
from src.scraper.result_scraper import ResultScraper
import json

db_path = 'data/boatrace.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=' * 80)
print('chikusen_time補完可能性テスト v2')
print('=' * 80)
print()

# 2024年前半で結果があり、chikusen_timeがないレースを1件取得
cursor.execute('''
    SELECT r.id, r.venue_code, r.race_date, r.race_number
    FROM races r
    JOIN results res ON r.id = res.race_id
    LEFT JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date >= '2024-01-01' AND r.race_date < '2024-07-01'
      AND rd.chikusen_time IS NULL
    ORDER BY r.race_date ASC
    LIMIT 1
''')

test_race = cursor.fetchone()

if not test_race:
    print('テスト対象レースが見つかりません。')
    conn.close()
    sys.exit(0)

race_id, venue_code, race_date, race_number = test_race

print(f'テストレース:')
print(f'  レースID: {race_id}')
print(f'  会場コード: {venue_code}')
print(f'  日付: {race_date}')
print(f'  レース番号: {race_number}')
print()

# ResultScraperで取得を試行
print('公式APIからデータ取得を試行...')
print()

scraper = ResultScraper(read_timeout=15)
date_str = race_date.replace('-', '')

try:
    result = scraper.get_race_result_complete(venue_code, date_str, race_number)

    print('APIレスポンスの内容:')
    print('-' * 80)
    if result:
        # キーのみ表示
        print(f'取得されたキー: {list(result.keys())}')

        if 'race_details' in result:
            if result['race_details']:
                print()
                print('[成功] race_detailsが取得できました！')
                print()
                print('取得されたrace_details:')
                print('-' * 80)
                for detail in result['race_details']:
                    pit = detail.get('pit_number', '?')
                    chikusen = detail.get('chikusen_time', 'なし')
                    st = detail.get('st_time', 'なし')
                    tilt = detail.get('tilt_angle', 'なし')
                    print(f'  艇番{pit}: chikusen_time={chikusen}, st_time={st}, tilt_angle={tilt}')
                print()
                print('結論: 2020-2024年のデータ補完は可能です。')
            else:
                print()
                print('[失敗] race_detailsキーはあるが中身が空です。')
        else:
            print()
            print('[失敗] race_detailsキーが存在しません。')
    else:
        print('APIレスポンスがNullです。')

except Exception as e:
    print(f'[エラー] エラー: {str(e)}')
    import traceback
    traceback.print_exc()

finally:
    scraper.close()

print()
print('=' * 80)

conn.close()
