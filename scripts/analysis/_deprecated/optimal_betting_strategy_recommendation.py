"""
最適な買い目戦略の推奨案を作成

前回の分析結果を元に、信頼度別・オッズ帯別の最適戦略を提案する
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'

def simulate_betting_strategies():
    """様々な買い目戦略をシミュレーション"""
    conn = sqlite3.connect(DB_PATH)

    # ベースクエリ
    base_query = """
    WITH race_predictions_wide AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) as pred_1st,
            MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) as pred_2nd,
            MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) as pred_3rd,
            MAX(CASE WHEN rank_prediction = 4 THEN pit_number END) as pred_4th,
            MAX(CASE WHEN rank_prediction = 5 THEN pit_number END) as pred_5th,
            MAX(CASE WHEN rank_prediction = 6 THEN pit_number END) as pred_6th,
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
    race_with_odds AS (
        SELECT
            rp.race_id,
            rp.confidence_1st,
            rp.pred_1st,
            rp.pred_2nd,
            rp.pred_3rd,
            rp.pred_4th,
            rp.pred_5th,
            rp.pred_6th,
            rr.actual_1st,
            rr.actual_2nd,
            rr.actual_3rd,
            t123.odds as odds_123,
            t124.odds as odds_124,
            t125.odds as odds_125,
            t126.odds as odds_126,
            t132.odds as odds_132,
            t134.odds as odds_134,
            t142.odds as odds_142,
            t143.odds as odds_143,
            actual_combo.odds as actual_odds
        FROM race_predictions_wide rp
        JOIN race_results_wide rr ON rp.race_id = rr.race_id
        LEFT JOIN trifecta_odds t123 ON rp.race_id = t123.race_id
            AND CAST(rp.pred_1st AS TEXT) || '-' || CAST(rp.pred_2nd AS TEXT) || '-' || CAST(rp.pred_3rd AS TEXT) = t123.combination
        LEFT JOIN trifecta_odds t124 ON rp.race_id = t124.race_id
            AND CAST(rp.pred_1st AS TEXT) || '-' || CAST(rp.pred_2nd AS TEXT) || '-' || CAST(rp.pred_4th AS TEXT) = t124.combination
        LEFT JOIN trifecta_odds t125 ON rp.race_id = t125.race_id
            AND CAST(rp.pred_1st AS TEXT) || '-' || CAST(rp.pred_2nd AS TEXT) || '-' || CAST(rp.pred_5th AS TEXT) = t125.combination
        LEFT JOIN trifecta_odds t126 ON rp.race_id = t126.race_id
            AND CAST(rp.pred_1st AS TEXT) || '-' || CAST(rp.pred_2nd AS TEXT) || '-' || CAST(rp.pred_6th AS TEXT) = t126.combination
        LEFT JOIN trifecta_odds t132 ON rp.race_id = t132.race_id
            AND CAST(rp.pred_1st AS TEXT) || '-' || CAST(rp.pred_3rd AS TEXT) || '-' || CAST(rp.pred_2nd AS TEXT) = t132.combination
        LEFT JOIN trifecta_odds t134 ON rp.race_id = t134.race_id
            AND CAST(rp.pred_1st AS TEXT) || '-' || CAST(rp.pred_3rd AS TEXT) || '-' || CAST(rp.pred_4th AS TEXT) = t134.combination
        LEFT JOIN trifecta_odds t142 ON rp.race_id = t142.race_id
            AND CAST(rp.pred_1st AS TEXT) || '-' || CAST(rp.pred_4th AS TEXT) || '-' || CAST(rp.pred_2nd AS TEXT) = t142.combination
        LEFT JOIN trifecta_odds t143 ON rp.race_id = t143.race_id
            AND CAST(rp.pred_1st AS TEXT) || '-' || CAST(rp.pred_4th AS TEXT) || '-' || CAST(rp.pred_3rd AS TEXT) = t143.combination
        LEFT JOIN trifecta_odds actual_combo ON rp.race_id = actual_combo.race_id
            AND CAST(rr.actual_1st AS TEXT) || '-' || CAST(rr.actual_2nd AS TEXT) || '-' || CAST(rr.actual_3rd AS TEXT) = actual_combo.combination
        WHERE rp.confidence_1st IS NOT NULL
    )
    """

    strategies = {
        '1点買い(1-2-3)': {
            'bets': [(400, 'odds_123', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_3rd = actual_3rd')],
            'total_bet': 400
        },
        'パターンH(200-100-100)': {
            'bets': [
                (200, 'odds_123', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_3rd = actual_3rd'),
                (100, 'odds_124', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_4th = actual_3rd'),
                (100, 'odds_125', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_5th = actual_3rd')
            ],
            'total_bet': 400
        },
        '均等3点(133-133-134)': {
            'bets': [
                (133, 'odds_123', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_3rd = actual_3rd'),
                (133, 'odds_124', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_4th = actual_3rd'),
                (134, 'odds_125', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_5th = actual_3rd')
            ],
            'total_bet': 400
        },
        '4点買い(100x4)': {
            'bets': [
                (100, 'odds_123', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_3rd = actual_3rd'),
                (100, 'odds_124', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_4th = actual_3rd'),
                (100, 'odds_125', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_5th = actual_3rd'),
                (100, 'odds_126', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_6th = actual_3rd')
            ],
            'total_bet': 400
        },
        '6点買い(1軸2-4着を2-4予測)': {
            'bets': [
                (67, 'odds_123', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_3rd = actual_3rd'),
                (67, 'odds_124', 'pred_1st = actual_1st AND pred_2nd = actual_2nd AND pred_4th = actual_3rd'),
                (67, 'odds_132', 'pred_1st = actual_1st AND pred_3rd = actual_2nd AND pred_2nd = actual_3rd'),
                (66, 'odds_134', 'pred_1st = actual_1st AND pred_3rd = actual_2nd AND pred_4th = actual_3rd'),
                (66, 'odds_142', 'pred_1st = actual_1st AND pred_4th = actual_2nd AND pred_2nd = actual_3rd'),
                (67, 'odds_143', 'pred_1st = actual_1st AND pred_4th = actual_2nd AND pred_3rd = actual_3rd')
            ],
            'total_bet': 400
        }
    }

    results = []
    for strategy_name, strategy in strategies.items():
        print(f"\n分析中: {strategy_name}")

        # 払戻金を計算するCASE文を構築
        return_cases = []
        for bet_amount, odds_col, condition in strategy['bets']:
            return_cases.append(f"CASE WHEN {condition} THEN {bet_amount} * {odds_col} ELSE 0 END")

        return_calc = " + ".join(return_cases)

        query = f"""
        {base_query}
        SELECT
            confidence_1st as confidence,
            COUNT(*) as race_count,
            SUM({strategy['total_bet']}) as total_investment,
            SUM({return_calc}) as total_return,
            SUM({return_calc}) - SUM({strategy['total_bet']}) as net_profit,
            ROUND(100.0 * SUM({return_calc}) / SUM({strategy['total_bet']}), 2) as roi
        FROM race_with_odds
        WHERE confidence_1st IS NOT NULL
          AND actual_odds IS NOT NULL
        GROUP BY confidence_1st
        ORDER BY confidence_1st
        """

        df = pd.read_sql(query, conn)
        df['strategy'] = strategy_name
        results.append(df)

    conn.close()
    return pd.concat(results, ignore_index=True)

def calculate_opportunity_loss_detail():
    """機会損失の詳細を計算"""
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
    missed_hits AS (
        SELECT
            rp.confidence_1st,
            CASE
                WHEN rp.pred_1st = rr.actual_1st AND rp.pred_2nd = rr.actual_2nd AND rp.pred_4th = rr.actual_3rd THEN '1-2-4的中（本命外し）'
                WHEN rp.pred_1st = rr.actual_1st AND rp.pred_2nd = rr.actual_2nd AND rp.pred_5th = rr.actual_3rd THEN '1-2-5的中（本命外し）'
            END as missed_type,
            to_.odds
        FROM race_predictions_wide rp
        JOIN race_results_wide rr ON rp.race_id = rr.race_id
        LEFT JOIN trifecta_odds to_ ON rp.race_id = to_.race_id
            AND CAST(rr.actual_1st AS TEXT) || '-' ||
                CAST(rr.actual_2nd AS TEXT) || '-' ||
                CAST(rr.actual_3rd AS TEXT) = to_.combination
        WHERE rp.confidence_1st IS NOT NULL
          AND rp.pred_1st = rr.actual_1st
          AND rp.pred_2nd = rr.actual_2nd
          AND rp.pred_3rd != rr.actual_3rd
          AND (rp.pred_4th = rr.actual_3rd OR rp.pred_5th = rr.actual_3rd)
    )
    SELECT
        confidence_1st as confidence,
        missed_type,
        COUNT(*) as missed_count,
        AVG(odds) as avg_odds,
        MIN(odds) as min_odds,
        MAX(odds) as max_odds,
        -- 1点買いなら逃した払戻金（400円賭け）
        SUM(odds * 400) as total_missed_return_1point,
        -- 3点買いなら回収できた払戻金（100円賭け）
        SUM(odds * 100) as total_recovered_return_3point
    FROM missed_hits
    WHERE missed_type IS NOT NULL
    GROUP BY confidence_1st, missed_type
    ORDER BY confidence_1st, missed_type
    """

    df = pd.read_sql(query, conn)
    conn.close()
    return df

