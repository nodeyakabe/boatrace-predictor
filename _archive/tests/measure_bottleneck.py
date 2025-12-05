"""
処理時間の詳細計測 - データ取得 vs DB書き込み

1レースの処理を詳細に計測して、
どこに時間がかかっているか特定する
"""

import time
from src.scraper.race_scraper_v2 import RaceScraperV2 as RaceScraper
from src.scraper.result_scraper import ResultScraper
from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from src.database.data_manager import DataManager
from src.database.fast_data_manager import FastDataManager

print("=" * 100)
print("処理時間詳細計測 - ボトルネック特定")
print("=" * 100)

# テスト対象: 住之江 2024-10-27 1R
venue_code = "12"
date_str = "20241027"
race_number = 1

print(f"\nテスト対象: 住之江 {date_str} {race_number}R")
print("=" * 100)

# スクレイパー初期化
race_scraper = RaceScraper()
result_scraper = ResultScraper()
beforeinfo_scraper = BeforeInfoScraper()

# 通常のDataManager
print("\n【パターン1: 通常DataManager】")
data_manager = DataManager()

total_start = time.time()

# 1. 出走表取得
t1 = time.time()
race_data = race_scraper.get_race_card(venue_code, date_str, race_number)
t2 = time.time()
print(f"1. 出走表取得: {t2-t1:.2f}秒")

# 2. DB保存（レース+エントリー）
t1 = time.time()
race_id = None
if data_manager.save_race_data(race_data):
    race_db_data = data_manager.get_race_data(venue_code, f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}", race_number)
    if race_db_data:
        race_id = race_db_data['id']
t2 = time.time()
print(f"2. DB保存（レース+エントリー）: {t2-t1:.2f}秒")

if not race_id:
    print("エラー: race_idが取得できません")
    exit(1)

# 3. 事前情報取得
t1 = time.time()
beforeinfo = beforeinfo_scraper.get_race_beforeinfo(venue_code, date_str, race_number)
t2 = time.time()
print(f"3. 事前情報取得: {t2-t1:.2f}秒")

# 4. 事前情報DB保存
t1 = time.time()
if beforeinfo:
    race_details = []
    for pit in range(1, 7):
        detail = {
            'pit_number': pit,
            'exhibition_time': beforeinfo['exhibition_times'].get(pit),
            'tilt_angle': beforeinfo['tilt_angles'].get(pit),
            'parts_replacement': beforeinfo['parts_replacements'].get(pit)
        }
        race_details.append(detail)
    data_manager.save_race_details(race_id, race_details)
t2 = time.time()
print(f"4. 事前情報DB保存: {t2-t1:.2f}秒")

# 5. 結果取得
t1 = time.time()
complete_result = result_scraper.get_race_result_complete(venue_code, date_str, race_number)
t2 = time.time()
print(f"5. 結果取得: {t2-t1:.2f}秒")

# 6. 結果DB保存
t1 = time.time()
if complete_result and not complete_result.get('is_invalid'):
    if complete_result.get('results'):
        result_data = {
            'venue_code': venue_code,
            'race_date': date_str,
            'race_number': race_number,
            'results': complete_result['results'],
            'is_invalid': False
        }
        data_manager.save_race_result(result_data)

    if complete_result.get('actual_courses'):
        course_details = []
        for pit, course in complete_result['actual_courses'].items():
            course_details.append({'pit_number': pit, 'actual_course': course})
        data_manager.save_race_details(race_id, course_details)

    if complete_result.get('st_times'):
        data_manager.update_st_times(race_id, complete_result['st_times'])

    if complete_result.get('payouts'):
        data_manager.save_payouts(race_id, complete_result['payouts'])

    if complete_result.get('kimarite'):
        data_manager.update_kimarite(race_id, complete_result['kimarite'])
t2 = time.time()
print(f"6. 結果DB保存（全て）: {t2-t1:.2f}秒")

total_end = time.time()
print(f"\n合計時間（待機なし）: {total_end-total_start:.2f}秒")

print("\n" + "=" * 100)
print("【パターン2: FastDataManager】")
print("=" * 100)

fast_manager = FastDataManager()
total_start = time.time()

# 1. 出走表取得（同じデータ再利用）
t1 = time.time()
# race_data は既に取得済み
t2 = time.time()
print(f"1. 出走表取得: {t2-t1:.2f}秒（キャッシュ）")

# 2. DB保存（Fast版）
fast_manager.begin_batch()
t1 = time.time()
race_id_fast = fast_manager.save_race_data_fast(race_data)
t2 = time.time()
print(f"2. DB保存（Fast版）: {t2-t1:.2f}秒")

# 3. 事前情報取得（同じデータ再利用）
t1 = time.time()
# beforeinfo は既に取得済み
t2 = time.time()
print(f"3. 事前情報取得: {t2-t1:.2f}秒（キャッシュ）")

# 4. 事前情報DB保存（Fast版）
t1 = time.time()
if beforeinfo:
    race_details = []
    for pit in range(1, 7):
        detail = {
            'pit_number': pit,
            'exhibition_time': beforeinfo['exhibition_times'].get(pit),
            'tilt_angle': beforeinfo['tilt_angles'].get(pit),
            'parts_replacement': beforeinfo['parts_replacements'].get(pit)
        }
        race_details.append(detail)
    fast_manager.save_race_details_batch(race_id_fast, race_details)
t2 = time.time()
print(f"4. 事前情報DB保存（Fast版）: {t2-t1:.2f}秒")

# 5. 結果取得（同じデータ再利用）
t1 = time.time()
# complete_result は既に取得済み
t2 = time.time()
print(f"5. 結果取得: {t2-t1:.2f}秒（キャッシュ）")

# 6. 結果DB保存（Fast版）
t1 = time.time()
if complete_result and not complete_result.get('is_invalid'):
    if complete_result.get('results'):
        result_data = {
            'venue_code': venue_code,
            'race_date': date_str,
            'race_number': race_number,
            'results': complete_result['results'],
            'is_invalid': False
        }
        fast_manager.save_race_result_fast(result_data)

    if complete_result.get('actual_courses'):
        course_details = []
        for pit, course in complete_result['actual_courses'].items():
            course_details.append({'pit_number': pit, 'actual_course': course})
        fast_manager.save_race_details_batch(race_id_fast, course_details)

    if complete_result.get('st_times'):
        fast_manager.update_st_times_batch(race_id_fast, complete_result['st_times'])

    if complete_result.get('payouts'):
        fast_manager.save_payouts_batch(race_id_fast, complete_result['payouts'])

    if complete_result.get('kimarite'):
        fast_manager.update_kimarite(race_id_fast, complete_result['kimarite'])

fast_manager.commit_batch()
t2 = time.time()
print(f"6. 結果DB保存（Fast版・全て）: {t2-t1:.2f}秒")

fast_manager.close()

total_end = time.time()
print(f"\n合計時間（待機なし）: {total_end-total_start:.2f}秒")

print("\n" + "=" * 100)
print("分析結果")
print("=" * 100)
print("\nHTTPリクエスト（データ取得）:")
print("  - 出走表取得: 最も時間がかかる")
print("  - 事前情報取得: 中程度")
print("  - 結果取得: 中程度")
print("\nDB書き込み:")
print("  - 通常版: connect/close + 個別INSERT")
print("  - Fast版: 接続再利用 + 一括INSERT")
print("\n結論:")
print("  上記の実測値から、HTTPリクエストとDB書き込みの")
print("  どちらがボトルネックか判定できます。")
