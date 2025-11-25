"""
潮位データスクレイパー（ブラウザ自動化版・改良版）
気象庁Webページから満潮・干潮データを取得
直接URL構築方式で確実にデータを取得
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import time
import re


class TideBrowserScraper:
    """気象庁Webページから潮位データを取得（Selenium使用・改良版）"""

    # 競艇場 -> 気象庁観測地点のマッピング
    VENUE_TO_STATION = {
        '15': {'name': '児島', 'station': '宇野', 'station_code': 'UN'},
        '16': {'name': '鳴門', 'station': '小松島', 'station_code': 'KM'},
        '17': {'name': '丸亀', 'station': '高松', 'station_code': 'TM'},
        '18': {'name': '児島', 'station': '広島', 'station_code': 'HS'},
        '20': {'name': '若松', 'station': '博多', 'station_code': 'HK'},
        '22': {'name': '福岡', 'station': '博多', 'station_code': 'HK'},
        '24': {'name': '大村', 'station': '長崎', 'station_code': 'NG'}
    }

    def __init__(self, headless=True, delay=2.0):
        """
        初期化

        Args:
            headless: ヘッドレスモードで実行するか
            delay: リクエスト間の待機時間（秒）
        """
        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--log-level=3')

        # webdriver-managerを使用してChromeDriverを自動管理
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)
        self.delay = delay
        self.base_url = "https://www.data.jma.go.jp/kaiyou/db/tide/suisan/suisan.php"

    def get_tide_data(self, venue_code, target_date):
        """
        指定日の潮位データ（満潮・干潮）を取得

        Args:
            venue_code: 競艇場コード（例: "15"）
            target_date: 対象日（datetime or "YYYY-MM-DD"）

        Returns:
            list: [
                {'time': '03:45', 'type': '満潮', 'level': 352.0},
                {'time': '10:12', 'type': '干潮', 'level': 28.0},
                ...
            ]
            海水場でない場合やエラー時は None
        """
        # 淡水場チェック
        if venue_code not in self.VENUE_TO_STATION:
            return None

        station_info = self.VENUE_TO_STATION[venue_code]
        station_code = station_info['station_code']

        # 日付を文字列に変換
        if isinstance(target_date, datetime):
            date_str = target_date.strftime('%Y-%m-%d')
        else:
            date_str = target_date

        year, month, day = date_str.split('-')

        try:
            # 直接URLを構築（GET方式）
            # 満潮・干潮データを取得するにはS_HILOパラメータが必要
            url = (f"{self.base_url}?"
                   f"stn={station_code}&"
                   f"ys={year}&ms={month.zfill(2)}&ds={day.zfill(2)}&"
                   f"ye={year}&me={month.zfill(2)}&de={day.zfill(2)}&"
                   f"S_HILO=on")  # 満潮・干潮を表示

            # ページにアクセス
            self.driver.get(url)
            time.sleep(2)

            # データを抽出
            tide_data = self._extract_tide_data()

            time.sleep(self.delay)
            return tide_data

        except Exception as e:
            print(f"潮位データ取得エラー ({venue_code}, {date_str}): {e}")
            return None

    def _extract_tide_data(self):
        """
        表示されたページから満潮・干潮データを抽出

        テーブル構造:
        年/月/日（曜日） 満潮 干潮
        時刻 潮位 時刻 潮位 時刻 潮位 時刻 潮位 時刻 潮位 時刻 潮位 時刻 潮位 時刻 潮位
        2020/10/30(金)   10:39 235 22:33 229 * * * * 4:30 59 16:46 79 * * * *

        満潮4回分、干潮4回分が交互に配置される

        Returns:
            list: 潮位データのリスト
        """
        tide_data = []

        try:
            # ページタイトルを確認
            title = self.driver.title
            if '潮位表' not in title:
                print(f"警告: 潮位表ページではありません（タイトル: {title}）")
                return None

            # すべてのテーブルを探す
            tables = self.driver.find_elements(By.TAG_NAME, "table")

            # テーブル5（満潮・干潮データテーブル）を探す
            target_table = None
            for table in tables:
                text = table.text
                # ヘッダー行に「満潮」「干潮」が含まれているテーブルを探す
                if '満潮' in text and '干潮' in text and '時刻' in text and '潮位' in text:
                    target_table = table
                    break

            if not target_table:
                print("警告: 満潮・干潮データテーブルが見つかりません")
                return None

            # テーブルの行を取得
            rows = target_table.find_elements(By.TAG_NAME, "tr")

            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")

                # データ行は18セル（日付 + 空白 + 満潮8セル + 干潮8セル）
                if len(cells) >= 18:
                    cell_texts = [cell.text.strip() for cell in cells]

                    # セル0: 日付（例: "2020/10/30(金)"）
                    # セル1: 空白（アイコン用）
                    # セル2-9: 満潮データ（時刻、潮位の4ペア）
                    # セル10-17: 干潮データ（時刻、潮位の4ペア）

                    # 満潮データを抽出（セル2-9）
                    for i in range(4):
                        time_idx = 2 + i * 2
                        level_idx = 3 + i * 2

                        if time_idx < len(cell_texts) and level_idx < len(cell_texts):
                            time_str = cell_texts[time_idx].strip()
                            level_str = cell_texts[level_idx].strip()

                            # "*" はデータなしを表す
                            if time_str and time_str != '*' and level_str and level_str != '*':
                                try:
                                    # 時刻検証
                                    if re.match(r'\d{1,2}:\d{2}', time_str):
                                        level = float(level_str)
                                        tide_data.append({
                                            'time': time_str,
                                            'type': '満潮',
                                            'level': level
                                        })
                                except ValueError:
                                    pass

                    # 干潮データを抽出（セル10-17）
                    for i in range(4):
                        time_idx = 10 + i * 2
                        level_idx = 11 + i * 2

                        if time_idx < len(cell_texts) and level_idx < len(cell_texts):
                            time_str = cell_texts[time_idx].strip()
                            level_str = cell_texts[level_idx].strip()

                            if time_str and time_str != '*' and level_str and level_str != '*':
                                try:
                                    if re.match(r'\d{1,2}:\d{2}', time_str):
                                        level = float(level_str)
                                        tide_data.append({
                                            'time': time_str,
                                            'type': '干潮',
                                            'level': level
                                        })
                                except ValueError:
                                    pass

        except Exception as e:
            print(f"データ抽出エラー: {e}")
            import traceback
            traceback.print_exc()

        return tide_data if tide_data else None

    def close(self):
        """ブラウザを閉じる"""
        try:
            self.driver.quit()
        except Exception:
            # ブラウザクリーンアップ時のエラーは無視
            pass


if __name__ == "__main__":
    # テスト実行
    scraper = TideBrowserScraper(headless=False)

    print("="*70)
    print("潮位データスクレイパーテスト（ブラウザ版・改良版）")
    print("="*70)

    # 児島（会場コード15）の2020-10-30のデータ取得（2020年データ利用可能）
    result = scraper.get_tide_data("15", "2020-10-30")

    if result:
        print("\n【潮位データ】")
        for data in result:
            print(f"  {data['time']} {data['type']}: {data['level']}cm")
    else:
        print("\nデータ取得失敗")

    scraper.close()
