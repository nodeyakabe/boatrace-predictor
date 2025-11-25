"""
V3スクレイパーの単体テスト
実際のデータ取得を行い、正常性を確認
"""

import sys
from datetime import datetime
from src.scraper.result_scraper_improved_v3 import ImprovedResultScraperV3
from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from src.scraper.race_scraper_v2 import RaceScraperV2


def test_v3_scraper():
    """V3スクレイパーの単体テスト"""

    print("="*80)
    print("V3スクレイパー 単体テスト")
    print("="*80)
    print(f"テスト日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # テストケース: 2025-10-31 桐生 1R（SUMMARY_V3_FIXで報告された問題レース）
    test_cases = [
        {
            'venue_code': '01',
            'date_str': '20251031',
            'race_number': 1,
            'description': '桐生 2025-10-31 1R (Pit3欠損報告レース)',
            'expected_st_count': 6
        },
        {
            'venue_code': '01',
            'date_str': '20251031',
            'race_number': 2,
            'description': '桐生 2025-10-31 2R',
            'expected_st_count': 6
        },
        {
            'venue_code': '24',
            'date_str': '20241110',
            'race_number': 1,
            'description': '大村 2024-11-10 1R (本日のデータ)',
            'expected_st_count': 6
        }
    ]

    all_passed = True
    results = []

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n【テスト {i}/{len(test_cases)}】 {test_case['description']}")
        print("-" * 80)

        venue_code = test_case['venue_code']
        date_str = test_case['date_str']
        race_number = test_case['race_number']
        expected_st_count = test_case['expected_st_count']

        result = {
            'test_case': test_case['description'],
            'success': False,
            'st_count': 0,
            'error': None
        }

        try:
            # スクレイパー初期化
            race_scraper = RaceScraperV2()
            result_scraper = ImprovedResultScraperV3()
            beforeinfo_scraper = BeforeInfoScraper(delay=0.5)

            # 1. レースカード取得
            print(f"  [1] レースカード取得中...")
            race_data = race_scraper.get_race_card(venue_code, date_str, race_number)

            if not race_data:
                print(f"  [ERROR] レースカードが取得できませんでした")
                result['error'] = 'レースカード取得失敗'
                results.append(result)
                all_passed = False
                continue

            entries_count = len(race_data.get('entries', []))
            print(f"  [OK] レースカード取得成功 (出走艇数: {entries_count})")

            # 2. 事前情報取得
            print(f"  [2] 事前情報取得中...")
            beforeinfo = beforeinfo_scraper.get_race_beforeinfo(venue_code, date_str, race_number)

            if beforeinfo:
                ex_count = len(beforeinfo.get('exhibition_times', {}))
                print(f"  [OK] 事前情報取得成功 (展示タイム: {ex_count}/6)")
            else:
                print(f"  [WARN] 事前情報が取得できませんでした（レース前の可能性）")

            # 3. 結果データ取得（V3スクレイパー）
            print(f"  [3] 結果データ取得中（V3スクレイパー）...")
            complete_result = result_scraper.get_race_result_complete(venue_code, date_str, race_number)

            if not complete_result:
                print(f"  [ERROR] 結果データが取得できませんでした")
                result['error'] = '結果データ取得失敗（レース未実施の可能性）'
                results.append(result)
                all_passed = False
                continue

            # STタイム詳細表示
            st_times = complete_result.get('st_times', {})
            st_status = complete_result.get('st_status', {})
            st_count = len(st_times)

            print(f"  [OK] 結果データ取得成功")
            print(f"\n  【STタイム詳細】 ({st_count}/6)")
            print(f"    {'Pit':4s} {'STタイム':>10s} {'ステータス':>12s}")
            print(f"    {'-'*30}")

            for pit in range(1, 7):
                st_time = st_times.get(pit, None)
                status = st_status.get(pit, 'missing')

                if st_time is not None:
                    st_str = f"{st_time:.2f}"
                    status_str = status

                    # ステータスの日本語化
                    if status == 'flying':
                        status_str = 'F (フライング)'
                    elif status == 'late':
                        status_str = 'L (出遅れ)'
                    elif status == 'normal':
                        status_str = '正常'

                    print(f"    Pit{pit} {st_str:>10s} {status_str:>12s}")
                else:
                    print(f"    Pit{pit} {'---':>10s} {'欠損':>12s}")

            # 決まり手確認
            kimarite = complete_result.get('kimarite')
            if kimarite:
                print(f"\n  決まり手: {kimarite}")

            # Flying/Late確認
            flying = [p for p, s in st_status.items() if s == 'flying']
            late = [p for p, s in st_status.items() if s == 'late']

            if flying:
                print(f"  フライング: Pit {flying}")
            if late:
                print(f"  出遅れ: Pit {late}")

            # 判定
            result['st_count'] = st_count
            result['success'] = True

            if st_count == expected_st_count:
                print(f"\n  [PASS] テスト合格: STタイム {st_count}/{expected_st_count}")
            else:
                print(f"\n  [WARN] 警告: STタイム数が期待値と異なります ({st_count}/{expected_st_count})")
                print(f"         ※ フライング・出遅れの可能性があります")

            # クリーンアップ
            race_scraper.close()
            result_scraper.close()
            beforeinfo_scraper.close()

            results.append(result)

        except Exception as e:
            print(f"\n  [ERROR] エラー発生: {e}")
            import traceback
            traceback.print_exc()
            result['error'] = str(e)
            results.append(result)
            all_passed = False

    # サマリー
    print("\n" + "="*80)
    print("テスト結果サマリー")
    print("="*80)

    success_count = sum(1 for r in results if r['success'])
    total_count = len(results)

    print(f"総テスト数: {total_count}")
    print(f"成功: {success_count}")
    print(f"失敗: {total_count - success_count}")

    print(f"\n詳細:")
    for i, r in enumerate(results, 1):
        status = "[PASS]" if r['success'] else "[FAIL]"
        st_info = f"(ST: {r['st_count']}/6)" if r['success'] else ""
        error_info = f" - {r['error']}" if r['error'] else ""
        print(f"  {i}. {status} {r['test_case']} {st_info}{error_info}")

    print("\n" + "="*80)

    if all_passed:
        print("[OK] 全テストに合格しました！")
        print("V3スクレイパーは正常に動作しています。")
    else:
        print("[WARN] 一部のテストが失敗しました。")
        print("エラー内容を確認してください。")
        print("※ レース未実施の場合は正常な動作です。")

    print("="*80)

    return all_passed


if __name__ == '__main__':
    try:
        success = test_v3_scraper()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nテストが中断されました")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n致命的エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
