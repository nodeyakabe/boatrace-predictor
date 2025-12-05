"""
AI解析用エクスポート機能のテストスクリプト
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from config.settings import DATABASE_PATH

# 決まり手の名称マッピング
KIMARITE_NAMES = {
    1: "逃げ",
    2: "差し",
    3: "まくり",
    4: "まくり差し",
    5: "抜き",
    6: "恵まれ"
}

def test_ai_export():
    """AI解析用エクスポート機能のテスト"""
    print("=" * 80)
    print("AI解析用エクスポート機能のテスト開始")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # データ期間の取得
    cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
    min_date_str, max_date_str = cursor.fetchone()

    if not min_date_str or not max_date_str:
        print("[ERROR] データベースにレースデータが存在しません")
        conn.close()
        return

    # 日付フォーマットを自動判定
    if '-' in min_date_str:
        # YYYY-MM-DD形式
        min_date = datetime.strptime(min_date_str, '%Y-%m-%d').date()
        max_date = datetime.strptime(max_date_str, '%Y-%m-%d').date()
        date_format = '%Y-%m-%d'
    else:
        # YYYYMMDD形式
        min_date = datetime.strptime(min_date_str, '%Y%m%d').date()
        max_date = datetime.strptime(max_date_str, '%Y%m%d').date()
        date_format = '%Y%m%d'

    print(f"\n📅 保有データ期間: {min_date} ~ {max_date}")

    # テスト1: 最新3ヶ月のデータ
    print("\n" + "=" * 80)
    print("テスト1: 最新3ヶ月のデータエクスポート")
    print("=" * 80)

    start_date = max_date - timedelta(days=90)
    end_date = max_date
    start_date_str = start_date.strftime(date_format)
    end_date_str = end_date.strftime(date_format)

    print(f"期間: {start_date} ~ {end_date}")

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

    if estimated_size_mb > 10:
        print("⚠️ 10MBを超えています")
    else:
        print("✅ 10MB以内")

    # 統合クエリの実行
    print("\nデータを統合中...")
    query = """
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            v.name as venue_name,
            r.race_number,
            r.race_time,

            e.pit_number,
            e.racer_number,
            e.racer_name,
            e.racer_class,
            e.win_rate,
            e.second_rate,

            e.motor_number,
            rd.motor_2tan_rate,
            e.boat_number,
            rd.exhibition_time,
            rd.actual_course,
            rd.st_time,
            rd.tilt_angle,

            w.temperature,
            w.weather_condition,
            w.wind_speed,
            w.wind_direction,
            w.wave_height,
            w.water_temperature,

            res.rank,
            res.winning_technique as kimarite,
            res.trifecta_odds as odds

        FROM races r
        LEFT JOIN venues v ON r.venue_code = v.code
        LEFT JOIN entries e ON r.id = e.race_id
        LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
        LEFT JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
        LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number

        WHERE r.race_date BETWEEN ? AND ?
        ORDER BY r.race_date, r.venue_code, r.race_number, e.pit_number
        LIMIT 1000
    """

    df = pd.read_sql_query(query, conn, params=(start_date_str, end_date_str))

    # 決まり手の名称を追加
    df['kimarite_name'] = df['kimarite'].map(KIMARITE_NAMES)

    print(f"✅ データ統合完了: {len(df):,}行（サンプル1000行）")

    # データプレビュー
    print("\n" + "=" * 80)
    print("データプレビュー（最初の5行）")
    print("=" * 80)
    print(df.head())

    # 統計情報
    print("\n" + "=" * 80)
    print("統計情報")
    print("=" * 80)
    print(f"ユニークレース数: {df['race_id'].nunique():,}")
    print(f"会場数: {df['venue_code'].nunique()}")
    print(f"選手数: {df['racer_number'].nunique():,}")
    print(f"結果データ: {df['rank'].notna().sum():,}")

    # データ品質チェック
    print("\n" + "=" * 80)
    print("データ品質チェック")
    print("=" * 80)

    null_counts = df.isnull().sum()
    print("\n欠損値の多い項目:")
    for col in null_counts[null_counts > 0].sort_values(ascending=False).head(10).index:
        null_rate = null_counts[col] / len(df) * 100
        print(f"  {col}: {null_counts[col]:,}行 ({null_rate:.1f}%)")

    # テスト2: 他の期間のレコード数確認
    print("\n" + "=" * 80)
    print("テスト2: 各期間のレコード数確認")
    print("=" * 80)

    periods = [
        ("最新6ヶ月", 180),
        ("最新1年", 365),
        ("最新2年", 730),
    ]

    for period_name, days in periods:
        start_date = max_date - timedelta(days=days)
        start_date_str = start_date.strftime(date_format)

        cursor.execute(query_count, (start_date_str, end_date_str))
        total_records = cursor.fetchone()[0]
        estimated_size_mb = total_records * 500 / (1024 * 1024)

        status = "✅" if estimated_size_mb <= 10 else "⚠️"
        print(f"{period_name}: {total_records:,}行, {estimated_size_mb:.2f} MB {status}")

    print("\n" + "=" * 80)
    print("✅ テスト完了")
    print("=" * 80)

    conn.close()


if __name__ == "__main__":
    test_ai_export()
