"""
全コース（1-6）の風向×会場補正テーブル作成

Priority 3タスク: 2-6コースへの気象補正拡張
"""
import os
import sys
import sqlite3
from collections import defaultdict
import json

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def create_wind_venue_table_all_courses(
    db_path: str,
    start_date: str = '2025-01-01',
    end_date: str = '2025-12-31',
    min_wind_speed: float = 3.0,
    min_races: int = 10,
    min_diff: float = 10.0
) -> dict:
    """
    全コース（1-6）の風向×会場補正テーブルを作成

    Args:
        db_path: データベースパス
        start_date: 分析開始日
        end_date: 分析終了日
        min_wind_speed: 最小風速（これ以上のみ分析）
        min_races: 最小レース数（これ以下は除外）
        min_diff: 最小差分（pt、これ以上のみテーブル化）

    Returns:
        {
            course: {
                venue_code: {
                    wind_direction: diff_pt
                }
            }
        }
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 会場コード→会場IDのマッピング
    venue_code_to_id = {
        '01': 1, '02': 2, '03': 3, '04': 4, '05': 5, '06': 6,
        '07': 7, '08': 8, '09': 9, '10': 10, '11': 11, '12': 12,
        '13': 13, '14': 14, '15': 15, '16': 16, '17': 17, '18': 18,
        '19': 19, '20': 20, '21': 21, '22': 22, '23': 23, '24': 24
    }

    # データを取得
    cursor.execute('''
        SELECT
            r.venue_code,
            rc.wind_speed,
            rc.wind_direction,
            COALESCE(ac.actual_course, res.pit_number) as course,
            res.rank
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        JOIN results res ON r.id = res.race_id
        LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
        WHERE r.race_date >= ?
          AND r.race_date <= ?
          AND rc.wind_speed >= ?
          AND rc.wind_direction IS NOT NULL
          AND rc.wind_direction != ''
          AND res.is_invalid = 0
    ''', (start_date, end_date, min_wind_speed))

    results = cursor.fetchall()
    conn.close()

    # コース別の全体ベースライン
    course_baseline = defaultdict(lambda: {'total': 0, 'wins': 0})

    # コース×会場×風向の集計
    course_venue_wind_stats = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'wins': 0}))

    for row in results:
        venue_code = row['venue_code']
        venue_id = venue_code_to_id.get(venue_code)
        if venue_id is None:
            continue

        wind_direction = row['wind_direction']
        course = row['course']
        rank = row['rank']

        # ベースライン
        course_baseline[course]['total'] += 1
        if rank == '1':
            course_baseline[course]['wins'] += 1

        # 会場×風向
        key = (venue_id, wind_direction)
        course_venue_wind_stats[course][key]['total'] += 1
        if rank == '1':
            course_venue_wind_stats[course][key]['wins'] += 1

    # 風向×会場補正テーブル
    wind_venue_table = {}

    for course, venue_wind_data in course_venue_wind_stats.items():
        baseline_total = course_baseline[course]['total']
        baseline_wins = course_baseline[course]['wins']
        baseline_winrate = baseline_wins / baseline_total * 100 if baseline_total > 0 else 0

        course_table = defaultdict(dict)

        for (venue_id, wind_direction), stats in venue_wind_data.items():
            total = stats['total']
            wins = stats['wins']

            if total < min_races:
                continue

            win_rate = wins / total * 100 if total > 0 else 0
            diff = win_rate - baseline_winrate

            if abs(diff) >= min_diff:
                # 会場IDを文字列に変換してテーブルに追加
                venue_id_str = str(venue_id)
                course_table[venue_id_str][wind_direction] = round(diff, 1)

        if course_table:
            wind_venue_table[str(course)] = dict(course_table)

    return wind_venue_table


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 120)
    print("全コース（1-6）の風向×会場補正テーブル作成（2025年、風速3m以上）")
    print("=" * 120)

    wind_table = create_wind_venue_table_all_courses(db_path)

    # 会場名マッピング
    venue_names = {
        '1': "桐生", '2': "戸田", '3': "江戸川", '4': "平和島", '5': "多摩川", '6': "浜名湖",
        '7': "蒲郡", '8': "常滑", '9': "津", '10': "三国", '11': "びわこ", '12': "住之江",
        '13': "尼崎", '14': "鳴門", '15': "丸亀", '16': "児島", '17': "宮島", '18': "徳山",
        '19': "下関", '20': "若松", '21': "芦屋", '22': "福岡", '23': "唐津", '24': "大村"
    }

    # 統計サマリー
    total_patterns = sum(
        sum(len(wind_dirs) for wind_dirs in venue_data.values())
        for venue_data in wind_table.values()
    )

    print(f"\n登録コース数: {len(wind_table)}コース")
    print(f"登録パターン数: {total_patterns:,}件")

    # コース別の登録数
    print("\n" + "=" * 120)
    print("コース別の登録パターン数")
    print("=" * 120)

    print(f"\n{'コース':<10} {'パターン数':<15}")
    print("-" * 30)

    for course in sorted(wind_table.keys(), key=int):
        venue_data = wind_table[course]
        pattern_count = sum(len(wind_dirs) for wind_dirs in venue_data.values())
        print(f"{course}コース   {pattern_count:<15,}")

    # サンプル表示（各コース上位5パターン）
    print("\n" + "=" * 120)
    print("サンプル表示（各コース上位5パターン、差分の絶対値が大きい順）")
    print("=" * 120)

    for course in sorted(wind_table.keys(), key=int):
        venue_data = wind_table[course]

        print(f"\n【{course}コース】")
        print(f"{'会場':<10} {'風向':<15} {'差分':<10}")
        print("-" * 40)

        # 全パターンを差分の絶対値でソート
        all_patterns = []
        for venue_id, wind_dirs in venue_data.items():
            for wind_dir, diff in wind_dirs.items():
                all_patterns.append((venue_id, wind_dir, diff))

        all_patterns.sort(key=lambda x: abs(x[2]), reverse=True)

        for venue_id, wind_dir, diff in all_patterns[:5]:
            venue_name = venue_names.get(venue_id, f"会場{venue_id}")
            print(f"{venue_name:<10} {wind_dir:<15} {diff:+5.1f}pt")

    # テーブルをJSONファイルに保存
    output_path = os.path.join(PROJECT_ROOT, 'src/analysis/wind_venue_table_all_courses.json')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(wind_table, f, ensure_ascii=False, indent=2)

    print(f"\n" + "=" * 120)
    print(f"テーブルを保存しました: {output_path}")
    print(f"合計 {len(wind_table)}コース、{total_patterns:,}パターンの風向×会場補正データ")
    print("=" * 120)


if __name__ == "__main__":
    main()
