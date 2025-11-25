"""
スクレイパー基底クラス v2
selectolax対応版
"""

import requests
import time
import random
from selectolax.parser import HTMLParser

from .scraper_result import ScraperResult, ScraperStatus, RaceScraperResult


class BaseScraperV2:
    """selectolax対応のスクレイパー基底クラス"""

    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'
    ]

    def __init__(self, min_delay=0.3, max_delay=0.8):
        """
        初期化

        Args:
            min_delay: 最小待機時間（秒）
            max_delay: 最大待機時間（秒）
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.last_request_time = 0

    def _wait(self):
        """リクエスト間の待機"""
        elapsed = time.time() - self.last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)

        if elapsed < delay:
            time.sleep(delay - elapsed)

        self.last_request_time = time.time()

    def _get_headers(self):
        """リクエストヘッダーを生成"""
        return {
            'User-Agent': random.choice(self.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

    def fetch_page(self, url, params=None, max_retries=3):
        """
        URLからHTMLを取得してselectolaxのHTMLParserオブジェクトを返す

        Args:
            url: 取得するURL
            params: URLパラメータ
            max_retries: 最大リトライ回数

        Returns:
            HTMLParserオブジェクト or None
        """
        for attempt in range(max_retries):
            try:
                self._wait()

                response = requests.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=15  # タイムアウトを15秒に延長
                )

                if response.status_code == 200:
                    # selectolax HTMLParser で解析
                    tree = HTMLParser(response.text)
                    return tree
                elif response.status_code == 429:
                    # Too Many Requests - 待機時間を増やして再試行
                    wait_time = (attempt + 1) * 10
                    print(f"429エラー: {wait_time}秒待機...")
                    time.sleep(wait_time)
                    continue
                elif response.status_code == 404:
                    # Not Found - リトライしない
                    return None
                else:
                    print(f"HTTPエラー {response.status_code}: {url}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    return None

            except requests.exceptions.Timeout:
                print(f"タイムアウト ({attempt + 1}/{max_retries}): {url}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
            except Exception as e:
                print(f"リクエストエラー ({attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None

        return None

    def fetch_race_data(self, venue_code, date_str, race_number):
        """
        レースデータを取得する共通インターフェース
        継承クラスで実装する場合はオーバーライドする

        Args:
            venue_code: 会場コード
            date_str: 日付文字列（YYYYMMDD）
            race_number: レース番号

        Returns:
            レースデータの辞書 or None
        """
        # デフォルトはget_race_cardを呼び出す
        if hasattr(self, 'get_race_card'):
            return self.get_race_card(venue_code, date_str, race_number)
        return None

    def close(self):
        """
        リソースをクローズ
        BaseScraperV2は requests.get() を直接使用するため、特に何もしない
        """
        pass

    def fetch_with_result(self, url, params=None, max_retries=3) -> ScraperResult:
        """
        URLからHTMLを取得してScraperResultで返す（統一インターフェース）

        Args:
            url: 取得するURL
            params: URLパラメータ
            max_retries: 最大リトライ回数

        Returns:
            ScraperResult
        """
        start_time = time.time()
        last_error = None

        for attempt in range(max_retries):
            try:
                self._wait()

                response = requests.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=10
                )

                elapsed = time.time() - start_time

                if response.status_code == 200:
                    tree = HTMLParser(response.text)
                    return ScraperResult.success(
                        data=tree,
                        url=url,
                        elapsed=elapsed
                    )
                elif response.status_code == 429:
                    wait_time = (attempt + 1) * 10
                    time.sleep(wait_time)
                    last_error = f"レート制限 (429)"
                    continue
                elif response.status_code == 404:
                    return ScraperResult.no_data(url=url, message="ページが見つかりません (404)")
                elif response.status_code >= 500:
                    last_error = f"サーバーエラー ({response.status_code})"
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return ScraperResult.error(
                        status=ScraperStatus.SERVER_ERROR,
                        message=last_error,
                        url=url,
                        retry_count=attempt + 1
                    )
                else:
                    last_error = f"HTTPエラー ({response.status_code})"
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue

            except requests.exceptions.Timeout:
                last_error = "タイムアウト"
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return ScraperResult.error(
                    status=ScraperStatus.TIMEOUT,
                    message=last_error,
                    url=url,
                    retry_count=attempt + 1
                )
            except requests.exceptions.ConnectionError as e:
                last_error = f"接続エラー: {str(e)}"
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return ScraperResult.error(
                    status=ScraperStatus.NETWORK_ERROR,
                    message=last_error,
                    url=url,
                    retry_count=attempt + 1
                )
            except Exception as e:
                last_error = f"予期しないエラー: {str(e)}"
                return ScraperResult.error(
                    status=ScraperStatus.UNKNOWN_ERROR,
                    message=last_error,
                    url=url,
                    retry_count=attempt + 1
                )

        # 全リトライ失敗
        elapsed = time.time() - start_time
        return ScraperResult.error(
            status=ScraperStatus.UNKNOWN_ERROR,
            message=last_error or "最大リトライ回数に到達",
            url=url,
            retry_count=max_retries
        )

    def fetch_race_with_result(
        self,
        venue_code: str,
        date_str: str,
        race_number: int
    ) -> RaceScraperResult:
        """
        レースデータを取得して統一結果で返す

        Args:
            venue_code: 会場コード
            date_str: 日付文字列（YYYYMMDD）
            race_number: レース番号

        Returns:
            RaceScraperResult
        """
        start_time = time.time()

        try:
            # 既存のfetch_race_dataを呼び出し
            data = self.fetch_race_data(venue_code, date_str, race_number)
            elapsed = time.time() - start_time

            if data is None:
                return RaceScraperResult(
                    status=ScraperStatus.NO_DATA,
                    error_message="データが見つかりませんでした",
                    venue_code=venue_code,
                    race_date=date_str,
                    race_number=race_number,
                    elapsed_seconds=elapsed
                )
            else:
                return RaceScraperResult(
                    status=ScraperStatus.SUCCESS,
                    data=data,
                    venue_code=venue_code,
                    race_date=date_str,
                    race_number=race_number,
                    elapsed_seconds=elapsed
                )

        except Exception as e:
            elapsed = time.time() - start_time
            return RaceScraperResult(
                status=ScraperStatus.UNKNOWN_ERROR,
                error_message=str(e),
                venue_code=venue_code,
                race_date=date_str,
                race_number=race_number,
                elapsed_seconds=elapsed
            )
