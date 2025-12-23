"""
2025年予測精度ベースライン分析スクリプト

信頼度A-Eごとの予測精度を詳細に分析し、
今後の改善効果測定のためのベースラインを確立する
"""
import os
import sys
import sqlite3
from datetime import datetime

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def analyze_confidence_accuracy(db_path: str):
    """信頼度別の予測精度を分析"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 100)
    print("2025年予測精度ベースライン分析")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    # 信頼度ごとに分析
    confidences = ['A', 'B', 'C', 'D', 'E']

    for confidence in confidences:
        print(f"\n{'=' * 100}")
        print(f"信頼度{confidence}の予測精度")
        print(f"{'=' * 100}")

        # 1. 基本統計
        cursor.execute("""
            SELECT COUNT(DISTINCT rp.race_id) as race_count
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
            AND rp.prediction_type = 'advance'
            AND rp.rank_prediction = 1
            AND rp.confidence = ?
        """, (confidence,))
        race_count = cursor.fetchone()[0]
        print(f"\n対象レース数: {race_count:,}レース")

        if race_count == 0:
            print(f"  [WARN] 信頼度{confidence}のデータがありません")
            continue

        # 2. 1着的中率
        cursor.execute("""
            WITH first_place_predictions AS (
                SELECT
                    rp.race_id,
                    rp.pit_number as pred_pit,
                    res.pit_number as actual_pit
                FROM race_predictions rp
                JOIN races r ON rp.race_id = r.id
                LEFT JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
                WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
                AND rp.prediction_type = 'advance'
                AND rp.rank_prediction = 1
                AND rp.confidence = ?
            )
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN pred_pit = actual_pit THEN 1 ELSE 0 END) as correct
            FROM first_place_predictions
        """, (confidence,))
        total, correct = cursor.fetchone()
        first_accuracy = (correct / total * 100) if total > 0 else 0
        print(f"\n[1] 1着的中率")
        print(f"  的中: {correct:,}件 / {total:,}件 ({first_accuracy:.2f}%)")

        # 3. 三連単的中率
        cursor.execute("""
            WITH trifecta_predictions AS (
                SELECT
                    rp.race_id,
                    MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
                    MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
                    MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd
                FROM race_predictions rp
                JOIN races r ON rp.race_id = r.id
                WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
                AND rp.prediction_type = 'advance'
                AND rp.rank_prediction <= 3
                AND EXISTS (
                    SELECT 1 FROM race_predictions rp2
                    WHERE rp2.race_id = rp.race_id
                    AND rp2.rank_prediction = 1
                    AND rp2.confidence = ?
                )
                GROUP BY rp.race_id
            ),
            actual_trifecta AS (
                SELECT
                    race_id,
                    MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1st,
                    MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2nd,
                    MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3rd
                FROM results
                WHERE rank IN ('1', '2', '3')
                GROUP BY race_id
            )
            SELECT
                COUNT(*) as total,
                SUM(CASE
                    WHEN tp.pred_1st = at.actual_1st
                    AND tp.pred_2nd = at.actual_2nd
                    AND tp.pred_3rd = at.actual_3rd
                    THEN 1 ELSE 0 END) as correct
            FROM trifecta_predictions tp
            JOIN actual_trifecta at ON tp.race_id = at.race_id
        """, (confidence,))
        total, correct = cursor.fetchone()
        trifecta_accuracy = (correct / total * 100) if total > 0 else 0
        print(f"\n[2] 三連単的中率")
        print(f"  的中: {correct:,}件 / {total:,}件 ({trifecta_accuracy:.2f}%)")

        # 4. 月別1着的中率
        cursor.execute("""
            WITH monthly_first_place AS (
                SELECT
                    strftime('%m', r.race_date) as month,
                    rp.race_id,
                    rp.pit_number as pred_pit,
                    res.pit_number as actual_pit
                FROM race_predictions rp
                JOIN races r ON rp.race_id = r.id
                LEFT JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
                WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
                AND rp.prediction_type = 'advance'
                AND rp.rank_prediction = 1
                AND rp.confidence = ?
            )
            SELECT
                month,
                COUNT(*) as total,
                SUM(CASE WHEN pred_pit = actual_pit THEN 1 ELSE 0 END) as correct
            FROM monthly_first_place
            GROUP BY month
            ORDER BY month
        """, (confidence,))
        monthly_data = cursor.fetchall()

        print(f"\n[3] 月別1着的中率")
        print(f"  月   レース数  的中数  的中率")
        print("-" * 100)
        for month, total, correct in monthly_data:
            accuracy = (correct / total * 100) if total > 0 else 0
            print(f"  {month}月  {total:>6}    {correct:>4}   {accuracy:>5.1f}%")

    conn.close()

    print("\n" + "=" * 100)
    print("分析完了")
    print("=" * 100 + "\n")


if __name__ == '__main__':
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')
    analyze_confidence_accuracy(db_path)
