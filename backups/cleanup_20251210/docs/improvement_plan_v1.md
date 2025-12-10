# ボートレース予想システム 改善計画書

作成日: 2025-11-28
作成者: Claude Code (Opus 4.5)
バージョン: 1.0

---

## エグゼクティブサマリー

### 現状の課題

1. **予想生成パフォーマンス**: 全レース（約144レース/日）の予想生成に27分以上かかる
2. **DBクエリ効率**: 1レースあたり約850回のDBクエリが発生（N+1問題）
3. **直前データ未活用**: 展示タイム・スタート展示などの直前情報が予想更新に反映されていない
4. **データ整合性**: 潮位テーブルが3つ存在（tide, rdmdb_tide, race_tide_data）し、役割が不明確
5. **UI肥大化**: 26個のUIコンポーネントが存在し、重複・未使用機能がある

### 改善目標

| 項目 | 現状 | 目標 |
|------|------|------|
| 予想生成時間（144レース） | 27分 | 3分以内（90%削減） |
| DBクエリ回数/レース | ~850回 | ~3回（99%削減） |
| 直前予想更新 | 未実装 | 自動更新（締切20分前） |
| 潮位テーブル | 3テーブル | 1テーブル統合 |

### 期待される効果

- 予想生成の高速化による運用効率向上
- 直前情報反映による予測精度向上（推定+2-3%）
- コードベースの簡素化・保守性向上
- ユーザー体験の改善

---

## Phase 1: 予想生成高速化 (最優先)

### 目標
- 予想生成時間: 27分 → 3分以内（90%削減）
- DBクエリ回数: ~850回/レース → ~3回/レース（99%削減）

### 現状分析

#### ボトルネック箇所の特定

現在の `race_predictor.py` の `predict_race()` メソッドでは、1レースの予想生成で以下のDBアクセスが発生:

| 処理 | クエリ回数 | 処理時間(推定) |
|------|-----------|---------------|
| レース情報取得 | 1回 | 0.01秒 |
| エントリー情報取得 | 1回 | 0.01秒 |
| 天候データ取得 | 2回 | 0.02秒 |
| RacerAnalyzer (6艇) | 6×7=42回 | 2.1秒 |
| MotorAnalyzer (6艇) | 6×3=18回 | 0.9秒 |
| KimariteScorer (6艇) | 6×2=12回 | 0.6秒 |
| GradeScorer (6艇) | 6×1=6回 | 0.3秒 |
| ExtendedScorer (6艇) | 6×~130=780回 | 7.8秒 |
| **合計** | **~850回** | **~11-12秒** |

#### 主要ボトルネックの詳細

**1. RacerAnalyzer (42クエリ/レース)**

ファイル: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\racer_analyzer.py`

```python
# 行372-449: analyze_race_entries()
# 各選手(6艇)に対して以下を個別実行:
- get_racer_overall_stats()  # 180日分の全成績集計
- get_racer_course_stats()   # コース別成績集計
- get_racer_venue_stats()    # 会場別成績集計
- get_racer_recent_form()    # 直近10戦
- get_racer_st_stats()       # ST統計
```

**2. KimariteScorer (12クエリ/レース)**

ファイル: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\kimarite_scorer.py`

```python
# 行33-177: calculate_kimarite_affinity_score()
# 各選手に対して:
- 選手のコース別決まり手傾向 (180日)
- 会場のコース別決まり手傾向 (180日)
```

**3. GradeScorer (6クエリ/レース)**

ファイル: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\grade_scorer.py`

```python
# 行49-188: calculate_grade_affinity_score()
# 各選手に対して:
- 選手のグレード別成績 (365日)
```

**4. ExtendedScorer (780クエリ/レース)**

ファイル: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\extended_scorer.py`

```python
# 行1191-1370: get_comprehensive_score()
# 各選手に対して13種類のスコア計算:
- calculate_session_performance()     # ~5クエリ
- calculate_previous_race_level()     # ~3クエリ
- calculate_course_entry_tendency()   # ~3クエリ
- analyze_motor_characteristics()     # ~3クエリ
- calculate_exhibition_time_score()   # ~2クエリ
- calculate_tilt_angle_score()        # ~2クエリ
- calculate_recent_form_score()       # ~3クエリ
- calculate_venue_affinity_score()    # ~3クエリ
- calculate_place_rate_score()        # ~3クエリ
# × 6艇 = ~130クエリ × 6 = ~780クエリ
```

