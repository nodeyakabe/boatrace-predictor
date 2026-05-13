"""D×5コース条件のミスマッチを詳細調査"""
import sqlite3
from typing import Dict, List

def main():
    conn = sqlite3.connect('data/boatrace.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # D×5コース条件の定義
    condition = {
        'confidence': 'D',
        'c1_rank': ['A1', 'B1', 'B2'],
        'venue_filter': [5, 6, 1, 4],
        'predicted_course': 5,
        'odds_min': 10,
        'odds_max': 200,
        'use_pattern_h': True
    }

    # 期間
    start_date = '2024-01-01'
    end_date = '2025-01-01'

    # Tier 2のクエリ（simplified）でD×5コース条件のレースを取得
    venue_codes = ','.join([f"'{v:02d}'" for v in condition['venue_filter']])
    c1_ranks = ','.join([f"'{r}'" for r in condition['c1_rank']])

    query = f"""
    SELECT
        r.id as race_id,
        r.venue_code,
        r.race_number,
        r.race_date,
        rp1.pit_number as p1,
        rp2.pit_number as p2,
        rp3.pit_number as p3,
        rp4.pit_number as p4,
        rp5.pit_number as p5,
        e1.racer_rank as c1_rank,
        (SELECT COUNT(*) FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before') as pred_count
    FROM races r
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp1.confidence = '{condition['confidence']}'
    AND e1.racer_rank IN ({c1_ranks})
    AND r.race_date >= '{start_date}'
    AND r.race_date < '{end_date}'
    AND r.venue_code IN ({venue_codes})
    AND rp1.pit_number = 5
    ORDER BY r.race_date, r.race_time
    LIMIT 10
    """

    cursor.execute(query)
    races = [dict(row) for row in cursor.fetchall()]

    print(f"D×5コース条件の候補レース（最初の10件）:")
    print(f"  期間: {start_date} ~ {end_date}")
    print(f"  条件: {condition['confidence']}信頼度, C1級別{condition['c1_rank']}, 会場{condition['venue_filter']}, 1着予測=5コース")
    print()

    for i, race in enumerate(races, 1):
        print(f"{i}. race_id: {race['race_id']}, 日付: {race['race_date']}, 会場: {race['venue_code']}, C1級別: {race['c1_rank']}")
        print(f"   予測: {race['p1']}-{race['p2']}-{race['p3']}-{race['p4']}-{race['p5']}, 予測数: {race['pred_count']}")

        # オッズを取得
        cursor.execute("""
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ?
            AND combination IN (?, ?, ?)
        """, (race['race_id'],
              f"{race['p1']}-{race['p2']}-{race['p3']}",
              f"{race['p1']}-{race['p2']}-{race['p4']}",
              f"{race['p1']}-{race['p2']}-{race['p5']}"))

        odds_rows = cursor.fetchall()
        odds_dict = {row['combination']: row['odds'] for row in odds_rows}

        combo_123 = f"{race['p1']}-{race['p2']}-{race['p3']}"
        combo_124 = f"{race['p1']}-{race['p2']}-{race['p4']}"
        combo_125 = f"{race['p1']}-{race['p2']}-{race['p5']}"

        odds_123 = odds_dict.get(combo_123, 0)
        odds_124 = odds_dict.get(combo_124, 0)
        odds_125 = odds_dict.get(combo_125, 0)

        print(f"   オッズ: {combo_123}={odds_123:.1f}, {combo_124}={odds_124:.1f}, {combo_125}={odds_125:.1f}")

        # オッズ範囲チェック
        in_range_123 = odds_123 > 0 and condition['odds_min'] <= odds_123 < condition['odds_max']
        in_range_124 = odds_124 > 0 and condition['odds_min'] <= odds_124 < condition['odds_max']
        in_range_125 = odds_125 > 0 and condition['odds_min'] <= odds_125 < condition['odds_max']

        any_in_range = in_range_123 or in_range_124 or in_range_125

        print(f"   範囲内({condition['odds_min']}-{condition['odds_max']}): {combo_123}={in_range_123}, {combo_124}={in_range_124}, {combo_125}={in_range_125} → Tier2購入: {any_in_range}")
        print()

    conn.close()

if __name__ == '__main__':
    main()
