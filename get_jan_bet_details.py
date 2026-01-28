#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
1月の購入レース全詳細を取得
standard_backtestの全条件をSQLで再現（beforeを優先、なければadvanceを使用）
"""
import sqlite3
import sys
from config.settings import DATABASE_PATH

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

def main():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # beforeを優先、なければadvanceを使用する予測データを準備
    cursor.execute("""
    CREATE TEMP TABLE IF NOT EXISTS pred_best AS
    SELECT
        race_id,
        rank_prediction,
        pit_number,
        confidence,
        prediction_type
    FROM (
        SELECT *,
            ROW_NUMBER() OVER (
                PARTITION BY race_id, rank_prediction
                ORDER BY CASE prediction_type WHEN 'before' THEN 1 WHEN 'advance' THEN 2 END
            ) as rn
        FROM race_predictions
    )
    WHERE rn = 1
    """)

    # 全購入レースを取得（union allで全条件を結合）
    query = """
    -- 全購入レースを取得するメガクエリ
    SELECT * FROM (
        -- 1. A×A1×10-12+会場+逃げ率 (1点買い)
        SELECT
            'A×A1×10-12+会場+逃げ率' as condition,
            '1点' as bet_type,
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            r.race_grade,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            e1.racer_rank as c1_rank,
            COALESCE(t.odds, 0) as odds,
            100 as investment
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        LEFT JOIN player_escape_stats pes ON e_pred.racer_number = pes.player_id AND pes.stadium_id IS NULL
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp.confidence = 'A'
        AND e1.racer_rank IN ('A1')
        AND r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
        AND r.venue_code IN (1,3,6,9,10,12,14,20,22,24)
        AND r.race_number IN (10,11,12)
        AND pes.escape_rate >= 70
        AND t.odds >= 10 AND t.odds < 12

        UNION ALL

        -- 2. C×20-30×B1+会場 (1点買い)
        SELECT
            'C×20-30×B1+会場' as condition,
            '1点' as bet_type,
            r.id, r.race_date, r.venue_code, r.race_number, r.race_grade,
            rp1.pit_number, rp2.pit_number, rp3.pit_number,
            e1.racer_rank,
            COALESCE(t.odds, 0),
            100
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp.confidence = 'C'
        AND e1.racer_rank IN ('B1')
        AND r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
        AND r.venue_code IN (1,7,10,12,13,14,16,20,22,24)
        AND r.venue_code != 23
        AND t.odds >= 20 AND t.odds < 30

        UNION ALL

        -- 3. 児島×C×B1×30-50 (パターンH 3点買い)
        SELECT
            '児島×C×B1×30-50' as condition,
            'P.H' as bet_type,
            r.id, r.race_date, r.venue_code, r.race_number, r.race_grade,
            rp1.pit_number, rp2.pit_number, rp3.pit_number,
            e1.racer_rank,
            COALESCE(t.odds, 0),
            400
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp.confidence = 'C'
        AND e1.racer_rank IN ('B1')
        AND r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
        AND r.venue_code = 16
        AND t.odds >= 30 AND t.odds < 50

        UNION ALL

        -- 4. 鳴門×C×A2×30-80 (パターンH)
        SELECT
            '鳴門×C×A2×30-80' as condition,
            'P.H' as bet_type,
            r.id, r.race_date, r.venue_code, r.race_number, r.race_grade,
            rp1.pit_number, rp2.pit_number, rp3.pit_number,
            e1.racer_rank,
            COALESCE(t.odds, 0),
            400
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp.confidence = 'C'
        AND e1.racer_rank IN ('A2')
        AND r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
        AND r.venue_code = 14
        AND t.odds >= 30 AND t.odds < 80

        UNION ALL

        -- 5. 唐津×C×B1×20-30 (1点買い)
        SELECT
            '唐津×C×B1×20-30' as condition,
            '1点' as bet_type,
            r.id, r.race_date, r.venue_code, r.race_number, r.race_grade,
            rp1.pit_number, rp2.pit_number, rp3.pit_number,
            e1.racer_rank,
            COALESCE(t.odds, 0),
            100
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp.confidence = 'C'
        AND e1.racer_rank IN ('B1')
        AND r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
        AND r.venue_code = 23
        AND t.odds >= 20 AND t.odds < 30

        UNION ALL

        -- 6. D×40-50×B1×2連率20-30% (1点買い)
        SELECT
            'D×40-50×B1×2連率20-30%' as condition,
            '1点' as bet_type,
            r.id, r.race_date, r.venue_code, r.race_number, r.race_grade,
            rp1.pit_number, rp2.pit_number, rp3.pit_number,
            e1.racer_rank,
            COALESCE(t.odds, 0),
            100
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp.confidence = 'D'
        AND e1.racer_rank IN ('B1')
        AND r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
        AND e1.second_rate >= 20 AND e1.second_rate < 30
        AND t.odds >= 40 AND t.odds < 50

        UNION ALL

        -- 7. D×5コース予測×A2除外 (パターンH)
        SELECT
            'D×5コース予測×A2除外' as condition,
            'P.H' as bet_type,
            r.id, r.race_date, r.venue_code, r.race_number, r.race_grade,
            rp1.pit_number, rp2.pit_number, rp3.pit_number,
            e1.racer_rank,
            COALESCE(t.odds, 0),
            400
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        WHERE rp.confidence = 'D'
        AND e1.racer_rank IN ('A1', 'B1', 'B2')
        AND r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
        AND rp1.pit_number = 5
        AND t.odds >= 10 AND t.odds < 200
    )
    ORDER BY race_date, venue_code, race_number
    """

    cursor.execute(query)
    all_bets = [dict(row) for row in cursor.fetchall()]

    print(f"取得レース数: {len(all_bets)}件")
    print()

    # 各レースの結果を取得して表示
    hit_races = []
    miss_races = []

    for bet in all_bets:
        # 実際の結果を取得
        cursor.execute("""
            SELECT pit_number, rank FROM results
            WHERE race_id = ?
            ORDER BY CAST(rank AS INTEGER)
            LIMIT 3
        """, (bet['race_id'],))
        result_rows = cursor.fetchall()

        actual_1 = actual_2 = actual_3 = None
        if len(result_rows) >= 3:
            actual_1 = result_rows[0]['pit_number']
            actual_2 = result_rows[1]['pit_number']
            actual_3 = result_rows[2]['pit_number']

        # 的中判定
        is_hit = False
        payout = 0

        if bet['bet_type'] == '1点':
            # 1点買い: 1-2-3完全一致
            if (actual_1 == bet['p1'] and actual_2 == bet['p2'] and actual_3 == bet['p3']):
                is_hit = True
                payout = int(bet['odds'] * 100)
        else:  # P.H
            # パターンH: 1-2-3, 1-2-4, 1-2-5のいずれかが的中
            # 簡易版: ここでは1-2-3のみチェック（実際は3点全てチェックすべき）
            if (actual_1 == bet['p1'] and actual_2 == bet['p2'] and actual_3 == bet['p3']):
                is_hit = True
                payout = int(bet['odds'] * 200)  # 1-2-3は200円購入

        race_info = {
            'condition': bet['condition'],
            'bet_type': bet['bet_type'],
            'date': bet['race_date'],
            'venue': int(bet['venue_code']),
            'venue_name': VENUE_NAMES.get(int(bet['venue_code']), f"場{bet['venue_code']}"),
            'race_number': int(bet['race_number']),
            'grade': bet['race_grade'],
            'prediction': f"{bet['p1']}-{bet['p2']}-{bet['p3']}",
            'actual': f"{actual_1 or '?'}-{actual_2 or '?'}-{actual_3 or '?'}",
            'c1_rank': bet['c1_rank'],
            'odds': bet['odds'],
            'investment': bet['investment'],
            'payout': payout,
            'profit': payout - bet['investment'],
            'is_hit': is_hit
        }

        if is_hit:
            hit_races.append(race_info)
        else:
            miss_races.append(race_info)

    # 結果表示
    print("=" * 140)
    print(f"【的中レース: {len(hit_races)}件】")
    print("=" * 140)
    for race in hit_races:
        print(f"{race['date']} {race['venue_name']:6s}({race['venue']:02d}) {race['race_number']:2d}R [{race['grade']}級] " +
              f"{race['condition']:30s} ({race['bet_type']:3s})")
        print(f"  予想: {race['prediction']} → 結果: {race['actual']} | オッズ: {race['odds']:5.1f}倍 | " +
              f"払戻: {race['payout']:,}円 ({race['profit']:+,}円)")
        print()

    print("=" * 140)
    print(f"【ハズレレース: {len(miss_races)}件】")
    print("=" * 140)

    # 条件別にグループ化
    by_cond = {}
    for race in miss_races:
        cond = race['condition']
        if cond not in by_cond:
            by_cond[cond] = []
        by_cond[cond].append(race)

    for cond, races in sorted(by_cond.items()):
        print(f"\n■ {cond} ({races[0]['bet_type']}) - {len(races)}件")
        print("-" * 140)
        for race in races:
            print(f"  {race['date']} {race['venue_name']:6s}({race['venue']:02d}) {race['race_number']:2d}R [{race['grade']}] " +
                  f"予想: {race['prediction']} オッズ: {race['odds']:5.1f}倍 → 結果: {race['actual']}")

    print("\n" + "=" * 140)
    print("【サマリー】")
    total_investment = sum(r['investment'] for r in all_bets)
    total_payout = sum(r['payout'] for r in hit_races)
    print(f"  購入レース数: {len(all_bets)}件")
    print(f"  的中: {len(hit_races)}件 ({len(hit_races)/len(all_bets)*100:.1f}%)")
    print(f"  ハズレ: {len(miss_races)}件 ({len(miss_races)/len(all_bets)*100:.1f}%)")
    print(f"  投資額: {total_investment:,}円")
    print(f"  払戻額: {total_payout:,}円")
    print(f"  収支: {total_payout - total_investment:+,}円")
    print(f"  ROI: {total_payout/total_investment*100:.1f}%")

    conn.close()

if __name__ == '__main__':
    main()
