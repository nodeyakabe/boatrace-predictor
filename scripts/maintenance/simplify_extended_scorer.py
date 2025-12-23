#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ExtendedScorerのDBアクセスメソッドを簡易版に置き換え

パフォーマンステストのため、一時的にDB未接続のデフォルト値を返すように変更
"""
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    print("="*70)
    print("ExtendedScorer 簡易版パッチ")
    print("="*70)

    filepath = 'src/analysis/extended_scorer.py'

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # DBアクセスメソッドの先頭に早期リターンを追加
    modified = []
    in_db_method = False
    method_name = None
    inserted = False

    db_methods = [
        'calculate_session_performance',
        'calculate_previous_race_level',
        'calculate_course_entry_tendency',
        'analyze_motor_characteristics',
        'calculate_exhibition_time_score',
        'calculate_tilt_angle_score',
        'calculate_recent_form_score',
        'calculate_venue_affinity_score',
        'calculate_place_rate_score'
    ]

    for i, line in enumerate(lines):
        # メソッド定義を検出
        for method in db_methods:
            if f'def {method}(' in line:
                in_db_method = True
                method_name = method
                inserted = False
                break

        # メソッド内の最初の"""の後に早期リターンを挿入
        if in_db_method and not inserted and '"""' in line and 'def ' not in line:
            # 次の行がインデントされていれば、そこに挿入
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                indent = len(next_line) - len(next_line.lstrip())

                # 早期リターンコード
                early_return = ' ' * indent + '# TEMPORARY: Skip DB access for performance test\n'
                early_return += ' ' * indent + 'if True:  # TODO: Remove this bypass\n'
                early_return += ' ' * (indent + 4) + f'# Default value for {method_name}\n'

                if method_name == 'calculate_session_performance':
                    early_return += ' ' * (indent + 4) + 'return {"score": 2.5, "races": 0, "avg_rank": None, "trend": "unknown", "description": "節間データなし"}\n'
                elif method_name == 'calculate_previous_race_level':
                    early_return += ' ' * (indent + 4) + 'return {"score": 2.5, "prev_grade": None, "prev_result": None, "description": "前走データなし"}\n'
                elif method_name == 'calculate_course_entry_tendency':
                    early_return += ' ' * (indent + 4) + f'return {{"front_entry_rate": 0.0, "predicted_course": pit_number, "confidence": 0.8, "score": 2.5, "is_front_entry_prone": False, "description": "進入データなし"}}\n'
                elif method_name == 'analyze_motor_characteristics':
                    early_return += ' ' * (indent + 4) + 'return {"score": 2.5, "characteristics": {}, "races": 0, "description": "モーターデータなし"}\n'
                elif method_name == 'calculate_exhibition_time_score':
                    early_return += ' ' * (indent + 4) + 'return {"score": 4.0, "exhibition_time": None, "rank": None, "description": "展示タイムデータなし"}\n'
                elif method_name == 'calculate_tilt_angle_score':
                    early_return += ' ' * (indent + 4) + 'return {"score": 1.0, "tilt_angle": None, "setting_type": "unknown", "description": "チルトデータなし"}\n'
                elif method_name == 'calculate_recent_form_score':
                    early_return += ' ' * (indent + 4) + 'return {"score": 4.0, "recent_win_rate": None, "recent_avg_rank": None, "trend": "unknown", "description": "直近成績データなし"}\n'
                elif method_name == 'calculate_venue_affinity_score':
                    early_return += ' ' * (indent + 4) + 'return {"score": 3.0, "venue_win_rate": None, "venue_avg_rank": None, "venue_races": 0, "is_strong": False, "description": "会場別データ不足"}\n'
                elif method_name == 'calculate_place_rate_score':
                    early_return += ' ' * (indent + 4) + 'return {"score": 2.5, "win_rate": None, "second_rate": None, "third_rate": None, "rentai_rate": None, "is_strong_rentai": False, "description": "連対率データ不足"}\n'

                modified.append(line)
                modified.append(early_return)
                inserted = True
                in_db_method = False
                continue

        modified.append(line)

    # ファイルに書き戻し
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(modified)

    print("\n✓ ExtendedScorerを簡易版に変更しました")
    print("\n変更されたメソッド:")
    for method in db_methods:
        print(f"  - {method}")

    print("\n注意: これはパフォーマンステスト用の一時的な変更です")
    print("      本番環境では使用しないでください")

    print("\n" + "="*70)


if __name__ == "__main__":
    main()
