#!/usr/bin/env python3
"""
データ充足率クイックチェック
"""

import sqlite3
from datetime import datetime

DB_PATH = "c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032/data/boatrace.db"

def main():
    print("データ充足率調査開始...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 年度別サマリー
    print("\n年度別サマリーを取得中...")
    query = """
    SELECT
        strftime('%Y', r.race_date) as year,
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT e.race_id) as with_entries,
        COUNT(DISTINCT res.race_id) as with_results,
        COUNT(DISTINCT t.race_id) as with_odds,
        COUNT(DISTINCT rd.race_id) as with_details,
        COUNT(DISTINCT rp.race_id) as with_predictions
    FROM races r
    LEFT JOIN entries e ON r.id = e.race_id
    LEFT JOIN results res ON r.id = res.race_id
    LEFT JOIN trifecta_odds t ON r.id = t.race_id
    LEFT JOIN race_details rd ON r.id = rd.race_id
    LEFT JOIN race_predictions rp ON r.id = rp.race_id
    WHERE r.race_date >= '2020-01-01' AND r.race_date <= '2025-12-31'
    GROUP BY year
    ORDER BY year
    """

    cursor.execute(query)
    yearly_data = cursor.fetchall()

    print("\n" + "="*100)
    print("年度別データ充足率")
    print("="*100)
    print(f"{'年度':<8} {'レース数':>10} {'出走表':>12} {'結果':>12} {'オッズ':>12} {'詳細':>12} {'予測':>12}")
    print("-"*100)

    for row in yearly_data:
        year, total, entries, results, odds, details, preds = row
        print(f"{year:<8} {total:>10,} {entries:>10,} {results:>10,} {odds:>10,} {details:>10,} {preds:>10,}")
        if total > 0:
            print(f"{'':8} {'':10} {entries/total*100:>10.1f}% {results/total*100:>10.1f}% {odds/total*100:>10.1f}% {details/total*100:>10.1f}% {preds/total*100:>10.1f}%")

    # 2021年9-12月の詳細
    print("\n" + "="*100)
    print("2021年9-12月の詳細（今回追加分）")
    print("="*100)

    for month in ['09', '10', '11', '12']:
        query = f"""
        SELECT
            COUNT(DISTINCT r.id) as total_races,
            COUNT(DISTINCT e.race_id) as with_entries,
            COUNT(DISTINCT res.race_id) as with_results,
            COUNT(DISTINCT t.race_id) as with_odds,
            COUNT(DISTINCT rd.race_id) as with_details,
            COUNT(DISTINCT rp.race_id) as with_predictions
        FROM races r
        LEFT JOIN entries e ON r.id = e.race_id
        LEFT JOIN results res ON r.id = res.race_id
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
        LEFT JOIN race_details rd ON r.id = rd.race_id
        LEFT JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= '2021-{month}-01' AND r.race_date < '2021-{int(month)+1:02d}-01'
        """

        cursor.execute(query)
        data = cursor.fetchone()
        total, entries, results, odds, details, preds = data

        if total > 0:
            print(f"\n2021-{month}:")
            print(f"  レース数: {total:,}")
            print(f"  出走表: {entries:,} ({entries/total*100:.1f}%)")
            print(f"  結果: {results:,} ({results/total*100:.1f}%)")
            print(f"  オッズ: {odds:,} ({odds/total*100:.1f}%)")
            print(f"  詳細: {details:,} ({details/total*100:.1f}%)")
            print(f"  予測: {preds:,} ({preds/total*100:.1f}%)")
        else:
            print(f"\n2021-{month}: データなし")

    # 2023年全期間の詳細
    print("\n" + "="*100)
    print("2023年全期間の詳細（今回追加分）")
    print("="*100)

    for month_num in range(1, 13):
        month = f"{month_num:02d}"
        next_month = f"{month_num+1:02d}" if month_num < 12 else "2024-01"

        query = f"""
        SELECT
            COUNT(DISTINCT r.id) as total_races,
            COUNT(DISTINCT e.race_id) as with_entries,
            COUNT(DISTINCT res.race_id) as with_results,
            COUNT(DISTINCT t.race_id) as with_odds,
            COUNT(DISTINCT rd.race_id) as with_details,
            COUNT(DISTINCT rp.race_id) as with_predictions
        FROM races r
        LEFT JOIN entries e ON r.id = e.race_id
        LEFT JOIN results res ON r.id = res.race_id
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
        LEFT JOIN race_details rd ON r.id = rd.race_id
        LEFT JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= '2023-{month}-01' AND r.race_date < '{next_month}-01'
        """

        cursor.execute(query)
        data = cursor.fetchone()
        total, entries, results, odds, details, preds = data

        if total > 0:
            print(f"\n2023-{month}:")
            print(f"  レース数: {total:,} | 出走表: {entries:,} ({entries/total*100:.1f}%) | 結果: {results:,} ({results/total*100:.1f}%) | オッズ: {odds:,} ({odds/total*100:.1f}%) | 詳細: {details:,} ({details/total*100:.1f}%) | 予測: {preds:,} ({preds/total*100:.1f}%)")

    conn.close()

    print("\n" + "="*100)
    print("調査完了")
    print("="*100)

if __name__ == "__main__":
    main()
