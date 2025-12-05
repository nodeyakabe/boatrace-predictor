"""
SQL構文エラー修正スクリプト

data_coverage_checker.py 内の12箇所のSQL構文エラーを修正します。

エラー内容:
  テーブルエイリアスと列名の間に不要なスペースが挿入されている
  例: "e. racer_number" → "e.racer_number"

修正箇所:
  - Line 136: e. racer_number
  - Line 148: e. racer_rank
  - Line 178: res. rank
  - Line 192: rd. tilt_angle
  - Line 217: e. motor_number
  - Line 234: res. rank
  - Line 248: e. boat_number
  - Line 265: res. rank
  - Line 430: rd. actual_course
  - Line 442: rd. exhibition_time
  - Line 454: rd. st_time
  - Line 529: res. rank
"""

import re
import shutil
from datetime import datetime

# バックアップ作成
file_path = 'src/analysis/data_coverage_checker.py'
backup_path = f'src/analysis/data_coverage_checker.py.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'

print(f"バックアップを作成: {backup_path}")
shutil.copy2(file_path, backup_path)

# ファイル読み込み
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 修正前のパターンを記録
errors_found = []

# パターン1: "e. " を "e." に置換（entriesテーブル）
pattern1 = r'\be\.\s+(\w+)'
matches1 = re.findall(pattern1, content)
if matches1:
    errors_found.append(f"  e. カラム名 パターン: {len(matches1)}箇所")
content = re.sub(pattern1, r'e.\1', content)

# パターン2: "res. " を "res." に置換（resultsテーブル）
pattern2 = r'\bres\.\s+(\w+)'
matches2 = re.findall(pattern2, content)
if matches2:
    errors_found.append(f"  res. カラム名 パターン: {len(matches2)}箇所")
content = re.sub(pattern2, r'res.\1', content)

# パターン3: "rd. " を "rd." に置換（race_detailsテーブル）
pattern3 = r'\brd\.\s+(\w+)'
matches3 = re.findall(pattern3, content)
if matches3:
    errors_found.append(f"  rd. カラム名 パターン: {len(matches3)}箇所")
content = re.sub(pattern3, r'rd.\1', content)

# パターン4: "r. " を "r." に置換（racesテーブル）
pattern4 = r'\br\.\s+(\w+)'
matches4 = re.findall(pattern4, content)
if matches4:
    errors_found.append(f"  r. カラム名 パターン: {len(matches4)}箇所")
content = re.sub(pattern4, r'r.\1', content)

# パターン5: "w. " を "w." に置換（weatherテーブル）
pattern5 = r'\bw\.\s+(\w+)'
matches5 = re.findall(pattern5, content)
if matches5:
    errors_found.append(f"  w. カラム名 パターン: {len(matches5)}箇所")
content = re.sub(pattern5, r'w.\1', content)

# パターン6: "p. " を "p." に置換（payoutsテーブル）
pattern6 = r'\bp\.\s+(\w+)'
matches6 = re.findall(pattern6, content)
if matches6:
    errors_found.append(f"  p. カラム名 パターン: {len(matches6)}箇所")
content = re.sub(pattern6, r'p.\1', content)

# ファイル書き込み
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

# 結果表示
print("=" * 60)
print("SQL構文エラー修正完了")
print("=" * 60)
print(f"修正ファイル: {file_path}")
print(f"バックアップ: {backup_path}")
print()
print("発見・修正したエラー:")
if errors_found:
    for error in errors_found:
        print(error)
    total_fixed = sum(len(re.findall(r'\d+', error)) for error in errors_found)
    print(f"\n合計修正箇所: {len(matches1) + len(matches2) + len(matches3) + len(matches4) + len(matches5) + len(matches6)}箇所")
else:
    print("  エラーは見つかりませんでした")

print()
print("修正内容:")
print("  'エイリアス. カラム名' → 'エイリアス.カラム名'")
print()
print("次のステップ:")
print("  1. データカバレッジチェックを実行して動作確認")
print("  2. 問題があれば、バックアップから復元")
print()
