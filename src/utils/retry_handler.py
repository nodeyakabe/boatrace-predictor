"""
リトライハンドラー - 統一されたエラーハンドリングとリトライロジック

全スクレイパーとワークフローで使用する共通のリトライ機構を提供
"""
import time
import logging
from typing import Callable, TypeVar, Optional, Tuple, Type
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryConfig:
    """リトライ設定"""
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 30.0,
        timeout: Optional[float] = None
    ):
        """
        Args:
            max_retries: 最大リトライ回数
            initial_delay: 初回リトライ待機時間（秒）
            backoff_factor: 指数バックオフの倍率
            max_delay: 最大待機時間（秒）
            timeout: タイムアウト時間（秒）
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        self.timeout = timeout


# デフォルト設定（用途別）
DEFAULT_CONFIG = RetryConfig(max_retries=3, initial_delay=1.0)
SCRAPER_CONFIG = RetryConfig(max_retries=2, initial_delay=0.5, timeout=30.0)
DB_CONFIG = RetryConfig(max_retries=5, initial_delay=0.1, backoff_factor=1.5)
NETWORK_CONFIG = RetryConfig(max_retries=3, initial_delay=2.0, timeout=60.0)


def retry_with_backoff(
    config: RetryConfig = DEFAULT_CONFIG,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    指数バックオフ付きリトライデコレーター

    使用例:
        @retry_with_backoff(config=SCRAPER_CONFIG)
        def fetch_data():
            # スクレイピング処理
            pass

        @retry_with_backoff(
            config=RetryConfig(max_retries=5),
            exceptions=(ConnectionError, TimeoutError)
        )
        def network_request():
            # ネットワークリクエスト
            pass

    Args:
        config: リトライ設定
        exceptions: リトライ対象の例外タプル
        on_retry: リトライ時のコールバック関数 (exception, attempt_number) -> None
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            attempt = 0
            last_exception = None

            while attempt <= config.max_retries:
                try:
                    # タイムアウト設定がある場合
                    if config.timeout:
                        import signal

                        def timeout_handler(signum, frame):
                            raise TimeoutError(f"処理がタイムアウトしました（{config.timeout}秒）")

                        # Windowsではsignal.SIGALRMが使えないため、threading.Timerを使用
                        import threading
                        timer = None
                        try:
                            # タイムアウトタイマーを設定
                            timer = threading.Timer(config.timeout, lambda: (_ for _ in ()).throw(TimeoutError(f"処理がタイムアウトしました（{config.timeout}秒）")))
                            timer.start()
                            result = func(*args, **kwargs)
                            return result
                        finally:
                            if timer:
                                timer.cancel()
                    else:
                        return func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e
                    attempt += 1

                    if attempt > config.max_retries:
                        logger.error(
                            f"{func.__name__} 失敗: {attempt}回試行後も成功せず - {type(e).__name__}: {e}"
                        )
                        raise

                    # リトライ待機時間を計算（指数バックオフ）
                    delay = min(
                        config.initial_delay * (config.backoff_factor ** (attempt - 1)),
                        config.max_delay
                    )

                    logger.warning(
                        f"{func.__name__} リトライ {attempt}/{config.max_retries} "
                        f"({delay:.1f}秒後) - {type(e).__name__}: {str(e)[:100]}"
                    )

                    # コールバック実行
                    if on_retry:
                        try:
                            on_retry(e, attempt)
                        except Exception as callback_error:
                            logger.error(f"リトライコールバックエラー: {callback_error}")

                    time.sleep(delay)

            # 到達しないはずだが、念のため
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def safe_execute(
    func: Callable[..., T],
    *args,
    default: Optional[T] = None,
    log_error: bool = True,
    **kwargs
) -> Optional[T]:
    """
    安全に関数を実行（エラー時はデフォルト値を返す）

    使用例:
        result = safe_execute(risky_function, arg1, arg2, default=[], log_error=True)

    Args:
        func: 実行する関数
        *args: 関数の引数
        default: エラー時の戻り値（デフォルトNone）
        log_error: エラーをログ出力するか
        **kwargs: 関数のキーワード引数

    Returns:
        関数の戻り値、またはエラー時はdefault
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_error:
            logger.error(f"{func.__name__} 実行エラー: {type(e).__name__}: {e}")
        return default


class CircuitBreaker:
    """
    サーキットブレーカーパターン実装

    連続失敗が閾値を超えた場合、一定時間リクエストを遮断する
    """
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ):
        """
        Args:
            failure_threshold: 連続失敗の閾値
            recovery_timeout: リカバリー待機時間（秒）
            expected_exception: 失敗と見なす例外
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'closed'  # closed, open, half_open

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """サーキットブレーカー経由で関数を実行"""
        if self.state == 'open':
            if time.time() - self.last_failure_time < self.recovery_timeout:
                raise Exception(f"サーキットブレーカー発動中（{self.recovery_timeout}秒間）")
            else:
                self.state = 'half_open'

        try:
            result = func(*args, **kwargs)

            # 成功したらリセット
            if self.state == 'half_open':
                self.state = 'closed'
            self.failure_count = 0

            return result

        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = 'open'
                logger.error(
                    f"サーキットブレーカー発動: {self.failure_count}回連続失敗"
                )

            raise
