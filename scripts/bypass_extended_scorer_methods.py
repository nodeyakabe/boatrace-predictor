#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ExtendedScorerの全DBアクセスメソッドに早期リターンを追加

パフォーマンステスト用の一時的な変更
"""
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


METHOD_BYPASSES = {
    'calculate_session_performance': '''
        # TEMPORARY BYPASS
        return {"score": 2.5, "races": 0, "avg_rank": None, "trend": "unknown", "description": "節間データなし"}
''',
    'calculate_previous_race_level': '''
        # TEMPORARY BYPASS
        return {"score": 2.5, "prev_grade": None, "prev_result": None, "description": "前走データなし"}
''',
    'calculate_course_entry_tendency': '''
        # TEMPORARY BYPASS
        return {"front_entry_rate": 0.0, "predicted_course": pit_number, "confidence": 0.8, "score": 2.5, "is_front_entry_prone": False, "description": "進入データなし"}
''',
    'analyze_motor_characteristics': '''
        # TEMPORARY BYPASS
        return {"score": 2.5, "characteristics": {}, "races": 0, "description": "モーターデータなし"}
''',
    'calculate_exhibition_time_score': '''
        # TEMPORARY BYPASS
        return {"score": 4.0, "exhibition_time": None, "rank": None, "description": "展示タイムデータなし"}
''',
    'calculate_tilt_angle_score': '''
        # TEMPORARY BYPASS
        return {"score": 1.0, "tilt_angle": None, "setting_type": "unknown", "description": "チルトデータなし"}
''',
    'calculate_recent_form_score': '''
        # TEMPORARY BYPASS
        return {"score": 4.0, "recent_win_rate": None, "recent_avg_rank": None, "trend": "unknown", "description": "直近成績データなし"}
''',
    'calculate_venue_affinity_score': '''
        # TEMPORARY BYPASS
        return {"score": 3.0, "venue_win_rate": None, "venue_avg_rank": None, "venue_races": 0, "is_strong": False, "description": "会場別データ不足"}
''',
    'calculate_place_rate_score': '''
        # TEMPORARY BYPASS
        return {"score": 2.5, "win_rate": None, "second_rate": None, "third_rate": None, "rentai_rate": None, "is_strong_rentai": False, "description": "連対率データ不足"}
'''
}


def main():
    print("="*70)
    print("ExtendedScorer メソッドバイパス（一時的）")
    print("="*70)

    filepath = 'src/analysis/extended_scorer.py'

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 各メソッドの直後にバイパスコードを追加
    for method_name, bypass_code in METHOD_BYPASSES.items():
        # メソッド定義を探す
        method_def = f'def {method_name}('
        if method_def not in content:
            print(f"  ✗ {method_name} が見つかりません")
            continue

        # メソッドの docstring 終了を探す
        method_start = content.find(method_def)
        docstring_end = content.find('"""', content.find('"""', method_start) + 3) + 3

        # インデントを検出
        next_line_start = docstring_end
        while next_line_start < len(content) and content[next_line_start] in '\r\n':
            next_line_start += 1

        # 次の行のインデントをコピー
        indent_end = next_line_start
        while indent_end < len(content) and content[indent_end] in ' \t':
            indent_end += 1

        indent = content[next_line_start:indent_end]

        # バイパスコードを整形
        bypass_lines = [indent + line if line.strip() else line for line in bypass_code.split('\n')]
        bypass_formatted = '\n'.join(bypass_lines) + '\n'

        # 挿入
        content = content[:docstring_end] + '\n' + bypass_formatted + content[docstring_end:]

        print(f"  ✓ {method_name} にバイパスを追加")

    # ファイルに書き戻し
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print("\n" + "="*70)
    print("完了: ExtendedScorerの9メソッドにバイパスを追加しました")
    print("注意: これはパフォーマンステスト用の一時的な変更です")
    print("="*70)


if __name__ == "__main__":
    main()
