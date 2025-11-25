"""
今日のレースがデータベースに保存されているか確認
"""
import sqlite3
from datetime import datetime
from config.settings import DATABASE_PATH, VENUES

def check_today_races():
    """今日のレースをデータベースから確認"""
    today = datetime.now().strftime('%Y%m%d')

    print("="*70)
    print(f"今日のレースデータ確認: {today}")
    print("="*70)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 今日のレースを取得
    cursor.execute("""
        SELECT
            venue_code,
            race_number,
            race_time
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
    """, (today,))

    races = cursor.fetchall()

    if races:
        print(f"\n[OK] 今日のレースが {len(races)} 件見つかりました")
        print()

        # 会場ごとに集計
        venue_counts = {}
        for venue_code, race_number, race_time in races:
            if venue_code not in venue_counts:
                venue_counts[venue_code] = []
            venue_counts[venue_code].append(race_number)

        # 会場名を取得して表示
        for venue_code in sorted(venue_counts.keys()):
            venue_name = None
            for venue_id, venue_info in VENUES.items():
                if venue_info['code'] == venue_code:
                    venue_name = venue_info['name']
                    break

            race_numbers = venue_counts[venue_code]
            print(f"  会場 {venue_code} ({venue_name}): {len(race_numbers)}R (R{min(race_numbers)}～R{max(race_numbers)})")

        # 最初の5レースを詳細表示
        print("\n最初の5レース:")
        for i, (venue_code, race_number, race_time) in enumerate(races[:5], 1):
            print(f"  {i}. 会場{venue_code} {race_number}R {race_time or '時刻未設定'}")

        # エントリー情報も確認
        print("\n" + "="*70)
        print("エントリー情報の確認")
        print("="*70)

        cursor.execute("""
            SELECT COUNT(*)
            FROM entries e
            JOIN races r ON e.race_id = r.id
            WHERE r.race_date = ?
        """, (today,))

        entry_count = cursor.fetchone()[0]

        if entry_count > 0:
            print(f"[OK] エントリー情報: {entry_count} 件")

            # 最初のレースのエントリーを確認
            first_race = races[0]
            cursor.execute("""
                SELECT
                    e.pit_number,
                    e.racer_name,
                    e.racer_number
                FROM entries e
                JOIN races r ON e.race_id = r.id
                WHERE r.race_date = ? AND r.venue_code = ? AND r.race_number = ?
                ORDER BY e.pit_number
            """, (today, first_race[0], first_race[1]))

            entries = cursor.fetchall()
            if entries:
                print(f"\n最初のレース (会場{first_race[0]} {first_race[1]}R) のエントリー:")
                for pit, name, racer_num in entries:
                    print(f"  {pit}号艇: {name} ({racer_num})")
        else:
            print("[NG] エントリー情報がありません")
            print("     → データ取得が不完全な可能性があります")

    else:
        print(f"\n[NG] 今日のレースが見つかりません")
        print(f"     データベース: {DATABASE_PATH}")
        print(f"     検索日付: {today}")

        # 最新のレースを確認
        cursor.execute("""
            SELECT race_date, COUNT(*) as count
            FROM races
            GROUP BY race_date
            ORDER BY race_date DESC
            LIMIT 5
        """)

        recent_dates = cursor.fetchall()

        if recent_dates:
            print("\n最近のレースデータ:")
            for date, count in recent_dates:
                print(f"  {date}: {count}レース")
        else:
            print("\nデータベースにレースデータが全くありません")

    conn.close()

    print("\n" + "="*70)


if __name__ == "__main__":
    check_today_races()
