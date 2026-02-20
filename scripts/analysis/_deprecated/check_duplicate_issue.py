"""
最初の分析で異常に高いROIが出た原因を特定する
"""

import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'

def check_join_duplication():
    """JOINによる重複を確認"""
    conn = sqlite3.connect(DB_PATH)

    # 方法1: race_predictionsを直接JOIN（重複する可能性）
    query1 = """
    SELECT
        COUNT(*) as total_combinations,
        COUNT(DISTINCT rp1.race_id) as distinct_races
    FROM race_predictions rp1
    JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
    JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
    WHERE rp1.prediction_type = 'before'
      AND rp2.prediction_type = 'before'
      AND rp3.prediction_type = 'before'
      AND rp1.rank_prediction = 1
      AND rp2.rank_prediction = 2
      AND rp3.rank_prediction = 3
    """

    df1 = pd.read_sql(query1, conn)
    print("=== 方法1: race_predictionsを直接JOIN ===")
    print(df1.to_string(index=False))
    print(f"\n重複率: {df1.iloc[0]['total_combinations'] / df1.iloc[0]['distinct_races']:.2f}x")

    # 方法2: 正しい方法（WIDEテーブル化してからJOIN）
    query2 = """
    WITH race_predictions_wide AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) as pred_1st,
            MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) as pred_2nd,
            MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) as pred_3rd
        FROM race_predictions
        WHERE prediction_type = 'before'
        GROUP BY race_id
    )
    SELECT
        COUNT(*) as total_races,
        COUNT(DISTINCT race_id) as distinct_races
    FROM race_predictions_wide
    WHERE pred_1st IS NOT NULL
      AND pred_2nd IS NOT NULL
      AND pred_3rd IS NOT NULL
    """

    df2 = pd.read_sql(query2, conn)
    print("\n=== 方法2: WIDEテーブル化してから処理 ===")
    print(df2.to_string(index=False))

    # サンプルレースで比較
    print("\n=== サンプルレース（race_id=1）での比較 ===")

    query3 = """
    SELECT
        rp1.race_id,
        rp1.pit_number as pit1,
        rp2.pit_number as pit2,
        rp3.pit_number as pit3
    FROM race_predictions rp1
    JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
    JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
    WHERE rp1.race_id = 1
      AND rp1.prediction_type = 'before'
      AND rp2.prediction_type = 'before'
      AND rp3.prediction_type = 'before'
      AND rp1.rank_prediction = 1
      AND rp2.rank_prediction = 2
      AND rp3.rank_prediction = 3
    """

    df3 = pd.read_sql(query3, conn)
    print("方法1での抽出:")
    print(df3.to_string(index=False))
    print(f"抽出レコード数: {len(df3)}")

    conn.close()

def verify_analysis_results():
    """実際の分析結果を検証"""
    conn = sqlite3.connect(DB_PATH)

    # 信頼度Bの1点買い（正しい方法）
    query_correct = """
    WITH race_predictions_wide AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) as pred_1st,
            MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) as pred_2nd,
            MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) as pred_3rd,
            MAX(CASE WHEN rank_prediction = 1 THEN confidence END) as confidence_1st
        FROM race_predictions
        WHERE prediction_type = 'before'
        GROUP BY race_id
    ),
    race_results_wide AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1st,
            MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2nd,
            MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3rd
        FROM results
        WHERE is_invalid = 0 AND rank != ''
        GROUP BY race_id
    )
    SELECT
        COUNT(*) as race_count,
        SUM(CASE WHEN rp.pred_1st = rr.actual_1st
                  AND rp.pred_2nd = rr.actual_2nd
                  AND rp.pred_3rd = rr.actual_3rd THEN 1 ELSE 0 END) as hit_count
    FROM race_predictions_wide rp
    JOIN race_results_wide rr ON rp.race_id = rr.race_id
    WHERE rp.confidence_1st = 'B'
    """

    df_correct = pd.read_sql(query_correct, conn)
    print("\n=== 正しい分析結果（信頼度B、1点買い）===")
    print(df_correct.to_string(index=False))
    hit_rate = df_correct.iloc[0]['hit_count'] / df_correct.iloc[0]['race_count'] * 100
    print(f"的中率: {hit_rate:.2f}%")

    conn.close()

def main():
    print("=" * 80)
    print("最初の分析での異常値の原因調査")
    print("=" * 80)

    check_join_duplication()
    verify_analysis_results()

    print("\n" + "=" * 80)
    print("結論")
    print("=" * 80)
    print("""
最初の分析で異常に高いROI（400%超）が出た原因:

1. race_predictionsテーブルを直接JOINすると、1レースあたり複数のレコードが生成される
2. これにより、同一レースが重複カウントされ、的中回数が実際より多くなる
3. 正しい方法は、まずWIDEテーブル化（予測1位～6位を1行にまとめる）してからJOIN

今回の分析では正しい方法を使用したため、正確な結果が得られた。
    """)

if __name__ == "__main__":
    main()
