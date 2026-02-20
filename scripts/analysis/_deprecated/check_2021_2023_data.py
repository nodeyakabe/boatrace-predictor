#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2021年・2023年のデータ充足率詳細分析
"""
import sqlite3
import sys
import os

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print('=' * 80)
    print('2021年・2023年データ充足率詳細分析')
    print('=' * 80)
    print()

    for year in [2021, 2023]:
        print(f'■ {year}年の状況')
        print('-' * 80)

        # レース総数
        cursor.execute(f'''
            SELECT COUNT(*) FROM races
            WHERE race_date >= '{year}-01-01' AND race_date < '{year+1}-01-01'
        ''')
        total_races = cursor.fetchone()[0]
        print(f'総レース数: {total_races:,}件')
        print()

        # テーブル別の詳細
        tables = [
            ('entries', 'エントリー情報'),
            ('results', 'レース結果'),
            ('trifecta_odds', '3連単オッズ'),
            ('race_predictions', '予測データ'),
        ]

        print(f'{"テーブル":<25} {"レース数":>10} {"充足率":>8} {"不足数":>10}')
        print('-' * 65)

        for table, desc in tables:
            cursor.execute(f'''
                SELECT COUNT(DISTINCT r.id)
                FROM races r
                JOIN {table} t ON r.id = t.race_id
                WHERE r.race_date >= '{year}-01-01' AND r.race_date < '{year+1}-01-01'
            ''')
            count = cursor.fetchone()[0]
            pct = (count / total_races * 100) if total_races > 0 else 0
            missing = total_races - count
            print(f'{desc:<25} {count:>10,} {pct:>7.1f}% {missing:>10,}')

        print()

        # サンプルで不足しているレースを確認
        cursor.execute(f'''
            SELECT r.race_date, r.venue_code, r.race_number, r.id
            FROM races r
            LEFT JOIN trifecta_odds o ON r.id = o.race_id
            WHERE r.race_date >= '{year}-01-01' AND r.race_date < '{year+1}-01-01'
            AND o.race_id IS NULL
            ORDER BY r.race_date
            LIMIT 10
        ''')
        missing_races = cursor.fetchall()

        if missing_races:
            print('オッズ欠損レースサンプル（最初の10件）:')
            print(f'{"日付":<12} {"会場":>4} {"R":>3} {"race_id":>8}')
            print('-' * 35)
            for date, venue, rnum, rid in missing_races:
                print(f'{date} {venue:>4} {rnum:>3}R {rid:>8}')

        print()
        print()

    # 月別の充足率
    print('=' * 80)
    print('2021年 月別データ充足率')
    print('=' * 80)
    print(f'{"月":>4} {"レース数":>8} {"オッズあり":>10} {"充足率":>8}')
    print('-' * 40)

    for month in range(1, 13):
        if month < 12:
            date_cond = f"race_date >= '2021-{month:02d}-01' AND race_date < '2021-{month+1:02d}-01'"
        else:
            date_cond = f"race_date >= '2021-12-01' AND race_date < '2022-01-01'"

        cursor.execute(f'SELECT COUNT(*) FROM races WHERE {date_cond}')
        total = cursor.fetchone()[0]

        cursor.execute(f'''
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            JOIN trifecta_odds o ON r.id = o.race_id
            WHERE {date_cond}
        ''')
        with_odds = cursor.fetchone()[0]

        pct = (with_odds / total * 100) if total > 0 else 0
        print(f'{month:>3}月 {total:>8} {with_odds:>10} {pct:>7.1f}%')

    print()
    print('=' * 80)
    print('2023年 月別データ充足率')
    print('=' * 80)
    print(f'{"月":>4} {"レース数":>8} {"オッズあり":>10} {"充足率":>8}')
    print('-' * 40)

    for month in range(1, 13):
        if month < 12:
            date_cond = f"race_date >= '2023-{month:02d}-01' AND race_date < '2023-{month+1:02d}-01'"
        else:
            date_cond = f"race_date >= '2023-12-01' AND race_date < '2024-01-01'"

        cursor.execute(f'SELECT COUNT(*) FROM races WHERE {date_cond}')
        total = cursor.fetchone()[0]

        cursor.execute(f'''
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            JOIN trifecta_odds o ON r.id = o.race_id
            WHERE {date_cond}
        ''')
        with_odds = cursor.fetchone()[0]

        pct = (with_odds / total * 100) if total > 0 else 0
        print(f'{month:>3}月 {total:>8} {with_odds:>10} {pct:>7.1f}%')

    # racesテーブルにあるのにオッズがないレースの会場別集計
    print()
    print('=' * 80)
    print('オッズ欠損レースの会場別集計（2021年）')
    print('=' * 80)
    cursor.execute('''
        SELECT r.venue_code, COUNT(*) as missing_count
        FROM races r
        LEFT JOIN trifecta_odds o ON r.id = o.race_id
        WHERE r.race_date >= '2021-01-01' AND r.race_date < '2022-01-01'
        AND o.race_id IS NULL
        GROUP BY r.venue_code
        ORDER BY missing_count DESC
    ''')
    results = cursor.fetchall()
    print(f'{"会場コード":>8} {"欠損数":>10}')
    print('-' * 25)
    for venue, count in results[:10]:
        print(f'{venue:>8} {count:>10,}')

    print()
    print('=' * 80)
    print('オッズ欠損レースの会場別集計（2023年）')
    print('=' * 80)
    cursor.execute('''
        SELECT r.venue_code, COUNT(*) as missing_count
        FROM races r
        LEFT JOIN trifecta_odds o ON r.id = o.race_id
        WHERE r.race_date >= '2023-01-01' AND r.race_date < '2024-01-01'
        AND o.race_id IS NULL
        GROUP BY r.venue_code
        ORDER BY missing_count DESC
    ''')
    results = cursor.fetchall()
    print(f'{"会場コード":>8} {"欠損数":>10}')
    print('-' * 25)
    for venue, count in results[:10]:
        print(f'{venue:>8} {count:>10,}')

    conn.close()

if __name__ == '__main__':
    main()
