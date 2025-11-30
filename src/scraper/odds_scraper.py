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
        self.base_url = "https://www.boatrace.jp/owpc/pc/race/odds3t"  # 3連単オッズ
        self.win_odds_url = "https://www.boatrace.jp/owpc/pc/race/oddstf"  # 単勝・複勝オッズ
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
        HTMLからオッズを解析（ボートレース公式1軸流し形式）

        テーブル構造（21行）：
        - Row 0: 空（ヘッダー）
        - Row 1-4: 2着=2の組み合わせ（Row1は18セル、Row2-4は12セル）
        - Row 5-8: 2着=3の組み合わせ
        - Row 9-12: 2着=4の組み合わせ
        - Row 13-16: 2着=5の組み合わせ
        - Row 17-20: 2着=6の組み合わせ

        各行のセル構造（18セル行）: [2着, 3着, オッズ] × 6（1着艇1-6）
        各行のセル構造（12セル行）: [3着, オッズ] × 6（2着は前の18セル行から継承）

        Args:
            soup: BeautifulSoup オブジェクト

        Returns:
            オッズ辞書 or None
        """
        odds_data = {}

        try:
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')
                if len(rows) < 20:
                    continue

                # 2着艇ごとのグループで処理
                second_boats = [2, 3, 4, 5, 6]
                row_idx = 1  # Row 0はヘッダー

                for second_boat in second_boats:
                    # 各2着艇のグループは4行
                    for sub_row in range(4):
                        if row_idx >= len(rows):
                            break

                        row = rows[row_idx]
                        cells = row.find_all('td')
                        row_idx += 1

                        if len(cells) < 6:
                            continue

                        # 18セル行（グループの最初の行）
                        if len(cells) >= 18:
                            for first_boat in range(1, 7):
                                base_idx = (first_boat - 1) * 3

                                try:
                                    # 2着（確認用）
                                    cell_second = int(cells[base_idx].text.strip())
                                    # 3着
                                    third_boat = int(cells[base_idx + 1].text.strip())
                                    # オッズ
                                    odds_text = cells[base_idx + 2].text.strip()
                                    odds_text = odds_text.replace(',', '').strip()
                                    if odds_text and odds_text != '-':
                                        odds_value = float(odds_text)
                                        if 1.0 <= odds_value <= 99999.0:
                                            if len(set([first_boat, cell_second, third_boat])) == 3:
                                                combination = f"{first_boat}-{cell_second}-{third_boat}"
                                                odds_data[combination] = odds_value
                                except (ValueError, IndexError):
                                    continue

                        # 12セル行（グループの2-4行目）
                        elif len(cells) >= 12:
                            for first_boat in range(1, 7):
                                base_idx = (first_boat - 1) * 2

                                try:
                                    # 3着
                                    third_boat = int(cells[base_idx].text.strip())
                                    # オッズ
                                    odds_text = cells[base_idx + 1].text.strip()
                                    odds_text = odds_text.replace(',', '').strip()
                                    if odds_text and odds_text != '-':
                                        odds_value = float(odds_text)
                                        if 1.0 <= odds_value <= 99999.0:
                                            # 2着はグループの2着艇、ただし1着と同じならスキップ
                                            actual_second = second_boat
                                            if first_boat == second_boat:
                                                # 1着=2着の場合、別の艇を2着とする
                                                continue
                                            if len(set([first_boat, actual_second, third_boat])) == 3:
                                                combination = f"{first_boat}-{actual_second}-{third_boat}"
                                                odds_data[combination] = odds_value
                                except (ValueError, IndexError):
                                    continue

                if len(odds_data) >= 100:
                    break

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

    def get_win_odds(self, venue_code, race_date, race_number):
        """
        単勝オッズを取得

        Args:
            venue_code: 競艇場コード（2桁の文字列、例: '01'）
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号

        Returns:
            {1: 1.5, 2: 3.2, 3: 5.8, 4: 12.5, 5: 18.0, 6: 35.0} or None
        """
        params = {
            'rno': race_number,
            'jcd': venue_code.zfill(2),
            'hd': race_date.replace('-', '')
        }

        for attempt in range(self.max_retries):
            try:
                time.sleep(self.delay)

                response = self.session.get(
                    self.win_odds_url,
                    params=params,
                    timeout=30
                )
                response.encoding = response.apparent_encoding

                if response.status_code != 200:
                    print(f"[WARNING] 単勝オッズ取得失敗: HTTP {response.status_code}（試行 {attempt + 1}/{self.max_retries}）")
                    if response.status_code in [500, 502, 503, 504] and attempt < self.max_retries - 1:
                        wait_time = self.delay * (2 ** attempt)
                        time.sleep(wait_time)
                        continue
                    return None

                soup = BeautifulSoup(response.text, 'lxml')

                # タイトルチェック
                title = soup.find('title')
                if title and ('エラー' in title.text or 'データがありません' in title.text):
                    print(f"[INFO] 単勝オッズ未発表: {venue_code} {race_date} {race_number}R")
                    return None

                # 単勝オッズを解析
                odds_data = self._parse_win_odds(soup)

                if odds_data and len(odds_data) == 6:
                    print(f"[OK] 単勝オッズ取得成功: {venue_code} {race_date} {race_number}R")
                    return odds_data

                print(f"[WARNING] 単勝オッズデータが不完全（試行 {attempt + 1}/{self.max_retries}）")
                if attempt < self.max_retries - 1:
                    wait_time = self.delay * (2 ** attempt)
                    time.sleep(wait_time)

            except Exception as e:
                print(f"[ERROR] 単勝オッズ取得エラー: {e}（試行 {attempt + 1}/{self.max_retries}）")
                if attempt < self.max_retries - 1:
                    time.sleep(self.delay * (2 ** attempt))

        print(f"[ERROR] 単勝オッズ取得失敗: {venue_code} {race_date} {race_number}R")
        return None

    def _parse_win_odds(self, soup):
        """
        HTMLから単勝オッズを解析

        Args:
            soup: BeautifulSoup オブジェクト

        Returns:
            {1: odds1, 2: odds2, ...} or None
        """
        odds_data = {}

        try:
            # 方法1: oddsTableクラスのテーブルから取得
            odds_table = soup.find('table', class_='is-w748')
            if odds_table:
                rows = odds_table.find_all('tr', class_='oddsPoint')
                for row in rows:
                    # 艇番を取得
                    num_td = row.find('td', class_='is-boatColor1-1')
                    if not num_td:
                        num_td = row.find('td', class_=re.compile(r'is-boatColor\d'))

                    # オッズを取得
                    odds_td = row.find('td', class_='oddsPoint__odd')

                    if num_td and odds_td:
                        pit_text = num_td.get_text(strip=True)
                        odds_text = odds_td.get_text(strip=True)

                        try:
                            pit_number = int(re.search(r'\d', pit_text).group())
                            odds_value = float(re.search(r'\d+\.\d+', odds_text).group())
                            odds_data[pit_number] = odds_value
                        except (AttributeError, ValueError):
                            continue

            # 方法2: tbodyから直接取得
            if not odds_data:
                tbody = soup.find('tbody', class_='is-oddsList')
                if tbody:
                    rows = tbody.find_all('tr')
                    for i, row in enumerate(rows, 1):
                        tds = row.find_all('td')
                        if len(tds) >= 2:
                            odds_text = tds[1].get_text(strip=True)
                            try:
                                odds_value = float(re.search(r'\d+\.\d+', odds_text).group())
                                odds_data[i] = odds_value
                            except (AttributeError, ValueError):
                                continue

            # 方法3: テーブルから艇番とオッズを探す（新規追加）
            if not odds_data:
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        tds = row.find_all('td')
                        if len(tds) >= 3:
                            # 1列目が数字（艇番）、3列目がオッズの可能性
                            first_text = tds[0].get_text(strip=True)
                            if first_text.isdigit() and 1 <= int(first_text) <= 6:
                                pit = int(first_text)
                                # 3列目からオッズを抽出
                                odds_text = tds[2].get_text(strip=True) if len(tds) > 2 else ''
                                odds_match = re.search(r'(\d+\.\d+)', odds_text)
                                if odds_match:
                                    odds_value = float(odds_match.group(1))
                                    if 1.0 <= odds_value <= 999.9 and pit not in odds_data:
                                        odds_data[pit] = odds_value

            # 方法4: パターンマッチング
            if not odds_data or len(odds_data) < 6:
                # テキスト全体から「1号艇: X.X倍」のようなパターンを探す
                text = soup.get_text()
                pattern = re.compile(r'(\d)\s*号.*?(\d+\.\d+)')
                matches = pattern.findall(text)
                for pit_str, odds_str in matches[:6]:
                    try:
                        pit = int(pit_str)
                        odds = float(odds_str)
                        if 1 <= pit <= 6 and 1.0 <= odds <= 999.9 and pit not in odds_data:
                            odds_data[pit] = odds
                    except ValueError:
                        continue

        except Exception as e:
            print(f"[ERROR] 単勝オッズ解析エラー: {e}")
            import traceback
            traceback.print_exc()

        return odds_data if len(odds_data) == 6 else None

    def close(self):
        """リソースクローズ（現在は何もしない）"""
        pass
