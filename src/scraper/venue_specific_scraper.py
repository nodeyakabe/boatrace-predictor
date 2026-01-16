"""
競艇場独自データスクレイパー

優先度高データを収集:
1. 潮汐表（海水面競艇場）
2. リアルタイム気象データ
3. 前検タイムランキング
4. 進入コース別成績
"""

import requests
import time
from datetime import datetime
from selectolax.parser import HTMLParser
from .base_scraper_v2 import BaseScraperV2
from .tide_scraper import TideScraper


class VenueSpecificScraper(BaseScraperV2):
    """競艇場独自データを収集するスクレイパー"""

    # 海水面競艇場（潮汐表あり）
    SEAWATER_VENUES = {
        '14': 'naruto',  # 鳴門
        '15': 'marugame',  # 丸亀
        '16': 'kojima',  # 児島
        '17': 'miyajima',  # 宮島
        '18': 'tokuyama',  # 徳山
        '19': 'shimonoseki',  # 下関
        '20': 'wakamatsu',  # 若松
        '22': 'fukuoka',  # 福岡
        '23': 'karatsu',  # 唐津
        # '24': 'omura',  # 大村（要確認）
    }

    def __init__(self, min_delay=0.5, max_delay=1.5, use_jma_tide=True):
        """
        初期化

        Args:
            min_delay: 最小待機時間（秒）- 競艇場サイトは負荷に配慮して長めに
            max_delay: 最大待機時間（秒）
            use_jma_tide: 気象庁の潮位データを使用するか（デフォルト: True）
        """
        super().__init__(min_delay, max_delay)
        self.use_jma_tide = use_jma_tide
        self.jma_tide_scraper = TideScraper() if use_jma_tide else None

    def get_weather_data(self, venue_code, date_str):
        """
        リアルタイム気象データを取得

        Args:
            venue_code: 競艇場コード（01-24）
            date_str: 日付文字列（YYYYMMDD）

        Returns:
            dict: {
                'wind_speed': 風速(m/s),
                'wind_direction': 風向,
                'temperature': 気温(℃),
                'water_temperature': 水温(℃),
                'weather': 天候,
                'wave_height': 波高(cm)
            } or None
        """
        # 実装は各競艇場のサイト構造に応じて個別に実装
        # ここではプレースホルダー
        return None

    def get_zenken_time_ranking(self, venue_code, date_str):
        """
        前検タイムランキングを取得

        Args:
            venue_code: 競艇場コード（01-24）
            date_str: 日付文字列（YYYYMMDD）

        Returns:
            list: [
                {
                    'racer_id': 選手登録番号,
                    'pit': 艇番,
                    'time': 前検タイム,
                    'motor_no': モーター番号
                },
                ...
            ] or None
        """
        # 実装は各競艇場のサイト構造に応じて個別に実装
        return None

    def get_course_stats(self, venue_code, year=None, month=None):
        """
        進入コース別成績を取得

        Args:
            venue_code: 競艇場コード（01-24）
            year: 年（省略時は最新）
            month: 月（省略時は最新）

        Returns:
            list: [
                {
                    'course': コース番号(1-6),
                    'win_rate': 1着率(%),
                    'place_rate_2': 2連対率(%),
                    'place_rate_3': 3連対率(%),
                    'samples': サンプル数
                },
                ...
            ] or None
        """
        # 実装は各競艇場のサイト構造に応じて個別に実装
        return None

    def get_tide_data_with_jma(self, venue_code, date_str):
        """
        潮汐データを取得（競艇場サイト + 気象庁データの統合）

        Args:
            venue_code: 競艇場コード
            date_str: 日付文字列（YYYY-MM-DD）

        Returns:
            dict: {
                'venue_tide': 競艇場サイトのデータ,
                'jma_tide': 気象庁のデータ,
                'source': 'both' | 'venue' | 'jma'
            } or None
        """
        result = {}

        # 競艇場サイトから取得（継承クラスで実装されている場合）
        venue_tide = None
        if hasattr(self, 'get_tide_table'):
            try:
                venue_tide = self.get_tide_table(date_str)
                if venue_tide:
                    result['venue_tide'] = venue_tide
            except Exception as e:
                print(f"競艇場サイト潮汐取得エラー ({venue_code}): {e}")

        # 気象庁から取得
        jma_tide = None
        if self.use_jma_tide and self.jma_tide_scraper:
            try:
                jma_tide = self.jma_tide_scraper.get_tide_data(venue_code, date_str)
                if jma_tide:
                    result['jma_tide'] = jma_tide
            except Exception as e:
                print(f"気象庁潮汐取得エラー ({venue_code}): {e}")

        # データソースを記録
        if venue_tide and jma_tide:
            result['source'] = 'both'
        elif venue_tide:
            result['source'] = 'venue'
        elif jma_tide:
            result['source'] = 'jma'
        else:
            return None

        return result if result else None


