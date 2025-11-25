# 競艇予測システム - ロジック・仕組み詳細分析

**作成日**: 2025-11-14
**対象**: 外部AIへのシステム改善提案依頼用
**内容範囲**: UIを除くロジック・アルゴリズム・データフロー

---

## 目次

1. [システムアーキテクチャ概要](#1-システムアーキテクチャ概要)
2. [データ収集ロジック](#2-データ収集ロジック)
3. [データベース設計とデータモデル](#3-データベース設計とデータモデル)
4. [特徴量エンジニアリング](#4-特徴量エンジニアリング)
5. [機械学習モデル](#5-機械学習モデル)
6. [予測エンジン](#6-予測エンジン)
7. [ベッティング戦略](#7-ベッティング戦略)
8. [主要なアルゴリズム詳細](#8-主要なアルゴリズム詳細)
9. [データフローと処理パイプライン](#9-データフローと処理パイプライン)
10. [既知の問題点と改善余地](#10-既知の問題点と改善余地)

---

## 1. システムアーキテクチャ概要

### 1.1 全体構成

```
┌─────────────────────────────────────────────────────────────┐
│                   データ収集層 (Scraping)                     │
│  ・24競艇場の公式サイトスクレイピング                           │
│  ・RDMDB API (潮位データ)                                     │
│  ・リトライ・レート制限・User-Agent ランダム化                  │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   永続化層 (Database)                         │
│  ・SQLite 3 (1.07GB, 27万レース)                             │
│  ・10テーブル (races, entries, results, weather, tide...)    │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   統計分析層 (Analysis)                        │
│  ・会場別/選手別/モーター別分析                                 │
│  ・コース別勝率・決まり手分布・時系列トレンド                    │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                 特徴量エンジニアリング (Features)              │
│  ・Phase 1: 基本特徴量 (40次元)                               │
│  ・Phase 2: 時系列特徴量 (19次元)                             │
│  ・Phase 3: リアルタイム特徴量                                 │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                 機械学習層 (ML Models)                         │
│  ・XGBoost 会場別モデル × 9                                   │
│  ・XGBoost 統合モデル × 1                                     │
│  ・アンサンブル重み付け統合                                     │
│  ・確率校正 (Isotonic Regression)                            │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                 予測エンジン (Prediction)                      │
│  ・各艇の勝率予測 (1着〜6着確率)                               │
│  ・決まり手予測 (逃げ/まくり/差し)                             │
│  ・SHAP による説明可能性                                       │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                 ベッティング戦略 (Betting)                     │
│  ・期待値計算 (EV = pred_prob × odds - 1)                    │
│  ・Kelly 基準資金配分                                         │
│  ・ポートフォリオ最適化                                         │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 技術スタック

- **言語**: Python 3.8+
- **ML**: XGBoost, scikit-learn
- **データ処理**: pandas, numpy
- **スクレイピング**: requests, BeautifulSoup4, Selenium
- **DB**: SQLite3
- **説明可能性**: SHAP
- **UI**: Streamlit (本ドキュメントでは省略)

### 1.3 ファイル構成

- **総ファイル数**: 115ファイル
- **総コード行数**: 約14,000行
- **主要モジュール**:
  - `src/scraper/` - 24ファイル (データ収集)
  - `src/analysis/` - 21ファイル (統計分析)
  - `src/ml/` - 7ファイル (機械学習)
  - `src/prediction/` - 11ファイル (予測統合)
  - `src/betting/` - 5ファイル (ベッティング)
  - `src/features/` - 4ファイル (特徴量生成)
  - `src/database/` - 6ファイル (DB管理)

---

## 2. データ収集ロジック

### 2.1 スクレイピング基盤

#### 2.1.1 SafeScraperBase (基底クラス)

[src/scraper/safe_scraper_base.py](src/scraper/safe_scraper_base.py:1-80)

**主要機能**:

1. **User-Agent ランダム化**
   ```python
   USER_AGENTS = [
       'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
       'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15',
       # ... 計6種類
   ]
   ```
   - リクエストごとにランダムに切り替え
   - Bot検知回避

2. **レート制限とランダム遅延**
   ```python
   min_delay = 0.3秒
   max_delay = 0.8秒
   delay = random.uniform(min_delay, max_delay)
   ```
   - 人間のブラウジングパターンを模倣
   - サーバー負荷軽減

3. **リトライロジック**
   ```python
   max_retries = 3
   for attempt in range(max_retries):
       try:
           response = session.get(url, timeout=30)
           if response.status_code == 200:
               return BeautifulSoup(response.content)
           elif response.status_code == 429:  # Too Many Requests
               wait_time = (2 ** attempt) * random.uniform(1, 3)  # 指数バックオフ
               time.sleep(wait_time)
       except requests.Timeout:
           continue
   ```
   - 429エラー: 指数バックオフ (1秒 → 2秒 → 4秒)
   - 503エラー: 同様に処理
   - タイムアウト: リトライ

4. **HTTP ヘッダー設定**
   ```python
   headers = {
       'User-Agent': random_user_agent,
       'Accept': 'text/html,application/xhtml+xml',
       'Accept-Language': 'ja,en-US;q=0.9',
       'DNT': '1',  # Do Not Track
       'Connection': 'keep-alive',
       'Referer': 'https://www.boatrace.jp/'
   }
   ```

### 2.2 データ収集パイプライン

#### 2.2.1 レース結果収集

[src/scraper/result_scraper_improved_v4.py](src/scraper/result_scraper_improved_v4.py:1)

**収集データ**:
- 着順 (1-6位)
- ST時間 (スタートタイミング)
- 決まり手 (逃げ/まくり/差し/まくり差し/抜き/恵まれ)
- イレギュラー (F=フライング, L=欠場, K=転覆, S=失格)

**HTML解析ロジック**:
```python
# 方法1: テーブル構造解析
table = soup.find('table', class_='result-table')
rows = table.find_all('tr')

for row in rows:
    cols = row.find_all('td')
    rank = cols[0].text.strip()
    pit_number = cols[1].text.strip()
    st_time = cols[5].text.strip()  # STタイム
    kimarite = cols[6].text.strip()  # 決まり手
```

**決まり手の正規化**:
```python
KIMARITE_MAP = {
    '逃げ': 'nige',
    'まくり': 'makuri',
    '差し': 'sashi',
    'まくり差し': 'makuri_sashi',
    '抜き': 'nuki',
    '恵まれ': 'megumare'
}
```

#### 2.2.2 出走表収集

[src/scraper/beforeinfo_scraper.py](src/scraper/beforeinfo_scraper.py:1)

**収集データ**:
- 選手情報 (登録番号, 名前, 級別, 年齢, 体重)
- 勝率 (全国勝率, 当地勝率)
- モーター/ボート番号
- モーター2連率・3連率
- 展示タイム
- チルト角度
- STタイミング平均

#### 2.2.3 オッズ収集

[src/scraper/odds_fetcher.py](src/scraper/odds_fetcher.py:1)

**収集方法**:
- 三連単オッズ (120通り)
- リアルタイムAPI呼び出し
- セッション管理による高速化

**エラーハンドリング**:
```python
if response.status_code == 404:
    # レース未開催・オッズ未確定
    return {'status': 'not_available'}
elif response.status_code == 200:
    # JSON解析
    odds_data = response.json()
    return parse_odds(odds_data)
```

#### 2.2.4 潮位データ収集

[src/scraper/tide_scraper.py](src/scraper/tide_scraper.py:1)
[src/scraper/rdmdb_tide_parser.py](src/scraper/rdmdb_tide_parser.py:1)

**データソース**: RDMDB (気象庁リアルタイムデータベース)

**収集内容**:
- 30秒間隔の潮位データ
- 満潮・干潮時刻
- 潮位変動率

**データ構造**:
```python
{
    'venue_code': '07',  # 蒲郡
    'datetime': '2024-01-01 14:30:00',
    'tide_level': 120.5,  # cm
    'tide_type': 'rising',  # rising/falling
    'next_high_tide': '2024-01-01 16:45:00',
    'next_low_tide': '2024-01-01 22:30:00'
}
```

### 2.3 並列処理とスケーラビリティ

#### 2.3.1 一括収集

[src/scraper/bulk_scraper.py](src/scraper/bulk_scraper.py:1)

**並列処理**:
```python
from concurrent.futures import ProcessPoolExecutor

with ProcessPoolExecutor(max_workers=10) as executor:
    futures = []
    for venue in venues:
        for date in date_range:
            future = executor.submit(scrape_race_data, venue, date)
            futures.append(future)

    results = [f.result() for f in futures]
```

**性能**:
- 10並列処理
- 約0.3タスク/秒
- エラー率: 0.1%未満

---

## 3. データベース設計とデータモデル

### 3.1 テーブル構造

[src/database/models.py](src/database/models.py:1-217)

#### 3.1.1 races (レース基本情報)

```sql
CREATE TABLE races (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_code TEXT NOT NULL,           -- 競艇場コード (01-24)
    race_date DATE NOT NULL,            -- レース日 (YYYY-MM-DD)
    race_number INTEGER NOT NULL,       -- レース番号 (1-12)
    race_time TEXT,                     -- 発走時刻 (HH:MM)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(venue_code, race_date, race_number)
);
```

**レコード数**: 約46,318件

#### 3.1.2 entries (出走表)

```sql
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    pit_number INTEGER NOT NULL,        -- 枠番 (1-6)
    racer_number TEXT,                  -- 選手登録番号
    racer_name TEXT,                    -- 選手名
    racer_rank TEXT,                    -- 級別 (A1/A2/B1/B2)
    racer_home TEXT,                    -- 支部
    racer_age INTEGER,
    racer_weight REAL,
    motor_number INTEGER,               -- モーター番号
    boat_number INTEGER,                -- ボート番号
    win_rate REAL,                      -- 全国勝率
    second_rate REAL,                   -- 全国2連対率
    third_rate REAL,                    -- 全国3連対率
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (race_id) REFERENCES races(id)
);
```

**レコード数**: 約274,423件 (46,318レース × 6艇)

#### 3.1.3 results (レース結果)

```sql
CREATE TABLE results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    pit_number INTEGER NOT NULL,
    rank TEXT,                          -- 着順 (1-6, F, L, K, S)
    is_invalid INTEGER DEFAULT 0,       -- イレギュラーフラグ
    trifecta_odds REAL,                 -- 三連単オッズ (1着艇のみ)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(race_id, pit_number),
    FOREIGN KEY (race_id) REFERENCES races(id)
);
```

**レコード数**: 約264,427件

**rank 値の種類**:
- `1`〜`6`: 通常着順
- `F`: フライング
- `L`: 出走取消
- `K`: 転覆
- `S`: 失格

#### 3.1.4 race_details (レース詳細)

```sql
CREATE TABLE race_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    pit_number INTEGER NOT NULL,
    exhibition_time REAL,               -- 展示タイム (秒)
    tilt_angle REAL,                    -- チルト角度 (度)
    parts_replacement TEXT,             -- 部品交換履歴
    actual_course INTEGER,              -- 実際の進入コース (1-6)
    st_time REAL,                       -- STタイミング (秒)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(race_id, pit_number),
    FOREIGN KEY (race_id) REFERENCES races(id)
);
```

**レコード数**: 約242,795件

**重要カラム**:
- `exhibition_time`: 展示航走のタイム (6.5秒以下が優秀)
- `st_time`: 0.00秒がベスト、マイナス値はフライング
- `actual_course`: 枠番と異なる場合がある

#### 3.1.5 weather (気象情報)

```sql
CREATE TABLE weather (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_code TEXT NOT NULL,
    weather_date DATE NOT NULL,
    temperature REAL,                   -- 気温 (℃)
    weather_condition TEXT,             -- 天候 (晴/曇/雨/雪)
    wind_speed REAL,                    -- 風速 (m/s)
    wind_direction TEXT,                -- 風向 (N/NE/E/SE/S/SW/W/NW)
    water_temperature REAL,             -- 水温 (℃)
    wave_height REAL,                   -- 波高 (cm)
    humidity INTEGER,                   -- 湿度 (%)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(venue_code, weather_date)
);
```

**レコード数**: 約3,421件

#### 3.1.6 rdmdb_tide (潮位データ)

```sql
CREATE TABLE rdmdb_tide (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_code TEXT NOT NULL,
    observation_datetime TEXT NOT NULL, -- YYYY-MM-DD HH:MM:SS
    tide_level REAL,                    -- 潮位 (cm)
    tide_status TEXT,                   -- rising/falling/high/low
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**レコード数**: 約6,475,040件 (30秒間隔)

### 3.2 データベース管理ロジック

[src/database/data_manager.py](src/database/data_manager.py:1)

**主要クラス**: `DataManager`

**機能**:

1. **スキーマ検証**
   ```python
   REQUIRED_RACE_FIELDS = ['venue_code', 'race_date', 'race_number']
   REQUIRED_ENTRY_FIELDS = ['pit_number', 'racer_number', 'racer_name']

   def validate_race_data(self, data):
       for field in REQUIRED_RACE_FIELDS:
           if field not in data:
               raise ValueError(f"Missing required field: {field}")
   ```

2. **トランザクション管理**
   ```python
   with Database() as conn:
       cursor = conn.cursor()
       try:
           cursor.execute("INSERT INTO races ...")
           cursor.execute("INSERT INTO entries ...")
           conn.commit()
       except Exception as e:
           conn.rollback()
           raise
   ```

3. **バルク挿入最適化**
   ```python
   # executemany で高速化
   cursor.executemany(
       "INSERT INTO entries VALUES (?, ?, ?, ...)",
       entries_list  # 6艇分のデータ
   )
   ```

### 3.3 データ整合性

**外部キー制約**:
```sql
FOREIGN KEY (race_id) REFERENCES races(id)
FOREIGN KEY (venue_code) REFERENCES venues(code)
```

**UNIQUE制約**:
```sql
UNIQUE(venue_code, race_date, race_number)  -- races
UNIQUE(race_id, pit_number)                  -- entries, results, race_details
```

**欠損値処理**:
- 数値カラム: `NULL` 許容 → 特徴量生成時に `fillna(0)` または平均値補完
- テキストカラム: `NULL` 許容 → 特徴量生成時に `fillna('')`

---

## 4. 特徴量エンジニアリング

### 4.1 Phase 1: 基本特徴量

[src/features/optimized_features.py](src/features/optimized_features.py:1)

**クラス**: `OptimizedFeatureGenerator`

#### 4.1.1 選手関連特徴量 (10次元)

```python
features = {
    'pit_number': 1-6,                    # 枠番
    'racer_class': 1-4,                   # 級別スコア (A1=4, A2=3, B1=2, B2=1)
    'win_rate': 0.0-1.0,                  # 全国勝率
    'nationwide_win_rate': 0.0-1.0,       # 全国勝率 (別集計)
    'local_win_rate': 0.0-1.0,            # 当地勝率
    'avg_st': 0.00-0.30,                  # 平均STタイミング
    'f_count': 0-N,                       # フライング回数
    'l_count': 0-N,                       # 出走取消回数
    'racer_age': 18-65,                   # 年齢
    'racer_weight': 40-70                 # 体重 (kg)
}
```

#### 4.1.2 機材関連特徴量 (6次元)

```python
features = {
    'motor_number': 1-N,                  # モーター番号
    'motor_2ren_rate': 0.0-1.0,          # モーター2連対率
    'motor_3ren_rate': 0.0-1.0,          # モーター3連対率
    'boat_number': 1-N,                   # ボート番号
    'boat_2ren_rate': 0.0-1.0,           # ボート2連対率
    'boat_3ren_rate': 0.0-1.0            # ボート3連対率
}
```

#### 4.1.3 環境関連特徴量 (8次元)

```python
features = {
    'wind_speed': 0-20,                   # 風速 (m/s)
    'wind_direction': 0-7,                # 風向 (8方位をエンコード)
    'wave_height': 0-20,                  # 波高 (cm)
    'temperature': -10-40,                # 気温 (℃)
    'weather_condition': 0-3,             # 天候 (晴=0, 曇=1, 雨=2, 雪=3)
    'water_temperature': 0-35,            # 水温 (℃)
    'tide_level': 0-300,                  # 潮位 (cm)
    'tide_status': 0-3                    # 潮汐状態 (rising=0, high=1, falling=2, low=3)
}
```

#### 4.1.4 派生特徴量 (16次元)

```python
# 経験値スコア
experience_score = win_rate * racer_class

# モーター総合性能
motor_performance = motor_2ren_rate + motor_3ren_rate

# 枠番優位性 (統計的計算)
pit_advantage = {
    1: 0.55,  # 1コース1着率 55%
    2: 0.14,
    3: 0.12,
    4: 0.10,
    5: 0.06,
    6: 0.03
}

# 直近フォーム (Phase 1追加)
recent_form = calculate_recent_n_races_avg_rank(racer_number, n=5)

# 会場経験値
venue_experience = count_races_at_venue(racer_number, venue_code)

# 対戦成績
head_to_head = calculate_win_rate_vs_opponents(racer_number, opponent_list)

# 天候変化フラグ
weather_change = abs(today_wind_speed - avg_wind_speed_7days)

# レース重要度
race_importance = {
    'SG': 5,
    'G1': 4,
    'G2': 3,
    'G3': 2,
    '一般': 1
}
```

**Phase 1 特徴量合計**: 約40次元

### 4.2 Phase 2: 時系列特徴量

[src/features/timeseries_features.py](src/features/timeseries_features.py:1)

**クラス**: `TimeseriesFeatureGenerator`

#### 4.2.1 選手トレンド特徴量 (6次元)

```python
# 直近5戦のモメンタム
momentum_score = sum([
    6 - rank_i for rank_i in recent_5_races
]) / 15.0  # 正規化

# トレンド (改善/安定/悪化)
recent_trend = classify_trend(recent_10_races)  # -1, 0, +1

# 一貫性 (標準偏差)
consistency = 1.0 / (std(recent_10_races) + 0.1)

# ピークパフォーマンス (最高着順の頻度)
peak_performance = count(recent_20_races, rank <= 2) / 20.0

# 直近3戦平均着順
recent_3_avg_rank = mean(recent_3_races)

# 直近10戦平均着順
recent_10_avg_rank = mean(recent_10_races)
```

#### 4.2.2 モータートレンド特徴量 (5次元)

```python
# モーター使用日数
motor_age_days = (today - motor_first_use_date).days

# モーター性能トレンド (過去30日)
motor_performance_trend = (
    motor_recent_30d_2ren_rate - motor_overall_2ren_rate
)

# モーター安定性
motor_stability = 1.0 / (std(motor_recent_20_races) + 0.1)

# 直近モーターパフォーマンス
motor_recent_performance = mean([
    2ren_rate_last_5_races
])

# 部品交換後レース数
races_since_parts_replacement = count_races_since_last_replacement()
```

#### 4.2.3 環境トレンド特徴量 (4次元)

```python
# 風速変動 (過去7日)
wind_volatility = std(wind_speed_last_7_days)

# 波高変動 (過去7日)
wave_volatility = std(wave_height_last_7_days)

# 気温トレンド (上昇/下降)
temp_trend = today_temp - mean(temp_last_7_days)

# 条件安定性 (風・波の総合変動)
condition_stability = 1.0 / (wind_volatility + wave_volatility + 0.1)
```

#### 4.2.4 季節・周期特徴量 (4次元)

```python
# 月 (1-12)
month = datetime.now().month

# 季節 (0-3)
season = {
    1-3: 0,   # 冬
    4-6: 1,   # 春
    7-9: 2,   # 夏
    10-12: 3  # 秋
}

# 月の進行度 (0-1)
month_progress = day_of_month / days_in_month

# 周期性エンコーディング
month_sin = sin(2 * pi * month / 12)
month_cos = cos(2 * pi * month / 12)

# 夏フラグ
is_summer = (month in [6, 7, 8])

# 冬フラグ
is_winter = (month in [12, 1, 2])
```

**Phase 2 特徴量合計**: 約19次元

### 4.3 Phase 3: リアルタイム特徴量

[src/prediction/realtime_system.py](src/prediction/realtime_system.py:1)

#### 4.3.1 直前情報特徴量

```python
# 展示タイム
exhibition_time = 6.70  # 秒 (6.5秒以下が優秀)

# 展示タイム評価
exhibition_score = {
    exhibition_time <= 6.50: 10,
    exhibition_time <= 6.65: 5,
    exhibition_time <= 6.80: 0,
    exhibition_time > 6.80: -5
}

# 実際の進入コース (枠番と異なる場合)
actual_course = 3  # 1-6
course_change_flag = (actual_course != pit_number)

# STタイミング (直近レースデータ)
st_time = 0.15  # 0.00がベスト

# オッズ変動 (過去1時間)
odds_change = current_odds - odds_1hour_ago
odds_volatility = std(odds_last_1hour)
```

#### 4.3.2 相対特徴量 (レース内比較)

```python
# レース内勝率ランキング
win_rate_rank = rank_within_race(win_rate, racers)  # 1-6

# レース内モーター性能ランキング
motor_rank = rank_within_race(motor_2ren_rate, racers)

# レース内ST平均比較
st_advantage = avg_st - mean([r.avg_st for r in racers])

# レース内最高勝率との差
win_rate_gap = max_win_rate_in_race - win_rate
```

**Phase 3 特徴量合計**: 約10次元

### 4.4 特徴量生成パイプライン

```python
class FeaturePipeline:
    def generate_all_features(self, race_data):
        # Phase 1: 基本特徴量
        basic_features = self.optimized_feature_gen.generate(race_data)

        # Phase 2: 時系列特徴量
        timeseries_features = self.timeseries_feature_gen.generate(
            race_data, lookback_days=30
        )

        # Phase 3: リアルタイム特徴量
        realtime_features = self.realtime_feature_gen.generate(
            race_data, current_datetime
        )

        # 統合
        all_features = pd.concat([
            basic_features,
            timeseries_features,
            realtime_features
        ], axis=1)

        return all_features  # 約70次元
```

---

## 5. 機械学習モデル

### 5.1 モデル構成

#### 5.1.1 アーキテクチャ

[src/ml/ensemble_predictor.py](src/ml/ensemble_predictor.py:1-190)

```
┌─────────────────────────────────────────────────────────┐
│             Ensemble Predictor (統合予測器)              │
└─────────────────┬───────────────────────────────────────┘
                  │
    ┌─────────────┴─────────────┐
    │                           │
    ▼                           ▼
┌──────────────┐        ┌──────────────────┐
│ 会場別モデル  │        │   統合モデル       │
│  (9モデル)   │        │  (全24場対応)     │
└──────────────┘        └──────────────────┘
│              │        │                  │
│ 蒲郡 (07)    │        │ XGBoost          │
│ AUC: 0.9341  │        │ AUC: 0.8324      │
│              │        │                  │
│ 常滑 (08)    │        │ 8ヶ月訓練データ   │
│ AUC: 0.8715  │        │                  │
│              │        └──────────────────┘
│ ... (他7場)  │
└──────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│  適応的重み付け統合                  │
│  weight = f(venue_auc, race_grade)  │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│  確率校正 (Isotonic Regression)     │
│  ECE: 0.0085                        │
└─────────────────────────────────────┘
        │
        ▼
    最終予測確率
```

#### 5.1.2 会場別モデルの性能

```python
VENUE_WEIGHTS = {
    '07': 0.9341,  # 蒲郡 (最高性能)
    '08': 0.8715,  # 常滑
    '05': 0.8512,  # 多摩川
    '12': 0.8496,  # 住之江
    '06': 0.8451,  # 浜名湖
    '01': 0.8343,  # 桐生
    '04': 0.8062,  # 平和島
    '02': 0.7658,  # 戸田
    '03': 0.7553,  # 江戸川
}

GENERAL_MODEL_AUC = 0.8324
```

**選定理由**:
- 上位9場: データ量が多く、特性が明確
- その他15場: データ不足のため統合モデルで対応

### 5.2 XGBoost パラメータ

[src/ml/model_trainer.py](src/ml/model_trainer.py:1)

```python
xgb_params = {
    'objective': 'binary:logistic',     # 二値分類
    'eval_metric': 'auc',               # AUC最大化
    'max_depth': 6,                     # 木の深さ
    'learning_rate': 0.05,              # 学習率 (小さめで過学習防止)
    'n_estimators': 500,                # 決定木の数
    'subsample': 0.8,                   # 行サンプリング
    'colsample_bytree': 0.8,            # 列サンプリング
    'min_child_weight': 3,              # 葉の最小重み
    'gamma': 0.1,                       # 分割の最小損失削減
    'scale_pos_weight': 1.5,            # クラス不均衡対応 (1着:5着 = 1:5)
    'random_state': 42,
    'n_jobs': -1,                       # 並列処理
    'tree_method': 'hist',              # 高速ヒストグラム法
    'early_stopping_rounds': 50         # Early Stopping
}
```

**ハイパーパラメータ調整**:
- Optunaによる最適化 (50試行)
- 交差検証: 5-fold CV
- 評価指標: AUC, Log Loss

### 5.3 アンサンブルロジック

#### 5.3.1 適応的重み計算

```python
def calculate_adaptive_weight(venue_code, race_grade, confidence_required):
    """
    状況に応じた適応的重み計算

    Args:
        venue_code: 会場コード
        race_grade: レースグレード (SG/G1/G2/G3/一般)
        confidence_required: 必要な確信度 (0-1)

    Returns:
        float: 会場別モデルの重み (0.3-0.9)
    """
    # 会場性能取得
    venue_auc = VENUE_WEIGHTS.get(venue_code, 0.75)

    # ベース重み: 会場性能 / (会場性能 + 統合モデル性能)
    base_weight = venue_auc / (venue_auc + GENERAL_MODEL_AUC)
    # 例: 0.9341 / (0.9341 + 0.8324) = 0.529

    # レース重要度による調整
    grade_bonus = {
        'SG': 0.0,      # 重要レースでは統合モデル重視
        'G1': 0.05,
        'G2': 0.10,
        'G3': 0.15,
        '一般': 0.20,   # 一般戦では会場特化重視
    }
    adjustment = grade_bonus.get(race_grade, 0.10)

    # 高確信度が必要な場合は会場特化モデルを重視
    if confidence_required > 0.7 and venue_auc > 0.85:
        adjustment += 0.15

    # 最終重み (0.3-0.9の範囲に制限)
    final_weight = np.clip(base_weight + adjustment, 0.3, 0.9)

    return final_weight
```

**例**:
- 蒲郡 (AUC 0.9341) + SG: weight = 0.53
- 蒲郡 + 一般戦: weight = 0.73
- 江戸川 (AUC 0.7553) + 一般戦: weight = 0.50

#### 5.3.2 予測統合

```python
def predict_proba(features, venue_code, race_grade):
    """アンサンブル予測"""
    predictions = []
    weights = []

    # 会場別モデルの予測
    if venue_code in venue_models:
        venue_pred = venue_models[venue_code].predict_proba(features)[0, 1]
        venue_weight = calculate_adaptive_weight(venue_code, race_grade, 0.5)
        predictions.append(venue_pred)
        weights.append(venue_weight)

    # 統合モデルの予測
    general_pred = general_model.predict_proba(features)[0, 1]
    general_weight = 1.0 - venue_weight
    predictions.append(general_pred)
    weights.append(general_weight)

    # 重み付き平均
    ensemble_pred = np.average(predictions, weights=weights)

    return ensemble_pred
```

### 5.4 確率校正

[src/ml/probability_calibration.py](src/ml/probability_calibration.py:1)

**手法**: Isotonic Regression

**目的**: 予測確率の信頼性向上

**アルゴリズム**:
```python
from sklearn.isotonic import IsotonicRegression

# 訓練
calibrator = IsotonicRegression(out_of_bounds='clip')
calibrator.fit(y_pred_proba, y_true)

# 予測
calibrated_proba = calibrator.predict(raw_proba)
```

**効果** (検証結果):

| 指標 | 校正前 | 校正後 | 改善率 |
|------|--------|--------|--------|
| Log Loss | 0.5624 | 0.5300 | 5.76% |
| Brier Score | 0.1902 | 0.1774 | 6.71% |
| ECE | 0.1128 | 0.0085 | **92.47%** |

**ECE (Expected Calibration Error)**:
```python
def calculate_ece(y_true, y_pred, n_bins=10):
    """
    予測確率の校正誤差を計算

    理想: 予測確率10%のサンプルで実際の陽性率も10%
    """
    bins = np.linspace(0, 1, n_bins + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2

    ece = 0.0
    for i in range(n_bins):
        mask = (y_pred >= bins[i]) & (y_pred < bins[i+1])
        if mask.sum() > 0:
            bin_acc = y_true[mask].mean()
            bin_conf = y_pred[mask].mean()
            ece += abs(bin_acc - bin_conf) * mask.sum()

    ece /= len(y_true)
    return ece
```

---

## 6. 予測エンジン

### 6.1 統合予測システム

[src/prediction/integrated_predictor.py](src/prediction/integrated_predictor.py:1-120)

**クラス**: `IntegratedPredictor`

#### 6.1.1 予測フロー

```python
class IntegratedPredictor:
    def predict_race(self, race_data):
        """
        レース全体の予測

        Returns:
            {
                'predictions': [
                    {
                        'pit_number': 1,
                        'win_prob': 0.35,
                        'rank_probs': [0.35, 0.25, 0.20, 0.10, 0.07, 0.03],
                        'kimarite_probs': {'nige': 0.80, 'makuri': 0.15, 'sashi': 0.05}
                    },
                    # ... 6艇分
                ],
                'recommended_combinations': ['1-2-3', '1-3-2', '1-2-4'],
                'confidence_scores': [0.85, 0.78, 0.72]
            }
        """
        # 1. 特徴量生成
        features = self._generate_all_features(race_data)

        # 2. Phase 2: アンサンブル予測
        ensemble_probs = []
        for racer_features in features:
            prob = self.ensemble_predictor.predict_proba(
                racer_features,
                venue_code=race_data['venue_code'],
                race_grade=race_data['race_grade']
            )
            ensemble_probs.append(prob)

        # 3. 確率校正
        calibrated_probs = self.calibrator.predict(ensemble_probs)

        # 4. Phase 3: リアルタイム情報反映
        final_probs = self.realtime_system.update_with_latest_info(
            calibrated_probs,
            race_data
        )

        # 5. 着順確率分布計算
        rank_distributions = self._calculate_rank_distributions(final_probs)

        # 6. 決まり手予測
        kimarite_probs = self._predict_kimarite(race_data, final_probs)

        # 7. 推奨組み合わせ生成
        recommendations = self._generate_recommendations(
            final_probs,
            rank_distributions
        )

        return {
            'predictions': self._format_predictions(
                final_probs, rank_distributions, kimarite_probs
            ),
            'recommended_combinations': recommendations['combinations'],
            'confidence_scores': recommendations['scores']
        }
```

#### 6.1.2 着順確率分布計算

```python
def _calculate_rank_distributions(self, win_probs):
    """
    1着確率から2着〜6着確率を推定

    アルゴリズム:
    - 1着確率: モデル出力
    - 2着確率: (1 - 自分の1着確率) × 他艇の1着確率の比率
    - 3着以降: 同様の方法で計算
    """
    n_racers = len(win_probs)
    rank_distributions = np.zeros((n_racers, n_racers))

    for racer_idx in range(n_racers):
        # 1着確率
        rank_distributions[racer_idx, 0] = win_probs[racer_idx]

        # 2着以降の確率
        remaining_prob = 1.0 - win_probs[racer_idx]
        other_probs = [win_probs[i] for i in range(n_racers) if i != racer_idx]

        for rank in range(1, n_racers):
            if rank == 1:
                # 2着確率
                rank_distributions[racer_idx, rank] = (
                    remaining_prob * other_probs[0] / sum(other_probs)
                )
            else:
                # 3着以降
                remaining_prob -= rank_distributions[racer_idx, rank-1]
                other_probs = [p for p in other_probs if p not in already_used]
                rank_distributions[racer_idx, rank] = (
                    remaining_prob * other_probs[0] / sum(other_probs)
                )

    return rank_distributions
```

### 6.2 決まり手予測

[src/prediction/kimarite_probability_engine.py](src/prediction/kimarite_probability_engine.py:1)

**決まり手の種類**:
- **逃げ**: 1コースが先行してそのまま勝つ
- **まくり**: 外側からスピードで抜き去る
- **差し**: ターンで内側を突く
- **まくり差し**: まくりと差しの複合
- **抜き**: 直線で追い抜く
- **恵まれ**: 前の艇のミスによる勝利

**予測ロジック**:
```python
def predict_kimarite(pit_number, actual_course, wind_speed, wave_height):
    """
    決まり手確率を予測

    Returns:
        {'nige': 0.70, 'makuri': 0.20, 'sashi': 0.10, ...}
    """
    # コース別基本確率
    base_probs = {
        1: {'nige': 0.95, 'makuri': 0.02, 'sashi': 0.03},
        2: {'nige': 0.05, 'makuri': 0.30, 'sashi': 0.65},
        3: {'nige': 0.01, 'makuri': 0.60, 'sashi': 0.39},
        4: {'nige': 0.00, 'makuri': 0.85, 'sashi': 0.15},
        5: {'nige': 0.00, 'makuri': 0.90, 'sashi': 0.10},
        6: {'nige': 0.00, 'makuri': 0.95, 'sashi': 0.05},
    }

    probs = base_probs[actual_course].copy()

    # 風速補正 (5m/s以上で逃げ不利)
    if wind_speed > 5.0:
        probs['nige'] *= 0.7
        probs['makuri'] *= 1.2
        probs['sashi'] *= 1.1

    # 波高補正 (15cm以上で差し有利)
    if wave_height > 15.0:
        probs['sashi'] *= 1.3
        probs['nige'] *= 0.8

    # 正規化
    total = sum(probs.values())
    probs = {k: v/total for k, v in probs.items()}

    return probs
```

### 6.3 説明可能性 (XAI)

[src/prediction/xai_explainer.py](src/prediction/xai_explainer.py:1)

**SHAP (SHapley Additive exPlanations)**

```python
import shap

class XAIExplainer:
    def __init__(self, model, feature_names):
        self.model = model
        self.feature_names = feature_names
        self.explainer = shap.TreeExplainer(model)

    def explain_prediction(self, features):
        """
        予測の根拠を説明

        Returns:
            {
                'base_value': 0.167,  # ベース確率 (1/6)
                'shap_values': {
                    'win_rate': +0.12,
                    'motor_2ren_rate': +0.08,
                    'pit_number': +0.05,
                    'wind_speed': -0.03,
                    ...
                },
                'final_prediction': 0.35
            }
        """
        shap_values = self.explainer.shap_values(features)

        # 特徴量ごとの寄与度
        contributions = {}
        for i, feature_name in enumerate(self.feature_names):
            contributions[feature_name] = shap_values[i]

        # 寄与度順にソート
        sorted_contributions = sorted(
            contributions.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        )

        return {
            'base_value': self.explainer.expected_value,
            'shap_values': dict(sorted_contributions),
            'final_prediction': (
                self.explainer.expected_value + sum(shap_values)
            )
        }

    def get_top_features(self, features, top_n=10):
        """最も影響した特徴量を取得"""
        explanation = self.explain_prediction(features)
        return list(explanation['shap_values'].items())[:top_n]
```

**出力例**:
```
予測確率: 35%

主要な寄与要因:
1. win_rate: +0.12 (勝率が高い)
2. motor_2ren_rate: +0.08 (モーター性能良好)
3. pit_number (1コース): +0.05 (枠順有利)
4. recent_form: +0.04 (直近好調)
5. wind_speed: -0.03 (風速が不利に働く)
```

---

## 7. ベッティング戦略

### 7.1 Kelly 基準

[src/betting/kelly_strategy.py](src/betting/kelly_strategy.py:1-485)

#### 7.1.1 理論的背景

**Kelly Formula**:
```
f* = (bp - q) / b

where:
  f*: 最適賭け金比率 (0-1)
  b: 純利益倍率 (odds - 1)
  p: 予測勝率
  q: 予測負率 (1 - p)
```

**例**:
- 予測確率: p = 0.20 (20%)
- オッズ: 6.0倍
- b = 6.0 - 1.0 = 5.0
- q = 0.80

```
f* = (5.0 × 0.20 - 0.80) / 5.0
   = (1.0 - 0.80) / 5.0
   = 0.20 / 5.0
   = 0.04 (4%)
```

→ 資金の4%を賭けるのが最適

#### 7.1.2 実装

```python
class KellyBettingStrategy:
    def __init__(self, bankroll=10000, kelly_fraction=0.25, min_ev=0.05):
        """
        Args:
            bankroll: 資金 (円)
            kelly_fraction: Kelly分数 (0.25 = 1/4 Kelly, リスク調整)
            min_ev: 最小期待値 (5%以上)
        """
        self.bankroll = bankroll
        self.kelly_fraction = kelly_fraction
        self.min_ev = min_ev

    def calculate_expected_value(self, pred_prob, odds):
        """
        期待値 = pred_prob × odds - 1

        例: 予測20%, オッズ6.0倍
        EV = 0.20 × 6.0 - 1.0 = 0.20 (20%)
        """
        return pred_prob * odds - 1.0

    def calculate_kelly_bet(self, pred_prob, odds):
        """
        Kelly基準での賭け金を計算

        Returns:
            (kelly_fraction, bet_amount)
        """
        p = pred_prob
        b = odds - 1.0
        q = 1.0 - p

        # Kelly formula
        kelly_f = (b * p - q) / b

        # Fractional Kelly (リスク削減)
        adjusted_kelly_f = max(0.0, kelly_f * self.kelly_fraction)

        # 最大賭け金制限 (資金の20%まで)
        adjusted_kelly_f = min(adjusted_kelly_f, 0.2)

        bet_amount = self.bankroll * adjusted_kelly_f

        return adjusted_kelly_f, bet_amount
```

#### 7.1.3 買い目選定ロジック

```python
def select_bets(self, predictions, odds_data, buy_score=1.0):
    """
    購入すべき買い目を選定

    Args:
        predictions: [{'combination': '1-2-3', 'prob': 0.15}, ...]
        odds_data: {'1-2-3': 10.5, '1-3-2': 15.2, ...}
        buy_score: レース選別スコア (Stage1の出力, 0-1)

    Returns:
        List[BetRecommendation]
    """
    recommendations = []

    for pred in predictions:
        combination = pred['combination']
        pred_prob = pred['prob']

        if combination not in odds_data:
            continue

        odds = odds_data[combination]

        # 期待値計算
        ev = self.calculate_expected_value(pred_prob, odds)

        # 期待値が閾値以下ならスキップ
        if ev < self.min_ev:
            continue

        # Kelly賭け金計算
        kelly_f, bet_amount = self.calculate_kelly_bet(pred_prob, odds)

        # buy_scoreで調整 (Stage1の信頼度を反映)
        adjusted_bet_amount = bet_amount * buy_score

        # 信頼度判定
        if ev > 0.15 and buy_score > 0.7:
            confidence = "High"
        elif ev > 0.08 and buy_score > 0.5:
            confidence = "Medium"
        else:
            confidence = "Low"

        recommendations.append(BetRecommendation(
            combination=combination,
            pred_prob=pred_prob,
            odds=odds,
            expected_value=ev,
            kelly_fraction=kelly_f,
            recommended_bet=adjusted_bet_amount,
            confidence=confidence
        ))

    # 期待値順にソート
    recommendations.sort(key=lambda x: x.expected_value, reverse=True)

    return recommendations
```

### 7.2 ポートフォリオ最適化

```python
def optimize_portfolio(self, recommendations, max_combinations=5):
    """
    複数の買い目を組み合わせて、リスク分散しつつリターンを最大化

    Args:
        recommendations: 購入推奨リスト
        max_combinations: 最大購入組み合わせ数

    Returns:
        最適化された購入推奨リスト
    """
    # 上位N件を選択
    top_recommendations = recommendations[:max_combinations]

    # 総賭け金が資金を超えないように調整
    total_bet = sum(rec.recommended_bet for rec in top_recommendations)

    if total_bet > self.bankroll * 0.2:  # 資金の20%まで
        # 比例配分で調整
        adjustment_factor = (self.bankroll * 0.2) / total_bet

        optimized = []
        for rec in top_recommendations:
            optimized.append(BetRecommendation(
                combination=rec.combination,
                pred_prob=rec.pred_prob,
                odds=rec.odds,
                expected_value=rec.expected_value,
                kelly_fraction=rec.kelly_fraction * adjustment_factor,
                recommended_bet=rec.recommended_bet * adjustment_factor,
                confidence=rec.confidence
            ))
        return optimized

    return top_recommendations
```

### 7.3 期待値分析

```python
class ExpectedValueCalculator:
    @staticmethod
    def calculate_breakeven_odds(pred_prob):
        """
        損益分岐点オッズを計算

        例: 予測確率20% → 損益分岐点オッズ = 5.0倍
        """
        return 1.0 / pred_prob

    @staticmethod
    def calculate_edge(pred_prob, odds):
        """
        エッジ (優位性) を計算

        エッジ = (予測確率 - オッズ含意確率) / オッズ含意確率 × 100

        例:
        予測確率: 20%
        オッズ: 6.0倍 → 含意確率 = 1/6 = 16.7%
        エッジ = (0.20 - 0.167) / 0.167 × 100 = 19.8%
        """
        implied_prob = 1.0 / odds
        edge = (pred_prob - implied_prob) / implied_prob * 100
        return edge

    @staticmethod
    def calculate_roi_range(pred_prob, odds, bet_amount):
        """
        ROIの信頼区間を計算 (95%)

        Returns:
            (lower_roi, upper_roi)
        """
        expected_return = pred_prob * odds * bet_amount
        std_return = np.sqrt(pred_prob * (1 - pred_prob)) * odds * bet_amount

        z_score = 1.96  # 95%信頼区間

        lower_return = expected_return - z_score * std_return
        upper_return = expected_return + z_score * std_return

        lower_roi = (lower_return - bet_amount) / bet_amount * 100
        upper_roi = (upper_return - bet_amount) / bet_amount * 100

        return lower_roi, upper_roi
```

### 7.4 リスク管理

```python
def calculate_risk_metrics(self, bet_history):
    """
    リスク指標を計算

    Args:
        bet_history: 資金推移データ (DataFrame)

    Returns:
        {
            'max_drawdown': -0.15,      # 最大ドローダウン (-15%)
            'win_rate': 0.35,           # 勝率 (35%)
            'avg_roi': 0.08,            # 平均ROI (8%)
            'sharpe_ratio': 1.2,        # シャープレシオ
            'total_profit': 5000        # 総利益 (円)
        }
    """
    # 最大ドローダウン
    cummax = bet_history['bankroll'].cummax()
    drawdown = (bet_history['bankroll'] - cummax) / cummax
    max_drawdown = drawdown.min()

    # 勝率
    win_rate = (bet_history['profit'] > 0).mean()

    # 平均ROI
    avg_roi = bet_history['roi'].mean()

    # シャープレシオ (リスク調整後リターン)
    returns = bet_history['bankroll'].pct_change().dropna()
    sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252)

    return {
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'avg_roi': avg_roi,
        'sharpe_ratio': sharpe_ratio,
        'total_bets': len(bet_history),
        'total_profit': bet_history['profit'].sum(),
        'final_bankroll': bet_history['bankroll'].iloc[-1]
    }
```

---

## 8. 主要なアルゴリズム詳細

### 8.1 コース別勝率計算

[src/analysis/statistics_calculator.py](src/analysis/statistics_calculator.py:1)

```python
def calculate_course_win_rates(venue_code, lookback_days=90):
    """
    コース別の1着率・2着率・3着率を計算

    Args:
        venue_code: 会場コード
        lookback_days: 集計期間 (デフォルト90日)

    Returns:
        {
            1: {'win_rate': 0.55, '2nd_rate': 0.17, '3rd_rate': 0.10},
            2: {'win_rate': 0.14, '2nd_rate': 0.25, '3rd_rate': 0.20},
            3: {'win_rate': 0.12, '2nd_rate': 0.21, '3rd_rate': 0.21},
            4: {'win_rate': 0.10, '2nd_rate': 0.17, '3rd_rate': 0.20},
            5: {'win_rate': 0.06, '2nd_rate': 0.12, '3rd_rate': 0.17},
            6: {'win_rate': 0.03, '2nd_rate': 0.08, '3rd_rate': 0.12}
        }
    """
    query = """
        SELECT
            rd.actual_course,
            r.rank,
            COUNT(*) as count
        FROM results r
        JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
        JOIN races rc ON r.race_id = rc.id
        WHERE rc.venue_code = ?
          AND rc.race_date >= date('now', '-? days')
          AND r.rank IN ('1', '2', '3')
        GROUP BY rd.actual_course, r.rank
    """

    results = execute_query(query, (venue_code, lookback_days))

    # 集計
    stats = {}
    for course in range(1, 7):
        total = sum(r['count'] for r in results if r['actual_course'] == course)
        win_count = sum(r['count'] for r in results
                        if r['actual_course'] == course and r['rank'] == '1')
        second_count = sum(r['count'] for r in results
                          if r['actual_course'] == course and r['rank'] == '2')
        third_count = sum(r['count'] for r in results
                         if r['actual_course'] == course and r['rank'] == '3')

        stats[course] = {
            'win_rate': win_count / total if total > 0 else 0,
            '2nd_rate': second_count / total if total > 0 else 0,
            '3rd_rate': third_count / total if total > 0 else 0
        }

    return stats
```

### 8.2 直近フォーム計算

```python
def calculate_recent_form(racer_number, n_races=5):
    """
    直近N戦の平均着順を計算

    Args:
        racer_number: 選手登録番号
        n_races: 集計レース数

    Returns:
        float: 平均着順 (1.0-6.0)
    """
    query = """
        SELECT r.rank
        FROM results r
        JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
        JOIN races rc ON r.race_id = rc.id
        WHERE e.racer_number = ?
          AND r.rank IN ('1', '2', '3', '4', '5', '6')
        ORDER BY rc.race_date DESC, rc.race_number DESC
        LIMIT ?
    """

    ranks = execute_query(query, (racer_number, n_races))

    if len(ranks) == 0:
        return 3.5  # デフォルト値

    avg_rank = sum(int(r['rank']) for r in ranks) / len(ranks)
    return avg_rank
```

### 8.3 モータートレンド分析

```python
def analyze_motor_trend(motor_number, venue_code, lookback_days=30):
    """
    モーター性能のトレンドを分析

    Returns:
        {
            'recent_2ren_rate': 0.45,
            'overall_2ren_rate': 0.38,
            'trend': 'improving',  # improving/stable/declining
            'days_used': 180,
            'races_count': 50
        }
    """
    # 直近30日の2連対率
    recent_query = """
        SELECT
            SUM(CASE WHEN r.rank IN ('1', '2') THEN 1 ELSE 0 END) as wins,
            COUNT(*) as total
        FROM results r
        JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
        JOIN races rc ON r.race_id = rc.id
        WHERE e.motor_number = ?
          AND rc.venue_code = ?
          AND rc.race_date >= date('now', '-? days')
          AND r.rank IN ('1', '2', '3', '4', '5', '6')
    """

    recent_stats = execute_query(recent_query, (motor_number, venue_code, lookback_days))[0]
    recent_2ren_rate = recent_stats['wins'] / recent_stats['total'] if recent_stats['total'] > 0 else 0

    # 全期間の2連対率
    overall_query = """
        SELECT
            SUM(CASE WHEN r.rank IN ('1', '2') THEN 1 ELSE 0 END) as wins,
            COUNT(*) as total
        FROM results r
        JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
        JOIN races rc ON r.race_id = rc.id
        WHERE e.motor_number = ?
          AND rc.venue_code = ?
          AND r.rank IN ('1', '2', '3', '4', '5', '6')
    """

    overall_stats = execute_query(overall_query, (motor_number, venue_code))[0]
    overall_2ren_rate = overall_stats['wins'] / overall_stats['total'] if overall_stats['total'] > 0 else 0

    # トレンド判定
    diff = recent_2ren_rate - overall_2ren_rate
    if diff > 0.05:
        trend = 'improving'
    elif diff < -0.05:
        trend = 'declining'
    else:
        trend = 'stable'

    return {
        'recent_2ren_rate': recent_2ren_rate,
        'overall_2ren_rate': overall_2ren_rate,
        'trend': trend,
        'races_count': overall_stats['total']
    }
```

### 8.4 三連単確率計算

```python
def calculate_trifecta_probabilities(win_probs):
    """
    1着確率から三連単確率を計算

    Args:
        win_probs: [0.35, 0.20, 0.18, 0.12, 0.10, 0.05]  # 6艇の1着確率

    Returns:
        {
            '1-2-3': 0.126,
            '1-3-2': 0.113,
            ...
        }
    """
    trifecta_probs = {}

    for i in range(6):
        p1 = win_probs[i]  # 1着確率

        # 2着候補の確率調整
        remaining_probs_2nd = [
            win_probs[j] for j in range(6) if j != i
        ]
        total_2nd = sum(remaining_probs_2nd)
        normalized_2nd = [p / total_2nd for p in remaining_probs_2nd]

        for j_idx, j in enumerate([k for k in range(6) if k != i]):
            p2 = normalized_2nd[j_idx]  # 2着確率

            # 3着候補の確率調整
            remaining_probs_3rd = [
                win_probs[k] for k in range(6) if k != i and k != j
            ]
            total_3rd = sum(remaining_probs_3rd)
            normalized_3rd = [p / total_3rd for p in remaining_probs_3rd]

            for k_idx, k in enumerate([m for m in range(6) if m != i and m != j]):
                p3 = normalized_3rd[k_idx]  # 3着確率

                # 三連単確率
                prob = p1 * p2 * p3
                combination = f"{i+1}-{j+1}-{k+1}"
                trifecta_probs[combination] = prob

    return trifecta_probs
```

---

## 9. データフローと処理パイプライン

### 9.1 全体フロー

```
[1] データ収集
    ↓
    スクレイピング (24競艇場 × 365日 × 12R)
    ↓
    HTML解析 → 構造化データ
    ↓
[2] データ保存
    ↓
    データ検証 (スキーマチェック)
    ↓
    SQLite挿入 (トランザクション管理)
    ↓
[3] 統計分析
    ↓
    会場別集計 (コース別勝率、決まり手分布)
    選手別集計 (勝率、直近フォーム)
    モーター別集計 (2連対率、トレンド)
    ↓
[4] 特徴量生成
    ↓
    Phase 1: 基本特徴量 (40次元)
    Phase 2: 時系列特徴量 (19次元)
    Phase 3: リアルタイム特徴量 (10次元)
    ↓
[5] モデル予測
    ↓
    会場別モデル予測
    統合モデル予測
    アンサンブル統合 (適応的重み付け)
    確率校正 (Isotonic Regression)
    ↓
[6] 着順予測
    ↓
    1着確率 → 2着〜6着確率計算
    決まり手予測
    三連単確率計算
    ↓
[7] ベッティング戦略
    ↓
    期待値計算 (EV = pred_prob × odds - 1)
    Kelly基準資金配分
    ポートフォリオ最適化
    ↓
[8] 購入推奨
    ↓
    推奨買い目リスト
    推奨賭け金
    信頼度 (High/Medium/Low)
```

### 9.2 リアルタイム予想のパイプライン

```python
def realtime_prediction_pipeline(venue_code, race_date, race_number):
    """
    リアルタイム予想パイプライン

    実行時間: 約2-3秒
    """
    # [1] データ取得 (0.5秒)
    race_data = fetch_race_data(venue_code, race_date, race_number)
    entries = fetch_entries(venue_code, race_date, race_number)
    weather = fetch_weather(venue_code, race_date)
    tide = fetch_tide_data(venue_code, race_date)

    # [2] 特徴量生成 (0.8秒)
    features_list = []
    for entry in entries:
        features = generate_all_features(
            entry, race_data, weather, tide
        )
        features_list.append(features)

    # [3] モデル予測 (0.5秒)
    predictions = []
    for features in features_list:
        prob = integrated_predictor.predict_proba(
            features, venue_code, race_data['race_grade']
        )
        predictions.append(prob)

    # [4] 着順予測 (0.2秒)
    rank_distributions = calculate_rank_distributions(predictions)
    trifecta_probs = calculate_trifecta_probabilities(predictions)

    # [5] オッズ取得 (0.3秒)
    odds_data = fetch_realtime_odds(venue_code, race_date, race_number)

    # [6] ベッティング戦略 (0.2秒)
    bet_recommendations = kelly_strategy.select_bets(
        [{'combination': k, 'prob': v} for k, v in trifecta_probs.items()],
        odds_data,
        buy_score=0.8
    )

    # [7] 結果返却
    return {
        'predictions': predictions,
        'rank_distributions': rank_distributions,
        'trifecta_probs': trifecta_probs,
        'bet_recommendations': bet_recommendations
    }
```

### 9.3 バックテストパイプライン

```python
def backtest_pipeline(start_date, end_date, initial_bankroll=100000):
    """
    バックテストパイプライン

    Args:
        start_date: 開始日 (YYYY-MM-DD)
        end_date: 終了日 (YYYY-MM-DD)
        initial_bankroll: 初期資金

    Returns:
        {
            'total_bets': 150,
            'win_rate': 0.35,
            'total_profit': +15000,
            'roi': 0.10,
            'max_drawdown': -0.08,
            'sharpe_ratio': 1.5,
            'final_bankroll': 115000
        }
    """
    bankroll = initial_bankroll
    bet_history = []

    # 日付範囲のレースを取得
    races = get_races_in_date_range(start_date, end_date)

    for race in races:
        # 予測
        predictions = realtime_prediction_pipeline(
            race['venue_code'],
            race['race_date'],
            race['race_number']
        )

        # 購入判定
        recommendations = predictions['bet_recommendations']

        if len(recommendations) == 0:
            continue  # 購入見送り

        # 実際の結果取得
        actual_result = get_actual_result(
            race['venue_code'],
            race['race_date'],
            race['race_number']
        )

        # 結果シミュレーション
        outcome = kelly_strategy.simulate_outcome(
            recommendations,
            actual_result['trifecta']
        )

        # 資金更新
        bankroll += outcome['profit']

        # 履歴記録
        bet_history.append({
            'date': race['race_date'],
            'venue': race['venue_code'],
            'race_number': race['race_number'],
            'bet': outcome['total_bet'],
            'return': outcome['total_return'],
            'profit': outcome['profit'],
            'bankroll': bankroll,
            'roi': outcome['roi']
        })

    # リスク指標計算
    df_history = pd.DataFrame(bet_history)
    risk_metrics = kelly_strategy.calculate_risk_metrics(df_history)

    return risk_metrics
```

---

## 10. 既知の問題点と改善余地

### 10.1 アーキテクチャ・設計

#### 10.1.1 モジュール重複

**問題**:
- スクレイパーが24ファイルに分散
- バージョン管理が曖昧 (v1, v2, v3, v4)
- 機能重複 (例: `odds_scraper.py` vs `odds_fetcher.py`)

**改善案**:
- 統合スクレイパーの設計
- バージョン管理の明確化
- 共通処理のユーティリティ化

#### 10.1.2 特徴量管理

**問題**:
- Phase 1-3 で特徴量が分散
- 特徴量の依存関係が不明確
- 特徴量の重要度評価が不十分

**改善案**:
- 特徴量レジストリの導入
- 特徴量の依存グラフ可視化
- SHAP による特徴量重要度の定期評価

#### 10.1.3 モデル管理

**問題**:
- 訓練済みモデルが `models/` に未保存
- モデルバージョン管理がない
- A/Bテスト機能がない

**改善案**:
- MLflow 導入によるモデル管理
- モデルバージョニング
- A/Bテストフレームワーク

### 10.2 データ品質

#### 10.2.1 欠損値処理

**問題**:
- 欠損値の処理方針が統一されていない
- 一部カラムで欠損率が高い (天候データ: 約90%欠損)

**改善案**:
- 欠損値処理方針の統一
- 欠損値の原因分析
- 代替データソースの検討

#### 10.2.2 データ整合性

**問題**:
- 外部キー制約が一部欠如
- データ更新時の整合性チェックが不十分

**改善案**:
- 外部キー制約の追加
- データ品質モニタリング
- 自動整合性チェック

### 10.3 機械学習

#### 10.3.1 モデル性能

**問題**:
- Stage1モデルの精度が不明 (AUC未測定)
- クラス不均衡対応が不十分
- ハイパーパラメータ最適化が手動

**改善案**:
- Stage1モデルの精度評価
- SMOTE によるクラス不均衡対応
- Optuna による自動最適化

#### 10.3.2 特徴量エンジニアリング

**問題**:
- 交互作用項が未実装
- ドメイン知識の特徴量化が不十分
- 特徴量の自動生成がない

**改善案**:
- 交互作用項の追加 (例: 風速 × コース)
- ドメインエキスパートへのヒアリング
- AutoFE (Featuretools) の導入

#### 10.3.3 アンサンブル

**問題**:
- 会場別モデルが9場のみ
- 重み付けロジックが経験則ベース
- スタッキングが未実装

**改善案**:
- 全24場の会場別モデル訓練
- メタ学習による重み最適化
- スタッキングアンサンブルの導入

### 10.4 ベッティング戦略

#### 10.4.1 Kelly基準

**問題**:
- Kelly分数が固定 (0.25)
- リスク許容度の動的調整がない
- 連敗時の資金管理ルールがない

**改善案**:
- Kelly分数の動的調整 (勝率に応じて)
- 最大ドローダウン制限
- 連敗時の自動停止機能

#### 10.4.2 ポートフォリオ最適化

**問題**:
- 相関考慮がない (独立前提)
- 最大化目標が期待値のみ
- リスク・リターンのトレードオフ考慮不足

**改善案**:
- 組み合わせ間の相関計算
- Mean-Variance 最適化
- Sharpe Ratio 最大化

### 10.5 パフォーマンス

#### 10.5.1 データベース

**問題**:
- インデックスが不十分
- クエリが最適化されていない
- SQLite の並行アクセス制限

**改善案**:
- 頻出クエリへのインデックス追加
- クエリプロファイリング
- PostgreSQL への移行検討

#### 10.5.2 特徴量生成

**問題**:
- 特徴量生成が逐次処理
- 計算コストの高い特徴量がある
- キャッシュ機構がない

**改善案**:
- 並列処理 (multiprocessing)
- 特徴量の事前計算とキャッシュ
- 増分更新機構

### 10.6 説明可能性

#### 10.6.1 SHAP

**問題**:
- SHAP計算が重い (1予測あたり1-2秒)
- バッチ処理に対応していない
- 可視化が限定的

**改善案**:
- TreeSHAP の高速化
- バッチ処理対応
- インタラクティブ可視化 (SHAP JS)

#### 10.6.2 予測根拠

**問題**:
- 予測根拠の説明が技術的
- ユーザーへの説明が不十分
- 誤予測の分析がない

**改善案**:
- 自然言語での説明生成
- 誤予測の原因分析機能
- 予測信頼区間の表示

### 10.7 テスト・品質

#### 10.7.1 テストカバレッジ

**問題**:
- ユニットテストが不足 (カバレッジ < 20%)
- 統合テストがない
- バックテストの自動化がない

**改善案**:
- pytest によるユニットテスト拡充
- CI/CD パイプライン構築
- 定期バックテストの自動実行

#### 10.7.2 エラーハンドリング

**問題**:
- `except: pass` が多数存在
- エラーログが不十分
- リカバリ機構がない

**改善案**:
- 明示的な例外処理
- 構造化ログ (JSON形式)
- エラー時の自動リトライ

### 10.8 運用

#### 10.8.1 モニタリング

**問題**:
- モデル性能の監視がない
- データドリフト検知がない
- アラート機能がない

**改善案**:
- モデル性能モニタリング (日次)
- データドリフト検知 (Evidently AI)
- Slack/Email アラート

#### 10.8.2 デプロイ

**問題**:
- デプロイ手順が未整備
- ロールバック機構がない
- 環境差異管理がない

**改善案**:
- Docker コンテナ化
- CI/CD パイプライン (GitHub Actions)
- 環境変数管理 (dotenv)

---

## まとめ

本システムは以下の特徴を持つ、競艇予測のための包括的なMLシステムです:

### 強み

1. **データ基盤**: 27万件のレース結果、1.07GBのデータベース
2. **高度なML**: XGBoost アンサンブル + 会場別専門モデル
3. **リアルタイム適応**: 直前情報による動的予測調整
4. **科学的資金管理**: Kelly基準による最適資金配分
5. **説明可能性**: SHAP による予測根拠の可視化

### 改善余地

1. **モジュール統合**: スクレイパー・特徴量の整理
2. **モデル精度**: Stage1のチューニング、特徴量追加
3. **リスク管理**: Kelly分数の動的調整、ドローダウン制限
4. **運用基盤**: モニタリング、CI/CD、エラー処理
5. **パフォーマンス**: DB最適化、特徴量キャッシュ

---

**本ドキュメントの用途**: 外部AIへのシステム改善提案依頼

**改善提案を求める観点**:
- アーキテクチャ設計の改善
- 機械学習モデルの精度向上
- ベッティング戦略の最適化
- パフォーマンス改善
- 運用性の向上
