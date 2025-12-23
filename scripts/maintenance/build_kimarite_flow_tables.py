"""
決まり手別の2着・3着コース分布を集計するスクリプト

P-3タスク Phase 1: 統計データ構築

出力:
- data/kimarite_flow_stats.json: 決まり手別の2着・3着分布統計
"""

import sqlite3
import json
from pathlib import Path
from collections import defaultdict
import sys

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

DATABASE_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "kimarite_flow_stats.json"


def build_kimarite_flow_stats():
    """決まり手別の2着・3着コース分布を集計"""

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 決まり手別の1着コース、2着コース、3着コースを集計
    query = """
    SELECT
        r1.pit_number as winner_course,
        r1.kimarite as winner_kimarite,
        r2.pit_number as second_course,
        r3.pit_number as third_course,
        COUNT(*) as count
    FROM results r1
    JOIN results r2 ON r1.race_id = r2.race_id AND r2.rank = 2
    JOIN results r3 ON r1.race_id = r3.race_id AND r3.rank = 3
    WHERE r1.rank = 1
      AND r1.kimarite IS NOT NULL
      AND r1.kimarite != ''
      AND r1.pit_number BETWEEN 1 AND 6
      AND r2.pit_number BETWEEN 1 AND 6
      AND r3.pit_number BETWEEN 1 AND 6
    GROUP BY winner_course, winner_kimarite, second_course, third_course
    ORDER BY winner_course, winner_kimarite, count DESC
    """

    print("決まり手別の2着・3着コース分布を集計中...")
    cursor.execute(query)
    rows = cursor.fetchall()

    # 統計データを構築
    stats = defaultdict(lambda: defaultdict(lambda: {
        'total': 0,
        'second_dist': defaultdict(int),
        'third_dist': defaultdict(int),
        'flow_patterns': defaultdict(int)  # (2着コース, 3着コース) の組み合わせ
    }))

    for row in rows:
        winner = row['winner_course']
        kimarite = row['winner_kimarite']
        second = row['second_course']
        third = row['third_course']
        count = row['count']

        key = f"{winner}_{kimarite}"
        stats[winner][kimarite]['total'] += count
        stats[winner][kimarite]['second_dist'][second] += count
        stats[winner][kimarite]['third_dist'][third] += count
        stats[winner][kimarite]['flow_patterns'][f"{second}-{third}"] += count

    # 確率に変換
    result = {}
    for winner_course in range(1, 7):
        result[winner_course] = {}
        for kimarite, data in stats[winner_course].items():
            total = data['total']
            if total < 30:  # サンプル数が少ない場合はスキップ
                continue

            # 2着コース確率
            second_prob = {}
            for course, cnt in data['second_dist'].items():
                second_prob[course] = round(cnt / total, 4)

            # 3着コース確率
            third_prob = {}
            for course, cnt in data['third_dist'].items():
                third_prob[course] = round(cnt / total, 4)

            # 上位5つの流れパターン
            top_flows = sorted(
                data['flow_patterns'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            flow_patterns = {
                pattern: round(cnt / total, 4)
                for pattern, cnt in top_flows
            }

            result[winner_course][kimarite] = {
                'total_samples': total,
                'second_course_prob': second_prob,
                'third_course_prob': third_prob,
                'top_flow_patterns': flow_patterns
            }

    conn.close()

    # 結果を保存
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n統計データを保存しました: {OUTPUT_PATH}")

    return result


def print_summary(stats):
    """統計サマリーを表示"""

    print("\n" + "=" * 60)
    print("決まり手別 2着・3着コース分布サマリー")
    print("=" * 60)

    # 決まり手の種類をカウント
    kimarite_counts = defaultdict(int)
    for winner_course, kimarite_data in stats.items():
        for kimarite, data in kimarite_data.items():
            kimarite_counts[kimarite] += data['total_samples']

    print("\n【決まり手別サンプル数】")
    for kimarite, count in sorted(kimarite_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {kimarite}: {count:,}件")

    # 主要パターンの表示
    print("\n【主要パターン: 1コース逃げの場合】")
    if 1 in stats and '逃げ' in stats[1]:
        data = stats[1]['逃げ']
        print(f"  サンプル数: {data['total_samples']:,}件")
        print(f"  2着コース確率: {data['second_course_prob']}")
        print(f"  3着コース確率: {data['third_course_prob']}")
        print(f"  上位流れパターン: {data['top_flow_patterns']}")

    print("\n【主要パターン: 3コースまくりの場合】")
    if 3 in stats and 'まくり' in stats[3]:
        data = stats[3]['まくり']
        print(f"  サンプル数: {data['total_samples']:,}件")
        print(f"  2着コース確率: {data['second_course_prob']}")
        print(f"  3着コース確率: {data['third_course_prob']}")
        print(f"  上位流れパターン: {data['top_flow_patterns']}")

    print("\n【主要パターン: 4コースまくりの場合】")
    if 4 in stats and 'まくり' in stats[4]:
        data = stats[4]['まくり']
        print(f"  サンプル数: {data['total_samples']:,}件")
        print(f"  2着コース確率: {data['second_course_prob']}")
        print(f"  3着コース確率: {data['third_course_prob']}")
        print(f"  上位流れパターン: {data['top_flow_patterns']}")

    print("\n【主要パターン: 2コース差しの場合】")
    if 2 in stats and '差し' in stats[2]:
        data = stats[2]['差し']
        print(f"  サンプル数: {data['total_samples']:,}件")
        print(f"  2着コース確率: {data['second_course_prob']}")
        print(f"  3着コース確率: {data['third_course_prob']}")
        print(f"  上位流れパターン: {data['top_flow_patterns']}")


def analyze_third_advantage():
    """3着有利コースの分析"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("3着有利コース分析（決まり手別）")
    print("=" * 60)

    # 主要な決まり手パターンごとに3着コースの分布を分析
    patterns = [
        (1, '逃げ', '1コース逃げ'),
        (2, '差し', '2コース差し'),
        (3, 'まくり', '3コースまくり'),
        (4, 'まくり', '4コースまくり'),
        (4, 'まくり差し', '4コースまくり差し'),
        (5, 'まくり', '5コースまくり'),
    ]

    for winner_course, kimarite, label in patterns:
        query = """
        SELECT
            r3.pit_number as third_course,
            COUNT(*) as count
        FROM results r1
        JOIN results r3 ON r1.race_id = r3.race_id AND r3.rank = 3
        WHERE r1.rank = 1
          AND r1.pit_number = ?
          AND r1.kimarite = ?
          AND r3.pit_number BETWEEN 1 AND 6
        GROUP BY third_course
        ORDER BY count DESC
        """

        cursor.execute(query, (winner_course, kimarite))
        rows = cursor.fetchall()

        if not rows:
            continue

        total = sum(r[1] for r in rows)

        print(f"\n【{label}】(n={total:,})")
        for course, count in rows:
            pct = count / total * 100
            bar = '█' * int(pct / 2)
            print(f"  {course}コース: {pct:5.1f}% ({count:,}件) {bar}")

    conn.close()


if __name__ == "__main__":
    stats = build_kimarite_flow_stats()
    print_summary(stats)
    analyze_third_advantage()
