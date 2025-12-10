# ボートレース予想システム 機能設計書

## 概要
kyoteibiyori と BOATERS の優れた機能を統合した、高度なボートレース予想システム

## 参考サイト分析結果

### kyoteibiyori の特徴
- **超展開データ**: 1マークでの攻め方を数値化した戦術分析
- **条件検索**: 逃げ率・逃し率・差し捲り率による絞り込み
- **アラート機能**: 展示タイム解析（まくり/前づけ/チルト）
- **場状況分析**: 固い場/荒れる場/イン逃率/万舟率ランキング

### BOATERS の特徴
- **複数AIモデル**: 4つの異なる予想タイプ
  - Hit（的中重視）
  - HighOdds（高配当狙い）
  - Profitable（収益性重視）
  - NewBalance（バランス型）
- **透明性**: 詳細な実績データを時系列公開
- **パフォーマンス指標**: 月間・週間・3ヶ月・半年・年間の成績追跡

---

## 実装機能一覧

### Phase 1: 基盤機能（優先度: 高）

#### 1.1 データ収集基盤 ✅
- [x] 出走表データの取得
- [x] レース結果データの取得
- [x] selectolax による高速化（54%削減）
- [x] 6並列処理による高速化（88%削減）
- [ ] 展示タイムデータの取得（前づけ/チルト/ST分析用）

#### 1.2 基礎統計計算
- [ ] コース別1着率・2着率・3着率
- [ ] 選手別勝率・連対率
- [ ] モーター別2連率・3連率
- [ ] 場別イン逃げ率

---

### Phase 2: 条件検索機能（優先度: 高）

#### 2.1 ガチガチレース検索（kyoteibiyori風）
**目的**: 堅いレースを見つけて的中率を上げる

**検索条件**:
- 1号艇の逃げ率（例: 70%以上）
- 2号艇の逃し率（例: 60%以上）
- 3-6号艇の平均勝率が低い

**実装**:
```python
def search_solid_races(data, escape_rate_min=70, miss_rate_min=60):
    """
    ガチガチレース検索

    Args:
        escape_rate_min: 1号艇の最低逃げ率 (%)
        miss_rate_min: 2号艇の最低逃し率 (%)

    Returns:
        条件に合致するレース一覧
    """
    pass
```

**出力例**:
```
[ガチガチレース候補]
桐生 10R: 1号艇逃げ率 78% / 2号艇逃し率 65%
予想: 1-2-3 (信頼度: 高)
```

#### 2.2 穴狙いレース検索
**目的**: 高配当レースを見つける

**検索条件**:
- 1号艇の逃げ率が低い（例: 50%未満）
- 2-6号艇の差し・捲り率が高い
- モーターの2連率が高い艇がいる

**実装**:
```python
def search_upset_races(data, escape_rate_max=50, attack_rate_min=30):
    """
    穴狙いレース検索

    Args:
        escape_rate_max: 1号艇の最大逃げ率 (%)
        attack_rate_min: 2-6号艇の最低差し捲り率 (%)

    Returns:
        穴候補レース一覧
    """
    pass
```

---

### Phase 3: アラート機能（優先度: 中）

#### 3.1 展示タイム解析アラート

**まくりアラート**:
- 展示タイムで外枠の艇が早い
- かつ、スタート予想が良い
- → まくりが決まる可能性大

**前づけアラート**:
- 進入コースが枠番と大きく違う
- 内側に強引に入ってくる艇がいる
- → 展開が荒れる可能性

**チルト跳アラート**:
- チルト角度が極端（-0.5以下 or +3.0以上）
- モーター2連率が高い
- → 有利な選手の可能性

**実装**:
```python
class RaceAlert:
    def check_makuri_alert(self, exhibition_data):
        """まくりアラート判定"""
        pass

    def check_maezuke_alert(self, course_data):
        """前づけアラート判定"""
        pass

    def check_tilt_alert(self, tilt_data, motor_data):
        """チルト跳アラート判定"""
        pass
```

---

### Phase 4: 複数AI予想モデル（優先度: 高）

#### 4.1 Hit型（的中重視）
**特徴**:
- 的中率最大化
- 低オッズでも安定した予想
- 初心者向け

