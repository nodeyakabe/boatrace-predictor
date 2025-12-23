"""
選手×コース別の得意・不得意テーブル作成

過去3年分のデータから、選手のコース別得意・不得意を抽出し、
補正テーブルを作成する
"""
import os
import sys
import sqlite3
from collections import defaultdict
import json

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def create_racer_course_skill_table(
    db_path: str,
    start_date: str = '2023-01-01',
    end_date: str = '2025-12-31',
    min_races: int = 20,
    min_diff: float = 10.0
) -> dict:
    """
    選手×コース別の得意・不得意テーブルを作成

    Args:
        db_path: データベースパス
        start_date: 分析開始日
        end_date: 分析終了日
        min_races: 最小レース数
        min_diff: 最小差分（pt）

    Returns:
        {
            racer_number: {
                course: diff_pt
            }
        }
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # データを取得
    cursor.execute('''
        SELECT
            e.racer_number,
            COALESCE(ac.actual_course, res.pit_number) as course,
            res.rank
        FROM races r
        JOIN entries e ON r.id = e.race_id
        JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        LEFT JOIN actual_courses ac ON r.id = ac.race_id AND e.pit_number = ac.pit_number
        WHERE r.race_date >= ?
          AND r.race_date <= ?
          AND res.is_invalid = 0
    ''', (start_date, end_date))

    racer_course_stats = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'wins': 0}))
    course_baseline = defaultdict(lambda: {'total': 0, 'wins': 0})

    for row in cursor.fetchall():
        racer_number = row['racer_number']
        course = row['course']
        rank = row['rank']

        racer_course_stats[racer_number][course]['total'] += 1
        if rank == '1':
            racer_course_stats[racer_number][course]['wins'] += 1

        course_baseline[course]['total'] += 1
        if rank == '1':
            course_baseline[course]['wins'] += 1

    conn.close()

    # 選手×コース別の得意・不得意テーブル
    racer_course_skill = {}

    for racer_number, course_data in racer_course_stats.items():
        racer_skill = {}

        for course, stats in course_data.items():
            total = stats['total']
            wins = stats['wins']

            if total < min_races:
                continue

            racer_winrate = wins / total * 100
            baseline_total = course_baseline[course]['total']
            baseline_wins = course_baseline[course]['wins']
            baseline_winrate = baseline_wins / baseline_total * 100

            diff = racer_winrate - baseline_winrate

            if abs(diff) >= min_diff:
                racer_skill[course] = round(diff, 1)

        if racer_skill:
            racer_course_skill[racer_number] = racer_skill

    return racer_course_skill


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 100)
    print("選手×コース別の得意・不得意テーブル作成（過去3年: 2023-2025）")
    print("=" * 100)

    skill_table = create_racer_course_skill_table(db_path)

    print(f"\n選手数: {len(skill_table):,}人")

    # コース別の統計
    course_count = defaultdict(int)
    for racer_number, course_skills in skill_table.items():
        for course in course_skills.keys():
            course_count[course] += 1

    print("\nコース別の登録数:")
    for course in sorted(course_count.keys()):
        print(f"  {course}コース: {course_count[course]:,}件")

    # サンプル表示（トップ20選手）
    print("\n" + "=" * 100)
    print("サンプル表示（得意・不得意の差分が大きい順、トップ20選手）")
    print("=" * 100)

    # 差分の絶対値が最も大きい選手を抽出
    racer_max_diff = []
    for racer_number, course_skills in skill_table.items():
        max_diff = max(abs(d) for d in course_skills.values())
        racer_max_diff.append((racer_number, max_diff, course_skills))

    racer_max_diff.sort(key=lambda x: x[1], reverse=True)

    print(f"\n{'選手番号':<10} {'得意・不得意コース':<60}")
    print("-" * 80)

    for racer_number, max_diff, course_skills in racer_max_diff[:20]:
        skills_str = ", ".join([f"{c}コース{d:+.1f}pt" for c, d in sorted(course_skills.items())])
        print(f"{racer_number:<10} {skills_str}")

    # テーブルをJSONファイルに保存
    output_path = os.path.join(PROJECT_ROOT, 'src/analysis/racer_course_skill_table.json')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(skill_table, f, ensure_ascii=False, indent=2)

    print(f"\n" + "=" * 100)
    print(f"テーブルを保存しました: {output_path}")
    print(f"合計 {len(skill_table):,}選手のコース別得意・不得意データ")
    print("=" * 100)


if __name__ == "__main__":
    main()