class MarugameScraper(VenueSpecificScraper):
    """丸亀競艇場専用スクレイパー"""

    BASE_URL = "https://www.marugameboat.jp"

    def get_tide_table(self, date_str):
        """
        潮汐表を取得

        Args:
            date_str: 日付文字列（YYYY-MM-DD）

        Returns:
            list: [
                {'time': '22:00', 'type': '満潮', 'tide_name': '大潮'},
                {'time': '17:24', 'type': '干潮', 'tide_name': '大潮'},
                ...
            ] or None
        """
        try:
            # まるがめの潮汐表URL
            url = f"{self.BASE_URL}/01shiomi/shiomi.htm"
            tree = self.fetch_page(url)

            if not tree:
                return None

            tide_data = []

            # テーブルを検索
            tables = tree.css('table')

            for table in tables:
                rows = table.css('tr')

                for row in rows:
                    cells = row.css('td')

                    if len(cells) >= 5:
                        try:
                            # セル内容を取得
                            date_cell = cells[0].text(strip=True)
                            mancho_time = cells[2].text(strip=True)  # 満潮時刻
                            kancho_time = cells[3].text(strip=True)  # 干潮時刻
                            tide_name = cells[4].text(strip=True)    # 潮周り

                            # 日付が対象日と一致するかチェック
                            # date_str: "2024-01-17" -> "1/17"形式に変換して比較
                            target_date_parts = date_str.split('-')
                            month_day = f"{int(target_date_parts[1])}/{int(target_date_parts[2])}"

                            if date_cell == month_day:
                                # 満潮データ追加
                                if mancho_time and mancho_time != '':
                                    tide_data.append({
                                        'time': mancho_time,
                                        'type': '満潮',
                                        'tide_name': tide_name,
                                        'level': None  # 潮位（cm）はページに記載なし
                                    })

                                # 干潮データ追加
                                if kancho_time and kancho_time != '':
                                    tide_data.append({
                                        'time': kancho_time,
                                        'type': '干潮',
                                        'tide_name': tide_name,
                                        'level': None
                                    })

                                break

                        except (IndexError, ValueError) as e:
                            continue

                if tide_data:
                    break

            return tide_data if tide_data else None

        except Exception as e:
            print(f"潮汐表取得エラー (丸亀, {date_str}): {e}")
            return None

    def get_weather_data(self, date_str):
        """
        リアルタイム気象データを取得

        Args:
            date_str: 日付文字列（YYYY-MM-DD）

        Returns:
            dict: {
                'wind_direction': '北西',
                'wind_speed': 2.2,
                'temperature': 9.5,
                'pressure': 1018,
                'humidity': 68,
                'rainfall': 0.0,
                'observed_at': '13:41'
            } or None
        """
        try:
            # まるがめのトップページ
            url = f"{self.BASE_URL}/"
            tree = self.fetch_page(url)

            if not tree:
                return None

            weather_data = {}

            # HTMLからtableタグを取得して解析
            # 気象データは<td>単位付き</td>の形式で格納されている
            html_content = tree.html

            import re

            # 風向（テーブルから抽出）
            wind_dir_match = re.search(r'<th>風向</th>.*?<td>([^<]+)</td>', html_content, re.DOTALL)
            if wind_dir_match:
                wind_dir = wind_dir_match.group(1).strip()
                if wind_dir and wind_dir != '-':
                    weather_data['wind_direction'] = wind_dir

            # 風速
            wind_speed_match = re.search(r'<td>(\d+\.?\d*)m</td>', html_content)
            if wind_speed_match:
                weather_data['wind_speed'] = float(wind_speed_match.group(1))

            # 気圧
            pressure_match = re.search(r'<td>(\d+)hPa</td>', html_content)
            if pressure_match:
                weather_data['pressure'] = float(pressure_match.group(1))

            # 気温
            temp_match = re.search(r'<td>(\d+\.?\d*)℃</td>', html_content)
            if temp_match:
                weather_data['temperature'] = float(temp_match.group(1))

            # 湿度
            humidity_match = re.search(r'<td>(\d+)%</td>', html_content)
            if humidity_match:
                weather_data['humidity'] = float(humidity_match.group(1))

            # 雨量
            rain_match = re.search(r'<td>(\d+\.?\d*)mm</td>', html_content)
            if rain_match:
                weather_data['rainfall'] = float(rain_match.group(1))

            # 観測時刻
            text = tree.body.text()
            time_match = re.search(r'(\d{1,2}:\d{2})現在', text)
            if time_match:
                weather_data['observed_at'] = time_match.group(1)

            return weather_data if weather_data else None

        except Exception as e:
            print(f"気象データ取得エラー (丸亀, {date_str}): {e}")
            return None

    def get_zenken_time_ranking(self, date_str):
        """
        前検タイムランキングを取得

        Args:
            date_str: 日付文字列（YYYY-MM-DD）

        Returns:
            list or None
        """
        try:
            # まるがめの前検タイムランキングURL
            # 例: /asp/marugame/kyogi/kyogihtml/zenken/zenken1505.htm
            # 日付によってURLが変わる可能性があるため要調査
            url = f"{self.BASE_URL}/asp/marugame/kyogi/kyogihtml/zenken/"
            tree = self.fetch_page(url)

            if not tree:
                return None

            # HTMLパース実装
            # 実際のHTML構造に合わせて実装が必要
            return None

        except Exception as e:
            print(f"前検タイム取得エラー (丸亀, {date_str}): {e}")
            return None

    def get_course_stats(self, year=None, month=None):
        """
        進入コース別成績を取得

        Args:
            year: 年
            month: 月

        Returns:
            list: [
                {'course': 1, 'win_rate': 52.9, 'place_rate_2': 71.4, 'place_rate_3': 81.7},
                {'course': 2, 'win_rate': 14.2, ...},
                ...
            ] or None
        """
        try:
            # まるがめの水面特性・進入コース別情報URL
            url = f"{self.BASE_URL}/01suimen/01suimen.htm"
            tree = self.fetch_page(url)

            if not tree:
                return None

            course_stats = []

            # テーブルを検索
            # 「コース別入着率」のテーブルを探す
            text = tree.body.text()

            import re

            # 各コースのデータを抽出
            # フォーマット例: "52.9 18.5 10.3 6.7 6.5 4.7"（1着～6着の率）
            for course in range(1, 7):
                # コース番号の行を探す
                pattern = rf'{course}\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)'
                match = re.search(pattern, text)

                if match:
                    rates = [float(match.group(i)) for i in range(1, 7)]

                    # 1着率、2連対率、3連対率を計算
                    win_rate = rates[0]  # 1着率
                    place_rate_2 = rates[0] + rates[1]  # 2連対率 = 1着率 + 2着率
                    place_rate_3 = sum(rates[:3])  # 3連対率 = 1着率 + 2着率 + 3着率

                    course_stats.append({
                        'course': course,
                        'win_rate': win_rate,
                        'place_rate_2': place_rate_2,
                        'place_rate_3': place_rate_3,
                        'samples': None  # サンプル数はページに記載なし
                    })

            return course_stats if course_stats else None

        except Exception as e:
            print(f"進入コース別成績取得エラー (丸亀): {e}")
            return None


