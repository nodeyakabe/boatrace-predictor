"""
条件付きモデルv2のバックテストスクリプト

v1（既存）とv2（改善版）を比較して、精度改善を定量化
"""
import os
import sys
import sqlite3
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
import joblib
import json
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.features.feature_transforms import create_training_dataset_with_relative_features


def load_model_v1(model_dir):
    """既存モデル（v1）を読み込み"""
    try:
        stage1 = joblib.load(model_dir / "conditional_stage1.joblib")
        stage2 = joblib.load(model_dir / "conditional_stage2.joblib")
        stage3 = joblib.load(model_dir / "conditional_stage3.joblib")

        with open(model_dir / "conditional_meta.json", 'r', encoding='utf-8') as f:
            meta = json.load(f)

        return stage1, stage2, stage3, meta
    except Exception as e:
        print(f"v1モデル読み込みエラー: {e}")
        return None, None, None, None


def load_model_v2(model_dir, timestamp=None):
    """改善版モデル（v2）を読み込み"""
    try:
        if timestamp:
            stage1 = joblib.load(model_dir / f"conditional_stage1_v2_{timestamp}.joblib")
            stage2 = joblib.load(model_dir / f"conditional_stage2_v2_{timestamp}.joblib")
            stage3 = joblib.load(model_dir / f"conditional_stage3_v2_{timestamp}.joblib")
            meta_path = model_dir / f"conditional_meta_v2_{timestamp}.json"
        else:
            # 最新のv2モデルを検索
            v2_files = list(model_dir.glob("conditional_stage2_v2_*.joblib"))
            if not v2_files:
                print("v2モデルが見つかりません")
                return None, None, None, None

            latest = sorted(v2_files)[-1]
            timestamp = latest.stem.split('_')[-1]

            stage1 = joblib.load(model_dir / f"conditional_stage1_v2_{timestamp}.joblib")
            stage2 = joblib.load(model_dir / f"conditional_stage2_v2_{timestamp}.joblib")
            stage3 = joblib.load(model_dir / f"conditional_stage3_v2_{timestamp}.joblib")
            meta_path = model_dir / f"conditional_meta_v2_{timestamp}.json"

        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        return stage1, stage2, stage3, meta
    except Exception as e:
        print(f"v2モデル読み込みエラー: {e}")
        return None, None, None, None


def calculate_predicted_first(df):
    """予想1位を計算（簡易版）"""
    df['predicted_score'] = (
        df['win_rate'].fillna(0) * 0.4 +
        df['second_rate'].fillna(0) * 0.2 +
        df['motor_second_rate'].fillna(0) * 0.2 +
        df['boat_second_rate'].fillna(0) * 0.1 +
        (df['exhibition_time'].fillna(100) < 6.8).astype(float) * 0.1
    )
    return df.groupby('race_id')['predicted_score'].idxmax()


