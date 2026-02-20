"""
波高の詳細分析

波高区分別、会場別、コース別の徹底調査
"""
import os
import sys
import sqlite3
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def analyze_wave_height_detailed(
    db_path: str,
    start_date: str = '2025-01-01',
    end_date: str = '2025-12-31'
) -> dict:
    """
    波高の詳細分析

    Returns:
        {
            'by_wave_range': {波高範囲: 統計},
            'by_venue': {会場コード: {波高範囲: 統計}},
            'baseline': ベースライン勝率
        }
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 全データを取得
    cursor.execute('''
        SELECT
            r.venue_code,
            rc.wave_height,
            COALESCE(ac.actual_course, res.pit_number) as course,
            res.rank,
            r.race_date,
            r.race_number
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        JOIN results res ON r.id = res.race_id
        LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
        WHERE r.race_date >= ?
          AND r.race_date <= ?
          AND rc.wave_height IS NOT NULL
          AND res.is_invalid = 0
        ORDER BY rc.wave_height DESC
    ''', (start_date, end_date))

    results = cursor.fetchall()
    conn.close()

    # 波高区分の定義
    def get_wave_range(wave_height):
        if wave_height >= 20:
            return '20cm+'
        elif wave_height >= 15:
            return '15-19cm'
        elif wave_height >= 10:
            return '10-14cm'
        elif wave_height >= 6:
            return '6-9cm'
        elif wave_height >= 3:
            return '3-5cm'
        else:
            return '0-2cm'

    # 統計集計（波高区分別）
    by_wave_range = defaultdict(lambda: {
        'races': set(),
        'course_stats': defaultdict(lambda: {'total': 0, 'wins': 0})
    })

    # 統計集計（会場別×波高区分別）
    by_venue = defaultdict(lambda: defaultdict(lambda: {
        'races': set(),
        'course_stats': defaultdict(lambda: {'total': 0, 'wins': 0})
    }))

    for row in results:
        venue_code = row['venue_code']
        wave_height = row['wave_height']
        course = row['course']
        rank = row['rank']
        race_key = f"{row['race_date']}_{row['race_number']:02d}R"

        wave_range = get_wave_range(wave_height)

        # 波高区分別
        by_wave_range[wave_range]['races'].add(race_key)
        by_wave_range[wave_range]['course_stats'][course]['total'] += 1
        if rank == '1':
            by_wave_range[wave_range]['course_stats'][course]['wins'] += 1

        # 会場別×波高区分別
        by_venue[venue_code][wave_range]['races'].add(race_key)
        by_venue[venue_code][wave_range]['course_stats'][course]['total'] += 1
        if rank == '1':
            by_venue[venue_code][wave_range]['course_stats'][course]['wins'] += 1

    # ベースライン（全体）の1コース勝率を計算
    baseline_total = 0
    baseline_wins = 0

    for wave_range, data in by_wave_range.items():
        course1_stats = data['course_stats'].get(1, {'total': 0, 'wins': 0})
        baseline_total += course1_stats['total']
        baseline_wins += course1_stats['wins']

    baseline_winrate = baseline_wins / baseline_total * 100 if baseline_total > 0 else 0

    return {
        'by_wave_range': dict(by_wave_range),
        'by_venue': dict(by_venue),
        'baseline': baseline_winrate
    }


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 100)
    print("波高の詳細分析（2025年通年データ）")
    print("=" * 100)

    data = analyze_wave_height_detailed(db_path)

    baseline = data['baseline']
    by_wave_range = data['by_wave_range']
    by_venue = data['by_venue']

    print(f"\nベースライン: 1コース勝率 {baseline:.1f}%")

    # === 1. 波高区分別の1コース勝率 ===
    print("\n" + "=" * 100)
    print("1. 波高区分別の1コース勝率")
    print("=" * 100)

    wave_ranges_order = ['0-2cm', '3-5cm', '6-9cm', '10-14cm', '15-19cm', '20cm+']

    print(f"\n{'波高範囲':<12} {'レース数':<10} {'1コース':<10} {'1コース勝':<10} {'勝率':<10} {'差分':<10}")
    print("-" * 100)

    for wave_range in wave_ranges_order:
        if wave_range not in by_wave_range:
            continue

        data = by_wave_range[wave_range]
        races = len(data['races'])
        course1_stats = data['course_stats'].get(1, {'total': 0, 'wins': 0})
        course1_total = course1_stats['total']
        course1_wins = course1_stats['wins']
        win_rate = course1_wins / course1_total * 100 if course1_total > 0 else 0
        diff = win_rate - baseline

        print(f"{wave_range:<12} {races:<10} {course1_total:<10} {course1_wins:<10} "
              f"{win_rate:5.1f}%    {diff:+6.1f}pt")

    # === 2. 波高区分別のコース別勝率 ===
    print("\n" + "=" * 100)
    print("2. 波高区分別のコース別勝率")
    print("=" * 100)

    for wave_range in wave_ranges_order:
        if wave_range not in by_wave_range:
            continue

        data = by_wave_range[wave_range]
        races = len(data['races'])

        print(f"\n【{wave_range}】 レース数: {races}")
        print(f"{'コース':<8} {'サンプル':<12} {'勝数':<12} {'勝率':<10}")
        print("-" * 50)

        for course in range(1, 7):
            stats = data['course_stats'].get(course, {'total': 0, 'wins': 0})
            total = stats['total']
            wins = stats['wins']
            rate = wins / total * 100 if total > 0 else 0

            print(f"{course}コース   {total:<12} {wins:<12} {rate:5.1f}%")

    # === 3. 高波時（10cm+）の会場別詳細 ===
    print("\n" + "=" * 100)
    print("3. 高波時（10cm+）の会場別詳細分析")
    print("=" * 100)

    # 10cm以上のデータを集計
    high_wave_by_venue = {}

    for venue_code, venue_data in by_venue.items():
        combined_stats = defaultdict(lambda: {'total': 0, 'wins': 0})
        total_races = set()

        for wave_range in ['10-14cm', '15-19cm', '20cm+']:
            if wave_range not in venue_data:
                continue

            data = venue_data[wave_range]
            total_races.update(data['races'])

            for course, stats in data['course_stats'].items():
                combined_stats[course]['total'] += stats['total']
                combined_stats[course]['wins'] += stats['wins']

        if len(total_races) >= 5:  # 5レース以上の会場のみ
            high_wave_by_venue[venue_code] = {
                'races': len(total_races),
                'course_stats': dict(combined_stats)
            }

    # 1コース勝率の差分でソート
    sorted_venues = sorted(
        high_wave_by_venue.items(),
        key=lambda x: (
            x[1]['course_stats'].get(1, {'total': 0, 'wins': 0})['wins'] /
            x[1]['course_stats'].get(1, {'total': 1, 'wins': 0})['total'] * 100
        ) - baseline,
        reverse=True
    )

    print(f"\n{'会場':<6} {'レース数':<10} {'1コース':<10} {'1コース勝':<10} {'勝率':<10} {'差分':<10}")
    print("-" * 100)

    for venue_code, data in sorted_venues:
        venue_num = int(venue_code) if isinstance(venue_code, str) else venue_code
        races = data['races']
        course1_stats = data['course_stats'].get(1, {'total': 0, 'wins': 0})
        course1_total = course1_stats['total']
        course1_wins = course1_stats['wins']
        win_rate = course1_wins / course1_total * 100 if course1_total > 0 else 0
        diff = win_rate - baseline

        print(f"{venue_num:02d}     {races:<10} {course1_total:<10} {course1_wins:<10} "
              f"{win_rate:5.1f}%    {diff:+6.1f}pt")

    # 各会場のコース別詳細
    print("\n" + "=" * 100)
    print("会場別のコース別勝率（高波10cm+）")
    print("=" * 100)

    for venue_code, data in sorted_venues:
        venue_num = int(venue_code) if isinstance(venue_code, str) else venue_code
        races = data['races']

        print(f"\n【会場{venue_num:02d}】 レース数: {races}")
        print(f"{'コース':<8} {'サンプル':<12} {'勝数':<12} {'勝率':<10}")
        print("-" * 50)

        for course in range(1, 7):
            stats = data['course_stats'].get(course, {'total': 0, 'wins': 0})
            total = stats['total']
            wins = stats['wins']
            rate = wins / total * 100 if total > 0 else 0

            print(f"{course}コース   {total:<12} {wins:<12} {rate:5.1f}%")

    # === 4. 江戸川の波高区分別詳細 ===
    print("\n" + "=" * 100)
    print("4. 江戸川（会場03）の波高区分別詳細")
    print("=" * 100)

    if '03' in by_venue:
        edogawa_data = by_venue['03']

        print(f"\n{'波高範囲':<12} {'レース数':<10} {'1コース':<10} {'1コース勝':<10} {'勝率':<10} {'差分':<10}")
        print("-" * 100)

        for wave_range in wave_ranges_order:
            if wave_range not in edogawa_data:
                continue

            data = edogawa_data[wave_range]
            races = len(data['races'])
            course1_stats = data['course_stats'].get(1, {'total': 0, 'wins': 0})
            course1_total = course1_stats['total']
            course1_wins = course1_stats['wins']
            win_rate = course1_wins / course1_total * 100 if course1_total > 0 else 0
            diff = win_rate - baseline

            print(f"{wave_range:<12} {races:<10} {course1_total:<10} {course1_wins:<10} "
                  f"{win_rate:5.1f}%    {diff:+6.1f}pt")

    print("\n" + "=" * 100)
    print("分析完了")
    print("=" * 100)


if __name__ == "__main__":
    main()
