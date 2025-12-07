# -*- coding: utf-8 -*-
"""
買い目システム設定

ロジックバージョン、機能フラグ、各種定数を一元管理
ロールバック時は STRATEGY_MODE を 'baseline' に変更するだけで対応可能
"""

from typing import Dict, Tuple, List

# ============================================================
# 戦略モード（排他的設計）
# ============================================================
# 'baseline': MODERATE戦略（旧ロジック、検証済み）
# 'edge_test': Edge計算のみ追加で検証
# 'venue_test': 場タイプ別オッズのみ追加で検証
# 'exclusion_test': 除外条件強化のみ追加で検証
# 'kelly_test': Kelly基準のみ追加で検証
# 'full_v2': 全機能ON（非推奨：個別検証後のみ）
STRATEGY_MODE = 'baseline'

# モード別の機能フラグ設定
_MODE_FEATURES = {
    'baseline': {
        'use_edge_filter': False,
        'use_exclusion_rules': False,
        'use_venue_odds': False,
        'use_dynamic_alloc': False,
        'use_kelly': False,
    },
    'edge_test': {
        'use_edge_filter': True,
        'use_exclusion_rules': False,
        'use_venue_odds': False,
        'use_dynamic_alloc': False,
        'use_kelly': False,
    },
    'venue_test': {
        'use_edge_filter': False,
        'use_exclusion_rules': False,
        'use_venue_odds': True,
        'use_dynamic_alloc': False,
        'use_kelly': False,
    },
    'exclusion_test': {
        'use_edge_filter': False,
        'use_exclusion_rules': True,
        'use_venue_odds': False,
        'use_dynamic_alloc': False,
        'use_kelly': False,
    },
    'kelly_test': {
        'use_edge_filter': False,
        'use_exclusion_rules': False,
        'use_venue_odds': False,
        'use_dynamic_alloc': False,
        'use_kelly': True,
    },
    'full_v2': {
        'use_edge_filter': True,
        'use_exclusion_rules': True,
        'use_venue_odds': True,
        'use_dynamic_alloc': True,
        'use_kelly': True,
    },
}

# 現在のモードから機能フラグを取得
FEATURES = _MODE_FEATURES.get(STRATEGY_MODE, _MODE_FEATURES['baseline'])

# ロジックバージョン（モードから自動設定）
LOGIC_VERSION = 'v1.0' if STRATEGY_MODE == 'baseline' else f'v2.0-{STRATEGY_MODE}'


def set_strategy_mode(mode: str):
    """
    戦略モードを動的に変更（テスト用）

    Args:
        mode: 'baseline', 'edge_test', 'venue_test', 'exclusion_test', 'kelly_test', 'full_v2'
    """
    global STRATEGY_MODE, FEATURES, LOGIC_VERSION
    if mode not in _MODE_FEATURES:
        raise ValueError(f"Unknown mode: {mode}. Available: {list(_MODE_FEATURES.keys())}")
    STRATEGY_MODE = mode
    FEATURES = _MODE_FEATURES[mode].copy()
    LOGIC_VERSION = 'v1.0' if mode == 'baseline' else f'v2.0-{mode}'


def get_feature(name: str) -> bool:
    """
    機能フラグを動的に取得（モジュール間で正しく動作させるため）

    Args:
        name: 機能名 ('use_edge_filter', 'use_venue_odds', etc.)

    Returns:
        機能がONかどうか
    """
    return _MODE_FEATURES.get(STRATEGY_MODE, _MODE_FEATURES['baseline']).get(name, False)


def get_current_features() -> Dict[str, bool]:
    """現在のモードの全機能フラグを取得"""
    return _MODE_FEATURES.get(STRATEGY_MODE, _MODE_FEATURES['baseline']).copy()


def get_logic_version() -> str:
    """現在のロジックバージョンを取得"""
    return 'v1.0' if STRATEGY_MODE == 'baseline' else f'v2.0-{STRATEGY_MODE}'

# ============================================================
# 基本設定
# ============================================================
BET_UNIT = 100  # 1点あたりの賭け金（円）

# 信頼度別の期待的中率（バックテストから算出）
CONFIDENCE_HIT_RATES = {
    'B': {'trifecta': 0.0513, 'exacta': 0.120},
    'C': {'trifecta': 0.0354, 'exacta': 0.100},
    'D': {'trifecta': 0.0171, 'exacta': 0.146},
}