class KojimaScraper(VenueSpecificScraper):
    """児島競艇場専用スクレイパー"""

    BASE_URL = "https://www.kojimaboat.jp"

    def get_tide_table(self, date_str):
        """
        潮汐表を取得（丸亀と同じ構造）

        Args:
            date_str: 日付文字列（YYYY-MM-DD）

        Returns:
            list: 潮汐データ or None
        """
        try:
            url = f"{self.BASE_URL}/01shiomi/shiomi.htm"
            tree = self.fetch_page(url)
            if not tree:
                return None

            tide_data = []
            tables = tree.css('table')

            for table in tables:
                rows = table.css('tr')

                for row in rows:
                    cells = row.css('td')

                    if len(cells) >= 5:
                        try:
                            date_cell = cells[0].text(strip=True)
                            mancho_time = cells[2].text(strip=True)
                            kancho_time = cells[3].text(strip=True)
                            tide_name = cells[4].text(strip=True)

                            # 日付変換
                            target_date_parts = date_str.split('-')
                            month_day = f"{int(target_date_parts[1])}/{int(target_date_parts[2])}"

                            if date_cell.startswith(month_day):
                                if mancho_time and mancho_time != '':
                                    tide_data.append({
                                        'time': mancho_time,
                                        'type': '満潮',
                                        'tide_name': tide_name,
                                        'level': None
                                    })

                                if kancho_time and kancho_time != '':
                                    tide_data.append({
                                        'time': kancho_time,
                                        'type': '干潮',
                                        'tide_name': tide_name,
                                        'level': None
                                    })

                                break

                        except (IndexError, ValueError):
                            continue

                if tide_data:
                    break

            return tide_data if tide_data else None

        except Exception as e:
            print(f"潮汐表取得エラー (児島, {date_str}): {e}")
            return None

    def get_weather_data(self, date_str):
        """
        リアルタイム気象データを取得（気象LIVE）

        Args:
            date_str: 日付文字列（YYYY-MM-DD）

        Returns:
            dict: 気象データ or None
        """
        try:
            # 気象LIVEページ
            url = f"{self.BASE_URL}/asp/kyogi/16/weather/index.html"
            tree = self.fetch_page(url)
            if not tree:
                return None

            weather_data = {}
            html_content = tree.html

            import re

            # 風向（テーブルから抽出）
            wind_dir_match = re.search(r'<th>風向</th>.*?<td>([^<]+)</td>', html_content, re.DOTALL)
            if wind_dir_match:
                wind_dir = wind_dir_match.group(1).strip()
                if wind_dir and wind_dir != '-':
                    weather_data['wind_direction'] = wind_dir

            # 風速
            wind_speed_match = re.search(r'<td>(\d+\.?\d*)m</td>', html_content)
            if wind_speed_match:
                weather_data['wind_speed'] = float(wind_speed_match.group(1))

            # 気圧
            pressure_match = re.search(r'<td>(\d+)hPa</td>', html_content)
            if pressure_match:
                weather_data['pressure'] = float(pressure_match.group(1))

            # 気温
            temp_match = re.search(r'<td>(\d+\.?\d*)℃</td>', html_content)
            if temp_match:
                weather_data['temperature'] = float(temp_match.group(1))

            # 湿度
            humidity_match = re.search(r'<td>(\d+)%</td>', html_content)
            if humidity_match:
                weather_data['humidity'] = float(humidity_match.group(1))

            # 雨量
            rain_match = re.search(r'<td>(\d+\.?\d*)mm</td>', html_content)
            if rain_match:
                weather_data['rainfall'] = float(rain_match.group(1))

            # 水温（2つ目の℃マッチ）
            temp_matches = re.findall(r'<td>(\d+\.?\d*)℃</td>', html_content)
            if len(temp_matches) >= 2:
                weather_data['water_temperature'] = float(temp_matches[1])

            # 波高
            wave_match = re.search(r'<td>(\d+\.?\d*)cm</td>', html_content)
            if wave_match:
                weather_data['wave_height'] = float(wave_match.group(1))

            # 観測時刻
            text = tree.body.text()
            time_match = re.search(r'(\d{1,2}:\d{2})現在', text)
            if time_match:
                weather_data['observed_at'] = time_match.group(1)

            return weather_data if weather_data else None

        except Exception as e:
            print(f"気象データ取得エラー (児島, {date_str}): {e}")
            return None

    def get_course_stats(self, year=None, month=None):
        """
        進入コース別成績を取得

        Args:
            year: 年
            month: 月

        Returns:
            list: コース別成績 or None
        """
        try:
            url = f"{self.BASE_URL}/01suimen/01suimen.htm"
            tree = self.fetch_page(url)
            if not tree:
                return None

            course_stats = []
            text = tree.body.text()

            import re

            for course in range(1, 7):
                pattern = rf'{course}\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)'
                match = re.search(pattern, text)

                if match:
                    rates = [float(match.group(i)) for i in range(1, 7)]

                    course_stats.append({
                        'course': course,
                        'win_rate': rates[0],
                        'place_rate_2': rates[0] + rates[1],
                        'place_rate_3': sum(rates[:3]),
                        'samples': None
                    })

            return course_stats if course_stats else None

        except Exception as e:
            print(f"進入コース別成績取得エラー (児島): {e}")
            return None


