# -*- coding: utf-8 -*-
"""
モデル設定統一ファイル

全てのモデル関連設定をここに集約することで:
- 設定の一元管理
- ハードコード防止
- 変更時の影響範囲明確化

作成日: 2025-12-15
"""

from typing import Dict, Any
from dataclasses import dataclass


# ==============================================================================
# 本番使用モデル設定
# ==============================================================================

PRODUCTION_MODEL = {
    'type': 'conditional_rank',
    'version': 'v1',
    'algorithm': 'lightgbm',
    'path': 'models',
    'files': {
        'stage1': 'conditional_stage1.joblib',
        'stage2': 'conditional_stage2.joblib',
        'stage3': 'conditional_stage3.joblib',
        'meta': 'conditional_meta.json',
    },
    'min_auc': {
        'stage1': 0.85,
        'stage2': 0.7423,  # 現行基準
        'stage3': 0.6675,  # 現行基準
    },
    'use_v2': False,  # HierarchicalPredictor用
}


# ==============================================================================
# モデル検証基準
# ==============================================================================

MODEL_VALIDATION_CRITERIA = {
    # AUC最低基準（これを下回ったら却下）
    'min_auc': {
        'stage1': 0.85,
        'stage2': 0.72,
        'stage3': 0.65,
    },
    # 改善閾値（これを上回ったら適用検討）
    'improvement_threshold': {
        'stage1': 0.01,  # +1pt
        'stage2': 0.01,  # +1pt
        'stage3': 0.01,  # +1pt
    },
    # 性能低下許容範囲（バックテスト）
    'max_performance_drop': {
        'roi': 0.02,       # ROI 2%以内の低下は許容
        'hit_rate': 0.01,  # 的中率 1%以内の低下は許容
    },
}


# ==============================================================================
# バックテスト基準
# ==============================================================================

BACKTEST_CRITERIA = {
    # 最低基準
    'min_roi': 1.00,           # 100%以上（元本割れしない）
    'min_hit_rate': 0.03,      # 3%以上
    'min_annual_profit': 0,    # 年間収支プラス

    # 現行基準（2025-12-15時点）
    'current_roi': 1.299,          # 129.9%
    'current_hit_rate': 0.092,     # 9.2%
    'current_annual_profit': 67570,  # +67,570円

    # テストデータ期間
    'test_period': {
        'start': '2025-01-01',
        'end': '2025-12-31',
    },
}


# ==============================================================================
# 学習パラメータ
# ==============================================================================

TRAINING_PARAMS = {
    'xgboost': {
        'objective': 'binary:logistic',
        'eval_metric': 'auc',
        'max_depth': 6,
        'learning_rate': 0.05,
        'n_estimators': 500,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'min_child_weight': 3,
        'gamma': 0.1,
        'random_state': 42,
        'n_jobs': -1,
        'use_label_encoder': False,
    },
    'lightgbm': {
        'objective': 'binary',
        'metric': 'auc',
        'boosting_type': 'gbdt',
        'num_leaves': 31,
        'learning_rate': 0.05,
        'n_estimators': 500,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'min_child_samples': 20,
        'random_state': 42,
        'n_jobs': -1,
        'verbose': -1,
    },
}


# ==============================================================================
# データ期間設定
# ==============================================================================

DATA_PERIOD = {
    'training': {
        'start': '2020-01-01',
        'end': '2025-12-31',
    },
    'validation_split': 0.2,  # 検証データ比率
    'cv_folds': 5,  # クロスバリデーション分割数
    'cv_method': 'TimeSeriesSplit',  # 時系列分割推奨
}


# ==============================================================================
# 特徴量設定
# ==============================================================================

FEATURE_CONFIG = {
    # Stage1基本特徴量
    'stage1_base': [
        'win_rate', 'second_rate', 'motor_second_rate', 'boat_second_rate',
        'exhibition_time', 'avg_st', 'actual_course',
    ],

    # 追加特徴量（相対特徴量）
    'relative_features': [
        'exh_rank', 'exh_diff', 'exh_zscore', 'exh_gap_to_best',
        'exh_relative_position', 'st_vs_expectation', 'st_rank',
        'st_diff', 'st_zscore', 'st_relative',
    ],

    # Stage2追加特徴量
    'stage2_winner_features': [
        'winner_win_rate', 'winner_second_rate', 'winner_motor_second_rate',
        'winner_boat_second_rate', 'winner_exhibition_time', 'winner_avg_st',
        'winner_actual_course',
    ],

    # 差分特徴量プレフィックス
    'diff_prefixes': ['diff_', 'gap_1st_2nd_'],
}


# ==============================================================================
# モデルパス生成ヘルパー
# ==============================================================================

