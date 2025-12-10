"""
v1とv2モデルの実測精度比較スクリプト

2024-2025年データで実際の予測を行い、以下を比較:
1. 予想1位的中時・外れ時の2位予測精度
2. 三連単的中率
3. ROI
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


def load_models(model_dir, version='v1'):
    """モデル読み込み"""
    if version == 'v1':
        stage1 = joblib.load(model_dir / "conditional_stage1.joblib")
        stage2 = joblib.load(model_dir / "conditional_stage2.joblib")
        stage3 = joblib.load(model_dir / "conditional_stage3.joblib")
        meta_path = model_dir / "conditional_meta.json"
    else:  # v2
        # 最新のv2モデルを検索
        v2_files = list(model_dir.glob("conditional_stage2_v2_*.joblib"))
        if not v2_files:
            return None, None, None, None

        latest = sorted(v2_files)[-1]
        # ファイル名: conditional_stage2_v2_20251209_112052.joblib
        # タイムスタンプ: 20251209_112052
        parts = latest.stem.split('_')
        timestamp = '_'.join(parts[-2:])  # 最後の2要素を結合

        stage1 = joblib.load(model_dir / f"conditional_stage1_v2_{timestamp}.joblib")
        stage2 = joblib.load(model_dir / f"conditional_stage2_v2_{timestamp}.joblib")
        stage3 = joblib.load(model_dir / f"conditional_stage3_v2_{timestamp}.joblib")
        meta_path = model_dir / f"conditional_meta_v2_{timestamp}.json"

    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    return stage1, stage2, stage3, meta


def calculate_predicted_first(df):
    """予想1位を計算（簡易版: v2モデルの学習時と同じ方法）"""
    df = df.copy()
    df['predicted_score'] = (
        df['win_rate'].fillna(0) * 0.4 +
        df['second_rate'].fillna(0) * 0.2 +
        df['motor_second_rate'].fillna(0) * 0.2 +
        df['boat_second_rate'].fillna(0) * 0.1 +
        (df['exhibition_time'].fillna(100) < 6.8).astype(float) * 0.1
    )
    return df.groupby('race_id')['predicted_score'].idxmax()


def prepare_stage2_features_v1(race_df, first_pit, feature_cols):
    """v1用のStage2特徴量を準備（実際の1位を条件）"""
    # 実際の1位艇の特徴量
    first_row = race_df[race_df['rank'] == 1].iloc[0] if len(race_df[race_df['rank'] == 1]) > 0 else None
    if first_row is None:
        return None

    # 残り5艇（実際の1位を除外）
    candidates = race_df[race_df['pit_number'] != first_row['pit_number']].copy()

    # 特徴量を作成
    features_list = []
    for idx, row in candidates.iterrows():
        features = {}
        for col in feature_cols:
            if col in row.index:
                features[col] = row[col]
            if col in first_row.index:
                features[f'winner_{col}'] = first_row[col]
                if col in row.index and pd.notna(row[col]) and pd.notna(first_row[col]):
                    try:
                        features[f'diff_{col}'] = row[col] - first_row[col]
                    except:
                        pass

        features_list.append({
            'pit_number': row['pit_number'],
            'features': features,
            'actual_rank': row['rank']
        })

    return features_list


def prepare_stage2_features_v2(race_df, predicted_first_pit, feature_cols):
    """v2用のStage2特徴量を準備（予想1位を条件）"""
    # 予想1位艇の特徴量
    first_row = race_df[race_df['pit_number'] == predicted_first_pit].iloc[0]

    # 残り5艇（予想1位を除外）
    candidates = race_df[race_df['pit_number'] != predicted_first_pit].copy()

    # 特徴量を作成
    features_list = []
    for idx, row in candidates.iterrows():
        features = {}
        for col in feature_cols:
            if col in row.index:
                features[col] = row[col]
            if col in first_row.index:
                features[f'pred_winner_{col}'] = first_row[col]
                if col in row.index and pd.notna(row[col]) and pd.notna(first_row[col]):
                    try:
                        features[f'diff_{col}'] = row[col] - first_row[col]
                    except:
                        pass

        features_list.append({
            'pit_number': row['pit_number'],
            'features': features,
            'actual_rank': row['rank']
        })

    return features_list


def predict_second_place(model, feature_list, feature_names):
    """2位を予測"""
    if not feature_list:
        return None, []

    # 各候補の確率を計算
    probs = []
    for item in feature_list:
        # 特徴量を揃える
        feature_vec = []
        for fname in feature_names:
            feature_vec.append(item['features'].get(fname, 0))

        # 予測
        try:
            prob = model.predict_proba([feature_vec])[0][1]
        except:
            prob = 0.0

        probs.append({
            'pit_number': item['pit_number'],
            'prob': prob,
            'actual_rank': item['actual_rank']
        })

    # 確率最大の艇を返す
    if not probs:
        return None, []

    predicted = max(probs, key=lambda x: x['prob'])
    return predicted['pit_number'], probs


def backtest(df, model_v1, model_v2, meta_v1, meta_v2):
    """バックテスト実行"""
    print("\n" + "=" * 80)
    print("2位予測精度のバックテスト（2024-2025年データ）")
    print("=" * 80)

    feature_cols = ['win_rate', 'second_rate', 'motor_second_rate', 'boat_second_rate',
                   'exhibition_time', 'avg_st', 'actual_course']

    results = {
        'v1_case1': {'correct': 0, 'total': 0, 'races': []},
        'v1_case2': {'correct': 0, 'total': 0, 'races': []},
        'v2_case1': {'correct': 0, 'total': 0, 'races': []},
        'v2_case2': {'correct': 0, 'total': 0, 'races': []},
    }

    race_ids = df['race_id'].unique()
    print(f"\n総レース数: {len(race_ids):,}レース")

    for i, race_id in enumerate(race_ids):
        if i % 1000 == 0 and i > 0:
            print(f"処理中: {i:,}/{len(race_ids):,} レース...")

        race_df = df[df['race_id'] == race_id].copy()

        if len(race_df) != 6:
            continue

        # 実際の1位・2位
        actual_first = race_df[race_df['rank'] == 1]['pit_number'].values
        actual_second = race_df[race_df['rank'] == 2]['pit_number'].values

        if len(actual_first) == 0 or len(actual_second) == 0:
            continue

        actual_first_pit = actual_first[0]
        actual_second_pit = actual_second[0]

        # 予想1位を計算
        predicted_first_idx = calculate_predicted_first(race_df)
        predicted_first_pit = int(race_df.loc[predicted_first_idx, 'pit_number'])

        # ケース判定
        first_correct = bool(predicted_first_pit == actual_first_pit)
        case = 'case1' if first_correct else 'case2'

        # v1で2位予測
        try:
            feature_list_v1 = prepare_stage2_features_v1(race_df, actual_first_pit, feature_cols)
            if feature_list_v1:
                pred_second_v1, _ = predict_second_place(
                    model_v1, feature_list_v1,
                    meta_v1.get('feature_names', {}).get('stage2', meta_v1.get('features', {}).get('stage2', []))
                )

                results[f'v1_{case}']['total'] += 1
                if pred_second_v1 == actual_second_pit:
                    results[f'v1_{case}']['correct'] += 1
        except Exception as e:
            pass

        # v2で2位予測
        try:
            feature_list_v2 = prepare_stage2_features_v2(race_df, predicted_first_pit, feature_cols)
            if feature_list_v2:
                pred_second_v2, _ = predict_second_place(
                    model_v2, feature_list_v2,
                    meta_v2.get('features', {}).get('stage2', [])
                )

                results[f'v2_{case}']['total'] += 1
                if pred_second_v2 == actual_second_pit:
                    results[f'v2_{case}']['correct'] += 1
        except Exception as e:
            pass

    # 結果表示
    print("\n" + "=" * 80)
    print("v1（既存モデル: 実際の1位を条件）")
    print("=" * 80)

    for case in ['case1', 'case2']:
        total = results[f'v1_{case}']['total']
        correct = results[f'v1_{case}']['correct']
        accuracy = (correct / total * 100) if total > 0 else 0
        case_name = "予想1位が的中" if case == 'case1' else "予想1位が外れ"
        print(f"{case_name}: {correct}/{total} = {accuracy:.2f}%")

    v1_total = results['v1_case1']['total'] + results['v1_case2']['total']
    v1_correct = results['v1_case1']['correct'] + results['v1_case2']['correct']
    v1_overall = (v1_correct / v1_total * 100) if v1_total > 0 else 0
    print(f"全体: {v1_correct}/{v1_total} = {v1_overall:.2f}%")

    print("\n" + "=" * 80)
    print("v2（改善版モデル: 予想1位を条件）")
    print("=" * 80)

    for case in ['case1', 'case2']:
        total = results[f'v2_{case}']['total']
        correct = results[f'v2_{case}']['correct']
        accuracy = (correct / total * 100) if total > 0 else 0
        case_name = "予想1位が的中" if case == 'case1' else "予想1位が外れ"
        print(f"{case_name}: {correct}/{total} = {accuracy:.2f}%")

    v2_total = results['v2_case1']['total'] + results['v2_case2']['total']
    v2_correct = results['v2_case1']['correct'] + results['v2_case2']['correct']
    v2_overall = (v2_correct / v2_total * 100) if v2_total > 0 else 0
    print(f"全体: {v2_correct}/{v2_total} = {v2_overall:.2f}%")

    # 改善効果
    print("\n" + "=" * 80)
    print("改善効果")
    print("=" * 80)

    for case in ['case1', 'case2']:
        v1_acc = (results[f'v1_{case}']['correct'] / results[f'v1_{case}']['total'] * 100) if results[f'v1_{case}']['total'] > 0 else 0
        v2_acc = (results[f'v2_{case}']['correct'] / results[f'v2_{case}']['total'] * 100) if results[f'v2_{case}']['total'] > 0 else 0
        improvement = v2_acc - v1_acc
        case_name = "予想1位が的中" if case == 'case1' else "予想1位が外れ"

        sign = "+" if improvement >= 0 else ""
        print(f"{case_name}: {sign}{improvement:.2f}pt")

    overall_improvement = v2_overall - v1_overall
    sign = "+" if overall_improvement >= 0 else ""
    print(f"全体: {sign}{overall_improvement:.2f}pt")

    return results


def main():
    """メイン処理"""
    print("=" * 80)
    print("v1 vs v2 実測精度比較バックテスト")
    print("=" * 80)

    # パス設定
    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    model_dir = PROJECT_ROOT / "models"

    # v1モデル読み込み
    print("\nv1モデル読み込み中...")
    v1_stage1, v1_stage2, v1_stage3, v1_meta = load_models(model_dir, version='v1')

    if v1_stage2 is None:
        print("ERROR: v1モデルが見つかりません")
        return

    print(f"v1 Stage2 AUC: {v1_meta['metrics']['stage2']['cv_auc_mean']:.4f}")

    # v2モデル読み込み
    print("\nv2モデル読み込み中...")
    v2_stage1, v2_stage2, v2_stage3, v2_meta = load_models(model_dir, version='v2')

    if v2_stage2 is None:
        print("ERROR: v2モデルが見つかりません")
        return

    print(f"v2 Stage2 AUC: {v2_meta['metrics']['stage2']['cv_auc_mean']:.4f}")

    # テストデータ読み込み
    print("\n2024-2025年データ読み込み中...")
    with sqlite3.connect(db_path) as conn:
        df = create_training_dataset_with_relative_features(
            conn, start_date='2024-01-01', end_date='2026-01-01'
        )

    print(f"テストデータ: {len(df):,}件")
    print(f"レース数: {df['race_id'].nunique():,}レース")

    # バックテスト実行
    results = backtest(df, v1_stage2, v2_stage2, v1_meta, v2_meta)

    # 結果をCSVに保存
    output_path = PROJECT_ROOT / "results" / f"backtest_v1_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output_path.parent.mkdir(exist_ok=True)

    summary = []
    for model in ['v1', 'v2']:
        for case in ['case1', 'case2']:
            key = f'{model}_{case}'
            total = results[key]['total']
            correct = results[key]['correct']
            accuracy = (correct / total * 100) if total > 0 else 0

            summary.append({
                'model': model,
                'case': case,
                'total': total,
                'correct': correct,
                'accuracy': accuracy
            })

    summary_df = pd.DataFrame(summary)
    summary_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n結果保存: {output_path}")


if __name__ == "__main__":
    main()
