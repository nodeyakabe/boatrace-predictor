"""
展示データの手動入力スクリプト
レース直前の展示航走データを入力
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from datetime import datetime
from config.settings import DATABASE_PATH


def input_exhibition_data(race_id: int):
    """展示データを対話的に入力"""

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
    print(f"展示データ入力: {race_date} 会場{int(venue_code):02d} {int(race_number):2d}R")
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

    print("\n出走表:")
    print("-" * 80)
    print("艇番 | 登録番号 | 選手名")
    print("-" * 80)
    for pit, reg_num, name in entries:
        print(f"  {pit}  |  {reg_num}  | {name:16s}")
    print("-" * 80)

    print("\n展示データを入力してください")
    print("（スキップする場合は Enter キーのみ押してください）")
    print()

    collected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for pit, reg_num, name in entries:
        print(f"\n【{pit}号艇 {name}】")

        # 展示タイム
        while True:
            time_input = input(f"  展示タイム（秒、例: 6.75）: ").strip()
            if not time_input:
                exhibition_time = None
                break
            try:
                exhibition_time = float(time_input)
                if 6.0 <= exhibition_time <= 8.0:
                    break
                else:
                    print("    ※ 通常6.0～8.0秒の範囲です")
            except ValueError:
                print("    ※ 数値で入力してください")

        # スタートタイミング評価
        while True:
            start_input = input(f"  スタート評価（1-5、5が最良）: ").strip()
            if not start_input:
                start_timing = None
                break
            try:
                start_timing = int(start_input)
                if 1 <= start_timing <= 5:
                    break
                else:
                    print("    ※ 1～5で入力してください")
            except ValueError:
                print("    ※ 整数で入力してください")

        # ターン評価
        while True:
            turn_input = input(f"  ターン評価（1-5、5が最良）: ").strip()
            if not turn_input:
                turn_quality = None
                break
            try:
                turn_quality = int(turn_input)
                if 1 <= turn_quality <= 5:
                    break
                else:
                    print("    ※ 1～5で入力してください")
            except ValueError:
                print("    ※ 整数で入力してください")

        # 体重変化
        while True:
            weight_input = input(f"  体重変化（kg、例: +1.5, -0.5）: ").strip()
            if not weight_input:
                weight_change = None
                break
            try:
                weight_change = float(weight_input)
                if -5.0 <= weight_change <= 5.0:
                    break
                else:
                    print("    ※ 通常-5.0～+5.0kgの範囲です")
            except ValueError:
                print("    ※ 数値で入力してください（符号付き可）")

        # データベースに保存
        cursor.execute("""
            INSERT OR REPLACE INTO exhibition_data (
                race_id,
                pit_number,
                exhibition_time,
                start_timing,
                turn_quality,
                weight_change,
                collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (race_id, pit, exhibition_time, start_timing,
              turn_quality, weight_change, collected_at))

    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print("展示データの入力が完了しました")
    print("=" * 80)


def main():
    if len(sys.argv) < 2:
        print("使用方法: python collect_exhibition_data.py <race_id>")
        print("例: python collect_exhibition_data.py 12345")
        return

    try:
        race_id = int(sys.argv[1])
        input_exhibition_data(race_id)
    except ValueError:
        print("エラー: race_id は整数で指定してください")


if __name__ == "__main__":
    main()
