"""
今日実装した機能の総合ロジックチェック
"""

from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from src.scraper.result_scraper import ResultScraper

print("="*70)
print("今日実装した機能の総合ロジックチェック")
print("="*70)

# テスト対象: 下関 10/28 5R
venue_code = "19"
date_str = "20251028"
race_number = 5

print(f"\nテスト対象: {venue_code} {date_str} R{race_number}")
print("-"*70)

# 1. チルト角度（6艇分）の取得
print("\n【1. チルト角度（6艇分）】")
beforeinfo_scraper = BeforeInfoScraper()
beforeinfo = beforeinfo_scraper.get_race_beforeinfo(venue_code, date_str, race_number)

if beforeinfo:
    tilt_angles = beforeinfo.get('tilt_angles', {})
    print(f"  取得数: {len(tilt_angles)}/6艇")

    if len(tilt_angles) == 6:
        print("  [OK] 6艇すべて取得成功")
        for pit in sorted(tilt_angles.keys()):
            print(f"    {pit}号艇: {tilt_angles[pit]}")
    else:
        print(f"  [NG] NG - {6 - len(tilt_angles)}艇が不足")
        for pit in range(1, 7):
            if pit not in tilt_angles:
                print(f"    {pit}号艇: 取得失敗")
else:
    print("  [NG] NG - データ取得失敗")

# 2. 部品交換情報（6艇分）の取得
print("\n【2. 部品交換情報（6艇分）】")
if beforeinfo:
    parts = beforeinfo.get('parts_replacements', {})
    print(f"  取得数: {len(parts)}/6艇")

    if len(parts) == 6:
        print("  [OK] OK - 6艇すべて取得成功")
        for pit in sorted(parts.keys()):
            print(f"    {pit}号艇: {parts[pit] if parts[pit] else '(なし)'}")
    else:
        print(f"  [NG] NG - {6 - len(parts)}艇が不足")
else:
    print("  [NG] NG - データ取得失敗")

# 3. 展示タイム（6艇分）の取得（既存機能の確認）
print("\n【3. 展示タイム（6艇分）】")
if beforeinfo:
    exhibition_times = beforeinfo.get('exhibition_times', {})
    print(f"  取得数: {len(exhibition_times)}/6艇")

    if len(exhibition_times) == 6:
        print("  [OK] OK - 6艇すべて取得成功")
    else:
        print(f"  [NG] NG - {6 - len(exhibition_times)}艇が不足")
else:
    print("  [NG] NG - データ取得失敗")

beforeinfo_scraper.close()

# 4. STタイム（6艇分）の取得
print("\n【4. STタイム（6艇分）】")
result_scraper = ResultScraper()
st_times = result_scraper.get_st_times(venue_code, date_str, race_number)

if st_times:
    print(f"  取得数: {len(st_times)}/6艇")

    if len(st_times) == 6:
        print("  [OK] OK - 6艇すべて取得成功")
        for pit in sorted(st_times.keys()):
            print(f"    {pit}号艇: {st_times[pit]}秒")
    else:
        print(f"  [NG] NG - {6 - len(st_times)}艇が不足")
        for pit in range(1, 7):
            if pit not in st_times:
                print(f"    {pit}号艇: 取得失敗")
else:
    print("  [NG] NG - データ取得失敗")

# 5. 払戻金データの取得
print("\n【5. 払戻金データ】")
payout_data = result_scraper.get_payouts_and_kimarite(venue_code, date_str, race_number)

if payout_data:
    payouts = payout_data.get('payouts', {})

    expected_types = ['trifecta', 'trio', 'exacta', 'quinella', 'quinella_place', 'win', 'place']
    missing_types = []

    for bet_type in expected_types:
        if bet_type not in payouts or not payouts[bet_type]:
            missing_types.append(bet_type)

    if len(missing_types) == 0:
        print(f"  [OK] OK - 7種類すべて取得成功")
        print(f"    3連単: {len(payouts.get('trifecta', []))}件")
        print(f"    3連複: {len(payouts.get('trio', []))}件")
        print(f"    2連単: {len(payouts.get('exacta', []))}件")
        print(f"    2連複: {len(payouts.get('quinella', []))}件")
        print(f"    拡連複: {len(payouts.get('quinella_place', []))}件")
        print(f"    単勝: {len(payouts.get('win', []))}件")
        print(f"    複勝: {len(payouts.get('place', []))}件")
    else:
        print(f"  [NG] NG - {len(missing_types)}種類が不足")
        for bet_type in missing_types:
            print(f"    {bet_type}: 取得失敗")
else:
    print("  [NG] NG - データ取得失敗")

# 6. 決まり手の取得
print("\n【6. 決まり手】")
if payout_data:
    kimarite = payout_data.get('kimarite')

    if kimarite and len(kimarite) > 0:
        print(f"  [OK] OK - 取得成功: {kimarite}")
    else:
        print("  [NG] NG - 取得失敗")
else:
    print("  [NG] NG - データ取得失敗")

# 7. 実際の進入コース（6艇分）の取得（既存機能の確認）
print("\n【7. 実際の進入コース（6艇分）】")
actual_courses = result_scraper.get_actual_courses(venue_code, date_str, race_number)

if actual_courses:
    print(f"  取得数: {len(actual_courses)}/6艇")

    if len(actual_courses) == 6:
        print("  [OK] OK - 6艇すべて取得成功")
        for pit in sorted(actual_courses.keys()):
            print(f"    {pit}号艇: {actual_courses[pit]}コース")
    else:
        print(f"  [NG] NG - {6 - len(actual_courses)}艇が不足")
else:
    print("  [NG] NG - データ取得失敗")

result_scraper.close()

# 総合評価
print("\n" + "="*70)
print("【総合評価】")
print("="*70)

check_results = []

# チェック項目と結果
if beforeinfo:
    check_results.append(("チルト角度（6艇）", len(beforeinfo.get('tilt_angles', {})) == 6))
    check_results.append(("部品交換情報（6艇）", len(beforeinfo.get('parts_replacements', {})) == 6))
    check_results.append(("展示タイム（6艇）", len(beforeinfo.get('exhibition_times', {})) == 6))
else:
    check_results.append(("チルト角度（6艇）", False))
    check_results.append(("部品交換情報（6艇）", False))
    check_results.append(("展示タイム（6艇）", False))

check_results.append(("STタイム（6艇）", st_times and len(st_times) == 6))
check_results.append(("払戻金データ（7種類）", payout_data and len(payout_data.get('payouts', {})) == 7))
check_results.append(("決まり手", payout_data and payout_data.get('kimarite') is not None))
check_results.append(("実際の進入コース（6艇）", actual_courses and len(actual_courses) == 6))

passed = sum(1 for _, result in check_results if result)
total = len(check_results)

print(f"\n合格: {passed}/{total}項目")

for check_name, result in check_results:
    status = "[OK] PASS" if result else "[NG] FAIL"
    print(f"  {status}: {check_name}")

if passed == total:
    print(f"\n*** すべてのチェック項目に合格しました！ ***")
else:
    print(f"\n注意: {total - passed}項目が不合格です。要確認。")

print("\n" + "="*70)
print("ロジックチェック完了")
print("="*70)
