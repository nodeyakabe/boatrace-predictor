"""
RealtimePredictorのテスト
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.analysis.realtime_predictor import RealtimePredictor

def test_get_today_races():
    """今日のレース取得テスト"""
    print("="*70)
    print("RealtimePredictor - 今日のレース取得テスト")
    print("="*70)

    try:
        predictor = RealtimePredictor()
        today_races = predictor.get_today_races()

        if today_races:
            print(f"\n[OK] 今日のレースが {len(today_races)} 件見つかりました")

            # 会場ごとに集計
            venue_counts = {}
            for race in today_races:
                venue_code = race['venue_code']
                if venue_code not in venue_counts:
                    venue_counts[venue_code] = {
                        'venue_name': race['venue_name'],
                        'races': []
                    }
                venue_counts[venue_code]['races'].append(race['race_number'])

            print("\n会場別レース数:")
            for venue_code in sorted(venue_counts.keys()):
                venue_info = venue_counts[venue_code]
                print(f"  {venue_code} ({venue_info['venue_name']}): {len(venue_info['races'])}R")

            # 最初の5レースを表示
            print("\n最初の5レース:")
            for i, race in enumerate(today_races[:5], 1):
                print(f"  {i}. {race['venue_name']} {race['race_number']}R "
                      f"({race['race_time']}) - {race['status']}")

            predictor.close()
            return True

        else:
            print("\n[NG] 今日のレースが見つかりません")
            predictor.close()
            return False

    except Exception as e:
        print(f"\n[NG] エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_today_summary():
    """今日のサマリー取得テスト"""
    print("\n" + "="*70)
    print("RealtimePredictor - サマリー取得テスト")
    print("="*70)

    try:
        predictor = RealtimePredictor()
        summary = predictor.get_today_predictions_summary()

        print(f"\n総レース数: {summary['total_races']}")
        print(f"これから: {summary['upcoming_races']}")
        print(f"終了: {summary['finished_races']}")

        if summary['venues']:
            print("\n会場別:")
            for venue in summary['venues']:
                print(f"  {venue['venue_name']}: 全{venue['total']}R "
                      f"(これから{venue['upcoming']}R, 終了{venue['finished']}R)")

        predictor.close()
        return True

    except Exception as e:
        print(f"\n[NG] エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "#"*70)
    print("# RealtimePredictor動作テスト")
    print("#"*70)

    results = []

    # テスト1: 今日のレース取得
    results.append(("今日のレース取得", test_get_today_races()))

    # テスト2: サマリー取得
    results.append(("サマリー取得", test_get_today_summary()))

    # 結果サマリー
    print("\n" + "="*70)
    print("テスト結果サマリー")
    print("="*70)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test_name}")

    total_tests = len(results)
    passed_tests = sum(1 for _, result in results if result)

    print(f"\n合計: {passed_tests}/{total_tests} テスト成功")

    if passed_tests == total_tests:
        print("\n[SUCCESS] 全テスト成功！UIのレース予想が正常に動作する見込みです。")
    else:
        print("\n[WARNING] 一部テストが失敗しました。")

    print("\n" + "#"*70)
