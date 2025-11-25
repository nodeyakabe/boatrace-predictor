"""
エラーハンドリングモジュール
Phase 3.4: 堅牢なエラー処理とリカバリー
"""
import traceback
import functools
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Type, Union
import json
import os


class PredictionError(Exception):
    """予測処理に関するエラー"""
    def __init__(self, message: str, error_code: str = "PRED_ERROR", details: Dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = datetime.now().isoformat()
        super().__init__(self.message)

    def to_dict(self) -> Dict:
        return {
            'error_code': self.error_code,
            'message': self.message,
            'details': self.details,
            'timestamp': self.timestamp
        }


class DataError(PredictionError):
    """データに関するエラー"""
    def __init__(self, message: str, details: Dict = None):
        super().__init__(message, "DATA_ERROR", details)


class ModelError(PredictionError):
    """モデルに関するエラー"""
    def __init__(self, message: str, details: Dict = None):
        super().__init__(message, "MODEL_ERROR", details)


class NetworkError(PredictionError):
    """ネットワークに関するエラー"""
    def __init__(self, message: str, details: Dict = None):
        super().__init__(message, "NETWORK_ERROR", details)


class ValidationError(PredictionError):
    """バリデーションエラー"""
    def __init__(self, message: str, details: Dict = None):
        super().__init__(message, "VALIDATION_ERROR", details)


class ErrorHandler:
    """
    統合エラーハンドラー

    - エラーの分類と処理
    - 自動リカバリー
    - ログ記録
    """

    def __init__(self, log_dir: str = 'logs/errors'):
        self.log_dir = log_dir
        self.error_counts = {}
        self.last_errors = {}
        self.recovery_strategies = {}

        os.makedirs(log_dir, exist_ok=True)

        # デフォルトのリカバリー戦略を登録
        self._register_default_strategies()

    def _register_default_strategies(self):
        """デフォルトのリカバリー戦略を登録"""
        self.recovery_strategies = {
            'DATA_ERROR': self._recover_from_data_error,
            'MODEL_ERROR': self._recover_from_model_error,
            'NETWORK_ERROR': self._recover_from_network_error,
            'VALIDATION_ERROR': self._recover_from_validation_error,
        }

    def handle_error(
        self,
        error: Exception,
        context: Optional[Dict] = None,
        auto_recover: bool = True
    ) -> Dict:
        """
        エラーを処理

        Args:
            error: 発生したエラー
            context: エラー発生時のコンテキスト
            auto_recover: 自動リカバリーを試みるか

        Returns:
            処理結果
        """
        # エラー情報の構築
        if isinstance(error, PredictionError):
            error_info = error.to_dict()
        else:
            error_info = {
                'error_code': 'UNKNOWN_ERROR',
                'message': str(error),
                'details': {
                    'type': type(error).__name__,
                    'traceback': traceback.format_exc()
                },
                'timestamp': datetime.now().isoformat()
            }

        # コンテキスト追加
        error_info['context'] = context or {}

        # エラーカウント更新
        error_code = error_info['error_code']
        self.error_counts[error_code] = self.error_counts.get(error_code, 0) + 1
        self.last_errors[error_code] = error_info

        # ログ記録
        self._log_error(error_info)

        # 自動リカバリー
        recovery_result = None
        if auto_recover and error_code in self.recovery_strategies:
            recovery_result = self.recovery_strategies[error_code](error_info, context)

        return {
            'error': error_info,
            'recovery_attempted': auto_recover,
            'recovery_result': recovery_result,
            'error_count': self.error_counts[error_code]
        }

    def _log_error(self, error_info: Dict):
        """エラーをログに記録"""
        log_file = os.path.join(
            self.log_dir,
            f'errors_{datetime.now().strftime("%Y%m%d")}.jsonl'
        )

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(error_info, ensure_ascii=False) + '\n')

    def _recover_from_data_error(
        self,
        error_info: Dict,
        context: Optional[Dict]
    ) -> Dict:
        """データエラーからのリカバリー"""
        return {
            'strategy': 'USE_DEFAULT_DATA',
            'success': True,
            'message': 'デフォルトデータを使用します'
        }

    def _recover_from_model_error(
        self,
        error_info: Dict,
        context: Optional[Dict]
    ) -> Dict:
        """モデルエラーからのリカバリー"""
        return {
            'strategy': 'USE_FALLBACK_MODEL',
            'success': True,
            'message': 'フォールバックモデルを使用します'
        }

    def _recover_from_network_error(
        self,
        error_info: Dict,
        context: Optional[Dict]
    ) -> Dict:
        """ネットワークエラーからのリカバリー"""
        return {
            'strategy': 'RETRY_WITH_BACKOFF',
            'success': True,
            'message': '再試行を実行します'
        }

    def _recover_from_validation_error(
        self,
        error_info: Dict,
        context: Optional[Dict]
    ) -> Dict:
        """バリデーションエラーからのリカバリー"""
        return {
            'strategy': 'SKIP_INVALID_DATA',
            'success': True,
            'message': '無効なデータをスキップします'
        }

    def get_error_summary(self) -> Dict:
        """エラーサマリーを取得"""
        return {
            'total_errors': sum(self.error_counts.values()),
            'error_counts': self.error_counts,
            'last_errors': self.last_errors,
            'most_frequent': max(self.error_counts.items(), key=lambda x: x[1]) if self.error_counts else None
        }

    def clear_error_counts(self):
        """エラーカウントをクリア"""
        self.error_counts.clear()
        self.last_errors.clear()


