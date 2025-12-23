"""
全コース（1-6）の風向×会場補正パターンを分析

Priority 3タスク: 2-6コースへの気象補正拡張
"""
import os
import sys
import sqlite3
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def analyze_wind_venue_all_courses(
    db_path: str,
    start_date: str = '2025-01-01',
    end_date: str = '2025-12-31',
    min_wind_speed: float = 3.0,
    min_races: int = 10
) -> dict:
    """
    全コース（1-6）の風向×会場補正パターンを分析

    Args:
        db_path: データベースパス
        start_date: 分析開始日
        end_date: 分析終了日
        min_wind_speed: 最小風速（これ以上のみ分析）
        min_races: 最小レース数（これ以下は除外）

    Returns:
        {
            'by_course_venue_wind': {
                course: {
                    (venue_id, wind_direction): {
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

    # 会場コード→会場IDのマッピング
    venue_code_to_id = {
        '01': 1, '02': 2, '03': 3, '04': 4, '05': 5, '06': 6,
        '07': 7, '08': 8, '09': 9, '10': 10, '11': 11, '12': 12,
        '13': 13, '14': 14, '15': 15, '16': 16, '17': 17, '18': 18,
        '19': 19, '20': 20, '21': 21, '22': 22, '23': 23, '24': 24
    }

    # データを取得
    cursor.execute('''
        SELECT
            r.venue_code,
            rc.wind_speed,
            rc.wind_direction,
            COALESCE(ac.actual_course, res.pit_number) as course,
            res.rank
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        JOIN results res ON r.id = res.race_id
        LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
        WHERE r.race_date >= ?
          AND r.race_date <= ?
          AND rc.wind_speed >= ?
          AND rc.wind_direction IS NOT NULL
          AND rc.wind_direction != ''
          AND res.is_invalid = 0
    ''', (start_date, end_date, min_wind_speed))

    results = cursor.fetchall()
    conn.close()

    # コース別の全体ベースライン
    course_baseline = defaultdict(lambda: {'total': 0, 'wins': 0})

    # コース×会場×風向の集計
    course_venue_wind_stats = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'wins': 0}))

    for row in results:
        venue_code = row['venue_code']
        venue_id = venue_code_to_id.get(venue_code)
        if venue_id is None:
            continue

        wind_direction = row['wind_direction']
        course = row['course']
        rank = row['rank']

        # ベースライン
        course_baseline[course]['total'] += 1
        if rank == '1':
            course_baseline[course]['wins'] += 1

        # 会場×風向
        key = (venue_id, wind_direction)
        course_venue_wind_stats[course][key]['total'] += 1
        if rank == '1':
            course_venue_wind_stats[course][key]['wins'] += 1

    # 結果を整理
    by_course_venue_wind = {}

    for course, venue_wind_data in course_venue_wind_stats.items():
        baseline_total = course_baseline[course]['total']
        baseline_wins = course_baseline[course]['wins']
        baseline_winrate = baseline_wins / baseline_total * 100 if baseline_total > 0 else 0

        by_course_venue_wind[course] = {}

        for key, stats in venue_wind_data.items():
            total = stats['total']
            wins = stats['wins']

            if total < min_races:
                continue

            win_rate = wins / total * 100 if total > 0 else 0
            diff = win_rate - baseline_winrate

            by_course_venue_wind[course][key] = {
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
        'by_course_venue_wind': by_course_venue_wind,
        'baseline': baseline
    }


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 120)
    print("全コース（1-6）の風向×会場補正パターン分析（2025年通年、風速3m以上）")
    print("=" * 120)

    data = analyze_wind_venue_all_courses(db_path)

    by_course_venue_wind = data['by_course_venue_wind']
    baseline = data['baseline']

    # === 1. コース別ベースライン ===
    print("\n" + "=" * 120)
    print("1. コース別ベースライン（風速3m以上）")
    print("=" * 120)

    print(f"\n{'コース':<10} {'1着率':<10}")
    print("-" * 30)

    for course in sorted(baseline.keys()):
        win_rate = baseline[course]
        print(f"{course}コース   {win_rate:5.1f}%")

    # === 2. コース別の有意な補正パターン（±10pt以上） ===
    print("\n" + "=" * 120)
    print("2. コース別の有意な補正パターン（差分±10pt以上、レース数10以上）")
    print("=" * 120)

    # 会場名マッピング
    venue_names = {
        1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川", 6: "浜名湖",
        7: "蒲郡", 8: "常滑", 9: "津", 10: "三国", 11: "びわこ", 12: "住之江",
        13: "尼崎", 14: "鳴門", 15: "丸亀", 16: "児島", 17: "宮島", 18: "徳山",
        19: "下関", 20: "若松", 21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村"
    }

    for course in sorted(by_course_venue_wind.keys()):
        print(f"\n【{course}コース】（ベースライン: {baseline[course]:.1f}%）")
        print(f"{'会場':<10} {'風向':<12} {'1着率':<10} {'差分':<10} {'レース数':<10}")
        print("-" * 70)

        # 差分が大きい順にソート
        venue_wind_data = by_course_venue_wind[course]
        sorted_patterns = sorted(
            venue_wind_data.items(),
            key=lambda x: abs(x[1]['diff_from_baseline']),
            reverse=True
        )

        # ±10pt以上のみ表示
        significant_patterns = [
            (key, stats) for key, stats in sorted_patterns
            if abs(stats['diff_from_baseline']) >= 10.0
        ]

        if significant_patterns:
            for (venue_id, wind_direction), stats in significant_patterns[:15]:
                venue_name = venue_names.get(venue_id, f"会場{venue_id}")
                win_rate = stats['win_rate']
                diff = stats['diff_from_baseline']
                total = stats['total']

                print(f"{venue_name:<10} {wind_direction:<12} {win_rate:5.1f}%    {diff:+5.1f}pt   {total:<10,}")
        else:
            print("（±10pt以上のパターンなし）")

    # === 3. 統計サマリー ===
    print("\n" + "=" * 120)
    print("3. 統計サマリー（差分±10pt以上のパターン数）")
    print("=" * 120)

    print(f"\n{'コース':<10} {'±10pt以上':<12} {'±15pt以上':<12} {'±20pt以上':<12}")
    print("-" * 60)

    for course in sorted(by_course_venue_wind.keys()):
        venue_wind_data = by_course_venue_wind[course]

        count_10pt = sum(1 for stats in venue_wind_data.values() if abs(stats['diff_from_baseline']) >= 10.0)
        count_15pt = sum(1 for stats in venue_wind_data.values() if abs(stats['diff_from_baseline']) >= 15.0)
        count_20pt = sum(1 for stats in venue_wind_data.values() if abs(stats['diff_from_baseline']) >= 20.0)

        print(f"{course}コース   {count_10pt:<12,} {count_15pt:<12,} {count_20pt:<12,}")

    print("\n" + "=" * 120)
    print("分析完了")
    print("=" * 120)


if __name__ == "__main__":
    main()
