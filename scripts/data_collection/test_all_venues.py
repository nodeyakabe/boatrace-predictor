"""
全競艇場スクレイパー統合テスト

海水面競艇場（9場）のスクレイパーを一括テストします。
- ファクトリー関数の動作確認
- 各競艇場の潮汐データ取得
- 気象庁潮位データとの統合確認
- 気象データ取得
- 進入コース別成績取得
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.scraper.venue_specific_scraper import create_venue_scraper
from datetime import datetime


def test_all_seawater_venues():
    """全海水面競艇場のテスト"""

    print("=" * 80)
    print("全海水面競艇場スクレイパー 統合テスト")
    print("=" * 80)

    # 海水面競艇場リスト
    seawater_venues = {
        '14': '鳴門',
        '15': '丸亀',
        '16': '児島',
        '17': '宮島',
        '18': '徳山',
        '19': '下関',
        '20': '若松',
        '22': '福岡',
        '23': '唐津',
    }

    test_date = "2026-01-17"

    results = {
        'factory': {'success': 0, 'failed': 0},
        'tide': {'success': 0, 'failed': 0, 'no_data': 0},
        'jma_tide': {'success': 0, 'failed': 0, 'no_data': 0},
        'weather': {'success': 0, 'failed': 0, 'no_data': 0},
        'course': {'success': 0, 'failed': 0, 'no_data': 0}
    }

    for venue_code, venue_name in seawater_venues.items():
        print(f"\n{'=' * 80}")
        print(f"競艇場: {venue_name} (場コード: {venue_code})")
        print("=" * 80)

        # 1. ファクトリー関数テスト
        print(f"\n[1] ファクトリー関数テスト")
        try:
            scraper = create_venue_scraper(venue_code)
            if scraper:
                print(f"  [OK] スクレイパー作成成功: {type(scraper).__name__}")
                results['factory']['success'] += 1
            else:
                print(f"  [NG] スクレイパー作成失敗")
                results['factory']['failed'] += 1
                continue
        except Exception as e:
            print(f"  [ERROR] {e}")
            results['factory']['failed'] += 1
            continue

        # 2. 潮汐データテスト（競艇場サイト）
        print(f"\n[2] 潮汐データ取得テスト（競艇場サイト）")
        try:
            if hasattr(scraper, 'get_tide_table'):
                tide_data = scraper.get_tide_table(test_date)
                if tide_data:
                    print(f"  [OK] 取得成功 ({len(tide_data)}件)")
                    for tide in tide_data[:2]:  # 最初の2件のみ表示
                        print(f"    - {tide['time']} {tide['type']} (潮周り: {tide.get('tide_name', 'N/A')})")
                    results['tide']['success'] += 1
                else:
                    print(f"  [NG] データなし")
                    results['tide']['no_data'] += 1
            else:
                print(f"  [SKIP] get_tide_table()未実装")
                results['tide']['no_data'] += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            results['tide']['failed'] += 1

        # 3. 気象庁潮位データテスト
        print(f"\n[3] 気象庁潮位データ統合テスト")
        try:
            jma_tide = scraper.get_tide_data_with_jma(venue_code, test_date)
            if jma_tide:
                print(f"  [OK] 取得成功")
                print(f"    - データソース: {jma_tide.get('source', 'N/A')}")
                if 'venue_tide' in jma_tide:
                    print(f"    - 競艇場データ: {len(jma_tide['venue_tide'])}件")
                if 'jma_tide' in jma_tide:
                    print(f"    - 気象庁データ: {len(jma_tide['jma_tide'])}件")
                results['jma_tide']['success'] += 1
            else:
                print(f"  [NG] データなし")
                results['jma_tide']['no_data'] += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            results['jma_tide']['failed'] += 1

        # 4. 気象データテスト
        print(f"\n[4] 気象データ取得テスト")
        try:
            if hasattr(scraper, 'get_weather_data'):
                weather_data = scraper.get_weather_data(test_date)
                if weather_data:
                    print(f"  [OK] 取得成功")
                    print(f"    - 風向: {weather_data.get('wind_direction', 'N/A')}")
                    print(f"    - 風速: {weather_data.get('wind_speed', 'N/A')} m/s")
                    print(f"    - 気温: {weather_data.get('temperature', 'N/A')} C")
                    print(f"    - 観測時刻: {weather_data.get('observed_at', 'N/A')}")
                    results['weather']['success'] += 1
                else:
                    print(f"  [NG] データなし")
                    results['weather']['no_data'] += 1
            else:
                print(f"  [SKIP] get_weather_data()未実装")
                results['weather']['no_data'] += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            results['weather']['failed'] += 1

        # 5. 進入コース別成績テスト
        print(f"\n[5] 進入コース別成績取得テスト")
        try:
            if hasattr(scraper, 'get_course_stats'):
                course_stats = scraper.get_course_stats()
                if course_stats:
                    print(f"  [OK] 取得成功 ({len(course_stats)}コース)")
                    if len(course_stats) > 0:
                        stat = course_stats[0]
                        print(f"    - 1C: 1着率 {stat['win_rate']:.1f}%, 2連対率 {stat['place_rate_2']:.1f}%")
                    results['course']['success'] += 1
                else:
                    print(f"  [NG] データなし")
                    results['course']['no_data'] += 1
            else:
                print(f"  [SKIP] get_course_stats()未実装")
                results['course']['no_data'] += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            results['course']['failed'] += 1

        # スクレイパークローズ
        if hasattr(scraper, 'close'):
            scraper.close()

    # 統計サマリー
    print("\n" + "=" * 80)
    print("テスト結果サマリー")
    print("=" * 80)

    total_venues = len(seawater_venues)

    print(f"\n対象競艇場: {total_venues}場")
    print(f"\n【ファクトリー関数】")
    print(f"  成功: {results['factory']['success']}/{total_venues}")
    print(f"  失敗: {results['factory']['failed']}/{total_venues}")

    print(f"\n【潮汐データ（競艇場サイト）】")
    print(f"  成功: {results['tide']['success']}/{total_venues}")
    print(f"  データなし: {results['tide']['no_data']}/{total_venues}")
    print(f"  エラー: {results['tide']['failed']}/{total_venues}")

    print(f"\n【気象庁潮位データ統合】")
    print(f"  成功: {results['jma_tide']['success']}/{total_venues}")
    print(f"  データなし: {results['jma_tide']['no_data']}/{total_venues}")
    print(f"  エラー: {results['jma_tide']['failed']}/{total_venues}")

    print(f"\n【気象データ】")
    print(f"  成功: {results['weather']['success']}/{total_venues}")
    print(f"  データなし: {results['weather']['no_data']}/{total_venues}")
    print(f"  エラー: {results['weather']['failed']}/{total_venues}")

    print(f"\n【進入コース別成績】")
    print(f"  成功: {results['course']['success']}/{total_venues}")
    print(f"  データなし: {results['course']['no_data']}/{total_venues}")
    print(f"  エラー: {results['course']['failed']}/{total_venues}")

    print("\n" + "=" * 80)
    print("統合テスト完了")
    print("=" * 80)


if __name__ == "__main__":
    test_all_seawater_venues()
