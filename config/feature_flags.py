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
    'pairwise_scoring': False,                # ペアワイズ相対スコアリング（アプローチ3）2着+7.3pt, 3着+3.9pt - 一時無効化（バグ修正中）
    'monte_carlo_simulation': False,          # モンテカルロシミュレーション（アプローチ5）不採用: 1着-8.5pt
    'motor_capsizing_penalty': True,           # モーター転覆履歴ペナルティ（2025-12-19追加）
    'kimarite_flow_prediction': True,          # 決まり手別展開予測 - 有効化（5%調整で+4.1pt効果、2025-12-20全件検証確認）
    'forward_mover_filter': False,             # 前付け常習者除外フィルター - 無効化（ab_rank ONで-7.6pt悪化のため）
    'negative_pattern_filter': True,           # ネガティブパターンフィルター（Opus分析 2025-12-21）4年間安定マイナスROIパターン除外
    'upset_pattern_filter': True,              # ポジティブフィルター（穴狙い）オッズ30-100倍×予測1着5コース（安定ROI+10%以上）
    'third_place_specialized_scorer': False,   # 3着専用スコアラー - 無効化（RacePredictor未統合、効果なし）
    'condition_factor': False,                 # 選手調子係数（直近20走）不採用: -9.5pt悪化（2025-12-20検証）
    'makuri_risk_adjustment': True,            # まくりリスク評価 - 有効化（5%調整で+4.1pt効果、2025-12-20全件検証確認）

    # === C,D予想精度向上（2026-01-08追加） ===
    'score_gap_confidence': True,              # スコア差ベースの信頼度判定（混戦レースをC,Dとして適切に分類）

    # === 展開指標スコアリング（2026-01-09追加） ===
    'escape_rate_scoring': False,              # 逃げ率スコアリング - 不採用（500レース検証で効果なし）
    'venue_attack_scoring': False,             # 会場攻撃率スコアリング - 不採用（840レース検証で効果なし、Z=0.00）

    # === A・Bランク特別条件（2025-12-19追加） ===
    # サンプル数増加により統計的に有効と判断された条件
    'ab_rank_special_betting': True,           # A・Bランク特別条件での購入を有効化（+17.2pt効果確認済み）
    # 有効条件:
    # 1. Bランク × 50-100倍帯: ROI 512% (n=14)
    # 2. A+Bランク × 1コースB1級: ROI 154% (n=82)
    # 注意: Aランク全体(ROI 60%)、Bランク全体(ROI 74%)は赤字のため除外

    # === 2025-12-23追加: 6年間安定条件 ===
    'b_rank_30_50_b1': True,                   # B×30-50倍×B1級（6年ROI 101.4%、年間約190件追加）
    'c_rank_paper_trade': False,               # C×30-50倍×A2級（6年ROI 119%）ペーパートレード中、本番は無効

    # === 2026-02-13追加: 潮位データ活用 ===
    'tide_adjustment': False,                  # 潮位補正（rdmdb_tide活用、7会場100%データあり）検証中 - OFF比較テスト実施

    # === 2026-02-16追加: TJ-9展示タイム信頼性マップ ===
    'exhibition_reliability_adjustment': False,  # 会場別展示タイム信頼性係数 - 不採用（ROI±0.0pt～-1.2pt、効果なし）

    # === デバッグ用 ===
    'verbose_logging': False,         # 詳細ログ出力
}