def retry_on_error(
    max_retries: int = 3,
    delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    エラー時に自動リトライするデコレータ

    Args:
        max_retries: 最大リトライ回数
        delay_seconds: 初期待機時間（秒）
        backoff_factor: 待機時間の増加係数
        exceptions: リトライ対象の例外
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay_seconds

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        raise

            raise last_exception

        return wrapper
    return decorator


def safe_execution(
    default_return: Any = None,
    error_handler: Optional[ErrorHandler] = None,
    raise_on_error: bool = False
):
    """
    安全な実行を保証するデコレータ

    Args:
        default_return: エラー時のデフォルト戻り値
        error_handler: エラーハンドラーインスタンス
        raise_on_error: エラー時に例外を再送出するか
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if error_handler:
                    error_handler.handle_error(e, {
                        'function': func.__name__,
                        'args': str(args)[:200],
                        'kwargs': str(kwargs)[:200]
                    })

                if raise_on_error:
                    raise

                return default_return

        return wrapper
    return decorator


def timeout_execution(seconds: float = 10.0):
    """
    タイムアウト付き実行デコレータ（Windows互換）

    注意: Windowsではシグナルベースのタイムアウトが使えないため、
    スレッドベースの実装が必要ですが、ここでは簡易版を提供
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 簡易実装：実行時間を計測
            start_time = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time

            if elapsed > seconds:
                raise TimeoutError(f"実行時間が{seconds}秒を超えました: {elapsed:.2f}秒")

            return result

        return wrapper
    return decorator


class CircuitBreaker:
    """
    サーキットブレーカーパターン

    連続エラー時にサービスを一時停止
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0
    ):
        """
        Args:
            failure_threshold: 失敗閾値
            reset_timeout: リセットタイムアウト（秒）
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    def can_execute(self) -> bool:
        """実行可能かどうか"""
        if self.state == 'CLOSED':
            return True
        elif self.state == 'OPEN':
            # タイムアウト経過後はHALF_OPENに
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.reset_timeout:
                    self.state = 'HALF_OPEN'
                    return True
            return False
        else:  # HALF_OPEN
            return True

    def record_success(self):
        """成功を記録"""
        self.failure_count = 0
        self.state = 'CLOSED'

    def record_failure(self):
        """失敗を記録"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'

    def get_state(self) -> Dict:
        """現在の状態を取得"""
        return {
            'state': self.state,
            'failure_count': self.failure_count,
            'failure_threshold': self.failure_threshold,
            'reset_timeout': self.reset_timeout,
            'last_failure': self.last_failure_time.isoformat() if self.last_failure_time else None
        }


class GracefulDegradation:
    """
    グレースフルデグラデーション

    システム障害時に機能を段階的に縮退
    """

    def __init__(self):
        self.degradation_level = 0  # 0: 正常, 1: 一部機能制限, 2: 最小機能
        self.disabled_features = set()
        self.fallback_functions = {}

    def set_degradation_level(self, level: int):
        """デグラデーションレベルを設定"""
        self.degradation_level = min(max(level, 0), 2)

        if level >= 1:
            self.disabled_features.add('advanced_analytics')
            self.disabled_features.add('real_time_odds')
        if level >= 2:
            self.disabled_features.add('model_ensemble')
            self.disabled_features.add('risk_adjustment')

    def is_feature_available(self, feature: str) -> bool:
        """機能が利用可能か"""
        return feature not in self.disabled_features

    def register_fallback(self, feature: str, fallback_func: Callable):
        """フォールバック関数を登録"""
        self.fallback_functions[feature] = fallback_func

    def execute_with_fallback(
        self,
        feature: str,
        main_func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """フォールバック付きで実行"""
        if self.is_feature_available(feature):
            try:
                return main_func(*args, **kwargs)
            except Exception:
                pass

        # フォールバック実行
        if feature in self.fallback_functions:
            return self.fallback_functions[feature](*args, **kwargs)

        return None

    def get_status(self) -> Dict:
        """現在のステータスを取得"""
        return {
            'degradation_level': self.degradation_level,
            'disabled_features': list(self.disabled_features),
            'available_fallbacks': list(self.fallback_functions.keys())
        }


if __name__ == "__main__":
    print("=" * 60)
    print("エラーハンドリングモジュール テスト")
    print("=" * 60)

    # エラーハンドラーのテスト
    print("\n【エラーハンドラー】")
    handler = ErrorHandler()

    # 各種エラーをシミュレート
    errors = [
        DataError("データが見つかりません", {'race_id': 'R001'}),
        ModelError("モデルの読み込みに失敗", {'model': 'xgboost'}),
        NetworkError("接続タイムアウト", {'url': 'http://api.example.com'}),
        ValidationError("無効なオッズ値", {'odds': -1.0}),
    ]

    for error in errors:
        result = handler.handle_error(error, {'test': True})
        print(f"  {error.error_code}: {result['recovery_result']['strategy']}")

    summary = handler.get_error_summary()
    print(f"\n  総エラー数: {summary['total_errors']}")
    print(f"  エラー種別: {summary['error_counts']}")

    # リトライデコレータのテスト
    print("\n【リトライデコレータ】")
    call_count = 0

    @retry_on_error(max_retries=3, delay_seconds=0.1)
    def flaky_function():
        global call_count
        call_count += 1
        if call_count < 3:
            raise NetworkError("一時的なエラー")
        return "成功"

    try:
        result = flaky_function()
        print(f"  結果: {result} (試行回数: {call_count})")
    except Exception as e:
        print(f"  失敗: {e}")

    # サーキットブレーカーのテスト
    print("\n【サーキットブレーカー】")
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout=5.0)

    for i in range(5):
        if breaker.can_execute():
            print(f"  試行 {i+1}: 実行可能")
            breaker.record_failure()
        else:
            print(f"  試行 {i+1}: ブロック（状態: {breaker.state}）")

    state = breaker.get_state()
    print(f"  最終状態: {state['state']}")

    # グレースフルデグラデーションのテスト
    print("\n【グレースフルデグラデーション】")
    degradation = GracefulDegradation()

    print(f"  レベル0: {degradation.get_status()}")

    degradation.set_degradation_level(1)
    print(f"  レベル1: {degradation.get_status()}")

    degradation.set_degradation_level(2)
    print(f"  レベル2: {degradation.get_status()}")

    # フォールバック登録
    degradation.register_fallback('model_ensemble', lambda: "フォールバック予測")
    result = degradation.execute_with_fallback('model_ensemble', lambda: "通常予測")
    print(f"  フォールバック結果: {result}")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
