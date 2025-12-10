"""
予測手法の比較スクリプト

1. race_predictions（既存予測データ）
2. 条件付きモデルv1（今回評価）
3. 条件付きモデルv2（今回評価）

の3つを同じレースで比較
"""
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.prediction.hierarchical_predictor import HierarchicalPredictor

def main():
    print("="*80)
    print("予測手法の比較")
    print("="*80)

    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    model_dir = PROJECT_ROOT / "models"

    # 2024年の最初の10レースで比較
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.id, r.race_date, r.venue_code, r.race_number
            FROM races r
            WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
            ORDER BY r.id
            LIMIT 10
        """)
        races = cursor.fetchall()

    print(f"\n比較レース数: {len(races)}\n")

    # 各予測手法の的中率
    stats = {
        'race_predictions': {'total': 0, 'hit': 0},
        'conditional_v1': {'total': 0, 'hit': 0},
        'conditional_v2': {'total': 0, 'hit': 0}
    }

    predictor_v1 = HierarchicalPredictor(str(db_path), str(model_dir), use_v2=False)
    predictor_v2 = HierarchicalPredictor(str(db_path), str(model_dir), use_v2=True)

    for race_id, race_date, venue_code, race_number in races:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 実際の結果
            cursor.execute("""
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            """, (race_id,))
            actual = cursor.fetchall()

            if len(actual) < 3:
                continue

            actual_combo = f"{actual[0][0]}-{actual[1][0]}-{actual[2][0]}"

            # 1. race_predictionsの予測
            cursor.execute("""
                SELECT pit_number FROM race_predictions
                WHERE race_id = ? AND prediction_type = 'advance'
                ORDER BY rank_prediction
                LIMIT 3
            """, (race_id,))
            pred_db = cursor.fetchall()

            if len(pred_db) == 3:
                db_combo = f"{pred_db[0][0]}-{pred_db[1][0]}-{pred_db[2][0]}"
                stats['race_predictions']['total'] += 1
                if db_combo == actual_combo:
                    stats['race_predictions']['hit'] += 1

                print(f"レースID {race_id}: race_predictions = {db_combo}, 実際 = {actual_combo}, {'的中' if db_combo == actual_combo else '外れ'}")

        # 2. 条件付きモデルv1
        try:
            result_v1 = predictor_v1.predict_race(race_id, use_conditional_model=True)
            if 'error' not in result_v1 and result_v1['top_combinations']:
                v1_combo = result_v1['top_combinations'][0][0]
                stats['conditional_v1']['total'] += 1
                if v1_combo == actual_combo:
                    stats['conditional_v1']['hit'] += 1

                print(f"            conditional_v1 = {v1_combo}, 実際 = {actual_combo}, {'的中' if v1_combo == actual_combo else '外れ'}")
        except Exception as e:
            print(f"            conditional_v1: エラー ({e})")

        # 3. 条件付きモデルv2
        try:
            result_v2 = predictor_v2.predict_race(race_id, use_conditional_model=True)
            if 'error' not in result_v2 and result_v2['top_combinations']:
                v2_combo = result_v2['top_combinations'][0][0]
                stats['conditional_v2']['total'] += 1
                if v2_combo == actual_combo:
                    stats['conditional_v2']['hit'] += 1

                print(f"            conditional_v2 = {v2_combo}, 実際 = {actual_combo}, {'的中' if v2_combo == actual_combo else '外れ'}")
        except Exception as e:
            print(f"            conditional_v2: エラー ({e})")

        print()

    # サマリー
    print("="*80)
    print("三連単的中率サマリー")
    print("="*80)
    for method, data in stats.items():
        if data['total'] > 0:
            rate = data['hit'] / data['total'] * 100
            print(f"{method:20s}: {data['hit']}/{data['total']} = {rate:.2f}%")
        else:
            print(f"{method:20s}: データなし")

if __name__ == "__main__":
    main()
