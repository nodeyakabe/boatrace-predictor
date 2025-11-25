"""
数学計算ユーティリティ
ゼロ除算ガードなどの安全な数学演算機能を提供
"""

from typing import Union, Optional


def safe_divide(numerator: Union[int, float], denominator: Union[int, float],
                default: Optional[Union[int, float]] = 0.0) -> float:
    """
    ゼロ除算を防ぐ安全な除算

    Args:
        numerator: 分子
        denominator: 分母
        default: 分母がゼロの場合の返り値（デフォルト: 0.0）

    Returns:
        除算結果、または分母がゼロの場合はdefault値

    Examples:
        >>> safe_divide(10, 2)
        5.0
        >>> safe_divide(10, 0)
        0.0
        >>> safe_divide(10, 0, default=None)
        None
    """
    if denominator == 0:
        return default
    return numerator / denominator


def safe_percentage(part: Union[int, float], total: Union[int, float],
                    default: Optional[float] = 0.0, decimal_places: int = 2) -> float:
    """
    ゼロ除算を防ぐ安全なパーセンテージ計算

    Args:
        part: 部分の値
        total: 全体の値
        default: 全体がゼロの場合の返り値（デフォルト: 0.0）
        decimal_places: 小数点以下の桁数（デフォルト: 2）

    Returns:
        パーセンテージ（0-100）、または全体がゼロの場合はdefault値

    Examples:
        >>> safe_percentage(25, 100)
        25.0
        >>> safe_percentage(1, 3)
        33.33
        >>> safe_percentage(10, 0)
        0.0
    """
    if total == 0:
        return default
    percentage = (part / total) * 100
    return round(percentage, decimal_places)


def safe_average(values: list, default: Optional[float] = 0.0,
                decimal_places: int = 2) -> float:
    """
    空のリストを防ぐ安全な平均計算

    Args:
        values: 数値のリスト
        default: リストが空の場合の返り値（デフォルト: 0.0）
        decimal_places: 小数点以下の桁数（デフォルト: 2）

    Returns:
        平均値、またはリストが空の場合はdefault値

    Examples:
        >>> safe_average([1, 2, 3, 4, 5])
        3.0
        >>> safe_average([])
        0.0
        >>> safe_average([10.5, 20.3, 15.2], decimal_places=1)
        15.3
    """
    if not values or len(values) == 0:
        return default
    avg = sum(values) / len(values)
    return round(avg, decimal_places)


def safe_rate(successes: int, attempts: int,
             default: Optional[float] = 0.0, decimal_places: int = 3) -> float:
    """
    ゼロ除算を防ぐ安全な成功率計算

    Args:
        successes: 成功回数
        attempts: 試行回数
        default: 試行回数がゼロの場合の返り値（デフォルト: 0.0）
        decimal_places: 小数点以下の桁数（デフォルト: 3）

    Returns:
        成功率（0.0-1.0）、または試行回数がゼロの場合はdefault値

    Examples:
        >>> safe_rate(7, 10)
        0.7
        >>> safe_rate(1, 3)
        0.333
        >>> safe_rate(5, 0)
        0.0
    """
    if attempts == 0:
        return default
    rate = successes / attempts
    return round(rate, decimal_places)


def clamp(value: Union[int, float], min_value: Union[int, float],
          max_value: Union[int, float]) -> Union[int, float]:
    """
    値を指定範囲内に制限

    Args:
        value: 制限する値
        min_value: 最小値
        max_value: 最大値

    Returns:
        制限された値

    Examples:
        >>> clamp(5, 0, 10)
        5
        >>> clamp(-5, 0, 10)
        0
        >>> clamp(15, 0, 10)
        10
    """
    return max(min_value, min(value, max_value))
