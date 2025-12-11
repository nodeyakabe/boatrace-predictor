"""
機能フラグ管理

新機能のロールアウト制御とロールバック手順を提供。
段階的導入により、リスクを最小化する。
"""

# 機能フラグ設定
FEATURE_FLAGS = {
    # Phase 1: 実装完了・動作確認済み
    'beforeinfo_flag_adjustment': False,  # 状態フラグ方式（検証結果: 1着的中率-3.65%悪化のためロールバック）
    'hierarchical_before_prediction': False,  # 階層的予測（検証結果: 1着的中率-0.5%悪化のためロールバック）
    'normalized_before_integration': False,  # 正規化統合（検証結果: 1着的中率-0.5%悪化のためロールバック）
    'dynamic_integration': False,     # 動的合成比（BEFORE_SCORE停止中 - 逆相関のため）
    'gated_before_integration': False,  # ゲーティング方式（PRE拮抗時のみBEFORE使用）
    'before_safe_integration': False,  # BEFORE_SAFE統合（安全版直前情報統合、正規化統合に置き換え）
    'before_safe_st_exhibition': False,  # BEFORE_SAFEにST/展示タイム統合（Phase 5テスト結果: 悪化、無効化）
    'before_pattern_bonus': True,     # パターン方式（検証結果: 信頼度B +9.5pt, C +8.3pt, A -6.5pt）
    'apply_pattern_to_confidence_d': False,  # 信頼度Dへのパターン適用（効果限定的+3.9pt、慎重モード）
    'negative_patterns': True,        # ネガティブパターン（Phase 2: 軽量実装、テスト結果+2.0%改善で有効化 2025-12-11）
    'venue_pattern_optimization': False,  # 会場別パターン最適化（Phase 3: テスト結果効果なし、無効維持）
    'compound_pattern_bonus': False,  # 複合パターンボーナス（Phase 3: テスト結果ROI+11%、的中率変化なし）
    'optimized_pattern_multipliers': False,  # 最適化パターン倍率（Phase 3: テスト中、200レース実績ベース）
    'entry_prediction_model': True,   # 進入予測モデル
    'confidence_refinement': False,   # 信頼度細分化（未実装）
    'st_course_interaction': True,    # ST×course交互作用（実装完了・再訓練済み）

    # Phase 2: 再訓練完了・有効化
    'lightgbm_ranking': True,         # LightGBMランキングモデル（再訓練完了）
    'kelly_betting': False,           # Kelly基準投資戦略（未実装）
    'optuna_optimization': False,     # Optunaパラメータ最適化（予測時不要）
    'interaction_features': True,     # 交互作用特徴量（再訓練完了）
    'auto_buff_learning': False,      # 複合バフ自動学習（未実装）
    'probability_calibration': False, # キャリブレーション（未実装）

    # Phase 3: 再訓練完了・有効化
    'venue_specific_models': False,   # 会場別専用モデル（未実装）
    'hierarchical_predictor': True,   # 階層的条件確率モデル（再訓練完了）
    'shap_explainability': False,     # SHAP説明可能性（予測時不要）
    'bayesian_hierarchical': False,   # ベイズ階層モデル（未実装）
    'reinforcement_learning': False,  # 強化学習最適化（未実装）

    # デバッグ・テスト用
    'verbose_logging': False,         # 詳細ログ出力
    'validation_mode': False,         # 検証モード（過去データで検証）
}


def is_feature_enabled(feature_name: str) -> bool:
    """
    機能が有効かどうかを判定

    Args:
        feature_name: 機能名

    Returns:
        機能が有効な場合True
    """
    return FEATURE_FLAGS.get(feature_name, False)


def enable_feature(feature_name: str):
    """
    機能を有効化

    Args:
        feature_name: 機能名
    """
    if feature_name in FEATURE_FLAGS:
        FEATURE_FLAGS[feature_name] = True


def disable_feature(feature_name: str):
    """
    機能を無効化

    Args:
        feature_name: 機能名
    """
    if feature_name in FEATURE_FLAGS:
        FEATURE_FLAGS[feature_name] = False


def set_feature_flag(feature_name: str, enabled: bool):
    """
    機能フラグを設定

    Args:
        feature_name: 機能名
        enabled: 有効/無効のフラグ
    """
    if feature_name in FEATURE_FLAGS:
        FEATURE_FLAGS[feature_name] = enabled


def get_all_features() -> dict:
    """
    全機能の状態を取得

    Returns:
        機能名と状態の辞書
    """
    return FEATURE_FLAGS.copy()


def get_enabled_features() -> list:
    """
    有効な機能のリストを取得

    Returns:
        有効な機能名のリスト
    """
    return [name for name, enabled in FEATURE_FLAGS.items() if enabled]


# 段階的ロールアウト設定
ROLLOUT_STAGES = {
    'stage1_dev': {
        'description': '開発環境でテスト',
        'duration_days': 7,
        'features': []  # 全機能をテスト可能
    },
    'stage2_backtest': {
        'description': 'バックテストで検証',
        'duration_days': 7,
        'features': []  # 過去データで検証
    },
    'stage3_trial_10pct': {
        'description': '本番環境の10%で試験運用',
        'duration_days': 7,
        'sample_rate': 0.1,
        'features': []
    },
    'stage4_trial_50pct': {
        'description': '本番環境の50%に拡大',
        'duration_days': 7,
        'sample_rate': 0.5,
        'features': []
    },
    'stage5_full_rollout': {
        'description': '全体展開',
        'sample_rate': 1.0,
        'features': []
    }
}


# 各機能のリスク評価
FEATURE_RISKS = {
    'negative_patterns': {
        'risk_level': 'low',
        'main_risks': ['過度なスコア減算による予測変更'],
        'mitigation': '段階的導入、モニタリング、ロールバック可能',
        'test_result': '+2.0%改善（50レーステスト 2025-12-11）',
        'enabled_date': '2025-12-11'
    },
    'dynamic_integration': {
        'risk_level': 'medium',
        'main_risks': ['過補正による精度低下'],
        'mitigation': '段階的導入、モニタリング'
    },
    'entry_prediction_model': {
        'risk_level': 'low',
        'main_risks': ['データ不足時の不安定性'],
        'mitigation': 'ベイズ更新で安定化'
    },
    'confidence_refinement': {
        'risk_level': 'low',
        'main_risks': ['UI変更の影響'],
        'mitigation': '後方互換性維持'
    },
    'auto_buff_learning': {
        'risk_level': 'medium',
        'main_risks': ['過学習'],
        'mitigation': '正則化、検証セット分離'
    },
    'probability_calibration': {
        'risk_level': 'medium',
        'main_risks': ['過去データへの過剰適合'],
        'mitigation': '時系列考慮、ウィンドウ制限'
    },
    'bayesian_hierarchical': {
        'risk_level': 'high',
        'main_risks': ['実装複雑', '計算コスト'],
        'mitigation': '段階的導入、キャッシュ活用'
    },
    'reinforcement_learning': {
        'risk_level': 'high',
        'main_risks': ['学習不安定', '実環境との乖離'],
        'mitigation': 'シミュレーション環境構築'
    }
}


def get_feature_risk(feature_name: str) -> dict:
    """
    機能のリスク情報を取得

    Args:
        feature_name: 機能名

    Returns:
        リスク情報の辞書
    """
    return FEATURE_RISKS.get(feature_name, {
        'risk_level': 'unknown',
        'main_risks': [],
        'mitigation': 'N/A'
    })
