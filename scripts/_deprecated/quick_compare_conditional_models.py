"""
条件付きモデル v1 vs v2 vs v3 の簡易比較スクリプト

2025年データの一部（1000レース）を使って、各モデルの精度を比較する
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pandas as pd
import numpy as np
from src.prediction.trifecta_calculator import TrifectaCalculator
from datetime import datetime

def load_sample_races(db_path: str = 'data/boatrace.db', sample_size: int = 1000) -> pd.DataFrame:
    """2025年のサンプルレースデータを読み込み"""
    conn = sqlite3.connect(db_path)

    query = f"""
    SELECT DISTINCT r.id as race_id
    FROM races r
    JOIN results res ON r.id = res.race_id
    WHERE r.race_date >= '2025-01-01'
      AND r.race_date <= '2025-12-31'
    GROUP BY r.id
    HAVING COUNT(DISTINCT res.pit_number) = 6
    LIMIT {sample_size}
    """

    race_ids = pd.read_sql_query(query, conn)['race_id'].tolist()

    # レースごとの詳細データを取得
    query = f"""
    SELECT
        r.id as race_id,
        CAST(res.pit_number AS INTEGER) as pit_number,
        CAST(res.rank AS INTEGER) as actual_rank,
        p.rank_prediction,
        p.total_score
    FROM races r
    JOIN results res ON r.id = res.race_id
    JOIN race_predictions p ON r.id = p.race_id
        AND res.pit_number = p.pit_number
        AND p.prediction_type = 'advance'
    WHERE r.id IN ({','.join(map(str, race_ids))})
      AND res.rank IS NOT NULL
    ORDER BY r.id, res.pit_number
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def evaluate_predictions(df: pd.DataFrame) -> dict:
    """予測精度を評価"""
    results = {
        '1着精度': 0,
        '2着精度': 0,
        '3着精度': 0,
        '三連単的中率': 0,
        'レース数': 0
    }

    race_ids = df['race_id'].unique()

    for race_id in race_ids:
        race_df = df[df['race_id'] == race_id].sort_values('rank_prediction')

        if len(race_df) != 6:
            continue

        results['レース数'] += 1

        # 予測1-2-3位
        pred_1st = race_df.iloc[0]['pit_number']
        pred_2nd = race_df.iloc[1]['pit_number']
        pred_3rd = race_df.iloc[2]['pit_number']

        # 実際の1-2-3位
        actual_df = race_df.sort_values('actual_rank')
        actual_1st = actual_df.iloc[0]['pit_number']
        actual_2nd = actual_df.iloc[1]['pit_number']
        actual_3rd = actual_df.iloc[2]['pit_number']

        # 的中判定
        if pred_1st == actual_1st:
            results['1着精度'] += 1
        if pred_2nd == actual_2nd:
            results['2着精度'] += 1
        if pred_3rd == actual_3rd:
            results['3着精度'] += 1
        if (pred_1st == actual_1st and pred_2nd == actual_2nd and pred_3rd == actual_3rd):
            results['三連単的中率'] += 1

    # 百分率に変換
    if results['レース数'] > 0:
        for key in ['1着精度', '2着精度', '3着精度', '三連単的中率']:
            results[key] = round(results[key] / results['レース数'] * 100, 2)

    return results

def main():
    print("=" * 70)
    print("条件付きモデル比較テスト（サンプル版）")
    print("=" * 70)

    # 既存の予測データを読み込み（これは現在のモデルを使用）
    print("\n既存予測データの読み込み...")
    df = load_sample_races(sample_size=1000)

    print(f"読み込みレース数: {df['race_id'].nunique()}")
    print(f"読み込みレコード数: {len(df)}")

    # 精度評価
    print("\n=== 現在のモデル（既存予測データ）===")
    results_current = evaluate_predictions(df)

    print(f"  レース数: {results_current['レース数']}")
    print(f"  1着精度: {results_current['1着精度']}%")
    print(f"  2着精度: {results_current['2着精度']}%")
    print(f"  3着精度: {results_current['3着精度']}%")
    print(f"  三連単的中率: {results_current['三連単的中率']}%")

    print("\n" + "=" * 70)
    print("【分析】")
    print("=" * 70)

    baseline_1st = 16.7  # 1/6
    baseline_2nd = 20.0  # 1/5
    baseline_3rd = 25.0  # 1/4

    print(f"1着精度: {results_current['1着精度']}% (ベースライン {baseline_1st}%との差: {results_current['1着精度'] - baseline_1st:+.1f}pt)")
    print(f"2着精度: {results_current['2着精度']}% (ベースライン {baseline_2nd}%との差: {results_current['2着精度'] - baseline_2nd:+.1f}pt)")
    print(f"3着精度: {results_current['3着精度']}% (ベースライン {baseline_3rd}%との差: {results_current['3着精度'] - baseline_3rd:+.1f}pt)")

    print("\n【課題】")
    if results_current['2着精度'] < 45:
        print(f"⚠️ 2着精度が目標（45%）に未達: {results_current['2着精度']}%")
    if results_current['3着精度'] < 35:
        print(f"⚠️ 3着精度が目標（35%）に未達: {results_current['3着精度']}%")

    print("\n【次のステップ】")
    print("v2/v3モデルを使った新しい予測を生成して比較する必要があります。")
    print("- v2モデル: models/conditional_rank_v2_20251215_*.json")
    print("- v3モデル: models/conditional_rank_v3_20251216_134119_*.json")

if __name__ == "__main__":
    main()
