"""
オッズスクレイパー
競艇公式サイトから3連単オッズを取得

改善点:
- リトライ機能（指数バックオフ）
- セッション管理でパフォーマンス向上
- 複数のHTML解析パターン対応
- 詳細なログ出力
"""

import requests
from bs4 import BeautifulSoup
import time
import re


class OddsScraper:
    """オッズ取得クラス（リトライ・指数バックオフ対応）"""

    def __init__(self, delay: float = 1.0, max_retries: int = 3):
        """
        初期化

        Args:
            delay: リクエスト間の遅延時間（秒）
            max_retries: 最大リトライ回数
        """
        self.base_url = "https://www.boatrace.jp/owpc/pc/race/oddstf"
        self.delay = delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Referer': 'https://www.boatrace.jp/'
        })

    def get_trifecta_odds(self, venue_code, race_date, race_number):
        """
        3連単オッズを取得（リトライ・指数バックオフ対応）

        Args:
            venue_code: 競艇場コード（2桁の文字列、例: '01'）
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号

        Returns:
            {
                '1-2-3': 12.5,
                '1-2-4': 25.3,
                ...
            } or None
        """
        params = {
            'rno': race_number,
            'jcd': venue_code.zfill(2),  # 2桁にゼロパディング
            'hd': race_date.replace('-', '')  # ハイフン除去
        }

        # リトライ処理（指数バックオフ）
        for attempt in range(self.max_retries):
            try:
                # リクエスト実行前の遅延
                time.sleep(self.delay)

                response = self.session.get(
                    self.base_url,
                    params=params,
                    timeout=30
                )
                response.encoding = response.apparent_encoding

                if response.status_code != 200:
                    print(f"[WARNING] オッズ取得失敗: HTTP {response.status_code}（試行 {attempt + 1}/{self.max_retries}）")

                    # リトライ可能なステータスコードの場合のみリトライ
                    if response.status_code in [500, 502, 503, 504] and attempt < self.max_retries - 1:
                        wait_time = self.delay * (2 ** attempt)
                        print(f"[INFO] {wait_time:.1f}秒後にリトライします...")
                        time.sleep(wait_time)
                        continue
                    else:
                        return None

                soup = BeautifulSoup(response.text, 'lxml')

                # データが存在するかチェック
                title = soup.find('title')
                if title and ('エラー' in title.text or 'データがありません' in title.text or 'ログイン' in title.text):
                    print(f"[INFO] オッズ未発表またはログイン必要: {venue_code} {race_date} {race_number}R")
                    return None

                # オッズデータを解析
                odds_data = self._parse_odds(soup)

                # データが取得できた場合は成功
                if odds_data:
                    print(f"[OK] オッズ取得成功: {venue_code} {race_date} {race_number}R - {len(odds_data)}通り")
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
                print(f"[ERROR] 予期しないエラー: {e}")
                import traceback
                traceback.print_exc()
                return None

        # 全てのリトライが失敗
        print(f"[ERROR] 全てのリトライが失敗しました: {venue_code} {race_date} {race_number}R")
        return None

    def _parse_odds(self, soup):
        """
        HTMLからオッズを解析（複数パターン対応）

        Args:
            soup: BeautifulSoup オブジェクト

        Returns:
            オッズ辞書 or None
        """
        odds_data = {}

        try:
            # 方法1: oddsテーブルから取得
            # 3連単は通常、tableタグに格納されている
            tables = soup.find_all('table')

            for table in tables:
                # tbody内の各行を解析
                tbody = table.find('tbody')
                if not tbody:
                    # tbodyがない場合は直接trを探索
                    rows = table.find_all('tr')
                else:
                    rows = tbody.find_all('tr')

                for row in rows:
                    tds = row.find_all('td')

                    if len(tds) < 2:
                        continue

                    # 組番とオッズを探す
                    combination = None
                    odds_value = None

                    for i, td in enumerate(tds):
                        text = td.text.strip()

                        # 組番パターン: "1-2-3"
                        if not combination and '-' in text:
                            parts = text.split('-')
                            if len(parts) == 3 and all(p.isdigit() and 1 <= int(p) <= 6 for p in parts):
                                combination = text

                        # オッズパターン: 数値
                        if combination and not odds_value:
                            try:
                                # カンマを除去して数値化
                                clean_text = text.replace(',', '').replace('円', '').replace('倍', '').strip()
                                if clean_text:
                                    odds_value = float(clean_text)
                            except ValueError:
                                continue

                    if combination and odds_value:
                        odds_data[combination] = odds_value

            # 方法2: フォールバック - データ属性から取得
            if not odds_data:
                # data-odds などの属性がある場合
                odds_elements = soup.find_all(attrs={'data-odds': True})
                for elem in odds_elements:
                    combination = elem.get('data-combination')
                    odds_value = elem.get('data-odds')
                    if combination and odds_value:
                        try:
                            odds_data[combination] = float(odds_value)
                        except ValueError:
                            continue

            # 方法3: divやspanからパターンマッチング
            if not odds_data:
                # 「1-2-3」形式の組番を探す
                combo_pattern = re.compile(r'(\d)-(\d)-(\d)')
                # オッズ数値を探す
                odds_pattern = re.compile(r'(\d+(?:,\d{3})*(?:\.\d+)?)')

                all_text = soup.get_text()
                combos = combo_pattern.findall(all_text)
                odds = odds_pattern.findall(all_text)

                # 組番とオッズをペアリング（簡易版）
                for i, combo in enumerate(combos):
                    if i < len(odds):
                        combination_str = f"{combo[0]}-{combo[1]}-{combo[2]}"
                        try:
                            odds_value = float(odds[i].replace(',', ''))
                            if 1.0 <= odds_value <= 99999.0:  # 妥当なオッズ範囲
                                odds_data[combination_str] = odds_value
                        except ValueError:
                            continue

        except Exception as e:
            print(f"[ERROR] オッズ解析エラー: {e}")
            import traceback
            traceback.print_exc()

        return odds_data if odds_data else None

    def get_all_odds_types(self, venue_code, race_date, race_number):
        """
        全オッズタイプを取得（3連単、3連複、2連単、2連複など）

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号

        Returns:
            {
                'trifecta': {...},  # 3連単
                'trio': {...},      # 3連複
                'exacta': {...},    # 2連単
                'quinella': {...}   # 2連複
            }
        """
        result = {}

        # 3連単
        result['trifecta'] = self.get_trifecta_odds(venue_code, race_date, race_number)

        # 他のオッズタイプは別URLになる可能性があるため、
        # 今回は3連単のみ実装

        return result

    def get_popular_combinations(self, venue_code, race_date, race_number, top_n=10):
        """
        人気順上位の組み合わせを取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号
            top_n: 取得件数

        Returns:
            [
                {'combination': '1-2-3', 'odds': 5.5, 'rank': 1},
                ...
            ]
        """
        odds_data = self.get_trifecta_odds(venue_code, race_date, race_number)

        if not odds_data:
            return []

        # オッズが低い順（人気順）にソート
        sorted_odds = sorted(odds_data.items(), key=lambda x: x[1])

        result = []
        for i, (combination, odds) in enumerate(sorted_odds[:top_n], 1):
            result.append({
                'combination': combination,
                'odds': odds,
                'rank': i
            })

        return result

    def close(self):
        """リソースクローズ（現在は何もしない）"""
        pass
