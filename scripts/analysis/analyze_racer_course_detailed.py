"""
選手のコース別成績詳細分析

サンプル数による信頼度を考慮した詳細分析
"""
import os
import sys
import sqlite3
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def analyze_racer_course_detailed(
    db_path: str,
    start_date: str = '2025-01-01',
    end_date: str = '2025-12-31'
) -> dict:
    """
    選手のコース別成績を詳細分析

    サンプル数別の分析:
    - 10-19レース
    - 20-29レース
    - 30レース以上

    Returns:
        統計データ
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
            e.win_rate as racer_overall_win_rate,
            COALESCE(ac.actual_course, res.pit_number) as course,
            res.rank
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
    racer_course_stats = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'wins': 0, 'racer_name': '', 'racer_rank': '', 'racer_overall_win_rate': 0.0}))

    # コース別の全体統計（ベースライン）
    course_baseline = defaultdict(lambda: {'total': 0, 'wins': 0})

    for row in results:
        racer_number = row['racer_number']
        racer_name = row['racer_name']
        racer_rank = row['racer_rank']
        racer_overall_win_rate = row['racer_overall_win_rate'] or 0.0
        course = row['course']
        rank = row['rank']

        # 選手×コース別
        racer_course_stats[racer_number][course]['total'] += 1
        racer_course_stats[racer_number][course]['racer_name'] = racer_name
        racer_course_stats[racer_number][course]['racer_rank'] = racer_rank
        racer_course_stats[racer_number][course]['racer_overall_win_rate'] = racer_overall_win_rate
        if rank == '1':
            racer_course_stats[racer_number][course]['wins'] += 1

        # コース別全体
        course_baseline[course]['total'] += 1
        if rank == '1':
            course_baseline[course]['wins'] += 1

    # サンプル数別の分析
    by_sample_size = {
        '10-19': [],
        '20-29': [],
        '30+': []
    }

    for racer_number, course_data in racer_course_stats.items():
        for course, stats in course_data.items():
            total = stats['total']
            wins = stats['wins']
            racer_name = stats['racer_name']
            racer_rank = stats['racer_rank']
            racer_overall_win_rate = stats['racer_overall_win_rate']

            racer_course_winrate = wins / total * 100 if total > 0 else 0

            # コース全体の勝率（ベースライン）
            baseline_total = course_baseline[course]['total']
            baseline_wins = course_baseline[course]['wins']
            baseline_winrate = baseline_wins / baseline_total * 100 if baseline_total > 0 else 0

            # 差分
            diff = racer_course_winrate - baseline_winrate

            # サンプル数で分類
            sample_category = None
            if 10 <= total < 20:
                sample_category = '10-19'
            elif 20 <= total < 30:
                sample_category = '20-29'
            elif total >= 30:
                sample_category = '30+'

            if sample_category and abs(diff) >= 5.0:
                by_sample_size[sample_category].append({
                    'racer_number': racer_number,
                    'racer_name': racer_name,
                    'racer_rank': racer_rank,
                    'racer_overall_win_rate': racer_overall_win_rate,
                    'course': course,
                    'racer_winrate': racer_course_winrate,
                    'baseline_winrate': baseline_winrate,
                    'diff': diff,
                    'total_races': total,
                    'wins': wins
                })

    # 各カテゴリーをソート
    for category in by_sample_size:
        by_sample_size[category].sort(key=lambda x: abs(x['diff']), reverse=True)

    return {
        'course_baseline': dict(course_baseline),
        'by_sample_size': by_sample_size
    }


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 120)
    print("選手のコース別成績詳細分析（サンプル数別、2025年通年データ）")
    print("=" * 120)

    data = analyze_racer_course_detailed(db_path)

    course_baseline = data['course_baseline']
    by_sample_size = data['by_sample_size']

    # === 1. サンプル数別の統計サマリー ===
    print("\n" + "=" * 120)
    print("1. サンプル数別の統計サマリー（差分±5pt以上）")
    print("=" * 120)

    print(f"\n{'サンプル数':<15} {'ケース数':<12} {'平均差分':<12} {'最大差分':<12}")
    print("-" * 70)

    for category in ['10-19', '20-29', '30+']:
        cases = by_sample_size[category]
        count = len(cases)

        if count > 0:
            avg_diff = sum(abs(c['diff']) for c in cases) / count
            max_diff = max(cases, key=lambda x: abs(x['diff']))['diff']

            print(f"{category}レース   {count:<12,} {avg_diff:5.1f}pt     {max_diff:+5.1f}pt")

    # === 2. サンプル数30以上の詳細（信頼度が高い） ===
    print("\n" + "=" * 120)
    print("2. サンプル数30以上のケース（信頼度が高い、トップ20）")
    print("=" * 120)

    print(f"\n{'選手':<6} {'名前':<16} {'級別':<6} {'全体勝率':<10} {'コース':<8} {'コース勝率':<12} {'全体':<10} {'差分':<10} {'レース数':<10}")
    print("-" * 120)

    cases_30plus = by_sample_size['30+']
    for case in cases_30plus[:20]:
        racer_number = case['racer_number']
        racer_name = case['racer_name']
        racer_rank = case['racer_rank']
        racer_overall_win_rate = case['racer_overall_win_rate']
        course = case['course']
        racer_winrate = case['racer_winrate']
        baseline_winrate = case['baseline_winrate']
        diff = case['diff']
        total_races = case['total_races']

        print(f"{racer_number:<6} {racer_name:<16} {racer_rank:<6} {racer_overall_win_rate:5.2f}     {course}コース   {racer_winrate:5.1f}%      {baseline_winrate:5.1f}%    {diff:+5.1f}pt   {total_races:<10,}")

    # === 3. 1コースのみの分析（重要） ===
    print("\n" + "=" * 120)
    print("3. 1コースの選手別成績（サンプル数30以上、差分±10pt以上）")
    print("=" * 120)

    course1_30plus = [c for c in cases_30plus if c['course'] == 1 and abs(c['diff']) >= 10.0]
    course1_30plus.sort(key=lambda x: x['diff'], reverse=True)

    print(f"\n{'選手':<6} {'名前':<16} {'級別':<6} {'全体勝率':<10} {'1コース勝率':<12} {'全体':<10} {'差分':<10} {'レース数':<10}")
    print("-" * 120)

    for case in course1_30plus[:20]:
        racer_number = case['racer_number']
        racer_name = case['racer_name']
        racer_rank = case['racer_rank']
        racer_overall_win_rate = case['racer_overall_win_rate']
        racer_winrate = case['racer_winrate']
        baseline_winrate = case['baseline_winrate']
        diff = case['diff']
        total_races = case['total_races']

        print(f"{racer_number:<6} {racer_name:<16} {racer_rank:<6} {racer_overall_win_rate:5.2f}     {racer_winrate:5.1f}%      {baseline_winrate:5.1f}%    {diff:+5.1f}pt   {total_races:<10,}")

    # === 4. 実装方針の検討 ===
    print("\n" + "=" * 120)
    print("4. 実装方針の検討")
    print("=" * 120)

    print("""
【発見】
1. サンプル数30以上でも差分±5pt以上のケースが存在する（信頼度が高い）
2. 1コースで差分±10pt以上のケースもある（重要度が高い）
3. 選手の全体勝率とコース別勝率の関係を考慮する必要がある

【実装案】
- サンプル数20以上のケースのみ補正を適用（信頼度を確保）
- 差分±10pt以上のケースを重点的に補正
- 補正スコア範囲: -5.0 ~ +5.0点（MOTOR_PERFORMANCE_WEIGHTと同じ）
- コース別に重み付け（1コース重視）
    """)

    print("\n" + "=" * 120)
    print("分析完了")
    print("=" * 120)


if __name__ == "__main__":
    main()
