"""
会場×風向×風速の補正テーブル作成

2025年通年データから会場別・風向別の1コース勝率を抽出し、
実装用の補正テーブルを生成する
"""
import os
import sys
import sqlite3
from typing import Dict, List
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def analyze_venue_wind_course1_winrate(db_path: str, start_date: str, end_date: str,
                                       min_wind: float = 8.0, min_samples: int = 5) -> Dict:
    """
    会場×風向×風速帯の1コース勝率を分析

    Args:
        db_path: データベースパス
        start_date: 開始日
        end_date: 終了日
        min_wind: 最低風速（デフォルト8.0m = 暴風）
        min_samples: 最低サンプル数

    Returns:
        {会場コード: {風向: {win_rate, total, wins, diff}}}
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ベースライン（全体の1コース勝率）を計算
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
        FROM races r
        JOIN results res ON r.id = res.race_id
        LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
          AND COALESCE(ac.actual_course, res.pit_number) = 1
    """, (start_date, end_date))

    baseline = cursor.fetchone()
    baseline_win_rate = baseline['wins'] / baseline['total'] * 100 if baseline['total'] > 0 else 50.3

    print(f"ベースライン（1コース勝率）: {baseline_win_rate:.1f}% (n={baseline['total']})")

    # 会場×風向×風速帯の1コース勝率
    cursor.execute("""
        SELECT
            r.venue_code,
            rc.wind_direction,
            COALESCE(ac.actual_course, res.pit_number) as course,
            res.rank
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        JOIN results res ON r.id = res.race_id
        LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND rc.wind_speed >= ?
          AND rc.wind_direction IS NOT NULL
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
    """, (start_date, end_date, min_wind))

    results = cursor.fetchall()
    conn.close()

    # 統計集計
    stats = defaultdict(lambda: defaultdict(lambda: {
        'total': 0,
        'wins': 0
    }))

    for row in results:
        venue = row['venue_code']
        direction = row['wind_direction']
        course = row['course']
        rank = int(row['rank']) if row['rank'] else None

        if course != 1 or rank is None:
            continue

        stats[venue][direction]['total'] += 1

        if rank == 1:
            stats[venue][direction]['wins'] += 1

    # 勝率を計算し、ベースラインとの差分を追加
    result = defaultdict(dict)

    for venue in stats:
        for direction in stats[venue]:
            total = stats[venue][direction]['total']
            wins = stats[venue][direction]['wins']

            if total >= min_samples:
                win_rate = wins / total * 100
                diff = win_rate - baseline_win_rate

                result[venue][direction] = {
                    'win_rate': win_rate,
                    'total': total,
                    'wins': wins,
                    'diff': diff
                }

    return dict(result)


