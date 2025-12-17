"""
オッズ取得の進捗確認スクリプト
"""
import os
import sys
import sqlite3
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)


def check_progress():
    """進捗を確認"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    if not os.path.exists(db_path):
        print(f"エラー: DB not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("オッズ取得進捗確認")
    print(f"確認日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    # 年別の取得状況
    cursor.execute("""
        SELECT
            substr(r.race_date, 1, 4) as year,
            COUNT(*) as total,
            COUNT(t.race_id) as fetched,
            CAST(COUNT(t.race_id) AS FLOAT) / COUNT(*) * 100 as progress
        FROM races r
        LEFT JOIN (
            SELECT DISTINCT race_id FROM trifecta_odds
        ) t ON r.id = t.race_id
        WHERE r.race_date BETWEEN '2020-01-01' AND '2024-12-31'
        GROUP BY year
        ORDER BY year
    """)

    results = cursor.fetchall()

    print("【年別進捗】")
    print(f"{'年':<8} {'全レース数':>12} {'取得済み':>12} {'進捗率':>10}")
    print("-" * 50)

    total_all = 0
    total_fetched = 0

    for year, total, fetched, progress in results:
        print(f"{year:<8} {total:>12,} {fetched:>12,} {progress:>9.1f}%")
        total_all += total
        total_fetched += fetched

    print("-" * 50)
    overall_progress = (total_fetched / total_all * 100) if total_all > 0 else 0
    print(f"{'合計':<8} {total_all:>12,} {total_fetched:>12,} {overall_progress:>9.1f}%")
    print()

    # 残りレース数
    remaining = total_all - total_fetched
    print(f"残りレース数: {remaining:,}件")

    if remaining > 0:
        # 推定残り時間（0.5秒/レース）
        estimated_minutes = remaining * 0.5 / 60
        estimated_hours = estimated_minutes / 60
        print(f"推定残り時間（0.5秒/レース）: {estimated_minutes:.1f}分 ({estimated_hours:.1f}時間)")

    print()

    # 最近取得したレース
    cursor.execute("""
        SELECT r.race_date, r.venue_code, r.race_number, t.fetched_at
        FROM trifecta_odds t
        JOIN races r ON t.race_id = r.id
        WHERE r.race_date BETWEEN '2020-01-01' AND '2024-12-31'
        ORDER BY t.fetched_at DESC
        LIMIT 5
    """)

    recent = cursor.fetchall()
    if recent:
        print("【最近取得したレース（最新5件）】")
        for race_date, venue_code, race_number, fetched_at in recent:
            print(f"  {race_date} {venue_code.zfill(2)}R{race_number} - 取得: {fetched_at}")

    print()
    print("=" * 80)

    conn.close()


if __name__ == '__main__':
    check_progress()
