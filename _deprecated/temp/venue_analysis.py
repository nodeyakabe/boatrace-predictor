# -*- coding: utf-8 -*-
"""
会場別・選手別 詳細分析スクリプト
2024年11月27日 作成
"""

import sqlite3
import pandas as pd
import sys

# UTF-8出力設定
sys.stdout.reconfigure(encoding='utf-8')

def main():
    conn = sqlite3.connect('data/boatrace.db')

    print('=' * 70)
    print('■ 会場別 荒れレース分析（2024年データ）')
    print('=' * 70)

    # 会場別荒れ率
    query = '''
    SELECT
        r.venue_code,
        v.name as venue_name,
        COUNT(DISTINCT r.id) as total_races,
        SUM(CASE WHEN res.rank = '1' AND res.pit_number = 1 THEN 1 ELSE 0 END) as pit1_wins,
        SUM(CASE WHEN res.rank = '1' AND res.pit_number != 1 THEN 1 ELSE 0 END) as upset_races,
        ROUND(100.0 * SUM(CASE WHEN res.rank = '1' AND res.pit_number != 1 THEN 1 ELSE 0 END) / COUNT(DISTINCT r.id), 1) as upset_rate,
        SUM(CASE WHEN res.rank = '1' AND res.pit_number >= 4 THEN 1 ELSE 0 END) as big_upset,
        ROUND(100.0 * SUM(CASE WHEN res.rank = '1' AND res.pit_number >= 4 THEN 1 ELSE 0 END) / COUNT(DISTINCT r.id), 1) as big_upset_rate
    FROM races r
    JOIN results res ON r.id = res.race_id
    JOIN venues v ON r.venue_code = v.code
    WHERE r.race_date >= '2024-01-01'
    GROUP BY r.venue_code, v.name
    ORDER BY upset_rate DESC
    '''
    df = pd.read_sql_query(query, conn)

    print()
    print('| 会場 | コード | 荒れ率 | 大穴率 | レース数 | 分類 |')
    print('|------|--------|--------|--------|----------|------|')
    for _, row in df.iterrows():
        if row['upset_rate'] >= 50:
            cat = '荒れ'
        elif row['upset_rate'] <= 40:
            cat = '堅い'
        else:
            cat = '普通'
        print(f"| {row['venue_name']} | {row['venue_code']} | {row['upset_rate']:5.1f}% | {row['big_upset_rate']:5.1f}% | {int(row['total_races']):>8} | {cat} |")

    print()
    print('=' * 70)
    print('■ 会場別 コース勝率分析')
    print('=' * 70)

    # 会場別コース別勝率
    query2 = '''
    SELECT
        r.venue_code,
        v.name as venue_name,
        res.pit_number,
        COUNT(*) as total,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(100.0 * SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate
    FROM races r
    JOIN results res ON r.id = res.race_id
    JOIN venues v ON r.venue_code = v.code
    WHERE r.race_date >= '2024-01-01'
    GROUP BY r.venue_code, v.name, res.pit_number
    ORDER BY r.venue_code, res.pit_number
    '''
    df2 = pd.read_sql_query(query2, conn)

    # ピボットテーブル作成
    pivot = df2.pivot_table(values='win_rate', index=['venue_code', 'venue_name'],
                            columns='pit_number', aggfunc='first')

    print()
    print('| 会場 | 1コース | 2コース | 3コース | 4コース | 5コース | 6コース |')
    print('|------|---------|---------|---------|---------|---------|---------|')
    for (code, name), row in pivot.iterrows():
        print(f"| {name} | {row.get(1, 0):6.1f}% | {row.get(2, 0):6.1f}% | {row.get(3, 0):6.1f}% | {row.get(4, 0):6.1f}% | {row.get(5, 0):6.1f}% | {row.get(6, 0):6.1f}% |")

    print()
    print('=' * 70)
    print('■ 級別 × コース 勝率分析')
    print('=' * 70)

    # 級別×コース勝率 (racer_rank = 級別)
    query3 = '''
    SELECT
        e.racer_rank,
        e.pit_number,
        COUNT(*) as total,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(100.0 * SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate
    FROM races r
    JOIN entries e ON r.id = e.race_id
    JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01'
        AND e.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    GROUP BY e.racer_rank, e.pit_number
    ORDER BY e.racer_rank, e.pit_number
    '''
    df3 = pd.read_sql_query(query3, conn)

    pivot3 = df3.pivot_table(values='win_rate', index='racer_rank', columns='pit_number', aggfunc='first')

    print()
    print('| 級別 | 1コース | 2コース | 3コース | 4コース | 5コース | 6コース |')
    print('|------|---------|---------|---------|---------|---------|---------|')
    for cls in ['A1', 'A2', 'B1', 'B2']:
        if cls in pivot3.index:
            row = pivot3.loc[cls]
            print(f"| {cls}   | {row.get(1, 0):6.1f}% | {row.get(2, 0):6.1f}% | {row.get(3, 0):6.1f}% | {row.get(4, 0):6.1f}% | {row.get(5, 0):6.1f}% | {row.get(6, 0):6.1f}% |")

    print()
    print('=' * 70)
    print('■ 展示タイム順位と結果の相関')
    print('=' * 70)

    # 展示タイムランクと勝率
    query4 = '''
    WITH exhibition_ranked AS (
        SELECT
            rd.race_id,
            rd.pit_number,
            rd.exhibition_time,
            RANK() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) as ex_rank
        FROM race_details rd
        WHERE rd.exhibition_time > 0 AND rd.exhibition_time < 10
    )
    SELECT
        er.ex_rank,
        COUNT(*) as total,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(100.0 * SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) / COUNT(*), 2) as win_rate,
        SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as place,
        ROUND(100.0 * SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) / COUNT(*), 2) as place_rate
    FROM exhibition_ranked er
    JOIN races r ON er.race_id = r.id
    JOIN results res ON er.race_id = res.race_id AND er.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01'
    GROUP BY er.ex_rank
    ORDER BY er.ex_rank
    '''
    df4 = pd.read_sql_query(query4, conn)

    print()
    print('| 展示順位 | 勝率 | 3着内率 | 件数 |')
    print('|----------|------|---------|------|')
    for _, row in df4.iterrows():
        print(f"| {int(row['ex_rank'])}位 | {row['win_rate']:5.2f}% | {row['place_rate']:5.2f}% | {int(row['total']):>6} |")

    print()
    print('=' * 70)
    print('■ STタイム別 勝率分析')
    print('=' * 70)

    # ST別勝率
    query5 = '''
    SELECT
        CASE
            WHEN rd.st_time >= 0 AND rd.st_time < 0.10 THEN '0.00-0.10'
            WHEN rd.st_time >= 0.10 AND rd.st_time < 0.15 THEN '0.10-0.15'
            WHEN rd.st_time >= 0.15 AND rd.st_time < 0.20 THEN '0.15-0.20'
            WHEN rd.st_time >= 0.20 AND rd.st_time < 0.25 THEN '0.20-0.25'
            WHEN rd.st_time >= 0.25 AND rd.st_time < 0.30 THEN '0.25-0.30'
            WHEN rd.st_time >= 0.30 THEN '0.30以上'
            ELSE 'フライング'
        END as st_range,
        COUNT(*) as total,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(100.0 * SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) / COUNT(*), 2) as win_rate
    FROM race_details rd
    JOIN races r ON rd.race_id = r.id
    JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01'
        AND rd.st_time IS NOT NULL
    GROUP BY st_range
    ORDER BY st_range
    '''
    df5 = pd.read_sql_query(query5, conn)

    print()
    print('| STタイム | 勝率 | 件数 |')
    print('|----------|------|------|')
    for _, row in df5.iterrows():
        print(f"| {row['st_range']} | {row['win_rate']:5.2f}% | {int(row['total']):>6} |")

    print()
    print('=' * 70)
    print('■ 決まり手 × 会場分析')
    print('=' * 70)

    # 決まり手×会場
    query6 = '''
    SELECT
        r.venue_code,
        v.name as venue_name,
        res.kimarite,
        COUNT(*) as cnt
    FROM races r
    JOIN results res ON r.id = res.race_id
    JOIN venues v ON r.venue_code = v.code
    WHERE r.race_date >= '2024-01-01'
        AND res.rank = '1'
        AND res.kimarite IS NOT NULL
        AND res.kimarite != ''
    GROUP BY r.venue_code, v.name, res.kimarite
    '''
    df6 = pd.read_sql_query(query6, conn)

    # ピボットテーブル
    pivot6 = df6.pivot_table(values='cnt', index=['venue_code', 'venue_name'],
                              columns='kimarite', aggfunc='sum', fill_value=0)

    print()
    print('会場別 決まり手分布:')
    for (code, name), row in pivot6.iterrows():
        total = row.sum()
        if total > 0:
            nige = row.get('逃げ', 0) / total * 100
            sashi = row.get('差し', 0) / total * 100
            makuri = row.get('まくり', 0) / total * 100
            makuri_sashi = row.get('まくり差し', 0) / total * 100
            print(f"  {name}({code}): 逃げ {nige:5.1f}%, 差し {sashi:5.1f}%, まくり {makuri:5.1f}%, まくり差し {makuri_sashi:5.1f}%")

    conn.close()
    print()
    print('分析完了')

if __name__ == '__main__':
    main()
