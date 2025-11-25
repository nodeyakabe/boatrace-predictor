"""
オッズ取得機能のテストスクリプト
"""
from src.scraper.auto_odds_fetcher import AutoOddsFetcher
from datetime import datetime

def test_single_race():
    """個別レースのオッズ取得テスト"""
    print("="*70)
    print("個別レースオッズ取得テスト")
    print("="*70)

    # 桐生の今日のレースでテスト
    venue_code = "01"  # 桐生
    race_date = datetime.now().strftime('%Y%m%d')
    race_number = 1

    print(f"\n会場: {venue_code} (桐生)")
    print(f"日付: {race_date}")
    print(f"レース: {race_number}R")

    try:
        from src.scraper.odds_scraper import OddsScraper

        scraper = OddsScraper()

        # 3連単オッズ取得
        print("\n[1] 3連単オッズ取得テスト")
        trifecta = scraper.get_trifecta_odds(venue_code, race_date, race_number)

        if trifecta:
            print(f"✅ 取得成功: {len(trifecta)}通り")
            # 人気上位5つを表示
            sorted_odds = sorted(trifecta.items(), key=lambda x: x[1])[:5]
            print("\n人気上位5つ:")
            for combo, odds in sorted_odds:
                print(f"  {combo}: {odds}倍")
        else:
            print("❌ 取得失敗（オッズ未発表の可能性があります）")

        # 単勝オッズ取得
        print("\n[2] 単勝オッズ取得テスト")
        win_odds = scraper.get_win_odds(venue_code, race_date, race_number)

        if win_odds:
            print("✅ 取得成功: 6艇")
            print("\n単勝オッズ:")
            for pit, odds in sorted(win_odds.items()):
                print(f"  {pit}号艇: {odds}倍")
        else:
            print("❌ 取得失敗（オッズ未発表の可能性があります）")

        scraper.close()

    except Exception as e:
        print(f"\n❌ エラー: {e}")
        import traceback
        traceback.print_exc()

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
