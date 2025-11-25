"""
天気データ取得
OpenWeatherMap APIを使用
"""

import requests
from datetime import datetime
from config.settings import WEATHER_API_KEY, WEATHER_API_URL


class WeatherScraper:
    """天気データ取得クラス"""

    def __init__(self):
        self.api_key = WEATHER_API_KEY
        self.api_url = WEATHER_API_URL

    def get_weather(self, latitude, longitude):
        """
        指定された緯度経度の天気情報を取得

        Args:
            latitude: 緯度
            longitude: 経度

        Returns:
            天気データの辞書
        """
        if not self.api_key:
            print("エラー: APIキーが設定されていません")
            return None

        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": self.api_key,
            "units": "metric",  # 摂氏温度
            "lang": "ja"  # 日本語
        }

        try:
            response = requests.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # データを整形
            weather_data = {
                "temperature": data["main"]["temp"],  # 気温（℃）
                "feels_like": data["main"]["feels_like"],  # 体感温度
                "humidity": data["main"]["humidity"],  # 湿度（%）
                "pressure": data["main"]["pressure"],  # 気圧（hPa）
                "weather_condition": data["weather"][0]["description"],  # 天気状態
                "weather_main": data["weather"][0]["main"],  # 天気メイン
                "wind_speed": data["wind"]["speed"],  # 風速（m/s）
                "wind_direction": data["wind"].get("deg", 0),  # 風向（度）
                "clouds": data["clouds"]["all"],  # 雲量（%）
                "timestamp": datetime.now()
            }

            return weather_data

        except requests.exceptions.RequestException as e:
            print(f"天気データ取得エラー: {e}")
            return None
        except KeyError as e:
            print(f"天気データ解析エラー: {e}")
            return None

    def get_wind_direction_text(self, degree):
        """
        風向の角度を方位に変換

        Args:
            degree: 風向（度）

        Returns:
            方位（文字列）
        """
        directions = [
            "北", "北北東", "北東", "東北東",
            "東", "東南東", "南東", "南南東",
            "南", "南南西", "南西", "西南西",
            "西", "西北西", "北西", "北北西"
        ]
        index = int((degree + 11.25) / 22.5) % 16
        return directions[index]

    def format_weather_data(self, weather_data):
        """
        天気データを読みやすい形式にフォーマット

        Args:
            weather_data: 天気データの辞書

        Returns:
            フォーマット済み文字列
        """
        if not weather_data:
            return "天気データなし"

        wind_dir_text = self.get_wind_direction_text(weather_data["wind_direction"])

        formatted = f"""
気温: {weather_data['temperature']:.1f}℃（体感: {weather_data['feels_like']:.1f}℃）
天気: {weather_data['weather_condition']}
風速: {weather_data['wind_speed']:.1f}m/s（{wind_dir_text}）
湿度: {weather_data['humidity']}%
気圧: {weather_data['pressure']}hPa
雲量: {weather_data['clouds']}%
        """
        return formatted.strip()
