"""
潮位データスクレイパー（気象庁）
"""
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
import re


class TideScraper:
    """気象庁の潮位観測データを取得"""

    # ボートレース場と気象庁観測地点のマッピング
    VENUE_TO_STATION = {
        '15': {'name': '児島', 'station': '宇野', 'station_id': '71'},       # 児島 → 宇野
        '16': {'name': '鳴門', 'station': '小松島', 'station_id': '79'},     # 鳴門 → 小松島
        '17': {'name': '丸亀', 'station': '高松', 'station_id': '74'},       # 丸亀 → 高松
        '18': {'name': '宮島', 'station': '広島', 'station_id': '69'},       # 宮島 → 広島
        '20': {'name': '下関', 'station': '関門', 'station_id': '66'},       # 下関 → 関門
        '22': {'name': '福岡', 'station': '博多', 'station_id': '61'},       # 福岡 → 博多
        '24': {'name': '大村', 'station': '長崎', 'station_id': '51'},       # 大村 → 長崎
    }

    def __init__(self, delay=2.0):
        """
        初期化

        Args:
            delay: リクエスト間の待機時間（秒）
        """
        self.base_url = "https://www.data.jma.go.jp/kaiyou/db/tide/suisan/txt"
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def get_tide_data(self, venue_code, target_date):
        """
        指定日の潮位データを取得

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
        station_id = station_info['station_id']

        # 日付を文字列に変換
        if isinstance(target_date, datetime):
            date_str = target_date.strftime('%Y-%m-%d')
        else:
            date_str = target_date

        year, month, day = date_str.split('-')

        try:
            # 気象庁の潮位データURL
            # 例: https://www.data.jma.go.jp/gmd/kaiyou/db/tide/suisan/txt/2024/TK202410.txt
            url = f"{self.base_url}/{year}/TK{year}{month}.txt"

            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            response.encoding = 'shift_jis'  # 気象庁のテキストファイルはShift_JIS

            # テキストデータをパース
            tide_data = self._parse_tide_text(response.text, station_id, int(day))

            time.sleep(self.delay)
            return tide_data

        except Exception as e:
            print(f"潮位データ取得エラー ({venue_code}, {date_str}): {e}")
            return None

    def _parse_tide_text(self, text, station_id, target_day):
        """
        気象庁の潮位テキストデータをパース

        Args:
            text: テキストデータ
            station_id: 観測地点ID
            target_day: 対象日（1-31）

        Returns:
            list: 潮位データのリスト
        """
        tide_data = []

        # テキストを行ごとに分割
        lines = text.split('\n')

        # 観測地点のセクションを探す
        in_target_station = False
        for line in lines:
            # 観測地点IDが含まれる行をチェック
            if station_id in line:
                in_target_station = True
                continue

            if in_target_station:
                # 対象日のデータ行を探す
                # フォーマット例: " 1 03:45  352 H  10:12   28 L  16:30  340 H  22:45   50 L"
                # 最初の数字が日
                parts = line.split()
                if not parts:
                    continue

                try:
                    day = int(parts[0])
                except (ValueError, IndexError):
                    # 数字でない場合は次の観測地点に移ったと判断
                    if in_target_station:
                        break
                    continue

                if day == target_day:
                    # 潮位データを抽出
                    # 形式: 時:分 潮位 タイプ(H=満潮, L=干潮)
                    i = 1
                    while i < len(parts):
                        if ':' in parts[i]:
                            time_str = parts[i]
                            if i + 2 < len(parts):
                                level = float(parts[i + 1])
                                tide_type = parts[i + 2]

                                tide_data.append({
                                    'time': time_str,
                                    'type': '満潮' if tide_type == 'H' else '干潮',
                                    'level': level
                                })
                                i += 3
                            else:
                                break
                        else:
                            i += 1
                    break

        return tide_data

    def close(self):
        """セッションを閉じる"""
        self.session.close()


if __name__ == "__main__":
    # テスト実行
    scraper = TideScraper()

    print("="*70)
    print("潮位スクレイパーテスト")
    print("="*70)

    # 児島 2024-10-30
    tide_data = scraper.get_tide_data("15", "2024-10-30")

    if tide_data:
        print("\n【児島 2024-10-30 潮位データ】")
        for data in tide_data:
            print(f"  {data['time']} {data['type']}: {data['level']}cm")
    else:
        print("\n潮位データ取得失敗")

    scraper.close()
