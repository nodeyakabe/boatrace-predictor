# -*- coding: utf-8 -*-
"""比較スクリプトのデバッグ"""
import sqlite3
from src.prediction.hierarchical_predictor import HierarchicalPredictor

# 1レースだけテスト
conn = sqlite3.connect('data/boatrace.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

query = '''
    SELECT id, race_date, venue_code, race_number
    FROM races
    WHERE race_date = '2024-11-02'
    LIMIT 1
'''
cursor.execute(query)
race = cursor.fetchone()

if race:
    print(f"テストレース: {race['race_date']} {race['venue_code']}-{race['race_number']}R (ID:{race['id']})")

    # V1予測
    print("\n=== V1予測 ===")
    pred_v1 = HierarchicalPredictor(db_path='data/boatrace.db', use_v2=False)
    pred_v1.load_models()
    result_v1 = pred_v1.predict_race(race['id'])

    if result_v1 and 'top_combinations' in result_v1:
        print(f"top_combinations件数: {len(result_v1['top_combinations'])}")
        if len(result_v1['top_combinations']) > 0:
            best = result_v1['top_combinations'][0]
            print(f"最良組合せ型: {type(best)}")
            print(f"最良組合せ: {best}")
            print(f"最良組合せ長さ: {len(best)}")
            if len(best) >= 3:
                print(f"予測1-2-3着: {best[0]}-{best[1]}-{best[2]}")

    # 実際の結果
    result_query = '''
        SELECT pit_number, rank
        FROM results
        WHERE race_id = ?
        AND is_invalid = 0
        ORDER BY CAST(rank AS INTEGER)
        LIMIT 3
    '''
    cursor.execute(result_query, (race['id'],))
    actual = cursor.fetchall()

    if actual and len(actual) >= 3:
        print(f"\n実際の結果: {actual[0]['pit_number']}-{actual[1]['pit_number']}-{actual[2]['pit_number']}")

        if result_v1 and 'top_combinations' in result_v1 and len(result_v1['top_combinations']) > 0:
            best = result_v1['top_combinations'][0]
            if len(best) >= 3:
                if best[0] == actual[0]['pit_number']:
                    print("✅ 1着的中！")
                if (best[0], best[1], best[2]) == (actual[0]['pit_number'], actual[1]['pit_number'], actual[2]['pit_number']):
                    print("✅✅✅ 3連単的中！")
    else:
        print(f"実際の結果が取得できません: {len(actual) if actual else 0}件")

conn.close()
