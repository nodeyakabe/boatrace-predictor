"""
主要な会場×風向パターンの風速別詳細分析

超有利・大幅不利の6パターンについて、風速を細かく区切って分析
"""
import os
import sys
import sqlite3
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


# 主要6パターン
KEY_PATTERNS = [
    # 超有利パターン
    {'venue': '13', 'direction': '西', 'name': '尼崎×西風'},
    {'venue': '19', 'direction': '北北東', 'name': '下関×北北東'},  # 修正: 北北西→北北東
    {'venue': '23', 'direction': '西', 'name': '唐津×西風'},
    # 大幅不利パターン
    {'venue': '02', 'direction': '北', 'name': '戸田×北風'},
    {'venue': '10', 'direction': '西', 'name': '桐生×西風'},
    {'venue': '14', 'direction': '東北東', 'name': '三国×東北東'},  # 修正: 西北東→東北東
]


def analyze_pattern_by_wind_speed_detail(
    db_path: str,
    venue_code: str,
    wind_direction: str,
    start_date: str = '2025-01-01',
    end_date: str = '2025-12-31'
) -> dict:
    """
    特定の会場×風向について、風速を細かく区切って分析

    風速区分:
    - 8.0-8.5m
    - 8.5-9.0m
    - 9.0-9.5m
    - 9.5-10.0m
    - 10.0m+

    Returns:
        {風速帯: {course1_total, course1_wins, win_rate, races}}
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            rc.wind_speed,
            COALESCE(ac.actual_course, res.pit_number) as course,
            res.rank,
            r.race_date,
            r.race_number
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        JOIN results res ON r.id = res.race_id
        LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
        WHERE r.venue_code = ?
          AND r.race_date >= ?
          AND r.race_date <= ?
          AND rc.wind_speed >= 8.0
          AND rc.wind_direction = ?
          AND res.is_invalid = 0
        ORDER BY rc.wind_speed, r.race_date, r.race_number
    ''', (venue_code, start_date, end_date, wind_direction))

    results = cursor.fetchall()
    conn.close()

    # 風速区分の定義
    def get_wind_range(wind_speed):
        if wind_speed < 8.5:
            return '8.0-8.5m'
        elif wind_speed < 9.0:
            return '8.5-9.0m'
        elif wind_speed < 9.5:
            return '9.0-9.5m'
        elif wind_speed < 10.0:
            return '9.5-10.0m'
        else:
            return '10.0m+'

    # 統計集計
    stats = defaultdict(lambda: {
        'races': set(),
        'course1_total': 0,
        'course1_wins': 0,
        'all_courses': defaultdict(lambda: {'total': 0, 'wins': 0})
    })

    for row in results:
        wind_speed = row['wind_speed']
        course = row['course']
        rank = row['rank']
        race_key = f"{row['race_date']}_{row['race_number']:02d}R"

        wind_range = get_wind_range(wind_speed)

        # レース数をカウント
        stats[wind_range]['races'].add(race_key)

        # 全コースの統計
        stats[wind_range]['all_courses'][course]['total'] += 1
        if rank == '1':
            stats[wind_range]['all_courses'][course]['wins'] += 1

        # 1コースの統計
        if course == 1:
            stats[wind_range]['course1_total'] += 1
            if rank == '1':
                stats[wind_range]['course1_wins'] += 1

    # 勝率を計算
    result = {}
    for wind_range in sorted(stats.keys()):
        data = stats[wind_range]
        course1_total = data['course1_total']
        course1_wins = data['course1_wins']

        result[wind_range] = {
            'races': len(data['races']),
            'course1_total': course1_total,
            'course1_wins': course1_wins,
            'win_rate': course1_wins / course1_total * 100 if course1_total > 0 else 0,
            'all_courses': dict(data['all_courses'])
        }

    return result


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 100)
    print("主要な会場×風向パターンの風速別詳細分析")
    print("=" * 100)

    for pattern in KEY_PATTERNS:
        venue = pattern['venue']
        direction = pattern['direction']
        name = pattern['name']

        print(f"\n{'=' * 100}")
        print(f"【{name}】 会場{venue} × {direction}")
        print("=" * 100)

        # 風速別詳細分析
        result = analyze_pattern_by_wind_speed_detail(db_path, venue, direction)

        if not result:
            print("  データなし")
            continue

        # 結果表示
        print(f"\n風速別1コース勝率:")
        print(f"{'風速帯':<12} {'レース数':<10} {'1コース':<12} {'1コース勝':<12} {'勝率':<10}")
        print("-" * 70)

        total_races = 0
        total_course1 = 0
        total_course1_wins = 0

        for wind_range in sorted(result.keys()):
            data = result[wind_range]
            races = data['races']
            course1_total = data['course1_total']
            course1_wins = data['course1_wins']
            win_rate = data['win_rate']

            total_races += races
            total_course1 += course1_total
            total_course1_wins += course1_wins

            print(f"{wind_range:<12} {races:<10} {course1_total:<12} "
                  f"{course1_wins:<12} {win_rate:5.1f}%")

        print("-" * 70)
        total_win_rate = total_course1_wins / total_course1 * 100 if total_course1 > 0 else 0
        print(f"{'合計':<12} {total_races:<10} {total_course1:<12} "
              f"{total_course1_wins:<12} {total_win_rate:5.1f}%")

        # コース別詳細（全風速合算）
        print(f"\nコース別勝率（全風速合算）:")
        print(f"{'コース':<8} {'サンプル':<12} {'勝数':<12} {'勝率':<10}")
        print("-" * 50)

        all_courses_combined = defaultdict(lambda: {'total': 0, 'wins': 0})

        for wind_range in result.values():
            for course, stats in wind_range['all_courses'].items():
                all_courses_combined[course]['total'] += stats['total']
                all_courses_combined[course]['wins'] += stats['wins']

        for course in sorted(all_courses_combined.keys()):
            stats = all_courses_combined[course]
            total = stats['total']
            wins = stats['wins']
            rate = wins / total * 100 if total > 0 else 0

            print(f"{course}コース   {total:<12} {wins:<12} {rate:5.1f}%")

    print("\n" + "=" * 100)
    print("分析完了")
    print("=" * 100)


if __name__ == "__main__":
    main()
