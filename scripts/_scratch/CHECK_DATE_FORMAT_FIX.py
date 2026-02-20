#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
日付形式修正スクリプトのチェック

投入スクリプトに日付形式変換が正しく実装されているかを確認します。
"""

print("=" * 80)
print("投入スクリプトの日付形式変換チェック")
print("=" * 80)

# 投入_2021_2023_補完データ.py の該当箇所を確認
with open('scripts/maintenance/投入_2021_2023_補完データ.py', 'r', encoding='utf-8') as f:
    content = f.read()

# import_trifecta_odds関数の日付変換部分
if '# 日付形式変換: YYYYMMDD → YYYY-MM-DD' in content:
    print("\n✅ import_trifecta_odds: 日付形式変換コードが存在")
    # 該当コードの行番号を特定
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        if '# 日付形式変換: YYYYMMDD → YYYY-MM-DD' in line:
            print(f"   行番号: {i}")
            # 前後5行を表示
            for j in range(max(0, i-2), min(len(lines), i+5)):
                print(f"   {j+1}: {lines[j]}")
else:
    print("\n❌ import_trifecta_odds: 日付形式変換コードが見つかりません")

print("\n" + "=" * 80)

# import_race_details関数の日付変換部分
if 'def import_race_details' in content:
    print("\n✅ import_race_details: 関数が存在")
    lines = content.split('\n')
    in_function = False
    found_conversion = False
    for i, line in enumerate(lines, 1):
        if 'def import_race_details' in line:
            in_function = True
            start_line = i
        if in_function and '# 日付形式変換: YYYYMMDD → YYYY-MM-DD' in line:
            found_conversion = True
            print(f"   ✅ 日付形式変換コードが存在（行番号: {i}）")
            # 前後5行を表示
            for j in range(max(0, i-2), min(len(lines), i+5)):
                print(f"   {j+1}: {lines[j]}")
            break
        if in_function and line.strip().startswith('def ') and i > start_line:
            # 次の関数定義に到達
            break

    if not found_conversion:
        print("   ❌ 日付形式変換コードが見つかりません")
else:
    print("\n❌ import_race_details: 関数が見つかりません")

print("\n" + "=" * 80)
print("\n【重要な発見】")
print("=" * 80)

# import_races関数をチェック
if 'def import_races' in content:
    lines = content.split('\n')
    in_function = False
    found_conversion = False
    for i, line in enumerate(lines, 1):
        if 'def import_races' in line:
            in_function = True
            start_line = i
        if in_function and '# 日付形式変換' in line:
            found_conversion = True
            break
        if in_function and line.strip().startswith('def ') and i > start_line:
            break

    if found_conversion:
        print("✅ import_races: 日付形式変換コードが存在")
    else:
        print("❌ import_races: 日付形式変換コードが存在しない")
        print("   → これが問題の根本原因です！")
        print("   → racesテーブルに投入される際、CSVの日付（YYYY-MM-DD）がそのまま投入されています")

# import_entries関数をチェック
if 'def import_entries' in content:
    lines = content.split('\n')
    in_function = False
    found_conversion = False
    for i, line in enumerate(lines, 1):
        if 'def import_entries' in line:
            in_function = True
            start_line = i
        if in_function and '# 日付形式変換' in line:
            found_conversion = True
            break
        if in_function and line.strip().startswith('def ') and i > start_line:
            break

    if found_conversion:
        print("✅ import_entries: 日付形式変換コードが存在")
    else:
        print("❌ import_entries: 日付形式変換コードが存在しない")

# その他の関数も同様にチェック
functions_to_check = [
    'import_results',
    'import_payouts',
    'import_race_conditions'
]

for func_name in functions_to_check:
    if f'def {func_name}' in content:
        lines = content.split('\n')
        in_function = False
        found_conversion = False
        for i, line in enumerate(lines, 1):
            if f'def {func_name}' in line:
                in_function = True
                start_line = i
            if in_function and '# 日付形式変換' in line:
                found_conversion = True
                break
            if in_function and line.strip().startswith('def ') and i > start_line:
                break

        if found_conversion:
            print(f"✅ {func_name}: 日付形式変換コードが存在")
        else:
            print(f"❌ {func_name}: 日付形式変換コードが存在しない")

print("\n" + "=" * 80)
print("\n結論:")
print("=" * 80)
print("""
1. import_trifecta_odds と import_race_details には日付変換コードが実装されている
2. しかし、import_races には日付変換コードが実装されていない
3. これにより、racesテーブルにはCSVの日付（YYYY-MM-DD）がそのまま投入される
4. entriesやresultsなどはrace_idで紐付けるため、日付形式の影響は受けない
5. しかし、racesテーブルの日付形式が異常なため、クエリで問題が発生する

解決策:
- import_races関数に日付形式変換コードを追加する必要がある
- または、既存の異常データを修正する必要がある
""")
