"""
直前情報取得モジュール

レース直前の展示情報を取得
- 展示タイム
- スタート展示（ST）
- 水面気象情報
- チルト角度
- プロペラ情報
"""

import requests
from bs4 import BeautifulSoup
import time
from typing import Dict, List, Optional
import re


class BeforeInfoFetcher:
    """
    直前情報取得クラス

    URL例: https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno=1&jcd=06&hd=20251103
    """

    def __init__(self, delay: float = 1.0):
        """
        初期化

        Args:
            delay: リクエスト間の待機時間（秒）
        """
        self.base_url = "https://www.boatrace.jp/owpc/pc/race/beforeinfo"
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def fetch_beforeinfo(self, race_date: str, venue_code: str, race_number: int) -> Optional[Dict]:
        """
        指定レースの直前情報を取得

        Args:
            race_date: レース日（YYYYMMDD形式）
            venue_code: 会場コード（2桁、例: '06'）
            race_number: レース番号（1-12）

        Returns:
            直前情報の辞書、エラー時はNone
            {
                'race_info': {...},
                'weather': {...},
                'racers': [{...}, {...}, ...]
            }
        """
        params = {
            'rno': race_number,
            'jcd': venue_code.zfill(2),
            'hd': race_date
        }

        try:
            response = self.session.get(
                self.base_url,
                params=params,
                timeout=15
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding

            soup = BeautifulSoup(response.text, 'html.parser')

            # データを抽出
            race_info = self._extract_race_info(soup, race_date, venue_code, race_number)
            weather_info = self._extract_weather_info(soup)
            racers_info = self._extract_racers_info(soup)

            return {
                'race_info': race_info,
                'weather': weather_info,
                'racers': racers_info
            }

        except requests.RequestException as e:
            print(f"❌ 直前情報取得エラー ({race_date} {venue_code} {race_number}R): {e}")
            return None
        except Exception as e:
            print(f"❌ 直前情報パースエラー: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _extract_race_info(self, soup: BeautifulSoup, race_date: str, venue_code: str, race_number: int) -> Dict:
        """レース基本情報を抽出"""
        race_info = {
            'race_date': race_date,
            'venue_code': venue_code,
            'race_number': race_number,
            'race_name': '',
            'distance': '',
            'race_time': ''
        }

        try:
            # レース名
            title = soup.find('h2', class_=re.compile('title.*'))
            if title:
                race_info['race_name'] = title.get_text(strip=True)

            # 距離（例: 1800m）
            distance_elem = soup.find(string=re.compile(r'\d+m'))
            if distance_elem:
                match = re.search(r'(\d+)m', distance_elem)
                if match:
                    race_info['distance'] = match.group(1)

            # レース時刻
            time_elem = soup.find(string=re.compile(r'\d{2}:\d{2}'))
            if time_elem:
                match = re.search(r'(\d{2}:\d{2})', time_elem)
                if match:
                    race_info['race_time'] = match.group(1)

        except Exception as e:
            print(f"⚠️ レース情報抽出エラー: {e}")

        return race_info

    def _extract_weather_info(self, soup: BeautifulSoup) -> Dict:
        """水面気象情報を抽出"""
        weather_info = {
            'temperature': None,  # 気温
            'weather': None,      # 天候
            'wind_speed': None,   # 風速
            'wind_direction': None, # 風向
            'water_temp': None,   # 水温
            'wave_height': None   # 波高
        }

        try:
            # 水面気象情報のセクションを探す
            weather_section = soup.find('div', class_=re.compile('weather.*'))

            if weather_section:
                # 気温（例: 気温 15.0℃）
                temp_elem = weather_section.find(string=re.compile(r'気温.*\d+'))
                if temp_elem:
                    match = re.search(r'(\d+\.?\d*)℃', temp_elem)
                    if match:
                        weather_info['temperature'] = float(match.group(1))

                # 水温（例: 水温 19.0℃）
                water_temp_elem = weather_section.find(string=re.compile(r'水温.*\d+'))
                if water_temp_elem:
                    match = re.search(r'(\d+\.?\d*)℃', water_temp_elem)
                    if match:
                        weather_info['water_temp'] = float(match.group(1))

                # 風速（例: 風速 4cm）
                wind_elem = weather_section.find(string=re.compile(r'風.*\d+'))
                if wind_elem:
                    match = re.search(r'(\d+)cm', wind_elem)
                    if match:
                        weather_info['wind_speed'] = int(match.group(1))

                # 波高（例: 6cm）
                wave_elem = weather_section.find(string=re.compile(r'(\d+)cm'))
                if wave_elem:
                    match = re.search(r'(\d+)cm', str(wave_elem))
                    if match and weather_info['wind_speed'] != int(match.group(1)):
                        weather_info['wave_height'] = int(match.group(1))

                # 天候（晴、曇、雨など）
                weather_elem = weather_section.find('span', class_=re.compile('weather.*icon.*'))
                if weather_elem:
                    # class名やalt属性から天候を判定
                    weather_class = ' '.join(weather_elem.get('class', []))
                    if '晴' in weather_class or 'sunny' in weather_class.lower():
                        weather_info['weather'] = '晴'
                    elif '曇' in weather_class or 'cloudy' in weather_class.lower():
                        weather_info['weather'] = '曇'
                    elif '雨' in weather_class or 'rainy' in weather_class.lower():
                        weather_info['weather'] = '雨'

        except Exception as e:
            print(f"⚠️ 水面気象情報抽出エラー: {e}")

        return weather_info

    def _extract_racers_info(self, soup: BeautifulSoup) -> List[Dict]:
        """選手情報を抽出（展示タイム、ST、体重など）"""
        racers = []

        try:
            # 選手情報のテーブルを探す
            racer_table = soup.find('table', class_=re.compile('.*table.*'))

            if not racer_table:
                # 別の構造を試す
                racer_rows = soup.find_all('tr', class_=re.compile('.*racer.*|.*row.*'))
            else:
                racer_rows = racer_table.find_all('tr')[1:]  # ヘッダーをスキップ

            for row in racer_rows:
                racer_data = {
                    'pit_number': None,
                    'racer_number': None,
                    'racer_name': None,
                    'weight': None,          # 体重
                    'exhibition_time': None, # 展示タイム
                    'start_timing': None,    # スタート展示（ST）
                    'tilt': None,            # チルト角度
                    'propeller': None,       # プロペラ
                    'course': None           # 実際のコース
                }

                try:
                    # 枠番
                    pit_elem = row.find('td', class_=re.compile('.*pit.*|.*waku.*'))
                    if not pit_elem:
                        pit_elem = row.find('div', class_=re.compile('.*pit.*|.*waku.*'))
                    if pit_elem:
                        pit_text = pit_elem.get_text(strip=True)
                        match = re.search(r'(\d)', pit_text)
                        if match:
                            racer_data['pit_number'] = int(match.group(1))

                    # 選手名
                    name_elem = row.find('a', class_=re.compile('.*name.*'))
                    if not name_elem:
                        name_elem = row.find('td', class_=re.compile('.*name.*'))
                    if name_elem:
                        racer_data['racer_name'] = name_elem.get_text(strip=True)

                    # 体重（例: 52.2kg）
                    weight_elem = row.find(string=re.compile(r'\d+\.\d+kg'))
                    if weight_elem:
                        match = re.search(r'(\d+\.\d+)', str(weight_elem))
                        if match:
                            racer_data['weight'] = float(match.group(1))

                    # 展示タイム（例: 6.82）
                    time_elem = row.find('td', class_=re.compile('.*time.*|.*exhibition.*'))
                    if time_elem:
                        time_text = time_elem.get_text(strip=True)
                        match = re.search(r'(\d+\.\d+)', time_text)
                        if match:
                            racer_data['exhibition_time'] = float(match.group(1))

                    # スタート展示（ST）（例: 0.07）
                    st_elem = row.find('td', class_=re.compile('.*st.*'))
                    if st_elem:
                        st_text = st_elem.get_text(strip=True)
                        match = re.search(r'(\d+\.\d+)', st_text)
                        if match:
                            racer_data['start_timing'] = float(match.group(1))

                    # チルト角度（例: 0.0）
                    tilt_elem = row.find('td', class_=re.compile('.*tilt.*'))
                    if tilt_elem:
                        tilt_text = tilt_elem.get_text(strip=True)
                        match = re.search(r'(-?\d+\.\d+)', tilt_text)
                        if match:
                            racer_data['tilt'] = float(match.group(1))

                    # コース
                    course_elem = row.find('td', class_=re.compile('.*course.*'))
                    if course_elem:
                        course_text = course_elem.get_text(strip=True)
                        match = re.search(r'(\d)', course_text)
                        if match:
                            racer_data['course'] = int(match.group(1))

                    # データがある場合のみ追加
                    if racer_data['pit_number']:
                        racers.append(racer_data)

                except Exception as e:
                    print(f"⚠️ 選手情報抽出エラー（1行）: {e}")
                    continue

        except Exception as e:
            print(f"❌ 選手情報抽出エラー: {e}")

        return racers

    def fetch_and_display(self, race_date: str, venue_code: str, race_number: int) -> None:
        """
        直前情報を取得して表示（デバッグ用）

        Args:
            race_date: レース日（YYYYMMDD）
            venue_code: 会場コード
            race_number: レース番号
        """
        print(f"\n=== 直前情報取得: {race_date} 会場{venue_code} {race_number}R ===\n")

        info = self.fetch_beforeinfo(race_date, venue_code, race_number)

        if not info:
            print("❌ データ取得失敗")
            return

        # レース情報表示
        print("【レース情報】")
        race_info = info['race_info']
        print(f"  レース名: {race_info.get('race_name', '不明')}")
        print(f"  距離: {race_info.get('distance', '不明')}m")
        print(f"  時刻: {race_info.get('race_time', '不明')}")

        # 水面気象情報表示
        print("\n【水面気象情報】")
        weather = info['weather']
        print(f"  天候: {weather.get('weather', '不明')}")
        print(f"  気温: {weather.get('temperature', '不明')}℃")
        print(f"  水温: {weather.get('water_temp', '不明')}℃")
        print(f"  風速: {weather.get('wind_speed', '不明')}m")
        print(f"  波高: {weather.get('wave_height', '不明')}cm")

        # 選手情報表示
        print("\n【選手情報】")
        print(f"{'枠':^4} {'選手名':^12} {'体重':^6} {'展示':^6} {'ST':^6} {'チルト':^6} {'コース':^6}")
        print("-" * 60)

        for racer in info['racers']:
            pit = racer.get('pit_number', '-')
            name = racer.get('racer_name', '不明')[:10]
            weight = f"{racer.get('weight', 0):.1f}" if racer.get('weight') else '-'
            ex_time = f"{racer.get('exhibition_time', 0):.2f}" if racer.get('exhibition_time') else '-'
            st = f"{racer.get('start_timing', 0):.2f}" if racer.get('start_timing') else '-'
            tilt = f"{racer.get('tilt', 0):.1f}" if racer.get('tilt') else '-'
            course = racer.get('course', '-')

            print(f"{pit:^4} {name:^12} {weight:^6} {ex_time:^6} {st:^6} {tilt:^6} {course:^6}")

        print("\n[OK] 直前情報取得完了\n")


# テスト用コード
if __name__ == "__main__":
    fetcher = BeforeInfoFetcher()

    # 画像のレースを取得（2025年11月3日 浜名湖 1R）
    # URL: https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno=1&jcd=06&hd=20251103
    fetcher.fetch_and_display("20251103", "06", 1)
