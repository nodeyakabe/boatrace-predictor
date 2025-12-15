"""
機能フラグ管理

新機能のロールアウト制御とロールバック手順を提供。
段階的導入により、リスクを最小化する。

更新履歴:
- 2025-12-15: フラグ整理（27個→12個）、重複加算バグ修正用フラグ追加
"""

# ============================================================
# 有効な機能フラグ（実績あり・本番運用中）
# ============================================================
FEATURE_FLAGS = {
    # === コア機能（常時有効） ===
    'before_pattern_bonus': True,     # パターン方式（検証結果: 信頼度B +9.5pt, C +8.3pt）
    'negative_patterns': True,        # ネガティブパターン（+2.0%改善 2025-12-11）
    'entry_prediction_model': True,   # 進入予測モデル
    'hierarchical_predictor': True,   # 階層的条件確率モデル
    'lightgbm_ranking': True,         # LightGBMランキングモデル
    'interaction_features': True,     # 交互作用特徴量
    'st_course_interaction': True,    # ST×course交互作用

    # === バグ修正用フラグ（2025-12-15追加） ===
    # 重複加算を避けるため、レガシー機能はデフォルト無効
    'legacy_exhibition_adjustment': False,  # 旧展示補正（ExtendedScorerと重複するため無効）

    # === オプション機能（必要時に有効化） ===
    'apply_pattern_to_confidence_d': False,  # 信頼度Dへのパターン適用
    'venue_pattern_optimization': False,     # 会場別パターン最適化
    'compound_pattern_bonus': False,         # 複合パターンボーナス（ROI+11%のみ）

    # === デバッグ用 ===
    'verbose_logging': False,         # 詳細ログ出力
}

# ============================================================
# アーカイブ済みフラグ（削除予定・参照用に残す）
# ============================================================
ARCHIVED_FLAGS = {
    # 以下は検証の結果、効果なしまたは悪化のため無効化済み
    # コード内での参照がなくなり次第削除予定
    'beforeinfo_flag_adjustment': False,      # -3.65%悪化
    'hierarchical_before_prediction': False,  # -0.5%悪化
    'normalized_before_integration': False,   # -0.5%悪化
    'dynamic_integration': False,             # 逆相関
    'gated_before_integration': False,        # 効果なし
    'before_safe_integration': False,         # 効果なし
    'before_safe_st_exhibition': False,       # 悪化
    'optimized_pattern_multipliers': False,   # 効果なし
    'confidence_refinement': False,           # 未実装
    'kelly_betting': False,                   # 未実装
    'optuna_optimization': False,             # 予測時不要
    'auto_buff_learning': False,              # 未実装
    'probability_calibration': False,         # 未実装
    'venue_specific_models': False,           # 未実装
    'shap_explainability': False,             # 予測時不要
    'bayesian_hierarchical': False,           # 未実装
    'reinforcement_learning': False,          # 未実装
    'prediction_engine_v2': False,            # 実験的
    'preset_based_adjustment': False,         # 実験的
    'adjustment_tracing': False,              # 実験的
    'validation_mode': False,                 # デバッグ用
}


def is_feature_enabled(feature_name: str) -> bool:
    """
    機能が有効かどうかを判定

    Args:
        feature_name: 機能名

    Returns:
        機能が有効な場合True
    """
    # メインフラグを優先、なければアーカイブを参照（後方互換性維持）
    if feature_name in FEATURE_FLAGS:
        return FEATURE_FLAGS[feature_name]
    return ARCHIVED_FLAGS.get(feature_name, False)


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
