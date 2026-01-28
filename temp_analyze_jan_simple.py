#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
1月の購入レース詳細分析（簡易版）
standard_backtestの実際のロジックを使用
"""
import sqlite3
from config.settings import DATABASE_PATH

# 会場名マッピング
VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

def analyze_condition(conn, cond_name, cond_sql):
    """特定条件の購入レースを分析"""
    cursor = conn.cursor()
    cursor.execute(cond_sql)
    results = cursor.fetchall()

    if not results:
        return None

    races = []
    for row in results:
        race_id, race_date, venue_code, p1, p2, p3, c1_rank, odds, investment, payout = row[:10]

        # 結果を取得
        cursor.execute("""
            SELECT pit_number, rank FROM results
            WHERE race_id = ?
            ORDER BY CAST(rank AS INTEGER)
            LIMIT 3
        """, (race_id,))
        result_rows = cursor.fetchall()

        actual_1 = actual_2 = actual_3 = None
        if len(result_rows) >= 3:
            actual_1 = result_rows[0][0]
            actual_2 = result_rows[1][0]
            actual_3 = result_rows[2][0]

        is_hit = payout > 0
        profit = payout - investment

        races.append({
            'race_id': race_id,
            'date': race_date,
            'venue': venue_code,
            'pred': f"{p1}-{p2}-{p3}",
            'actual': f"{actual_1 or '?'}-{actual_2 or '?'}-{actual_3 or '?'}",
            'c1_rank': c1_rank,
            'odds': odds,
            'investment': investment,
            'payout': payout,
            'profit': profit,
            'is_hit': is_hit
        })

    return races

def main():
    conn = sqlite3.connect(DATABASE_PATH)

    print("=" * 120)
    print("1月購入レース詳細分析（2026年1月1日～21日）")
    print("=" * 120)
    print()

    # 条件1: A×A1×10-12+会場+逃げ率 (1点買い)
    cond1_sql = """
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            e1.racer_rank as c1_rank,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        LEFT JOIN player_escape_stats pes ON e_pred.racer_number = pes.player_id AND pes.stadium_id IS NULL
        WHERE rp.rank_prediction = 1
        AND rp.confidence = 'A'
        AND e1.racer_rank IN ('A1')
        AND r.race_date >= '2026-01-01'
        AND r.race_date < '2026-02-01'
        AND r.venue_code IN (1,3,6,9,10,12,14,20,22,24)
        AND r.race_number IN (10,11,12)
        AND pes.escape_rate >= 70
    )
    SELECT
        rb.race_id,
        rb.race_date,
        rb.venue_code,
        rb.p1, rb.p2, rb.p3,
        rb.c1_rank,
        COALESCE(t.odds, 0) as odds,
        100 as investment,
        CASE
            WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3'
                AND t.odds >= 10 AND t.odds < 12
            THEN t.odds * 100
            ELSE 0
        END as payout
    FROM race_base rb
    LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id
        AND t.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
    LEFT JOIN results res1 ON rb.race_id = res1.race_id AND res1.pit_number = rb.p1
    LEFT JOIN results res2 ON rb.race_id = res2.race_id AND res2.pit_number = rb.p2
    LEFT JOIN results res3 ON rb.race_id = res3.race_id AND res3.pit_number = rb.p3
    WHERE t.odds >= 10 AND t.odds < 12
    """

    print("\n■ A×A1×10-12+会場+逃げ率 (1点買い 100円)")
    print("=" * 120)
    races1 = analyze_condition(conn, "A×A1×10-12", cond1_sql)
    if races1:
        display_races(races1, "1点")
    else:
        print("  ※該当レースなし")

    # 条件2: C×20-30×B1+会場 (1点買い)
    cond2_sql = """
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        rp1.pit_number as p1,
        rp2.pit_number as p2,
        rp3.pit_number as p3,
        e1.racer_rank as c1_rank,
        COALESCE(t.odds, 0) as odds,
        100 as investment,
        CASE
            WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3'
                AND t.odds >= 20 AND t.odds < 30
            THEN t.odds * 100
            ELSE 0
        END as payout
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    LEFT JOIN trifecta_odds t ON r.id = t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
    LEFT JOIN results res1 ON r.id = res1.race_id AND res1.pit_number = rp1.pit_number
    LEFT JOIN results res2 ON r.id = res2.race_id AND res2.pit_number = rp2.pit_number
    LEFT JOIN results res3 ON r.id = res3.race_id AND res3.pit_number = rp3.pit_number
    WHERE rp.rank_prediction = 1
    AND rp.confidence = 'C'
    AND e1.racer_rank IN ('B1')
    AND r.race_date >= '2026-01-01'
    AND r.race_date < '2026-02-01'
    AND r.venue_code IN (1,7,10,12,13,14,16,20,22,24)
    AND r.venue_code != 23
    AND t.odds >= 20 AND t.odds < 30
    """

    print("\n■ C×20-30×B1+会場 (1点買い 100円)")
    print("=" * 120)
    races2 = analyze_condition(conn, "C×20-30×B1", cond2_sql)
    if races2:
        display_races(races2, "1点")
    else:
        print("  ※該当レースなし")

    conn.close()

def display_races(races, bet_type):
    """レース一覧を表示"""
    hit_races = [r for r in races if r['is_hit']]
    miss_races = [r for r in races if not r['is_hit']]

    total_investment = sum(r['investment'] for r in races)
    total_payout = sum(r['payout'] for r in races)
    total_profit = total_payout - total_investment
    roi = (total_payout / total_investment * 100) if total_investment > 0 else 0

    print(f"\n【概要】")
    print(f"  購入: {len(races)}件, 的中: {len(hit_races)}件 ({len(hit_races)/len(races)*100:.1f}%), " +
          f"投資: {total_investment:,}円, 払戻: {total_payout:,}円, " +
          f"収支: {total_profit:+,}円, ROI: {roi:.1f}%")

    if hit_races:
        print(f"\n【的中レース: {len(hit_races)}件】")
        for race in hit_races:
            venue_name = VENUE_NAMES.get(race['venue'], f"場{race['venue']}")
            print(f"  {race['date']} {venue_name:6s} 予想:{race['pred']} オッズ:{race['odds']:5.1f}倍 " +
                  f"→ 結果:{race['actual']} 払戻:{race['payout']:,}円 ({race['profit']:+,}円)")

    if miss_races:
        print(f"\n【ハズレレース: {len(miss_races)}件】")
        for race in miss_races[:20]:  # 最初の20件のみ
            venue_name = VENUE_NAMES.get(race['venue'], f"場{race['venue']}")
            print(f"  {race['date']} {venue_name:6s} 予想:{race['pred']} オッズ:{race['odds']:5.1f}倍 " +
                  f"→ 結果:{race['actual']} ({race['profit']:+,}円)")
        if len(miss_races) > 20:
            print(f"  ... 他{len(miss_races)-20}件")

if __name__ == '__main__':
    main()
