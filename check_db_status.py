"""
データベースの詳細な状況を確認するスクリプト
"""

import sqlite3
from datetime import datetime

def main():
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    print("=" * 80)
    print("データベース状況レポート")
    print("=" * 80)

    # 基本統計
    print("\n【基本統計】")
    cursor.execute('SELECT COUNT(*) FROM races')
    print(f"  総レース数: {cursor.fetchone()[0]:,}")

    cursor.execute('SELECT COUNT(*) FROM entries')
    print(f"  出走表エントリ数: {cursor.fetchone()[0]:,}")

    cursor.execute('SELECT COUNT(*) FROM results')
    print(f"  レース結果データ数: {cursor.fetchone()[0]:,}")

    cursor.execute('SELECT COUNT(*) FROM weather')
    print(f"  天気データ数: {cursor.fetchone()[0]:,}")

    # race_detailsテーブルの確認
    print("\n【race_detailsテーブル】")
    cursor.execute('SELECT COUNT(*) FROM race_details')
    total_details = cursor.fetchone()[0]
    print(f"  総レコード数: {total_details:,}")

    cursor.execute('SELECT COUNT(*) FROM race_details WHERE exhibition_time IS NOT NULL')
    print(f"  展示タイムあり: {cursor.fetchone()[0]:,}")

    cursor.execute('SELECT COUNT(*) FROM race_details WHERE actual_course IS NOT NULL')
    print(f"  進入コースあり: {cursor.fetchone()[0]:,}")

    cursor.execute('SELECT COUNT(*) FROM race_details WHERE tilt_angle IS NOT NULL')
    print(f"  チルト角度あり: {cursor.fetchone()[0]:,}")

    cursor.execute('SELECT COUNT(*) FROM race_details WHERE st_time IS NOT NULL')
    print(f"  STタイムあり: {cursor.fetchone()[0]:,}")

    cursor.execute('SELECT COUNT(*) FROM race_details WHERE parts_replacement IS NOT NULL')
    print(f"  部品交換情報あり: {cursor.fetchone()[0]:,}")

    # データ期間
    print("\n【データ期間】")
    cursor.execute('SELECT MIN(race_date), MAX(race_date) FROM races')
    date_range = cursor.fetchone()
    print(f"  {date_range[0]} ～ {date_range[1]}")

    # 競艇場別データ数
    print("\n【競艇場別レース数（上位10場）】")
    cursor.execute("""
        SELECT v.name, COUNT(r.id) as cnt
        FROM venues v
        LEFT JOIN races r ON v.code = r.venue_code
        GROUP BY v.code, v.name
        ORDER BY cnt DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,}レース")

    # 最近のデータ取得日
    print("\n【最近のデータ取得日（直近10日）】")
    cursor.execute("""
        SELECT race_date, COUNT(*) as cnt
        FROM races
        GROUP BY race_date
        ORDER BY race_date DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}レース")

    # データ品質チェック
    print("\n【データ品質チェック】")
    cursor.execute("""
        SELECT
            COUNT(DISTINCT r.id) as total_races,
            COUNT(DISTINCT CASE WHEN rd.exhibition_time IS NOT NULL THEN r.id END) as with_exhibition,
            COUNT(DISTINCT CASE WHEN rd.actual_course IS NOT NULL THEN r.id END) as with_course,
            COUNT(DISTINCT CASE WHEN res.id IS NOT NULL THEN r.id END) as with_result
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        LEFT JOIN results res ON r.id = res.race_id
    """)
    stats = cursor.fetchone()
    total = stats[0]
    if total > 0:
        print(f"  展示タイムあり: {stats[1]:,}/{total:,} ({stats[1]*100/total:.1f}%)")
        print(f"  進入コースあり: {stats[2]:,}/{total:,} ({stats[2]*100/total:.1f}%)")
        print(f"  レース結果あり: {stats[3]:,}/{total:,} ({stats[3]*100/total:.1f}%)")

    # 不足データの確認
    print("\n【不足データの確認】")

    # オッズ/払戻金テーブルの存在確認
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payouts'")
    if cursor.fetchone():
        cursor.execute('SELECT COUNT(*) FROM payouts')
        print(f"  払戻金データ: {cursor.fetchone()[0]:,}件")
    else:
        print(f"  払戻金データ: テーブル未作成（要実装）")

    # STタイムの不足
    cursor.execute("""
        SELECT COUNT(*) FROM race_details WHERE st_time IS NULL AND actual_course IS NOT NULL
    """)
    print(f"  STタイム不足: {cursor.fetchone()[0]:,}レコード")

    # 決まり手の確認
    cursor.execute("PRAGMA table_info(results)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'kimarite' in columns:
        cursor.execute('SELECT COUNT(*) FROM results WHERE kimarite IS NOT NULL')
        print(f"  決まり手データ: {cursor.fetchone()[0]:,}件")
    else:
        print(f"  決まり手データ: カラム未作成（要実装）")

    conn.close()
    print("=" * 80)

if __name__ == "__main__":
    main()
