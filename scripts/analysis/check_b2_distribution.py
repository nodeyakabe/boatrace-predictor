#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B2級の予測順位分布を確認
"""
import sqlite3
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATABASE_PATH = 'data/boatrace.db'

def check_b2_distribution():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("="*80)
    print("B2級の予測順位分布")
    print("="*80)
    print()

    # B2級の予測順位分布
    cursor.execute('''
        SELECT
            rp.rank_prediction,
            COUNT(*) as count
        FROM race_predictions rp
        LEFT JOIN racers r ON rp.racer_number = r.racer_number
        WHERE r.rank = 'B2級'
        AND rp.prediction_type = 'before'
        GROUP BY rp.rank_prediction
        ORDER BY rp.rank_prediction
    ''')

    rows = cursor.fetchall()
    total = sum(row[1] for row in rows)

    print(f"{'予測順位':<10} {'件数':<12} {'割合':<10}")
    print("-"*40)
    for rank, count in rows:
        pct = 100.0 * count / total
        print(f"{rank}位        {count:>6,}件      {pct:>5.1f}%")

    print(f"\n合計: {total:,}件")
    print()

    # B2級が存在する年度別の件数
    print("="*80)
    print("B2級の年度別件数")
    print("="*80)
    print()

    cursor.execute('''
        SELECT
            strftime('%Y', r.race_date) as year,
            COUNT(*) as count
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN racers racer ON rp.racer_number = racer.racer_number
        WHERE racer.rank = 'B2級'
        AND rp.prediction_type = 'before'
        GROUP BY year
        ORDER BY year
    ''')

    print(f"{'年度':<10} {'件数':<12}")
    print("-"*30)
    for year, count in cursor.fetchall():
        print(f"{year}年      {count:>6,}件")

    print()

    conn.close()

if __name__ == '__main__':
    check_b2_distribution()
