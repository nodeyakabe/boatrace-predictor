"""
安全性を高めたスクレイパー基底クラス

- User-Agentランダム化
- アクセス間隔ランダム化
- 429エラー対応
- リトライロジック
"""

import requests
from bs4 import BeautifulSoup
import time
import random

from .scraper_result import ScraperResult, ScraperStatus


class SafeScraperBase:
    """安全性を高めたスクレイパー基底クラス"""

    # User-Agentのリスト（実際のブラウザのもの）
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'
    ]

    def __init__(self, min_delay=0.3, max_delay=0.8, read_timeout=30):
        """
        初期化

        Args:
            min_delay: 最小待機時間（秒）
            max_delay: 最大待機時間（秒）
            read_timeout: 読み取りタイムアウト（秒）
        """
        self.session = requests.Session()
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.read_timeout = read_timeout
        self._update_user_agent()

    def _update_user_agent(self):
        """User-Agentをランダムに更新"""
        user_agent = random.choice(self.USER_AGENTS)
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

    def _random_delay(self, multiplier=1.0):
        """
        ランダムな待機時間を生成

        Args:
            multiplier: 待機時間の倍率
        """
        delay = random.uniform(self.min_delay, self.max_delay) * multiplier
        time.sleep(delay)

    def fetch_page(self, url, params=None, max_retries=3, timeout=30):
        """
        ページを取得（リトライ・エラーハンドリング付き）

        Args:
            url: URL
            params: クエリパラメータ
            max_retries: 最大リトライ回数
            timeout: タイムアウト（秒）

        Returns:
            BeautifulSoupオブジェクト or None
        """
        for attempt in range(max_retries):
            try:
                # 10リクエストごとにUser-Agentを変更
                if random.random() < 0.1:
                    self._update_user_agent()

                response = self.session.get(
                    url,
                    params=params,
                    timeout=timeout
                )

                # 429エラー（Too Many Requests）対応
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    print(f"  レート制限検知。{retry_after}秒待機...")
                    time.sleep(retry_after)
                    continue

                # 503エラー（Service Unavailable）対応
                if response.status_code == 503:
                    wait_time = min(30 * (attempt + 1), 120)  # 最大2分
                    print(f"  サーバービジー。{wait_time}秒待機...")
                    time.sleep(wait_time)
                    continue

                # 404エラーはそのまま返す（開催なし判定用）
                if response.status_code == 404:
                    return None

                # その他のエラー
                response.raise_for_status()

                # 成功時はランダムな待機
                self._random_delay()

                return BeautifulSoup(response.text, 'lxml')

            except requests.exceptions.Timeout:
                print(f"  タイムアウト（試行 {attempt + 1}/{max_retries}）")
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue

            except requests.exceptions.RequestException as e:
                print(f"  リクエストエラー: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue

            except Exception as e:
                print(f"  予期しないエラー: {e}")
                return None

        print(f"  最大リトライ回数に到達。取得失敗。")
        return None

    def close(self):
        """セッションをクローズ"""
        self.session.close()

    def fetch_page_with_result(self, url, params=None, max_retries=3, timeout=30) -> ScraperResult:
        """
        ページを取得してScraperResultで返す（統一インターフェース）

        Args:
            url: URL
            params: クエリパラメータ
            max_retries: 最大リトライ回数
            timeout: タイムアウト（秒）

        Returns:
            ScraperResult
        """
        start_time = time.time()
        last_error = None

        for attempt in range(max_retries):
            try:
                if random.random() < 0.1:
                    self._update_user_agent()

                response = self.session.get(
                    url,
                    params=params,
                    timeout=timeout
                )

                elapsed = time.time() - start_time

                # 429エラー（Too Many Requests）対応
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    time.sleep(retry_after)
                    last_error = f"レート制限 (429)"
                    continue

                # 503エラー（Service Unavailable）対応
                if response.status_code == 503:
                    wait_time = min(30 * (attempt + 1), 120)
                    time.sleep(wait_time)
                    last_error = f"サーバービジー (503)"
                    continue

                # 404エラー
                if response.status_code == 404:
                    return ScraperResult.no_data(url=url, message="ページが見つかりません (404)")

                # その他のエラー
                if response.status_code >= 400:
                    last_error = f"HTTPエラー ({response.status_code})"
                    if attempt < max_retries - 1:
                        time.sleep(5 * (attempt + 1))
                        continue
                    return ScraperResult.error(
                        status=ScraperStatus.SERVER_ERROR,
                        message=last_error,
                        url=url,
                        retry_count=attempt + 1
                    )

                # 成功
                self._random_delay()
                soup = BeautifulSoup(response.text, 'lxml')
                return ScraperResult.success(
                    data=soup,
                    url=url,
                    elapsed=elapsed
                )

            except requests.exceptions.Timeout:
                last_error = "タイムアウト"
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                return ScraperResult.error(
                    status=ScraperStatus.TIMEOUT,
                    message=last_error,
                    url=url,
                    retry_count=attempt + 1
                )

            except requests.exceptions.RequestException as e:
                last_error = f"リクエストエラー: {str(e)}"
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                return ScraperResult.error(
                    status=ScraperStatus.NETWORK_ERROR,
                    message=last_error,
                    url=url,
                    retry_count=attempt + 1
                )

            except Exception as e:
                return ScraperResult.error(
                    status=ScraperStatus.UNKNOWN_ERROR,
                    message=f"予期しないエラー: {str(e)}",
                    url=url,
                    retry_count=attempt + 1
                )

        # 全リトライ失敗
        return ScraperResult.error(
            status=ScraperStatus.UNKNOWN_ERROR,
            message=last_error or "最大リトライ回数に到達",
            url=url,
            retry_count=max_retries
        )
