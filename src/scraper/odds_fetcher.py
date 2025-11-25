"""
オッズデータ取得モジュール

公式のオッズAPI（または非公式）からリアルタイムオッズを取得
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional
import re
import time


class OddsFetcher:
    """
    オッズデータ取得クラス

    BOAT RACE公式サイトからオッズをスクレイピング
    """

    BASE_URL = "https://www.boatrace.jp/owpc/pc/race"

    def __init__(self, delay: float = 1.0, max_retries: int = 3):
        """
        初期化

        Args:
            delay: リクエスト間の遅延時間（秒）
            max_retries: 最大リトライ回数
        """
        self.delay = delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Referer': 'https://www.boatrace.jp/'
        })

    def fetch_sanrentan_odds(
        self,
        race_date: str,
        venue_code: str,
        race_number: int
    ) -> Dict[str, float]:
        """
        三連単オッズを取得（リトライ・指数バックオフ対応）

        Args:
            race_date: レース日（YYYYMMDD）
            venue_code: 会場コード（01-24）
            race_number: レース番号

        Returns:
            Dict[str, float]: オッズデータ {'1-2-3': 8.5, '1-3-2': 12.3, ...}
        """
        # URLパラメータ
        params = {
            'rno': race_number,
            'jcd': venue_code.zfill(2),
            'hd': race_date.replace('-', '')
        }

        # オッズページURL
        url = f"{self.BASE_URL}/odds3t"

        # リトライ処理（指数バックオフ）
        for attempt in range(self.max_retries):
            try:
                # リクエスト実行
                time.sleep(self.delay)
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, 'html.parser')

                odds_data = {}

                # オッズデータの抽出
                # パターン1: oddsBoxクラスを探索
                odds_boxes = soup.find_all('div', class_=re.compile(r'oddsBox|odds3t'))

                if not odds_boxes:
                    # パターン2: テーブルを直接探索
                    odds_tables = soup.find_all('table', class_=re.compile(r'is-w\d+|odds'))

                    if not odds_tables:
                        # パターン3: 全てのtableを探索
                        odds_tables = soup.find_all('table')

                    for table in odds_tables:
                        rows = table.find_all('tr')
                        for row in rows:
                            cols = row.find_all('td')
                            if len(cols) >= 2:
                                combination_text = cols[0].get_text(strip=True)
                                odds_text = cols[1].get_text(strip=True)

                                # 組み合わせ形式: "1-2-3" or "123" or "1 2 3"
                                match = re.search(r'(\d)[-\s]?(\d)[-\s]?(\d)', combination_text)

                                if match:
                                    combination = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

                                    # オッズを抽出
                                    try:
                                        odds = float(odds_text.replace(',', '').replace('倍', ''))
                                        odds_data[combination] = odds
                                    except ValueError:
                                        continue
                else:
                    # oddsBoxから抽出
                    for box in odds_boxes:
                        # 組み合わせとオッズのペアを探索
                        combo_elements = box.find_all(string=re.compile(r'\d-\d-\d|\d\d\d'))
                        odds_elements = box.find_all(string=re.compile(r'[\d,]+\.?\d*'))

                        for combo_text, odds_text in zip(combo_elements, odds_elements):
                            match = re.search(r'(\d)[-\s]?(\d)[-\s]?(\d)', combo_text)
                            if match:
                                combination = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                                try:
                                    odds = float(odds_text.replace(',', '').replace('倍', ''))
                                    odds_data[combination] = odds
                                except ValueError:
                                    continue

                # データが取得できた場合は成功
                if odds_data:
                    print(f"[OK] オッズ取得成功: {len(odds_data)}件")
                    return odds_data

                # データが空の場合、リトライ
                print(f"[WARNING] オッズデータが空です（試行 {attempt + 1}/{self.max_retries}）")

                if attempt < self.max_retries - 1:
                    # 指数バックオフ
                    wait_time = self.delay * (2 ** attempt)
                    print(f"[INFO] {wait_time:.1f}秒後にリトライします...")
                    time.sleep(wait_time)

            except requests.Timeout:
                print(f"[ERROR] タイムアウト（試行 {attempt + 1}/{self.max_retries}）")
                if attempt < self.max_retries - 1:
                    wait_time = self.delay * (2 ** attempt)
                    time.sleep(wait_time)

            except requests.RequestException as e:
                print(f"[ERROR] リクエストエラー: {e}（試行 {attempt + 1}/{self.max_retries}）")
                if attempt < self.max_retries - 1:
                    wait_time = self.delay * (2 ** attempt)
                    time.sleep(wait_time)

            except Exception as e:
                print(f"[ERROR] 解析エラー: {e}")
                import traceback
                traceback.print_exc()
                return {}

        # 全てのリトライが失敗
        print("[ERROR] 全てのリトライが失敗しました。モックオッズを使用してください。")
        return {}

    def fetch_sanrentan_odds_top(
        self,
        race_date: str,
        venue_code: str,
        race_number: int,
        top_n: int = 10
    ) -> Dict[str, float]:
        """
        三連単オッズの上位N件を取得（軽量版）

        Args:
            race_date: レース日（YYYYMMDD）
            venue_code: 会場コード
            race_number: レース番号
            top_n: 取得する上位件数

        Returns:
            Dict[str, float]: 上位オッズデータ
        """
        all_odds = self.fetch_sanrentan_odds(race_date, venue_code, race_number)

        # オッズ昇順でソート
        sorted_odds = sorted(all_odds.items(), key=lambda x: x[1])

        return dict(sorted_odds[:top_n])

    def fetch_odds_for_combinations(
        self,
        race_date: str,
        venue_code: str,
        race_number: int,
        combinations: list
    ) -> Dict[str, float]:
        """
        指定された組み合わせのオッズのみを取得

        Args:
            race_date: レース日
            venue_code: 会場コード
            race_number: レース番号
            combinations: 組み合わせリスト ['1-2-3', '1-3-2', ...]

        Returns:
            Dict[str, float]: 指定組み合わせのオッズ
        """
        all_odds = self.fetch_sanrentan_odds(race_date, venue_code, race_number)

        # 指定された組み合わせのみフィルター
        filtered_odds = {
            combo: all_odds.get(combo, 100.0)  # 見つからない場合は100倍（低人気）
            for combo in combinations
        }

        return filtered_odds


def generate_mock_odds(predictions: list) -> Dict[str, float]:
    """
    モックオッズを生成（APIが使えない場合のフォールバック）

    Args:
        predictions: 予測データ [{'combination': '1-2-3', 'prob': 0.15}, ...]

    Returns:
        Dict[str, float]: オッズデータ
    """
    odds_data = {}

    for pred in predictions:
        combination = pred['combination']
        prob = pred['prob']

        # 市場効率80%と仮定してオッズを逆算
        implied_prob = prob * 0.8
        if implied_prob > 0:
            odds_data[combination] = 1.0 / implied_prob
        else:
            odds_data[combination] = 100.0

    return odds_data


if __name__ == "__main__":
    # テスト実行
    fetcher = OddsFetcher()

    # 例: 2025年11月2日、桐生（01）、1R
    odds = fetcher.fetch_sanrentan_odds_top(
        race_date='20251102',
        venue_code='01',
        race_number=1,
        top_n=10
    )

    print(f"取得したオッズ: {len(odds)}件")
    for combo, odd in list(odds.items())[:5]:
        print(f"{combo}: {odd}倍")