def main():
    print("=" * 80)
    print("最適な買い目戦略の推奨案")
    print("=" * 80)

    # 各戦略のシミュレーション
    print("\n【各戦略の信頼度別パフォーマンス】")
    results = simulate_betting_strategies()

    for conf in ['A', 'B', 'C', 'D', 'E']:
        conf_data = results[results['confidence'] == conf]
        if not conf_data.empty:
            print(f"\n信頼度{conf}:")
            display_cols = ['strategy', 'race_count', 'total_investment', 'total_return', 'net_profit', 'roi']
            print(conf_data[display_cols].to_string(index=False))

    # 全信頼度合計
    print("\n" + "=" * 80)
    print("【全信頼度合計】")
    print("=" * 80)
    total_by_strategy = results.groupby('strategy').agg({
        'race_count': 'sum',
        'total_investment': 'sum',
        'total_return': 'sum',
        'net_profit': 'sum'
    }).reset_index()
    total_by_strategy['roi'] = (total_by_strategy['total_return'] / total_by_strategy['total_investment'] * 100).round(2)
    total_by_strategy['hit_rate'] = 'N/A'  # 信頼度ごとに異なるため集計不可
    print(total_by_strategy.to_string(index=False))

    # ROI順にソート
    print("\n【ROI順ランキング】")
    ranked = total_by_strategy.sort_values('roi', ascending=False)
    for idx, row in ranked.iterrows():
        print(f"{row['strategy']:30s} ROI: {row['roi']:7.2f}% 収支: {row['net_profit']:+13,.0f}円")

    # 機会損失の詳細
    print("\n" + "=" * 80)
    print("【機会損失の詳細（1点買いで逃した的中）】")
    print("=" * 80)
    missed = calculate_opportunity_loss_detail()
    print(missed.to_string(index=False))

    # 信頼度別の機会損失サマリー
    print("\n【信頼度別の機会損失サマリー】")
    for conf in ['A', 'B', 'C', 'D', 'E']:
        conf_missed = missed[missed['confidence'] == conf]
        if not conf_missed.empty:
            total_missed = conf_missed['missed_count'].sum()
            total_missed_return_1point = conf_missed['total_missed_return_1point'].sum()
            total_recovered_3point = conf_missed['total_recovered_return_3point'].sum()
            print(f"\n信頼度{conf}:")
            print(f"  1点買いで逃した的中数: {total_missed:,}レース")
            print(f"  逃した払戻金総額（1点買い想定）: {total_missed_return_1point:,.0f}円")
            print(f"  3点買いで回収できた払戻金: {total_recovered_3point:,.0f}円")

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)

if __name__ == "__main__":
    main()
