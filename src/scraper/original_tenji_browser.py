"""
オリジナル展示データスクレイパー（ブラウザ自動化版）
Selenium使用
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
from datetime import datetime


class OriginalTenjiBrowserScraper:
    """Seleniumでboaters-boatrace.comからオリジナル展示データを取得"""

    # 会場コードのマッピング（公式コード → boaters-boatrace.com会場名）
    VENUE_CODE_TO_NAME = {
        '01': 'kiryu',      # 桐生
        '02': 'toda',       # 戸田
        '03': 'edogawa',    # 江戸川
        '04': 'heiwajima',  # 平和島
        '05': 'tamagawa',   # 多摩川
        '06': 'hamanako',   # 浜名湖
        '07': 'gamagori',   # 蒲郡
        '08': 'tokoname',   # 常滑
        '09': 'tsu',        # 津
        '10': 'mikuni',     # 三国
        '11': 'biwako',     # びわこ
        '12': 'suminoe',    # 住之江
        '13': 'amagasaki',  # 尼崎
        '14': 'naruto',     # 鳴門
        '15': 'marugame',   # 丸亀
        '16': 'kojima',     # 児島
        '17': 'miyajima',   # 宮島
        '18': 'tokuyama',   # 徳山
        '19': 'shimonoseki',# 下関
        '20': 'wakamatsu',  # 若松
        '21': 'ashiya',     # 芦屋
        '22': 'fukuoka',    # 福岡
        '23': 'karatsu',    # 唐津
        '24': 'omura',      # 大村
    }

    def __init__(self, headless=True, timeout=30):
        """
        初期化

        Args:
            headless: ヘッドレスモードで実行するか
            timeout: ページ読み込みタイムアウト（秒）
        """
        self.timeout = timeout
        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        chrome_options.add_argument(f'--page-load-timeout={timeout * 1000}')  # ミリ秒単位

        # webdriver-managerを使用してChromeDriverを自動管理
        try:
            import os
            # ChromeDriverManagerを使用（キャッシュをクリアして再ダウンロード）
            driver_path = ChromeDriverManager().install()

            # webdriver-managerが間違ったファイルパスを返す問題を修正
            # THIRD_PARTY_NOTICES.chromedriverではなくchromedriver.exeを指すように
            if 'THIRD_PARTY_NOTICES' in driver_path or not driver_path.endswith('.exe'):
                # ディレクトリから正しいchromedriver.exeを探す
                driver_dir = os.path.dirname(driver_path)
                correct_path = os.path.join(driver_dir, 'chromedriver.exe')

                # chromedriver-win32サブディレクトリも確認
                if not os.path.exists(correct_path):
                    win32_dir = os.path.join(driver_dir, 'chromedriver-win32')
                    if os.path.exists(win32_dir):
                        correct_path = os.path.join(win32_dir, 'chromedriver.exe')

                if os.path.exists(correct_path):
                    driver_path = correct_path

            service = Service(driver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            # フォールバック: システムのChromeDriverを使用
            try:
                self.driver = webdriver.Chrome(options=chrome_options)
            except Exception as e2:
                raise Exception(
                    f"ChromeDriverの初期化に失敗しました。\n"
                    f"エラー1: {e}\n"
                    f"エラー2: {e2}\n\n"
                    f"解決方法:\n"
                    f"1. ChromeDriverをダウンロード: https://chromedriver.chromium.org/downloads\n"
                    f"2. システムのPATHに追加\n"
                    f"3. または、以下のコマンドを実行:\n"
                    f"   pip uninstall webdriver-manager -y\n"
                    f"   pip install webdriver-manager\n"
                )

        self.wait = WebDriverWait(self.driver, 10)

    def get_original_tenji(self, venue_code, target_date, race_number):
        """
        オリジナル展示データを取得

        Args:
            venue_code: 競艇場コード（例: "20"）
            target_date: 対象日（datetime or "YYYY-MM-DD"）
            race_number: レース番号（1-12）

        Returns:
            dict: {
                1: {'chikusen_time': 6.11, 'isshu_time': 36.85, 'mawariashi_time': 5.84},
                2: {'chikusen_time': 6.29, 'isshu_time': 38.29, 'mawariashi_time': 6.63},
                ...
            }
            エラー時やデータなしの場合は None
        """
        # 会場名に変換
        if venue_code not in self.VENUE_CODE_TO_NAME:
            return None

        venue_name = self.VENUE_CODE_TO_NAME[venue_code]

        # 日付を文字列に変換
        if isinstance(target_date, datetime):
            date_str = target_date.strftime('%Y-%m-%d')
        else:
            date_str = target_date

        # URLを構築
        url = f"https://boaters-boatrace.com/race/{venue_name}/{date_str}/{race_number}R/last-minute?last-minute-content=original-tenji"

        try:
            # タイムアウト設定
            self.driver.set_page_load_timeout(self.timeout)

            # ページにアクセス
            self.driver.get(url)

            # ページが読み込まれるまで待機（オリジナル展示タブのコンテンツ）
            time.sleep(2)

            # データが存在するか確認
            # 「データがありません」などのメッセージがあれば None を返す
            try:
                no_data = self.driver.find_element(By.XPATH, "//*[contains(text(), 'データがありません')]")
                if no_data:
                    return None
            except Exception:
                # 要素が見つからない = データが存在する
                pass

            # テーブルからデータを抽出
            result = {}

            # データコンテナから各艇のデータを取得
            try:
                # 各データは .css-1qmyagr コンテナに格納されている
                # 構造: 各艇につき4つの連続したコンテナ
                #   - コンテナ0: 1周タイム (isshu_time)
                #   - コンテナ1: 回り足タイム (mawariashi_time)
                #   - コンテナ2: 直線タイム (chikusen_time)
                #   - コンテナ3: 展示タイム (tenji_time)

                data_containers = self.driver.find_elements(By.CSS_SELECTOR, ".css-1qmyagr")

                # 各艇のデータを取得（6艇 × 4コンテナ = 24コンテナ）
                for boat_num in range(1, 7):
                    try:
                        # 各艇のデータは4つの連続したコンテナに格納
                        base_index = (boat_num - 1) * 4

                        # インデックスが範囲内か確認
                        if base_index + 3 >= len(data_containers):
                            continue

                        # 各タイムを取得
                        try:
                            isshu_text = data_containers[base_index].text.strip()
                            isshu = float(isshu_text) if isshu_text and isshu_text.replace('.', '').replace('-', '').isdigit() else None
                        except (ValueError, IndexError, AttributeError):
                            isshu = None

                        try:
                            mawariashi_text = data_containers[base_index + 1].text.strip()
                            mawariashi = float(mawariashi_text) if mawariashi_text and mawariashi_text.replace('.', '').replace('-', '').isdigit() else None
                        except (ValueError, IndexError, AttributeError):
                            mawariashi = None

                        try:
                            chikusen_text = data_containers[base_index + 2].text.strip()
                            chikusen = float(chikusen_text) if chikusen_text and chikusen_text.replace('.', '').replace('-', '').isdigit() else None
                        except (ValueError, IndexError, AttributeError):
                            chikusen = None

                        # 少なくとも1つのタイムが取得できた場合のみ結果に追加
                        if isshu is not None or mawariashi is not None or chikusen is not None:
                            result[boat_num] = {
                                'chikusen_time': chikusen,
                                'isshu_time': isshu,
                                'mawariashi_time': mawariashi
                            }

                    except Exception as row_error:
                        print(f"  艇{boat_num}のデータ取得失敗: {row_error}")
                        continue

                return result if result else None

            except Exception as e:
                print(f"データ抽出エラー ({venue_code}, {date_str}, R{race_number}): {e}")
                return None

        except Exception as e:
            print(f"オリジナル展示取得エラー ({venue_code}, {date_str}, R{race_number}): {e}")
            return None

    def close(self):
        """ブラウザを閉じる"""
        self.driver.quit()


if __name__ == "__main__":
    # テスト実行
    scraper = OriginalTenjiBrowserScraper(headless=False)

    print("="*70)
    print("オリジナル展示スクレイパーテスト（ブラウザ版）")
    print("="*70)

    # 若松 2025-10-31 1R
    tenji_data = scraper.get_original_tenji("20", "2025-10-31", 1)

    if tenji_data:
        print("\n【若松 2025-10-31 1R オリジナル展示】")
        for boat_num in sorted(tenji_data.keys()):
            data = tenji_data[boat_num]
            print(f"  {boat_num}号艇:")
            print(f"    直線: {data['chikusen_time']}秒")
            print(f"    1周: {data['isshu_time']}秒")
            print(f"    回り足: {data['mawariashi_time']}秒")
    else:
        print("\nオリジナル展示データ取得失敗")

    scraper.close()