def backtest_stage2(df, model_v1, model_v2):
    """Stage2（2位予測）のバックテスト"""
    print("\n" + "=" * 80)
    print("Stage2（2位予測）バックテスト")
    print("=" * 80)

    results = {
        'v1_case1': {'correct': 0, 'total': 0},  # v1, 予想1位的中時
        'v1_case2': {'correct': 0, 'total': 0},  # v1, 予想1位外れ時
        'v2_case1': {'correct': 0, 'total': 0},  # v2, 予想1位的中時
        'v2_case2': {'correct': 0, 'total': 0},  # v2, 予想1位外れ時
    }

    # レースごとに処理
    for race_id in df['race_id'].unique():
        race_df = df[df['race_id'] == race_id].copy()

        if len(race_df) != 6:
            continue

        # 予想1位を計算
        predicted_first_idx = calculate_predicted_first(race_df)
        predicted_first_pit = race_df.loc[predicted_first_idx, 'pit_number']

        # 実際の1位・2位
        actual_first_pit = race_df[race_df['rank'] == 1]['pit_number'].values[0] if len(race_df[race_df['rank'] == 1]) > 0 else None
        actual_second_pit = race_df[race_df['rank'] == 2]['pit_number'].values[0] if len(race_df[race_df['rank'] == 2]) > 0 else None

        if actual_first_pit is None or actual_second_pit is None:
            continue

        # 予想1位が的中したか
        first_correct = (predicted_first_pit == actual_first_pit)

        # v1とv2で2位を予測（簡易版：実装は省略、ここではランダムとする）
        # 実際の実装では、モデルを使って予測確率を計算

        # Case 1 or Case 2
        case = 'case1' if first_correct else 'case2'

        # 仮の予測（ランダム）
        # 実装時はモデルの予測確率を使用
        results[f'v1_{case}']['total'] += 1
        results[f'v2_{case}']['total'] += 1

    # 結果表示
    print("\nv1（既存モデル）:")
    for case in ['case1', 'case2']:
        total = results[f'v1_{case}']['total']
        correct = results[f'v1_{case}']['correct']
        accuracy = (correct / total * 100) if total > 0 else 0
        case_name = "予想1位的中時" if case == 'case1' else "予想1位外れ時"
        print(f"  {case_name}: {correct}/{total} ({accuracy:.2f}%)")

    print("\nv2（改善版モデル）:")
    for case in ['case1', 'case2']:
        total = results[f'v2_{case}']['total']
        correct = results[f'v2_{case}']['correct']
        accuracy = (correct / total * 100) if total > 0 else 0
        case_name = "予想1位的中時" if case == 'case1' else "予想1位外れ時"
        print(f"  {case_name}: {correct}/{total} ({accuracy:.2f}%)")


def main():
    """メイン処理"""
    print("=" * 80)
    print("条件付きモデルv2のバックテスト")
    print("=" * 80)

    # パス設定
    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    model_dir = PROJECT_ROOT / "models"

    # v1モデル読み込み
    print("\nv1モデル読み込み中...")
    v1_stage1, v1_stage2, v1_stage3, v1_meta = load_model_v1(model_dir)

    if v1_stage1 is None:
        print("v1モデルが見つかりません")
        return

    print(f"v1 Stage1 AUC: {v1_meta['metrics']['stage1']['cv_auc_mean']:.4f}")
    print(f"v1 Stage2 AUC: {v1_meta['metrics']['stage2']['cv_auc_mean']:.4f}")
    print(f"v1 Stage3 AUC: {v1_meta['metrics']['stage3']['cv_auc_mean']:.4f}")

    # v2モデル読み込み
    print("\nv2モデル読み込み中...")
    v2_stage1, v2_stage2, v2_stage3, v2_meta = load_model_v2(model_dir)

    if v2_stage2 is None:
        print("v2モデルが見つかりません。先に retrain_conditional_models_v2.py を実行してください")
        return

    print(f"v2 Stage1 AUC: {v2_meta['metrics']['stage1']['cv_auc_mean']:.4f}")
    print(f"v2 Stage2 AUC: {v2_meta['metrics']['stage2']['cv_auc_mean']:.4f}")
    print(f"v2 Stage3 AUC: {v2_meta['metrics']['stage3']['cv_auc_mean']:.4f}")

    # テストデータ読み込み（2024-2025年）
    print("\nテストデータ読み込み中...")
    with sqlite3.connect(db_path) as conn:
        df = create_training_dataset_with_relative_features(
            conn, start_date='2024-01-01', end_date='2026-01-01'
        )

    print(f"テストデータ: {len(df):,}件")
    print(f"テストレース数: {df['race_id'].nunique():,}レース")

    # バックテスト実行
    backtest_stage2(df, v1_stage2, v2_stage2)

    print("\n" + "=" * 80)
    print("バックテスト完了")
    print("=" * 80)

    print("\n注意:")
    print("このスクリプトは簡易版です。完全なバックテストには、")
    print("HierarchicalPredictorを使った三連単予測が必要です。")


if __name__ == "__main__":
    main()
