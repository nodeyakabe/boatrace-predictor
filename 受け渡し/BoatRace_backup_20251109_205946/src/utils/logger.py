"""
ロギング設定ユーティリティ
プロジェクト全体で使用する統一ロガー設定
"""

import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logger(
    name: str = None,
    level: int = logging.INFO,
    log_file: str = None,
    console_output: bool = True
) -> logging.Logger:
    """
    ロガーをセットアップ

    Args:
        name: ロガー名（Noneの場合はルートロガー）
        level: ログレベル（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        log_file: ログファイルパス（Noneの場合はファイル出力なし）
        console_output: コンソール出力の有無

    Returns:
        設定済みロガー

    Examples:
        >>> logger = setup_logger(__name__, level=logging.DEBUG)
        >>> logger.info("処理開始")
        >>> logger.error("エラー発生", exc_info=True)
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 既存のハンドラーをクリア（重複防止）
    logger.handlers.clear()

    # フォーマッター設定
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # コンソールハンドラー
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # ファイルハンドラー
    if log_file:
        # ログディレクトリ作成
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    既存のロガーを取得（存在しない場合は新規作成）

    Args:
        name: ロガー名

    Returns:
        ロガー

    Examples:
        >>> logger = get_logger(__name__)
        >>> logger.info("ログメッセージ")
    """
    return logging.getLogger(name)


# プロジェクト用デフォルトロガー設定
def setup_project_logger(log_level: str = "INFO") -> logging.Logger:
    """
    プロジェクト全体で使用するデフォルトロガーをセットアップ

    Args:
        log_level: ログレベル（"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"）

    Returns:
        設定済みロガー
    """
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    level = level_map.get(log_level.upper(), logging.INFO)

    # ログファイル名（日付付き）
    today = datetime.now().strftime('%Y%m%d')
    log_file = f"logs/boatrace_{today}.log"

    return setup_logger(
        name="boatrace",
        level=level,
        log_file=log_file,
        console_output=True
    )
