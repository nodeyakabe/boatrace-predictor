"""
P-5: モデル弱点調査

各予測モデルの失敗パターンを分類し、改善の方向性を明確化する
"""

import sqlite3
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple

DATABASE_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"


def get_prediction_results(start_date: str, end_date: str, limit: int = 5000):
    """予測結果と実際の結果を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 予測と結果を結合
    query = """
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        rp.confidence,
        rp.pit_number as predicted_pit,
        rp.rank_prediction as predicted_rank,
        res.pit_number as actual_pit,
        res.rank as actual_rank,
        res.kimarite
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id
    JOIN results res ON r.id = res.race_id AND rp.rank_prediction = res.rank
    WHERE r.race_date BETWEEN ? AND ?
      AND rp.prediction_type = 'advance'
      AND rp.rank_prediction IN (1, 2, 3)
      AND res.rank IN (1, 2, 3)
    ORDER BY r.race_date DESC
    LIMIT ?
    """

    cursor.execute(query, (start_date, end_date, limit))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_race_entries(race_id: int) -> Dict[int, Dict]:
    """レースのエントリー情報を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pit_number, racer_number, racer_rank
        FROM entries
        WHERE race_id = ?
    """, (race_id,))

    entries = {row['pit_number']: dict(row) for row in cursor.fetchall()}
    conn.close()
    return entries


def analyze_first_place_failures(results: List[Dict]) -> Dict:
    """1着予測の失敗パターンを分析"""
    stats = {
        'total': 0,
        'hit': 0,
        'miss': 0,
        'by_confidence': defaultdict(lambda: {'total': 0, 'hit': 0}),
        'by_predicted_course': defaultdict(lambda: {'total': 0, 'hit': 0}),
        'by_actual_course': defaultdict(lambda: {'total': 0, 'hit': 0}),
        'miss_patterns': defaultdict(int),  # 予測コース→実際コース
    }

    first_place_data = [r for r in results if r['predicted_rank'] == 1]

    for row in first_place_data:
        stats['total'] += 1
        conf = row['confidence'] or 'Unknown'
        pred_pit = row['predicted_pit']
        actual_pit = row['actual_pit']
        is_hit = (pred_pit == actual_pit)

        stats['by_confidence'][conf]['total'] += 1
        stats['by_predicted_course'][pred_pit]['total'] += 1
        stats['by_actual_course'][actual_pit]['total'] += 1

        if is_hit:
            stats['hit'] += 1
            stats['by_confidence'][conf]['hit'] += 1
            stats['by_predicted_course'][pred_pit]['hit'] += 1
            stats['by_actual_course'][actual_pit]['hit'] += 1
        else:
            stats['miss'] += 1
            pattern = f"{pred_pit}→{actual_pit}"
            stats['miss_patterns'][pattern] += 1

    return stats


def analyze_second_place_failures(results: List[Dict]) -> Dict:
    """2着予測の失敗パターンを分析"""
    stats = {
        'total': 0,
        'hit': 0,
        'miss': 0,
        'by_confidence': defaultdict(lambda: {'total': 0, 'hit': 0}),
        'by_first_hit': {'hit': {'total': 0, 'hit': 0}, 'miss': {'total': 0, 'hit': 0}},
        'miss_patterns': defaultdict(int),
    }

    # レースIDごとにグループ化して1着の的中も判定
    races = defaultdict(dict)
    for row in results:
        race_id = row['race_id']
        rank = row['predicted_rank']
        races[race_id][rank] = row

    for race_id, preds in races.items():
        if 2 not in preds:
            continue

        row = preds[2]
        stats['total'] += 1
        conf = row['confidence'] or 'Unknown'
        pred_pit = row['predicted_pit']
        actual_pit = row['actual_pit']
        is_hit = (pred_pit == actual_pit)

        # 1着が当たっているか
        first_hit = False
        if 1 in preds:
            first_hit = (preds[1]['predicted_pit'] == preds[1]['actual_pit'])

        stats['by_confidence'][conf]['total'] += 1
        key = 'hit' if first_hit else 'miss'
        stats['by_first_hit'][key]['total'] += 1

        if is_hit:
            stats['hit'] += 1
            stats['by_confidence'][conf]['hit'] += 1
            stats['by_first_hit'][key]['hit'] += 1
        else:
            stats['miss'] += 1
            pattern = f"{pred_pit}→{actual_pit}"
            stats['miss_patterns'][pattern] += 1

    return stats


def analyze_third_place_failures(results: List[Dict]) -> Dict:
    """3着予測の失敗パターンを分析"""
    stats = {
        'total': 0,
        'hit': 0,
        'miss': 0,
        'by_confidence': defaultdict(lambda: {'total': 0, 'hit': 0}),
        'by_first_second_hit': defaultdict(lambda: {'total': 0, 'hit': 0}),
        'miss_patterns': defaultdict(int),
    }

    # レースIDごとにグループ化
    races = defaultdict(dict)
    for row in results:
        race_id = row['race_id']
        rank = row['predicted_rank']
        races[race_id][rank] = row

    for race_id, preds in races.items():
        if 3 not in preds:
            continue

        row = preds[3]
        stats['total'] += 1
        conf = row['confidence'] or 'Unknown'
        pred_pit = row['predicted_pit']
        actual_pit = row['actual_pit']
        is_hit = (pred_pit == actual_pit)

        # 1着・2着の的中状況
        first_hit = 1 in preds and (preds[1]['predicted_pit'] == preds[1]['actual_pit'])
        second_hit = 2 in preds and (preds[2]['predicted_pit'] == preds[2]['actual_pit'])
        hit_key = f"1着{'○' if first_hit else '×'}2着{'○' if second_hit else '×'}"

        stats['by_confidence'][conf]['total'] += 1
        stats['by_first_second_hit'][hit_key]['total'] += 1

        if is_hit:
            stats['hit'] += 1
            stats['by_confidence'][conf]['hit'] += 1
            stats['by_first_second_hit'][hit_key]['hit'] += 1
        else:
            stats['miss'] += 1
            pattern = f"{pred_pit}→{actual_pit}"
            stats['miss_patterns'][pattern] += 1

    return stats


def analyze_kimarite_impact(results: List[Dict]) -> Dict:
    """決まり手別の精度を分析"""
    stats = defaultdict(lambda: {'total': 0, 'first_hit': 0, 'second_hit': 0, 'third_hit': 0})

    # レースIDごとにグループ化
    races = defaultdict(dict)
    for row in results:
        race_id = row['race_id']
        rank = row['predicted_rank']
        races[race_id][rank] = row

    for race_id, preds in races.items():
        if 1 not in preds:
            continue

        kimarite = preds[1].get('kimarite') or 'unknown'
        stats[kimarite]['total'] += 1

        if preds[1]['predicted_pit'] == preds[1]['actual_pit']:
            stats[kimarite]['first_hit'] += 1

        if 2 in preds and preds[2]['predicted_pit'] == preds[2]['actual_pit']:
            stats[kimarite]['second_hit'] += 1

        if 3 in preds and preds[3]['predicted_pit'] == preds[3]['actual_pit']:
            stats[kimarite]['third_hit'] += 1

    return stats


def print_results(first_stats, second_stats, third_stats, kimarite_stats):
    """結果を表示"""
    print("=" * 70)
    print("P-5 モデル弱点調査レポート")
    print("=" * 70)

    # 1着予測
    print("\n【1着予測の分析】")
    total = first_stats['total']
    hit_rate = first_stats['hit'] / total * 100 if total > 0 else 0
    print(f"全体: {first_stats['hit']}/{total} ({hit_rate:.1f}%)")

    print("\n信頼度別:")
    for conf in sorted(first_stats['by_confidence'].keys()):
        data = first_stats['by_confidence'][conf]
        rate = data['hit'] / data['total'] * 100 if data['total'] > 0 else 0
        print(f"  {conf}: {data['hit']}/{data['total']} ({rate:.1f}%)")

    print("\n予測コース別:")
    for course in sorted(first_stats['by_predicted_course'].keys()):
        data = first_stats['by_predicted_course'][course]
        rate = data['hit'] / data['total'] * 100 if data['total'] > 0 else 0
        print(f"  {course}コース: {data['hit']}/{data['total']} ({rate:.1f}%)")

    print("\n主な失敗パターン (Top 10):")
    sorted_patterns = sorted(first_stats['miss_patterns'].items(), key=lambda x: -x[1])[:10]
    for pattern, count in sorted_patterns:
        pct = count / first_stats['miss'] * 100 if first_stats['miss'] > 0 else 0
        print(f"  {pattern}: {count}回 ({pct:.1f}%)")

    # 2着予測
    print("\n" + "-" * 70)
    print("【2着予測の分析】")
    total = second_stats['total']
    hit_rate = second_stats['hit'] / total * 100 if total > 0 else 0
    print(f"全体: {second_stats['hit']}/{total} ({hit_rate:.1f}%)")

    print("\n1着的中との関係:")
    for key in ['hit', 'miss']:
        data = second_stats['by_first_hit'][key]
        rate = data['hit'] / data['total'] * 100 if data['total'] > 0 else 0
        label = "1着○" if key == 'hit' else "1着×"
        print(f"  {label}: {data['hit']}/{data['total']} ({rate:.1f}%)")

    print("\n主な失敗パターン (Top 10):")
    sorted_patterns = sorted(second_stats['miss_patterns'].items(), key=lambda x: -x[1])[:10]
    for pattern, count in sorted_patterns:
        pct = count / second_stats['miss'] * 100 if second_stats['miss'] > 0 else 0
        print(f"  {pattern}: {count}回 ({pct:.1f}%)")

    # 3着予測
    print("\n" + "-" * 70)
    print("【3着予測の分析】")
    total = third_stats['total']
    hit_rate = third_stats['hit'] / total * 100 if total > 0 else 0
    print(f"全体: {third_stats['hit']}/{total} ({hit_rate:.1f}%)")

    print("\n1着・2着的中との関係:")
    for key in sorted(third_stats['by_first_second_hit'].keys()):
        data = third_stats['by_first_second_hit'][key]
        rate = data['hit'] / data['total'] * 100 if data['total'] > 0 else 0
        print(f"  {key}: {data['hit']}/{data['total']} ({rate:.1f}%)")

    print("\n主な失敗パターン (Top 10):")
    sorted_patterns = sorted(third_stats['miss_patterns'].items(), key=lambda x: -x[1])[:10]
    for pattern, count in sorted_patterns:
        pct = count / third_stats['miss'] * 100 if third_stats['miss'] > 0 else 0
        print(f"  {pattern}: {count}回 ({pct:.1f}%)")

    # 決まり手別
    print("\n" + "-" * 70)
    print("【決まり手別の精度】")
    print(f"{'決まり手':<12} {'レース数':>8} {'1着':>8} {'2着':>8} {'3着':>8}")
    print("-" * 50)
    sorted_kimarite = sorted(kimarite_stats.items(), key=lambda x: -x[1]['total'])
    for kimarite, data in sorted_kimarite[:10]:
        first_rate = data['first_hit'] / data['total'] * 100 if data['total'] > 0 else 0
        second_rate = data['second_hit'] / data['total'] * 100 if data['total'] > 0 else 0
        third_rate = data['third_hit'] / data['total'] * 100 if data['total'] > 0 else 0
        print(f"{kimarite:<12} {data['total']:>8} {first_rate:>7.1f}% {second_rate:>7.1f}% {third_rate:>7.1f}%")

    # 改善ポイントの提案
    print("\n" + "=" * 70)
    print("【改善ポイント】")

    # 1着の弱点
    worst_pred_course = min(
        first_stats['by_predicted_course'].items(),
        key=lambda x: x[1]['hit'] / x[1]['total'] if x[1]['total'] > 50 else 1
    )
    if worst_pred_course[1]['total'] > 50:
        rate = worst_pred_course[1]['hit'] / worst_pred_course[1]['total'] * 100
        print(f"1. {worst_pred_course[0]}コース予測時の精度が低い ({rate:.1f}%) - 外コース予測ロジック見直し")

    # 2着の弱点
    first_miss_data = second_stats['by_first_hit']['miss']
    if first_miss_data['total'] > 0:
        rate = first_miss_data['hit'] / first_miss_data['total'] * 100
        print(f"2. 1着外れ時の2着精度が低い ({rate:.1f}%) - 1着予測に依存しすぎ")

    # 3着の弱点
    both_miss_key = "1着×2着×"
    if both_miss_key in third_stats['by_first_second_hit']:
        data = third_stats['by_first_second_hit'][both_miss_key]
        if data['total'] > 0:
            rate = data['hit'] / data['total'] * 100
            print(f"3. 1着・2着両外れ時の3着精度 ({rate:.1f}%) - 独立した3着予測が必要")

    # 決まり手別の弱点
    weak_kimarite = []
    for kimarite, data in kimarite_stats.items():
        if data['total'] >= 100:
            first_rate = data['first_hit'] / data['total'] * 100
            if first_rate < 40:
                weak_kimarite.append((kimarite, first_rate, data['total']))

    if weak_kimarite:
        weak_kimarite.sort(key=lambda x: x[1])
        print(f"4. 決まり手別弱点:")
        for k, rate, cnt in weak_kimarite[:3]:
            print(f"   - {k}: 1着精度{rate:.1f}% (n={cnt})")


def main():
    print("データ取得中...")
    results = get_prediction_results("2025-01-01", "2025-11-30", limit=10000)
    print(f"取得レコード数: {len(results)}")

    print("\n分析中...")
    first_stats = analyze_first_place_failures(results)
    second_stats = analyze_second_place_failures(results)
    third_stats = analyze_third_place_failures(results)
    kimarite_stats = analyze_kimarite_impact(results)

    print_results(first_stats, second_stats, third_stats, kimarite_stats)


if __name__ == "__main__":
    main()
