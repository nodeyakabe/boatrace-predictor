"""
data_coverage_checker.pyの全てのクエリにrace_status='completed'条件を追加
"""

import re

file_path = 'src/analysis/data_coverage_checker.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# entries関連のクエリを修正
# "SELECT COUNT(*) FROM entries" を "SELECT COUNT(*) FROM entries e JOIN races r ON e.race_id = r.id WHERE r.race_status = 'completed'" に
content = re.sub(
    r'SELECT COUNT\(\*\) FROM entries WHERE',
    r"SELECT COUNT(*) FROM entries e JOIN races r ON e.race_id = r.id WHERE r.race_status = 'completed' AND e.",
    content
)

# entries単独のCOUNTを修正（WHERE句がない場合）
content = re.sub(
    r'SELECT COUNT\(\*\) FROM entries"\n',
    r'SELECT COUNT(*) FROM entries e JOIN races r ON e.race_id = r.id WHERE r.race_status = \'completed\'"\n',
    content
)

# race_details関連のクエリを修正
content = re.sub(
    r'SELECT COUNT\(\*\) FROM race_details WHERE',
    r"SELECT COUNT(*) FROM race_details rd JOIN races r ON rd.race_id = r.id WHERE r.race_status = 'completed' AND rd.",
    content
)

# COUNT(DISTINCT e.id) のクエリ - entries e WHERE の部分を修正
content = re.sub(
    r'FROM entries e\s+WHERE e\.',
    r"FROM entries e JOIN races r ON e.race_id = r.id WHERE r.race_status = 'completed' AND e.",
    content
)

# race_details rd WHERE の部分を修正
content = re.sub(
    r'FROM race_details rd\s+WHERE rd\.',
    r"FROM race_details rd JOIN races r ON rd.race_id = r.id WHERE r.race_status = 'completed' AND rd.",
    content
)

# payouts関連
content = re.sub(
    r'SELECT COUNT\(DISTINCT race_id\) FROM payouts',
    r"SELECT COUNT(DISTINCT p.race_id) FROM payouts p JOIN races r ON p.race_id = r.id WHERE r.race_status = 'completed'",
    content
)

# results関連 - COUNT(*)の場合
content = re.sub(
    r'SELECT COUNT\(\*\) FROM results WHERE',
    r"SELECT COUNT(*) FROM results res JOIN races r ON res.race_id = r.id WHERE r.race_status = 'completed' AND res.",
    content
)

# results関連 - COUNT(DISTINCT race_id)の場合
content = re.sub(
    r'SELECT COUNT\(DISTINCT rd\.race_id\)',
    r'SELECT COUNT(DISTINCT rd.race_id)',
    content
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("data_coverage_checker.pyを修正しました")
print("- 全てのクエリにrace_status='completed'条件を追加")
print("- 開催中止レースはデータ欠損としてカウントされません")
