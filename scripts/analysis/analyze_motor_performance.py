"""
モーター成績の予測への影響分析

モーター2連率・3連率が1着率にどの程度影響するかを分析
"""
import os
import sys
import sqlite3
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def analyze_motor_performance(
    db_path: str,
    start_date: str = '2025-01-01',
    end_date: str = '2025-12-31'
) -> dict:
    """
    モーター成績と1着率の相関を分析

    Returns:
        {
            'by_motor_2rate': {範囲: {統計}},
            'by_course': {コース: {モーター2連率範囲: {統計}}},
            'by_rank': {級別: {モーター2連率範囲: {統計}}}
        }
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # データを取得
    cursor.execute('''
        SELECT
            e.motor_second_rate,
            e.motor_third_rate,
            e.pit_number,
            e.racer_rank,
            COALESCE(ac.actual_course, res.pit_number) as course,
            res.rank
        FROM races r
        JOIN entries e ON r.id = e.race_id
        JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        LEFT JOIN actual_courses ac ON r.id = ac.race_id AND e.pit_number = ac.pit_number
        WHERE r.race_date >= ?
          AND r.race_date <= ?
          AND e.motor_second_rate IS NOT NULL
          AND res.is_invalid = 0
        ORDER BY e.motor_second_rate
    ''', (start_date, end_date))

    results = cursor.fetchall()
    conn.close()

    # モーター2連率の区分
    def get_motor_range(motor_2rate):
        if motor_2rate < 20:
            return '0-20%'
        elif motor_2rate < 30:
            return '20-30%'
        elif motor_2rate < 35:
            return '30-35%'
        elif motor_2rate < 40:
            return '35-40%'
        elif motor_2rate < 45:
            return '40-45%'
        else:
            return '45%+'

    # 統計集計（モーター2連率別）
    by_motor_2rate = defaultdict(lambda: {'total': 0, 'wins': 0})

    # 統計集計（コース別×モーター2連率別）
    by_course = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'wins': 0}))

    # 統計集計（級別×モーター2連率別）
    by_rank = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'wins': 0}))

    for row in results:
        motor_2rate = row['motor_second_rate']
        course = row['course']
        rank = row['rank']
        racer_rank = row['racer_rank']

        motor_range = get_motor_range(motor_2rate)

        # モーター2連率別
        by_motor_2rate[motor_range]['total'] += 1
        if rank == '1':
            by_motor_2rate[motor_range]['wins'] += 1

        # コース別×モーター2連率別
        by_course[course][motor_range]['total'] += 1
        if rank == '1':
            by_course[course][motor_range]['wins'] += 1

        # 級別×モーター2連率別
        if racer_rank:
            by_rank[racer_rank][motor_range]['total'] += 1
            if rank == '1':
                by_rank[racer_rank][motor_range]['wins'] += 1

    return {
        'by_motor_2rate': dict(by_motor_2rate),
        'by_course': dict(by_course),
        'by_rank': dict(by_rank)
    }


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 100)
    print("モーター成績の予測への影響分析（2025年通年データ）")
    print("=" * 100)

    data = analyze_motor_performance(db_path)

    by_motor_2rate = data['by_motor_2rate']
    by_course = data['by_course']
    by_rank = data['by_rank']

    # === 1. モーター2連率別の1着率 ===
    print("\n" + "=" * 100)
    print("1. モーター2連率別の1着率（全コース・全級別）")
    print("=" * 100)

    motor_ranges_order = ['0-20%', '20-30%', '30-35%', '35-40%', '40-45%', '45%+']

    print(f"\n{'モーター2連率':<15} {'サンプル数':<12} {'1着数':<12} {'1着率':<10}")
    print("-" * 60)

    baseline_total = 0
    baseline_wins = 0

    for motor_range in motor_ranges_order:
        if motor_range not in by_motor_2rate:
            continue

        stats = by_motor_2rate[motor_range]
        total = stats['total']
        wins = stats['wins']
        win_rate = wins / total * 100 if total > 0 else 0

        baseline_total += total
        baseline_wins += wins

        print(f"{motor_range:<15} {total:<12,} {wins:<12,} {win_rate:5.1f}%")

    baseline_winrate = baseline_wins / baseline_total * 100 if baseline_total > 0 else 0
    print("-" * 60)
    print(f"{'合計':<15} {baseline_total:<12,} {baseline_wins:<12,} {baseline_winrate:5.1f}%")

    # === 2. コース別×モーター2連率別の1着率 ===
    print("\n" + "=" * 100)
    print("2. コース別×モーター2連率別の1着率")
    print("=" * 100)

    for course in sorted(by_course.keys()):
        course_data = by_course[course]

        print(f"\n【{course}コース】")
        print(f"{'モーター2連率':<15} {'サンプル数':<12} {'1着数':<12} {'1着率':<10} {'差分':<10}")
        print("-" * 70)

        # コース全体の1着率（ベースライン）
        course_total = sum(stats['total'] for stats in course_data.values())
        course_wins = sum(stats['wins'] for stats in course_data.values())
        course_baseline = course_wins / course_total * 100 if course_total > 0 else 0

        for motor_range in motor_ranges_order:
            if motor_range not in course_data:
                continue

            stats = course_data[motor_range]
            total = stats['total']
            wins = stats['wins']
            win_rate = wins / total * 100 if total > 0 else 0
            diff = win_rate - course_baseline

            print(f"{motor_range:<15} {total:<12,} {wins:<12,} {win_rate:5.1f}%    {diff:+5.1f}pt")

    # === 3. 級別×モーター2連率別の1着率 ===
    print("\n" + "=" * 100)
    print("3. 級別×モーター2連率別の1着率")
    print("=" * 100)

    rank_order = ['A1', 'A2', 'B1', 'B2']

    for racer_rank in rank_order:
        if racer_rank not in by_rank:
            continue

        rank_data = by_rank[racer_rank]

        print(f"\n【{racer_rank}級】")
        print(f"{'モーター2連率':<15} {'サンプル数':<12} {'1着数':<12} {'1着率':<10} {'差分':<10}")
        print("-" * 70)

        # 級別全体の1着率（ベースライン）
        rank_total = sum(stats['total'] for stats in rank_data.values())
        rank_wins = sum(stats['wins'] for stats in rank_data.values())
        rank_baseline = rank_wins / rank_total * 100 if rank_total > 0 else 0

        for motor_range in motor_ranges_order:
            if motor_range not in rank_data:
                continue

            stats = rank_data[motor_range]
            total = stats['total']
            wins = stats['wins']
            win_rate = wins / total * 100 if total > 0 else 0
            diff = win_rate - rank_baseline

            print(f"{motor_range:<15} {total:<12,} {wins:<12,} {win_rate:5.1f}%    {diff:+5.1f}pt")

    # === 4. 1コースのモーター2連率別詳細 ===
    print("\n" + "=" * 100)
    print("4. 1コースのモーター2連率別詳細（級別内訳）")
    print("=" * 100)

    if 1 in by_course:
        course1_data = by_course[1]

        print(f"\n{'モーター2連率':<15} {'全体':<10} {'A1級':<10} {'A2級':<10} {'B1級':<10} {'B2級':<10}")
        print("-" * 70)

        for motor_range in motor_ranges_order:
            if motor_range not in course1_data:
                continue

            # 全体
            all_stats = course1_data[motor_range]
            all_total = all_stats['total']
            all_wins = all_stats['wins']
            all_rate = all_wins / all_total * 100 if all_total > 0 else 0

            # 級別ごと
            rates = [f"{all_rate:5.1f}%"]

            for racer_rank in rank_order:
                if racer_rank in by_rank:
                    rank_data = by_rank[racer_rank]
                    if motor_range in rank_data:
                        stats = rank_data[motor_range]
                        total = stats['total']
                        wins = stats['wins']
                        rate = wins / total * 100 if total > 0 else 0
                        rates.append(f"{rate:5.1f}%")
                    else:
                        rates.append("-")
                else:
                    rates.append("-")

            print(f"{motor_range:<15} " + " ".join(f"{r:<10}" for r in rates))

    print("\n" + "=" * 100)
    print("分析完了")
    print("=" * 100)


if __name__ == "__main__":
    main()