**ロジック**:
- 1号艇逃げ率が高い場合は1-2-3/1-2-4を推奨
- コース別1着率を重視
- 選手の平均STを考慮

**目標**:
- 的中率: 40%以上
- 回収率: 0.8-0.9倍

#### 4.2 HighOdds型（高配当狙い）
**特徴**:
- 高配当レースを狙う
- 的中率は低いが当たれば大きい
- 上級者向け

**ロジック**:
- 1号艇逃げ率が低いレースを選択
- 差し・捲りが決まりやすい選手を重視
- モーター性能の良い外枠を評価

**目標**:
- 的中率: 15-20%
- 回収率: 1.2-1.5倍

#### 4.3 Profitable型（収益性重視）
**特徴**:
- 回収率最大化
- オッズと確率のバランスを取る
- 中級者向け

**ロジック**:
- 期待値計算: 予想的中率 × オッズ
- 期待値が1.0を超える買い目のみ推奨
- 過去の配当分布を考慮

**目標**:
- 的中率: 25-30%
- 回収率: 1.0-1.2倍

#### 4.4 NewBalance型（バランス型）
**特徴**:
- 的中率と回収率のバランス
- 汎用性が高い
- 万人向け

**ロジック**:
- Hit型とHighOdds型の中間
- レース状況に応じて戦略を切り替え
- ガチガチレースでは堅く、荒れそうなレースでは攻める

**目標**:
- 的中率: 30-35%
- 回収率: 0.9-1.1倍

**実装**:
```python
class PredictionModels:
    def hit_model(self, race_data):
        """的中重視型予想"""
        pass

    def high_odds_model(self, race_data):
        """高配当狙い型予想"""
        pass

    def profitable_model(self, race_data, odds_data):
        """収益性重視型予想"""
        pass

    def new_balance_model(self, race_data, odds_data):
        """バランス型予想"""
        pass
```

---

### Phase 5: 場状況分析（優先度: 中）

#### 5.1 固い場ランキング
**計算方法**:
- 1号艇1着率の高い場所順
- 平均配当金額が低い場所順

**用途**:
- ガチガチレース検索での場所絞り込み
- Hit型予想の精度向上

#### 5.2 荒れている場ランキング
**計算方法**:
- 1号艇1着率の低い場所順
- 万舟券出現率の高い場所順

**用途**:
- 穴狙いレース検索での場所絞り込み
- HighOdds型予想の精度向上

#### 5.3 イン逃率ランキング
**計算方法**:
- 1-3号艇の1着率合計が高い場所順

#### 5.4 万舟率ランキング
**計算方法**:
- 3連単配当10,000円以上の出現率順

**実装**:
```python
class VenueAnalysis:
    def rank_solid_venues(self, race_results):
        """固い場ランキング"""
        pass

    def rank_upset_venues(self, race_results):
        """荒れる場ランキング"""
        pass

    def rank_inside_escape_rate(self, race_results):
        """イン逃率ランキング"""
        pass

    def rank_high_payout_rate(self, race_results):
        """万舟率ランキング"""
        pass
```

---

### Phase 6: 実績追跡システム（優先度: 中）

#### 6.1 予想パフォーマンス記録
**記録データ**:
- 日付
- 予想タイプ（Hit/HighOdds/Profitable/NewBalance）
- レース情報（場所、レース番号）
- 予想した買い目
- 的中/不的中
- 配当金額
- 回収率

**データベース設計**:
```sql
CREATE TABLE prediction_results (
    id INTEGER PRIMARY KEY,
    prediction_date DATE,
    prediction_type TEXT, -- 'hit', 'high_odds', 'profitable', 'new_balance'
    venue_code TEXT,
    race_number INTEGER,
    predicted_combination TEXT, -- '1-2-3'
    is_hit BOOLEAN,
    payout_amount REAL,
    bet_amount REAL,
    return_rate REAL, -- 回収率
    created_at TIMESTAMP
);
```

#### 6.2 統計レポート
**日次レポート**:
- 今日の予想数
- 的中数
- 的中率
- 回収率

**週次レポート**:
- 週間予想数
- 週間的中率
- 週間回収率
- 最高配当

**月次レポート**:
- 月間予想数
- 月間的中率
- 月間回収率
- 予想タイプ別パフォーマンス比較

