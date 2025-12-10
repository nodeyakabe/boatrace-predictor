"""
三連対スコアリングの性能評価（信頼度Bレース）

現在のスコア vs 三連対スコアの比較
"""

import sys
from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.top3_scorer import Top3Scorer


def main():
    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    scorer = Top3Scorer(str(db_path))

    print("=" * 80)
    print("三連対スコアリングの性能評価（信頼度Bレース）")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 信頼度Bのレースを取得（2024-2025年、最大200レース）
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        WHERE rp.confidence = 'B'
          AND rp.prediction_type = 'advance'
          AND r.race_date >= '2024-01-01'
          AND r.race_date < '2026-01-01'
        ORDER BY r.race_date
        LIMIT 200
    ''')
    races = cursor.fetchall()

    print(f"\n評価レース数: {len(races)}レース\n")

    # 統計
    stats = {
        'current': {'hit': 0, 'coverage_3': 0, 'coverage_2': 0, 'coverage_1': 0},
        'top3': {'hit': 0, 'coverage_3': 0, 'coverage_2': 0, 'coverage_1': 0},
        'total': 0
    }

    for idx, (race_id, race_date, venue_code, race_number) in enumerate(races):
        if (idx + 1) % 50 == 0:
            print(f"処理中: {idx+1}/{len(races)}レース...")

        # エントリー情報取得
        cursor.execute('''
            SELECT e.pit_number, e.racer_number, e.motor_number
            FROM entries e
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        ''', (race_id,))
        entries = []
        for row in cursor.fetchall():
            entries.append({
                'pit_number': row[0],
                'racer_number': row[1],
                'motor_number': row[2]
            })

        if len(entries) < 6:
            continue

        # 現在のスコア取得
        cursor.execute('''
            SELECT pit_number, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        current_ranks = {row[0]: row[1] for row in cursor.fetchall()}

        # 実際の結果取得
        cursor.execute('''
            SELECT pit_number, CAST(rank AS INTEGER) as rank_int
            FROM results
            WHERE race_id = ? AND is_invalid = 0 AND CAST(rank AS INTEGER) <= 3
            ORDER BY rank_int
        ''', (race_id,))
        actual_results = cursor.fetchall()

        if len(actual_results) < 3:
            continue

        actual_finish = [row[0] for row in actual_results]

        # 三連対スコアを計算
        top3_scores = []
        for entry in entries:
            try:
                top3_result = scorer.calculate_top3_score(
                    racer_number=entry['racer_number'],
                    venue_code=venue_code,
                    course=entry['pit_number'],
                    motor_number=entry['motor_number'],
                    race_date=race_date
                )
                top3_scores.append({
                    'pit_number': entry['pit_number'],
                    'top3_score': top3_result['top3_score']
                })
            except Exception as e:
                continue

        if len(top3_scores) < 6:
            continue

        # 三連対スコアで順位付け
        top3_scores.sort(key=lambda x: x['top3_score'], reverse=True)
        top3_ranks = {item['pit_number']: rank + 1 for rank, item in enumerate(top3_scores)}

        # 現在のスコアでの予想（上位3艇）
        current_top3_sorted = sorted(current_ranks.items(), key=lambda x: x[1])[:3]
        current_prediction = [pit for pit, _ in current_top3_sorted]

        # 三連対スコアでの予想（上位3艇）
        top3_prediction = [item['pit_number'] for item in top3_scores[:3]]

        stats['total'] += 1

        # 的中判定
        if current_prediction == actual_finish:
            stats['current']['hit'] += 1

        if top3_prediction == actual_finish:
            stats['top3']['hit'] += 1

        # カバレッジ（3艇中何艇が実際のTOP3に含まれるか）
        current_coverage = sum(1 for pit in current_prediction if pit in actual_finish)
        top3_coverage = sum(1 for pit in top3_prediction if pit in actual_finish)

        if current_coverage == 3:
            stats['current']['coverage_3'] += 1
        elif current_coverage == 2:
            stats['current']['coverage_2'] += 1
        elif current_coverage == 1:
            stats['current']['coverage_1'] += 1

        if top3_coverage == 3:
            stats['top3']['coverage_3'] += 1
        elif top3_coverage == 2:
            stats['top3']['coverage_2'] += 1
        elif top3_coverage == 1:
            stats['top3']['coverage_1'] += 1

    conn.close()

    # 結果表示
    print("\n" + "=" * 80)
    print("評価結果サマリー")
    print("=" * 80)

    print(f"\n評価レース数: {stats['total']}レース")

    print("\n【三連単的中率】")
    current_hit_rate = stats['current']['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0
    top3_hit_rate = stats['top3']['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0

    print(f"  現在のスコア: {stats['current']['hit']}/{stats['total']} = {current_hit_rate:.2f}%")
    print(f"  三連対スコア: {stats['top3']['hit']}/{stats['total']} = {top3_hit_rate:.2f}%")
    print(f"  差分: {top3_hit_rate - current_hit_rate:+.2f}pt")

    print("\n【カバレッジ分析（予想3艇のうち実際のTOP3に何艇含まれるか）】")

    print("\n現在のスコア:")
    print(f"  3艇とも的中: {stats['current']['coverage_3']}レース ({stats['current']['coverage_3']/stats['total']*100:.1f}%)")
    print(f"  2艇的中: {stats['current']['coverage_2']}レース ({stats['current']['coverage_2']/stats['total']*100:.1f}%)")
    print(f"  1艇的中: {stats['current']['coverage_1']}レース ({stats['current']['coverage_1']/stats['total']*100:.1f}%)")
    print(f"  0艇的中: {stats['total'] - stats['current']['coverage_3'] - stats['current']['coverage_2'] - stats['current']['coverage_1']}レース")

    print("\n三連対スコア:")
    print(f"  3艇とも的中: {stats['top3']['coverage_3']}レース ({stats['top3']['coverage_3']/stats['total']*100:.1f}%)")
    print(f"  2艇的中: {stats['top3']['coverage_2']}レース ({stats['top3']['coverage_2']/stats['total']*100:.1f}%)")
    print(f"  1艇的中: {stats['top3']['coverage_1']}レース ({stats['top3']['coverage_1']/stats['total']*100:.1f}%)")
    print(f"  0艇的中: {stats['total'] - stats['top3']['coverage_3'] - stats['top3']['coverage_2'] - stats['top3']['coverage_1']}レース")

    # 平均カバレッジ
    current_avg_coverage = (
        stats['current']['coverage_3'] * 3 +
        stats['current']['coverage_2'] * 2 +
        stats['current']['coverage_1'] * 1
    ) / stats['total'] if stats['total'] > 0 else 0

    top3_avg_coverage = (
        stats['top3']['coverage_3'] * 3 +
        stats['top3']['coverage_2'] * 2 +
        stats['top3']['coverage_1'] * 1
    ) / stats['total'] if stats['total'] > 0 else 0

    print(f"\n平均カバレッジ（3艇中）:")
    print(f"  現在のスコア: {current_avg_coverage:.2f}艇")
    print(f"  三連対スコア: {top3_avg_coverage:.2f}艇")
    print(f"  差分: {top3_avg_coverage - current_avg_coverage:+.2f}艇")

    print("\n" + "=" * 80)
    print("評価完了")
    print("=" * 80)

    # 結論
    print("\n【結論】")
    if top3_hit_rate > current_hit_rate:
        print(f"三連対スコアは現在のスコアより{top3_hit_rate - current_hit_rate:.2f}pt優れています")
    else:
        print(f"現在のスコアは三連対スコアより{current_hit_rate - top3_hit_rate:.2f}pt優れています")

    if top3_avg_coverage > current_avg_coverage:
        print(f"三連対スコアはカバレッジが{top3_avg_coverage - current_avg_coverage:.2f}艇分優れています")
        print("→ 2着・3着の艇をより正確に捉えています")
    else:
        print("カバレッジに大きな差はありません")


if __name__ == "__main__":
    main()