# 汎用スクレイパー（丸亀・児島と同じ構造を持つ競艇場用）
class GenericVenueScraper(VenueSpecificScraper):
    """
    丸亀・児島と同じHTML構造を持つ競艇場用の汎用スクレイパー

    以下の競艇場で使用可能（構造が同じ場合）:
    - 鳴門、宮島、徳山、下関、若松、福岡、唐津
    """

    def __init__(self, base_url, venue_code, min_delay=0.5, max_delay=1.5):
        """
        初期化

        Args:
            base_url: 競艇場のベースURL
            venue_code: 競艇場コード（01-24）
            min_delay: 最小待機時間
            max_delay: 最大待機時間
        """
        super().__init__(min_delay, max_delay)
        self.BASE_URL = base_url
        self.venue_code = venue_code

    def get_tide_table(self, date_str):
        """潮汐表を取得（丸亀・児島と同じ構造）"""
        try:
            url = f"{self.BASE_URL}/01shiomi/shiomi.htm"
            tree = self.fetch_page(url)
            if not tree:
                return None

            tide_data = []
            tables = tree.css('table')

            for table in tables:
                rows = table.css('tr')

                for row in rows:
                    cells = row.css('td')

                    if len(cells) >= 5:
                        try:
                            date_cell = cells[0].text(strip=True)
                            mancho_time = cells[2].text(strip=True)
                            kancho_time = cells[3].text(strip=True)
                            tide_name = cells[4].text(strip=True)

                            target_date_parts = date_str.split('-')
                            month_day = f"{int(target_date_parts[1])}/{int(target_date_parts[2])}"

                            if date_cell.startswith(month_day):
                                if mancho_time and mancho_time != '':
                                    tide_data.append({
                                        'time': mancho_time,
                                        'type': '満潮',
                                        'tide_name': tide_name,
                                        'level': None
                                    })

                                if kancho_time and kancho_time != '':
                                    tide_data.append({
                                        'time': kancho_time,
                                        'type': '干潮',
                                        'tide_name': tide_name,
                                        'level': None
                                    })

                                break

                        except (IndexError, ValueError):
                            continue

                if tide_data:
                    break

            return tide_data if tide_data else None

        except Exception as e:
            print(f"潮汐表取得エラー ({self.venue_code}, {date_str}): {e}")
            return None

    def get_weather_data(self, date_str):
        """気象データを取得（丸亀と同じHTML構造を想定）"""
        try:
            url = f"{self.BASE_URL}/"
            tree = self.fetch_page(url)
            if not tree:
                return None

            weather_data = {}
            html_content = tree.html

            import re

            # 風向（テーブルから抽出）
            wind_dir_match = re.search(r'<th>風向</th>.*?<td>([^<]+)</td>', html_content, re.DOTALL)
            if wind_dir_match:
                wind_dir = wind_dir_match.group(1).strip()
                if wind_dir and wind_dir != '-':
                    weather_data['wind_direction'] = wind_dir

            # 風速
            wind_speed_match = re.search(r'<td>(\d+\.?\d*)m</td>', html_content)
            if wind_speed_match:
                weather_data['wind_speed'] = float(wind_speed_match.group(1))

            # 気圧
            pressure_match = re.search(r'<td>(\d+)hPa</td>', html_content)
            if pressure_match:
                weather_data['pressure'] = float(pressure_match.group(1))

            # 気温
            temp_match = re.search(r'<td>(\d+\.?\d*)℃</td>', html_content)
            if temp_match:
                weather_data['temperature'] = float(temp_match.group(1))

            # 湿度
            humidity_match = re.search(r'<td>(\d+)%</td>', html_content)
            if humidity_match:
                weather_data['humidity'] = float(humidity_match.group(1))

            # 雨量
            rain_match = re.search(r'<td>(\d+\.?\d*)mm</td>', html_content)
            if rain_match:
                weather_data['rainfall'] = float(rain_match.group(1))

            # 水温（一部の競艇場のみ）
            water_temp_match = re.search(r'<td>(\d+\.?\d*)℃</td>', html_content)
            if water_temp_match:
                # 気温と区別するために2つ目のマッチを探す
                matches = re.findall(r'<td>(\d+\.?\d*)℃</td>', html_content)
                if len(matches) >= 2:
                    weather_data['water_temperature'] = float(matches[1])

            # 波高（海水面競艇場のみ）
            wave_match = re.search(r'<td>(\d+\.?\d*)cm</td>', html_content)
            if wave_match:
                weather_data['wave_height'] = float(wave_match.group(1))

            # 観測時刻
            text = tree.body.text()
            time_match = re.search(r'(\d{1,2}:\d{2})現在', text)
            if time_match:
                weather_data['observed_at'] = time_match.group(1)

            return weather_data if weather_data else None

        except Exception as e:
            print(f"気象データ取得エラー ({self.venue_code}, {date_str}): {e}")
            return None

    def get_course_stats(self, year=None, month=None):
        """進入コース別成績を取得"""
        try:
            url = f"{self.BASE_URL}/01suimen/01suimen.htm"
            tree = self.fetch_page(url)
            if not tree:
                return None

            course_stats = []
            text = tree.body.text()

            import re

            for course in range(1, 7):
                pattern = rf'{course}\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)'
                match = re.search(pattern, text)

                if match:
                    rates = [float(match.group(i)) for i in range(1, 7)]

                    course_stats.append({
                        'course': course,
                        'win_rate': rates[0],
                        'place_rate_2': rates[0] + rates[1],
                        'place_rate_3': sum(rates[:3]),
                        'samples': None
                    })

            return course_stats if course_stats else None

        except Exception as e:
            print(f"進入コース別成績取得エラー ({self.venue_code}): {e}")
            return None