### 実装計画

#### Step 1-1: データ一括取得クラスの実装

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\database\batch_data_loader.py` (新規作成)

**変更内容**:
```python
class BatchDataLoader:
    """日単位でデータを一括取得・キャッシュするクラス"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._cache = {}
        self._cache_date = None

    def load_daily_data(self, target_date: str) -> None:
        """指定日の全データを一括取得"""
        # 1クエリで全選手の180日成績を取得
        self._load_racer_stats_batch(target_date)
        # 1クエリで全モーターの90日成績を取得
        self._load_motor_stats_batch(target_date)
        # 1クエリで全会場の決まり手傾向を取得
        self._load_kimarite_stats_batch(target_date)
        # 1クエリで全選手のグレード成績を取得
        self._load_grade_stats_batch(target_date)
        # 1クエリで全選手の拡張スコア用データを取得
        self._load_extended_stats_batch(target_date)

    def get_racer_stats(self, racer_number: int) -> Dict:
        """キャッシュから選手成績を取得"""
        return self._cache.get('racer_stats', {}).get(racer_number, {})
```

**期待効果**:
- DBクエリ: 850回/レース → 5回/日（一括取得）
- 処理時間: 11秒/レース → 1.2秒/レース

**SQLクエリ例（選手成績一括取得）**:
```sql
-- 対象日に出走する全選手の180日成績を1クエリで取得
WITH target_racers AS (
    SELECT DISTINCT e.racer_number
    FROM entries e
    JOIN races r ON e.race_id = r.id
    WHERE r.race_date = :target_date
)
SELECT
    e.racer_number,
    COUNT(*) as total_races,
    SUM(CASE WHEN res.rank = 1 THEN 1 ELSE 0 END) as win_count,
    SUM(CASE WHEN res.rank <= 2 THEN 1 ELSE 0 END) as place_2,
    SUM(CASE WHEN res.rank <= 3 THEN 1 ELSE 0 END) as place_3,
    AVG(res.rank) as avg_rank,
    AVG(rd.st_time) as avg_st
FROM entries e
JOIN races r ON e.race_id = r.id
JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
WHERE e.racer_number IN (SELECT racer_number FROM target_racers)
  AND r.race_date >= date(:target_date, '-180 days')
  AND r.race_date < :target_date
  AND res.is_invalid = 0
GROUP BY e.racer_number
```

---

#### Step 1-2: RacerAnalyzerのキャッシュ対応

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\racer_analyzer.py`

**変更内容**:

1. コンストラクタにキャッシュオプション追加（行37-45付近）
```python
class RacerAnalyzer:
    def __init__(self, db_path="data/boatrace.db", batch_loader=None):
        self.db_path = db_path
        self.batch_loader = batch_loader  # 追加
        self._use_cache = batch_loader is not None
```

2. 各メソッドにキャッシュ分岐追加（行71-131付近）
```python
def get_racer_overall_stats(self, racer_number: int, days: int = 180) -> Dict:
    # キャッシュ使用時
    if self._use_cache and self.batch_loader:
        cached = self.batch_loader.get_racer_stats(racer_number)
        if cached:
            return cached.get('overall_stats', self._default_overall_stats())

    # 従来のDB直接クエリ（互換性維持）
    # ... 既存コード ...
```

**影響範囲**:
- `get_racer_overall_stats()` (行71-131)
- `get_racer_course_stats()` (行133-191)
- `get_racer_venue_stats()` (行193-243)
- `get_racer_recent_form()` (行249-312)
- `get_racer_st_stats()` (行318-366)

**期待効果**:
- 選手分析: 42クエリ/レース → 0クエリ/レース（キャッシュヒット時）

---

#### Step 1-3: MotorAnalyzerのキャッシュ対応

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\motor_analyzer.py`

**変更内容**:

1. コンストラクタ修正（行28-32付近）
```python
class MotorAnalyzer:
    def __init__(self, db_path="data/boatrace.db", batch_loader=None):
        self.db_path = db_path
        self.batch_loader = batch_loader
```

2. メソッドにキャッシュ分岐追加（行62-119付近）
```python
def get_motor_stats(self, venue_code: str, motor_number: int, days: int = 90) -> Dict:
    if self._use_cache and self.batch_loader:
        cached = self.batch_loader.get_motor_stats(venue_code, motor_number)
        if cached:
            return cached
    # 従来のコード...
```

**影響範囲**:
- `get_motor_stats()` (行62-119)
- `get_motor_recent_form()` (行121-168)
- `get_boat_stats()` (行174-231)

**期待効果**:
- モーター分析: 18クエリ/レース → 0クエリ/レース

---

#### Step 1-4: KimariteScorerのキャッシュ対応

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\kimarite_scorer.py`

**変更内容**:

1. コンストラクタ修正（行24-26付近）
```python
def __init__(self, db_path: str = "data/boatrace.db", batch_loader=None):
    self.db_path = db_path
    self.batch_loader = batch_loader
```

2. `calculate_kimarite_affinity_score()` にキャッシュ分岐（行33-177）
```python
def calculate_kimarite_affinity_score(self, ...):
    if self.batch_loader:
        # キャッシュから選手・会場の決まり手傾向を取得
        racer_kimarite = self.batch_loader.get_racer_kimarite(racer_number, course)
        venue_kimarite = self.batch_loader.get_venue_kimarite(venue_code, course)
        # ... スコア計算 ...
```

**期待効果**:
- 決まり手スコア: 12クエリ/レース → 0クエリ/レース

---

#### Step 1-5: GradeScorerのキャッシュ対応

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\grade_scorer.py`

**変更内容**:

1. コンストラクタ修正（行40-42付近）
```python
def __init__(self, db_path: str = "data/boatrace.db", batch_loader=None):
    self.db_path = db_path
    self.batch_loader = batch_loader
```

2. `calculate_grade_affinity_score()` にキャッシュ分岐（行49-188）

**期待効果**:
- グレードスコア: 6クエリ/レース → 0クエリ/レース

---

#### Step 1-6: ExtendedScorerのキャッシュ対応

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\extended_scorer.py`

**変更内容**:

最も大きなボトルネック（780クエリ/レース）のため、段階的に対応:

1. コンストラクタ修正（行62-63付近）
2. 以下のメソッドをキャッシュ対応:
   - `calculate_session_performance()` (行210-309)
   - `calculate_previous_race_level()` (行311-394)
   - `calculate_course_entry_tendency()` (行496-634)
   - `calculate_exhibition_time_score()` (行636-720)
   - `calculate_tilt_angle_score()` (行722-819)
   - `calculate_recent_form_score()` (行821-923)
   - `calculate_venue_affinity_score()` (行925-1016)
   - `calculate_place_rate_score()` (行1018-1115)
   - `analyze_motor_characteristics()` (行1117-1189)

**期待効果**:
- 拡張スコア: 780クエリ/レース → 0クエリ/レース

---

#### Step 1-7: RacePredictorの統合

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\race_predictor.py`

**変更内容**:

1. コンストラクタでBatchDataLoaderを初期化（行35-48付近）
```python
def __init__(self, db_path="data/boatrace.db", custom_weights=None, use_cache=False):
    self.db_path = db_path
    self.batch_loader = BatchDataLoader(db_path) if use_cache else None

    # 各Analyzerにbatch_loaderを渡す
    self.racer_analyzer = RacerAnalyzer(db_path, batch_loader=self.batch_loader)
    self.motor_analyzer = MotorAnalyzer(db_path, batch_loader=self.batch_loader)
    self.kimarite_scorer = KimariteScorer(db_path, batch_loader=self.batch_loader)
    self.grade_scorer = GradeScorer(db_path, batch_loader=self.batch_loader)
    self.extended_scorer = ExtendedScorer(db_path, batch_loader=self.batch_loader)
```

2. `predict_race()` 呼び出し前にキャッシュをプリロード
```python
def predict_race_batch(self, race_ids: List[int], target_date: str) -> Dict[int, List[Dict]]:
    """複数レースの予想を一括生成"""
    # 日次データを一括ロード（1回のみ）
    if self.batch_loader:
        self.batch_loader.load_daily_data(target_date)

    # 各レースの予想を生成
    results = {}
    for race_id in race_ids:
        results[race_id] = self.predict_race(race_id)
    return results
```

---

#### Step 1-8: FastPredictionGeneratorの改修

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\scripts\fast_prediction_generator.py`

**変更内容**:

1. RacePredictorをキャッシュ有効モードで初期化（行36付近）
```python
def __init__(self):
    # キャッシュ有効化
    self.predictor = RacePredictor(use_cache=True)
    self.data_manager = DataManager()
```

2. `generate_all_predictions()` でバッチ予想メソッドを使用（行159-299付近）
```python
def generate_all_predictions(self, target_date: str, skip_existing: bool = True):
    # ... 既存の前処理 ...

    # 変更: 一括予想生成
    predictions_batch = self.predictor.predict_race_batch(
        [r['race_id'] for r in races_to_predict],
        target_date
    )

    # 結果を保存
    for race_id, predictions in predictions_batch.items():
        self.data_manager.save_race_predictions(race_id, predictions)
```

**期待効果**:
- 全体処理時間: 27分 → 2-3分

---

### テスト計画

#### 単体テスト

1. **BatchDataLoaderテスト**
   - 全選手データの一括取得が正しく動作するか
   - キャッシュヒット率の計測
   - メモリ使用量の確認

2. **各Analyzerテスト**
   - キャッシュ使用時と非使用時で同一結果が得られるか
   - エッジケース（データなし選手）の処理

#### 統合テスト

1. **パフォーマンステスト**
   - 144レースの予想生成時間を計測
   - DBクエリ回数の計測（SQLiteのログ有効化）

2. **精度テスト**
   - キャッシュ導入前後で予想結果が同一か検証
   - 過去データでのバックテスト実行

#### テストコード配置
- `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\tests\test_batch_data_loader.py`
- `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\tests\test_cache_integration.py`
- `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\tests\test_performance.py`

### 成功基準

| 指標 | 目標値 | 計測方法 |
|------|--------|----------|
| 予想生成時間（144レース） | 3分以内 | time.time()による計測 |
| DBクエリ回数（日次） | 10回以下 | SQLiteクエリログ |
| メモリ使用量 | 500MB以下 | memory_profiler |
| キャッシュヒット率 | 95%以上 | カスタムカウンタ |
| 予想精度差異 | 0%（同一結果） | 比較テスト |

---

## Phase 2: 直前予想機能の整備

### 目標
- 展示データ取得後の予想自動更新
- 事前予想と直前予想の区別・比較
- 締切20分前の自動更新スケジュール

### 現状の確認

#### 既存の直前情報取得機能

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\scraper\beforeinfo_fetcher.py`

```python
class BeforeInfoFetcher:
    """直前情報取得クラス"""

    def fetch_beforeinfo(self, race_date, venue_code, race_number):
        """展示タイム、スタート展示、水面気象情報、チルト角度等を取得"""
        # URL: https://www.boatrace.jp/owpc/pc/race/beforeinfo
```

取得可能なデータ:
- 展示タイム
- スタート展示（ST）
- 水面気象情報（気温、水温、風速、風向、波高）
- チルト角度
- 体重

#### 現状の課題

1. `race_predictions` テーブルに予想タイプの区別がない
2. 直前情報取得後の自動更新トリガーがない
3. 事前予想と直前予想の比較機能がない

### 実装計画

#### Step 2-1: race_predictionsテーブルのスキーマ拡張

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\database\models.py`

**変更内容**: マイグレーションSQL追加

```sql
-- 予想タイプカラム追加
ALTER TABLE race_predictions ADD COLUMN prediction_type TEXT DEFAULT 'advance';
-- 'advance': 事前予想（出走表確定後）
-- 'before': 直前予想（展示終了後）

-- 予想生成時刻カラム追加
ALTER TABLE race_predictions ADD COLUMN generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- インデックス追加
CREATE INDEX IF NOT EXISTS idx_predictions_type
ON race_predictions(race_id, prediction_type);
```

---

#### Step 2-2: 直前情報取得・保存の自動化

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\scraper\beforeinfo_scraper.py`

**変更内容**:

1. 取得したデータを `race_details` テーブルに保存する機能追加
```python
def fetch_and_save_beforeinfo(self, race_date, venue_code, race_number, data_manager):
    """直前情報を取得してDBに保存"""
    info = self.fetch_beforeinfo(race_date, venue_code, race_number)
    if info:
        # race_detailsに展示データを更新
        race_id = data_manager.get_race_id(venue_code, race_date, race_number)
        for racer in info['racers']:
            data_manager.update_race_details(
                race_id,
                racer['pit_number'],
                exhibition_time=racer['exhibition_time'],
                tilt_angle=racer['tilt'],
                st_time=racer['start_timing']
            )
        # race_conditionsに気象データを更新
        data_manager.save_race_conditions(
            race_id,
            wind_speed=info['weather']['wind_speed'],
            wave_height=info['weather']['wave_height'],
            wind_direction=info['weather']['wind_direction']
        )
    return info
```

---

#### Step 2-3: 予想更新トリガーの実装

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\scripts\update_predictions_before_race.py` (新規作成)

**変更内容**:

```python
class PredictionUpdater:
    """直前予想更新クラス"""

    def __init__(self):
        self.predictor = RacePredictor(use_cache=True)
        self.data_manager = DataManager()
        self.beforeinfo_fetcher = BeforeInfoFetcher()

    def update_race_prediction(self, race_id: int) -> bool:
        """
        単一レースの直前予想を更新

        1. 直前情報を取得
        2. race_detailsを更新
        3. 予想を再生成（prediction_type='before'）
        4. 保存
        """
        # 直前情報取得
        race_info = self.data_manager.get_race_info(race_id)
        beforeinfo = self.beforeinfo_fetcher.fetch_and_save_beforeinfo(
            race_info['race_date'],
            race_info['venue_code'],
            race_info['race_number'],
            self.data_manager
        )

        if not beforeinfo:
            return False

        # 予想再生成
        predictions = self.predictor.predict_race(race_id)

        # 直前予想として保存
        return self.data_manager.save_race_predictions(
            race_id,
            predictions,
            prediction_type='before'
        )

    def update_upcoming_races(self, minutes_before: int = 20) -> Dict:
        """
        締切間近のレースの直前予想を一括更新

        Args:
            minutes_before: 締切何分前のレースを対象とするか
        """
        upcoming = self.data_manager.get_races_before_deadline(minutes_before)
        results = {'success': 0, 'failed': 0}

        for race in upcoming:
            if self.update_race_prediction(race['race_id']):
                results['success'] += 1
            else:
                results['failed'] += 1

        return results
```

---

#### Step 2-4: UIからの手動更新機能

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\ui\components\unified_race_detail.py`

**変更内容**: 直前予想更新ボタン追加

```python
# レース詳細画面に追加
if st.button("直前情報を取得して予想を更新"):
    with st.spinner("直前情報を取得中..."):
        updater = PredictionUpdater()
        success = updater.update_race_prediction(race_id)
        if success:
            st.success("直前予想を更新しました")
            st.rerun()
        else:
            st.error("直前情報の取得に失敗しました")
```

---

#### Step 2-5: 自動更新スケジュールの実装

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\scripts\scheduled_prediction_update.py` (新規作成)

**変更内容**:

```python
import schedule
import time
from datetime import datetime

class ScheduledPredictionUpdater:
    """スケジュール実行による予想自動更新"""

    def __init__(self):
        self.updater = PredictionUpdater()

    def run_scheduled_update(self):
        """スケジュール実行（5分間隔）"""
        # 現在時刻から20分後に締切のレースを更新
        results = self.updater.update_upcoming_races(minutes_before=20)
        print(f"[{datetime.now()}] 直前予想更新: 成功={results['success']}, 失敗={results['failed']}")

    def start(self):
        """スケジューラ開始"""
        schedule.every(5).minutes.do(self.run_scheduled_update)

        while True:
            schedule.run_pending()
            time.sleep(60)
```

---

#### Step 2-6: 事前予想 vs 直前予想の比較機能

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\prediction_comparator.py` (新規作成)

**変更内容**:

```python
class PredictionComparator:
    """事前予想と直前予想の比較分析"""

    def compare_predictions(self, race_id: int) -> Dict:
        """
        同一レースの事前/直前予想を比較

        Returns:
            {
                'rank_changes': [...],  # 順位変動
                'score_changes': [...], # スコア変動
                'key_factors': [...]    # 変動要因
            }
        """
        advance = self.data_manager.get_predictions(race_id, 'advance')
        before = self.data_manager.get_predictions(race_id, 'before')

        changes = []
        for adv, bef in zip(advance, before):
            rank_change = adv['rank_prediction'] - bef['rank_prediction']
            score_change = bef['total_score'] - adv['total_score']
            changes.append({
                'pit_number': adv['pit_number'],
                'rank_change': rank_change,
                'score_change': score_change,
                'advance_rank': adv['rank_prediction'],
                'before_rank': bef['rank_prediction']
            })

        return {
            'changes': changes,
            'significant_changes': [c for c in changes if abs(c['rank_change']) >= 2]
        }
```

---

### バックテスト機能

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\backtest_prediction_type.py` (新規作成)

**変更内容**:

```python
class PredictionTypeBacktest:
    """事前予想 vs 直前予想の精度比較バックテスト"""

    def run_backtest(self, start_date: str, end_date: str) -> Dict:
        """
        過去データで事前/直前予想の精度を比較

        Returns:
            {
                'advance': {
                    'hit_rate_1': 0.25,  # 1着的中率
                    'hit_rate_3': 0.55,  # 3連複的中率
                    'roi': 0.82          # 回収率
                },
                'before': {
                    'hit_rate_1': 0.28,
                    'hit_rate_3': 0.58,
                    'roi': 0.87
                },
                'improvement': {
                    'hit_rate_1': +0.03,
                    'hit_rate_3': +0.03,
                    'roi': +0.05
                }
            }
        """
```

### テスト計画

1. **直前情報取得テスト**
   - 各会場のbeforinfoページが正しくパースできるか
   - 展示データがrace_detailsに正しく保存されるか

2. **予想更新テスト**
   - 直前予想が事前予想と区別して保存されるか
   - 展示データが予想スコアに正しく反映されるか

3. **スケジュール実行テスト**
   - 5分間隔の実行が安定しているか
   - 締切時刻の判定が正しいか

### 成功基準

| 指標 | 目標値 |
|------|--------|
| 直前情報取得成功率 | 95%以上 |
| 予想更新所要時間 | 10秒/レース以下 |
| 直前予想による精度向上 | 1着的中率+2%以上 |

---

## Phase 3: データ整合性改善

### 目標
- 潮位テーブルの統合（3テーブル → 1テーブル）
- 変数名・カラム名の統一
- 不要テーブルの整理

### 潮位テーブルの統合

#### 現状の潮位関連テーブル

データベースには以下3つの潮位関連テーブルが存在:

```
1. tide (models.py で定義)
   - 標準的な潮汐データ
   - venue_code, tide_date, tide_time, tide_type, tide_level

2. rdmdb_tide (外部インポート?)
   - 詳細不明

3. race_tide_data (レース単位の潮位?)
   - 詳細不明
```

#### Step 3-1: テーブル構造・データ調査

**タスク**:
1. 各テーブルのカラム構造を確認
2. データ量・更新頻度を確認
3. 使用箇所の特定

**調査SQL**:
```sql
-- 各テーブルの構造確認
PRAGMA table_info(tide);
PRAGMA table_info(rdmdb_tide);
PRAGMA table_info(race_tide_data);

-- データ量確認
SELECT COUNT(*) FROM tide;
SELECT COUNT(*) FROM rdmdb_tide;
SELECT COUNT(*) FROM race_tide_data;

-- 重複データ確認
SELECT venue_code, tide_date, COUNT(*)
FROM tide
GROUP BY venue_code, tide_date
HAVING COUNT(*) > 1;
```

---

#### Step 3-2: 統合テーブル設計

**新テーブル**: `tide_unified`

```sql
CREATE TABLE tide_unified (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_code TEXT NOT NULL,
    tide_date DATE NOT NULL,
    tide_time TEXT,              -- HH:MM形式
    tide_type TEXT,              -- '満潮', '干潮', '上げ潮', '下げ潮'
    tide_level REAL,             -- cm
    high_tide_time_1 TEXT,       -- 満潮時刻1
    high_tide_level_1 REAL,      -- 満潮潮位1
    high_tide_time_2 TEXT,       -- 満潮時刻2（あれば）
    high_tide_level_2 REAL,
    low_tide_time_1 TEXT,        -- 干潮時刻1
    low_tide_level_1 REAL,
    low_tide_time_2 TEXT,        -- 干潮時刻2（あれば）
    low_tide_level_2 REAL,
    source TEXT,                 -- データソース（'official', 'rdmdb', 'calculated'）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(venue_code, tide_date)
);

CREATE INDEX idx_tide_unified_venue_date ON tide_unified(venue_code, tide_date);
```

---

#### Step 3-3: データマイグレーション

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\scripts\migrate_tide_tables.py` (新規作成)

```python
def migrate_tide_data():
    """3つの潮位テーブルを統合"""

    # 1. tide テーブルからデータ移行（優先度: 高）
    # 2. rdmdb_tide からデータ補完
    # 3. race_tide_data から不足分を補完
    # 4. 重複データの解決（最新データを優先）
    # 5. 旧テーブルをバックアップ後に削除
```

---

#### Step 3-4: TideAdjusterの更新

**ファイル**: `c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\tide_adjuster.py`

**変更内容**: 新しい統合テーブルを参照するように修正

---

### 変数名・カラム名の統一

#### 要統一項目リスト

| カテゴリ | 現状 | 統一後 |
|---------|------|--------|
| 選手番号 | racer_number, racer_no, player_no | racer_number |
| 枠番 | pit_number, waku, lane | pit_number |
| コース | course, actual_course, entry_course | actual_course |
| 勝率 | win_rate, winning_rate, win_ratio | win_rate |
| レース日 | race_date, date, raceday | race_date |

---

### 成功基準

| 指標 | 目標値 |
|------|--------|
| 潮位テーブル | 1テーブルに統合 |
| データ整合性エラー | 0件 |
| 命名規則違反 | 0件 |

---

## Phase 4: UI整理・最適化

### 目標
- UIコンポーネントの整理（26ファイル → 15ファイル程度）
- 重複機能の統合
- 未使用機能の削除

### 現状のUIコンポーネント一覧

```
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\ui\components\

1.  betting_recommendation.py      - 買い目推奨
2.  original_tenji_collector.py    - 展示データ収集
3.  venue_strategy.py              - 会場別戦略
4.  racer_analysis.py              - 選手分析
5.  stage2_training.py             - Stage2学習
6.  model_training.py              - モデル学習
7.  venue_analysis.py              - 会場分析
8.  data_quality_monitor.py        - データ品質監視
9.  system_monitor.py              - システム監視
10. backtest.py                    - バックテスト
11. hybrid_prediction.py           - ハイブリッド予想
12. advanced_training.py           - 高度な学習
13. integrated_prediction.py       - 統合予想
14. smart_recommendations.py       - スマート推奨
15. realtime_dashboard.py          - リアルタイムダッシュボード
16. odds_fetcher_ui.py             - オッズ取得UI
17. data_export.py                 - データエクスポート
18. prediction_viewer.py           - 予想ビューア
19. auto_data_collector.py         - 自動データ収集
20. bet_history.py                 - 賭け履歴
21. bulk_data_collector.py         - 一括データ収集
22. unified_race_list.py           - 統合レース一覧
23. data_maintenance.py            - データメンテナンス
24. unified_race_detail.py         - 統合レース詳細
25. improvements_display.py        - 改善表示
26. workflow_manager.py            - ワークフロー管理
```

### 削除候補ファイル（10ファイル）

| ファイル | 理由 | 代替 |
|---------|------|------|
| hybrid_prediction.py | integrated_prediction.pyと重複 | integrated_prediction.py |
| advanced_training.py | model_training.pyと重複 | model_training.py |
| smart_recommendations.py | betting_recommendation.pyと重複 | betting_recommendation.py |
| original_tenji_collector.py | auto_data_collector.pyと重複 | auto_data_collector.py |
| venue_strategy.py | venue_analysis.pyと重複 | venue_analysis.py |
| prediction_viewer.py | unified_race_detail.pyと重複 | unified_race_detail.py |
| improvements_display.py | 一時的な機能、本番不要 | 削除 |
| bulk_data_collector.py | auto_data_collector.pyに統合可能 | auto_data_collector.py |
| stage2_training.py | model_training.pyに統合可能 | model_training.py |
| workflow_manager.py | 使用頻度低 | 削除 |

### 実装計画

#### Step 4-1: 削除候補ファイルの依存関係調査

```bash
# 各ファイルがどこからimportされているか確認
grep -r "from ui.components.hybrid_prediction" --include="*.py"
grep -r "import hybrid_prediction" --include="*.py"
```

#### Step 4-2: 段階的削除スケジュール

1. **Week 1**: improvements_display.py, workflow_manager.py（影響小）
2. **Week 2**: hybrid_prediction.py, advanced_training.py（統合後）
3. **Week 3**: smart_recommendations.py, original_tenji_collector.py
4. **Week 4**: venue_strategy.py, prediction_viewer.py
5. **Week 5**: bulk_data_collector.py, stage2_training.py（統合後）

#### Step 4-3: 統合後のファイル構成（目標）

```
ui/components/
├── unified_race_list.py         # レース一覧
├── unified_race_detail.py       # レース詳細・予想表示
├── betting_recommendation.py    # 買い目推奨
├── racer_analysis.py            # 選手分析
├── venue_analysis.py            # 会場分析
├── model_training.py            # モデル学習（統合版）
├── backtest.py                  # バックテスト
├── data_quality_monitor.py      # データ品質監視
├── system_monitor.py            # システム監視
├── realtime_dashboard.py        # リアルタイムダッシュボード
├── odds_fetcher_ui.py           # オッズ取得
├── data_export.py               # データエクスポート
├── auto_data_collector.py       # 自動データ収集（統合版）
├── bet_history.py               # 賭け履歴
└── data_maintenance.py          # データメンテナンス
```

### 成功基準

| 指標 | 目標値 |
|------|--------|
| UIファイル数 | 15ファイル以下 |
| 重複機能 | 0件 |
| 未使用コード | 0行 |

---

## 実装スケジュール

| Phase | タスク | 工数見積 | 依存関係 | 優先度 |
|-------|--------|----------|----------|--------|
| 1-1 | BatchDataLoader実装 | 8h | なし | 最優先 |
| 1-2 | RacerAnalyzerキャッシュ対応 | 4h | 1-1 | 最優先 |
| 1-3 | MotorAnalyzerキャッシュ対応 | 2h | 1-1 | 最優先 |
| 1-4 | KimariteScorerキャッシュ対応 | 2h | 1-1 | 最優先 |
| 1-5 | GradeScorerキャッシュ対応 | 2h | 1-1 | 最優先 |
| 1-6 | ExtendedScorerキャッシュ対応 | 6h | 1-1 | 最優先 |
| 1-7 | RacePredictor統合 | 4h | 1-2〜1-6 | 最優先 |
| 1-8 | FastPredictionGenerator改修 | 2h | 1-7 | 最優先 |
| 2-1 | DBスキーマ拡張 | 1h | なし | 高 |
| 2-2 | 直前情報取得・保存自動化 | 3h | 2-1 | 高 |
| 2-3 | 予想更新トリガー実装 | 4h | 2-2 | 高 |
| 2-4 | UI手動更新機能 | 2h | 2-3 | 高 |
| 2-5 | 自動更新スケジュール | 3h | 2-3 | 中 |
| 2-6 | 事前/直前予想比較機能 | 4h | 2-3 | 中 |
| 3-1 | 潮位テーブル調査 | 2h | なし | 中 |
| 3-2 | 統合テーブル設計 | 2h | 3-1 | 中 |
| 3-3 | データマイグレーション | 4h | 3-2 | 中 |
| 3-4 | TideAdjuster更新 | 2h | 3-3 | 中 |
| 4-1 | 依存関係調査 | 2h | なし | 低 |
| 4-2 | 段階的削除 | 8h | 4-1 | 低 |
| 4-3 | 統合・整理 | 6h | 4-2 | 低 |

**合計工数**: 約73時間（約9-10人日）

---

## リスクと対策

| リスク | 影響度 | 発生確率 | 対策 |
|--------|--------|----------|------|
| キャッシュによるメモリ不足 | 高 | 中 | メモリ監視、LRUキャッシュ導入 |
| キャッシュ不整合 | 高 | 低 | 日次キャッシュクリア、検証テスト |
| 直前情報取得失敗 | 中 | 中 | リトライ機構、フォールバック処理 |
| 潮位データ損失 | 高 | 低 | マイグレーション前のバックアップ必須 |
| UI削除による影響 | 中 | 中 | 段階的削除、ユーザーテスト |
| 予想精度の低下 | 高 | 低 | バックテストによる事前検証 |

---

## 付録: 詳細ファイルパス一覧

### 変更対象ファイル

```
# Phase 1: 予想生成高速化
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\database\batch_data_loader.py (新規)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\racer_analyzer.py (変更)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\motor_analyzer.py (変更)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\kimarite_scorer.py (変更)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\grade_scorer.py (変更)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\extended_scorer.py (変更)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\race_predictor.py (変更)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\scripts\fast_prediction_generator.py (変更)

# Phase 2: 直前予想機能
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\database\models.py (変更)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\database\data_manager.py (変更)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\scraper\beforeinfo_scraper.py (変更)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\scripts\update_predictions_before_race.py (新規)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\scripts\scheduled_prediction_update.py (新規)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\prediction_comparator.py (新規)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\ui\components\unified_race_detail.py (変更)

# Phase 3: データ整合性
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\scripts\migrate_tide_tables.py (新規)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\src\analysis\tide_adjuster.py (変更)

# Phase 4: UI整理
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\ui\components\*.py (複数削除・統合)

# テストファイル
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\tests\test_batch_data_loader.py (新規)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\tests\test_cache_integration.py (新規)
c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\tests\test_performance.py (新規)
```

---

以上
