#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
A-2: B/C条件×モーター効果検証

目的:
    既存B/C条件にモーター条件を追加した場合の効果を検証
    期待効果: +3,000～8,000円

検証対象:
    - B条件（現状ROI 155%程度）にモーター条件追加
    - C条件（現状ROI 200%程度）にモーター条件追加
"""
import sqlite3
import sys
import io
import os

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def analyze_b_condition_with_motor(cursor):
    """B条件にモーター条件を追加した場合の効果"""
    print("=" * 70)
    print(" B条件 × モーター効果検証")
    print("=" * 70)

    # 現状のB条件（オッズ10-30倍）
    results = []

    # モーターなし
    query_no_motor = '''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = 'B'
        AND e1.racer_rank IN ('A1', 'A2')
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_bets AS (
        SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
    ),
    race_with_odds AS (
        SELECT rb.*, COALESCE(t.odds, 0) as odds
        FROM race_bets rb
        LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
    ),
    race_with_payout AS (
        SELECT ro.*, COALESCE(p.amount, 0) as payout
        FROM race_with_odds ro
        LEFT JOIN payouts p ON ro.race_id = p.race_id AND p.bet_type = 'trifecta' AND p.combination = ro.combination
    )
    SELECT COUNT(*), SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), SUM(payout)
    FROM race_with_payout
    WHERE odds >= 10 AND odds < 30
    '''

    cursor.execute(query_no_motor)
    result = cursor.fetchone()
    total, hits, payout = result if result else (0, 0, 0)
    total = total or 0
    hits = hits or 0
    payout = payout or 0
    cost = total * 100
    roi_no_motor = (payout / cost) * 100 if cost > 0 else 0
    profit_no_motor = payout - cost
    results.append({'name': 'B条件（モーターなし）', 'total': total, 'hits': hits, 'roi': roi_no_motor, 'profit': profit_no_motor})

    # モーター30%+
    for motor_threshold in [30, 35, 40, 45]:
        query_with_motor = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            WHERE rp.rank_prediction = 1
            AND rp.confidence = 'B'
            AND e1.racer_rank IN ('A1', 'A2')
            AND e1.motor_second_rate >= {motor_threshold}.0
            AND r.race_date >= '2020-01-01'
            AND r.race_date <= '2025-12-31'
        ),
        race_bets AS (
            SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
        ),
        race_with_odds AS (
            SELECT rb.*, COALESCE(t.odds, 0) as odds
            FROM race_bets rb
            LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
        ),
        race_with_payout AS (
            SELECT ro.*, COALESCE(p.amount, 0) as payout
            FROM race_with_odds ro
            LEFT JOIN payouts p ON ro.race_id = p.race_id AND p.bet_type = 'trifecta' AND p.combination = ro.combination
        )
        SELECT COUNT(*), SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), SUM(payout)
        FROM race_with_payout
        WHERE odds >= 10 AND odds < 30
        '''

        cursor.execute(query_with_motor)
        result = cursor.fetchone()
        total, hits, payout = result if result else (0, 0, 0)
        total = total or 0
        hits = hits or 0
        payout = payout or 0
        cost = total * 100
        roi = (payout / cost) * 100 if cost > 0 else 0
        profit = payout - cost
        results.append({'name': f'B条件 + Motor{motor_threshold}%+', 'total': total, 'hits': hits, 'roi': roi, 'profit': profit})

    print(f"\n{'条件':<25} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>10} {'効果':>10}")
    print("-" * 75)

    base_profit = results[0]['profit']
    for r in results:
        effect = r['profit'] - base_profit if r['name'] != 'B条件（モーターなし）' else 0
        status = "★" if r['roi'] >= 150 else ("◎" if r['roi'] >= 100 else " ")
        print(f"{r['name']:<25} {r['total']:>6} {r['hits']:>4} {r['roi']:>7.1f}% {r['profit']:>+10,.0f} {effect:>+10,.0f} {status}")

    return results


def analyze_c_condition_with_motor(cursor):
    """C条件にモーター条件を追加した場合の効果"""
    print("\n" + "=" * 70)
    print(" C条件 × モーター効果検証")
    print("=" * 70)

    results = []

    # モーターなし（鳴門×A2×30-80倍は既に採用済みなので、それ以外を検証）
    query_no_motor = '''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = 'C'
        AND e1.racer_rank IN ('A1', 'A2')
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_bets AS (
        SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
    ),
    race_with_odds AS (
        SELECT rb.*, COALESCE(t.odds, 0) as odds
        FROM race_bets rb
        LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
    ),
    race_with_payout AS (
        SELECT ro.*, COALESCE(p.amount, 0) as payout
        FROM race_with_odds ro
        LEFT JOIN payouts p ON ro.race_id = p.race_id AND p.bet_type = 'trifecta' AND p.combination = ro.combination
    )
    SELECT COUNT(*), SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), SUM(payout)
    FROM race_with_payout
    WHERE odds >= 10 AND odds < 100
    '''

    cursor.execute(query_no_motor)
    result = cursor.fetchone()
    total, hits, payout = result if result else (0, 0, 0)
    total = total or 0
    hits = hits or 0
    payout = payout or 0
    cost = total * 100
    roi_no_motor = (payout / cost) * 100 if cost > 0 else 0
    profit_no_motor = payout - cost
    results.append({'name': 'C条件（モーターなし）', 'total': total, 'hits': hits, 'roi': roi_no_motor, 'profit': profit_no_motor})

    # モーター条件追加
    for motor_threshold in [30, 35, 40, 45]:
        query_with_motor = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            WHERE rp.rank_prediction = 1
            AND rp.confidence = 'C'
            AND e1.racer_rank IN ('A1', 'A2')
            AND e1.motor_second_rate >= {motor_threshold}.0
            AND r.race_date >= '2020-01-01'
            AND r.race_date <= '2025-12-31'
        ),
        race_bets AS (
            SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
        ),
        race_with_odds AS (
            SELECT rb.*, COALESCE(t.odds, 0) as odds
            FROM race_bets rb
            LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
        ),
        race_with_payout AS (
            SELECT ro.*, COALESCE(p.amount, 0) as payout
            FROM race_with_odds ro
            LEFT JOIN payouts p ON ro.race_id = p.race_id AND p.bet_type = 'trifecta' AND p.combination = ro.combination
        )
        SELECT COUNT(*), SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), SUM(payout)
        FROM race_with_payout
        WHERE odds >= 10 AND odds < 100
        '''

        cursor.execute(query_with_motor)
        result = cursor.fetchone()
        total, hits, payout = result if result else (0, 0, 0)
        total = total or 0
        hits = hits or 0
        payout = payout or 0
        cost = total * 100
        roi = (payout / cost) * 100 if cost > 0 else 0
        profit = payout - cost
        results.append({'name': f'C条件 + Motor{motor_threshold}%+', 'total': total, 'hits': hits, 'roi': roi, 'profit': profit})

    print(f"\n{'条件':<25} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>10} {'効果':>10}")
    print("-" * 75)

    base_profit = results[0]['profit']
    for r in results:
        effect = r['profit'] - base_profit if r['name'] != 'C条件（モーターなし）' else 0
        status = "★" if r['roi'] >= 150 else ("◎" if r['roi'] >= 100 else " ")
        print(f"{r['name']:<25} {r['total']:>6} {r['hits']:>4} {r['roi']:>7.1f}% {r['profit']:>+10,.0f} {effect:>+10,.0f} {status}")

    return results


def analyze_existing_conditions_with_motor(cursor):
    """既存の採用条件にモーター条件を追加した場合の効果"""
    print("\n" + "=" * 70)
    print(" 既存採用条件 × モーター効果検証（2025年データ）")
    print("=" * 70)

    # 既存のB条件（鳴門、児島、津のB条件）
    existing_conditions = [
        {'name': '児島×B×A1', 'confidence': 'B', 'c1_rank': 'A1', 'venue': 16, 'odds_min': 10, 'odds_max': 30},
        {'name': '児島×B×A2', 'confidence': 'B', 'c1_rank': 'A2', 'venue': 16, 'odds_min': 10, 'odds_max': 30},
        {'name': '津×B×A1', 'confidence': 'B', 'c1_rank': 'A1', 'venue': 9, 'odds_min': 10, 'odds_max': 30},
    ]

    for cond in existing_conditions:
        print(f"\n--- {cond['name']} ---")

        results = []

        # モーターなし
        query_no_motor = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            WHERE rp.rank_prediction = 1
            AND rp.confidence = '{cond["confidence"]}'
            AND e1.racer_rank = '{cond["c1_rank"]}'
            AND r.venue_code = '{cond["venue"]:02d}'
            AND r.race_date >= '2025-01-01'
            AND r.race_date <= '2025-12-31'
        ),
        race_bets AS (
            SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
        ),
        race_with_odds AS (
            SELECT rb.*, COALESCE(t.odds, 0) as odds
            FROM race_bets rb
            LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
        ),
        race_with_payout AS (
            SELECT ro.*, COALESCE(p.amount, 0) as payout
            FROM race_with_odds ro
            LEFT JOIN payouts p ON ro.race_id = p.race_id AND p.bet_type = 'trifecta' AND p.combination = ro.combination
        )
        SELECT COUNT(*), SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), SUM(payout)
        FROM race_with_payout
        WHERE odds >= {cond["odds_min"]} AND odds < {cond["odds_max"]}
        '''

        cursor.execute(query_no_motor)
        result = cursor.fetchone()
        total, hits, payout = result if result else (0, 0, 0)
        total = total or 0
        hits = hits or 0
        payout = payout or 0
        cost = total * 100
        roi = (payout / cost) * 100 if cost > 0 else 0
        profit = payout - cost
        results.append({'name': 'モーターなし', 'total': total, 'hits': hits, 'roi': roi, 'profit': profit})

        # モーター35%+, 40%+
        for motor_threshold in [35, 40]:
            query_with_motor = f'''
            WITH race_base AS (
                SELECT
                    r.id as race_id,
                    rp1.pit_number as p1,
                    rp2.pit_number as p2,
                    rp3.pit_number as p3
                FROM races r
                JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
                JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
                JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
                JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
                JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
                WHERE rp.rank_prediction = 1
                AND rp.confidence = '{cond["confidence"]}'
                AND e1.racer_rank = '{cond["c1_rank"]}'
                AND e1.motor_second_rate >= {motor_threshold}.0
                AND r.venue_code = '{cond["venue"]:02d}'
                AND r.race_date >= '2025-01-01'
                AND r.race_date <= '2025-12-31'
            ),
            race_bets AS (
                SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
            ),
            race_with_odds AS (
                SELECT rb.*, COALESCE(t.odds, 0) as odds
                FROM race_bets rb
                LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
            ),
            race_with_payout AS (
                SELECT ro.*, COALESCE(p.amount, 0) as payout
                FROM race_with_odds ro
                LEFT JOIN payouts p ON ro.race_id = p.race_id AND p.bet_type = 'trifecta' AND p.combination = ro.combination
            )
            SELECT COUNT(*), SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), SUM(payout)
            FROM race_with_payout
            WHERE odds >= {cond["odds_min"]} AND odds < {cond["odds_max"]}
            '''

            cursor.execute(query_with_motor)
            result = cursor.fetchone()
            total, hits, payout = result if result else (0, 0, 0)
            total = total or 0
            hits = hits or 0
            payout = payout or 0
            cost = total * 100
            roi = (payout / cost) * 100 if cost > 0 else 0
            profit = payout - cost
            results.append({'name': f'Motor{motor_threshold}%+', 'total': total, 'hits': hits, 'roi': roi, 'profit': profit})

        print(f"{'条件':<15} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>10}")
        print("-" * 50)
        for r in results:
            status = "★" if r['roi'] >= 150 else ("◎" if r['roi'] >= 100 else " ")
            print(f"{r['name']:<15} {r['total']:>6} {r['hits']:>4} {r['roi']:>7.1f}% {r['profit']:>+10,.0f} {status}")


def main():
    print("=" * 70)
    print(" A-2: B/C条件 × モーター効果検証")
    print("=" * 70)
    print()
    print("目的: 既存B/C条件にモーター条件（2連率40%+等）を追加した効果を検証")
    print("期待効果: +3,000～8,000円")
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 各分析を実行
    b_results = analyze_b_condition_with_motor(cursor)
    c_results = analyze_c_condition_with_motor(cursor)
    analyze_existing_conditions_with_motor(cursor)

    # 結論
    print("\n" + "=" * 70)
    print(" 調査結論")
    print("=" * 70)
    print()
    print("上記データを確認して、B/C条件へのモーター条件追加の効果を判断してください。")
    print()
    print("判断基準:")
    print("  - ROI改善: +5pt以上なら有意な効果")
    print("  - 収支改善: +3,000円以上なら採用検討")
    print("  - サンプル数: 50件以上で統計的に有意")

    conn.close()


if __name__ == "__main__":
    main()