**実装**:
```python
class PerformanceTracker:
    def record_prediction(self, prediction_data, result_data):
        """予想結果を記録"""
        pass

    def generate_daily_report(self, date):
        """日次レポート生成"""
        pass

    def generate_weekly_report(self, week_start):
        """週次レポート生成"""
        pass

    def generate_monthly_report(self, year, month):
        """月次レポート生成"""
        pass

    def compare_model_performance(self, start_date, end_date):
        """モデル別パフォーマンス比較"""
        pass
```

---

## データベース拡張

### 新規テーブル

#### exhibition_data（展示データ）
```sql
CREATE TABLE exhibition_data (
    id INTEGER PRIMARY KEY,
    race_id INTEGER,
    pit_number INTEGER,
    exhibition_time REAL, -- 展示タイム
    tilt_angle REAL, -- チルト角度
    FOREIGN KEY (race_id) REFERENCES races(id)
);
```

#### course_entry（進入コース）
```sql
CREATE TABLE course_entry (
    id INTEGER PRIMARY KEY,
    race_id INTEGER,
    pit_number INTEGER,
    expected_course INTEGER, -- 予想進入コース
    actual_course INTEGER, -- 実際の進入コース
    FOREIGN KEY (race_id) REFERENCES races(id)
);
```

#### venue_statistics（場所別統計）
```sql
CREATE TABLE venue_statistics (
    id INTEGER PRIMARY KEY,
    venue_code TEXT,
    stat_date DATE,
    course_1_win_rate REAL, -- 1号艇1着率
    inside_escape_rate REAL, -- イン逃率（1-3号艇）
    high_payout_rate REAL, -- 万舟率
    avg_payout REAL, -- 平均配当
    total_races INTEGER
);
```

---

## UI設計（Streamlit）

### ページ構成

#### 1. ホーム画面
- 今日のレース一覧
- 注目レース（アラート発動）
- 本日の予想（4タイプ別）

#### 2. レース検索
- ガチガチレース検索
- 穴狙いレース検索
- 条件カスタム検索

#### 3. 場所別分析
- 固い場ランキング
- 荒れる場ランキング
- イン逃率ランキング
- 万舟率ランキング

#### 4. AI予想
- Hit型予想
- HighOdds型予想
- Profitable型予想
- NewBalance型予想
- 予想理由の表示

#### 5. 実績追跡
- 日次/週次/月次レポート
- モデル別パフォーマンス比較
- グラフ表示（的中率・回収率推移）

---

## 実装スケジュール

### Week 1: Phase 1（基盤機能）
- [x] データ収集基盤
- [ ] 展示タイムデータ取得
- [ ] 基礎統計計算

### Week 2: Phase 2 & 4（検索 + AI予想）
- [ ] ガチガチレース検索
- [ ] 穴狙いレース検索
- [ ] Hit型予想モデル
- [ ] HighOdds型予想モデル

### Week 3: Phase 4 & 5（AI予想 + 場分析）
- [ ] Profitable型予想モデル
- [ ] NewBalance型予想モデル
- [ ] 場状況分析（ランキング）

### Week 4: Phase 3 & 6（アラート + 実績追跡）
- [ ] 展示タイム解析アラート
- [ ] 実績追跡システム
- [ ] UI実装（Streamlit）

---

## 成功指標（KPI）

### Phase 1完了時
- データ収集速度: 4時間以内で1ヶ月分
- データ品質: 欠損率5%以下

### Phase 2-4完了時
- Hit型的中率: 40%以上
- HighOdds型回収率: 1.2倍以上
- レース検索精度: 検索結果の70%以上が条件合致

### Phase 6完了時
- 実績追跡の自動化
- 月次レポート自動生成
- 全予想タイプの透明性確保

---

## 今後の拡張案

### Phase 7: 上級機能
- オッズ変動追跡
- リアルタイム予想更新
- ユーザー別カスタム予想設定

### Phase 8: 機械学習強化
- LightGBM/XGBoostによる予測精度向上
- 過去10年分のデータで学習
- 特徴量エンジニアリングの高度化

### Phase 9: API提供
- REST API開発
- 外部アプリケーションとの連携
- Webhook通知機能
