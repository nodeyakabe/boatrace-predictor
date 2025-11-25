"""
2025-11-13のデータがDBに正しく保存されているか確認 (改訂版)
"""

from src.database.data_manager import DataManager
import sqlite3

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

    # オリジナル展示データの確認 (race_detailsテーブル内)
    print(f"\n[2] オリジナル展示データの確認")
    print(f"    (race_detailsテーブルのchikusen_time, isshu_time, mawariashi_time)")

    try:
        conn = sqlite3.connect('data/boatrace.db')
        cursor = conn.cursor()

        # race_detailsテーブルからオリジナル展示データを取得
        # races.idとrace_detailsを結合
        query = """
        SELECT rd.pit_number, rd.chikusen_time, rd.isshu_time, rd.mawariashi_time
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.venue_code = ? AND r.race_date = ? AND r.race_number = ?
        ORDER BY rd.pit_number
        """

        tenji_data_found = 0
        for race_num in range(1, 13):
            cursor.execute(query, (venue_code, target_date, race_num))
            results = cursor.fetchall()

            if results:
                has_tenji = False
                for pit, chikusen, isshu, mawari in results:
                    if chikusen is not None or isshu is not None or mawari is not None:
                        has_tenji = True
                        break

                if has_tenji:
                    tenji_data_found += 1
                    print(f"  {race_num}R: [OK] オリジナル展示データあり")

        print(f"\nオリジナル展示データ保存状況: {tenji_data_found}/12レース")

        conn.close()

    except Exception as e:
        print(f"  [ERROR] オリジナル展示データ確認エラー: {e}")

    print("\n" + "=" * 70)
    print("確認完了")
    print("=" * 70)

    # サマリー
    print(f"\n[サマリー]")
    print(f"  レースデータ: {races_found}/12レース")
    print(f"  オリジナル展示: {tenji_data_found}/12レース")

    if races_found == 12 and tenji_data_found == 12:
        print(f"\n[OK] すべてのデータが正常に保存されています！")
        return True
    elif races_found == 12:
        print(f"\n[INFO] レースデータは保存済み。オリジナル展示データが不足しています。")
        return False
    else:
        print(f"\n[NG] データが不足しています。")
        return False


if __name__ == "__main__":
    check_database()
