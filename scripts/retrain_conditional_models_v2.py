"""
条件付きモデル改善版の学習スクリプト

問題: 既存のStage2/3モデルは実際の1位を条件として学習しているが、
      予測時は予想1位を条件として使うため、データ分布が一致しない

改善: 予想1位を条件とした学習データで再学習
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.train_conditional_models import ConditionalModelTrainer


def main():
    """メイン処理"""
    print("=" * 80)
    print("条件付きモデル改善版の学習")
    print("=" * 80)

    # パス設定
    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    model_dir = PROJECT_ROOT / "models"

    # トレーナー初期化
    trainer = ConditionalModelTrainer(str(db_path), str(model_dir))

    # 学習データ読み込み（2023年以前を学習用、2024-2025を検証用）
    print("\n学習データ読み込み中...")
    df = trainer.load_training_data(start_date='2020-01-01', end_date='2024-01-01')

    if len(df) == 0:
        print("ERROR: 学習データが見つかりません")
        return

    print(f"総データ数: {len(df):,}件")
    print(f"総レース数: {df['race_id'].nunique():,}レース")

    # Stage1モデル学習（変更なし）
    print("\n" + "=" * 80)
    print("Stage1モデル学習（1位予測）")
    print("=" * 80)
    X1, y1 = trainer.prepare_stage1_data(df)
    print(f"学習データサイズ: {len(X1):,}件")
    print(f"ポジティブ率: {y1.mean()*100:.2f}%（理論値: 16.67%）")

    stage1_model, stage1_metrics = trainer.train_xgboost(X1, y1, 'Stage1_v2')
    trainer.models['stage1'] = stage1_model
    trainer.feature_names['stage1'] = list(X1.columns)
    trainer.metrics['stage1'] = stage1_metrics

    print(f"\nStage1 CV AUC: {stage1_metrics['cv_auc_mean']:.4f} +/- {stage1_metrics['cv_auc_std']:.4f}")

    # Stage2モデル学習（改善版）
    print("\n" + "=" * 80)
    print("Stage2モデル学習（2位予測）- 改善版")
    print("=" * 80)
    print("変更点: 予想1位を条件として使用")

    X2, y2 = trainer.prepare_stage2_data_v2(df)
    print(f"学習データサイズ: {len(X2):,}件")
    print(f"ポジティブ率: {y2.mean()*100:.2f}%（理論値: 20.00%）")

    stage2_model, stage2_metrics = trainer.train_xgboost(X2, y2, 'Stage2_v2')
    trainer.models['stage2'] = stage2_model
    trainer.feature_names['stage2'] = list(X2.columns)
    trainer.metrics['stage2'] = stage2_metrics

    print(f"\nStage2 CV AUC: {stage2_metrics['cv_auc_mean']:.4f} +/- {stage2_metrics['cv_auc_std']:.4f}")

    # Stage3モデル学習（改善版）
    print("\n" + "=" * 80)
    print("Stage3モデル学習（3位予測）- 改善版")
    print("=" * 80)
    print("変更点: 予想1位・予想2位を条件として使用")

    X3, y3 = trainer.prepare_stage3_data_v2(df)
    print(f"学習データサイズ: {len(X3):,}件")
    print(f"ポジティブ率: {y3.mean()*100:.2f}%（理論値: 25.00%）")

    stage3_model, stage3_metrics = trainer.train_xgboost(X3, y3, 'Stage3_v2')
    trainer.models['stage3'] = stage3_model
    trainer.feature_names['stage3'] = list(X3.columns)
    trainer.metrics['stage3'] = stage3_metrics

    print(f"\nStage3 CV AUC: {stage3_metrics['cv_auc_mean']:.4f} +/- {stage3_metrics['cv_auc_std']:.4f}")

    # モデル保存
    print("\n" + "=" * 80)
    print("モデル保存")
    print("=" * 80)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # v2サフィックスをつけて保存
    import joblib
    import json

    model_dir.mkdir(exist_ok=True)

    # Stage1モデル
    stage1_path = model_dir / f"conditional_stage1_v2_{timestamp}.joblib"
    joblib.dump(stage1_model, stage1_path)
    print(f"Stage1モデル保存: {stage1_path}")

    # Stage2モデル
    stage2_path = model_dir / f"conditional_stage2_v2_{timestamp}.joblib"
    joblib.dump(stage2_model, stage2_path)
    print(f"Stage2モデル保存: {stage2_path}")

    # Stage3モデル
    stage3_path = model_dir / f"conditional_stage3_v2_{timestamp}.joblib"
    joblib.dump(stage3_model, stage3_path)
    print(f"Stage3モデル保存: {stage3_path}")

    # メタデータ保存
    meta = {
        'version': 'v2',
        'created_at': timestamp,
        'description': 'Improved conditional models using predicted first/second as conditions',
        'training_period': {
            'start': '2020-01-01',
            'end': '2024-01-01'
        },
        'features': {
            'stage1': trainer.feature_names['stage1'],
            'stage2': trainer.feature_names['stage2'],
            'stage3': trainer.feature_names['stage3'],
        },
        'metrics': {
            'stage1': {
                'cv_auc_mean': stage1_metrics['cv_auc_mean'],
                'cv_auc_std': stage1_metrics['cv_auc_std'],
            },
            'stage2': {
                'cv_auc_mean': stage2_metrics['cv_auc_mean'],
                'cv_auc_std': stage2_metrics['cv_auc_std'],
            },
            'stage3': {
                'cv_auc_mean': stage3_metrics['cv_auc_mean'],
                'cv_auc_std': stage3_metrics['cv_auc_std'],
            }
        },
        'improvements': {
            'stage2': 'Uses predicted first instead of actual first',
            'stage3': 'Uses predicted first and second instead of actual first and second'
        }
    }

    meta_path = model_dir / f"conditional_meta_v2_{timestamp}.json"
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"メタデータ保存: {meta_path}")

    # サマリー表示
    print("\n" + "=" * 80)
    print("学習完了サマリー")
    print("=" * 80)
    print(f"Stage1 AUC: {stage1_metrics['cv_auc_mean']:.4f}")
    print(f"Stage2 AUC: {stage2_metrics['cv_auc_mean']:.4f}")
    print(f"Stage3 AUC: {stage3_metrics['cv_auc_mean']:.4f}")

    print("\n次のステップ:")
    print("1. バックテストスクリプトで精度検証")
    print("2. 既存モデルとの比較")
    print("3. 改善効果の定量化")


if __name__ == "__main__":
    main()
