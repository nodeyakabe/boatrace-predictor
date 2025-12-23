"""
前付け常習者リストの抽出

P-1タスク: 前付け常習者がいるレースを購入対象から除外するためのリスト生成
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import json

DATABASE_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"
OUTPUT_PATH = Path(__file__).parent.parent / "config" / "forward_movers.json"


def extract_forward_movers(min_rate: float = 40.0, min_races: int = 30, days: int = 365):
    """
    前付け常習者を抽出

    Args:
        min_rate: 最低前付け率（%）
        min_races: 最低出走数
        days: 集計期間（日数）

    Returns:
        前付け常習者のリスト
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    query = """
    SELECT
        e.racer_number,
        e.racer_name,
        COUNT(*) as total_races,
        SUM(CASE WHEN rd.actual_course < e.pit_number THEN 1 ELSE 0 END) as forward_moves,
        ROUND(100.0 * SUM(CASE WHEN rd.actual_course < e.pit_number THEN 1 ELSE 0 END) / COUNT(*), 1) as forward_rate
    FROM entries e
    JOIN races ra ON e.race_id = ra.id
    JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    WHERE ra.race_date >= ?
      AND rd.actual_course IS NOT NULL
      AND e.pit_number > 1
    GROUP BY e.racer_number, e.racer_name
    HAVING COUNT(*) >= ? AND forward_rate >= ?
    ORDER BY forward_rate DESC
    """

    cursor.execute(query, (start_date, min_races, min_rate))
    results = cursor.fetchall()
    conn.close()

    forward_movers = []
    for row in results:
        forward_movers.append({
            'racer_number': row[0],
            'racer_name': row[1],
            'total_races': row[2],
            'forward_moves': row[3],
            'forward_rate': row[4]
        })

    return forward_movers


def save_forward_movers(forward_movers: list):
    """前付け常習者リストをJSONファイルに保存"""
    data = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'criteria': {
            'min_forward_rate': 40.0,
            'min_races': 30,
            'period_days': 365
        },
        'count': len(forward_movers),
        'racer_numbers': [m['racer_number'] for m in forward_movers],
        'details': forward_movers
    }

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"保存完了: {OUTPUT_PATH}")


def main():
    print("=" * 60)
    print("前付け常習者リスト抽出")
    print("=" * 60)

    forward_movers = extract_forward_movers()

    print(f"\n該当選手数: {len(forward_movers)}名\n")
    print(f"{'登録番号':>8} | {'選手名':<10} | {'出走数':>6} | {'前付け数':>8} | {'前付け率':>7}")
    print("-" * 60)

    for m in forward_movers:
        print(f"{m['racer_number']:>8} | {m['racer_name']:<10} | {m['total_races']:>6} | {m['forward_moves']:>8} | {m['forward_rate']:>6.1f}%")

    # JSONファイルに保存
    save_forward_movers(forward_movers)

    return forward_movers


if __name__ == "__main__":
    main()
