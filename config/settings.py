# 競艇予想システム - 設定ファイル

import os
from pathlib import Path
from dotenv import load_dotenv

# .envファイルを読み込み
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# 競艇場情報
# 全24競艇場（データベースから動的に取得することを推奨）
VENUES = {
    "kiryu": {"name": "桐生", "code": "01", "latitude": 36.4069, "longitude": 139.3314},
    "toda": {"name": "戸田", "code": "02", "latitude": 35.8147, "longitude": 139.6947},
    "edogawa": {"name": "江戸川", "code": "03", "latitude": 35.6858, "longitude": 139.8831},
    "heiwajima": {"name": "平和島", "code": "04", "latitude": 35.5842, "longitude": 139.7394},
    "tamagawa": {"name": "多摩川", "code": "05", "latitude": 35.6097, "longitude": 139.5936},
    "hamanako": {"name": "浜名湖", "code": "06", "latitude": 34.7500, "longitude": 137.5833},
    "gamagori": {"name": "蒲郡", "code": "07", "latitude": 34.8233, "longitude": 137.2169},
    "tokoname": {"name": "常滑", "code": "08", "latitude": 34.8889, "longitude": 136.8333},
    "tsu": {"name": "津", "code": "09", "latitude": 34.7214, "longitude": 136.5028},
    "mikuni": {"name": "三国", "code": "10", "latitude": 36.2167, "longitude": 136.1500},
    "biwako": {"name": "びわこ", "code": "11", "latitude": 35.1333, "longitude": 136.0667},
    "suminoe": {"name": "住之江", "code": "12", "latitude": 34.6139, "longitude": 135.4656},
    "amagasaki": {"name": "尼崎", "code": "13", "latitude": 34.7167, "longitude": 135.4167},
    "naruto": {"name": "鳴門", "code": "14", "latitude": 34.1667, "longitude": 134.6167},
    "marugame": {"name": "丸亀", "code": "15", "latitude": 34.2900, "longitude": 133.7967},
    "kojima": {"name": "児島", "code": "16", "latitude": 34.4833, "longitude": 133.8167},
    "miyajima": {"name": "宮島", "code": "17", "latitude": 34.2833, "longitude": 132.3167},
    "tokuyama": {"name": "徳山", "code": "18", "latitude": 34.0511, "longitude": 131.8147},
    "shimonoseki": {"name": "下関", "code": "19", "latitude": 33.9667, "longitude": 130.9333},
    "wakamatsu": {"name": "若松", "code": "20", "latitude": 33.9131, "longitude": 130.8089},
    "ashiya": {"name": "芦屋", "code": "21", "latitude": 33.8847, "longitude": 130.6653},
    "fukuoka": {"name": "福岡", "code": "22", "latitude": 33.6844, "longitude": 130.3394},
    "karatsu": {"name": "唐津", "code": "23", "latitude": 33.4500, "longitude": 129.9833},
    "omura": {"name": "大村", "code": "24", "latitude": 32.9167, "longitude": 129.9500},
}

# BOAT RACE公式サイトのURL
BOATRACE_BASE_URL = "https://www.boatrace.jp"
BOATRACE_OFFICIAL_URL = "https://www.boatrace.jp/owpc/pc/race"

# データベース設定
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/boatrace.db")

# 天気API設定（OpenWeatherMap）
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
if not WEATHER_API_KEY:
    raise ValueError("WEATHER_API_KEY is not set in environment variables. Please check your .env file.")
WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"

# スクレイピング設定
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
REQUEST_DELAY = int(os.getenv("REQUEST_DELAY", "1"))  # リクエスト間隔（秒）

# おすすめレース抽出条件（デフォルト値）
RECOMMEND_CONDITIONS = {
    "max_wind_speed": 5.0,  # 風速5m以下
    "min_racer_win_rate": 0.3,  # 1号艇勝率30%以上
    "tide_status": "rising"  # 上げ潮
}
