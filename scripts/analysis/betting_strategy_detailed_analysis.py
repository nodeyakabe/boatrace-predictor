"""
買い目戦略の詳細分析: 信頼度別・オッズ帯別の最適化

前回の分析で異常に高いROIが出たため、より詳細に検証する
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'

def analyze_by_confidence_and_odds():
    """信頼度別・オッズ帯別の詳細分析"""
    conn = sqlite3.connect(DB_PATH)

    query = """
    WITH race_predictions_wide AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) as pred_1st,
            MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) as pred_2nd,
            MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) as pred_3rd,
            MAX(CASE WHEN rank_prediction = 4 THEN pit_number END) as pred_4th,
            MAX(CASE WHEN rank_prediction = 5 THEN pit_number END) as pred_5th,
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
    ),
    race_odds AS (
        SELECT
            race_id,
            combination,
            odds
        FROM trifecta_odds
    )
    SELECT
        rp.confidence_1st as confidence,
        CASE
            WHEN ro.odds < 5 THEN '1-5倍未満'
            WHEN ro.odds < 10 THEN '5-10倍'
            WHEN ro.odds < 20 THEN '10-20倍'
            WHEN ro.odds < 50 THEN '20-50倍'
            ELSE '50倍以上' END as odds_range,
        COUNT(*) as race_count,
        -- 1点買い (1-2-3)
        SUM(CASE WHEN rp.pred_1st = rr.actual_1st AND rp.pred_2nd = rr.actual_2nd AND rp.pred_3rd = rr.actual_3rd THEN 1 ELSE 0 END) as hit_1point,
        -- 3点買い (1-2-3, 1-2-4, 1-2-5)
        SUM(CASE WHEN rp.pred_1st = rr.actual_1st AND rp.pred_2nd = rr.actual_2nd AND
            (rp.pred_3rd = rr.actual_3rd OR rp.pred_4th = rr.actual_3rd OR rp.pred_5th = rr.actual_3rd) THEN 1 ELSE 0 END) as hit_3point,
        AVG(ro.odds) as avg_odds
    FROM race_predictions_wide rp
    JOIN race_results_wide rr ON rp.race_id = rr.race_id
    LEFT JOIN race_odds ro ON rp.race_id = ro.race_id
        AND CAST(rr.actual_1st AS TEXT) || '-' ||
            CAST(rr.actual_2nd AS TEXT) || '-' ||
            CAST(rr.actual_3rd AS TEXT) = ro.combination
    WHERE rp.confidence_1st IS NOT NULL
      AND ro.odds IS NOT NULL
    GROUP BY rp.confidence_1st,
             CASE
                WHEN ro.odds < 5 THEN '1-5倍未満'
                WHEN ro.odds < 10 THEN '5-10倍'
                WHEN ro.odds < 20 THEN '10-20倍'
                WHEN ro.odds < 50 THEN '20-50倍'
                ELSE '50倍以上' END
    ORDER BY rp.confidence_1st,
             CASE
                WHEN ro.odds < 5 THEN 1
                WHEN ro.odds < 10 THEN 2
                WHEN ro.odds < 20 THEN 3
                WHEN ro.odds < 50 THEN 4
                ELSE 5 END
    """

    df = pd.read_sql(query, conn)
    conn.close()

    # 的中率とROIを計算
    df['hit_rate_1point'] = (df['hit_1point'] / df['race_count'] * 100).round(2)
    df['hit_rate_3point'] = (df['hit_3point'] / df['race_count'] * 100).round(2)

    # 1点買いのROI (400円賭け)
    df['roi_1point'] = ((df['hit_1point'] * df['avg_odds'] * 400) / (df['race_count'] * 400) * 100).round(2)

    # 3点買いのROI (合計400円賭け: 200円 + 100円 + 100円)
    # 的中時は本命厚めの配分を考慮
    df['roi_3point_pattern_h'] = ((df['hit_1point'] * df['avg_odds'] * 200 +
                                    (df['hit_3point'] - df['hit_1point']) * df['avg_odds'] * 100) /
                                   (df['race_count'] * 400) * 100).round(2)

    return df

def analyze_winning_combinations():
    """実際の的中パターンの詳細分析"""
    conn = sqlite3.connect(DB_PATH)

    query = """
    WITH race_predictions_wide AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) as pred_1st,
            MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) as pred_2nd,
            MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) as pred_3rd,
            MAX(CASE WHEN rank_prediction = 4 THEN pit_number END) as pred_4th,
            MAX(CASE WHEN rank_prediction = 5 THEN pit_number END) as pred_5th,
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
        rp.confidence_1st as confidence,
        CASE
            WHEN rp.pred_1st = rr.actual_1st AND rp.pred_2nd = rr.actual_2nd AND rp.pred_3rd = rr.actual_3rd THEN '1-2-3的中'
            WHEN rp.pred_1st = rr.actual_1st AND rp.pred_2nd = rr.actual_2nd AND rp.pred_4th = rr.actual_3rd THEN '1-2-4的中'
            WHEN rp.pred_1st = rr.actual_1st AND rp.pred_2nd = rr.actual_2nd AND rp.pred_5th = rr.actual_3rd THEN '1-2-5的中'
            WHEN rp.pred_1st = rr.actual_1st AND rp.pred_2nd = rr.actual_2nd THEN '1-2的中(3着外し)'
            WHEN rp.pred_1st = rr.actual_1st THEN '1着のみ的中'
            ELSE '全外し' END as hit_pattern,
        COUNT(*) as race_count
    FROM race_predictions_wide rp
    JOIN race_results_wide rr ON rp.race_id = rr.race_id
    WHERE rp.confidence_1st IS NOT NULL
    GROUP BY rp.confidence_1st, hit_pattern
    ORDER BY rp.confidence_1st, hit_pattern
    """

    df = pd.read_sql(query, conn)
    conn.close()

    return df

def check_data_integrity():
    """データ整合性チェック"""
    conn = sqlite3.connect(DB_PATH)

    queries = {
        'before予測があるレース数': """
            SELECT COUNT(DISTINCT race_id) as count
            FROM race_predictions
            WHERE prediction_type = 'before'
        """,
        '結果があるレース数': """
            SELECT COUNT(DISTINCT race_id) as count
            FROM results
            WHERE is_invalid = 0
        """,
        'オッズがあるレース数': """
            SELECT COUNT(DISTINCT race_id) as count
            FROM trifecta_odds
        """,
        '予測と結果の両方があるレース数': """
            SELECT COUNT(DISTINCT rp.race_id) as count
            FROM race_predictions rp
            JOIN results r ON rp.race_id = r.race_id
            WHERE rp.prediction_type = 'before'
              AND r.is_invalid = 0
        """,
        '予測と結果とオッズすべてあるレース数': """
            SELECT COUNT(DISTINCT rp.race_id) as count
            FROM race_predictions rp
            JOIN results r ON rp.race_id = r.race_id
            JOIN trifecta_odds t ON rp.race_id = t.race_id
            WHERE rp.prediction_type = 'before'
              AND r.is_invalid = 0
        """
    }

    results = {}
    for name, query in queries.items():
        df = pd.read_sql(query, conn)
        results[name] = df.iloc[0]['count']

    conn.close()
    return results

def main():
    print("=" * 80)
    print("買い目戦略の詳細分析")
    print("=" * 80)

    # データ整合性チェック
    print("\n【データ整合性チェック】")
    integrity = check_data_integrity()
    for name, count in integrity.items():
        print(f"{name}: {count:,}レース")

    # 信頼度別・オッズ帯別の分析
    print("\n" + "=" * 80)
    print("【信頼度別・オッズ帯別の分析】")
    print("=" * 80)
    df_odds = analyze_by_confidence_and_odds()
    print(df_odds.to_string(index=False))

    # 信頼度ごとにサマリーを表示
    print("\n" + "=" * 80)
    print("【信頼度別サマリー】")
    print("=" * 80)
    for conf in ['A', 'B', 'C', 'D', 'E']:
        conf_data = df_odds[df_odds['confidence'] == conf]
        if not conf_data.empty:
            total_races = conf_data['race_count'].sum()
            total_hit_1point = conf_data['hit_1point'].sum()
            total_hit_3point = conf_data['hit_3point'].sum()
            hit_rate_1point = total_hit_1point / total_races * 100
            hit_rate_3point = total_hit_3point / total_races * 100

            print(f"\n信頼度{conf}: 総レース数={total_races:,}")
            print(f"  1点買い: 的中{total_hit_1point:,}レース ({hit_rate_1point:.2f}%)")
            print(f"  3点買い: 的中{total_hit_3point:,}レース ({hit_rate_3point:.2f}%)")
            print(f"  3点買いで増える的中: {total_hit_3point - total_hit_1point:,}レース")

    # 的中パターンの分析
    print("\n" + "=" * 80)
    print("【的中パターンの分布】")
    print("=" * 80)
    df_patterns = analyze_winning_combinations()
    print(df_patterns.to_string(index=False))

    # 信頼度別の的中パターン割合
    print("\n" + "=" * 80)
    print("【信頼度別の的中パターン割合】")
    print("=" * 80)
    for conf in ['A', 'B', 'C', 'D', 'E']:
        conf_data = df_patterns[df_patterns['confidence'] == conf]
        if not conf_data.empty:
            total = conf_data['race_count'].sum()
            print(f"\n信頼度{conf} (総レース数: {total:,})")
            for _, row in conf_data.iterrows():
                pct = row['race_count'] / total * 100
                print(f"  {row['hit_pattern']}: {row['race_count']:,}レース ({pct:.2f}%)")

if __name__ == "__main__":
    main()