def generate_venue_wind_table(data: Dict, baseline: float = 50.3) -> str:
    """
    実装用の会場×風向補正テーブルを生成

    Args:
        data: 分析データ
        baseline: ベースライン勝率

    Returns:
        Pythonコード（辞書定義）
    """
    lines = [
        "# 会場×風向×風速の補正テーブル（暴風時8m+）",
        "# 値は1コース勝率の差分（ベースライン50.3%からの乖離）",
        "VENUE_WIND_DIRECTION_ADJUSTMENT = {",
    ]

    for venue_code in sorted(data.keys(), key=lambda x: int(x) if isinstance(x, str) and x.isdigit() else 999):
        venue_num = int(venue_code) if isinstance(venue_code, str) else venue_code
        venue_str = f"{venue_num:02d}"
        lines.append(f"    '{venue_str}': {{  # 会場{venue_num:02d}")

        # 差分の大きい順にソート
        sorted_directions = sorted(data[venue_code].items(),
                                   key=lambda x: abs(x[1]['diff']), reverse=True)

        for direction, stats in sorted_directions:
            diff = stats['diff']
            win_rate = stats['win_rate']
            total = stats['total']

            lines.append(f"        '{direction}': {diff:+6.1f},  "
                        f"# 勝率{win_rate:5.1f}% (n={total:2d})")

        lines.append("    },")

    lines.append("}")

    return '\n'.join(lines)


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 80)
    print("会場×風向×風速の補正テーブル作成")
    print("=" * 80)

    # 対象期間（2025年通年）
    start_date = '2025-01-01'
    end_date = '2025-12-31'

    print(f"\n対象期間: {start_date} ~ {end_date}")
    print(f"条件: 風速8m以上（暴風）、最低サンプル数5件\n")

    # 分析実行
    data = analyze_venue_wind_course1_winrate(db_path, start_date, end_date,
                                              min_wind=8.0, min_samples=5)

    # 結果表示
    print("\n" + "=" * 80)
    print("分析結果（会場×風向別の1コース勝率）")
    print("=" * 80)

    for venue_code in sorted(data.keys(), key=lambda x: int(x) if isinstance(x, str) and x.isdigit() else 999):
        venue_num = int(venue_code) if isinstance(venue_code, str) else venue_code
        print(f"\n### 会場{venue_num:02d} ###")

        # 差分の大きい順にソート
        sorted_directions = sorted(data[venue_code].items(),
                                   key=lambda x: x[1]['diff'], reverse=True)

        print(f"{'風向':<12} {'1コース勝率':<12} {'差分':<10} {'サンプル':<10}")
        print("-" * 60)

        for direction, stats in sorted_directions:
            print(f"{direction:<12} {stats['win_rate']:5.1f}%      "
                  f"{stats['diff']:+6.1f}pt   {stats['wins']}/{stats['total']}艇")

    # テーブル生成
    print("\n" + "=" * 80)
    print("実装用テーブル")
    print("=" * 80)

    table_code = generate_venue_wind_table(data)
    print("\n" + table_code)

    # ファイルに保存
    output_path = os.path.join(PROJECT_ROOT, 'docs', 'venue_wind_direction_table.py')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(table_code)

    print(f"\n保存先: {output_path}")

    # 統計サマリー
    print("\n" + "=" * 80)
    print("統計サマリー")
    print("=" * 80)

    total_venues = len(data)
    total_combinations = sum(len(directions) for directions in data.values())

    print(f"\n会場数: {total_venues}会場")
    print(f"会場×風向の組み合わせ数: {total_combinations}件")

    # 差分の分布
    all_diffs = []
    for venue in data.values():
        for stats in venue.values():
            all_diffs.append(stats['diff'])

    if all_diffs:
        all_diffs.sort()
        print(f"\n差分の分布:")
        print(f"  最大: {max(all_diffs):+6.1f}pt")
        print(f"  最小: {min(all_diffs):+6.1f}pt")
        print(f"  平均: {sum(all_diffs)/len(all_diffs):+6.1f}pt")
        print(f"  中央値: {all_diffs[len(all_diffs)//2]:+6.1f}pt")

    # 極端なケース
    print(f"\n極端なケース（差分の絶対値が大きい上位10件）:")
    print(f"{'会場':<6} {'風向':<12} {'1コース勝率':<12} {'差分':<10} {'サンプル':<10}")
    print("-" * 70)

    extreme_cases = []
    for venue_code, directions in data.items():
        for direction, stats in directions.items():
            extreme_cases.append({
                'venue': venue_code,
                'direction': direction,
                'win_rate': stats['win_rate'],
                'diff': stats['diff'],
                'total': stats['total']
            })

    extreme_cases.sort(key=lambda x: abs(x['diff']), reverse=True)

    for case in extreme_cases[:10]:
        venue_num = int(case['venue']) if isinstance(case['venue'], str) else case['venue']
        print(f"{venue_num:02d}     {case['direction']:<12} {case['win_rate']:5.1f}%      "
              f"{case['diff']:+6.1f}pt   {case['total']}艇")

    print("\n" + "=" * 80)
    print("完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
