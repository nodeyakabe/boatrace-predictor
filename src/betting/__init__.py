# -*- coding: utf-8 -*-
"""
betting パッケージ

買い目生成、期待値計算、Kelly基準投資戦略など

v2.0: 改善版（Edge計算、除外条件強化、場タイプ別オッズ、動的配分、Kelly基準）
"""

# 設定
from .config import (
    LOGIC_VERSION,
    FEATURES,
    BET_UNIT,
    CONFIDENCE_HIT_RATES,
    get_odds_range,
    get_venue_type,
)

# フィルタエンジン
from .filter_engine import FilterEngine, FilterResult

# 期待値計算
from .ev_calculator import EVCalculator, EVResult, calc_simple_ev, calc_simple_edge

# 買い目選択
from .bet_selector import (
    BetSelector,
    BetDecision,
    RaceBetPlan,
    BetType,
    DynamicAllocator,
)

# Kelly計算
from .kelly_calculator import KellyCalculator, KellyBetResult, SimpleKelly

# 戦略エンジン
from .strategy_engine import StrategyEngine, StrategyResult, DailyBetSummary, create_engine

# ログ管理
from .bet_logger import BetLogger, BetRecord, write_log

# 旧モジュール（互換性のため維持）
from .ev_bet_selector import EVBetSelector, EVBetAnalyzer, EVBet
from .kelly_strategy import KellyBettingStrategy, ExpectedValueCalculator, BetRecommendation
from .bet_target_evaluator import BetTargetEvaluator, BetTarget, BetStatus, ExactaBetTarget

__all__ = [
    # 設定
    'LOGIC_VERSION',
    'FEATURES',
    'BET_UNIT',
    'CONFIDENCE_HIT_RATES',
    'get_odds_range',
    'get_venue_type',
    # フィルタ
    'FilterEngine',
    'FilterResult',
    # EV計算
    'EVCalculator',
    'EVResult',
    'calc_simple_ev',
    'calc_simple_edge',
    # 買い目選択
    'BetSelector',
    'BetDecision',
    'RaceBetPlan',
    'BetType',
    'DynamicAllocator',
    # Kelly
    'KellyCalculator',
    'KellyBetResult',
    'SimpleKelly',
    # 戦略エンジン
    'StrategyEngine',
    'StrategyResult',
    'DailyBetSummary',
    'create_engine',
    # ログ
    'BetLogger',
    'BetRecord',
    'write_log',
    # 旧モジュール（互換性）
    'EVBetSelector',
    'EVBetAnalyzer',
    'EVBet',
    'KellyBettingStrategy',
    'ExpectedValueCalculator',
    'BetRecommendation',
    'BetTargetEvaluator',
    'BetTarget',
    'BetStatus',
    'ExactaBetTarget',
]
