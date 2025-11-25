"""
オッズスクレイパーのテストスクリプト

改善されたOddsScraperクラスの機能を検証
"""

import sys
sys.path.append('.')

from src.scraper.odds_scraper import OddsScraper
from datetime import datetime, timedelta


def test_odds_scraper():
    """オッズスクレイパーの基本機能テスト"""

    print("=" * 60)
    print("オッズスクレイパー 機能テスト")
    print("=" * 60)

    # OddsScraper初期化（delay=1秒, max_retries=3回）
    scraper = OddsScraper(delay=1.0, max_retries=3)

    # テスト用パラメータ
    # 今日 or 明日のレース（データがある可能性が高い）
    today = datetime.now()
    tomorrow = today + timedelta(days=1)

    test_cases = [
        # (venue_code, race_date, race_number, description)
        ('01', tomorrow.strftime('%Y%m%d'), 1, '桐生 1R (明日)'),
        ('24', tomorrow.strftime('%Y%m%d'), 1, '大村 1R (明日)'),
        ('01', today.strftime('%Y%m%d'), 12, '桐生 12R (今日)'),
    ]

    results = []

    for venue_code, race_date, race_number, description in test_cases:
        print(f"\n[テストケース] {description}")
        print(f"  会場: {venue_code}, 日付: {race_date}, R: {race_number}")
        print("-" * 60)

        try:
            # 3連単オッズを取得
            odds_data = scraper.get_trifecta_odds(venue_code, race_date, race_number)

            if odds_data:
                print(f"  [成功] {len(odds_data)}通りのオッズを取得")

                # 人気上位5件を表示
                sorted_odds = sorted(odds_data.items(), key=lambda x: x[1])
                print(f"\n  【人気上位5件】")
                for i, (combo, odds) in enumerate(sorted_odds[:5], 1):
                    print(f"    {i}. {combo}: {odds:.1f}倍")

                results.append({
                    'test': description,
                    'status': 'SUCCESS',
                    'odds_count': len(odds_data)
                })
            else:
                print(f"  [情報なし] オッズ未発表またはデータなし")
                results.append({
                    'test': description,
                    'status': 'NO_DATA',
                    'odds_count': 0
                })

        except Exception as e:
            print(f"  [エラー] {e}")
            import traceback
            traceback.print_exc()
            results.append({
                'test': description,
                'status': 'ERROR',
                'odds_count': 0
            })

    # サマリー表示
    print("\n" + "=" * 60)
    print("テスト結果サマリー")
    print("=" * 60)

    success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
    no_data_count = sum(1 for r in results if r['status'] == 'NO_DATA')
    error_count = sum(1 for r in results if r['status'] == 'ERROR')

    print(f"  成功: {success_count}/{len(results)}")
    print(f"  データなし: {no_data_count}/{len(results)}")
    print(f"  エラー: {error_count}/{len(results)}")

    print("\n[詳細]")
    for result in results:
        status_icon = {
            'SUCCESS': '[OK]',
            'NO_DATA': '[--]',
            'ERROR': '[NG]'
        }.get(result['status'], '[??]')

        print(f"  {status_icon} {result['test']}: {result['odds_count']}通り")

    # リソースクローズ
    scraper.close()

    print("\n" + "=" * 60)

    # テスト結果判定
    if success_count > 0:
        print("[OK] オッズスクレイパーは正常に動作しています")
        return True
    elif no_data_count == len(results):
        print("[INFO] 全てのテストケースでデータなし（レース未開催の可能性）")
        return True
    else:
        print("[WARNING] オッズ取得に失敗しました")
        return False


def test_popular_combinations():
    """人気順上位取得のテスト"""

    print("\n" + "=" * 60)
    print("人気順上位取得テスト")
    print("=" * 60)

    scraper = OddsScraper(delay=0.5, max_retries=2)

    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y%m%d')

    print(f"\n[テスト] 桐生 1R (明日) - 人気上位10件")
    print("-" * 60)

    try:
        popular = scraper.get_popular_combinations('01', tomorrow, 1, top_n=10)

        if popular:
            print(f"  [成功] {len(popular)}件取得\n")
            for item in popular:
                print(f"    {item['rank']:2d}位. {item['combination']}: {item['odds']:6.1f}倍")
        else:
            print(f"  [情報なし] データなし")

    except Exception as e:
        print(f"  [エラー] {e}")
        import traceback
        traceback.print_exc()

    scraper.close()


if __name__ == '__main__':
    # 基本機能テスト
    success = test_odds_scraper()

    # 人気順取得テスト
    test_popular_combinations()

    print("\n" + "=" * 60)
    print("全テスト完了")
    print("=" * 60)

    sys.exit(0 if success else 1)
