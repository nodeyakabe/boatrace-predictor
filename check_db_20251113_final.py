"""
2025-11-13のデータがDBに正しく保存されているか確認 (最終版)
"""

from src.database.data_manager import DataManager
import sqlite3

def check_database():
    """DBの確認"""
    print("=" * 70)
    print("2025-11-13のデータベース確認 (最終版)")
    print("=" * 70)

    # 正しい日付フォーマット (ハイフン区切り)
    target_date = "2025-11-13"
    venue_code = "10"  # 若松

    # レースデータの確認
    print(f"\n[1] レースデータの確認")
    print(f"対象: {target_date} 若松（{venue_code}）")

    try:
        conn = sqlite3.connect('data/boatrace.db')
        cursor = conn.cursor()

        query = """
        SELECT r.id, r.race_number, r.race_time, COUNT(e.id) as entry_count
        FROM races r
        LEFT JOIN entries e ON r.id = e.race_id
        WHERE r.venue_code = ? AND r.race_date = ?
        GROUP BY r.id, r.race_number, r.race_time
        ORDER BY r.race_number
        """

        cursor.execute(query, (venue_code, target_date))
        results = cursor.fetchall()

        if results:
            print(f"\n  見つかりました: {len(results)}レース\n")
            for race_id, race_num, race_time, entry_count in results:
                print(f"  {race_num}R: [OK] 選手数={entry_count}名 (時刻={race_time})")
        else:
            print("\n  [NG] レースデータが見つかりません")

        # オリジナル展示データの確認
        print(f"\n[2] オリジナル展示データの確認")
        print(f"    (chikusen_time, isshu_time, mawariashi_time)")

        query = """
        SELECT r.race_number,
               COUNT(CASE WHEN rd.chikusen_time IS NOT NULL THEN 1 END) as chikusen_count,
               COUNT(CASE WHEN rd.isshu_time IS NOT NULL THEN 1 END) as isshu_count,
               COUNT(CASE WHEN rd.mawariashi_time IS NOT NULL THEN 1 END) as mawari_count
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        WHERE r.venue_code = ? AND r.race_date = ?
        GROUP BY r.race_number
        ORDER BY r.race_number
        """

        cursor.execute(query, (venue_code, target_date))
        tenji_results = cursor.fetchall()

        if tenji_results:
            print(f"\n  見つかりました: {len(tenji_results)}レース\n")
            for race_num, chikusen, isshu, mawari in tenji_results:
                if chikusen > 0 or isshu > 0 or mawari > 0:
                    print(f"  {race_num}R: [OK] 直線={chikusen}艇, 一周={isshu}艇, まわり足={mawari}艇")
                else:
                    print(f"  {race_num}R: [INFO] オリジナル展示データなし")
        else:
            print("\n  [NG] オリジナル展示データが見つかりません")

        conn.close()

        print("\n" + "=" * 70)
        print("確認完了")
        print("=" * 70)

        if results and len(results) == 12:
            print(f"\n[OK] 2025-11-13のデータが正常に保存されています！")
            print(f"  - レースデータ: 12/12レース")
            print(f"  - オリジナル展示: {len(tenji_results)}/12レース")
            return True
        else:
            print(f"\n[NG] データが不足しています")
            return False

    except Exception as e:
        print(f"\n[ERROR] エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    check_database()
