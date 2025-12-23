# -*- coding: utf-8 -*-
"""
コース×会場期待勝率テーブル生成スクリプト

24会場 × 6コース = 144エントリーの期待勝率テーブルを生成し、
race_predictor.pyで使用できるPythonコードとして出力する。
"""

import sqlite3
import json
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent.parent / 'data' / 'boatrace.db'
OUTPUT_PATH = Path(__file__).parent.parent / 'config' / 'venue_course_win_rates.py'


def generate_win_rate_table():
    """
    会場別・コース別の1着勝率を集計してテーブルを生成
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 会場×コース別の1着勝率を集計
    query = '''
        SELECT
            r.venue_code,
            rd.actual_course,
            COUNT(*) as total_races,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_place_count
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
        WHERE rd.actual_course IS NOT NULL
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
          AND r.race_date >= '2020-01-01'
        GROUP BY r.venue_code, rd.actual_course
        HAVING total_races >= 100
        ORDER BY r.venue_code, rd.actual_course
    '''

    cursor.execute(query)
    results = cursor.fetchall()

    # 会場コードと名前のマッピング
    cursor.execute('SELECT code, name FROM venues ORDER BY CAST(code AS INTEGER)')
    venues = {row['code']: row['name'] for row in cursor.fetchall()}

    # データ構造: {venue_code: {course: win_rate}}
    win_rate_table = defaultdict(dict)
    stats = []

    for row in results:
        venue_code = row['venue_code']
        course = row['actual_course']
        total = row['total_races']
        first_count = row['first_place_count']
        win_rate = first_count / total if total > 0 else 0.0

        win_rate_table[venue_code][course] = {
            'win_rate': round(win_rate, 4),
            'total_races': total,
            'first_count': first_count
        }

        stats.append({
            'venue_code': venue_code,
            'venue_name': venues.get(venue_code, '不明'),
            'course': course,
            'win_rate': win_rate,
            'total_races': total,
            'first_count': first_count
        })

    conn.close()

    # 統計情報を表示
    print("=" * 80)
    print("コース×会場期待勝率テーブル生成")
    print("=" * 80)
    print(f"データ期間: 2020年以降")
    print(f"エントリー数: {len(stats)}")
    print()

    # 会場別のサマリー
    print("[会場別サマリー（コース1の勝率順）]")
    print(f"{'会場コード':<6} {'会場名':<10} {'1C勝率':<8} {'2C勝率':<8} {'3C勝率':<8} {'4C勝率':<8} {'5C勝率':<8} {'6C勝率':<8}")
    print("-" * 80)

    venue_summary = []
    for venue_code in sorted(win_rate_table.keys(), key=lambda x: int(x)):
        venue_name = venues.get(venue_code, '不明')
        course_rates = []
        for course in range(1, 7):
            rate = win_rate_table[venue_code].get(course, {}).get('win_rate', 0.0)
            course_rates.append(rate)

        venue_summary.append({
            'venue_code': venue_code,
            'venue_name': venue_name,
            'course_1_rate': course_rates[0]
        })

        print(f"{venue_code:<6} {venue_name:<10} {course_rates[0]:<8.3f} {course_rates[1]:<8.3f} {course_rates[2]:<8.3f} {course_rates[3]:<8.3f} {course_rates[4]:<8.3f} {course_rates[5]:<8.3f}")

    # Pythonコードとして出力
    output_code = f'''# -*- coding: utf-8 -*-
"""
コース×会場期待勝率テーブル

自動生成: {Path(__file__).name}
データ期間: 2020年以降
エントリー数: {len(stats)}
最小レース数: 100レース

使い方:
    from config.venue_course_win_rates import get_venue_course_win_rate

    win_rate = get_venue_course_win_rate(venue_code='01', course=1)
"""

# 会場×コース別勝率テーブル
# 構造: {{venue_code: {{course: {{'win_rate': float, 'total_races': int, 'first_count': int}}}}}}
VENUE_COURSE_WIN_RATES = {json.dumps(dict(win_rate_table), indent=4, ensure_ascii=False)}


def get_venue_course_win_rate(venue_code: str, course: int, default: float = 0.167) -> float:
    """
    会場・コース別の期待勝率を取得

    Args:
        venue_code: 会場コード（'01'-'24'）
        course: コース番号（1-6）
        default: データがない場合のデフォルト値（1/6 = 0.167）

    Returns:
        期待勝率（0.0-1.0）
    """
    venue_data = VENUE_COURSE_WIN_RATES.get(venue_code, {{}})
    course_data = venue_data.get(course, {{}})
    return course_data.get('win_rate', default)


def get_venue_course_stats(venue_code: str, course: int) -> dict:
    """
    会場・コース別の詳細統計を取得

    Args:
        venue_code: 会場コード（'01'-'24'）
        course: コース番号（1-6）

    Returns:
        {{'win_rate': float, 'total_races': int, 'first_count': int}} or None
    """
    venue_data = VENUE_COURSE_WIN_RATES.get(venue_code, {{}})
    return venue_data.get(course)


# 会場名マッピング
VENUE_NAMES = {json.dumps(venues, indent=4, ensure_ascii=False)}
'''

    # ファイルに書き込み
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(output_code)

    print()
    print("=" * 80)
    print(f"テーブルを出力しました: {OUTPUT_PATH}")
    print("=" * 80)

    # 特徴的な会場を抽出
    print()
    print("[イン強会場 TOP5（コース1勝率）]")
    venue_summary_sorted = sorted(venue_summary, key=lambda x: x['course_1_rate'], reverse=True)
    for i, v in enumerate(venue_summary_sorted[:5], 1):
        print(f"  {i}. {v['venue_code']} {v['venue_name']}: {v['course_1_rate']:.3f}")

    print()
    print("[イン弱会場 TOP5（コース1勝率）]")
    for i, v in enumerate(venue_summary_sorted[-5:], 1):
        print(f"  {i}. {v['venue_code']} {v['venue_name']}: {v['course_1_rate']:.3f}")

    return win_rate_table


if __name__ == '__main__':
    generate_win_rate_table()
