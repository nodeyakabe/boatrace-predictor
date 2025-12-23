"""
前付け常習者フィルターの効果測定

P-1タスク: 前付け常習者がいるレースを除外した場合の効果を検証
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

DATABASE_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"
FORWARD_MOVERS_PATH = Path(__file__).parent.parent / "config" / "forward_movers.json"


def load_forward_movers():
    """前付け常習者リストを読み込む"""
    with open(FORWARD_MOVERS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return set(str(rn) for rn in data.get('racer_numbers', []))


def get_races_with_predictions(start_date: str, end_date: str):
    """予測データがあるレースを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # race_predictionsから各レースの1-3着予測を取得
    query = """
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        rp.prediction_type,
        rp.confidence,
        rp.pit_number,
        rp.rank_prediction
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id
    WHERE r.race_date BETWEEN ? AND ?
      AND rp.prediction_type = 'advance'
      AND rp.rank_prediction IN (1, 2, 3)
    ORDER BY r.id, rp.rank_prediction
    """

    cursor.execute(query, (start_date, end_date))
    rows = cursor.fetchall()
    conn.close()

    # レースIDごとに予測を集約
    race_predictions = {}
    for row in rows:
        race_id = row['race_id']
        if race_id not in race_predictions:
            race_predictions[race_id] = {
                'race_id': race_id,
                'race_date': row['race_date'],
                'venue_code': row['venue_code'],
                'confidence': row['confidence'],
                'predicted_first': None,
                'predicted_second': None,
                'predicted_third': None,
            }

        rank = row['rank_prediction']
        pit = row['pit_number']
        if rank == 1:
            race_predictions[race_id]['predicted_first'] = pit
        elif rank == 2:
            race_predictions[race_id]['predicted_second'] = pit
        elif rank == 3:
            race_predictions[race_id]['predicted_third'] = pit

    return list(race_predictions.values())


def get_race_entries(race_id: int):
    """レースの出走選手を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT racer_number
        FROM entries
        WHERE race_id = ?
    """, (race_id,))

    entries = [str(row[0]) for row in cursor.fetchall()]
    conn.close()
    return entries


def get_race_result(race_id: int):
    """レース結果を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pit_number, rank
        FROM results
        WHERE race_id = ?
        ORDER BY rank
    """, (race_id,))

    results = {}
    for row in cursor.fetchall():
        try:
            rank = int(row[1])
            if rank in [1, 2, 3]:
                results[rank] = row[0]
        except (ValueError, TypeError):
            continue

    conn.close()
    return results


def evaluate_filter_effect():
    """フィルター効果を測定"""
    forward_movers = load_forward_movers()
    print(f"前付け常習者: {len(forward_movers)}名")

    # 2025年データで検証
    start_date = "2025-01-01"
    end_date = "2025-11-30"

    print(f"\n検証期間: {start_date} ~ {end_date}")
    print("予測データを取得中...")

    races = get_races_with_predictions(start_date, end_date)
    print(f"取得レース数: {len(races)}")

    # 結果を集計
    results = {
        'all': {'total': 0, 'first_hit': 0, 'trifecta_hit': 0},
        'with_forward_mover': {'total': 0, 'first_hit': 0, 'trifecta_hit': 0},
        'without_forward_mover': {'total': 0, 'first_hit': 0, 'trifecta_hit': 0},
    }

    for i, race in enumerate(races):
        if i % 1000 == 0:
            print(f"  処理中: {i}/{len(races)}")

        race_id = race['race_id']
        entries = get_race_entries(race_id)
        actual = get_race_result(race_id)

        if not actual or 1 not in actual:
            continue

        # 前付け常習者がいるか
        has_forward_mover = any(rn in forward_movers for rn in entries)

        pred_first = race['predicted_first']
        pred_second = race['predicted_second']
        pred_third = race['predicted_third']

        actual_first = actual.get(1)
        actual_second = actual.get(2)
        actual_third = actual.get(3)

        # 1着的中判定
        first_hit = (pred_first == actual_first)

        # 3連単的中判定
        trifecta_hit = (
            pred_first == actual_first and
            pred_second == actual_second and
            pred_third == actual_third
        )

        # 全体
        results['all']['total'] += 1
        if first_hit:
            results['all']['first_hit'] += 1
        if trifecta_hit:
            results['all']['trifecta_hit'] += 1

        # 前付け常習者あり/なし
        key = 'with_forward_mover' if has_forward_mover else 'without_forward_mover'
        results[key]['total'] += 1
        if first_hit:
            results[key]['first_hit'] += 1
        if trifecta_hit:
            results[key]['trifecta_hit'] += 1

    return results


def print_results(results):
    """結果を表示"""
    print("\n" + "=" * 70)
    print("P-1 前付け常習者フィルター 効果測定結果")
    print("=" * 70)

    categories = [
        ('全体', 'all'),
        ('前付け常習者あり', 'with_forward_mover'),
        ('前付け常習者なし', 'without_forward_mover'),
    ]

    print(f"\n{'カテゴリ':<20} {'レース数':>10} {'1着的中率':>12} {'3連単的中率':>12}")
    print("-" * 60)

    for label, key in categories:
        data = results[key]
        total = data['total']
        if total == 0:
            continue

        first_rate = data['first_hit'] / total * 100
        trifecta_rate = data['trifecta_hit'] / total * 100

        print(f"{label:<20} {total:>10} {first_rate:>11.2f}% {trifecta_rate:>11.2f}%")

    # 改善効果の計算
    print("\n" + "-" * 60)
    print("【改善効果】")

    all_total = results['all']['total']
    all_first = results['all']['first_hit'] / all_total * 100 if all_total > 0 else 0

    without_total = results['without_forward_mover']['total']
    without_first = results['without_forward_mover']['first_hit'] / without_total * 100 if without_total > 0 else 0

    with_total = results['with_forward_mover']['total']
    with_first = results['with_forward_mover']['first_hit'] / with_total * 100 if with_total > 0 else 0

    print(f"  除外対象レース数: {with_total}件 ({with_total/all_total*100:.1f}%)")
    print(f"  除外後レース数: {without_total}件")
    print(f"  1着的中率改善: {all_first:.2f}% → {without_first:.2f}% ({without_first - all_first:+.2f}pt)")
    print(f"  前付けありレースの精度: {with_first:.2f}%")
    print(f"  精度差: {without_first - with_first:.2f}pt")


def main():
    results = evaluate_filter_effect()
    print_results(results)


if __name__ == "__main__":
    main()
