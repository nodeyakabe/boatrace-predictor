"""
app.pyのインデントを修正するスクリプト
"""

# 行993-1492の部分を正しいインデントに修正
with open('ui/app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 修正対象の範囲を特定
start_line = 992  # try:の行 (0-indexed)
end_line = 1491    # exceptの行まで

# この範囲のインデントを修正
# try文の中なので、基本インデントは12スペース
# ifやfor, withなどのブロック内部はさらに+4スペース

fixed_lines = []
for i in range(len(lines)):
    if i < start_line or i > end_line:
        fixed_lines.append(lines[i])
        continue

    line = lines[i]
    stripped = line.lstrip()

    if not stripped:  # 空行
        fixed_lines.append(line)
        continue

    # インデントレベルを判定
    # except, else, elif, finally など
    if stripped.startswith(('except ', 'else:', 'elif ', 'finally:')):
        fixed_lines.append('        ' + stripped)  # 8スペース (try と同じレベル)
    # tryの直下 (集計期間を選択など)
    elif i in range(start_line+1, start_line+30):  # try直後の部分
        fixed_lines.append('            ' + stripped)  # 12スペース
    else:
        # 元のインデントを保持しつつ、基本12スペースに調整
        # forやifの中は16スペース、さらにその中は20スペースなど
        original_indent = len(line) - len(line.lstrip())

        # 行の内容に基づいてインデントを決定
        if stripped.startswith('#'):  # コメント
            if 'コース別勝率' in stripped or '競艇場特性' in stripped or '時間帯別分析' in stripped:
                fixed_lines.append('            ' + stripped)  # 12スペース
            else:
                fixed_lines.append('                ' + stripped)  # 16スペース
        elif any(stripped.startswith(x) for x in ['if ', 'for ', 'with ', 'try:', 'while ']):
            # ネストレベルに応じて調整が必要だが、とりあえず16スペース
            fixed_lines.append('            ' + stripped)  # 12スペース
        elif any(stripped.startswith(x) for x in ['st.', 'course_stats', 'escape_rate', 'venue_chars',
                                                    'stats_list', 'df_', 'query_', 'conn_', 'pattern_analyzer',
                                                    'kimarite_', 'venue_code', 'selected_', 'days', 'col1',
                                                    'new_', 'c_']):
            # 通常の文は context に応じて
            # とりあえず16スペースで統一
            fixed_lines.append('                ' + stripped)  # 16スペース
        else:
            # その他
            fixed_lines.append('            ' + stripped)  # 12スペース

with open('ui/app.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print('Indentation fixed!')
