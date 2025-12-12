"""
全コース（1-6）の波高補正パターンを分析

Priority 3タスク: 3-6コースへの波高補正拡張
"""
import os
import sys
import sqlite3
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def analyze_wave_height_all_courses(
    db_path: str,
    start_date: str = '2025-01-01',
    end_date: str = '2025-12-31',
    min_races: int = 10
) -> dict:
    """
    全コース（1-6）の波高補正パターンを分析

    Args:
        db_path: データベースパス
        start_date: 分析開始日
        end_date: 分析終了日
        min_races: 最小レース数（これ以下は除外）

    Returns:
        {
            'by_course_wave': {
                course: {
                    wave_category: {
                        'total': int,
                        'wins': int,
                        'win_rate': float,
                        'diff_from_baseline': float
                    }
                }
            },
            'baseline': {course: win_rate}
        }
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # データを取得
    cursor.execute('''
        SELECT
            rc.wave_height,
            COALESCE(ac.actual_course, res.pit_number) as course,
            res.rank
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        JOIN results res ON r.id = res.race_id
        LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
        WHERE r.race_date >= ?
          AND r.race_date <= ?
          AND rc.wave_height IS NOT NULL
          AND rc.wave_height >= 10
          AND res.is_invalid = 0
    ''', (start_date, end_date))

    results = cursor.fetchall()
    conn.close()

    # コース別の全体ベースライン（波高10cm以上）
    course_baseline = defaultdict(lambda: {'total': 0, 'wins': 0})

    # コース×波高カテゴリの集計
    course_wave_stats = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'wins': 0}))

    for row in results:
        wave_height = row['wave_height']
        course = row['course']
        rank = row['rank']

        # 波高カテゴリ分類
        if 10 <= wave_height < 15:
            wave_category = '10-14cm'
        elif 15 <= wave_height < 20:
            wave_category = '15-19cm'
        elif 20 <= wave_height < 25:
            wave_category = '20-24cm'
        else:
            wave_category = '25cm+'

        # ベースライン
        course_baseline[course]['total'] += 1
        if rank == '1':
            course_baseline[course]['wins'] += 1

        # 波高カテゴリ別
        course_wave_stats[course][wave_category]['total'] += 1
        if rank == '1':
            course_wave_stats[course][wave_category]['wins'] += 1

    # 結果を整理
    by_course_wave = {}

    for course, wave_data in course_wave_stats.items():
        baseline_total = course_baseline[course]['total']
        baseline_wins = course_baseline[course]['wins']
        baseline_winrate = baseline_wins / baseline_total * 100 if baseline_total > 0 else 0

        by_course_wave[course] = {}

        for wave_category, stats in wave_data.items():
            total = stats['total']
            wins = stats['wins']

            if total < min_races:
                continue

            win_rate = wins / total * 100 if total > 0 else 0
            diff = win_rate - baseline_winrate

            by_course_wave[course][wave_category] = {
                'total': total,
                'wins': wins,
                'win_rate': win_rate,
                'diff_from_baseline': diff
            }

    # ベースラインの整理
    baseline = {}
    for course, stats in course_baseline.items():
        total = stats['total']
        wins = stats['wins']
        baseline[course] = wins / total * 100 if total > 0 else 0

    return {
        'by_course_wave': by_course_wave,
        'baseline': baseline
    }


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 120)
    print("全コース（1-6）の波高補正パターン分析（2025年通年、波高10cm以上）")
    print("=" * 120)

    data = analyze_wave_height_all_courses(db_path)

    by_course_wave = data['by_course_wave']
    baseline = data['baseline']

    # === 1. コース別ベースライン ===
    print("\n" + "=" * 120)
    print("1. コース別ベースライン（波高10cm以上）")
    print("=" * 120)

    print(f"\n{'コース':<10} {'1着率':<10} {'レース数':<10}")
    print("-" * 40)

    for course in sorted(baseline.keys()):
        win_rate = baseline[course]
        total_races = sum(stats['total'] for stats in by_course_wave[course].values())
        print(f"{course}コース   {win_rate:5.1f}%    {total_races:,}")

    # === 2. コース別の波高カテゴリ影響 ===
    print("\n" + "=" * 120)
    print("2. コース別の波高カテゴリ影響（差分±5pt以上のみ表示）")
    print("=" * 120)

    for course in sorted(by_course_wave.keys()):
        print(f"\n【{course}コース】（ベースライン: {baseline[course]:.1f}%）")
        print(f"{'波高':<15} {'1着率':<10} {'差分':<10} {'レース数':<10}")
        print("-" * 60)

        wave_data = by_course_wave[course]

        # 波高カテゴリを順番通りにソート
        wave_order = ['10-14cm', '15-19cm', '20-24cm', '25cm+']
        for wave_category in wave_order:
            if wave_category not in wave_data:
                continue

            stats = wave_data[wave_category]
            win_rate = stats['win_rate']
            diff = stats['diff_from_baseline']
            total = stats['total']

            # ±5pt以上のみ表示
            if abs(diff) >= 5.0:
                print(f"{wave_category:<15} {win_rate:5.1f}%    {diff:+5.1f}pt   {total:<10,}")

        # ±5pt以上のパターンがない場合
        has_significant = any(abs(stats['diff_from_baseline']) >= 5.0 for stats in wave_data.values())
        if not has_significant:
            print("（±5pt以上のパターンなし）")

    # === 3. 統計サマリー ===
    print("\n" + "=" * 120)
    print("3. 統計サマリー（全コース、全波高カテゴリ）")
    print("=" * 120)

    print(f"\n{'コース':<10} {'±5pt以上':<12} {'±10pt以上':<12} {'最大差分':<15}")
    print("-" * 60)

    for course in sorted(by_course_wave.keys()):
        wave_data = by_course_wave[course]

        count_5pt = sum(1 for stats in wave_data.values() if abs(stats['diff_from_baseline']) >= 5.0)
        count_10pt = sum(1 for stats in wave_data.values() if abs(stats['diff_from_baseline']) >= 10.0)

        if wave_data:
            max_diff_stats = max(wave_data.values(), key=lambda x: abs(x['diff_from_baseline']))
            max_diff = max_diff_stats['diff_from_baseline']
        else:
            max_diff = 0.0

        print(f"{course}コース   {count_5pt:<12} {count_10pt:<12} {max_diff:+5.1f}pt")

    print("\n" + "=" * 120)
    print("分析完了")
    print("=" * 120)


if __name__ == "__main__":
    main()
