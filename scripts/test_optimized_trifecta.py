"""
最適化版三連単計算のテスト

既存版との精度比較と速度測定
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import time
import sqlite3
import pandas as pd
from prediction.trifecta_calculator import TrifectaCalculator
from prediction.trifecta_calculator_optimized import TrifectaCalculatorOptimized


def get_sample_race_features(db_path: str, race_id: int) -> pd.DataFrame:
    """サンプルレースの特徴量を取得"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    query = """
    SELECT
        e.pit_number,
        e.racer_number,
        e.motor_number,
        e.boat_number,
        COALESCE(rd.exhibition_time, 0) as exhibition_time,
        COALESCE(rd.st_time, 0) as st_time
    FROM entries e
    LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    WHERE e.race_id = ?
    ORDER BY e.pit_number
    """

    df = pd.DataFrame([dict(row) for row in conn.execute(query, (race_id,))])
    conn.close()

    # ダミー特徴量を追加（実際のシステムと同じ構造にする）
    for i in range(20):
        df[f'feature_{i}'] = 0.5

    return df


def main():
    db_path = 'data/boatrace.db'

    # サンプルレース取得
    race_id = 21939
    race_features = get_sample_race_features(db_path, race_id)

    print("=" * 80)
    print("三連単計算 最適化版テスト")
    print("=" * 80)
    print(f"\nテストレースID: {race_id}")
    print(f"艇数: {len(race_features)}")

    # 既存版
    print("\n[既存版] TrifectaCalculator")
    calc_original = TrifectaCalculator(model_dir='models', model_name='conditional')

    start = time.time()
    probs_original = calc_original.calculate(race_features)
    time_original = time.time() - start

    print(f"処理時間: {time_original:.4f}秒")
    print(f"確率合計: {sum(probs_original.values()):.6f}")
    top_original = calc_original.get_top_combinations(probs_original, 5)
    print("上位5件:")
    for combo, prob in top_original:
        print(f"  {combo}: {prob:.6f}")

    # 最適化版
    print("\n[最適化版] TrifectaCalculatorOptimized")
    calc_optimized = TrifectaCalculatorOptimized(model_dir='models', model_name='conditional')

    start = time.time()
    probs_optimized = calc_optimized.calculate(race_features)
    time_optimized = time.time() - start

    print(f"処理時間: {time_optimized:.4f}秒")
    print(f"確率合計: {sum(probs_optimized.values()):.6f}")
    top_optimized = calc_optimized.get_top_combinations(probs_optimized, 5)
    print("上位5件:")
    for combo, prob in top_optimized:
        print(f"  {combo}: {prob:.6f}")

    # 比較
    print("\n" + "=" * 80)
    print("比較結果")
    print("=" * 80)
    print(f"速度改善: {time_original:.4f}秒 → {time_optimized:.4f}秒 ({(1 - time_optimized/time_original)*100:.1f}%削減)")

    # 精度検証（上位10件の一致率）
    top10_original = set([combo for combo, _ in calc_original.get_top_combinations(probs_original, 10)])
    top10_optimized = set([combo for combo, _ in calc_optimized.get_top_combinations(probs_optimized, 10)])
    match_rate = len(top10_original & top10_optimized) / 10 * 100
    print(f"上位10件の一致率: {match_rate:.1f}%")

    # 確率の差分チェック
    max_diff = 0
    for combo in probs_original:
        diff = abs(probs_original[combo] - probs_optimized.get(combo, 0))
        max_diff = max(max_diff, diff)
    print(f"確率の最大差分: {max_diff:.8f}")

    if match_rate == 100 and max_diff < 1e-6:
        print("\n✓ 精度は完全に一致しています")
    elif match_rate >= 90 and max_diff < 1e-4:
        print("\n✓ 精度はほぼ一致しています（許容範囲）")
    else:
        print("\n⚠ 精度に差異があります。要確認")


if __name__ == '__main__':
    main()
