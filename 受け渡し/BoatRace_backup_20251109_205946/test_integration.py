"""
統合テスト - 少数レースでデータ収集の動作確認
fetch_improved_v3.py の動作を小規模で検証
"""

import sys
import time
from datetime import datetime
from src.database.data_manager import DataManager
from src.scraper.result_scraper_improved_v3 import ImprovedResultScraperV3
from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from src.scraper.race_scraper_v2 import RaceScraperV2


def test_integration():
    """統合テスト - データ収集からDB保存までの一連の流れを検証"""

    print("="*80)
    print("統合テスト - データ収集・保存フロー検証")
    print("="*80)
    print(f"テスト日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # テストケース: 実際のレースデータで検証
    test_races = [
        ('01', '20211231', 2),  # 桐生 2021-12-31 2R（Pit3欠損パターン）
        ('01', '20211231', 4),  # 桐生 2021-12-31 4R（Pit3欠損パターン）
        ('02', '20211231', 11), # 戸田 2021-12-31 11R（Pit3欠損パターン）
    ]

    print(f"\nテスト対象: {len(test_races)} レース")
    print("これらは check_pit3_pattern.py で Pit3欠損が確認されたレースです")
    print("V3スクレイパーで正しく取得できるかを検証します\n")

    db = DataManager()
    results = []
    start_time = time.time()

    for i, (venue_code, date_str, race_number) in enumerate(test_races, 1):
        print(f"\n【テスト {i}/{len(test_races)}】 {venue_code} {date_str} {race_number}R")
        print("-" * 80)

        result = {
            'venue_code': venue_code,
            'date_str': date_str,
            'race_number': race_number,
            'success': False,
            'st_count': 0,
            'saved': False,
            'error': None
        }

        try:
            # 1. データ取得
            print(f"  [1] データ取得中...")

            race_scraper = RaceScraperV2()
            result_scraper = ImprovedResultScraperV3()
            beforeinfo_scraper = BeforeInfoScraper(delay=0.3)

            race_data = race_scraper.get_race_card(venue_code, date_str, race_number)
            beforeinfo = beforeinfo_scraper.get_race_beforeinfo(venue_code, date_str, race_number)
            complete_result = result_scraper.get_race_result_complete(venue_code, date_str, race_number)

            race_scraper.close()
            result_scraper.close()
            beforeinfo_scraper.close()

            if not race_data or len(race_data.get('entries', [])) == 0:
                print(f"  [ERROR] レースカードが空です")
                result['error'] = 'Empty race card'
                results.append(result)
                continue

            print(f"  [OK] データ取得成功")

            # STタイム確認
            st_times = complete_result.get('st_times', {}) if complete_result else {}
            st_status = complete_result.get('st_status', {}) if complete_result else {}
            st_count = len(st_times)

            result['st_count'] = st_count
            result['success'] = True

            print(f"\n  【取得データ詳細】")
            print(f"    出走艇数: {len(race_data.get('entries', []))}")
            if beforeinfo:
                print(f"    展示タイム: {len(beforeinfo.get('exhibition_times', {}))}/6")
            if complete_result:
                print(f"    STタイム: {st_count}/6")
                print(f"    決まり手: {complete_result.get('kimarite', 'なし')}")

            # STタイム詳細表示
            if st_times:
                print(f"\n  【STタイム詳細】")
                for pit in range(1, 7):
                    st_time = st_times.get(pit, None)
                    status = st_status.get(pit, 'missing')

                    if st_time is not None:
                        status_label = {
                            'flying': 'F',
                            'late': 'L',
                            'normal': '正常'
                        }.get(status, status)
                        print(f"    Pit{pit}: {st_time:6.2f} ({status_label})")
                    else:
                        print(f"    Pit{pit}: {'---':>6s} (欠損)")

            # 2. データベース保存
            print(f"\n  [2] データベース保存中...")

            # レース基本データ保存
            db.save_race_data(race_data)

            # レースID取得
            race_date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            race_record = db.get_race_data(venue_code, race_date_formatted, race_number)

            if not race_record:
                print(f"  [ERROR] レースIDが取得できませんでした")
                result['error'] = 'Race ID not found'
                results.append(result)
                continue

            race_id = race_record['id']
            print(f"  [OK] レースID取得: {race_id}")

            # 事前情報保存
            if beforeinfo:
                detail_updates = []
                for pit in range(1, 7):
                    pit_detail = {'pit_number': pit}

                    if pit in beforeinfo.get('exhibition_times', {}):
                        pit_detail['exhibition_time'] = beforeinfo['exhibition_times'][pit]
                    if pit in beforeinfo.get('tilt_angles', {}):
                        pit_detail['tilt_angle'] = beforeinfo['tilt_angles'][pit]
                    if pit in beforeinfo.get('parts_replacements', {}):
                        pit_detail['parts_replacement'] = beforeinfo['parts_replacements'][pit]

                    if len(pit_detail) > 1:
                        detail_updates.append(pit_detail)

                if detail_updates:
                    db.save_race_details(race_id, detail_updates)
                    print(f"  [OK] 事前情報保存完了")

            # 結果保存
            if complete_result and not complete_result.get('is_invalid'):
                # 決まり手
                kimarite_text = complete_result.get('kimarite')
                winning_technique = None
                if kimarite_text:
                    kimarite_map = {
                        '逃げ': 1, '差し': 2, 'まくり': 3,
                        'まくり差し': 4, '抜き': 5, '恵まれ': 6
                    }
                    winning_technique = kimarite_map.get(kimarite_text)

                # 結果データ
                result_data_for_save = {
                    'venue_code': venue_code,
                    'race_date': date_str,
                    'race_number': race_number,
                    'results': complete_result.get('results', []),
                    'trifecta_odds': complete_result.get('trifecta_odds'),
                    'is_invalid': complete_result.get('is_invalid', False),
                    'winning_technique': winning_technique,
                    'kimarite': kimarite_text
                }
                db.save_race_result(result_data_for_save)
                print(f"  [OK] 結果データ保存完了")

                # STタイムと進入コース
                actual_courses = complete_result.get('actual_courses', {})

                if actual_courses or st_times:
                    detail_updates = []
                    for pit in range(1, 7):
                        pit_detail = {'pit_number': pit}

                        if pit in actual_courses:
                            pit_detail['actual_course'] = actual_courses[pit]
                        if pit in st_times:
                            pit_detail['st_time'] = st_times[pit]

                        if len(pit_detail) > 1:
                            detail_updates.append(pit_detail)

                    if detail_updates:
                        db.save_race_details(race_id, detail_updates)
                        print(f"  [OK] STタイム・進入コース保存完了")

            result['saved'] = True
            print(f"\n  [PASS] 保存成功")

        except Exception as e:
            print(f"\n  [ERROR] エラー: {e}")
            import traceback
            traceback.print_exc()
            result['error'] = str(e)

        results.append(result)

    elapsed_time = time.time() - start_time

    # テスト結果サマリー
    print("\n" + "="*80)
    print("統合テスト結果サマリー")
    print("="*80)

    success_count = sum(1 for r in results if r['success'])
    saved_count = sum(1 for r in results if r['saved'])

    print(f"総テスト数: {len(results)}")
    print(f"データ取得成功: {success_count}/{len(results)}")
    print(f"データベース保存成功: {saved_count}/{len(results)}")
    print(f"実行時間: {elapsed_time:.1f}秒")

    print(f"\n詳細:")
    for r in results:
        status = "[PASS]" if r['saved'] else "[ERROR]"
        st_info = f"ST:{r['st_count']}/6" if r['success'] else "取得失敗"
        error_info = f" - {r['error']}" if r['error'] else ""
        print(f"  {status} {r['venue_code']} {r['date_str']} {r['race_number']}R ({st_info}){error_info}")

    print("\n" + "="*80)

    # STタイム取得率の評価
    st_counts = [r['st_count'] for r in results if r['success']]
    if st_counts:
        avg_st = sum(st_counts) / len(st_counts)
        perfect_st = sum(1 for c in st_counts if c == 6)
        print(f"\nSTタイム取得評価:")
        print(f"  平均STタイム数: {avg_st:.1f}/6")
        print(f"  完全取得レース: {perfect_st}/{len(st_counts)} ({perfect_st/len(st_counts)*100:.1f}%)")

        if perfect_st == len(st_counts):
            print(f"  [PASS] 全レースで6/6のSTタイムを取得！")
            print(f"  V3スクレイパーは Pit3欠損問題を正しく修正しています！")
        elif perfect_st > 0:
            print(f"  [WARN] 一部レースで欠損あり（F/Lの可能性）")
        else:
            print(f"  [ERROR] STタイム取得に問題がある可能性があります")

    print("="*80)

    if saved_count == len(results):
        print("[PASS] 全テストに合格しました！")
        print("データ収集・保存フローは正常に動作しています。")
        print("本格実行（fetch_improved_v3.py）を開始できます。")
    else:
        print("[WARN] 一部のテストが失敗しました。")

    print("="*80)

    return saved_count == len(results)


if __name__ == '__main__':
    try:
        success = test_integration()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nテストが中断されました")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n致命的エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
