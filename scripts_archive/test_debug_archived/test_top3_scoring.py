"""
三連対スコアリングのテスト

現在のスコア（1着確率ベース）と三連対スコア（3着以内確率ベース）を比較
信頼度Bレースで検証
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
    print("三連対スコアリングのテスト")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 信頼度Bのレースを取得
    cursor.execute('''
        SELECT DISTINCT race_id
        FROM race_predictions
        WHERE confidence = 'B'
          AND prediction_type = 'advance'
        LIMIT 10
    ''')
    race_ids = [row[0] for row in cursor.fetchall()]

    print(f"\nテストレース数: {len(race_ids)}")

    for race_id in race_ids:
        print("\n" + "=" * 80)

        # レース情報取得
        cursor.execute('''
            SELECT race_date, venue_code, race_number
            FROM races
            WHERE id = ?
        ''', (race_id,))
        race_info = cursor.fetchone()
        if not race_info:
            continue

        race_date, venue_code, race_number = race_info
        print(f"レースID: {race_id} ({race_date} {venue_code}場 {race_number}R)")

        # エントリー情報取得
        cursor.execute('''
            SELECT e.pit_number, e.racer_number, e.motor_number, r.name
            FROM entries e
            JOIN racers r ON e.racer_number = r.racer_number
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        ''', (race_id,))
        entries = []
        for row in cursor.fetchall():
            entries.append({
                'pit_number': row[0],
                'racer_number': row[1],
                'motor_number': row[2],
                'racer_name': row[3]
            })

        # 現在のスコア取得
        cursor.execute('''
            SELECT pit_number, total_score, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        current_scores = {row[0]: {'score': row[1], 'rank': row[2]} for row in cursor.fetchall()}

        # 実際の結果取得
        cursor.execute('''
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        actual_results = {row[0]: row[1] for row in cursor.fetchall()}

        print("\n【スコア比較】")
        print(f"{'艇':>2} {'選手名':<12} {'現スコア':>6} {'現順位':>4} {'三連対':>6} {'三順位':>4} {'実着順':>4}")
        print("-" * 70)

        # 三連対スコアを計算
        top3_scores = []
        for entry in entries:
            top3_result = scorer.calculate_top3_score(
                racer_number=entry['racer_number'],
                venue_code=venue_code,
                course=entry['pit_number'],
                motor_number=entry['motor_number'],
                race_date=race_date
            )
            top3_scores.append({
                'pit_number': entry['pit_number'],
                'racer_name': entry['racer_name'],
                'top3_score': top3_result['top3_score']
            })

        # 三連対スコアで順位付け
        top3_scores.sort(key=lambda x: x['top3_score'], reverse=True)
        top3_ranks = {item['pit_number']: rank + 1 for rank, item in enumerate(top3_scores)}

        # 表示
        for entry in entries:
            pit = entry['pit_number']
            current = current_scores.get(pit, {'score': 0, 'rank': '-'})
            top3_score = next((x['top3_score'] for x in top3_scores if x['pit_number'] == pit), 0)
            top3_rank = top3_ranks.get(pit, '-')
            actual_rank = actual_results.get(pit, '-')

            print(f"{pit:2d}号 {entry['racer_name']:<12} "
                  f"{current['score']:6.1f} {current['rank']:4} "
                  f"{top3_score:6.1f} {top3_rank:4} "
                  f"{actual_rank:4}")

        # 予想と実際の比較
        print("\n【予想結果】")

        # 現在のスコアでの予想（上位3艇）
        current_top3 = sorted(current_scores.items(), key=lambda x: x[1]['rank'])[:3]
        current_prediction = [pit for pit, _ in current_top3]

        # 三連対スコアでの予想（上位3艇）
        top3_prediction = [item['pit_number'] for item in top3_scores[:3]]

        # 実際の1-2-3着
        actual_top3 = sorted(actual_results.items(), key=lambda x: x[1])
        actual_finish = [pit for pit, _ in actual_top3]

        print(f"現スコア予想: {'-'.join(map(str, current_prediction))}")
        print(f"三連対予想　: {'-'.join(map(str, top3_prediction))}")
        print(f"実際の結果　: {'-'.join(map(str, actual_finish))}")

        # 的中判定
        current_hit = (current_prediction == actual_finish)
        top3_hit = (top3_prediction == actual_finish)

        print(f"\n現スコア: {'的中' if current_hit else '外れ'}")
        print(f"三連対　: {'的中' if top3_hit else '外れ'}")

        # カバレッジ（3艇中何艇が実際のTOP3に含まれるか）
        current_coverage = sum(1 for pit in current_prediction if pit in actual_finish)
        top3_coverage = sum(1 for pit in top3_prediction if pit in actual_finish)

        print(f"\nカバレッジ（3艇中）:")
        print(f"  現スコア: {current_coverage}/3艇")
        print(f"  三連対　: {top3_coverage}/3艇")

    conn.close()

    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
