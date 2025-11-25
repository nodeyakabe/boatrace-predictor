"""
日付フォーマット変換ユーティリティ
一元化された日付変換機能を提供
"""

from datetime import datetime
from typing import Union


def to_yyyymmdd(date: Union[str, datetime]) -> str:
    """
    日付をYYYYMMDD形式の文字列に変換

    Args:
        date: 日付（YYYY-MM-DD形式の文字列、YYYYMMDDの文字列、またはdatetimeオブジェクト）

    Returns:
        YYYYMMDD形式の文字列

    Examples:
        >>> to_yyyymmdd("2024-11-02")
        '20241102'
        >>> to_yyyymmdd("20241102")
        '20241102'
        >>> to_yyyymmdd(datetime(2024, 11, 2))
        '20241102'
    """
    if isinstance(date, datetime):
        return date.strftime('%Y%m%d')
    elif isinstance(date, str):
        # ハイフンを削除
        date_str = date.replace('-', '')
        # 長さチェック
        if len(date_str) == 8 and date_str.isdigit():
            return date_str
        else:
            raise ValueError(f"Invalid date format: {date}")
    else:
        raise TypeError(f"Unsupported type: {type(date)}")


def to_iso_format(date: Union[str, datetime]) -> str:
    """
    日付をYYYY-MM-DD形式の文字列に変換

    Args:
        date: 日付（YYYYMMDDの文字列、YYYY-MM-DD形式の文字列、またはdatetimeオブジェクト）

    Returns:
        YYYY-MM-DD形式の文字列

    Examples:
        >>> to_iso_format("20241102")
        '2024-11-02'
        >>> to_iso_format("2024-11-02")
        '2024-11-02'
        >>> to_iso_format(datetime(2024, 11, 2))
        '2024-11-02'
    """
    if isinstance(date, datetime):
        return date.strftime('%Y-%m-%d')
    elif isinstance(date, str):
        # 既にハイフン区切りの場合はそのまま返す
        if '-' in date and len(date) == 10:
            # 日付の妥当性チェック
            try:
                datetime.strptime(date, '%Y-%m-%d')
                return date
            except ValueError:
                raise ValueError(f"Invalid date format: {date}")
        # YYYYMMDDの場合はYYYY-MM-DDに変換
        elif len(date) == 8 and date.isdigit():
            return f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        else:
            raise ValueError(f"Invalid date format: {date}")
    else:
        raise TypeError(f"Unsupported type: {type(date)}")


def to_datetime(date: Union[str, datetime]) -> datetime:
    """
    日付をdatetimeオブジェクトに変換

    Args:
        date: 日付（YYYYMMDDの文字列、YYYY-MM-DD形式の文字列、またはdatetimeオブジェクト）

    Returns:
        datetimeオブジェクト

    Examples:
        >>> to_datetime("20241102")
        datetime.datetime(2024, 11, 2, 0, 0)
        >>> to_datetime("2024-11-02")
        datetime.datetime(2024, 11, 2, 0, 0)
    """
    if isinstance(date, datetime):
        return date
    elif isinstance(date, str):
        # ハイフン区切り
        if '-' in date:
            return datetime.strptime(date, '%Y-%m-%d')
        # YYYYMMDD
        elif len(date) == 8 and date.isdigit():
            return datetime.strptime(date, '%Y%m%d')
        else:
            raise ValueError(f"Invalid date format: {date}")
    else:
        raise TypeError(f"Unsupported type: {type(date)}")


def validate_date(date_str: str, format: str = '%Y-%m-%d') -> bool:
    """
    日付文字列の妥当性を検証

    Args:
        date_str: 検証する日付文字列
        format: 期待される日付フォーマット（デフォルト: '%Y-%m-%d'）

    Returns:
        妥当な日付の場合True、そうでない場合False

    Examples:
        >>> validate_date("2024-11-02")
        True
        >>> validate_date("2024-13-01")
        False
        >>> validate_date("20241102", "%Y%m%d")
        True
    """
    try:
        datetime.strptime(date_str, format)
        return True
    except ValueError:
        return False
