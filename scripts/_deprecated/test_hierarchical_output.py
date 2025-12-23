# -*- coding: utf-8 -*-
"""HierarchicalPredictorの出力形式を確認"""
import sqlite3
from src.prediction.hierarchical_predictor import HierarchicalPredictor

# DB接続
conn = sqlite3.connect('data/boatrace.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 2024-11-02のレースを1つ取得
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

    # V1で予測
    print("\n=== V1モデル ===")
    pred_v1 = HierarchicalPredictor(db_path='data/boatrace.db', use_v2=False)
    pred_v1.load_models()
    result_v1 = pred_v1.predict_race(race['id'])

    print(f"結果キー: {result_v1.keys() if result_v1 else 'None'}")
    if result_v1 and 'top3_predictions' in result_v1:
        print(f"top3_predictions型: {type(result_v1['top3_predictions'])}")
        print(f"top3_predictions内容: {result_v1['top3_predictions'][:3] if len(result_v1['top3_predictions']) >= 3 else result_v1['top3_predictions']}")
        if len(result_v1['top3_predictions']) > 0:
            print(f"1件目の型: {type(result_v1['top3_predictions'][0])}")
            print(f"1件目の内容: {result_v1['top3_predictions'][0]}")

    # V2で予測
    print("\n=== V2モデル ===")
    pred_v2 = HierarchicalPredictor(db_path='data/boatrace.db', use_v2=True)
    pred_v2.load_models()
    result_v2 = pred_v2.predict_race(race['id'])

    print(f"結果キー: {result_v2.keys() if result_v2 else 'None'}")
    if result_v2 and 'top3_predictions' in result_v2:
        print(f"top3_predictions型: {type(result_v2['top3_predictions'])}")
        print(f"top3_predictions内容: {result_v2['top3_predictions'][:3] if len(result_v2['top3_predictions']) >= 3 else result_v2['top3_predictions']}")
        if len(result_v2['top3_predictions']) > 0:
            print(f"1件目の型: {type(result_v2['top3_predictions'][0])}")
            print(f"1件目の内容: {result_v2['top3_predictions'][0]}")
else:
    print("テストレースが見つかりません")

conn.close()
