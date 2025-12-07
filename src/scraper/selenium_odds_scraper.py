"""
Seleniumベース オッズスクレイパー
JavaScriptで動的にレンダリングされるオッズデータを取得
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import re


class SeleniumOddsScraper:
    """Seleniumを使ったオッズ取得クラス"""

    def __init__(self, headless: bool = True, wait_timeout: int = 10):
        """
        初期化

        Args:
            headless: ヘッドレスモードで実行するか
            wait_timeout: 要素待機のタイムアウト（秒）
        """
        self.headless = headless
        self.wait_timeout = wait_timeout
        self.driver = None
        self.base_url = "https://www.boatrace.jp/owpc/pc/race/oddstf"

    def _init_driver(self):
        """WebDriverを初期化"""
        if self.driver is not None:
            return

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless=new')  # 新しいヘッドレスモード
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--lang=ja')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--remote-debugging-port=9222')

        # ログレベルを抑制
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(30)
            print("[INFO] Chrome WebDriver初期化成功")
        except Exception as e:
            print(f"[ERROR] Chrome WebDriver初期化失敗: {e}")
            raise

    def get_trifecta_odds(self, venue_code: str, race_date: str, race_number: int) -> dict:
        """
        3連単オッズを取得

        Args:
            venue_code: 競艇場コード（2桁の文字列、例: '01'）
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号

        Returns:
            {'1-2-3': 12.5, '1-2-4': 25.3, ...} or None
        """
        self._init_driver()

        # URLパラメータを構築
        url = f"{self.base_url}?rno={race_number}&jcd={venue_code.zfill(2)}&hd={race_date.replace('-', '')}"
        print(f"[INFO] アクセス中: {url}")

        try:
            self.driver.get(url)

            # ページが完全に読み込まれるまで待機
            time.sleep(2)  # 初期待機

            # JavaScriptが実行されるまで待機
            WebDriverWait(self.driver, self.wait_timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

            # オッズテーブルが表示されるまで待機
            try:
                # テーブル要素を待機
                WebDriverWait(self.driver, self.wait_timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
                )
            except TimeoutException:
                print("[WARNING] テーブル要素が見つかりませんでした")

            # 追加待機（動的コンテンツの完全読み込み）
            time.sleep(3)

            # ページソースを取得して解析
            page_source = self.driver.page_source
            odds_data = self._parse_trifecta_odds(page_source)

            if odds_data:
                print(f"[OK] 3連単オッズ取得成功: {len(odds_data)}通り")
            else:
                print("[WARNING] オッズデータが見つかりませんでした")
                # デバッグ: ページタイトルを確認
                title = self.driver.title
                print(f"[DEBUG] ページタイトル: {title}")

            return odds_data

        except TimeoutException:
            print("[ERROR] ページ読み込みタイムアウト")
            return None
        except Exception as e:
            print(f"[ERROR] オッズ取得エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _parse_trifecta_odds(self, html: str) -> dict:
        """
        HTMLから3連単オッズを解析

        Args:
            html: ページのHTMLソース

        Returns:
            オッズ辞書 or None
        """
        from bs4 import BeautifulSoup

        odds_data = {}
        soup = BeautifulSoup(html, 'lxml')

        try:
            # 方法1: テーブルからオッズを取得
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')

                for row in rows:
                    tds = row.find_all('td')

                    if len(tds) < 2:
                        continue

                    # 各セルを調査
                    combination = None
                    odds_value = None

                    for td in tds:
                        text = td.get_text(strip=True)

                        # 組番パターン: "1-2-3" または "1-2-3"形式
                        if not combination:
                            match = re.match(r'^(\d)-(\d)-(\d)$', text)
                            if match:
                                parts = [match.group(1), match.group(2), match.group(3)]
                                if all(1 <= int(p) <= 6 for p in parts):
                                    combination = text

                        # オッズパターン: 数値
                        if combination and not odds_value:
                            # カンマを除去して数値化を試みる
                            clean_text = text.replace(',', '').replace('円', '').replace('倍', '').strip()
                            if clean_text:
                                try:
                                    val = float(clean_text)
                                    if 1.0 <= val <= 99999.0:
                                        odds_value = val
                                except ValueError:
                                    pass

                    if combination and odds_value:
                        odds_data[combination] = odds_value

            # 方法2: 特定のクラスを持つ要素から取得
            if not odds_data:
                # oddsテーブルのクラスを探す
                odds_tables = soup.find_all('table', class_=re.compile(r'odds|trifecta', re.I))
                for table in odds_tables:
                    tbody = table.find('tbody')
                    if tbody:
                        rows = tbody.find_all('tr')
                        for row in rows:
                            cols = row.find_all(['td', 'th'])
                            if len(cols) >= 2:
                                combo_text = cols[0].get_text(strip=True)
                                odds_text = cols[1].get_text(strip=True)

                                match = re.match(r'^(\d)-(\d)-(\d)$', combo_text)
                                if match:
                                    try:
                                        odds_val = float(odds_text.replace(',', ''))
                                        if 1.0 <= odds_val <= 99999.0:
                                            odds_data[combo_text] = odds_val
                                    except ValueError:
                                        pass

            # 方法3: 全テキストからパターンマッチング
            if not odds_data:
                # 「1-2-3」の後に数値が続くパターンを探す
                pattern = re.compile(r'(\d)-(\d)-(\d)\s*[:\s]*(\d+(?:,\d{3})*(?:\.\d+)?)')
                all_text = soup.get_text()
                matches = pattern.findall(all_text)

                for match in matches:
                    combo = f"{match[0]}-{match[1]}-{match[2]}"
                    try:
                        odds_val = float(match[3].replace(',', ''))
                        if 1.0 <= odds_val <= 99999.0:
                            # 重複を避けるため、既存の値より小さい場合のみ上書き
                            if combo not in odds_data or odds_val < odds_data[combo]:
                                odds_data[combo] = odds_val
                    except ValueError:
                        pass

        except Exception as e:
            print(f"[ERROR] HTMLパース失敗: {e}")
            import traceback
            traceback.print_exc()

        return odds_data if odds_data else None

    def get_exacta_odds(self, venue_code: str, race_date: str, race_number: int) -> dict:
        """
        2連単オッズを取得

        Args:
            venue_code: 競艇場コード（2桁の文字列、例: '01'）
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号

        Returns:
            {'1-2': 3.5, '1-3': 5.2, ...} or None
        """
        self._init_driver()

        # 2連単オッズページのURL
        url = f"https://www.boatrace.jp/owpc/pc/race/odds2tf?rno={race_number}&jcd={venue_code.zfill(2)}&hd={race_date.replace('-', '')}"

        try:
            self.driver.get(url)
            time.sleep(2)

            WebDriverWait(self.driver, self.wait_timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

            time.sleep(3)

            page_source = self.driver.page_source
            odds_data = self._parse_exacta_odds(page_source)

            if odds_data:
                print(f"[OK] 2連単オッズ取得成功: {len(odds_data)}通り")
            else:
                print("[WARNING] 2連単オッズが見つかりませんでした")

            return odds_data

        except Exception as e:
            print(f"[ERROR] 2連単オッズ取得エラー: {e}")
            return None

    def _parse_exacta_odds(self, html: str) -> dict:
        """
        HTMLから2連単オッズを解析

        Args:
            html: ページのHTMLソース

        Returns:
            {'1-2': 3.5, '1-3': 5.2, ...} or None
        """
        from bs4 import BeautifulSoup

        odds_data = {}
        soup = BeautifulSoup(html, 'lxml')

        try:
            # 方法1: テーブルからオッズを取得
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')

                for row in rows:
                    tds = row.find_all('td')

                    if len(tds) < 2:
                        continue

                    # 各セルを調査
                    combination = None
                    odds_value = None

                    for td in tds:
                        text = td.get_text(strip=True)

                        # 組番パターン: "1-2" 形式
                        if not combination:
                            match = re.match(r'^(\d)-(\d)$', text)
                            if match:
                                first, second = match.group(1), match.group(2)
                                if 1 <= int(first) <= 6 and 1 <= int(second) <= 6 and first != second:
                                    combination = text

                        # オッズパターン: 数値
                        if combination and not odds_value:
                            clean_text = text.replace(',', '').replace('円', '').replace('倍', '').strip()
                            if clean_text:
                                try:
                                    val = float(clean_text)
                                    if 1.0 <= val <= 9999.0:
                                        odds_value = val
                                except ValueError:
                                    pass

                    if combination and odds_value:
                        odds_data[combination] = odds_value

            # 方法2: 2連単専用のテーブル構造をパース
            # ボートレース公式サイトの2連単は6x5のマトリクス形式
            if not odds_data:
                for table in tables:
                    rows = table.find_all('tr')
                    if len(rows) >= 6:
                        for row_idx, row in enumerate(rows):
                            cells = row.find_all('td')
                            for col_idx, cell in enumerate(cells):
                                text = cell.get_text(strip=True).replace(',', '')
                                try:
                                    odds_val = float(text)
                                    if 1.0 <= odds_val <= 9999.0:
                                        # 行と列から組み合わせを推定
                                        # 1着が行、2着が列
                                        first = row_idx + 1
                                        second = col_idx + 1
                                        if 1 <= first <= 6 and 1 <= second <= 6 and first != second:
                                            combo = f"{first}-{second}"
                                            if combo not in odds_data:
                                                odds_data[combo] = odds_val
                                except ValueError:
                                    pass

            # 方法3: パターンマッチング
            if not odds_data:
                pattern = re.compile(r'(\d)-(\d)\s*[:\s]*(\d+(?:,\d{3})*(?:\.\d+)?)')
                all_text = soup.get_text()
                matches = pattern.findall(all_text)

                for match in matches:
                    first, second, odds_str = match
                    if first != second and 1 <= int(first) <= 6 and 1 <= int(second) <= 6:
                        combo = f"{first}-{second}"
                        try:
                            odds_val = float(odds_str.replace(',', ''))
                            if 1.0 <= odds_val <= 9999.0:
                                if combo not in odds_data or odds_val < odds_data[combo]:
                                    odds_data[combo] = odds_val
                        except ValueError:
                            pass

        except Exception as e:
            print(f"[ERROR] 2連単オッズパース失敗: {e}")

        return odds_data if odds_data else None

    def get_win_odds(self, venue_code: str, race_date: str, race_number: int) -> dict:
        """
        単勝オッズを取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号

        Returns:
            {1: 1.5, 2: 3.2, ...} or None
        """
        self._init_driver()

        # 単勝オッズページのURL
        url = f"https://www.boatrace.jp/owpc/pc/race/odds3t?rno={race_number}&jcd={venue_code.zfill(2)}&hd={race_date.replace('-', '')}"
        print(f"[INFO] 単勝オッズ取得中: {url}")

        try:
            self.driver.get(url)
            time.sleep(2)

            WebDriverWait(self.driver, self.wait_timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

            time.sleep(3)

            page_source = self.driver.page_source
            odds_data = self._parse_win_odds(page_source)

            if odds_data and len(odds_data) == 6:
                print(f"[OK] 単勝オッズ取得成功")
            else:
                print("[WARNING] 単勝オッズが不完全です")

            return odds_data

        except Exception as e:
            print(f"[ERROR] 単勝オッズ取得エラー: {e}")
            return None

    def _parse_win_odds(self, html: str) -> dict:
        """
        HTMLから単勝オッズを解析

        Args:
            html: ページのHTMLソース

        Returns:
            {1: odds1, 2: odds2, ...} or None
        """
        from bs4 import BeautifulSoup

        odds_data = {}
        soup = BeautifulSoup(html, 'lxml')

        try:
            # 単勝オッズテーブルを探す
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')

                for row in rows:
                    tds = row.find_all('td')
                    if len(tds) >= 2:
                        # 艇番を探す
                        pit_text = tds[0].get_text(strip=True)
                        odds_text = tds[1].get_text(strip=True)

                        # 艇番が1-6の数字かチェック
                        pit_match = re.search(r'(\d)', pit_text)
                        if pit_match:
                            pit_number = int(pit_match.group(1))
                            if 1 <= pit_number <= 6:
                                # オッズを抽出
                                odds_match = re.search(r'(\d+\.\d+)', odds_text)
                                if odds_match:
                                    odds_value = float(odds_match.group(1))
                                    if 1.0 <= odds_value <= 999.9:
                                        odds_data[pit_number] = odds_value

            # 6艇分揃っていなければパターンマッチング
            if len(odds_data) < 6:
                # テキスト全体から探す
                text = soup.get_text()
                pattern = re.compile(r'(\d)\s*号艇?\s*[:\s]*(\d+\.\d+)')
                matches = pattern.findall(text)

                for pit_str, odds_str in matches:
                    pit = int(pit_str)
                    if 1 <= pit <= 6 and pit not in odds_data:
                        odds_data[pit] = float(odds_str)

        except Exception as e:
            print(f"[ERROR] 単勝オッズパース失敗: {e}")

        return odds_data if len(odds_data) == 6 else None

    def close(self):
        """WebDriverを終了"""
        if self.driver:
            try:
                self.driver.quit()
                print("[INFO] WebDriver終了")
            except Exception as e:
                print(f"[WARNING] WebDriver終了エラー: {e}")
            finally:
                self.driver = None

    def __enter__(self):
        """コンテキストマネージャー開始"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャー終了"""
        self.close()


