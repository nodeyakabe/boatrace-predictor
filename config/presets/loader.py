"""
プリセット設定ローダー

YAMLファイルからスコアリング設定を読み込み、
旧ロジック（race_predictor.py）で使用可能な形式で提供する。

更新日: 2025-12-15
"""

import os
import yaml
from typing import Dict, Any, Optional
from functools import lru_cache

# プリセットディレクトリ
PRESET_DIR = os.path.dirname(os.path.abspath(__file__))


@lru_cache(maxsize=1)
def load_scoring_weights() -> Dict[str, Any]:
    """
    スコアリング重み設定を読み込む

    Returns:
        スコアリング設定の辞書
    """
    path = os.path.join(PRESET_DIR, 'scoring_weights.yaml')

    if not os.path.exists(path):
        print(f"Warning: {path} not found, using defaults")
        return get_default_scoring_weights()

    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_optimization_targets() -> Dict[str, Any]:
    """
    最適化対象パラメータ設定を読み込む

    Returns:
        最適化対象設定の辞書
    """
    path = os.path.join(PRESET_DIR, 'optimization_targets.yaml')

    if not os.path.exists(path):
        print(f"Warning: {path} not found")
        return {}

    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_extended_scorer_weights() -> Dict[str, float]:
    """
    ExtendedScorer用の重み設定を取得

    Returns:
        各要素の重み辞書
    """
    config = load_scoring_weights()
    return config.get('extended_scorer', get_default_extended_scorer_weights())


def get_before_pattern_multipliers() -> Dict[str, Dict[str, Any]]:
    """
    BEFORE_PATTERNSの倍率設定を取得

    Returns:
        パターン別の倍率辞書
    """
    config = load_scoring_weights()
    return config.get('before_patterns', {})


def get_dynamic_weights_config() -> Dict[str, Any]:
    """
    動的重み調整設定を取得

    Returns:
        動的重み設定の辞書
    """
    config = load_scoring_weights()
    return config.get('dynamic_weights', get_default_dynamic_weights())


def get_adjustment_limits() -> Dict[str, float]:
    """
    補正の最大影響範囲を取得

    Returns:
        補正上限の辞書
    """
    config = load_scoring_weights()
    return config.get('adjustment_limits', {
        'max_exhibition_adjustment': 10.0,
        'max_rule_adjustment': 10.0,
        'max_weather_adjustment': 8.0,
        'max_tide_adjustment': 5.0,
        'max_compound_buff': 15.0,
    })


def get_course_rank_win_rates() -> Dict[tuple, float]:
    """
    コース×ランク勝率を取得

    Returns:
        (コース, ランク): 勝率 の辞書
    """
    config = load_scoring_weights()
    raw = config.get('course_rank_win_rates', {})

    result = {}
    for course_key, ranks in raw.items():
        course_num = int(course_key.replace('course_', ''))
        for rank, rate in ranks.items():
            result[(course_num, rank)] = rate

    return result


def get_pattern_multiplier(pattern_name: str, default: float = 1.0) -> float:
    """
    特定パターンの倍率を取得

    Args:
        pattern_name: パターン名
        default: デフォルト倍率

    Returns:
        倍率
    """
    patterns = get_before_pattern_multipliers()

    # 各カテゴリを検索
    for category in ['first_place', 'second_place', 'third_place', 'top3']:
        if category in patterns and pattern_name in patterns[category]:
            return patterns[category][pattern_name].get('multiplier', default)

    return default


# ============================================================
# デフォルト値（YAML読み込み失敗時のフォールバック）
# ============================================================

def get_default_scoring_weights() -> Dict[str, Any]:
    """デフォルトのスコアリング重み"""
    return {
        'extended_scorer': get_default_extended_scorer_weights(),
        'dynamic_weights': get_default_dynamic_weights(),
        'adjustment_limits': {
            'max_exhibition_adjustment': 10.0,
            'max_rule_adjustment': 10.0,
            'max_weather_adjustment': 8.0,
            'max_tide_adjustment': 5.0,
            'max_compound_buff': 15.0,
        }
    }


def get_default_extended_scorer_weights() -> Dict[str, float]:
    """デフォルトのExtendedScorer重み"""
    return {
        'class_score': 10,
        'fl_penalty_max': -10,
        'session': 5,
        'prev_race': 5,
        'course_entry': 5,
        'matchup': 5,
        'motor': 5,
        'start_timing': 10,
        'exhibition': 8,
        'tilt': 3,
        'recent_form': 8,
        'venue_affinity': 3,
        'total_weight': 20.0,
        'max_possible': 76,
        'min_possible': -10,
    }


def get_default_dynamic_weights() -> Dict[str, Any]:
    """デフォルトの動的重み設定"""
    return {
        'base': {
            'course_weight': 35,
            'racer_weight': 35,
            'motor_weight': 20,
            'kimarite_weight': 5,
            'grade_weight': 5,
        },
        'high_motor_venues': {
            'venues': ['23', '22', '18', '21'],
            'adjustments': {
                'motor_weight': 8,
                'course_weight': -5,
                'kimarite_weight': 2,
            }
        }
    }


def clear_cache():
    """キャッシュをクリア（設定ファイル更新時に使用）"""
    load_scoring_weights.cache_clear()
    load_optimization_targets.cache_clear()


def reload_config():
    """設定を再読み込み"""
    clear_cache()
    return load_scoring_weights()


# ============================================================
# 設定表示用ユーティリティ
# ============================================================

def print_current_config():
    """現在の設定を表示"""
    config = load_scoring_weights()

    print("=" * 60)
    print("Current Scoring Configuration")
    print("=" * 60)

    # ExtendedScorer
    print("\n[ExtendedScorer Weights]")
    es = config.get('extended_scorer', {})
    for key, val in es.items():
        print(f"  {key}: {val}")

    # Adjustment Limits
    print("\n[Adjustment Limits]")
    limits = config.get('adjustment_limits', {})
    for key, val in limits.items():
        print(f"  {key}: {val}")

    # Pattern Multipliers (sample)
    print("\n[Before Pattern Multipliers (sample)]")
    patterns = config.get('before_patterns', {})
    if 'first_place' in patterns:
        for name, data in list(patterns['first_place'].items())[:3]:
            print(f"  {name}: {data.get('multiplier', 1.0)}")

    print("=" * 60)


if __name__ == '__main__':
    print_current_config()
