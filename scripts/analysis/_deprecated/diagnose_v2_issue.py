# -*- coding: utf-8 -*-
"""
V2モデル劣化問題の診断スクリプト
"""
import sys
from pathlib import Path
import json

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

def diagnose_model_files():
    """モデルファイルの状況を診断"""
    print("=" * 80)
    print("V2モデル劣化問題 - 診断レポート")
    print("=" * 80)

    models_dir = ROOT_DIR / 'models'

    # 体系A: LightGBM (.joblib)
    print("\n## 体系A: LightGBM (.joblib) - TrifectaCalculator系が使用")
    print("-" * 60)

    # V1
    v1_meta_path = models_dir / 'conditional_meta.json'
    if v1_meta_path.exists():
        with open(v1_meta_path, 'r', encoding='utf-8') as f:
            v1_meta = json.load(f)
        print("\n### 体系A V1 (conditional_meta.json)")
        print(f"作成日: {v1_meta.get('created_at', 'N/A')}")
        metrics = v1_meta.get('metrics', {})
        print(f"Stage1 AUC: {metrics.get('stage1', {}).get('cv_auc_mean', 'N/A'):.4f}")
        print(f"Stage2 AUC: {metrics.get('stage2', {}).get('cv_auc_mean', 'N/A'):.4f}")
        print(f"Stage3 AUC: {metrics.get('stage3', {}).get('cv_auc_mean', 'N/A'):.4f}")
        features = v1_meta.get('feature_names', v1_meta.get('features', {}))
        if isinstance(features, dict):
            print(f"特徴量数: S1={len(features.get('stage1', []))}, S2={len(features.get('stage2', []))}, S3={len(features.get('stage3', []))}")

    # V2
    v2_meta_path = models_dir / 'conditional_meta_v2_20251209_112052.json'
    if v2_meta_path.exists():
        with open(v2_meta_path, 'r', encoding='utf-8') as f:
            v2_meta = json.load(f)
        print("\n### 体系A V2 (conditional_meta_v2_20251209_112052.json)")
        print(f"作成日: {v2_meta.get('created_at', 'N/A')}")
        metrics = v2_meta.get('metrics', {})
        print(f"Stage1 AUC: {metrics.get('stage1', {}).get('cv_auc_mean', 'N/A'):.4f}")
        print(f"Stage2 AUC: {metrics.get('stage2', {}).get('cv_auc_mean', 'N/A'):.4f}")
        print(f"Stage3 AUC: {metrics.get('stage3', {}).get('cv_auc_mean', 'N/A'):.4f}")
        features = v2_meta.get('features', {})
        if isinstance(features, dict):
            print(f"特徴量数: S1={len(features.get('stage1', []))}, S2={len(features.get('stage2', []))}, S3={len(features.get('stage3', []))}")

    # 体系B: XGBoost (.json)
    print("\n\n## 体系B: XGBoost (.json) - ConditionalRankModel系")
    print("-" * 60)

    # V1
    v1_rank_meta = models_dir / 'conditional_rank_v1.meta.json'
    if v1_rank_meta.exists():
        with open(v1_rank_meta, 'r', encoding='utf-8') as f:
            v1_rank = json.load(f)
        print("\n### 体系B V1 (conditional_rank_v1.meta.json)")
        print(f"作成日: {v1_rank.get('created_at', 'N/A')}")
        print(f"特徴量数: S1={len(v1_rank.get('feature_names', []))}, S2={len(v1_rank.get('second_feature_names', []))}, S3={len(v1_rank.get('third_feature_names', []))}")

    # V2
    v2_rank_meta = models_dir / 'conditional_rank_v2_20251215.meta.json'
    if v2_rank_meta.exists():
        with open(v2_rank_meta, 'r', encoding='utf-8') as f:
            v2_rank = json.load(f)
        print("\n### 体系B V2 (conditional_rank_v2_20251215.meta.json)")
        print(f"作成日: {v2_rank.get('created_at', 'N/A')}")
        print(f"特徴量数: S1={len(v2_rank.get('feature_names', []))}, S2={len(v2_rank.get('second_feature_names', []))}, S3={len(v2_rank.get('third_feature_names', []))}")

    # 問題の分析
    print("\n\n" + "=" * 80)
    print("## 問題の分析")
    print("=" * 80)

    print("""
【根本原因】
TrifectaCalculator / TrifectaCalculatorOptimized は use_v2=True の場合、
「体系A V2」(conditional_stage*_v2_20251209_112052.joblib) を読み込みます。

しかし、この体系A V2は元のV1よりAUCが低下しています:
- Stage2 AUC: 0.7423 → 0.6935 (-4.9pt)
- Stage3 AUC: 0.6675 → 0.6278 (-4.0pt)

一方で、「体系B V2」(conditional_rank_v2_20251215_*.json) は
ConditionalRankModel クラス専用であり、HierarchicalPredictor では使用されていません。

【結論】
比較スクリプトで「V1 vs V2」を比較する際:
- V1 → 体系A V1 (AUC高い)
- V2 → 体系A V2 (AUC低い)

これにより、V2が大幅に劣化して見えるのは当然の結果です。
体系A V2自体のAUCが既に低いからです。

【推奨対策】
1. 体系A V2のモデルを削除するか、V1に戻す
2. または、体系B V2をTrifectaCalculatorで使えるように統合する
3. 最もシンプルな解決策: use_v2=False をデフォルトにして、体系A V1を使用する
""")


def check_current_settings():
    """現在の設定を確認"""
    print("\n\n" + "=" * 80)
    print("## 現在の実行時設定の確認")
    print("=" * 80)

    # HierarchicalPredictorのデフォルト値
    print("""
HierarchicalPredictor のデフォルト:
- use_v2=False (V1モデルを使用)
- use_optimized=True (TrifectaCalculatorOptimizedを使用)

compare_model_versions.py:
- V1評価時: use_v2=False → 体系A V1
- V2評価時: use_v2=True → 体系A V2 (これが低AUCモデル)
""")


if __name__ == '__main__':
    diagnose_model_files()
    check_current_settings()
