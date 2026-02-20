"""
D×35-60条件の検証分析スクリプト
上位AIの指摘（ROI 71.8%）と実データの差異を調査
"""
import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def verify_d_condition():
    """D×35-60条件の複数の計算方式で検証"""
    conn = get_connection()

    print("=" * 80)
    print("D×35-60条件 検証分析")
    print("=" * 80)

    # 方式1: 予測1位が1着になった場合のみカウント（旧方式）
    # 的中 = 予測1位艇が実際に1着だった場合
    print("\n" + "=" * 80)
    print("方式1: 予測1位 = 実結果1着 の単純一致（3連単無関係）")
    print("=" * 80)

    query1 = """
    SELECT
        strftime('%Y', r.race_date) as year,
        COUNT(*) as total_count,
        SUM(CASE WHEN rp.pit_number = res1.pit_number THEN 1 ELSE 0 END) as hit_count,
        AVG(t.odds) as avg_odds
    FROM races r
    INNER JOIN race_predictions rp ON r.id = rp.race_id
    INNER JOIN entries e ON r.id = e.race_id AND rp.pit_number = e.pit_number
    INNER JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1' AND res1.is_invalid = 0
    LEFT JOIN (
        SELECT race_id, combination, odds FROM trifecta_odds
    ) t ON r.id = t.race_id
        AND t.combination = (
            SELECT res1.pit_number || '-' || res2.pit_number || '-' || res3.pit_number
            FROM results res1, results res2, results res3
            WHERE res1.race_id = r.id AND res1.rank = '1' AND res1.is_invalid = 0
            AND res2.race_id = r.id AND res2.rank = '2' AND res2.is_invalid = 0
            AND res3.race_id = r.id AND res3.rank = '3' AND res3.is_invalid = 0
        )
    WHERE rp.rank_prediction = 1
    AND rp.confidence = 'D'
    AND e.racer_rank IN ('A1', 'A2', 'B1')
    AND r.race_date >= '2020-01-01'
    AND r.race_date <= '2025-12-31'
    AND r.race_number != 9
    AND r.venue_code != '10'
    AND t.odds >= 35 AND t.odds < 60
    GROUP BY strftime('%Y', r.race_date)
    ORDER BY year
    """

    # 方式2: 3連単買い目（予測1-2-3）が的中した場合
    print("\n" + "=" * 80)
    print("方式2: 3連単買い目（予測1-2-3）の的中判定")
    print("=" * 80)

    query2 = """
    WITH pred_combos AS (
        -- 各レースの予測1-2-3の組み合わせを取得
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 1 AND prediction_type = 'advance') as pred_1,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 2 AND prediction_type = 'advance') as pred_2,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 3 AND prediction_type = 'advance') as pred_3,
            (SELECT confidence FROM race_predictions WHERE race_id = r.id AND rank_prediction = 1 AND prediction_type = 'advance') as confidence
        FROM races r
        WHERE r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    actual_results AS (
        -- 各レースの実結果（1-2-3着）
        SELECT
            race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1,
            MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2,
            MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3
        FROM results
        WHERE is_invalid = 0 AND rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    with_odds AS (
        SELECT
            pc.*,
            ar.actual_1, ar.actual_2, ar.actual_3,
            e.racer_rank as c1_rank,
            t.odds as trifecta_odds
        FROM pred_combos pc
        INNER JOIN actual_results ar ON pc.race_id = ar.race_id
        INNER JOIN entries e ON pc.race_id = e.race_id AND e.pit_number = 1
        LEFT JOIN trifecta_odds t ON pc.race_id = t.race_id
            AND t.combination = ar.actual_1 || '-' || ar.actual_2 || '-' || ar.actual_3
        WHERE pc.confidence = 'D'
        AND pc.pred_1 IS NOT NULL
        AND pc.pred_2 IS NOT NULL
        AND pc.pred_3 IS NOT NULL
        AND pc.race_number != 9
        AND pc.venue_code != '10'
        AND e.racer_rank IN ('A1', 'A2', 'B1')
    )
    SELECT
        strftime('%Y', race_date) as year,
        COUNT(*) as total_count,
        SUM(CASE WHEN pred_1 = actual_1 AND pred_2 = actual_2 AND pred_3 = actual_3 THEN 1 ELSE 0 END) as hit_count,
        AVG(trifecta_odds) as avg_odds
    FROM with_odds
    WHERE trifecta_odds >= 35 AND trifecta_odds < 60
    GROUP BY strftime('%Y', race_date)
    ORDER BY year
    """

    df2 = pd.read_sql_query(query2, conn)
    print(f"\n{'年度':<8} {'件数':>8} {'的中':>6} {'的中率':>10} {'平均オッズ':>10}")
    print("-" * 50)

    total_count = 0
    total_hit = 0
    for _, row in df2.iterrows():
        hit_rate = row['hit_count'] / row['total_count'] * 100 if row['total_count'] > 0 else 0
        total_count += row['total_count']
        total_hit += row['hit_count']
        print(f"{row['year']:<8} {row['total_count']:>8} {row['hit_count']:>6} {hit_rate:>9.2f}% {row['avg_odds']:>9.1f}倍")

    total_hit_rate = total_hit / total_count * 100 if total_count > 0 else 0
    print(f"\n6年間合計: {total_count}件, 的中{total_hit}件, 的中率 {total_hit_rate:.2f}%")

    # 方式3: 予測買い目のオッズを使った的中判定（本来の計算方法）
    print("\n" + "=" * 80)
    print("方式3: 予測買い目（予測1-2-3組み合わせ）のオッズで判定")
    print("       ※ 購入オッズと払戻オッズの一致が必要")
    print("=" * 80)

    query3 = """
    WITH pred_combos AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 1 AND prediction_type = 'advance') as pred_1,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 2 AND prediction_type = 'advance') as pred_2,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 3 AND prediction_type = 'advance') as pred_3,
            (SELECT confidence FROM race_predictions WHERE race_id = r.id AND rank_prediction = 1 AND prediction_type = 'advance') as confidence
        FROM races r
        WHERE r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    actual_results AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1,
            MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2,
            MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3
        FROM results
        WHERE is_invalid = 0 AND rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    with_odds AS (
        SELECT
            pc.*,
            ar.actual_1, ar.actual_2, ar.actual_3,
            e.racer_rank as c1_rank,
            -- 予測買い目のオッズ（購入時）
            pred_odds.odds as pred_combo_odds,
            -- 実結果のオッズ（払戻時）
            actual_odds.odds as actual_combo_odds
        FROM pred_combos pc
        INNER JOIN actual_results ar ON pc.race_id = ar.race_id
        INNER JOIN entries e ON pc.race_id = e.race_id AND e.pit_number = 1
        -- 予測買い目のオッズ
        LEFT JOIN trifecta_odds pred_odds ON pc.race_id = pred_odds.race_id
            AND pred_odds.combination = pc.pred_1 || '-' || pc.pred_2 || '-' || pc.pred_3
        -- 実結果の払戻オッズ
        LEFT JOIN trifecta_odds actual_odds ON pc.race_id = actual_odds.race_id
            AND actual_odds.combination = ar.actual_1 || '-' || ar.actual_2 || '-' || ar.actual_3
        WHERE pc.confidence = 'D'
        AND pc.pred_1 IS NOT NULL
        AND pc.pred_2 IS NOT NULL
        AND pc.pred_3 IS NOT NULL
        AND pc.race_number != 9
        AND pc.venue_code != '10'
        AND e.racer_rank IN ('A1', 'A2', 'B1')
    )
    SELECT
        strftime('%Y', race_date) as year,
        COUNT(*) as total_count,
        SUM(CASE WHEN pred_1 = actual_1 AND pred_2 = actual_2 AND pred_3 = actual_3 THEN 1 ELSE 0 END) as hit_count,
        -- 的中時の払戻（予測買い目が的中した場合のみ）
        SUM(CASE WHEN pred_1 = actual_1 AND pred_2 = actual_2 AND pred_3 = actual_3 THEN actual_combo_odds ELSE 0 END) as total_payout,
        AVG(pred_combo_odds) as avg_pred_odds
    FROM with_odds
    WHERE pred_combo_odds >= 35 AND pred_combo_odds < 60
    GROUP BY strftime('%Y', race_date)
    ORDER BY year
    """

    df3 = pd.read_sql_query(query3, conn)
    print(f"\n{'年度':<8} {'件数':>8} {'的中':>6} {'払戻合計':>12} {'ROI':>10}")
    print("-" * 55)

    total_count = 0
    total_hit = 0
    total_payout = 0
    for _, row in df3.iterrows():
        roi = row['total_payout'] * 100 / row['total_count'] if row['total_count'] > 0 else 0
        profit = row['total_payout'] * 100 - row['total_count'] * 100
        total_count += row['total_count']
        total_hit += row['hit_count']
        total_payout += row['total_payout']
        status = "◎" if roi >= 100 else "×"
        print(f"{row['year']:<8} {row['total_count']:>8} {row['hit_count']:>6} {row['total_payout']*100:>11,.0f}円 {roi:>9.1f}% {status}")

    total_roi = total_payout * 100 / total_count if total_count > 0 else 0
    total_profit = total_payout * 100 - total_count * 100
    print(f"\n6年間合計: {total_count}件, 的中{total_hit}件, ROI {total_roi:.1f}%, 収支 {total_profit:+,.0f}円")

    # 上位AIが指摘した71.8%の可能性を調査
    print("\n" + "=" * 80)
    print("調査: 71.8%になりそうな条件の探索")
    print("=" * 80)

    # オッズ35-60倍の全データ（除外なし）で計算
    query_no_filter = """
    WITH pred_combos AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 1 AND prediction_type = 'advance') as pred_1,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 2 AND prediction_type = 'advance') as pred_2,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 3 AND prediction_type = 'advance') as pred_3,
            (SELECT confidence FROM race_predictions WHERE race_id = r.id AND rank_prediction = 1 AND prediction_type = 'advance') as confidence
        FROM races r
        WHERE r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    actual_results AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1,
            MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2,
            MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3
        FROM results
        WHERE is_invalid = 0 AND rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    with_odds AS (
        SELECT
            pc.*,
            ar.actual_1, ar.actual_2, ar.actual_3,
            e.racer_rank as c1_rank,
            pred_odds.odds as pred_combo_odds,
            actual_odds.odds as actual_combo_odds
        FROM pred_combos pc
        INNER JOIN actual_results ar ON pc.race_id = ar.race_id
        INNER JOIN entries e ON pc.race_id = e.race_id AND e.pit_number = 1
        LEFT JOIN trifecta_odds pred_odds ON pc.race_id = pred_odds.race_id
            AND pred_odds.combination = pc.pred_1 || '-' || pc.pred_2 || '-' || pc.pred_3
        LEFT JOIN trifecta_odds actual_odds ON pc.race_id = actual_odds.race_id
            AND actual_odds.combination = ar.actual_1 || '-' || ar.actual_2 || '-' || ar.actual_3
        WHERE pc.confidence = 'D'
        AND pc.pred_1 IS NOT NULL
    )
    SELECT
        '全条件（フィルターなし）' as condition_name,
        COUNT(*) as total_count,
        SUM(CASE WHEN pred_1 = actual_1 AND pred_2 = actual_2 AND pred_3 = actual_3 THEN 1 ELSE 0 END) as hit_count,
        SUM(CASE WHEN pred_1 = actual_1 AND pred_2 = actual_2 AND pred_3 = actual_3 THEN actual_combo_odds ELSE 0 END) as total_payout
    FROM with_odds
    WHERE pred_combo_odds >= 35 AND pred_combo_odds < 60

    UNION ALL

    SELECT
        'A1/A2/B1のみ' as condition_name,
        COUNT(*) as total_count,
        SUM(CASE WHEN pred_1 = actual_1 AND pred_2 = actual_2 AND pred_3 = actual_3 THEN 1 ELSE 0 END) as hit_count,
        SUM(CASE WHEN pred_1 = actual_1 AND pred_2 = actual_2 AND pred_3 = actual_3 THEN actual_combo_odds ELSE 0 END) as total_payout
    FROM with_odds
    WHERE pred_combo_odds >= 35 AND pred_combo_odds < 60
    AND c1_rank IN ('A1', 'A2', 'B1')

    UNION ALL

    SELECT
        'A1/A2/B1 + 9R除外 + 三国除外' as condition_name,
        COUNT(*) as total_count,
        SUM(CASE WHEN pred_1 = actual_1 AND pred_2 = actual_2 AND pred_3 = actual_3 THEN 1 ELSE 0 END) as hit_count,
        SUM(CASE WHEN pred_1 = actual_1 AND pred_2 = actual_2 AND pred_3 = actual_3 THEN actual_combo_odds ELSE 0 END) as total_payout
    FROM with_odds
    WHERE pred_combo_odds >= 35 AND pred_combo_odds < 60
    AND c1_rank IN ('A1', 'A2', 'B1')
    AND race_number != 9
    AND venue_code != '10'
    """

    df_check = pd.read_sql_query(query_no_filter, conn)
    print(f"\n{'条件':<35} {'件数':>8} {'的中':>6} {'ROI':>10}")
    print("-" * 65)
    for _, row in df_check.iterrows():
        roi = row['total_payout'] * 100 / row['total_count'] if row['total_count'] > 0 else 0
        print(f"{row['condition_name']:<35} {row['total_count']:>8} {row['hit_count']:>6} {roi:>9.1f}%")

    # B2を含む場合
    query_with_b2 = """
    WITH pred_combos AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 1 AND prediction_type = 'advance') as pred_1,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 2 AND prediction_type = 'advance') as pred_2,
            (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 3 AND prediction_type = 'advance') as pred_3,
            (SELECT confidence FROM race_predictions WHERE race_id = r.id AND rank_prediction = 1 AND prediction_type = 'advance') as confidence
        FROM races r
        WHERE r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    actual_results AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1,
            MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2,
            MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3
        FROM results
        WHERE is_invalid = 0 AND rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    with_odds AS (
        SELECT
            pc.*,
            ar.actual_1, ar.actual_2, ar.actual_3,
            e.racer_rank as c1_rank,
            pred_odds.odds as pred_combo_odds,
            actual_odds.odds as actual_combo_odds
        FROM pred_combos pc
        INNER JOIN actual_results ar ON pc.race_id = ar.race_id
        INNER JOIN entries e ON pc.race_id = e.race_id AND e.pit_number = 1
        LEFT JOIN trifecta_odds pred_odds ON pc.race_id = pred_odds.race_id
            AND pred_odds.combination = pc.pred_1 || '-' || pc.pred_2 || '-' || pc.pred_3
        LEFT JOIN trifecta_odds actual_odds ON pc.race_id = actual_odds.race_id
            AND actual_odds.combination = ar.actual_1 || '-' || ar.actual_2 || '-' || ar.actual_3
        WHERE pc.confidence = 'D'
        AND pc.pred_1 IS NOT NULL
    )
    SELECT
        c1_rank,
        COUNT(*) as total_count,
        SUM(CASE WHEN pred_1 = actual_1 AND pred_2 = actual_2 AND pred_3 = actual_3 THEN 1 ELSE 0 END) as hit_count,
        SUM(CASE WHEN pred_1 = actual_1 AND pred_2 = actual_2 AND pred_3 = actual_3 THEN actual_combo_odds ELSE 0 END) as total_payout
    FROM with_odds
    WHERE pred_combo_odds >= 35 AND pred_combo_odds < 60
    GROUP BY c1_rank
    ORDER BY c1_rank
    """

    df_by_rank = pd.read_sql_query(query_with_b2, conn)
    print(f"\n級別ごとのROI（35-60倍）:")
    print(f"{'級別':<8} {'件数':>8} {'的中':>6} {'ROI':>10}")
    print("-" * 35)
    for _, row in df_by_rank.iterrows():
        roi = row['total_payout'] * 100 / row['total_count'] if row['total_count'] > 0 else 0
        print(f"{row['c1_rank']:<8} {row['total_count']:>8} {row['hit_count']:>6} {roi:>9.1f}%")

    conn.close()

if __name__ == "__main__":
    verify_d_condition()
