# -*- coding: utf-8 -*-
"""
V1/V2モデルの簡易比較テスト（10レースで確認）
"""
import sys
from pathlib import Path
import sqlite3

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

DB_PATH = ROOT_DIR / 'data' / 'boatrace.db'

def test_v1_v2_comparison():
    """V1/V2の予測を比較"""
    from src.prediction.hierarchical_predictor import HierarchicalPredictor

    # 2024-11のレースを10件取得
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = '''
        SELECT DISTINCT r.id as race_id, r.race_date, r.venue_code, r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE r.race_date BETWEEN '2024-11-01' AND '2024-11-30'
        ORDER BY r.race_date, r.venue_code, r.race_number
        LIMIT 10
    '''
    cursor.execute(query)
    races = cursor.fetchall()

    print(f"テスト対象: {len(races)} レース")
    print("=" * 80)

    # V1予測器
    predictor_v1 = HierarchicalPredictor(
        db_path=str(DB_PATH),
        model_dir='models',
        use_v2=False,
        use_optimized=True
    )
    predictor_v1.load_models()

    # V2予測器
    predictor_v2 = HierarchicalPredictor(
        db_path=str(DB_PATH),
        model_dir='models',
        use_v2=True,
        use_optimized=True
    )
    predictor_v2.load_models()

    v1_correct = 0
    v2_correct = 0
    v1_trifecta = 0
    v2_trifecta = 0

    for race in races:
        race_id = race['race_id']
        race_date = race['race_date']
        venue_code = race['venue_code']
        race_number = race['race_number']

        # 実際の結果取得
        result_query = '''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0
            ORDER BY CAST(rank AS INTEGER) LIMIT 3
        '''
        cursor.execute(result_query, (race_id,))
        actual = [r['pit_number'] for r in cursor.fetchall()]

        if len(actual) < 3:
            continue

        # V1予測
        try:
            pred_v1 = predictor_v1.predict_race(race_id)
            if pred_v1 and 'top_combinations' in pred_v1:
                top1_v1 = pred_v1['top_combinations'][0][0]
                pits_v1 = [int(p) for p in top1_v1.split('-')]

                if pits_v1[0] == actual[0]:
                    v1_correct += 1
                if pits_v1 == actual:
                    v1_trifecta += 1
        except Exception as e:
            print(f"V1 Error: {e}")
            pits_v1 = []

        # V2予測
        try:
            pred_v2 = predictor_v2.predict_race(race_id)
            if pred_v2 and 'top_combinations' in pred_v2:
                top1_v2 = pred_v2['top_combinations'][0][0]
                pits_v2 = [int(p) for p in top1_v2.split('-')]

                if pits_v2[0] == actual[0]:
                    v2_correct += 1
                if pits_v2 == actual:
                    v2_trifecta += 1
        except Exception as e:
            print(f"V2 Error: {e}")
            pits_v2 = []

        print(f"{race_date} {venue_code}R{race_number}: 実際={actual[0]}-{actual[1]}-{actual[2]}, V1={'-'.join(map(str, pits_v1)) if pits_v1 else 'N/A'}, V2={'-'.join(map(str, pits_v2)) if pits_v2 else 'N/A'}")

    conn.close()

    print("\n" + "=" * 80)
    print(f"結果 (10レース)")
    print(f"V1: 1着的中={v1_correct}, 3連単的中={v1_trifecta}")
    print(f"V2: 1着的中={v2_correct}, 3連単的中={v2_trifecta}")


if __name__ == '__main__':
    test_v1_v2_comparison()
