"""
オッズ取得APIのテストスクリプト
"""
import sys
import os
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.scraper.odds_fetcher import OddsFetcher, generate_mock_odds


def test_odds_fetcher():
    """オッズ取得のテスト"""
    print("=" * 60)
    print("オッズ取得APIテスト")
    print("=" * 60)

    fetcher = OddsFetcher()

    # テスト用のレースデータ
    # 今日または明日のレースを試す
    today = datetime.now()
    tomorrow = today + timedelta(days=1)

    test_dates = [
        today.strftime('%Y%m%d'),
        tomorrow.strftime('%Y%m%d')
    ]

    # いくつかの会場をテスト
    test_venues = [
        ('01', '桐生'),
        ('03', '江戸川'),
        ('20', '若松'),
        ('24', '大村')
    ]

    for race_date in test_dates:
        print(f"\n{'='*60}")
        print(f"日付: {race_date[:4]}/{race_date[4:6]}/{race_date[6:]}")
        print(f"{'='*60}")

        for venue_code, venue_name in test_venues:
            print(f"\n【{venue_name}（{venue_code}）- 1R】")

            # 三連単オッズ取得（上位10件のみ）
            try:
                odds_data = fetcher.fetch_sanrentan_odds_top(
                    race_date=race_date,
                    venue_code=venue_code,
                    race_number=1,
                    top_n=10
                )

                if odds_data and len(odds_data) > 0:
                    print(f"[OK] オッズ取得成功: {len(odds_data)}件")
                    print("\n組み合わせ | オッズ")
                    print("-" * 30)
                    for combo, odd in list(odds_data.items())[:5]:
                        print(f"{combo:>10} | {odd:>6.1f}倍")
                    return True  # 成功したら終了
                else:
                    print("[WARN] オッズデータが空です")

            except Exception as e:
                print(f"[ERROR] エラー: {e}")

    print("\n" + "=" * 60)
    print("リアルAPIからの取得に失敗しました")
    print("モックオッズ生成機能をテストします")
    print("=" * 60)

    # モックオッズのテスト
    mock_predictions = [
        {'combination': '1-2-3', 'prob': 0.15},
        {'combination': '1-2-4', 'prob': 0.12},
        {'combination': '1-3-2', 'prob': 0.10},
        {'combination': '2-1-3', 'prob': 0.08},
        {'combination': '1-4-2', 'prob': 0.07},
    ]

    print("\nテスト予測データ:")
    for pred in mock_predictions:
        print(f"  {pred['combination']}: 確率 {pred['prob']:.1%}")

    mock_odds = generate_mock_odds(mock_predictions)

    print("\n生成されたモックオッズ:")
    print("\n組み合わせ | オッズ | 市場確率")
    print("-" * 40)
    for combo, odd in mock_odds.items():
        implied_prob = 1.0 / odd
        print(f"{combo:>10} | {odd:>6.1f}倍 | {implied_prob:>6.1%}")

    print("\n[OK] モックオッズ生成は正常に動作しています")

    return False


if __name__ == "__main__":
    success = test_odds_fetcher()

    print("\n" + "=" * 60)
    if success:
        print("[OK] リアルタイムオッズ取得に成功しました")
    else:
        print("[WARN] リアルタイムオッズ取得は失敗しました")
        print("モックオッズを使用してください")
    print("=" * 60)
