"""
モダンCMS競艇場スクレイパー

対象競艇場:
- 鳴門（14）: https://www.n14.jp
- 徳山（18）: https://www.boatrace-tokuyama.jp
- 下関（19）: https://www.boatrace-shimonoseki.jp
- 若松（20）: https://www.wmb.jp

これらの競艇場は共通のCMSシステムを使用しており、
URL構造とHTML構造が類似しています。
"""

from datetime import datetime
import re
from .base_scraper_v2 import BaseScraperV2


class ModernCMSVenueScraper(BaseScraperV2):
    """モダンCMSを使用する競艇場用スクレイパー"""

    # 各競艇場のベースURL
    VENUE_URLS = {
        '14': 'https://www.n14.jp',  # 鳴門
        '18': 'https://www.boatrace-tokuyama.jp',  # 徳山
        '19': 'https://www.boatrace-shimonoseki.jp',  # 下関
        '20': 'https://www.wmb.jp',  # 若松
    }

    def __init__(self, venue_code, min_delay=0.5, max_delay=1.5):
        """
        初期化

        Args:
            venue_code: 競艇場コード（14, 18, 19, 20）
            min_delay: 最小待機時間（秒）
            max_delay: 最大待機時間（秒）
        """
        super().__init__(min_delay, max_delay)
        self.venue_code = venue_code

        if venue_code not in self.VENUE_URLS:
            raise ValueError(f"非対応の競艇場コード: {venue_code}")

        self.BASE_URL = self.VENUE_URLS[venue_code]

    def get_tide_table(self, date_str):
        """
        潮汐表を取得

        Args:
            date_str: 日付文字列（YYYY-MM-DD）

        Returns:
            list: [
                {
                    'time': '06:32',
                    'type': 'high',  # 'high' or 'low'
                    'level': 270.0,  # cm単位
                    'tide_name': '中潮'  # 鳴門のみ
                },
                ...
            ] or None
        """
        try:
            url = f"{self.BASE_URL}/modules/datafile/?page=index_tide_table"
            tree = self.fetch_page(url)
            if not tree:
                return None

            # テーブルを探す（複数のテーブルがページに存在する可能性）
            tables = tree.css('table')

            tide_data = []

            for table in tables:
                # ヘッダーをチェック（「干潮」「満潮」を含むテーブルを探す）
                thead = table.css_first('thead')
                if not thead:
                    continue

                header_text = thead.text()
                if '干潮' not in header_text or '満潮' not in header_text:
                    continue

                # このテーブルから潮位データを抽出
                tbody = table.css_first('tbody')
                if not tbody:
                    continue

                rows = tbody.css('tr')

                for row in rows:
                    cols = row.css('td')
                    if len(cols) < 4:  # 最低4列必要（日付、潮名、干潮、満潮）
                        continue

                    # 日付チェック（YYYY/MM/DD または MM/DD 形式）
                    date_cell = cols[0].text().strip()

                    # 日付をパース（例: "2026/01/15" または "01/15" または "01/15木"）
                    if '/' not in date_cell:
                        continue

                    # 曜日を除去（例: "01/15木" → "01/15"）
                    import re
                    date_match = re.match(r'(\d{2,4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2})', date_cell)
                    if not date_match:
                        continue

                    date_text = date_match.group(1)
                    parts = date_text.split('/')
                    if len(parts) == 3:
                        row_year, row_month, row_day = parts
                    elif len(parts) == 2:
                        # 年が省略されている場合は現在の年を使用
                        row_month, row_day = parts
                        row_year = datetime.now().year
                    else:
                        continue

                    # 目標日付と一致するかチェック
                    target_date = datetime.strptime(date_str, '%Y-%m-%d')
                    try:
                        row_date = datetime(int(row_year), int(row_month), int(row_day))
                    except ValueError:
                        continue

                    if row_date.date() != target_date.date():
                        continue

                    # 列数から潮位データの有無を判定
                    # 鳴門: 4列（日付、潮名、干潮時刻、満潮時刻）
                    # 徳山・下関・若松: 5列（日付、干潮時刻、干潮潮位、満潮時刻、満潮潮位）

                    if len(cols) == 4:
                        # 鳴門形式（潮位データなし）
                        tide_name = cols[1].text().strip()
                        low_time = cols[2].text().strip()
                        high_time = cols[3].text().strip()
                        low_level = None
                        high_level = None
                    else:
                        # 徳山・下関・若松形式（潮位データあり）
                        low_time = cols[1].text().strip()
                        low_level_text = cols[2].text().strip()
                        high_time = cols[3].text().strip()
                        high_level_text = cols[4].text().strip()
                        tide_name = None

                        # 潮位をcm単位に変換（例: "1.28m" → 128.0）
                        def parse_tide_level(level_text):
                            """潮位文字列をcm単位のfloatに変換"""
                            if not level_text or level_text == '-':
                                return None
                            # "m"を除去して数値化
                            level_text = level_text.replace('m', '').strip()
                            try:
                                return float(level_text) * 100  # m → cm
                            except ValueError:
                                return None

                        low_level = parse_tide_level(low_level_text)
                        high_level = parse_tide_level(high_level_text)

                    # 干潮データを追加
                    if low_time:
                        tide_entry = {
                            'time': low_time,
                            'type': 'low',
                        }
                        if low_level is not None:
                            tide_entry['level'] = low_level
                        if tide_name:
                            tide_entry['tide_name'] = tide_name
                        tide_data.append(tide_entry)

                    # 満潮データを追加
                    if high_time:
                        tide_entry = {
                            'time': high_time,
                            'type': 'high',
                        }
                        if high_level is not None:
                            tide_entry['level'] = high_level
                        if tide_name:
                            tide_entry['tide_name'] = tide_name
                        tide_data.append(tide_entry)

            return tide_data if tide_data else None

        except Exception as e:
            print(f"潮汐表取得エラー (場コード: {self.venue_code}, 日付: {date_str}): {e}")
            return None

    def get_course_stats(self, year=None, month=None):
        """
        進入コース別成績を取得

        Args:
            year: 年（省略時は最新）
            month: 月（省略時は最新）

        Returns:
            list: [
                {
                    'course': 1,
                    'win_rate': 59.8,  # 1着率
                    'place_rate_2': 77.5,  # 2連対率
                    'place_rate_3': 84.4,  # 3連対率
                },
                ...
            ] or None
        """
        try:
            url = f"{self.BASE_URL}/modules/datafile/?page=index_suimen"
            tree = self.fetch_page(url)
            if not tree:
                return None

            # テーブルを探す
            tables = tree.css('table')

            for table in tables:
                # ヘッダーをチェック（「1着」「2着」...を含むテーブルを探す）
                thead = table.css_first('thead')
                if not thead:
                    continue

                header_text = thead.text()
                if '1着' not in header_text or '2着' not in header_text:
                    continue

                # ヘッダー行を解析して列インデックスを取得
                headers = []
                for th in thead.css('th'):
                    headers.append(th.text().strip())

                # 必要な列のインデックスを探す
                try:
                    win_idx = headers.index('1着')
                    place2_idx = headers.index('2着')
                    place3_idx = headers.index('3着')
                except ValueError:
                    continue

                # データ行を解析
                tbody = table.css_first('tbody')
                if not tbody:
                    continue

                course_stats = []

                for row in tbody.css('tr'):
                    cols = row.css('td')
                    if len(cols) < max(win_idx, place2_idx, place3_idx) + 1:
                        continue

                    # 1列目がコース名かチェック（例: "1コース", "1 コース"）
                    course_label = cols[0].text().strip()

                    # コース番号を抽出
                    course_match = re.match(r'(\d+)\s*コース', course_label)
                    if not course_match:
                        continue

                    course_num = int(course_match.group(1))

                    # 数値をパース
                    try:
                        win_rate = float(cols[win_idx].text().strip())
                        place_rate_2 = float(cols[place2_idx].text().strip())
                        place_rate_3 = float(cols[place3_idx].text().strip())
                    except (ValueError, IndexError):
                        continue

                    course_stats.append({
                        'course': course_num,
                        'win_rate': win_rate,
                        'place_rate_2': win_rate + place_rate_2,
                        'place_rate_3': win_rate + place_rate_2 + place_rate_3,
                    })

                if course_stats:
                    return course_stats

            return None

        except Exception as e:
            print(f"進入コース別成績取得エラー (場コード: {self.venue_code}): {e}")
            return None

    def get_tide_data_with_jma(self, venue_code, date_str):
        """
        競艇場サイトと気象庁の潮位データを統合

        Args:
            venue_code: 競艇場コード
            date_str: 日付文字列（YYYY-MM-DD）

        Returns:
            dict: {
                'source': 'venue' or 'jma' or 'both',
                'venue_tide': [...],  # 競艇場サイトのデータ
                'jma_tide': [...]  # 気象庁のデータ
            } or None
        """
        result = {}

        # 競艇場サイトから取得
        venue_tide = self.get_tide_table(date_str)
        if venue_tide:
            result['venue_tide'] = venue_tide

        # 気象庁から取得（TideScraperを使用）
        from .tide_scraper import TideScraper
        jma_scraper = TideScraper()

        try:
            jma_tide = jma_scraper.get_tide_data(venue_code, date_str)
            if jma_tide:
                result['jma_tide'] = jma_tide
        except Exception as e:
            print(f"気象庁潮位データ取得エラー (場コード: {venue_code}, 日付: {date_str}): {e}")

        # データソースを判定
        if 'venue_tide' in result and 'jma_tide' in result:
            result['source'] = 'both'
        elif 'venue_tide' in result:
            result['source'] = 'venue'
        elif 'jma_tide' in result:
            result['source'] = 'jma'
        else:
            return None

        return result
