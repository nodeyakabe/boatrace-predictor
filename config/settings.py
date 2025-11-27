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

# ==============================================================================
# デフォルト買い目設定
# ==============================================================================
# バックテスト結果に基づく推奨設定（2024年11月27日更新）
#
# 【バックテスト結果サマリー】
# - 3連単4点 + 3連複1点: 回収率75.5%, 収支-134万円/年
# - 3連単6点 + 3連複1点: 回収率76.5%, 収支-180万円/年
# - 動的(4-10点): 回収率76.0%, 収支-175万円/年
#
# 回収率はほぼ同じ（約75-76%）のため、損失を抑える4点買いを基本とする
# ==============================================================================

DEFAULT_BETTING_CONFIG = {
    # 3連単の基本買い目数
    "trifecta_default_points": 4,

    # 3連単の最大買い目数（レース状況により拡張可能）
    "trifecta_max_points": 10,

    # 3連複の買い目数（保険として固定）
    "trio_points": 1,

    # 1点あたりの賭け金（円）
    "unit_bet": 100,

    # 買い目パターン判定閾値
    "thresholds": {
        # 1着圧倒時の条件（6点買いに拡張）
        "first_dominant_gap": 15,

        # 混戦時の条件（10点買いに拡張）
        "melee_gap": 10,
    },

    # 3連単4点の買い方（1着固定、2-3着は2-4位候補）
    # 例: 1-2-3, 1-2-4, 1-3-2, 1-3-4
    "trifecta_4points_pattern": "first_fixed_2nd3rd_swap",

    # 3連単6点の買い方（1着固定、2-3着は2-4位で全展開）
    "trifecta_6points_pattern": "first_fixed_full",
}

# スコアリング重み設定
# 2024年11月27日更新: 最適化バックテスト結果を反映
# バックテスト結果: 58.75% → 59.71% (+0.96%)
# - コース: 35→20（展示系データ重視のため軽減）
# - モーター: 20→14（ML分析で影響度2.4%と判明、過大配点を修正）
# - 展示ST: 新規追加（当日ST順位、勝率相関3倍）
# - 展示タイム: 新規追加（展示タイム順位、勝率相関3倍）
SCORING_WEIGHTS = {
    "course": 20,   # コース有利度（従来35→20に軽減）
    "racer": 31,    # 選手能力（勝率）
    "motor": 14,    # モーター性能（従来20→14に軽減）
    "rank": 10,     # 級別
    "exhibition_st": 15,    # 展示ST順位（新規）
    "exhibition_time": 10,  # 展示タイム順位（新規）
}

# 旧設定（バックアップ）
SCORING_WEIGHTS_LEGACY = {
    "course": 35,
    "racer": 35,
    "motor": 20,
    "rank": 10,
}

# ==============================================================================
# 会場別特性と動的配点設定（2024年11月27日追加）
# ==============================================================================
# 2024年データ分析に基づく会場別1コース勝率
# ==============================================================================

VENUE_IN1_RATES = {
    '01': 51.9,  # 桐生
    '02': 45.4,  # 戸田（最低）
    '03': 49.5,  # 江戸川
    '04': 46.2,  # 平和島
    '05': 55.1,  # 多摩川
    '06': 55.4,  # 浜名湖
    '07': 61.4,  # 蒲郡
    '08': 60.4,  # 常滑
    '09': 60.5,  # 津
    '10': 56.2,  # 三国
    '11': 58.9,  # びわこ
    '12': 60.8,  # 住之江
    '13': 61.9,  # 尼崎
    '14': 50.6,  # 鳴門
    '15': 58.6,  # 丸亀
    '16': 60.7,  # 児島
    '17': 62.4,  # 宮島
    '18': 67.1,  # 徳山（最高）
    '19': 62.6,  # 下関
    '20': 58.1,  # 若松
    '21': 58.4,  # 芦屋
    '22': 58.9,  # 福岡
    '23': 55.3,  # 唐津
    '24': 66.2,  # 大村
}

# 会場分類（1コース勝率ベース）
HIGH_IN_VENUES = ['18', '24', '17', '19', '13', '07', '16', '12', '08', '09']  # 60%以上
LOW_IN_VENUES = ['02', '04', '03', '14']  # 50%以下
NORMAL_IN_VENUES = ['01', '05', '06', '10', '11', '15', '20', '21', '22', '23']  # その他

# 会場別荒れ率（1号艇以外が1着になる率）
VENUE_UPSET_RATES = {
    '04': 54.9,  # 平和島（最高）
    '02': 54.6,  # 戸田
    '03': 51.5,  # 江戸川
    '14': 50.2,  # 鳴門
    '01': 48.6,  # 桐生
    '06': 45.2,  # 浜名湖
    '23': 45.2,  # 唐津
    '05': 45.1,  # 多摩川
    '10': 44.6,  # 三国
    '20': 42.6,  # 若松
    '21': 42.3,  # 芦屋
    '15': 41.9,  # 丸亀
    '22': 41.9,  # 福岡
    '11': 41.7,  # びわこ
    '08': 40.2,  # 常滑
    '09': 40.2,  # 津
    '12': 40.1,  # 住之江
    '16': 39.9,  # 児島
    '07': 39.2,  # 蒲郡
    '13': 38.5,  # 尼崎
    '17': 38.0,  # 宮島
    '19': 38.0,  # 下関
    '24': 34.5,  # 大村
    '18': 33.3,  # 徳山（最低）
}

