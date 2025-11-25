"""
実際の進入コースデータの手動入力スクリプト
スタート直前の実際の進入隊形（コース取り）を入力
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from datetime import datetime
from config.settings import DATABASE_PATH


def input_actual_courses(race_id: int):
    """実際の進入コースを対話的に入力"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # レース情報を取得
    cursor.execute("""
        SELECT r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE r.id = ?
    """, (race_id,))

    race_info = cursor.fetchone()
    if not race_info:
        print(f"エラー: レースID {race_id} が見つかりません")
        conn.close()
        return

    race_date, venue_code, race_number = race_info

    print("=" * 80)
    print(f"実際の進入コース入力: {race_date} 会場{int(venue_code):02d} {int(race_number):2d}R")
    print("=" * 80)

    # 出走表を表示
    cursor.execute("""
        SELECT
            e.pit_number,
            e.racer_number,
            e.racer_name
        FROM entries e
        WHERE e.race_id = ?
        ORDER BY e.pit_number
    """, (race_id,))

    entries = cursor.fetchall()

    print("\n出走表（予定コース）:")
    print("-" * 80)
    print("艇番 | 登録番号 | 選手名           | 予定コース")
    print("-" * 80)
    for pit, reg_num, name in entries:
        expected_course = pit  # 予定コースは通常pit_numberと同じ
        print(f"  {pit}  |  {reg_num}  | {name:16s} |      {expected_course}")
    print("-" * 80)

    print("\n実際の進入コース（スタート直前の隊形）を入力してください")
    print("通常は艇番=コース番号ですが、「進入変化」があった場合のみ変更してください")
    print("（Enter キーのみ押すと予定コースのままになります）")
    print()

    collected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    course_changes = []

    for pit, reg_num, name in entries:
        expected_course = pit  # 予定コースは通常pit_numberと同じ
        while True:
            course_input = input(f"{pit}号艇 {name} の実際のコース（1-6、デフォルト: {expected_course}）: ").strip()

            if not course_input:
                # デフォルト値を使用
                actual_course = expected_course
                break

            try:
                actual_course = int(course_input)
                if 1 <= actual_course <= 6:
                    if actual_course != expected_course:
                        course_changes.append(f"{pit}号艇: {expected_course}→{actual_course}コース")
                    break
                else:
                    print("  ※ 1～6で入力してください")
            except ValueError:
                print("  ※ 整数で入力してください")

        # データベースに保存
        cursor.execute("""
            INSERT OR REPLACE INTO actual_courses (
                race_id,
                pit_number,
                actual_course,
                collected_at
            ) VALUES (?, ?, ?, ?)
        """, (race_id, pit, actual_course, collected_at))

    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print("実際の進入コースの入力が完了しました")
    print("=" * 80)

    if course_changes:
        print("\n進入変化:")
        for change in course_changes:
            print(f"  • {change}")
    else:
        print("\n進入変化なし（全艇枠なり進入）")

    print("=" * 80)


def main():
    if len(sys.argv) < 2:
        print("使用方法: python collect_actual_courses.py <race_id>")
        print("例: python collect_actual_courses.py 12345")
        return

    try:
        race_id = int(sys.argv[1])
        input_actual_courses(race_id)
    except ValueError:
        print("エラー: race_id は整数で指定してください")


if __name__ == "__main__":
    main()
