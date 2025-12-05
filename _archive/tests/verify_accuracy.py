"""
予測的中率検証スクリプト
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from collections import defaultdict

def verify_accuracy(target_date='2025-11-17'):
    print("=" * 80)
    print(f"予測的中率検証: {target_date}")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 予測と結果を結合して取得
    cursor.execute("""
        SELECT
            r.venue_code,
            r.race_number,
            rp.pit_number as predicted_pit,
            rp.rank_prediction,
            rp.confidence,
            rp.total_score,
            res.pit_number as result_pit,
            res.rank
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND CAST(res.rank AS INTEGER) = rp.rank_prediction
        WHERE r.race_date = ?
          AND rp.rank_prediction = 1
        ORDER BY r.venue_code, r.race_number
    """, (target_date,))

    predictions = cursor.fetchall()

    if not predictions:
        print("予測データまたは結果データがありません")
        conn.close()
        return

    # 統計情報
    total_races = len(predictions)
    correct_1st = 0
    by_confidence = defaultdict(lambda: {'total': 0, 'correct': 0})
    by_pit = defaultdict(lambda: {'total': 0, 'correct': 0})

    print(f"\n全レース数: {total_races}")
    print("\n詳細結果:")
    print("-" * 80)
    print("会場 | R# | 予測 | 信頼度 | スコア | 実際の1着 | 的中")
    print("-" * 80)

    for venue, race, pred_pit, rank, conf, score, result_pit, finish in predictions:
        # 実際の1着を取得（result_pitはNoneの場合がある）
        if result_pit is None:
            # 結果データから1着を取得
            cursor.execute("""
                SELECT pit_number
                FROM results
                WHERE race_id = (SELECT id FROM races WHERE venue_code = ? AND race_number = ? AND race_date = ?)
                  AND CAST(rank AS INTEGER) = 1
            """, (venue, race, target_date))
            actual_first = cursor.fetchone()
            actual_first = actual_first[0] if actual_first else None
        else:
            actual_first = result_pit

        is_correct = (pred_pit == actual_first) if actual_first else False

        if is_correct:
            correct_1st += 1

        # 統計を記録
        by_confidence[conf]['total'] += 1
        if is_correct:
            by_confidence[conf]['correct'] += 1

        by_pit[pred_pit]['total'] += 1
        if is_correct:
            by_pit[pred_pit]['correct'] += 1

        hit_mark = "○" if is_correct else "×"
        actual_str = f"{actual_first}号艇" if actual_first else "N/A"

        print(f"{int(venue):02d}   | {int(race):2d} | {pred_pit}号艇 | {conf:4s}   | {score:5.1f} | {actual_str:6s} | {hit_mark}")

    # サマリー
    print("-" * 80)
    print("\n" + "=" * 80)
    print("的中率サマリー")
    print("=" * 80)

    accuracy = (correct_1st / total_races * 100) if total_races > 0 else 0
    print(f"\n総合的中率: {correct_1st}/{total_races} = {accuracy:.1f}%")

    # 信頼度別の的中率
    print("\n信頼度別の的中率:")
    print("  信頼度 | レース数 | 的中数 | 的中率")
    print("  " + "-" * 45)
    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf in by_confidence:
            stats = by_confidence[conf]
            conf_acc = (stats['correct'] / stats['total'] * 100) if stats['total'] > 0 else 0
            print(f"  {conf:4s}   | {stats['total']:4d}     | {stats['correct']:4d}   | {conf_acc:5.1f}%")

    # 号艇別の予測数と的中率
    print("\n予測号艇別の的中率:")
    print("  号艇 | 予測回数 | 的中数 | 的中率")
    print("  " + "-" * 45)
    for pit in sorted(by_pit.keys()):
        stats = by_pit[pit]
        pit_acc = (stats['correct'] / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"  {pit}号艇 | {stats['total']:4d}     | {stats['correct']:4d}   | {pit_acc:5.1f}%")

    # 1号艇の実際の勝率
    print("\n" + "=" * 80)
    print("実際の結果分布")
    print("=" * 80)

    cursor.execute("""
        SELECT res.pit_number, COUNT(*) as count
        FROM results res
        JOIN races r ON res.race_id = r.id
        WHERE r.race_date = ?
          AND CAST(res.rank AS INTEGER) = 1
        GROUP BY res.pit_number
        ORDER BY res.pit_number
    """, (target_date,))

    actual_results = cursor.fetchall()
    actual_total = sum(r[1] for r in actual_results)

    print(f"\n実際の1着分布（{actual_total}レース）:")
    for pit, count in actual_results:
        pct = count / actual_total * 100 if actual_total > 0 else 0
        print(f"  {pit}号艇: {count:3d}回 ({pct:5.1f}%)")

    conn.close()

    print("\n" + "=" * 80)
    print("検証完了")
    print("=" * 80)


if __name__ == "__main__":
    import sys
    target_date = sys.argv[1] if len(sys.argv) > 1 else '2025-11-17'
    verify_accuracy(target_date)
