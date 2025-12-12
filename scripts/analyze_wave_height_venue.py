"""
波高×会場の詳細分析

高波時（10cm以上）の会場別1コース勝率を分析
"""
import os
import sys
import sqlite3
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def analyze_wave_height_by_venue(
    db_path: str,
    start_date: str = '2025-01-01',
    end_date: str = '2025-12-31',
    min_wave_height: int = 10
) -> dict:
    """
    会場別×波高別の1コース勝率を分析

    Args:
        db_path: データベースパス
        start_date: 開始日
        end_date: 終了日
        min_wave_height: 最低波高（cm）

    Returns:
        {会場コード: {統計データ}}
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 高波レースのデータを取得
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
          AND rc.wave_height >= ?
          AND res.is_invalid = 0
        ORDER BY r.venue_code, rc.wave_height
    ''', (start_date, end_date, min_wave_height))

    results = cursor.fetchall()
    conn.close()

    # 統計集計
    venue_stats = defaultdict(lambda: {
        'races': set(),
        'course1_total': 0,
        'course1_wins': 0,
        'all_courses': defaultdict(lambda: {'total': 0, 'wins': 0}),
        'wave_heights': set()
    })

    for row in results:
        venue_code = row['venue_code']
        wave_height = row['wave_height']
        course = row['course']
        rank = row['rank']
        race_key = f"{row['race_date']}_{row['race_number']:02d}R"

        # レース数をカウント
        venue_stats[venue_code]['races'].add(race_key)
        venue_stats[venue_code]['wave_heights'].add(wave_height)

        # 全コースの統計
        venue_stats[venue_code]['all_courses'][course]['total'] += 1
        if rank == '1':
            venue_stats[venue_code]['all_courses'][course]['wins'] += 1

        # 1コースの統計
        if course == 1:
            venue_stats[venue_code]['course1_total'] += 1
            if rank == '1':
                venue_stats[venue_code]['course1_wins'] += 1

    # 勝率を計算
    result = {}
    for venue_code, data in venue_stats.items():
        course1_total = data['course1_total']
        course1_wins = data['course1_wins']

        result[venue_code] = {
            'races': len(data['races']),
            'course1_total': course1_total,
            'course1_wins': course1_wins,
            'win_rate': course1_wins / course1_total * 100 if course1_total > 0 else 0,
            'all_courses': dict(data['all_courses']),
            'wave_heights': sorted(data['wave_heights'])
        }

    return result


def get_baseline_winrate(
    db_path: str,
    start_date: str = '2025-01-01',
    end_date: str = '2025-12-31'
) -> float:
    """
    ベースライン（全体）の1コース勝率を取得
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
        FROM races r
        JOIN results res ON r.id = res.race_id
        LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
        WHERE r.race_date >= ?
          AND r.race_date <= ?
          AND COALESCE(ac.actual_course, res.pit_number) = 1
          AND res.is_invalid = 0
    ''', (start_date, end_date))

    row = cursor.fetchone()
    conn.close()

    total = row[0]
    wins = row[1]

    return wins / total * 100 if total > 0 else 0


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    # ベースラインを取得
    baseline_winrate = get_baseline_winrate(db_path)

    print("=" * 100)
    print("波高×会場の詳細分析（2025年通年データ）")
    print("=" * 100)
    print(f"\nベースライン: 1コース勝率 {baseline_winrate:.1f}%")
    print(f"分析対象: 波高10cm以上の高波レース")

    # 会場別分析
    venue_data = analyze_wave_height_by_venue(db_path, min_wave_height=10)

    print(f"\n" + "=" * 100)
    print("会場別×高波時（10cm+）の1コース勝率")
    print("=" * 100)

    print(f"\n{'会場':<6} {'レース数':<10} {'波高範囲':<15} {'1コース':<10} "
          f"{'1コース勝':<10} {'勝率':<10} {'差分':<10}")
    print("-" * 100)

    # 差分の大きい順にソート
    sorted_venues = sorted(
        venue_data.items(),
        key=lambda x: abs(x[1]['win_rate'] - baseline_winrate),
        reverse=True
    )

    for venue_code, stats in sorted_venues:
        venue_num = int(venue_code) if isinstance(venue_code, str) else venue_code
        races = stats['races']
        course1_total = stats['course1_total']
        course1_wins = stats['course1_wins']
        win_rate = stats['win_rate']
        diff = win_rate - baseline_winrate

        # 波高範囲
        wave_heights = stats['wave_heights']
        wave_range = f"{wave_heights[0]}-{wave_heights[-1]}cm" if len(wave_heights) > 1 else f"{wave_heights[0]}cm"

        # サンプル数5件以上のみ表示
        if races >= 5:
            print(f"{venue_num:02d}     {races:<10} {wave_range:<15} {course1_total:<10} "
                  f"{course1_wins:<10} {win_rate:5.1f}%    {diff:+6.1f}pt")

    print("\n" + "=" * 100)
    print("コース別勝率（高波時10cm+、全会場合算）")
    print("=" * 100)

    # 全会場合算のコース別統計
    all_courses_combined = defaultdict(lambda: {'total': 0, 'wins': 0})

    for venue_code, stats in venue_data.items():
        for course, course_stats in stats['all_courses'].items():
            all_courses_combined[course]['total'] += course_stats['total']
            all_courses_combined[course]['wins'] += course_stats['wins']

    print(f"\n{'コース':<8} {'サンプル':<12} {'勝数':<12} {'勝率':<10}")
    print("-" * 50)

    for course in sorted(all_courses_combined.keys()):
        stats = all_courses_combined[course]
        total = stats['total']
        wins = stats['wins']
        rate = wins / total * 100 if total > 0 else 0

        print(f"{course}コース   {total:<12} {wins:<12} {rate:5.1f}%")

    # 超有利・大幅不利パターンの抽出
    print("\n" + "=" * 100)
    print("補正候補パターン（サンプル5件以上、差分±15pt以上）")
    print("=" * 100)

    super_favorable = []
    highly_unfavorable = []

    for venue_code, stats in sorted_venues:
        if stats['races'] < 5:
            continue

        diff = stats['win_rate'] - baseline_winrate

        if diff >= 15.0:
            super_favorable.append((venue_code, stats, diff))
        elif diff <= -15.0:
            highly_unfavorable.append((venue_code, stats, diff))

    if super_favorable:
        print("\n【超有利パターン（+15pt以上）】")
        print(f"{'会場':<6} {'差分':<10} {'勝率':<10} {'サンプル':<10}")
        print("-" * 50)

        for venue_code, stats, diff in super_favorable:
            venue_num = int(venue_code) if isinstance(venue_code, str) else venue_code
            print(f"{venue_num:02d}     {diff:+6.1f}pt  {stats['win_rate']:5.1f}%    "
                  f"{stats['course1_wins']}/{stats['course1_total']}艇")

    if highly_unfavorable:
        print("\n【大幅不利パターン（-15pt以上）】")
        print(f"{'会場':<6} {'差分':<10} {'勝率':<10} {'サンプル':<10}")
        print("-" * 50)

        for venue_code, stats, diff in highly_unfavorable:
            venue_num = int(venue_code) if isinstance(venue_code, str) else venue_code
            print(f"{venue_num:02d}     {diff:+6.1f}pt  {stats['win_rate']:5.1f}%    "
                  f"{stats['course1_wins']}/{stats['course1_total']}艇")

    if not super_favorable and not highly_unfavorable:
        print("\n補正候補なし（差分±15pt以上のパターンが見つかりませんでした）")

    print("\n" + "=" * 100)
    print("分析完了")
    print("=" * 100)


if __name__ == "__main__":
    main()
