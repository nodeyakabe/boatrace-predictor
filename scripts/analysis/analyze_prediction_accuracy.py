"""
予測精度の詳細分析スクリプト

予測順位別の的中率を徹底的に分析し、特に予測3位の3着的中率が低い原因を究明する。
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# データベースパス
DB_PATH = r"c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db"

def get_db_connection():
    """データベース接続を取得"""
    return sqlite3.connect(DB_PATH)

def analyze_basic_prediction_accuracy():
    """基本的な予測精度分析"""
    conn = get_db_connection()

    # 予測順位別 × 実際の着順のマトリックス
    query = """
    WITH prediction_actual AS (
        SELECT
            rp.rank_prediction as predicted_rank,
            r.pit_number,
            CAST(r.rank AS INTEGER) as result_rank,
            rp.confidence
        FROM race_predictions rp
        JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
        WHERE r.rank IS NOT NULL
            AND r.rank != ''
            AND CAST(r.rank AS INTEGER) > 0
            AND rp.rank_prediction BETWEEN 1 AND 6
    )
    SELECT
        predicted_rank,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN result_rank = 1 THEN 1 ELSE 0 END) as rank1_count,
        SUM(CASE WHEN result_rank = 2 THEN 1 ELSE 0 END) as rank2_count,
        SUM(CASE WHEN result_rank = 3 THEN 1 ELSE 0 END) as rank3_count,
        SUM(CASE WHEN result_rank = 4 THEN 1 ELSE 0 END) as rank4_count,
        SUM(CASE WHEN result_rank = 5 THEN 1 ELSE 0 END) as rank5_count,
        SUM(CASE WHEN result_rank = 6 THEN 1 ELSE 0 END) as rank6_count,
        ROUND(AVG(CASE WHEN result_rank = 1 THEN 100.0 ELSE 0 END), 2) as rank1_rate,
        ROUND(AVG(CASE WHEN result_rank = 2 THEN 100.0 ELSE 0 END), 2) as rank2_rate,
        ROUND(AVG(CASE WHEN result_rank = 3 THEN 100.0 ELSE 0 END), 2) as rank3_rate,
        ROUND(AVG(CASE WHEN result_rank = 4 THEN 100.0 ELSE 0 END), 2) as rank4_rate,
        ROUND(AVG(CASE WHEN result_rank = 5 THEN 100.0 ELSE 0 END), 2) as rank5_rate,
        ROUND(AVG(CASE WHEN result_rank = 6 THEN 100.0 ELSE 0 END), 2) as rank6_rate
    FROM prediction_actual
    GROUP BY predicted_rank
    ORDER BY predicted_rank
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def analyze_confidence_level_accuracy():
    """信頼度別の予測精度分析"""
    conn = get_db_connection()

    query = """
    WITH prediction_actual AS (
        SELECT
            rp.rank_prediction as predicted_rank,
            CAST(r.rank AS INTEGER) as result_rank,
            rp.confidence
        FROM race_predictions rp
        JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
        WHERE r.rank IS NOT NULL
            AND r.rank != ''
            AND CAST(r.rank AS INTEGER) > 0
            AND rp.rank_prediction BETWEEN 1 AND 3
    )
    SELECT
        confidence,
        predicted_rank,
        COUNT(*) as total,
        SUM(CASE WHEN predicted_rank = result_rank THEN 1 ELSE 0 END) as correct,
        ROUND(AVG(CASE WHEN predicted_rank = result_rank THEN 100.0 ELSE 0 END), 2) as accuracy_rate
    FROM prediction_actual
    GROUP BY confidence, predicted_rank
    ORDER BY confidence, predicted_rank
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def analyze_rank3_by_course():
    """予測3位のコース別3着的中率"""
    conn = get_db_connection()

    query = """
    SELECT
        rp.pit_number as course,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN CAST(r.rank AS INTEGER) = 3 THEN 1 ELSE 0 END) as rank3_correct,
        ROUND(AVG(CASE WHEN CAST(r.rank AS INTEGER) = 3 THEN 100.0 ELSE 0 END), 2) as rank3_accuracy,
        ROUND(AVG(CAST(r.rank AS INTEGER)), 2) as avg_actual_rank
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    WHERE rp.rank_prediction = 3
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
    GROUP BY rp.pit_number
    ORDER BY rp.pit_number
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def analyze_rank3_by_venue():
    """予測3位の会場別3着的中率"""
    conn = get_db_connection()

    query = """
    SELECT
        ra.venue_code,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN CAST(r.rank AS INTEGER) = 3 THEN 1 ELSE 0 END) as rank3_correct,
        ROUND(AVG(CASE WHEN CAST(r.rank AS INTEGER) = 3 THEN 100.0 ELSE 0 END), 2) as rank3_accuracy,
        ROUND(AVG(CAST(r.rank AS INTEGER)), 2) as avg_actual_rank
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    JOIN races ra ON rp.race_id = ra.id
    WHERE rp.rank_prediction = 3
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
    GROUP BY ra.venue_code
    ORDER BY rank3_accuracy DESC
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def analyze_rank3_by_class():
    """予測3位の級別3着的中率"""
    conn = get_db_connection()

    query = """
    SELECT
        e.racer_rank as class,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN CAST(r.rank AS INTEGER) = 3 THEN 1 ELSE 0 END) as rank3_correct,
        ROUND(AVG(CASE WHEN CAST(r.rank AS INTEGER) = 3 THEN 100.0 ELSE 0 END), 2) as rank3_accuracy,
        ROUND(AVG(CAST(r.rank AS INTEGER)), 2) as avg_actual_rank
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
    WHERE rp.rank_prediction = 3
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
        AND e.racer_rank IS NOT NULL
        AND e.racer_rank != ''
    GROUP BY e.racer_rank
    ORDER BY rank3_accuracy DESC
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def analyze_rank3_by_exhibition_time():
    """予測3位の展示タイム別3着的中率"""
    conn = get_db_connection()

    query = """
    SELECT
        CASE
            WHEN rd.exhibition_time < 6.70 THEN '~6.69'
            WHEN rd.exhibition_time < 6.75 THEN '6.70-6.74'
            WHEN rd.exhibition_time < 6.80 THEN '6.75-6.79'
            WHEN rd.exhibition_time < 6.85 THEN '6.80-6.84'
            WHEN rd.exhibition_time < 6.90 THEN '6.85-6.89'
            WHEN rd.exhibition_time < 6.95 THEN '6.90-6.94'
            WHEN rd.exhibition_time < 7.00 THEN '6.95-6.99'
            ELSE '7.00~'
        END as exhibition_time_range,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN CAST(r.rank AS INTEGER) = 3 THEN 1 ELSE 0 END) as rank3_correct,
        ROUND(AVG(CASE WHEN CAST(r.rank AS INTEGER) = 3 THEN 100.0 ELSE 0 END), 2) as rank3_accuracy,
        ROUND(AVG(rd.exhibition_time), 3) as avg_exhibition_time
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    JOIN race_details rd ON rp.race_id = rd.race_id AND rp.pit_number = rd.pit_number
    WHERE rp.rank_prediction = 3
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
        AND rd.exhibition_time IS NOT NULL
        AND rd.exhibition_time > 0
    GROUP BY exhibition_time_range
    ORDER BY avg_exhibition_time
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def analyze_rank3_by_motor_performance():
    """予測3位のモーター性能別3着的中率"""
    conn = get_db_connection()

    query = """
    SELECT
        CASE
            WHEN e.motor_second_rate < 30 THEN '~29%'
            WHEN e.motor_second_rate < 35 THEN '30-34%'
            WHEN e.motor_second_rate < 40 THEN '35-39%'
            WHEN e.motor_second_rate < 45 THEN '40-44%'
            WHEN e.motor_second_rate < 50 THEN '45-49%'
            ELSE '50%~'
        END as motor_2rate_range,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN CAST(r.rank AS INTEGER) = 3 THEN 1 ELSE 0 END) as rank3_correct,
        ROUND(AVG(CASE WHEN CAST(r.rank AS INTEGER) = 3 THEN 100.0 ELSE 0 END), 2) as rank3_accuracy,
        ROUND(AVG(e.motor_second_rate), 2) as avg_motor_2rate
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
    WHERE rp.rank_prediction = 3
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
        AND e.motor_second_rate IS NOT NULL
        AND e.motor_second_rate > 0
    GROUP BY motor_2rate_range
    ORDER BY avg_motor_2rate
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def analyze_rank3_by_odds():
    """予測3位のオッズ別3着的中率"""
    conn = get_db_connection()

    query = """
    SELECT
        CASE
            WHEN wo.odds < 5 THEN '~4.9'
            WHEN wo.odds < 10 THEN '5-9.9'
            WHEN wo.odds < 20 THEN '10-19.9'
            WHEN wo.odds < 30 THEN '20-29.9'
            WHEN wo.odds < 50 THEN '30-49.9'
            ELSE '50~'
        END as odds_range,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN CAST(r.rank AS INTEGER) = 3 THEN 1 ELSE 0 END) as rank3_correct,
        ROUND(AVG(CASE WHEN CAST(r.rank AS INTEGER) = 3 THEN 100.0 ELSE 0 END), 2) as rank3_accuracy,
        ROUND(AVG(wo.odds), 2) as avg_odds
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    LEFT JOIN win_odds wo ON rp.race_id = wo.race_id AND rp.pit_number = wo.pit_number
    WHERE rp.rank_prediction = 3
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
        AND wo.odds IS NOT NULL
        AND wo.odds > 0
    GROUP BY odds_range
    ORDER BY avg_odds
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def analyze_rank3_miss_distribution():
    """予測3位が外れた時の実際の着順分布"""
    conn = get_db_connection()

    query = """
    SELECT
        CAST(r.rank AS INTEGER) as result_rank,
        COUNT(*) as count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    WHERE rp.rank_prediction = 3
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
    GROUP BY CAST(r.rank AS INTEGER)
    ORDER BY result_rank
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def analyze_who_came_3rd():
    """実際に3着に来たのは予測何位だったか"""
    conn = get_db_connection()

    query = """
    SELECT
        rp.rank_prediction as predicted_rank,
        COUNT(*) as count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    WHERE r.rank = '3'
    GROUP BY rp.rank_prediction
    ORDER BY rp.rank_prediction
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def analyze_rank1_details():
    """予測1位の詳細分析"""
    conn = get_db_connection()

    # コース別
    query_course = """
    SELECT
        rp.pit_number as course,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN CAST(r.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) as rank1_correct,
        ROUND(AVG(CASE WHEN CAST(r.rank AS INTEGER) = 1 THEN 100.0 ELSE 0 END), 2) as rank1_accuracy
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    WHERE rp.rank_prediction = 1
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
    GROUP BY rp.pit_number
    ORDER BY rp.pit_number
    """
    df_course = pd.read_sql_query(query_course, conn)

    # 級別
    query_class = """
    SELECT
        e.racer_rank as class,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN CAST(r.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) as rank1_correct,
        ROUND(AVG(CASE WHEN CAST(r.rank AS INTEGER) = 1 THEN 100.0 ELSE 0 END), 2) as rank1_accuracy
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
    WHERE rp.rank_prediction = 1
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
        AND e.racer_rank IS NOT NULL
        AND e.racer_rank != ''
    GROUP BY e.racer_rank
    ORDER BY rank1_accuracy DESC
    """
    df_class = pd.read_sql_query(query_class, conn)

    # 会場別（上位10・下位10）
    query_venue = """
    SELECT
        ra.venue_code,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN CAST(r.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) as rank1_correct,
        ROUND(AVG(CASE WHEN CAST(r.rank AS INTEGER) = 1 THEN 100.0 ELSE 0 END), 2) as rank1_accuracy
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    JOIN races ra ON rp.race_id = ra.id
    WHERE rp.rank_prediction = 1
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
    GROUP BY ra.venue_code
    ORDER BY rank1_accuracy DESC
    """
    df_venue = pd.read_sql_query(query_venue, conn)

    conn.close()

    return {
        'course': df_course,
        'class': df_class,
        'venue': df_venue
    }

def analyze_rank2_details():
    """予測2位の詳細分析"""
    conn = get_db_connection()

    # コース別
    query_course = """
    SELECT
        rp.pit_number as course,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN CAST(r.rank AS INTEGER) = 2 THEN 1 ELSE 0 END) as rank2_correct,
        ROUND(AVG(CASE WHEN CAST(r.rank AS INTEGER) = 2 THEN 100.0 ELSE 0 END), 2) as rank2_accuracy
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    WHERE rp.rank_prediction = 2
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
    GROUP BY rp.pit_number
    ORDER BY rp.pit_number
    """
    df_course = pd.read_sql_query(query_course, conn)

    # 級別
    query_class = """
    SELECT
        e.racer_rank as class,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN CAST(r.rank AS INTEGER) = 2 THEN 1 ELSE 0 END) as rank2_correct,
        ROUND(AVG(CASE WHEN CAST(r.rank AS INTEGER) = 2 THEN 100.0 ELSE 0 END), 2) as rank2_accuracy
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
    WHERE rp.rank_prediction = 2
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
        AND e.racer_rank IS NOT NULL
        AND e.racer_rank != ''
    GROUP BY e.racer_rank
    ORDER BY rank2_accuracy DESC
    """
    df_class = pd.read_sql_query(query_class, conn)

    # 会場別（上位10・下位10）
    query_venue = """
    SELECT
        ra.venue_code,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN CAST(r.rank AS INTEGER) = 2 THEN 1 ELSE 0 END) as rank2_correct,
        ROUND(AVG(CASE WHEN CAST(r.rank AS INTEGER) = 2 THEN 100.0 ELSE 0 END), 2) as rank2_accuracy
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    JOIN races ra ON rp.race_id = ra.id
    WHERE rp.rank_prediction = 2
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
    GROUP BY ra.venue_code
    ORDER BY rank2_accuracy DESC
    """
    df_venue = pd.read_sql_query(query_venue, conn)

    conn.close()

    return {
        'course': df_course,
        'class': df_class,
        'venue': df_venue
    }

def analyze_rank3_miss_by_conditions():
    """予測3位が外れた時の条件別分析"""
    conn = get_db_connection()

    # コース別で外れた時の実際の着順
    query = """
    SELECT
        rp.pit_number as course,
        CAST(r.rank AS INTEGER) as result_rank,
        COUNT(*) as count
    FROM race_predictions rp
    JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
    WHERE rp.rank_prediction = 3
        AND r.rank IS NOT NULL
        AND r.rank != ''
        AND CAST(r.rank AS INTEGER) > 0
        AND CAST(r.rank AS INTEGER) != 3
    GROUP BY rp.pit_number, CAST(r.rank AS INTEGER)
    ORDER BY rp.pit_number, result_rank
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def main():
    """メイン処理"""
    print("=" * 80)
    print("予測精度の詳細分析")
    print("=" * 80)
    print()

    results = {}

    # 1. 基本的な予測精度
    print("1. 基本的な予測精度分析...")
    results['basic_accuracy'] = analyze_basic_prediction_accuracy()
    print(results['basic_accuracy'])
    print()

    # 2. 信頼度別の予測精度
    print("2. 信頼度別の予測精度...")
    results['confidence_accuracy'] = analyze_confidence_level_accuracy()
    print(results['confidence_accuracy'])
    print()

    # 3. 予測3位の詳細分析
    print("3. 予測3位のコース別分析...")
    results['rank3_course'] = analyze_rank3_by_course()
    print(results['rank3_course'])
    print()

    print("4. 予測3位の会場別分析...")
    results['rank3_venue'] = analyze_rank3_by_venue()
    print(f"会場数: {len(results['rank3_venue'])}")
    print("上位5会場:")
    print(results['rank3_venue'].head())
    print("下位5会場:")
    print(results['rank3_venue'].tail())
    print()

    print("5. 予測3位の級別分析...")
    results['rank3_class'] = analyze_rank3_by_class()
    print(results['rank3_class'])
    print()

    print("6. 予測3位の展示タイム別分析...")
    results['rank3_exhibition'] = analyze_rank3_by_exhibition_time()
    print(results['rank3_exhibition'])
    print()

    print("7. 予測3位のモーター性能別分析...")
    results['rank3_motor'] = analyze_rank3_by_motor_performance()
    print(results['rank3_motor'])
    print()

    print("8. 予測3位のオッズ別分析...")
    results['rank3_odds'] = analyze_rank3_by_odds()
    print(results['rank3_odds'])
    print()

    # 4. 予測3位が外れた時の分析
    print("9. 予測3位が外れた時の着順分布...")
    results['rank3_miss_dist'] = analyze_rank3_miss_distribution()
    print(results['rank3_miss_dist'])
    print()

    print("10. 実際に3着に来た選手の予測順位...")
    results['who_came_3rd'] = analyze_who_came_3rd()
    print(results['who_came_3rd'])
    print()

    print("11. 予測3位が外れた時の条件別分析...")
    results['rank3_miss_conditions'] = analyze_rank3_miss_by_conditions()
    print(f"データ件数: {len(results['rank3_miss_conditions'])}")
    print()

    # 5. 予測1位・2位の分析
    print("12. 予測1位の詳細分析...")
    results['rank1_details'] = analyze_rank1_details()
    print("コース別:")
    print(results['rank1_details']['course'])
    print()

    print("13. 予測2位の詳細分析...")
    results['rank2_details'] = analyze_rank2_details()
    print("コース別:")
    print(results['rank2_details']['course'])
    print()

    # データをCSVとして保存
    output_dir = Path(r"c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\analysis")
    output_dir.mkdir(exist_ok=True, parents=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 各データフレームを保存
    results['basic_accuracy'].to_csv(output_dir / f"basic_accuracy_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['confidence_accuracy'].to_csv(output_dir / f"confidence_accuracy_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank3_course'].to_csv(output_dir / f"rank3_course_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank3_venue'].to_csv(output_dir / f"rank3_venue_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank3_class'].to_csv(output_dir / f"rank3_class_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank3_exhibition'].to_csv(output_dir / f"rank3_exhibition_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank3_motor'].to_csv(output_dir / f"rank3_motor_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank3_odds'].to_csv(output_dir / f"rank3_odds_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank3_miss_dist'].to_csv(output_dir / f"rank3_miss_dist_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['who_came_3rd'].to_csv(output_dir / f"who_came_3rd_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank3_miss_conditions'].to_csv(output_dir / f"rank3_miss_conditions_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank1_details']['course'].to_csv(output_dir / f"rank1_course_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank1_details']['class'].to_csv(output_dir / f"rank1_class_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank1_details']['venue'].to_csv(output_dir / f"rank1_venue_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank2_details']['course'].to_csv(output_dir / f"rank2_course_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank2_details']['class'].to_csv(output_dir / f"rank2_class_{timestamp}.csv", index=False, encoding='utf-8-sig')
    results['rank2_details']['venue'].to_csv(output_dir / f"rank2_venue_{timestamp}.csv", index=False, encoding='utf-8-sig')

    print(f"分析結果を {output_dir} に保存しました")
    print()

    return results

if __name__ == "__main__":
    main()
