"""
複数日付の一括的中率検証
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from collections import defaultdict

def verify_date_accuracy(target_date):
    """指定日の的中率を計算"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            rp.pit_number as predicted_pit,
            rp.confidence,
            res.pit_number as result_pit
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND CAST(res.rank AS INTEGER) = 1
        WHERE r.race_date = ?
          AND rp.rank_prediction = 1
    """, (target_date,))

    predictions = cursor.fetchall()
    conn.close()

    if not predictions:
        return None

    total = len(predictions)
    correct = sum(1 for pred_pit, conf, result_pit in predictions if pred_pit == result_pit)

    # 信頼度別
    by_conf = defaultdict(lambda: {'total': 0, 'correct': 0})
    for pred_pit, conf, result_pit in predictions:
        by_conf[conf]['total'] += 1
        if pred_pit == result_pit:
            by_conf[conf]['correct'] += 1

    return {
        'total': total,
        'correct': correct,
        'accuracy': (correct / total * 100) if total > 0 else 0,
        'by_confidence': dict(by_conf)
    }


def main():
    print("=" * 80)
    print("複数日付での一括的中率検証")
    print("=" * 80)

    # テスト対象日付
    test_dates = [
        '2025-11-17',  # 既に予測済み
        '2025-08-01',
        '2024-10-27',
        '2025-07-03',
        '2025-10-11',
    ]

    results = []

    print("\n日付別的中率:")
    print("-" * 80)
    print("日付       | レース数 | 的中数 | 的中率 | A    | B    | C    | D    | E")
    print("-" * 80)

    for date in test_dates:
        result = verify_date_accuracy(date)

        if result is None:
            print(f"{date} | 予測なし")
            continue

        total = result['total']
        correct = result['correct']
        accuracy = result['accuracy']

        # 信頼度別の的中率
        conf_str = []
        for conf in ['A', 'B', 'C', 'D', 'E']:
            if conf in result['by_confidence']:
                stats = result['by_confidence'][conf]
                conf_acc = (stats['correct'] / stats['total'] * 100) if stats['total'] > 0 else 0
                conf_str.append(f"{conf_acc:4.0f}%")
            else:
                conf_str.append("  - ")

        print(f"{date} |   {total:3d}    |  {correct:3d}   | {accuracy:5.1f}% | {' | '.join(conf_str)}")

        results.append({
            'date': date,
            'total': total,
            'correct': correct,
            'accuracy': accuracy
        })

    # 平均的中率
    if results:
        avg_accuracy = sum(r['accuracy'] for r in results) / len(results)
        total_races = sum(r['total'] for r in results)
        total_correct = sum(r['correct'] for r in results)
        overall_accuracy = (total_correct / total_races * 100) if total_races > 0 else 0

        print("-" * 80)
        print(f"平均的中率: {avg_accuracy:.1f}%")
        print(f"総合的中率: {total_correct}/{total_races} = {overall_accuracy:.1f}%")

    print("\n" + "=" * 80)
    print("検証完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
