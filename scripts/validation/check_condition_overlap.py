"""条件間の重複を調査"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import sqlite3
from config.bet_conditions import STANDARD_BET_CONDITIONS

def check_overlap():
    conn = sqlite3.connect('data/boatrace.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # D×40-50×B1条件とD×5コース条件の定義
    cond1 = next(c for c in STANDARD_BET_CONDITIONS if c['id'] == 'D_40_50_B1')
    cond2 = next(c for c in STANDARD_BET_CONDITIONS if c['id'] == 'D_course5')

    print("=" * 80)
    print("条件間の重複調査")
    print("=" * 80)
    print(f"\n条件1: {cond1['id']} - {cond1['name']}")
    print(f"  信頼度: {cond1['confidence']}, C1級別: {cond1['c1_rank']}, オッズ: {cond1['odds_min']}-{cond1['odds_max']}")
    print(f"  会場: {cond1.get('venue_filter', 'なし')}, 予測コース: {cond1.get('predicted_course', 'なし')}")
    print(f"\n条件2: {cond2['id']} - {cond2['name']}")
    print(f"  信頼度: {cond2['confidence']}, C1級別: {cond2['c1_rank']}, オッズ: {cond2['odds_min']}-{cond2['odds_max']}")
    print(f"  会場: {cond2.get('venue_filter', 'なし')}, 予測コース: {cond2.get('predicted_course', 'なし')}")

    # 期間
    start_date = '2024-01-01'
    end_date = '2025-01-01'

    # 共通条件
    common_confidence = cond1['confidence']  # 両方とも'D'
    common_c1_ranks = list(set(cond1['c1_rank']) & set(cond2['c1_rank']))  # 両方に含まれる級別

    if not common_c1_ranks:
        print("\n結果: C1級別の重複なし → 重複レースは発生しない")
        return

    print(f"\n共通C1級別: {common_c1_ranks}")

    # 条件1のレースを取得（簡略化）
    c1_ranks_str = ','.join([f"'{r}'" for r in cond1['c1_rank']])
    query1 = f"""
    SELECT DISTINCT r.id, r.race_date, r.venue_code
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp.confidence = '{cond1['confidence']}'
    AND e1.racer_rank IN ({c1_ranks_str})
    AND r.race_date >= '{start_date}'
    AND r.race_date < '{end_date}'
    """

    cursor.execute(query1)
    cond1_races = set(row['id'] for row in cursor.fetchall())
    print(f"\n条件1該当レース数: {len(cond1_races)}")

    # 条件2のレースを取得（予測コース5も含む）
    c2_ranks_str = ','.join([f"'{r}'" for r in cond2['c1_rank']])
    venue_codes_str = ','.join([f"'{v:02d}'" for v in cond2.get('venue_filter', [])])
    query2 = f"""
    SELECT DISTINCT r.id, r.race_date, r.venue_code
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp.confidence = '{cond2['confidence']}'
    AND e1.racer_rank IN ({c2_ranks_str})
    AND r.race_date >= '{start_date}'
    AND r.race_date < '{end_date}'
    AND r.venue_code IN ({venue_codes_str})
    AND rp.pit_number = 5
    """

    cursor.execute(query2)
    cond2_races = set(row['id'] for row in cursor.fetchall())
    print(f"条件2該当レース数: {len(cond2_races)}")

    # 重複レース
    overlap_races = cond1_races & cond2_races
    print(f"\n重複レース数: {len(overlap_races)}")
    print(f"重複率: {len(overlap_races) / len(cond2_races) * 100:.1f}% (条件2ベース)")

    if overlap_races:
        print(f"\n重複レースの例（最初の5件）:")
        for race_id in list(overlap_races)[:5]:
            cursor.execute("SELECT race_date, venue_code, race_number FROM races WHERE id = ?", (race_id,))
            row = cursor.fetchone()
            print(f"  race_id: {race_id}, 日付: {row['race_date']}, 会場: {row['venue_code']}, レース: {row['race_number']}R")

    conn.close()

if __name__ == '__main__':
    check_overlap()
