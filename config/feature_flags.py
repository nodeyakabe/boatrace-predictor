"""
機能フラグ管理

新機能のロールアウト制御とロールバック手順を提供。
段階的導入により、リスクを最小化する。

更新履歴:
- 2025-12-19: モンテカルロシミュレーション（アプローチ5）フラグ追加
- 2025-12-18: ペアワイズスコアリング（アプローチ3）フラグ追加
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
    'odds_calibration': False,               # 1着オッズ校正（効果なし、保留中）
    'rank23_odds_calibration': False,        # 2着・3着オッズ校正（2024年+2.04pt, 2025年±0.00pt → 不採用）
    'second_place_specialized': True,        # 2着専用スコアリングモデル（アプローチ2）
    'confidence_based_switching': True,       # 信頼度ベース戦略切り替え（アプローチ1）
    'pairwise_scoring': True,                 # ペアワイズ相対スコアリング（アプローチ3）2着+7.3pt, 3着+3.9pt
    'monte_carlo_simulation': False,          # モンテカルロシミュレーション（アプローチ5）不採用: 1着-8.5pt
    'motor_capsizing_penalty': True,           # モーター転覆履歴ペナルティ（2025-12-19追加）

    # === A・Bランク特別条件（2025-12-19追加） ===
    # サンプル数増加により統計的に有効と判断された条件
    'ab_rank_special_betting': True,           # A・Bランク特別条件での購入を有効化
    # 有効条件:
    # 1. Bランク × 50-100倍帯: ROI 512% (n=14)
    # 2. A+Bランク × 1コースB1級: ROI 154% (n=82)
    # 注意: Aランク全体(ROI 60%)、Bランク全体(ROI 74%)は赤字のため除外

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
    },
    'odds_calibration': {
        'risk_level': 'low',
        'main_risks': ['オッズデータ欠損時の処理', '市場確率の過信'],
        'mitigation': 'オッズなし時はスキップ、alpha=0.3で緩やかな補正',
        'expected_effect': '効果なし（1着予測は市場効率が高い）',
        'status': '保留中'
    },
    'rank23_odds_calibration': {
        'risk_level': 'low',
        'main_risks': ['オッズデータ欠損時の処理', '2着・3着順位の変動'],
        'mitigation': 'オッズなし時はスキップ、alpha=0.3で緩やかな統合',
        'expected_effect': '+2.0pt（三連単的中率改善）',
        'test_result': '2024年: +2.04pt（49レース）, 2025年: ±0.00pt（100レース）',
        'enabled_date': '2025-12-18',
        'disabled_date': '2025-12-18',  # モデルドリフトにより効果消失
        'status': '不採用 - 2025年データで効果なし'
    },
    'second_place_specialized': {
        'risk_level': 'low',
        'main_risks': ['モデル未学習時の処理', '2着順位の変動'],
        'mitigation': 'モデルなし時はスキップ、統合重み0.5で緩やかな適用',
        'expected_effect': '+6.0pt（2着的中率改善）',
        'test_result': '+6.8pt（432レース検証 2025-12-18）AUC=0.6819',
        'enabled_date': '2025-12-18'  # 実装日
    },
    'confidence_based_switching': {
        'risk_level': 'low',
        'main_risks': ['戦略切り替えによる予測変動', '閾値チューニングの必要性'],
        'mitigation': '段階的閾値（high=0.7, medium=0.5）で緩やかな切り替え',
        'expected_effect': '+2-3pt（2着・3着的中率改善）',
        'test_result': '検証中（アプローチ1: 信頼度ベース戦略切り替え）',
        'enabled_date': '2025-12-18'  # 実装日
    },
    'pairwise_scoring': {
        'risk_level': 'low',
        'main_risks': ['計算コスト増加', '既存スコアとの統合バランス'],
        'mitigation': 'integration_weight=0.5で緩やかな統合、モデルなし時はスキップ',
        'expected_effect': '+2-3pt（2着・3着的中率改善）',
        'test_result': '2着+7.3pt, 3着+3.9pt, ROI+1.7pt（482レース検証 2025-12-19）AUC=0.7351',
        'enabled_date': '2025-12-19'  # 検証完了
    },
    'monte_carlo_simulation': {
        'risk_level': 'medium',
        'main_risks': ['計算コスト増加（5000回シミュレーション）', '物理モデルの精度依存'],
        'mitigation': 'シミュレーション回数を調整可能、integration_weight=0.3で緩やかな統合',
        'expected_effect': '+3pt（2着・3着的中率改善、最高ポテンシャル）',
        'test_result': '検証中（アプローチ5: モンテカルロレースシミュレーション）',
        'enabled_date': '2025-12-19'  # 実装日
    },
    'motor_capsizing_penalty': {
        'risk_level': 'low',
        'main_risks': ['転覆データの不完全性（DB欠損）', '過度なペナルティによる予測変動'],
        'mitigation': '結果欠損からの推定、最大ペナルティ-5pt制限、リスクレベル別の段階的適用',
        'expected_effect': 'モーター性能低下の反映による予測精度向上',
        'test_result': '検証中',
        'enabled_date': '2025-12-19'
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
