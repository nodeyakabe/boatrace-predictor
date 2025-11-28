#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
各競艇場の公式HPからオリジナル展示データを収集

Boatersサイトにデータがない場合の代替手段として、
各場の公式ホームページから直接収集する
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
from datetime import datetime
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class VenueTenjiScraper:
    """各競艇場の公式HPからオリジナル展示データを取得"""

    # 各会場の公式HP URL パターン
    VENUE_URLS = {
        '01': {  # 桐生
            'name': '桐生',
            'url_pattern': 'https://www.boatrace-kiryu.com/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'kiryu'
        },
        '02': {  # 戸田
            'name': '戸田',
            'url_pattern': 'https://www.boatrace-toda.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'toda'
        },
        '03': {  # 江戸川
            'name': '江戸川',
            'url_pattern': 'https://www.boatrace-edogawa.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'edogawa'
        },
        '04': {  # 平和島
            'name': '平和島',
            'url_pattern': 'https://www.boatrace-heiwajima.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'heiwajima'
        },
        '05': {  # 多摩川
            'name': '多摩川',
            'url_pattern': 'https://www.boatrace-tamagawa.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'tamagawa'
        },
        '06': {  # 浜名湖
            'name': '浜名湖',
            'url_pattern': 'https://www.boatrace-hamanako.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'hamanako'
        },
        '07': {  # 蒲郡
            'name': '蒲郡',
            'url_pattern': 'https://www.gamagori-kyotei.com/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'gamagori'
        },
        '08': {  # 常滑
            'name': '常滑',
            'url_pattern': 'https://www.boatrace-tokoname.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'tokoname'
        },
        '09': {  # 津
            'name': '津',
            'url_pattern': 'https://www.boatrace-tsu.com/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'tsu'
        },
        '10': {  # 三国
            'name': '三国',
            'url_pattern': 'https://www.boatrace-mikuni.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'mikuni'
        },
        '11': {  # びわこ
            'name': 'びわこ',
            'url_pattern': 'https://www.boatrace-biwako.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'biwako'
        },
        '12': {  # 住之江
            'name': '住之江',
            'url_pattern': 'https://www.boatrace-suminoe.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'suminoe'
        },
        '13': {  # 尼崎
            'name': '尼崎',
            'url_pattern': 'https://www.boatrace-amagasaki.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'amagasaki'
        },
        '14': {  # 鳴門
            'name': '鳴門',
            'url_pattern': 'https://www.boatrace-naruto.com/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'naruto'
        },
        '15': {  # 丸亀
            'name': '丸亀',
            'url_pattern': 'https://www.boatrace-marugame.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'marugame'
        },
        '16': {  # 児島
            'name': '児島',
            'url_pattern': 'https://www.boatrace-kojima.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'kojima'
        },
        '17': {  # 宮島
            'name': '宮島',
            'url_pattern': 'https://www.boatrace-miyajima.com/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'miyajima'
        },
        '18': {  # 徳山
            'name': '徳山',
            'url_pattern': 'https://www.boatrace-tokuyama.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'tokuyama'
        },
        '19': {  # 下関
            'name': '下関',
            'url_pattern': 'https://www.boatrace-shimonoseki.com/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'shimonoseki'
        },
        '20': {  # 若松
            'name': '若松',
            'url_pattern': 'https://www.boatrace-wakamatsu.com/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'wakamatsu'
        },
        '21': {  # 芦屋
            'name': '芦屋',
            'url_pattern': 'https://www.boatrace-ashiya.com/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'ashiya'
        },
        '22': {  # 福岡
            'name': '福岡',
            'url_pattern': 'https://www.boatrace-fukuoka.com/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'fukuoka'
        },
        '23': {  # 唐津
            'name': '唐津',
            'url_pattern': 'https://www.boatrace-karatsu.com/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'karatsu'
        },
        '24': {  # 大村
            'name': '大村',
            'url_pattern': 'https://www.boatrace-omura.jp/modules/racedata/index.php?cmd=detail&date={date}&rno={race}',
            'parser': 'omura'
        },
    }

    def __init__(self, headless=True, timeout=15):
        """
        初期化

        Args:
            headless: ヘッドレスモードで実行するか
            timeout: ページ読み込みタイムアウト（秒）
        """
        self.timeout = timeout
        self.driver = None
        self.headless = headless

    def _init_driver(self):
        """Seleniumドライバーを初期化（遅延初期化）"""
        if self.driver:
            return

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

        try:
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            driver_path = ChromeDriverManager().install()

            # webdriver-managerのパス修正
            import os
            if 'THIRD_PARTY_NOTICES' in driver_path or not driver_path.endswith('.exe'):
                driver_dir = os.path.dirname(driver_path)
                correct_path = os.path.join(driver_dir, 'chromedriver.exe')

                if not os.path.exists(correct_path):
                    win32_dir = os.path.join(driver_dir, 'chromedriver-win32')
                    if os.path.exists(win32_dir):
                        correct_path = os.path.join(win32_dir, 'chromedriver.exe')

                if os.path.exists(correct_path):
                    driver_path = correct_path

            service = Service(driver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            # フォールバック
            self.driver = webdriver.Chrome(options=chrome_options)

    def get_original_tenji(self, venue_code: str, target_date, race_number: int) -> Optional[Dict]:
        """
        各場の公式HPからオリジナル展示データを取得

        Args:
            venue_code: 会場コード（例: "20"）
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
        if venue_code not in self.VENUE_URLS:
            logger.warning(f"Venue {venue_code} not supported for official HP scraping")
            return None

        venue_info = self.VENUE_URLS[venue_code]

        # 日付を文字列に変換
        if isinstance(target_date, datetime):
            date_str = target_date.strftime('%Y%m%d')  # 20251128 形式
        else:
            date_str = target_date.replace('-', '')  # YYYY-MM-DD → YYYYMMDD

        # URLを構築
        url = venue_info['url_pattern'].format(date=date_str, race=race_number)

        try:
            self._init_driver()
            self.driver.set_page_load_timeout(self.timeout)
            self.driver.get(url)

            # ページ読み込み待機
            time.sleep(2)

            # パーサーを選択して実行
            parser_method = getattr(self, f'_parse_{venue_info["parser"]}', None)
            if parser_method:
                return parser_method()
            else:
                # 汎用パーサー
                return self._parse_generic()

        except TimeoutException:
            logger.warning(f"Timeout accessing {url}")
            return None
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None

    def _parse_generic(self) -> Optional[Dict]:
        """
        汎用パーサー（多くの場が同じHTML構造を使用）

        オリジナル展示タイムは通常、以下のような構造で表示される:
        - テーブル内に各艇の展示データ
        - 直線タイム、1周タイム、回り足タイムのカラム
        """
        try:
            result = {}

            # よくあるパターン1: テーブル行から取得
            # <tr>タグで各艇のデータが1行ずつ
            rows = self.driver.find_elements(By.CSS_SELECTOR, "table.racedata tbody tr, table.exhibition tbody tr")

            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")

                    if len(cells) < 4:  # 最低限のセル数
                        continue

                    # 艇番を取得（通常は最初のセル）
                    boat_num_text = cells[0].text.strip()
                    if not boat_num_text.isdigit():
                        continue

                    boat_num = int(boat_num_text)
                    if boat_num < 1 or boat_num > 6:
                        continue

                    # タイムデータを抽出（セルの位置は会場により異なる可能性がある）
                    # 一般的なパターン: [艇番, 選手名, ..., 直線, 1周, 回り足, ...]

                    # すべてのセルから数値を探す
                    times = []
                    for cell in cells[1:]:  # 艇番以外
                        text = cell.text.strip()
                        # 秒数のパターン（例: 6.11, 36.85）
                        if '.' in text and text.replace('.', '').replace('-', '').isdigit():
                            try:
                                times.append(float(text))
                            except ValueError:
                                pass

                    # タイムが3つ以上あれば（直線、1周、回り足）
                    if len(times) >= 3:
                        result[boat_num] = {
                            'chikusen_time': times[0],  # 直線
                            'isshu_time': times[1],     # 1周
                            'mawariashi_time': times[2] # 回り足
                        }

                except Exception as e:
                    logger.debug(f"Error parsing row: {e}")
                    continue

            return result if result else None

        except Exception as e:
            logger.error(f"Generic parser error: {e}")
            return None

    def close(self):
        """ドライバーを閉じる"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def __del__(self):
        """デストラクタ"""
        self.close()


# 個別会場パーサーのサンプル（必要に応じて拡張）
    def _parse_kiryu(self):
        """桐生専用パーサー（汎用パーサーで対応できない場合）"""
        return self._parse_generic()

    def _parse_toda(self):
        """戸田専用パーサー"""
        return self._parse_generic()

    # 他の会場も同様に必要に応じて実装
