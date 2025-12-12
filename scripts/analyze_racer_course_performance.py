"""
選手のコース別成績分析

選手ごとのコース別勝率を分析し、予測への影響度を定量化する
"""
import os
import sys
import sqlite3
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def analyze_racer_course_performance(
    db_path: str,
    start_date: str = '2025-01-01',
    end_date: str = '2025-12-31',
    min_races: int = 10
) -> dict:
    """
    選手のコース別成績と1着率の相関を分析

    Args:
        db_path: データベースパス
        start_date: 分析開始日
        end_date: 分析終了日
        min_races: 最小レース数（これ以下は除外）

    Returns:
        {
            'by_course': {コース: {統計}},
            'racer_samples': {選手番号: {コース別成績}},
            'baseline': {全体統計}
        }
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # データを取得
    cursor.execute('''
        SELECT
            e.racer_number,
            e.racer_name,
            e.racer_rank,
            COALESCE(ac.actual_course, res.pit_number) as course,
            res.rank,
            e.win_rate as racer_overall_win_rate
        FROM races r
        JOIN entries e ON r.id = e.race_id
        JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        LEFT JOIN actual_courses ac ON r.id = ac.race_id AND e.pit_number = ac.pit_number
        WHERE r.race_date >= ?
          AND r.race_date <= ?
          AND res.is_invalid = 0
        ORDER BY e.racer_number, course
    ''', (start_date, end_date))

    results = cursor.fetchall()
    conn.close()

    # 選手×コース別の集計
    racer_course_stats = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'wins': 0}))

    # コース別の全体統計（ベースライン）
    course_baseline = defaultdict(lambda: {'total': 0, 'wins': 0})

    for row in results:
        racer_number = row['racer_number']
        course = row['course']
        rank = row['rank']

        # 選手×コース別
        racer_course_stats[racer_number][course]['total'] += 1
        if rank == '1':
            racer_course_stats[racer_number][course]['wins'] += 1

        # コース別全体
        course_baseline[course]['total'] += 1
        if rank == '1':
            course_baseline[course]['wins'] += 1

    # 選手のコース別勝率が全体勝率と比較してどの程度差があるか
    significant_diffs = []

    for racer_number, course_data in racer_course_stats.items():
        for course, stats in course_data.items():
            total = stats['total']
            wins = stats['wins']

            # 最小レース数チェック
            if total < min_races:
                continue

            racer_course_winrate = wins / total * 100 if total > 0 else 0

            # コース全体の勝率（ベースライン）
            baseline_total = course_baseline[course]['total']
            baseline_wins = course_baseline[course]['wins']
            baseline_winrate = baseline_wins / baseline_total * 100 if baseline_total > 0 else 0

            # 差分
            diff = racer_course_winrate - baseline_winrate

            # 差分が大きい（±5pt以上）場合は記録
            if abs(diff) >= 5.0:
                significant_diffs.append({
                    'racer_number': racer_number,
                    'course': course,
                    'racer_winrate': racer_course_winrate,
                    'baseline_winrate': baseline_winrate,
                    'diff': diff,
                    'total_races': total,
                    'wins': wins
                })

    # 差分が大きい順にソート
    significant_diffs.sort(key=lambda x: abs(x['diff']), reverse=True)

    return {
        'course_baseline': dict(course_baseline),
        'racer_course_stats': racer_course_stats,
        'significant_diffs': significant_diffs
    }


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 100)
    print("選手のコース別成績分析（2025年通年データ）")
    print("=" * 100)

    data = analyze_racer_course_performance(db_path, min_races=10)

    course_baseline = data['course_baseline']
    significant_diffs = data['significant_diffs']

    # === 1. コース別の全体ベースライン ===
    print("\n" + "=" * 100)
    print("1. コース別の全体ベースライン（2025年）")
    print("=" * 100)

    print(f"\n{'コース':<10} {'レース数':<12} {'1着数':<12} {'1着率':<10}")
    print("-" * 60)

    for course in sorted(course_baseline.keys()):
        stats = course_baseline[course]
        total = stats['total']
        wins = stats['wins']
        win_rate = wins / total * 100 if total > 0 else 0

        print(f"{course}コース   {total:<12,} {wins:<12,} {win_rate:5.1f}%")

    # === 2. 選手×コース別で差分が大きいケース（トップ30） ===
    print("\n" + "=" * 100)
    print("2. 選手×コース別の勝率差分が大きいケース（±5pt以上、レース数10以上、トップ30）")
    print("=" * 100)

    print(f"\n{'選手番号':<10} {'コース':<8} {'選手勝率':<12} {'全体勝率':<12} {'差分':<10} {'レース数':<10}")
    print("-" * 80)

    for i, diff_data in enumerate(significant_diffs[:30], 1):
        racer_number = diff_data['racer_number']
        course = diff_data['course']
        racer_winrate = diff_data['racer_winrate']
        baseline_winrate = diff_data['baseline_winrate']
        diff = diff_data['diff']
        total_races = diff_data['total_races']

        print(f"{racer_number:<10} {course}コース   {racer_winrate:5.1f}%      {baseline_winrate:5.1f}%      {diff:+5.1f}pt   {total_races:<10,}")

    # === 3. 統計サマリー ===
    print("\n" + "=" * 100)
    print("3. 統計サマリー")
    print("=" * 100)

    print(f"\n差分±5pt以上のケース数: {len(significant_diffs):,}件")

    # 差分の分布
    positive_count = sum(1 for d in significant_diffs if d['diff'] > 0)
    negative_count = sum(1 for d in significant_diffs if d['diff'] < 0)

    print(f"  - プラス差分（得意コース）: {positive_count:,}件")
    print(f"  - マイナス差分（苦手コース）: {negative_count:,}件")

    # 最大差分
    if significant_diffs:
        max_positive = max([d for d in significant_diffs if d['diff'] > 0], key=lambda x: x['diff'], default=None)
        max_negative = min([d for d in significant_diffs if d['diff'] < 0], key=lambda x: x['diff'], default=None)

        if max_positive:
            print(f"\n最大プラス差分: 選手{max_positive['racer_number']} {max_positive['course']}コース {max_positive['diff']:+.1f}pt ({max_positive['total_races']}レース)")

        if max_negative:
            print(f"最大マイナス差分: 選手{max_negative['racer_number']} {max_negative['course']}コース {max_negative['diff']:+.1f}pt ({max_negative['total_races']}レース)")

    # === 4. コース別の差分分布 ===
    print("\n" + "=" * 100)
    print("4. コース別の差分分布（±5pt以上のケース）")
    print("=" * 100)

    course_diff_count = defaultdict(int)
    for diff_data in significant_diffs:
        course_diff_count[diff_data['course']] += 1

    print(f"\n{'コース':<10} {'差分±5pt以上のケース数':<20}")
    print("-" * 40)

    for course in sorted(course_diff_count.keys()):
        count = course_diff_count[course]
        print(f"{course}コース   {count:<20,}")

    print("\n" + "=" * 100)
    print("分析完了")
    print("=" * 100)


if __name__ == "__main__":
    main()