def test_scraper():
    """スクレイパーのテスト"""
    print("=" * 60)
    print("Selenium オッズスクレイパー テスト")
    print("=" * 60)

    with SeleniumOddsScraper(headless=True) as scraper:
        # 今日の日付を使用
        from datetime import datetime
        today = datetime.now().strftime('%Y%m%d')

        # 競艇場コード一覧（主要な場所）
        venues = [
            ('01', '桐生'),
            ('02', '戸田'),
            ('03', '江戸川'),
            ('04', '平和島'),
            ('05', '多摩川'),
        ]

        for venue_code, venue_name in venues:
            print(f"\n--- {venue_name}競艇場 ({venue_code}) ---")

            # 1Rのオッズを取得
            print("3連単オッズ取得中...")
            odds = scraper.get_trifecta_odds(venue_code, today, 1)

            if odds:
                # 人気上位5通りを表示
                sorted_odds = sorted(odds.items(), key=lambda x: x[1])[:5]
                print("人気上位5通り:")
                for combo, o in sorted_odds:
                    print(f"  {combo}: {o:.1f}倍")
                break  # 1つ成功したら終了
            else:
                print("データなし（レース未開催または終了）")

        # 単勝オッズも試す
        if odds:
            print("\n--- 単勝オッズテスト ---")
            win_odds = scraper.get_win_odds(venue_code, today, 1)
            if win_odds:
                print("単勝オッズ:")
                for pit, o in sorted(win_odds.items()):
                    print(f"  {pit}号艇: {o:.1f}倍")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)


if __name__ == "__main__":
    test_scraper()