# ============================================================
# アーカイブ済みフラグ - 削除完了（2025-12-22）
# ============================================================
# 以下のフラグは検証の結果、効果なしまたは悪化のため削除されました。
# 詳細は docs/CONFIG_CLEANUP_PLAN_20251222.md 参照
# - beforeinfo_flag_adjustment: -3.65%悪化
# - hierarchical_before_prediction: -0.5%悪化
# - normalized_before_integration: -0.5%悪化
# - dynamic_integration: 逆相関
# - gated_before_integration: 効果なし
# - before_safe_integration: 効果なし
# - before_safe_st_exhibition: 悪化
# - optimized_pattern_multipliers: 効果なし
# - confidence_refinement: 未実装
# - kelly_betting: 未実装
# - optuna_optimization: 予測時不要
# - auto_buff_learning: 未実装
# - probability_calibration: 未実装
# - venue_specific_models: 未実装
# - shap_explainability: 予測時不要
# - bayesian_hierarchical: 未実装
# - reinforcement_learning: 未実装
# - prediction_engine_v2: 実験的
# - preset_based_adjustment: 実験的
# - adjustment_tracing: 実験的
# - validation_mode: デバッグ用


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
    },
    'forward_mover_filter': {
        'risk_level': 'low',
        'main_risks': ['購入機会損失（約5.4%のレースが除外）', '前付け常習者リストの陳腐化'],
        'mitigation': '定期的なリスト更新（scripts/extract_forward_movers.py）、機能フラグでON/OFF可能',
        'expected_effect': '+4pt（予測精度向上）- 前付けレースの不安定性回避',
        'test_result': '前付けありレース: 予測精度-4pt低下を確認。除外により精度向上見込み',
        'enabled_date': '2025-12-20'
    },
    'condition_factor': {
        'risk_level': 'low',
        'main_risks': ['DB負荷増加（選手毎に直近20走取得）', '短期変動への過剰反応'],
        'mitigation': '係数範囲制限（0.8〜1.2）、データ不足時は中立（1.0）',
        'expected_effect': '+1-2pt（好調選手の評価向上、不調選手の評価低下）',
        'test_result': '検証中',
        'enabled_date': '2025-12-20'
    },
    'third_place_specialized_scorer': {
        'risk_level': 'low',
        'main_risks': ['統計データ不足時の予測変動', 'Stage3モデルとの統合バランス'],
        'mitigation': 'integration_weight=0.5で緩やかな統合、統計なし時はStage3モデルのみ使用',
        'expected_effect': '+2-3pt（3着的中率改善）',
        'test_result': '検証中（P-6-1タスク）',
        'enabled_date': '2025-12-20'
    },
    'makuri_risk_adjustment': {
        'risk_level': 'low',
        'main_risks': ['まくりリスク過大評価による1コース過小評価', '外コース過大評価'],
        'mitigation': 'adjustment_strength=1.0で段階的調整、最大調整幅-8%制限',
        'expected_effect': '+2-4pt（まくり展開時の2着・3着精度向上）',
        'test_result': '検証中（P-6-2タスク）',
        'analysis_basis': '''
            - 1コースB2: 敗北率65.1%, B1: 54.1% (A1は28.1%)
            - 1コースST 0.25秒以上: まくられ率51.6%
            - 会場別まくり率: 戸田36.1% vs 三国22.8%
            - まくり成功者平均ST: 4コース0.138秒（最速）
        ''',
        'enabled_date': '2025-12-20'
    },
    'negative_pattern_filter': {
        'risk_level': 'low',
        'main_risks': ['購入機会損失（条件に該当するレースを除外）', 'オッズ情報欠損時の除外漏れ'],
        'mitigation': '機能フラグでON/OFF可能、オッズなし時は除外しない',
        'expected_effect': '+2-3pt（4年間安定マイナスROIパターン除外による損失回避）',
        'test_result': '''
            Opus分析結果（2022-2025年4年間）:
            - オッズ10-30倍 × 予測1着3/4コース: 訓練ROI -48%、検証ROI -37%（安定マイナス）
            - オッズ100倍以上 × 予測1着6コース: 的中率0%（絶対除外）
        ''',
        'enabled_date': '2025-12-21'
    },
    'upset_pattern_filter': {
        'risk_level': 'low',
        'main_risks': ['サンプル数少（年間約300レース）', '予測1着5コースの不安定性'],
        'mitigation': '機能フラグでON/OFF可能、除外条件を満たすレースのみ対象',
        'expected_effect': '+1-2pt（穴狙いパターンによる高期待値レースの復活）',
        'test_result': '''
            Opus分析結果（2022-2025年4年間）:
            - オッズ30-100倍 × 予測1着5コース: 訓練ROI +1.6%、検証ROI +18.3%（安定プラス）
            - サンプル: 訓練N=185、検証N=137
        ''',
        'enabled_date': '2025-12-21'
    },
    'escape_rate_scoring': {
        'risk_level': 'low',
        'main_risks': ['DBアクセス増加（選手毎に逃げ率取得）', '逃げ率データの時系列依存'],
        'mitigation': 'キャッシュ機構、機能フラグでON/OFF可能',
        'expected_effect': '+1-3pt（1コース艇の評価精度向上）',
        'test_result': '''
            不採用（2026-01-09検証）:
            - 500レース検証: 1着的中 ±0.0pt、2着的中 ±0.0pt（効果なし）
            - 理由: 既存の級別スコア・勝率が逃げ率情報をカバー済み
        ''',
        'implementation': '''
            逃げ率スコアリング（1コース艇のみ）:
            - 70%以上: +3pt（優秀）
            - 60-70%: +1.5pt（良好）
            - 50-60%: ±0pt（平均）
            - 45-50%: -1pt（やや低い）
            - 45%未満: -2pt（低い）
            当地逃げ率を優先、なければ全国逃げ率を使用
        ''',
        'enabled_date': None,  # 不採用
        'disabled_date': '2026-01-09',
        'status': '不採用 - 既存特徴量と重複'
    },
    'tide_adjustment': {
        'risk_level': 'low',
        'main_risks': ['潮位フェーズ判定精度の不確実性', '補正係数の最適性検証不足', '会場別特性の反映不完全'],
        'mitigation': '''
            - 機能フラグでON/OFF即時切り替え可能
            - 最大±5点の補正制限あり
            - rdmdb_tide完全性100%（6.47M記録）
            - 7会場のみ適用（宮島、徳山、下関、福岡、芦屋、若松、大村）
        ''',
        'expected_effect': '+1-3pt（海水会場の潮位影響を反映、1コース補正最大±7%）',
        'test_result': '検証中（ON/OFF比較テスト実施中）',
        'implementation': '''
            TideAdjuster仕様:
            - 対象: 7会場（データ期間: 2022-11-01以降）
            - 補正内容:
              - 1コース: 上げ潮+2%～+7%、下げ潮-2%～-7%（会場別係数）
              - 外コース: 上げ潮-1%～-2%、下げ潮+1%～+2%
              - 若松のみ逆パターン（下げ潮で1コース有利）
            - 最大補正: ±5点（スコア×補正係数）
            - データ取得: rdmdb_tideからリアルタイム取得（±30分範囲）
            - フェーズ判定: 前後10分の変化傾向から判定
        ''',
        'enabled_date': '2026-02-13',  # 検証開始日
        'verification_date': '2026-02-13',  # ON/OFF比較完了
        'status': '不採用 - ROI±0.0pt（効果ゼロ）'
    },
    'exhibition_reliability_adjustment': {
        'risk_level': 'low',
        'main_risks': ['会場別係数の最適性検証不足', '過学習リスク'],
        'mitigation': '''
            - 機能フラグでON/OFF即時切り替え可能
            - 係数範囲を±10%に制限（控えめな設定）
            - 7会場のみ適用（高信頼6会場、低信頼1会場）
            - 市場効率性検証済み（オッズ差+38.67%、ROI差+30.19pt）
        ''',
        'expected_effect': '+2-4pt（高信頼性会場で+30pt見込み、全体平均+2-4pt）',
        'test_result': '検証中（標準バックテスト実施予定）',
        'implementation': '''
            TJ-9仕様:
            - 対象: 7会場（高信頼6会場: 徳山18, 蒲郡07, 住之江12, 丸亀15, 尼崎13, 福岡22 / 低信頼1会場: 江戸川03）
            - 係数設定:
              - 高信頼性会場（勝率差20pt以上）: 係数1.10（+10%）
              - 低信頼性会場（勝率差12pt）: 係数0.90（-10%）
              - その他会場: 係数1.0（調整なし）
            - 市場効率性:
              - 高信頼性会場: 平均オッズ90.57倍、ROI 69.26%
              - 低信頼性会場: 平均オッズ59.02倍、ROI 39.07%
              - ROI差: +30.19pt（市場は展示タイムの会場別信頼性を正しく評価していない）
            - 勝率差データ（Explore agent分析）:
              - 徳山: 展示1位勝率76.47%, 6位51.60%（差24.87pt）
              - 蒲郡: 勝率差21.52pt
              - 住之江: 勝率差21.46pt
              - 丸亀: 勝率差21.27pt
              - 尼崎: 勝率差20.78pt
              - 福岡: 勝率差20.01pt
              - 江戸川: 勝率差12.03pt（河川特性）
        ''',
        'enabled_date': '2026-02-16',  # 実装開始日
        'verification_date': '2026-02-16',  # 標準バックテスト完了
        'status': '不採用 - ROI±0.0pt～-1.2pt（係数±10%で効果なし、係数±50%で悪化）'
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
