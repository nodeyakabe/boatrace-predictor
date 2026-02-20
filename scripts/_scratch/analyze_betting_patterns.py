#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
信頼度別 的中率分析スクリプト
1点買い vs 3点買いの比較
"""
import sqlite3
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATABASE_PATH = 'data/boatrace.db'

def analyze_confidence_patterns():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("="*80)
    print("信頼度別 的中率分析（1点買い vs 3点買い）")
    print("="*80)
    print()

    # 信頼度ごとに分析
    confidences = ['A', 'B', 'C', 'D', 'E']

    for conf in confidences:
        print(f"{'='*80}")
        print(f"【信頼度 {conf}】")
        print(f"{'='*80}")

        # 基本的中率の分析
        cursor.execute('''
            WITH predictions AS (
                SELECT
                    rp1.race_id,
                    rp1.confidence,
                    rp1.pit_number as p1,
                    rp2.pit_number as p2,
                    rp3.pit_number as p3,
                    rp4.pit_number as p4,
                    rp5.pit_number as p5
                FROM race_predictions rp1
                LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                    AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
                LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                    AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
                LEFT JOIN race_predictions rp4 ON rp1.race_id = rp4.race_id
                    AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
                LEFT JOIN race_predictions rp5 ON rp1.race_id = rp5.race_id
                    AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
                WHERE rp1.prediction_type = 'before'
                AND rp1.rank_prediction = 1
                AND rp1.confidence = ?
            ),
            results_agg AS (
                SELECT
                    race_id,
                    MAX(CASE WHEN rank = '1' THEN pit_number END) as a1,
                    MAX(CASE WHEN rank = '2' THEN pit_number END) as a2,
                    MAX(CASE WHEN rank = '3' THEN pit_number END) as a3
                FROM results
                WHERE rank IN ('1', '2', '3')
                GROUP BY race_id
            )
            SELECT
                COUNT(*) as total_races,
                -- 1着的中
                SUM(CASE WHEN p.p1 = r.a1 THEN 1 ELSE 0 END) as hit_1st,
                -- 2連単的中
                SUM(CASE WHEN p.p1 = r.a1 AND p.p2 = r.a2 THEN 1 ELSE 0 END) as hit_exacta,
                -- 3連単的中（1点買い）
                SUM(CASE WHEN p.p1 = r.a1 AND p.p2 = r.a2 AND p.p3 = r.a3 THEN 1 ELSE 0 END) as hit_1bet,
                -- 3連単的中（3点買い: 1-2-3 OR 1-2-4 OR 1-2-5）
                SUM(CASE WHEN p.p1 = r.a1 AND p.p2 = r.a2 AND (p.p3 = r.a3 OR p.p4 = r.a3 OR p.p5 = r.a3)
                    THEN 1 ELSE 0 END) as hit_3bet
            FROM predictions p
            LEFT JOIN results_agg r ON p.race_id = r.race_id
        ''', (conf,))

        row = cursor.fetchone()
        total, hit_1st, hit_exacta, hit_1bet, hit_3bet = row

        if total == 0:
            print(f"  データなし\n")
            continue

        # 的中率計算
        rate_1st = 100.0 * hit_1st / total
        rate_exacta = 100.0 * hit_exacta / total
        rate_1bet = 100.0 * hit_1bet / total
        rate_3bet = 100.0 * hit_3bet / total

        print(f"  レース数:         {total:>6,}件")
        print(f"  1着的中率:        {rate_1st:>5.1f}%  ({hit_1st:>6,}件)")
        print(f"  2連単的中率:      {rate_exacta:>5.1f}%  ({hit_exacta:>6,}件)")
        print(f"  3連単的中率（1点）: {rate_1bet:>5.1f}%  ({hit_1bet:>6,}件)")
        print(f"  3連単的中率（3点）: {rate_3bet:>5.1f}%  ({hit_3bet:>6,}件)")
        print()

        # 1点買いの収支分析
        cursor.execute('''
            WITH predictions AS (
                SELECT
                    rp1.race_id,
                    rp1.pit_number as p1,
                    rp2.pit_number as p2,
                    rp3.pit_number as p3
                FROM race_predictions rp1
                LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                    AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
                LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                    AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
                WHERE rp1.prediction_type = 'before'
                AND rp1.rank_prediction = 1
                AND rp1.confidence = ?
            ),
            results_agg AS (
                SELECT
                    race_id,
                    CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                    CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                    CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
                FROM results
                WHERE rank IN ('1', '2', '3')
                GROUP BY race_id
            )
            SELECT
                COUNT(*) as races,
                SUM(CASE WHEN pred_combo = r.actual_combo THEN 1 ELSE 0 END) as hits,
                SUM(CASE WHEN pred_combo = r.actual_combo THEN o.odds * 100 ELSE 0 END) as returns,
                SUM(100) as investment,
                AVG(CASE WHEN pred_combo = r.actual_combo THEN o.odds END) as avg_hit_odds
            FROM (
                SELECT
                    p.race_id,
                    CAST(p.p1 AS TEXT) || '-' || CAST(p.p2 AS TEXT) || '-' || CAST(p.p3 AS TEXT) as pred_combo
                FROM predictions p
            ) pred
            LEFT JOIN trifecta_odds o ON pred.race_id = o.race_id AND o.combination = pred.pred_combo
            LEFT JOIN results_agg r ON pred.race_id = r.race_id
        ''', (conf,))

        row = cursor.fetchone()
        races_1bet, hits_1bet, returns_1bet, investment_1bet, avg_odds_1bet = row

        if races_1bet and investment_1bet:
            profit_1bet = returns_1bet - investment_1bet
            roi_1bet = 100.0 * returns_1bet / investment_1bet
            print(f"  【1点買い（100円）】")
            print(f"    的中数:     {hits_1bet:>6,}件")
            print(f"    投資額:     {investment_1bet:>8,.0f}円")
            print(f"    払戻額:     {returns_1bet:>8,.0f}円")
            print(f"    収支:       {profit_1bet:>+8,.0f}円")
            print(f"    ROI:        {roi_1bet:>6.1f}%")
            if avg_odds_1bet:
                print(f"    平均配当:   {avg_odds_1bet:>6.1f}倍")
        else:
            print(f"  【1点買い】 データ不足")

        print()

        # 3点買いの収支分析
        cursor.execute('''
            WITH predictions AS (
                SELECT
                    rp1.race_id,
                    rp1.pit_number as p1,
                    rp2.pit_number as p2,
                    rp3.pit_number as p3,
                    rp4.pit_number as p4,
                    rp5.pit_number as p5
                FROM race_predictions rp1
                LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                    AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
                LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                    AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
                LEFT JOIN race_predictions rp4 ON rp1.race_id = rp4.race_id
                    AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
                LEFT JOIN race_predictions rp5 ON rp1.race_id = rp5.race_id
                    AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
                WHERE rp1.prediction_type = 'before'
                AND rp1.rank_prediction = 1
                AND rp1.confidence = ?
            ),
            results_agg AS (
                SELECT
                    race_id,
                    CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                    CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                    CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
                FROM results
                WHERE rank IN ('1', '2', '3')
                GROUP BY race_id
            )
            SELECT
                COUNT(*) as races,
                SUM(CASE WHEN combo_123 = r.actual_combo THEN 1
                         WHEN combo_124 = r.actual_combo THEN 1
                         WHEN combo_125 = r.actual_combo THEN 1
                         ELSE 0 END) as hits,
                SUM(CASE WHEN combo_123 = r.actual_combo THEN o123.odds * 200
                         WHEN combo_124 = r.actual_combo THEN o124.odds * 100
                         WHEN combo_125 = r.actual_combo THEN o125.odds * 100
                         ELSE 0 END) as returns,
                SUM(400) as investment,
                AVG(CASE WHEN combo_123 = r.actual_combo THEN o123.odds
                         WHEN combo_124 = r.actual_combo THEN o124.odds
                         WHEN combo_125 = r.actual_combo THEN o125.odds END) as avg_hit_odds
            FROM (
                SELECT
                    p.race_id,
                    CAST(p.p1 AS TEXT) || '-' || CAST(p.p2 AS TEXT) || '-' || CAST(p.p3 AS TEXT) as combo_123,
                    CAST(p.p1 AS TEXT) || '-' || CAST(p.p2 AS TEXT) || '-' || CAST(p.p4 AS TEXT) as combo_124,
                    CAST(p.p1 AS TEXT) || '-' || CAST(p.p2 AS TEXT) || '-' || CAST(p.p5 AS TEXT) as combo_125
                FROM predictions p
            ) pred
            LEFT JOIN trifecta_odds o123 ON pred.race_id = o123.race_id AND o123.combination = pred.combo_123
            LEFT JOIN trifecta_odds o124 ON pred.race_id = o124.race_id AND o124.combination = pred.combo_124
            LEFT JOIN trifecta_odds o125 ON pred.race_id = o125.race_id AND o125.combination = pred.combo_125
            LEFT JOIN results_agg r ON pred.race_id = r.race_id
        ''', (conf,))

        row = cursor.fetchone()
        races_3bet, hits_3bet, returns_3bet, investment_3bet, avg_odds_3bet = row

        if races_3bet and investment_3bet:
            profit_3bet = returns_3bet - investment_3bet
            roi_3bet = 100.0 * returns_3bet / investment_3bet
            print(f"  【3点買い（400円: 200/100/100）】")
            print(f"    的中数:     {hits_3bet:>6,}件")
            print(f"    投資額:     {investment_3bet:>8,.0f}円")
            print(f"    払戻額:     {returns_3bet:>8,.0f}円")
            print(f"    収支:       {profit_3bet:>+8,.0f}円")
            print(f"    ROI:        {roi_3bet:>6.1f}%")
            if avg_odds_3bet:
                print(f"    平均配当:   {avg_odds_3bet:>6.1f}倍")

            # 比較
            if investment_1bet:
                diff = profit_3bet - profit_1bet
                print()
                print(f"  【比較】")
                print(f"    収支差:     {diff:>+8,.0f}円  ", end='')
                if diff > 0:
                    print(f"(3点買いの方が有利)")
                elif diff < 0:
                    print(f"(1点買いの方が有利)")
                else:
                    print(f"(同等)")
        else:
            print(f"  【3点買い】 データ不足")

        print()

    # 全体サマリー
    print("="*80)
    print("【全信頼度 合計】")
    print("="*80)

    cursor.execute('''
        WITH predictions AS (
            SELECT
                rp1.race_id,
                rp1.confidence,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3,
                rp4.pit_number as p4,
                rp5.pit_number as p5
            FROM race_predictions rp1
            LEFT JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            LEFT JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            LEFT JOIN race_predictions rp4 ON rp1.race_id = rp4.race_id
                AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            LEFT JOIN race_predictions rp5 ON rp1.race_id = rp5.race_id
                AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
            WHERE rp1.prediction_type = 'before'
            AND rp1.rank_prediction = 1
        ),
        results_agg AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank = '1' THEN pit_number END) as a1,
                MAX(CASE WHEN rank = '2' THEN pit_number END) as a2,
                MAX(CASE WHEN rank = '3' THEN pit_number END) as a3
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            COUNT(*) as total_races,
            SUM(CASE WHEN p.p1 = r.a1 THEN 1 ELSE 0 END) as hit_1st,
            SUM(CASE WHEN p.p1 = r.a1 AND p.p2 = r.a2 THEN 1 ELSE 0 END) as hit_exacta,
            SUM(CASE WHEN p.p1 = r.a1 AND p.p2 = r.a2 AND p.p3 = r.a3 THEN 1 ELSE 0 END) as hit_1bet,
            SUM(CASE WHEN p.p1 = r.a1 AND p.p2 = r.a2 AND (p.p3 = r.a3 OR p.p4 = r.a3 OR p.p5 = r.a3)
                THEN 1 ELSE 0 END) as hit_3bet
        FROM predictions p
        LEFT JOIN results_agg r ON p.race_id = r.race_id
    ''')

    row = cursor.fetchone()
    total, hit_1st, hit_exacta, hit_1bet, hit_3bet = row

    if total > 0:
        print(f"  総レース数:       {total:>6,}件")
        print(f"  1着的中率:        {100.0*hit_1st/total:>5.1f}%")
        print(f"  2連単的中率:      {100.0*hit_exacta/total:>5.1f}%")
        print(f"  3連単的中率（1点）: {100.0*hit_1bet/total:>5.1f}%")
        print(f"  3連単的中率（3点）: {100.0*hit_3bet/total:>5.1f}%")
        print(f"  的中率向上:       {100.0*(hit_3bet-hit_1bet)/total:>+5.1f}pt  (3点買い)")

    conn.close()
    print()
    print("="*80)
    print("分析完了")
    print("="*80)

if __name__ == '__main__':
    import time
    start = time.time()
    analyze_confidence_patterns()
    elapsed = time.time() - start
    print(f"\n実行時間: {elapsed:.1f}秒")
