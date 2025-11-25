"""
BOAT RACE公式サイトから各競艇場の詳細データを取得

公式URL: https://www.boatrace.jp/owpc/pc/data/stadium?jcd={venue_code}
取得データ: 水面特性、コース情報、統計データなど
"""

import requests
from bs4 import BeautifulSoup
import time
import re
from typing import Dict, Optional
import traceback


class OfficialVenueScraper:
    """
    BOAT RACE公式サイトから会場データを取得するスクレイパー
    """

    BASE_URL = "https://www.boatrace.jp/owpc/pc/data/stadium"

    # 会場コードと名前のマッピング（01-24）
    VENUE_NAMES = {
        '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
        '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
        '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
        '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
        '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
        '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
    }

    def __init__(self, timeout: int = 30):
        """
        初期化

        Args:
            timeout: タイムアウト時間（秒）
        """
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.timeout = timeout

    def fetch_venue_data(self, venue_code: str) -> Optional[Dict]:
        """
        指定会場のデータを取得

        Args:
            venue_code: 会場コード（'01'〜'24'）

        Returns:
            {
                'venue_code': '01',
                'venue_name': '桐生',
                'water_type': '淡水',
                'tidal_range': 'なし',
                'motor_type': '減音',
                'course_1_win_rate': 47.6,
                'course_features': {...},
                'record_time': '1.42.8',
                'record_holder': '石田章央',
                'record_date': '2004/10/27'
            }
        """
        try:
            # URL構築
            url = f"{self.BASE_URL}?jcd={venue_code}"

            print(f"  取得中: {self.VENUE_NAMES.get(venue_code, venue_code)} ({url})")

            # HTTPリクエスト
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = response.apparent_encoding  # 文字化け対策

            # HTML解析
            soup = BeautifulSoup(response.content, 'html.parser')

            # データ抽出
            venue_data = {
                'venue_code': venue_code,
                'venue_name': self.VENUE_NAMES.get(venue_code, '不明'),
                'water_type': None,
                'tidal_range': None,
                'motor_type': None,
                'course_1_win_rate': None,
                'course_2_win_rate': None,
                'course_3_win_rate': None,
                'course_4_win_rate': None,
                'course_5_win_rate': None,
                'course_6_win_rate': None,
                'record_time': None,
                'record_holder': None,
                'record_date': None,
                'characteristics': None
            }

            # 1. 水面特性の抽出（dl/dtタグから）
            memo_section = soup.find('div', class_='table1')
            if memo_section:
                dl_items = memo_section.find_all('dl')
                for dl in dl_items:
                    dt = dl.find('dt')
                    dd = dl.find('dd')
                    if dt and dd:
                        key = dt.get_text(strip=True)
                        value = dd.get_text(strip=True)

                        if '水質' in key:
                            venue_data['water_type'] = value
                        elif '干満差' in key:
                            venue_data['tidal_range'] = value
                        elif 'モーター' in key:
                            venue_data['motor_type'] = value

            # 2. コース別1着率の抽出（最近3ヶ月データ）
            # テーブルから1着率を抽出
            tables = soup.find_all('table', class_='is-w495')
            if tables:
                # 最初のテーブル（コース別データ）
                first_table = tables[0]
                tbody = first_table.find('tbody')
                if tbody:
                    rows = tbody.find_all('tr')
                    for i, row in enumerate(rows[:6]):  # 1〜6コース
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            # 2列目が1着率
                            try:
                                win_rate_text = cells[1].get_text(strip=True).replace('%', '')
                                win_rate = float(win_rate_text)
                                venue_data[f'course_{i+1}_win_rate'] = win_rate
                            except (ValueError, IndexError):
                                pass

            # 3. レコード情報の抽出
            record_section = soup.find('div', class_='table1')
            if record_section:
                # レコード時間
                record_time_tag = record_section.find(text=re.compile(r'\d+\.\d+秒'))
                if record_time_tag:
                    match = re.search(r'(\d+\.\d+)秒', record_time_tag)
                    if match:
                        venue_data['record_time'] = match.group(1)

                # レコードホルダーと日付
                record_info = record_section.find_all('dd')
                for dd in record_info:
                    text = dd.get_text(strip=True)
                    # 例: "石田章央（2004/10/27）"
                    match = re.match(r'(.+?)（(\d{4}/\d{1,2}/\d{1,2})）', text)
                    if match:
                        venue_data['record_holder'] = match.group(1)
                        venue_data['record_date'] = match.group(2)

            # 4. 会場特性の説明文を抽出（あれば）
            # ページによっては特性説明が記載されている場合がある
            description = soup.find('div', class_='stadium-description')
            if description:
                venue_data['characteristics'] = description.get_text(strip=True)[:500]  # 最大500文字

            return venue_data

        except requests.exceptions.Timeout:
            print(f"  ✗ タイムアウト: {venue_code}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"  ✗ HTTPエラー: {venue_code} - {e}")
            return None
        except Exception as e:
            print(f"  ✗ 予期しないエラー: {venue_code}")
            traceback.print_exc()
            return None

    def fetch_all_venues(self, delay: float = 1.0) -> Dict[str, Dict]:
        """
        全24会場のデータを取得

        Args:
            delay: リクエスト間の待機時間（秒）

        Returns:
            {
                '01': {...},
                '02': {...},
                ...
            }
        """
        print("="*70)
        print("BOAT RACE公式サイトから全24会場のデータを取得")
        print("="*70)

        all_data = {}

        for venue_code in sorted(self.VENUE_NAMES.keys()):
            data = self.fetch_venue_data(venue_code)
            if data:
                all_data[venue_code] = data
                print(f"  ✓ 成功: {data['venue_name']} - 1コース勝率: {data['course_1_win_rate']}%")
            else:
                print(f"  ✗ 失敗: {self.VENUE_NAMES[venue_code]}")

            # レート制限対策
            time.sleep(delay)

        print("="*70)
        print(f"取得完了: {len(all_data)}/24 会場")
        print("="*70)

        return all_data

    def close(self):
        """セッションを閉じる"""
        self.session.close()


if __name__ == "__main__":
    # テスト実行
    scraper = OfficialVenueScraper(timeout=30)

    print("\n【テスト1: 桐生（01）のデータ取得】")
    kiryu_data = scraper.fetch_venue_data('01')
    if kiryu_data:
        print("\n取得データ:")
        for key, value in kiryu_data.items():
            print(f"  {key}: {value}")

    print("\n" + "="*70)
    print("【テスト2: 全24会場のデータ取得】")
    print("実行しますか？ (y/n): ", end='')
    # コメントアウト: 自動実行しない
    # if input().lower() == 'y':
    #     all_data = scraper.fetch_all_venues(delay=2.0)
    #     print(f"\n取得成功: {len(all_data)}会場")
    print("（スキップ: 手動で実行してください）")

    scraper.close()
