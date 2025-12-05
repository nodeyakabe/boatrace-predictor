"""
AI解析用エクスポート機能の簡易テスト
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from config.settings import DATABASE_PATH

def test_query():
    """クエリのテスト"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # データ期間の取得
    cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
    min_date_str, max_date_str = cursor.fetchone()

    print("保有データ期間:", min_date_str, "~", max_date_str)

    # 日付フォーマットを自動判定
    if '-' in min_date_str:
        min_date = datetime.strptime(min_date_str, '%Y-%m-%d').date()
        max_date = datetime.strptime(max_date_str, '%Y-%m-%d').date()
        date_format = '%Y-%m-%d'
    else:
        min_date = datetime.strptime(min_date_str, '%Y%m%d').date()
        max_date = datetime.strptime(max_date_str, '%Y%m%d').date()
        date_format = '%Y%m%d'

    # 最新3ヶ月のデータ
    start_date = max_date - timedelta(days=90)
    end_date = max_date
    start_date_str = start_date.strftime(date_format)
    end_date_str = end_date.strftime(date_format)

    print("テスト期間:", start_date, "~", end_date)

    # レコード数の取得
    query_count = """
        SELECT COUNT(*)
        FROM races r
        JOIN entries e ON r.id = e.race_id
        WHERE r.race_date BETWEEN ? AND ?
    """
    cursor.execute(query_count, (start_date_str, end_date_str))
    total_records = cursor.fetchone()[0]

    estimated_size_mb = total_records * 500 / (1024 * 1024)

    print(f"推定レコード数: {total_records:,}行")
    print(f"推定ファイルサイズ: {estimated_size_mb:.2f} MB")

    # クエリのテスト（サンプル100行）
    query = """
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            v.name as venue_name,
            r.race_number,
            e.pit_number,
            e.racer_name,
            e.racer_rank as racer_class,
            e.win_rate,
            res.rank,
            res.winning_technique as kimarite
        FROM races r
        LEFT JOIN venues v ON r.venue_code = v.code
        LEFT JOIN entries e ON r.id = e.race_id
        LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
        LEFT JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
        LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE r.race_date BETWEEN ? AND ?
        ORDER BY r.race_date, r.venue_code, r.race_number, e.pit_number
        LIMIT 100
    """

    df = pd.read_sql_query(query, conn, params=(start_date_str, end_date_str))

    print(f"\nデータ取得完了: {len(df)}行")
    print("\n先頭5行:")
    print(df.head())

    print("\n統計情報:")
    print(f"ユニークレース数: {df['race_id'].nunique()}")
    print(f"会場数: {df['venue_code'].nunique()}")

    # 各期間のテスト
    print("\n各期間のレコード数:")
    periods = [("3ヶ月", 90), ("6ヶ月", 180), ("1年", 365), ("2年", 730)]

    for period_name, days in periods:
        start_date = max_date - timedelta(days=days)
        start_date_str = start_date.strftime(date_format)

        cursor.execute(query_count, (start_date_str, end_date_str))
        total_records = cursor.fetchone()[0]
        estimated_size_mb = total_records * 500 / (1024 * 1024)

        status = "OK" if estimated_size_mb <= 10 else "WARN"
        print(f"{period_name}: {total_records:,}行, {estimated_size_mb:.2f} MB [{status}]")

    print("\nテスト完了")
    conn.close()


if __name__ == "__main__":
    test_query()
