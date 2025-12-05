"""
収集データの分析スクリプト
データ収集完了後に実行して、データの品質と内容を確認
"""

import sqlite3
import pandas as pd
from datetime import datetime

def analyze_data():
    """収集データを分析"""
    conn = sqlite3.connect('data/boatrace_readonly.db')

    print("=" * 80)
    print("収集データ分析レポート")
    print("=" * 80)
    print()

    # 1. 基本統計
    print("## 1. 基本統計")
    print("-" * 80)

    races_df = pd.read_sql_query("SELECT * FROM races", conn)
    entries_df = pd.read_sql_query("SELECT * FROM entries", conn)
    results_df = pd.read_sql_query("SELECT * FROM results", conn)

    print(f"総レース数: {len(races_df):,}")
    print(f"総出走表件数: {len(entries_df):,}")
    print(f"総結果件数: {len(results_df):,}")
    print(f"結果があるレース: {results_df['race_id'].nunique():,}")
    print()

    # 2. 日付別集計
    print("## 2. 日付別集計")
    print("-" * 80)

    date_summary = races_df.groupby('race_date').agg({
        'id': 'count'
    }).rename(columns={'id': 'レース数'})

    print(date_summary.tail(10))
    print()

    # 3. 競艇場別集計
    print("## 3. 競艇場別集計")
    print("-" * 80)

    venue_summary = races_df.groupby('venue_code').agg({
        'id': 'count'
    }).rename(columns={'id': 'レース数'}).sort_values('レース数', ascending=False)

    print(venue_summary)
    print()

    # 4. データ品質チェック
    print("## 4. データ品質チェック")
    print("-" * 80)

    # 欠損値チェック
    null_counts = entries_df.isnull().sum()
    print("欠損値:")
    for col, count in null_counts[null_counts > 0].items():
        print(f"  {col}: {count:,} ({count/len(entries_df)*100:.2f}%)")
    print()

    # 5. 特徴量の基本統計
    print("## 5. 特徴量の基本統計")
    print("-" * 80)

    numeric_cols = ['win_rate', 'second_rate', 'third_rate', 'avg_st',
                    'motor_second_rate', 'motor_third_rate',
                    'boat_second_rate', 'boat_third_rate']

    stats = entries_df[numeric_cols].describe()
    print(stats)
    print()

    # 6. 結果分布
    print("## 6. 結果分布（着順）")
    print("-" * 80)

    rank_dist = results_df['rank'].value_counts().sort_index()
    print(rank_dist)
    print()

    # 7. 枠番別勝率
    print("## 7. 枠番別1着率")
    print("-" * 80)

    pit_wins = pd.read_sql_query("""
        SELECT e.pit_number, COUNT(*) as races, SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as wins
        FROM entries e
        LEFT JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
        WHERE r.rank IS NOT NULL
        GROUP BY e.pit_number
        ORDER BY e.pit_number
    """, conn)

    pit_wins['win_rate'] = pit_wins['wins'] / pit_wins['races'] * 100
    print(pit_wins)
    print()

    conn.close()

    print("=" * 80)
    print("分析完了")
    print("=" * 80)

if __name__ == "__main__":
    analyze_data()