# 各競艇場のスクレイパーインスタンスを作成するファクトリー関数
def create_venue_scraper(venue_code):
    """
    競艇場コードからスクレイパーインスタンスを作成

    Args:
        venue_code: 競艇場コード（'01'-'24'）

    Returns:
        VenueSpecificScraperのインスタンス or None
    """
    from .modern_cms_venue_scraper import ModernCMSVenueScraper

    # モダンCMS使用競艇場（鳴門、徳山、下関、若松）
    if venue_code in ['14', '18', '19', '20']:
        return ModernCMSVenueScraper(venue_code)
    # 旧式HTML使用競艇場
    elif venue_code == '15':
        return MarugameScraper()
    elif venue_code == '16':
        return KojimaScraper()
    # 潮見表データなし競艇場（気象庁データのみ使用）
    elif venue_code in ['17', '22', '23']:
        # 宮島、福岡、唐津は潮見表データなし
        # GenericVenueScraperを返すが、潮見表は使用不可
        venue_configs = {
            '17': ('https://www.boatrace-miyajima.com', '宮島'),
            '22': ('http://www.boatrace-fukuoka.com', '福岡'),
            '23': ('http://www.boatrace-karatsu.jp', '唐津'),
        }
        base_url, name = venue_configs[venue_code]
        return GenericVenueScraper(base_url, venue_code)
    else:
        print(f"警告: 競艇場コード {venue_code} のスクレイパーは未実装です")
        return None


if __name__ == "__main__":
    # テスト実行
    print("=" * 70)
    print("競艇場独自データスクレイパーテスト")
    print("=" * 70)

    # 丸亀のテスト
    marugame = MarugameScraper()

    print("\n【丸亀競艇場】")
    print("潮汐表取得テスト...")
    tide_data = marugame.get_tide_table("2024-11-15")
    if tide_data:
        for t in tide_data:
            print(f"  {t['time']} {t['type']}: {t['level']}cm")
    else:
        print("  取得失敗（実装が必要）")

    marugame.close()
    print("\n完了")