# 動的配点パターン
DYNAMIC_SCORING_WEIGHTS = {
    # 堅い会場（1コース勝率60%以上）: コース重視
    'solid': {
        "course": 45,   # ↑10
        "racer": 30,    # ↓5
        "motor": 15,    # ↓5
        "rank": 10,
    },
    # 荒れ会場（1コース勝率50%以下）: 選手重視
    'chaotic': {
        "course": 25,   # ↓10
        "racer": 40,    # ↑5
        "motor": 20,
        "rank": 15,     # ↑5
    },
    # 普通の会場: 標準配点
    'normal': {
        "course": 35,
        "racer": 35,
        "motor": 20,
        "rank": 10,
    },
}

# 会場別モーター影響度（高い方がモーター重視）
VENUE_MOTOR_IMPACT = {
    '24': 3.45,  # 大村（最高）
    '04': 3.32,  # 平和島
    '05': 3.30,  # 多摩川
    '06': 2.84,  # 浜名湖
    '20': 2.74,  # 若松
    '10': 2.62,  # 三国
    '18': 2.27,  # 徳山
    '13': 2.23,  # 尼崎
    '07': 2.11,  # 蒲郡
    '12': 1.87,  # 住之江
    '23': 1.87,  # 唐津
    '08': 1.68,  # 常滑
    '22': 1.66,  # 福岡
    '11': 1.62,  # びわこ
    '02': 1.55,  # 戸田
    '21': 1.49,  # 芦屋
    '01': 1.48,  # 桐生
    '14': 1.46,  # 鳴門
    '16': 1.38,  # 児島
    '09': 1.32,  # 津
    '15': 1.32,  # 丸亀
    '03': 1.19,  # 江戸川
    '17': 0.79,  # 宮島
    '19': 0.45,  # 下関（最低）
}


def get_dynamic_weights(venue_code: str) -> dict:
    """
    会場特性に応じた動的配点を取得

    Args:
        venue_code: 会場コード（'01'-'24'）

    Returns:
        dict: スコアリング重み設定
    """
    if venue_code in HIGH_IN_VENUES:
        return DYNAMIC_SCORING_WEIGHTS['solid']
    elif venue_code in LOW_IN_VENUES:
        return DYNAMIC_SCORING_WEIGHTS['chaotic']
    else:
        return DYNAMIC_SCORING_WEIGHTS['normal']


def get_venue_type(venue_code: str) -> str:
    """
    会場タイプを取得

    Args:
        venue_code: 会場コード

    Returns:
        str: 'solid'（堅い）, 'chaotic'（荒れ）, 'normal'（普通）
    """
    if venue_code in HIGH_IN_VENUES:
        return 'solid'
    elif venue_code in LOW_IN_VENUES:
        return 'chaotic'
    else:
        return 'normal'


# ==============================================================================
# 拡張スコア重み設定（2024年11月27日更新）
# ==============================================================================
# 分析結果に基づく調整:
# - ST関連: 勝率との相関が高い（3倍差）→ 重み強化
# - 展示タイム: 勝率との相関が高い（3倍差）→ 重み強化
# - チルト: 影響小 → 重み低下
# ==============================================================================

EXTENDED_SCORE_WEIGHTS = {
    'class': 10,           # 級別（A1=10, A2=7, B1=4, B2=1）
    'fl_penalty': 10,      # F/Lペナルティ（最大-10）
    'session': 5,          # 節間成績
    'prev_race': 5,        # 前走レベル
    'course_entry': 5,     # 進入傾向
    'matchup': 5,          # 選手間相性
    'motor': 5,            # モーター特性
    'start_timing': 10,    # 平均ST（8→10に強化）
    'exhibition': 10,      # 展示タイム（8→10に強化）
    'tilt': 2,             # チルト角度（3→2に低下）
    'recent_form': 8,      # 直近成績
    'venue_affinity': 8,   # 会場別勝率（6→8に強化）
    'place_rate': 5,       # 連対率
}

# 拡張スコアの最大値（正規化用）
EXTENDED_SCORE_MAX = sum(v for k, v in EXTENDED_SCORE_WEIGHTS.items() if k != 'fl_penalty')  # 78点
EXTENDED_SCORE_MIN = -EXTENDED_SCORE_WEIGHTS['fl_penalty']  # -10点

# 期待値計算用設定（Bパターン予想用）
EXPECTED_VALUE_CONFIG = {
    # 期待値プラスと判定する閾値
    "positive_ev_threshold": 1.0,

    # 期待値計算時のマージン（控除率を考慮）
    "house_edge": 0.25,

    # オッズ取得タイミング
    "odds_timing": "締切5分前",
}
