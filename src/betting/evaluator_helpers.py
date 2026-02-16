"""BetTargetEvaluator生成のヘルパー関数

predictor_helpers.pyと同じ思想で、設定の一貫性を保証
テストと実運用で同じ設定を使用することで、実装乖離を防止
"""

from src.betting.bet_target_evaluator import BetTargetEvaluator
from src.betting.multi_bet_generator import MultiBetPattern
from config.bet_conditions import STANDARD_EVALUATOR_PARAMS

def create_standard_evaluator(db_path='data/boatrace.db') -> BetTargetEvaluator:
    """
    標準設定のBetTargetEvaluatorを生成

    テスト・実運用で同じ設定を使用することで、実装乖離を防止
    予測生成におけるcreate_standard_predictor()と同じ思想

    使用箇所:
    - scripts/backtest/standard_backtest.py （バックテスト）
    - scripts/automation/generate_daily_predictions.py （実運用）
    - scripts/validation/verify_prediction_consistency.py （検証）

    Usage:
        >>> evaluator = create_standard_evaluator()
        >>> bet_target = evaluator.evaluate_race(race_data, predictions, odds_data)

    Args:
        db_path: データベースパス

    Returns:
        BetTargetEvaluator: 標準設定のインスタンス
    """
    return BetTargetEvaluator(
        use_multi_bet=STANDARD_EVALUATOR_PARAMS['use_multi_bet'],
        multi_bet_pattern=getattr(MultiBetPattern, STANDARD_EVALUATOR_PARAMS['multi_bet_pattern']),
        enable_venue_wind_filter=STANDARD_EVALUATOR_PARAMS['enable_venue_wind_filter'],
        enable_venue_course_adjustment=STANDARD_EVALUATOR_PARAMS['enable_venue_course_adjustment'],
        venue_course_adjustment_scale=STANDARD_EVALUATOR_PARAMS.get('venue_course_adjustment_scale', 1.0),
        db_path=db_path
    )

def create_custom_evaluator(
    use_multi_bet: bool = None,
    multi_bet_pattern: MultiBetPattern = None,
    enable_venue_wind_filter: bool = None,
    enable_venue_course_adjustment: bool = None,
    venue_course_adjustment_scale: float = None,
    db_path='data/boatrace.db'
) -> BetTargetEvaluator:
    """
    カスタム設定のBetTargetEvaluatorを生成

    特殊な分析やアブレーションテストに使用
    指定されたパラメータのみを上書きし、それ以外は標準設定を使用

    Usage:
        >>> # 風速フィルターのみ無効化してテスト
        >>> evaluator = create_custom_evaluator(enable_venue_wind_filter=False)
        >>>
        >>> # パターンHを無効化（全て1点買い）
        >>> from src.betting.multi_bet_generator import MultiBetPattern
        >>> evaluator = create_custom_evaluator(
        ...     use_multi_bet=False,
        ...     multi_bet_pattern=MultiBetPattern.DISABLED
        ... )

    Args:
        use_multi_bet: 複数点買いを使用するか（Noneなら標準設定）
        multi_bet_pattern: パターン（Noneなら標準設定）
        enable_venue_wind_filter: 風速フィルター（Noneなら標準設定）
        enable_venue_course_adjustment: 会場コース調整（Noneなら標準設定）
        venue_course_adjustment_scale: 会場コース調整の倍率（Noneなら標準設定）
        db_path: データベースパス

    Returns:
        BetTargetEvaluator: カスタム設定のインスタンス
    """
    params = STANDARD_EVALUATOR_PARAMS.copy()

    if use_multi_bet is not None:
        params['use_multi_bet'] = use_multi_bet
    if multi_bet_pattern is not None:
        params['multi_bet_pattern'] = multi_bet_pattern.name
    if enable_venue_wind_filter is not None:
        params['enable_venue_wind_filter'] = enable_venue_wind_filter
    if enable_venue_course_adjustment is not None:
        params['enable_venue_course_adjustment'] = enable_venue_course_adjustment
    if venue_course_adjustment_scale is not None:
        params['venue_course_adjustment_scale'] = venue_course_adjustment_scale

    return BetTargetEvaluator(
        use_multi_bet=params['use_multi_bet'],
        multi_bet_pattern=getattr(MultiBetPattern, params['multi_bet_pattern']),
        enable_venue_wind_filter=params['enable_venue_wind_filter'],
        enable_venue_course_adjustment=params['enable_venue_course_adjustment'],
        venue_course_adjustment_scale=params.get('venue_course_adjustment_scale', 1.0),
        db_path=db_path
    )
