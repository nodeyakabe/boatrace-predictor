"""
機能フラグ管理

新機能のロールアウト制御とロールバック手順を提供。
段階的導入により、リスクを最小化する。
"""

# 機能フラグ設定
FEATURE_FLAGS = {
    # Phase 1: 実装完了・動作確認済み
    'dynamic_integration': True,      # 動的合成比
    'entry_prediction_model': True,   # 進入予測モデル
    'confidence_refinement': False,   # 信頼度細分化（未実装）
    'st_course_interaction': False,   # ST×course交互作用（未実装）

    # Phase 2: 未実装または動作未確認
    'lightgbm_ranking': False,        # LightGBMランキングモデル（未実装）
    'kelly_betting': False,           # Kelly基準投資戦略（未実装）
    'optuna_optimization': False,     # Optunaパラメータ最適化（予測時不要）
    'interaction_features': False,    # 交互作用特徴量（未実装）
    'auto_buff_learning': False,      # 複合バフ自動学習（未実装）
    'probability_calibration': False, # キャリブレーション（未実装）

    # Phase 3: 未実装または動作未確認
    'venue_specific_models': False,   # 会場別専用モデル（未実装）
    'hierarchical_predictor': False,  # 階層的条件確率モデル（未実装）
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