# ============================================================
# ① 場タイプ別オッズレンジ
# ============================================================
VENUE_TYPE_ODDS_RANGES = {
    'high_in': {
        # イン強場: 1コース勝率60%以上
        'venues': [18, 24, 19, 21, 20],  # 徳山, 大村, 下関, 芦屋, 若松
        'odds_range': (15, 40),
        'description': 'イン逃げ率高（本命場）',
    },
    'sashi': {
        # 差し場: 1コース勝率50%以下、2-4コース活躍
        'venues': [4, 2, 3, 6],  # 平和島, 戸田, 江戸川, 浜名湖
        'odds_range': (25, 80),
        'description': '差し・まくり差し多発',
    },
    'rough': {
        # 荒れ水面: 波乱傾向
        'venues': [17, 22, 10],  # 宮島, 福岡, 三国
        'odds_range': (40, 150),
        'description': '波乱傾向',
    },
    'nighter': {
        # ナイター場
        'venues': [7, 12, 8],  # 蒲郡, 住之江, 常滑
        'odds_range': (20, 70),
        'description': 'ナイター開催',
    },
    'default': {
        'venues': [],
        'odds_range': (20, 60),
        'description': '標準',
    },
}


def get_odds_range(venue_code: int) -> Tuple[int, int]:
    """
    会場コードから最適オッズレンジを取得

    Args:
        venue_code: 会場コード (1-24)

    Returns:
        (min_odds, max_odds)
    """
    if not FEATURES['use_venue_odds']:
        return VENUE_TYPE_ODDS_RANGES['default']['odds_range']

    for vtype, config in VENUE_TYPE_ODDS_RANGES.items():
        if venue_code in config['venues']:
            return config['odds_range']
    return VENUE_TYPE_ODDS_RANGES['default']['odds_range']


def get_venue_type(venue_code: int) -> str:
    """
    会場コードから場タイプを取得

    Args:
        venue_code: 会場コード (1-24)

    Returns:
        場タイプ ('high_in', 'sashi', 'rough', 'nighter', 'default')
    """
    for vtype, config in VENUE_TYPE_ODDS_RANGES.items():
        if venue_code in config['venues']:
            return vtype
    return 'default'


# ============================================================
# ⑤ 除外条件
# ============================================================
# 信頼度除外
EXCLUDED_CONFIDENCE = ['A', 'B']  # A, Bはサンプル不足・不安定

# 級別除外
EXCLUDED_C1_RANKS = ['B1', 'B2']  # A1のみ採用

# 風速差許容（予報と実測の差）
MAX_WIND_GAP = 3  # m/s

# 進入信頼度の最低ライン
MIN_ENTRY_CONFIDENCE = 0.6

# Edge最小値（市場乖離度）
MIN_EDGE = 0.0  # Edgeがマイナスなら購入しない

# ============================================================
# ② Kelly基準設定
# ============================================================
KELLY_CONFIG = {
    'fraction': 0.25,       # フルKellyの1/4（リスク抑制）
    'max_bet_ratio': 0.05,  # 資金の5%上限
    'min_edge': 0.05,       # Edge 5%未満は購入しない
}

# ============================================================
# ④ 動的資金配分
# ============================================================
ALLOCATION_CONFIG = {
    'base_ratio': {'trifecta': 0.7, 'exacta': 0.3},
    'high_edge_ratio': {'trifecta': 0.9, 'exacta': 0.1},  # Edge高い時
    'upset_ratio': {'trifecta': 0.5, 'exacta': 0.5},       # 荒れ予測時
}

# ============================================================
# EV閾値
# ============================================================
EV_THRESHOLD = 1.0  # 期待値1.0以上で購入

# ============================================================
# 安全機構
# ============================================================
SAFETY_CONFIG = {
    'max_loss_streak': 10,  # 連敗上限（超えたら自動停止）
    'max_ev': 5.0,          # EV異常値（5.0超は無効）
    'max_daily_bets': 20,   # 1日の最大購入数
    'min_bankroll': 5000,   # 最低資金（これ以下で停止）
}

# ============================================================
# 購入条件定義（MODERATE戦略ベース）
# ============================================================
BET_CONDITIONS = {
    'C': [
        {
            'method': '従来',
            'odds_min': 30, 'odds_max': 60,
            'c1_rank': ['A1'],
            'expected_roi': 127.2,
            'bet_amount': 500,
            'sample_count': 363,
            'priority': 1,
        },
        {
            'method': '従来',
            'odds_min': 20, 'odds_max': 40,
            'c1_rank': ['A1'],
            'expected_roi': 122.8,
            'bet_amount': 400,
            'sample_count': 451,
            'priority': 2,
        },
    ],
    'D': [
        {
            'method': '新方式',
            'odds_min': 25, 'odds_max': 50,
            'c1_rank': ['A1'],
            'expected_roi': 251.5,
            'bet_amount': 300,
            'sample_count': 75,
            'priority': 1,
        },
        {
            'method': '従来',
            'odds_min': 20, 'odds_max': 50,
            'c1_rank': ['A1'],
            'expected_roi': 215.7,
            'bet_amount': 300,
            'sample_count': 173,
            'priority': 2,
        },
    ],
}

# 2連単条件
EXACTA_CONDITIONS = {
    'D': {
        'c1_rank': ['A1'],
        'expected_roi': 106.7,
        'bet_amount': 200,
        'sample_count': 907,
        'hit_rate': 14.6,
    },
}
