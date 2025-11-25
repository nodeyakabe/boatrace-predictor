"""
潮位データの欠損状況を詳細分析
"""

import sqlite3
from datetime import datetime

def analyze_tide_data():
    """潮位データの詳細分析"""

    db_path = "data/boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("="*80)
    print("潮位データ欠損分析レポート")
    print("="*80)
    print(f"分析日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # 1. テーブル構造確認
    print("\n【1. 潮位関連テーブル】")

    # rdmdb_tideテーブル
    cursor.execute("SELECT COUNT(*) FROM rdmdb_tide")
    rdmdb_count = cursor.fetchone()[0]
    print(f"  rdmdb_tide: {rdmdb_count:,} レコード（気象庁の潮位データ）")

    if rdmdb_count > 0:
        cursor.execute("SELECT MIN(observation_datetime), MAX(observation_datetime) FROM rdmdb_tide")
        min_date, max_date = cursor.fetchone()
        print(f"    期間: {min_date} ～ {max_date}")

    # tideテーブル
    cursor.execute("SELECT COUNT(*) FROM tide")
    tide_count = cursor.fetchone()[0]
    print(f"  tide: {tide_count:,} レコード（処理済み潮位データ）")

    if tide_count > 0:
        cursor.execute("SELECT MIN(tide_date), MAX(tide_date) FROM tide")
        min_date, max_date = cursor.fetchone()
        print(f"    期間: {min_date} ～ {max_date}")

    # race_tide_dataテーブル
    cursor.execute("SELECT COUNT(*) FROM race_tide_data")
    race_tide_count = cursor.fetchone()[0]
    print(f"  race_tide_data: {race_tide_count:,} レコード（レース別潮位データ）")

    if race_tide_count > 0:
        cursor.execute("""
            SELECT MIN(r.race_date), MAX(r.race_date)
            FROM race_tide_data rtd
            JOIN races r ON rtd.race_id = r.id
        """)
        result = cursor.fetchone()
        if result[0]:
            min_date, max_date = result
            print(f"    期間: {min_date} ～ {max_date}")

    # 2. レースと潮位データの関連分析（2015-2021）
    print("\n【2. レース別潮位データ状況（2015-2021）】")

    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
    """)
    total_races = cursor.fetchone()[0]
    print(f"  総レース数: {total_races:,}")

    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        INNER JOIN race_tide_data rtd ON r.id = rtd.race_id
        WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
    """)
    races_with_tide = cursor.fetchone()[0]
    print(f"  潮位データあり: {races_with_tide:,} ({races_with_tide/total_races*100:.1f}%)")
    print(f"  潮位データなし: {total_races - races_with_tide:,} ({(total_races - races_with_tide)/total_races*100:.1f}%)")

    # 3. 会場別潮位データ状況
    print("\n【3. 会場別潮位データ状況（2015-2021）】")

    cursor.execute("""
        SELECT
            r.venue_code,
            COUNT(DISTINCT r.id) as total_races,
            COUNT(DISTINCT rtd.race_id) as races_with_tide
        FROM races r
        LEFT JOIN race_tide_data rtd ON r.id = rtd.race_id
        WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
        GROUP BY r.venue_code
        ORDER BY r.venue_code
    """)

    venue_data = cursor.fetchall()
    print(f"  {'会場':4s} {'総レース':>10s} {'潮位あり':>10s} {'取得率':>8s} {'欠損数':>10s}")
    print("  " + "-"*50)

    total_missing = 0
    for venue_code, total, with_tide in venue_data:
        rate = with_tide / total * 100 if total > 0 else 0
        missing = total - with_tide
        total_missing += missing
        print(f"  {venue_code:4s} {total:10d} {with_tide:10d} {rate:7.1f}% {missing:10d}")

    print("  " + "-"*50)
    print(f"  合計: {total_races:,} レース、欠損: {total_missing:,} レース")

    # 4. 年別潮位データ状況
    print("\n【4. 年別潮位データ状況】")

    cursor.execute("""
        SELECT
            substr(r.race_date, 1, 4) as year,
            COUNT(DISTINCT r.id) as total_races,
            COUNT(DISTINCT rtd.race_id) as races_with_tide
        FROM races r
        LEFT JOIN race_tide_data rtd ON r.id = rtd.race_id
        WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
        GROUP BY substr(r.race_date, 1, 4)
        ORDER BY year
    """)

    year_data = cursor.fetchall()
    print(f"  {'年':6s} {'総レース':>10s} {'潮位あり':>10s} {'取得率':>8s}")
    print("  " + "-"*40)

    for year, total, with_tide in year_data:
        rate = with_tide / total * 100 if total > 0 else 0
        print(f"  {year:6s} {total:10d} {with_tide:10d} {rate:7.1f}%")

    # 5. rdmdb_tideとtideテーブルの関係
    print("\n【5. 気象庁データ（rdmdb_tide）の分析】")

    if rdmdb_count > 0:
        # 観測点別データ数
        cursor.execute("""
            SELECT station_name, COUNT(*) as count
            FROM rdmdb_tide
            GROUP BY station_name
            ORDER BY count DESC
            LIMIT 10
        """)

        station_data = cursor.fetchall()
        print(f"  観測点別データ数（上位10件）:")
        print(f"    {'観測点':20s} {'データ数':>10s}")
        print("    " + "-"*35)
        for station_name, count in station_data:
            print(f"    {station_name:20s} {count:10d}")

        # 日付範囲
        cursor.execute("""
            SELECT
                MIN(DATE(observation_datetime)) as min_date,
                MAX(DATE(observation_datetime)) as max_date,
                COUNT(DISTINCT DATE(observation_datetime)) as date_count
            FROM rdmdb_tide
        """)
        min_date, max_date, date_count = cursor.fetchone()
        print(f"\n  データ期間:")
        print(f"    開始: {min_date}")
        print(f"    終了: {max_date}")
        print(f"    日数: {date_count:,} 日")

    # 6. tideテーブルの詳細
    print("\n【6. 処理済み潮位データ（tide）の分析】")

    if tide_count > 0:
        cursor.execute("""
            SELECT
                venue_code,
                COUNT(*) as count,
                MIN(tide_date) as min_date,
                MAX(tide_date) as max_date
            FROM tide
            GROUP BY venue_code
            ORDER BY venue_code
        """)

        tide_venue_data = cursor.fetchall()
        print(f"  会場別データ数:")
        print(f"    {'会場':4s} {'データ数':>10s} {'開始日':>12s} {'終了日':>12s}")
        print("    " + "-"*45)
        for venue_code, count, min_date, max_date in tide_venue_data:
            print(f"    {venue_code:4s} {count:10d} {min_date:>12s} {max_date:>12s}")

    # 7. 欠損レースのサンプル
    print("\n【7. 潮位データ欠損レースのサンプル（最新10件）】")

    cursor.execute("""
        SELECT
            r.venue_code,
            r.race_date,
            r.race_number,
            r.id
        FROM races r
        LEFT JOIN race_tide_data rtd ON r.id = rtd.race_id
        WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
          AND rtd.race_id IS NULL
        ORDER BY r.race_date DESC, r.venue_code, r.race_number
        LIMIT 10
    """)

    missing_samples = cursor.fetchall()
    if missing_samples:
        print(f"  {'会場':4s} {'日付':12s} {'R':3s} {'ID':8s}")
        print("  " + "-"*30)
        for venue, date, race_num, race_id in missing_samples:
            print(f"  {venue:4s} {date:12s} {race_num:3d} {race_id:8d}")

    conn.close()

    print("\n" + "="*80)
    print("分析完了")
    print("="*80)

    # 推奨事項
    print("\n【推奨事項】")
    print(f"1. 潮位データ欠損レース: {total_missing:,} レース")
    print(f"2. rdmdb_tideデータ: {rdmdb_count:,} レコード（気象庁）")

    if rdmdb_count > 0:
        print("   → 気象庁データは存在します。race_tide_dataへの紐付けが必要")
    else:
        print("   → 気象庁データの取得が必要です")

    if total_missing > 0:
        print(f"\n3. 対応が必要な処理:")
        print(f"   - rdmdb_tideから会場近隣の観測点データを取得")
        print(f"   - tideテーブルにデータを集約")
        print(f"   - race_tide_dataに各レースの潮位情報を紐付け")


if __name__ == '__main__':
    analyze_tide_data()
