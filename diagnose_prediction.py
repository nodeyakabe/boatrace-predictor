"""
予測精度問題の診断スクリプト
- 現在の重み設定を確認
- スコア分布を分析
- 1着予測の傾向を分析
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from src.utils.scoring_config import ScoringConfig
from collections import Counter

def diagnose():
    print("=" * 60)
    print("予測精度診断")
    print("=" * 60)

    # 1. 現在の重み設定を確認
    print("\n[1] 現在の重み設定")
    config = ScoringConfig()
    weights = config.load_weights()
    for key, value in weights.items():
        print(f"  {key}: {value}")

    # 2. 過去レースの実績を確認（1コース勝率）
    print("\n[2] 過去データの1コース勝率")
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 1着になった艇の分布（pit_numberをコースと仮定）
    cursor.execute("""
        SELECT
            pit_number,
            COUNT(*) as wins
        FROM results
        WHERE rank = '1'
        GROUP BY pit_number
        ORDER BY pit_number
    """)
    wins_by_pit = cursor.fetchall()
    total_races = sum(w[1] for w in wins_by_pit)

    if wins_by_pit:
        print(f"  総レース数: {total_races}")
        for pit, wins in wins_by_pit:
            win_rate = wins / total_races * 100
            print(f"  {pit}号艇1着: {wins} ({win_rate:.1f}%)")

    # 3. 予測データの傾向を分析
    print("\n[3] 予測データの1着予測分布")
    cursor.execute("""
        SELECT pit_number, COUNT(*) as count
        FROM race_predictions
        WHERE rank_prediction = 1
        GROUP BY pit_number
        ORDER BY count DESC
    """)
    predictions = cursor.fetchall()
    total_predictions = sum(p[1] for p in predictions)

    for pit, count in predictions:
        pct = count / total_predictions * 100 if total_predictions > 0 else 0
        print(f"  {pit}号艇: {count}回 ({pct:.1f}%)")

    # 4. サンプルレースのスコア内訳を確認
    print("\n[4] サンプルレースのスコア内訳")
    cursor.execute("""
        SELECT
            rp.pit_number,
            rp.total_score,
            rp.rank_prediction,
            e.racer_name,
            e.win_rate
        FROM race_predictions rp
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        WHERE rp.race_id = (
            SELECT id FROM races WHERE race_date = '2025-11-19' LIMIT 1
        )
        ORDER BY rp.rank_prediction
    """)
    sample = cursor.fetchall()
    if sample:
        print("  順位 | 枠 | 選手名 | 勝率 | スコア")
        print("  " + "-" * 50)
        for pit, score, rank, name, win_rate in sample:
            print(f"  {rank}位 | {pit}号艇 | {name:8s} | {win_rate or 0:.2f} | {score:.1f}")

    # 5. 実際の結果との比較
    print("\n[5] 予測 vs 実結果（直近レース）")
    cursor.execute("""
        SELECT
            ra.venue_code,
            ra.race_number,
            rp.pit_number as predicted_1st,
            res.pit_number as actual_1st,
            CASE WHEN rp.pit_number = res.pit_number THEN 'O' ELSE 'X' END as result
        FROM races ra
        JOIN race_predictions rp ON ra.id = rp.race_id AND rp.rank_prediction = 1
        JOIN results res ON ra.id = res.race_id AND res.rank = '1'
        WHERE ra.race_date = (SELECT MAX(race_date) FROM results r2 JOIN races ra2 ON r2.race_id = ra2.id)
        ORDER BY ra.venue_code, ra.race_number
        LIMIT 20
    """)
    comparisons = cursor.fetchall()
    if comparisons:
        correct = sum(1 for c in comparisons if c[4] == 'O')
        total = len(comparisons)
        print(f"  直近{total}レースの的中: {correct}/{total} ({correct/total*100:.1f}%)")
        print("\n  会場 | R | 予測 | 実際 | 結果")
        print("  " + "-" * 35)
        for venue, race_num, pred, actual, result in comparisons[:10]:
            print(f"  {venue:4s} | {race_num:2d} | {pred}号艇 | {actual}号艇 | {result}")

    # 6. 6号艇が1着になっている割合
    print("\n[6] 6号艇予測問題の分析")
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN rp.pit_number = 6 THEN 1 ELSE 0 END) as pred_6,
            SUM(CASE WHEN res.pit_number = 6 THEN 1 ELSE 0 END) as actual_6
        FROM race_predictions rp
        JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
        WHERE rp.rank_prediction = 1
    """)
    row = cursor.fetchone()
    if row and row[0] > 0:
        total = row[0]
        pred_6 = row[1]
        actual_6 = row[2]
        print(f"  6号艇1着予測: {pred_6}/{total} ({pred_6/total*100:.1f}%)")
        print(f"  6号艇実際1着: {actual_6}/{total} ({actual_6/total*100:.1f}%)")

    conn.close()

    # 7. 問題点の特定
    print("\n[7] 問題点の特定")
    print("  - 1コースの勝率が約55%なのに、予測では6号艇が多い")
    print("  - これはスコア計算のバランスに問題がある")
    print("  - コーススコアの重みが低い、またはスケーリングに問題")

    print("\n" + "=" * 60)
    print("診断完了")
    print("=" * 60)


if __name__ == "__main__":
    diagnose()
