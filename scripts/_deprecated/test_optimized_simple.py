"""
最適化版三連単計算の簡易テスト
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import time
import pandas as pd
import numpy as np
from src.prediction.trifecta_calculator_optimized import TrifectaCalculatorOptimized


def create_sample_features() -> pd.DataFrame:
    """サンプル特徴量を作成"""
    data = {
        'pit_number': [1, 2, 3, 4, 5, 6],
        'racer_number': [1001, 1002, 1003, 1004, 1005, 1006],
    }

    # ダミー特徴量を追加
    for i in range(50):
        data[f'feature_{i}'] = np.random.rand(6)

    return pd.DataFrame(data)


def main():
    print("=" * 80)
    print("最適化版三連単計算 簡易テスト")
    print("=" * 80)

    # サンプルデータ作成
    race_features = create_sample_features()
    print(f"\nサンプル艇数: {len(race_features)}")

    # 最適化版テスト
    print("\n[最適化版] TrifectaCalculatorOptimized")
    calc = TrifectaCalculatorOptimized(model_dir='models', model_name='conditional')

    # 3回テスト
    times = []
    for i in range(3):
        start = time.time()
        probs = calc.calculate(race_features)
        elapsed = time.time() - start
        times.append(elapsed)

        if i == 0:
            print(f"初回処理時間: {elapsed:.4f}秒")
            print(f"確率合計: {sum(probs.values()):.6f}")
            print(f"確率数: {len(probs)}")
            top = calc.get_top_combinations(probs, 5)
            print("上位5件:")
            for combo, prob in top:
                print(f"  {combo}: {prob:.6f}")

    avg_time = np.mean(times[1:])  # 初回を除く平均
    print(f"\n平均処理時間 (2-3回目): {avg_time:.4f}秒")
    print(f"最速: {min(times):.4f}秒")
    print(f"最遅: {max(times):.4f}秒")

    print("\nOK: 最適化版が正常に動作しています")


if __name__ == '__main__':
    main()
