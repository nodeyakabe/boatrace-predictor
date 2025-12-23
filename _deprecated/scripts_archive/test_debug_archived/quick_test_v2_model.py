"""
v2モデルの簡易動作確認スクリプト

HierarchicalPredictorでv2モデルを使用して実際に予測を行う
"""
import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.prediction.hierarchical_predictor import HierarchicalPredictor


def main():
    """メイン処理"""
    print("=" * 80)
    print("v2モデルの動作確認")
    print("=" * 80)

    # パス設定
    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    model_dir = PROJECT_ROOT / "models"

    # サンプルレースIDを取得（2024年のレース）
    import sqlite3
    race_id = None

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM races
                WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'
                ORDER BY id
                LIMIT 1
            """)
            result = cursor.fetchone()
            if result:
                race_id = result[0]

        if not race_id:
            print("ERROR: 2024年のレースが見つかりません")
            return

        print(f"\nサンプルレースID: {race_id}")

    except Exception as e:
        print(f"レースID取得エラー: {e}")
        return

    # v1モデルで予測
    print("\n【v1モデル（既存）】")
    predictor_v1 = HierarchicalPredictor(str(db_path), str(model_dir), use_v2=False)

    try:

        # v1で予測
        result_v1 = predictor_v1.predict_race(race_id, use_conditional_model=True)

        if 'error' not in result_v1:
            print(f"モデル使用: {result_v1['model_used']}")
            print("\n上位5組み合わせ:")
            for i, (comb, prob) in enumerate(result_v1['top_combinations'][:5], 1):
                print(f"  {i}. {comb}: {prob*100:.2f}%")

            # 各艇の1位確率
            print("\n各艇の1位確率:")
            for pit, probs in sorted(result_v1['rank_probs'].items()):
                first_prob = probs.get(1, 0) * 100
                print(f"  {pit}号艇: {first_prob:.2f}%")
        else:
            print(f"エラー: {result_v1['error']}")

    except Exception as e:
        print(f"v1モデルエラー: {e}")
        import traceback
        traceback.print_exc()

    # v2モデルで予測
    print("\n" + "=" * 80)
    print("【v2モデル（改善版）】")
    print("=" * 80)

    predictor_v2 = HierarchicalPredictor(str(db_path), str(model_dir), use_v2=True)

    try:
        # v2で予測
        result_v2 = predictor_v2.predict_race(race_id, use_conditional_model=True)

        if 'error' not in result_v2:
            print(f"モデル使用: {result_v2['model_used']}")
            print("\n上位5組み合わせ:")
            for i, (comb, prob) in enumerate(result_v2['top_combinations'][:5], 1):
                print(f"  {i}. {comb}: {prob*100:.2f}%")

            # 各艇の1位確率
            print("\n各艇の1位確率:")
            for pit, probs in sorted(result_v2['rank_probs'].items()):
                first_prob = probs.get(1, 0) * 100
                print(f"  {pit}号艇: {first_prob:.2f}%")

            # v1との違いを表示
            print("\n" + "=" * 80)
            print("【v1とv2の比較】")
            print("=" * 80)

            print("\n上位1組み合わせの確率:")
            if result_v1.get('top_combinations') and result_v2.get('top_combinations'):
                v1_top = result_v1['top_combinations'][0]
                v2_top = result_v2['top_combinations'][0]
                print(f"  v1: {v1_top[0]} = {v1_top[1]*100:.2f}%")
                print(f"  v2: {v2_top[0]} = {v2_top[1]*100:.2f}%")

        else:
            print(f"エラー: {result_v2['error']}")

    except Exception as e:
        print(f"v2モデルエラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
