#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
racersテーブルの構造とrank列の値を確認
"""
import sqlite3
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATABASE_PATH = 'data/boatrace.db'

def check_racers_table():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("="*80)
    print("racersテーブルの確認")
    print("="*80)
    print()

    # テーブル構造
    print("■ テーブル構造")
    cursor.execute("PRAGMA table_info(racers)")
    for row in cursor.fetchall():
        print(f"  {row[1]}: {row[2]}")
    print()

    # rank列の値の種類
    print("■ rank列の値の種類と件数")
    cursor.execute('''
        SELECT
            rank,
            COUNT(*) as count
        FROM racers
        GROUP BY rank
        ORDER BY rank
    ''')

    print(f"{'rank値':<15} {'件数':<12}")
    print("-"*30)
    for rank, count in cursor.fetchall():
        rank_str = str(rank) if rank else 'NULL'
        print(f"{rank_str:<15} {count:>6,}件")
    print()

    # racersテーブルの総件数
    cursor.execute("SELECT COUNT(*) FROM racers")
    total = cursor.fetchone()[0]
    print(f"racersテーブルの総件数: {total:,}件")
    print()

    # race_predictionsとracersのJOIN可能性
    print("■ race_predictionsとracersのJOIN状況")
    cursor.execute('''
        SELECT
            COUNT(*) as total,
            COUNT(r.racer_number) as joined
        FROM race_predictions rp
        LEFT JOIN racers r ON rp.racer_number = r.racer_number
        WHERE rp.prediction_type = 'before'
        LIMIT 1
    ''')

    total, joined = cursor.fetchone()
    print(f"race_predictions総件数: {total:,}件")
    print(f"racersとJOIN成功: {joined:,}件 ({100.0*joined/total:.1f}%)")
    print()

    # サンプルデータ
    print("■ racersテーブルのサンプルデータ（最初の5件）")
    cursor.execute('''
        SELECT racer_number, name, rank, win_rate, second_rate
        FROM racers
        LIMIT 5
    ''')

    print(f"{'選手登録番号':<12} {'名前':<20} {'級別':<8} {'勝率':<8} {'2連率':<8}")
    print("-"*70)
    for row in cursor.fetchall():
        racer_num, name, rank, win_rate, second_rate = row
        name_str = name if name else 'N/A'
        rank_str = rank if rank else 'N/A'
        win_str = f"{win_rate:.2f}" if win_rate else 'N/A'
        second_str = f"{second_rate:.2f}" if second_rate else 'N/A'
        print(f"{racer_num:<12} {name_str:<20} {rank_str:<8} {win_str:<8} {second_str:<8}")

    conn.close()

if __name__ == '__main__':
    check_racers_table()
