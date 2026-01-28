"""
公式サイトから実際のオッズを取得して、DBと比較
"""
import sys
sys.path.append(r'c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032')

from src.scraper.odds_scraper import OddsScraper
import sqlite3

DB_PATH = r'c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db'

def check_odds(venue_code, race_date, race_number, expected_combination):
    """
    公式サイトからオッズを取得してDBと比較
    """
    print("=" * 80)
    print(f"【調査】{race_date} venue={venue_code} R{race_number}")
    print("=" * 80)

    # 公式サイトから取得
    scraper = OddsScraper(delay=1.0)
    live_odds = scraper.get_trifecta_odds(str(venue_code).zfill(2), race_date, race_number)

    print(f"\n公式サイトから取得したオッズ（最初の20件、オッズ低い順）:")
    if live_odds:
        sorted_odds = sorted(live_odds.items(), key=lambda x: x[1])
        for i, (combo, odds) in enumerate(sorted_odds[:20], 1):
            marker = " ← 予想買い目" if combo == expected_combination else ""
            print(f"  {i:2d}. {combo}: {odds:6.1f}倍{marker}")

        # 予想買い目のオッズ
        if expected_combination in live_odds:
            print(f"\n[OK] 予想買い目 {expected_combination} のオッズ: {live_odds[expected_combination]}倍")
        else:
            print(f"\n[NG] 予想買い目 {expected_combination} のオッズが見つかりません")
    else:
        print("  ⚠️ オッズが取得できませんでした（過去レースのためオッズ削除済み？）")

    # DBから取得
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # race_id取得
    cursor.execute("""
        SELECT id FROM races
        WHERE race_date = ? AND venue_code = ? AND race_number = ?
    """, (race_date, venue_code, race_number))
    row = cursor.fetchone()

    if not row:
        print("\n[NG] DBにレースが存在しません")
        conn.close()
        return

    race_id = row[0]
    print(f"\nrace_id: {race_id}")

    # DB保存オッズ（最初の20件）
    cursor.execute("""
        SELECT combination, odds
        FROM trifecta_odds
        WHERE race_id = ?
        ORDER BY odds ASC
        LIMIT 20
    """, (race_id,))
    db_odds = cursor.fetchall()

    print(f"\nDB保存オッズ（最初の20件、オッズ低い順）:")
    for i, (combo, odds) in enumerate(db_odds, 1):
        marker = " ← 予想買い目" if combo == expected_combination else ""
        print(f"  {i:2d}. {combo}: {odds:6.1f}倍{marker}")

    # 予想買い目のDB保存オッズ
    cursor.execute("""
        SELECT combination, odds
        FROM trifecta_odds
        WHERE race_id = ? AND combination = ?
    """, (race_id, expected_combination))
    db_target = cursor.fetchone()

    if db_target:
        print(f"\n[OK] DB保存の予想買い目 {expected_combination}: {db_target[1]}倍")
    else:
        print(f"\n[NG] DB保存の予想買い目 {expected_combination} が見つかりません")

    conn.close()
    print()


if __name__ == '__main__':
    # 徳山8R (2026-01-18, venue_code=18, race_number=8, 予想1-2-5)
    check_odds(18, '2026-01-18', 8, '1-2-5')

    # 大村11R (2026-01-15, venue_code=24, race_number=11, 予想1-2-4)
    check_odds(24, '2026-01-15', 11, '1-2-4')
