"""
スクレイパー結果クラス

改善点_1118.md ⑦ スクレイパー例外処理の統一
戻り値フォーマットを統一し、エラーハンドリングを標準化
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum


class ScraperStatus(Enum):
    """スクレイパー実行状態"""
    SUCCESS = "success"           # 成功
    NO_DATA = "no_data"          # データなし（404など）
    TIMEOUT = "timeout"          # タイムアウト
    RATE_LIMITED = "rate_limited"  # レート制限
    SERVER_ERROR = "server_error"  # サーバーエラー
    PARSE_ERROR = "parse_error"   # パースエラー
    NETWORK_ERROR = "network_error"  # ネットワークエラー
    UNKNOWN_ERROR = "unknown_error"  # その他のエラー


@dataclass
class ScraperResult:
    """
    スクレイパーの統一結果クラス

    全てのスクレイパーはこのクラスのインスタンスを返すことで、
    呼び出し元でのエラーハンドリングを統一できる
    """
    status: ScraperStatus
    data: Optional[Any] = None
    error_message: Optional[str] = None
    url: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    elapsed_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """成功かどうか"""
        return self.status == ScraperStatus.SUCCESS

    @property
    def is_error(self) -> bool:
        """エラーかどうか"""
        return self.status not in [ScraperStatus.SUCCESS, ScraperStatus.NO_DATA]

    @property
    def should_retry(self) -> bool:
        """リトライすべきかどうか"""
        return self.status in [
            ScraperStatus.TIMEOUT,
            ScraperStatus.RATE_LIMITED,
            ScraperStatus.SERVER_ERROR,
            ScraperStatus.NETWORK_ERROR
        ]

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            'status': self.status.value,
            'data': self.data,
            'error_message': self.error_message,
            'url': self.url,
            'timestamp': self.timestamp.isoformat(),
            'retry_count': self.retry_count,
            'elapsed_seconds': self.elapsed_seconds,
            'metadata': self.metadata
        }

    @staticmethod
    def success(data: Any, url: str = None, elapsed: float = 0.0, **metadata) -> 'ScraperResult':
        """成功結果を作成"""
        return ScraperResult(
            status=ScraperStatus.SUCCESS,
            data=data,
            url=url,
            elapsed_seconds=elapsed,
            metadata=metadata
        )

    @staticmethod
    def no_data(url: str = None, message: str = None) -> 'ScraperResult':
        """データなし結果を作成"""
        return ScraperResult(
            status=ScraperStatus.NO_DATA,
            url=url,
            error_message=message or "データが見つかりませんでした"
        )

    @staticmethod
    def error(
        status: ScraperStatus,
        message: str,
        url: str = None,
        retry_count: int = 0
    ) -> 'ScraperResult':
        """エラー結果を作成"""
        return ScraperResult(
            status=status,
            error_message=message,
            url=url,
            retry_count=retry_count
        )


@dataclass
class RaceScraperResult(ScraperResult):
    """レースデータ用の拡張結果クラス"""
    venue_code: Optional[str] = None
    race_date: Optional[str] = None
    race_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        result = super().to_dict()
        result.update({
            'venue_code': self.venue_code,
            'race_date': self.race_date,
            'race_number': self.race_number
        })
        return result


class ScraperResultCollector:
    """複数のスクレイパー結果を集約するクラス"""

    def __init__(self):
        self.results: List[ScraperResult] = []

    def add(self, result: ScraperResult):
        """結果を追加"""
        self.results.append(result)

    def get_success_count(self) -> int:
        """成功数を取得"""
        return sum(1 for r in self.results if r.is_success)

    def get_error_count(self) -> int:
        """エラー数を取得"""
        return sum(1 for r in self.results if r.is_error)

    def get_no_data_count(self) -> int:
        """データなし数を取得"""
        return sum(1 for r in self.results if r.status == ScraperStatus.NO_DATA)

    def get_success_data(self) -> List[Any]:
        """成功したデータのリストを取得"""
        return [r.data for r in self.results if r.is_success and r.data is not None]

    def get_errors(self) -> List[ScraperResult]:
        """エラー結果のリストを取得"""
        return [r for r in self.results if r.is_error]

    def get_summary(self) -> Dict[str, Any]:
        """集約サマリーを取得"""
        status_counts = {}
        for result in self.results:
            status = result.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        total_elapsed = sum(r.elapsed_seconds for r in self.results)

        return {
            'total': len(self.results),
            'success': self.get_success_count(),
            'errors': self.get_error_count(),
            'no_data': self.get_no_data_count(),
            'status_counts': status_counts,
            'total_elapsed_seconds': total_elapsed,
            'average_elapsed_seconds': total_elapsed / len(self.results) if self.results else 0
        }

    def print_summary(self):
        """サマリーを表示"""
        summary = self.get_summary()
        print("=" * 50)
        print("スクレイピング結果サマリー")
        print("=" * 50)
        print(f"総数: {summary['total']}")
        print(f"成功: {summary['success']}")
        print(f"エラー: {summary['errors']}")
        print(f"データなし: {summary['no_data']}")
        print(f"合計時間: {summary['total_elapsed_seconds']:.2f}秒")
        print(f"平均時間: {summary['average_elapsed_seconds']:.2f}秒")

        if summary['status_counts']:
            print("\nステータス別内訳:")
            for status, count in sorted(summary['status_counts'].items()):
                print(f"  {status}: {count}")


def wrap_scraper_call(func):
    """
    スクレイパー関数をラップしてScraperResultを返すデコレータ

    Usage:
        @wrap_scraper_call
        def fetch_data(url):
            # 既存の実装（成功時はデータ、失敗時はNone）
            return data
    """
    import functools
    import time

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time

            if result is None:
                return ScraperResult.no_data(elapsed_seconds=elapsed)
            else:
                return ScraperResult.success(data=result, elapsed=elapsed)

        except Exception as e:
            elapsed = time.time() - start_time
            error_type = type(e).__name__

            # エラータイプに応じたステータス
            if 'Timeout' in error_type:
                status = ScraperStatus.TIMEOUT
            elif 'Connection' in error_type or 'Network' in error_type:
                status = ScraperStatus.NETWORK_ERROR
            else:
                status = ScraperStatus.UNKNOWN_ERROR

            return ScraperResult.error(
                status=status,
                message=f"{error_type}: {str(e)}",
                elapsed_seconds=elapsed
            )

    return wrapper


if __name__ == "__main__":
    # テスト
    print("ScraperResult テスト")
    print("-" * 40)

    # 成功結果
    success = ScraperResult.success(
        data={'race_id': 1, 'entries': []},
        url='https://example.com/race/1',
        elapsed=1.5,
        venue_code='01',
        race_date='2025-01-01'
    )
    print(f"Success: {success.is_success}, {success.status.value}")

    # エラー結果
    error = ScraperResult.error(
        status=ScraperStatus.TIMEOUT,
        message="Connection timed out",
        url='https://example.com/race/2',
        retry_count=3
    )
    print(f"Error: {error.is_error}, {error.status.value}")
    print(f"Should retry: {error.should_retry}")

    # コレクター
    collector = ScraperResultCollector()
    collector.add(success)
    collector.add(error)
    collector.add(ScraperResult.no_data(url='https://example.com/race/3'))

    print("\n")
    collector.print_summary()