def get_model_path(model_dir: str = 'models', version: str = 'v1') -> Dict[str, str]:
    """
    モデルファイルパスを取得

    Args:
        model_dir: モデルディレクトリ
        version: バージョン（'v1' or 'v2'）

    Returns:
        各ステージのファイルパス辞書
    """
    import os

    if version == 'v1':
        return {
            'stage1': os.path.join(model_dir, 'conditional_stage1.joblib'),
            'stage2': os.path.join(model_dir, 'conditional_stage2.joblib'),
            'stage3': os.path.join(model_dir, 'conditional_stage3.joblib'),
            'meta': os.path.join(model_dir, 'conditional_meta.json'),
        }
    else:
        # V2は最新ファイルを自動検索が必要
        from pathlib import Path
        model_path = Path(model_dir)
        v2_files = list(model_path.glob("conditional_stage2_v2_*.joblib"))

        if not v2_files:
            raise FileNotFoundError("V2モデルが見つかりません")

        latest = sorted(v2_files)[-1]
        parts = latest.stem.split('_')
        timestamp = '_'.join(parts[-2:])

        return {
            'stage1': os.path.join(model_dir, f'conditional_stage1_v2_{timestamp}.joblib'),
            'stage2': os.path.join(model_dir, f'conditional_stage2_v2_{timestamp}.joblib'),
            'stage3': os.path.join(model_dir, f'conditional_stage3_v2_{timestamp}.joblib'),
            'meta': os.path.join(model_dir, f'conditional_meta_v2_{timestamp}.json'),
        }


def get_current_auc() -> Dict[str, float]:
    """
    現在の本番モデルのAUCを取得

    Returns:
        {'stage1': auc, 'stage2': auc, 'stage3': auc}
    """
    import json
    import os

    meta_path = os.path.join(PRODUCTION_MODEL['path'], PRODUCTION_MODEL['files']['meta'])

    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        metrics = meta.get('metrics', {})
        return {
            'stage1': metrics.get('stage1', {}).get('cv_auc_mean', 0),
            'stage2': metrics.get('stage2', {}).get('cv_auc_mean', 0),
            'stage3': metrics.get('stage3', {}).get('cv_auc_mean', 0),
        }
    except Exception:
        return {
            'stage1': 0,
            'stage2': 0,
            'stage3': 0,
        }


def validate_new_model(new_meta_path: str) -> Dict[str, Any]:
    """
    新モデルの検証

    Args:
        new_meta_path: 新モデルのメタ情報ファイルパス

    Returns:
        検証結果辞書
    """
    import json

    result = {
        'valid': True,
        'errors': [],
        'warnings': [],
        'comparison': {},
    }

    try:
        with open(new_meta_path, 'r', encoding='utf-8') as f:
            new_meta = json.load(f)
    except Exception as e:
        result['valid'] = False
        result['errors'].append(f"メタファイル読み込みエラー: {e}")
        return result

    # 現在のAUCを取得
    current_auc = get_current_auc()

    # 新モデルのAUC
    new_metrics = new_meta.get('metrics', {})

    for stage in ['stage1', 'stage2', 'stage3']:
        new_auc = new_metrics.get(stage, {}).get('cv_auc_mean', 0)
        curr_auc = current_auc.get(stage, 0)
        min_auc = MODEL_VALIDATION_CRITERIA['min_auc'].get(stage, 0)

        result['comparison'][stage] = {
            'current': curr_auc,
            'new': new_auc,
            'diff': new_auc - curr_auc,
            'min': min_auc,
        }

        # 最低基準チェック
        if new_auc < min_auc:
            result['valid'] = False
            result['errors'].append(f"{stage}: AUC {new_auc:.4f} < 最低基準 {min_auc:.4f}")

        # 現行比較
        if new_auc < curr_auc:
            result['warnings'].append(f"{stage}: 現行AUC {curr_auc:.4f} より低下 ({new_auc:.4f})")

    return result


# ==============================================================================
# HierarchicalPredictor用設定
# ==============================================================================

HIERARCHICAL_PREDICTOR_CONFIG = {
    'use_v2': False,  # V1を使用（デフォルト）
    'use_optimized': True,  # 最適化版TrifectaCalculatorを使用
    'use_conditional_model': True,  # 条件付きモデルを使用
}


# ==============================================================================
# ベッティング設定（参照用）
# ==============================================================================

BETTING_CONFIG = {
    'strategy': 'B',  # 戦略B
    'multi_bet_pattern': 'PATTERN_H',
    'enable_venue_wind_filter': True,
    'enable_venue_course_adjustment': True,
    'default_bet_amount': 300,  # 1点買い時
    'pattern_h_amounts': {
        '1-2-3': 200,
        '1-2-4': 100,
        '1-2-5': 100,
    },
}


if __name__ == "__main__":
    # 設定確認
    print("=== 本番モデル設定 ===")
    print(f"バージョン: {PRODUCTION_MODEL['version']}")
    print(f"アルゴリズム: {PRODUCTION_MODEL['algorithm']}")
    print(f"最低AUC Stage2: {PRODUCTION_MODEL['min_auc']['stage2']}")

    print("\n=== 現在のAUC ===")
    current = get_current_auc()
    for stage, auc in current.items():
        print(f"{stage}: {auc:.4f}")

    print("\n=== モデルパス ===")
    paths = get_model_path('models', 'v1')
    for key, path in paths.items():
        print(f"{key}: {path}")
