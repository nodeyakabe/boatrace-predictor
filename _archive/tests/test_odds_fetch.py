"""
オッズ取得機能のテストスクリプト（DB保存機能付き）
"""
from src.scraper.auto_odds_fetcher import AutoOddsFetcher
from datetime import datetime
import sqlite3
from config.settings import DATABASE_PATH

def test_single_race():
    """個別レースのオッズ取得テスト"""
    print("="*70)
    print("個別レースオッズ取得テスト（DB保存機能付き）")
    print("="*70)

    # 今日開催されているレースを検索
    today = datetime.now().strftime('%Y-%m-%d')
    race_date_fmt = datetime.now().strftime('%Y%m%d')

    print(f"\n今日の日付: {today}")
    print("今日開催されているレースを検索中...")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, venue_code, race_number, race_time
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
        LIMIT 5
    """, (today,))

    races = cursor.fetchall()

    if not races:
        print(f"\n⚠️ {today} のレースが見つかりませんでした")
        print("デフォルトで桐生1Rをテストします（オッズ未発表の可能性あり）")
        venue_code = "01"
        race_number = 1
        race_id = None
    else:
        print(f"\n✅ 今日のレース {len(races)}件を発見")
        for race in races:
            race_id_tmp, venue_code_tmp, race_number_tmp, race_time = race
            print(f"  - 会場{venue_code_tmp} {race_number_tmp}R ({race_time or '時刻未定'})")

        # 最初のレースでテスト
        race_id, venue_code, race_number, race_time = races[0]

    print(f"\n{'='*70}")
    print(f"テスト対象: 会場{venue_code} {race_number}R")
    print("="*70)

    try:
        from src.scraper.odds_scraper import OddsScraper

        scraper = OddsScraper()

        # 3連単オッズ取得
        print("\n[1] 3連単オッズ取得テスト")
        print(f"  会場コード: {venue_code}")
        print(f"  レース番号: {race_number}")
        print(f"  日付: {race_date_fmt}")

        trifecta = scraper.get_trifecta_odds(venue_code, race_date_fmt, race_number)

        if trifecta:
            print(f"\n✅ 取得成功: {len(trifecta)}通り")

            # 人気上位5つを表示
            sorted_odds = sorted(trifecta.items(), key=lambda x: x[1])[:5]
            print("\n人気上位5つ:")
            for combo, odds in sorted_odds:
                print(f"  {combo}: {odds}倍")

            # データベースに保存
            if race_id:
                print(f"\n[DB保存] race_id={race_id} にオッズを保存中...")
                saved_count = 0
                for combination, odds in trifecta.items():
                    try:
                        cursor.execute("""
                            INSERT OR REPLACE INTO trifecta_odds
                            (race_id, combination, odds, fetched_at)
                            VALUES (?, ?, ?, ?)
                        """, (race_id, combination, odds, datetime.now()))
                        saved_count += 1
                    except Exception as e:
                        print(f"  ⚠️ 保存エラー ({combination}): {e}")

                conn.commit()
                print(f"✅ {saved_count}件のオッズを保存しました")

                # 保存確認
                cursor.execute("""
                    SELECT COUNT(*) FROM trifecta_odds
                    WHERE race_id = ?
                """, (race_id,))
                count = cursor.fetchone()[0]
                print(f"データベース確認: {count}件のオッズが保存されています")
            else:
                print("\n⚠️ race_idが不明なため、DB保存をスキップしました")

        else:
            print("❌ 取得失敗（オッズ未発表の可能性があります）")

        # 単勝オッズ取得
        print("\n[2] 単勝オッズ取得テスト")
        win_odds = scraper.get_win_odds(venue_code, race_date_fmt, race_number)

        if win_odds:
            print("✅ 取得成功: 6艇")
            print("\n単勝オッズ:")
            for pit, odds in sorted(win_odds.items()):
                print(f"  {pit}号艇: {odds}倍")

            # データベースに保存
            if race_id:
                print(f"\n[DB保存] race_id={race_id} に単勝オッズを保存中...")
                saved_count = 0
                for pit_number, odds in win_odds.items():
                    try:
                        cursor.execute("""
                            INSERT OR REPLACE INTO win_odds
                            (race_id, pit_number, odds, fetched_at)
                            VALUES (?, ?, ?, ?)
                        """, (race_id, int(pit_number), odds, datetime.now()))
                        saved_count += 1
                    except Exception as e:
                        print(f"  ⚠️ 保存エラー ({pit_number}号艇): {e}")

                conn.commit()
                print(f"✅ {saved_count}艇分のオッズを保存しました")
        else:
            print("❌ 取得失敗（オッズ未発表の可能性があります）")

        scraper.close()

    except Exception as e:
        print(f"\n❌ エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

    print("\n" + "="*70)
    print("テスト完了")
    print("="*70)


if __name__ == "__main__":
    test_single_race()

    print("\n")
    print("="*70)
    print("注意事項")
    print("="*70)
    print("- オッズはレース開始前に公開されます")
    print("- 公開前のレースは取得できません")
    print("- 本日開催がない場合は別の日付でテストしてください")
    print("="*70)
