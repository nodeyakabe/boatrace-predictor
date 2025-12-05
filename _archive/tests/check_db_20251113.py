"""
2025-11-13のデータがDBに正しく保存されているか確認
"""

from src.database.data_manager import DataManager
from datetime import datetime

def check_database():
    """DBの確認"""
    print("=" * 70)
    print("2025-11-13のデータベース確認")
    print("=" * 70)

    dm = DataManager()
    target_date = "20251113"
    venue_code = "10"  # 若松

    # レースデータの確認
    print(f"\n[1] レースデータの確認")
    print(f"対象: {target_date} 若松（{venue_code}）")

    races_found = 0
    for race_num in range(1, 13):
        try:
            race_data = dm.get_race_data(venue_code, target_date, race_num)
            if race_data:
                races_found += 1
                print(f"  {race_num}R: [OK] データあり（選手数={len(race_data.get('entries', []))}名）")
            else:
                print(f"  {race_num}R: [NG] データなし")
        except Exception as e:
            print(f"  {race_num}R: [ERROR] {e}")

    print(f"\nレースデータ保存状況: {races_found}/12レース")

    # オリジナル展示データの確認
    print(f"\n[2] オリジナル展示データの確認")

    try:
        import sqlite3
        conn = sqlite3.connect('data/boatrace.db')
        cursor = conn.cursor()

        # original_tenji_dataテーブルからデータを取得
        query = """
        SELECT race_number, COUNT(*) as entry_count
        FROM original_tenji_data
        WHERE venue_code = ? AND race_date = ?
        GROUP BY race_number
        ORDER BY race_number
        """

        cursor.execute(query, (venue_code, target_date))
        results = cursor.fetchall()

        if results:
            print(f"  オリジナル展示データが見つかりました:")
            for race_num, count in results:
                print(f"    {race_num}R: {count}艇のデータ")
            print(f"\n  合計: {len(results)}レース")
        else:
            print("  [NG] オリジナル展示データが見つかりません")

        conn.close()

    except Exception as e:
        print(f"  [ERROR] オリジナル展示データ確認エラー: {e}")

    # 事前情報データの確認
    print(f"\n[3] 事前情報データの確認")

    try:
        conn = sqlite3.connect('data/boatrace.db')
        cursor = conn.cursor()

        # before_infoテーブルからデータを取得
        query = """
        SELECT race_number, COUNT(*) as entry_count
        FROM before_info
        WHERE venue_code = ? AND race_date = ?
        GROUP BY race_number
        ORDER BY race_number
        """

        cursor.execute(query, (venue_code, target_date))
        results = cursor.fetchall()

        if results:
            print(f"  事前情報データが見つかりました:")
            for race_num, count in results:
                print(f"    {race_num}R: {count}艇のデータ")
            print(f"\n  合計: {len(results)}レース")
        else:
            print("  [INFO] 事前情報データが見つかりません（未取得の可能性あり）")

        conn.close()

    except Exception as e:
        print(f"  [ERROR] 事前情報データ確認エラー: {e}")

    print("\n" + "=" * 70)
    print("確認完了")
    print("=" * 70)


if __name__ == "__main__":
    check_database()
