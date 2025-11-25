# 競艇予想システム - 改善ロードマップ

## 📋 現状分析（2025年11月1日時点）

### システム完成度
| 項目 | 評価 | 現状 |
|------|------|------|
| データ収集 | 95/100 | V5並列化完了、2年分データ取得可能 |
| 統計分析 | 90/100 | 会場・選手の深い分析完了 |
| 法則ベース予測 | 90/100 | 98法則 + 統計検証完了 |
| 機械学習 | 85/100 | XGBoost/LightGBM実装済み |
| UI/UX | 90/100 | 12タブ、包括的機能 |
| **期待値・収益化** | **60/100** | ❌ オッズ未統合、見送り判定なし |
| 運用自動化 | 85/100 | 再解析機能あり、劣化検知は未実装 |

### 🎯 根本的な課題

**「当てる」仕組みは完成している**
**「勝ち続ける」仕組みはこれから**

現状のシステムは「的中率」を重視しているが、実際のギャンブルで重要なのは「回収率」。

```
的中率80% × 平均配当1.2倍 = 回収率96%（赤字）
的中率40% × 平均配当3.0倍 = 回収率120%（黒字）
```

オッズと予測確率を組み合わせた **期待値ベース** の判断が必須。

---

## 🚀 Phase 1: 精度向上（2-3週間）

### 目標
- 予測精度: 85% → 88-90%
- 直近のコンディション変動を反映
- 場×気象の相互作用を捉える

### Sprint 1-1: 動的特徴量の追加（最優先）

**期間**: 2-3日
**難易度**: ⭐⭐ (中)

#### 実装タスク

##### 1. 直近成績特徴量
```python
# src/ml/feature_calculator.py に追加

def calculate_recent_performance(racer_number: str, reference_date: str) -> Dict:
    """
    直近のレース成績から動的特徴量を計算

    Returns:
        {
            'recent_avg_rank_5': 直近5レースの平均順位,
            'recent_win_rate_10': 直近10レースの1着率,
            'recent_st_avg_5': 直近5レースの平均ST,
            'recent_st_stability_5': 直近5レースのST標準偏差,
            'recent_quinella_rate_10': 直近10レースの2連率,
            'days_since_last_race': 前回レースからの日数,
            'form_trend': 調子トレンド（上昇/下降/安定）
        }
    """
    # 実装内容:
    # 1. reference_date 以前の直近10レースを取得
    # 2. 平均順位、1着率、2着以内率を計算
    # 3. STの平均と標準偏差を計算
    # 4. トレンド（最近3レース vs 過去7レース）を計算
```

##### 2. モーター状態特徴量
```python
def calculate_motor_trend(motor_number: int, venue_code: str, reference_date: str) -> Dict:
    """
    モーターの状態変化を追跡

    Returns:
        {
            'motor_recent_2rate': 直近30日間の2連率,
            'motor_rate_trend': 2連率のトレンド（増加/減少）,
            'motor_days_since_exchange': 最後の部品交換からの日数,
            'motor_parts_replacement_count': 部品交換回数,
            'motor_performance_change': 2連率の変化量（今期 - 前期）
        }
    """
```

##### 3. 展示信頼度スコア
```python
def calculate_exhibition_reliability(racer_number: str) -> Dict:
    """
    展示タイムと実際のレース結果の相関を選手ごとに計算

    Returns:
        {
            'exhibition_reliability_score': 展示信頼度（0-1）,
            'exhibition_actual_correlation': 展示タイムと実タイムの相関係数,
            'exhibition_bias': 展示タイムと実タイムの平均差
        }
    """
    # 実装:
    # 1. 選手の過去レースで展示タイムと実タイムを比較
    # 2. 相関係数を計算（高いほど展示が信頼できる）
    # 3. 展示詐欺（展示は速いが本番は遅い）を検出
```

##### 4. データベーススキーマ更新
```sql
-- race_details テーブルに列追加（不要、動的計算でOK）
-- 特徴量は学習時・予測時に動的に計算する方針
```

**期待効果**:
- 精度 +2-3%
- 特に直近好調・不調の選手で改善

---

### Sprint 1-2: 場×気象の相互作用（中優先）

**期間**: 2-3日
**難易度**: ⭐⭐⭐ (中-高)

#### 実装タスク

##### 1. 会場×風向×風速の相互作用
```python
def calculate_venue_wind_interaction(venue_code: str, wind_speed: float, wind_direction: str) -> Dict:
    """
    会場ごとの風の影響を定量化

    Returns:
        {
            'venue_wind_effect_1course': 1コースへの影響（-0.2 ~ +0.2）,
            'venue_wind_effect_2course': 2コースへの影響,
            'venue_wind_effect_3course': 3コースへの影響,
            'venue_wind_sensitivity': 会場の風感度（0-1）,
            'expected_kimarite': 予想される決まり手（まくり/差し/逃げ）
        }
    """
    # 実装:
    # 1. 各会場の過去データから、風速・風向と1コース勝率の関係を回帰分析
    # 2. 風速4m以上、向かい風 → 若松では1コース勝率-10%等
    # 3. 会場ごとのパラメータをconfig/wind_effects.jsonに保存
```

##### 2. 会場×天候の相互作用
```python
def calculate_venue_weather_interaction(venue_code: str, weather: str) -> Dict:
    """
    会場ごとの天候の影響を定量化

    Returns:
        {
            'venue_weather_effect_inner': イン（1-3コース）への影響,
            'venue_weather_effect_outer': アウト（4-6コース）への影響,
            'rain_effect': 雨の影響（インが強い/弱い）
        }
    """
    # 例:
    # - 桐生: 雨 → インが強い（ダッシュが効かない）
    # - 江戸川: 雨 → 荒れる（視界不良）
```

##### 3. 設定ファイルの作成
```json
// config/venue_interactions.json
{
    "20": {  // 若松
        "wind_sensitivity": 0.8,
        "wind_effects": {
            "strong_headwind": {  // 向かい風 4m以上
                "course_1": -0.10,
                "course_2": +0.05,
                "course_3": +0.03
            }
        },
        "weather_effects": {
            "rain": {
                "inner_courses": +0.05,
                "outer_courses": -0.05
            }
        }
    }
}
```

**期待効果**:
- 特定条件下で精度 +2-5%
- 荒れるレースの予測改善

---

### Sprint 1-3: 潮汐データ取得（低優先）

**期間**: 1週間
**難易度**: ⭐⭐⭐⭐ (高)

#### 実装タスク

##### 1. 気象庁APIから潮汐データ取得
```python
# src/scraper/tide_scraper.py

class TideScraper:
    """潮汐データ取得（海上保安庁 潮汐表API）"""

    def get_tide_data(self, venue_code: str, date: str) -> Dict:
        """
        指定日の潮汐情報を取得

        Returns:
            {
                'high_tide_time_1': 第1満潮時刻,
                'high_tide_level_1': 第1満潮潮位,
                'low_tide_time_1': 第1干潮時刻,
                'low_tide_level_1': 第1干潮潮位,
                'tide_name': 潮名（大潮/中潮/小潮/長潮/若潮）,
                'moon_age': 月齢
            }
        """
```

##### 2. データベースに保存
```sql
CREATE TABLE tide_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_code TEXT NOT NULL,
    tide_date DATE NOT NULL,
    high_tide_time_1 TIME,
    high_tide_level_1 REAL,
    low_tide_time_1 TIME,
    low_tide_level_1 REAL,
    high_tide_time_2 TIME,
    high_tide_level_2 REAL,
    low_tide_time_2 TIME,
    low_tide_level_2 REAL,
    tide_name TEXT,
    moon_age REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(venue_code, tide_date)
);
```

##### 3. 海水場のみ適用
```python
SEA_WATER_VENUES = ['03', '04', '08', '11', '13', '14', '18', '19', '20', '21', '22', '23']
# 鳴門、下関、児島、びわこ（湖水）、宮島、徳山、下関、若松、芦屋、福岡、唐津、大村
```

**期待効果**:
- 海水場で +1-2%（限定的）
- 優先度低、後回しでOK

---

## 🚀 Phase 2: 収益化（2-3週間）

### 目標
- 回収率: 80% → 105-110%
- 期待値（EV）> 0 の買い目のみ推奨
- 見送り率: 約50%

### Sprint 2-1: オッズ取得（最重要）

**期間**: 3-5日
**難易度**: ⭐⭐⭐⭐⭐ (最高)

#### 課題
- 公式APIなし
- リアルタイムオッズは頻繁に変動
- スクレイピング頻度の制限

#### 実装タスク

##### 1. オッズスクレイパー
```python
# src/scraper/odds_scraper.py

class OddsScraper:
    """オッズ取得スクレイパー"""

    def get_odds_before_race(self, venue_code: str, date: str, race_number: int,
                             bet_type: str = '3tan') -> Dict:
        """
        発走5分前のオッズを取得（安定期）

        Args:
            bet_type: '3tan'（3連単）, '3fuku'（3連複）, '2tan'（2連単）等

        Returns:
            {
                'odds_data': {
                    '1-2-3': 5.2,
                    '1-2-4': 8.7,
                    ...
                },
                'timestamp': '2025-11-01 10:25:00',
                'time_until_race': 300  # 秒
            }
        """
        # 実装:
        # 1. https://www.boatrace.jp/owpc/pc/race/oddstf から取得
        # 2. 人気上位20組のみ取得（効率化）
        # 3. 5分前のオッズをキャッシュ
```

##### 2. データベース保存
```sql
CREATE TABLE odds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    bet_type TEXT NOT NULL,  -- '3tan', '3fuku', '2tan'等
    combination TEXT NOT NULL,  -- '1-2-3'
    odds REAL NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    FOREIGN KEY (race_id) REFERENCES races(id),
    UNIQUE(race_id, bet_type, combination, timestamp)
);

CREATE INDEX idx_odds_race ON odds(race_id, bet_type);
```

##### 3. キャッシュ・レート制限
```python
# 同一レースへのリクエストは5分間隔
# キャッシュで無駄なリクエスト削減
```

**期待効果**:
- 収益化の土台完成

---

### Sprint 2-2: 期待値計算・見送り判定（最重要）

**期間**: 2-3日
**難易度**: ⭐⭐ (中)

#### 実装タスク

##### 1. 期待値計算エンジン
```python
# src/analysis/expected_value_calculator.py

class ExpectedValueCalculator:
    """期待値計算エンジン"""

    def calculate_ev(self, predicted_prob: float, odds: float) -> float:
        """
        期待値を計算

        Args:
            predicted_prob: 予測確率（0-1）
            odds: オッズ（配当倍率）

        Returns:
            期待値（EV）: (予測確率 × オッズ) - 1

        例:
            予測30%、オッズ4.0倍
            EV = (0.30 × 4.0) - 1 = +0.20 (+20%)
        """
        return (predicted_prob * odds) - 1

    def get_positive_ev_bets(self, predictions: List[Dict], odds_data: Dict,
                            min_ev: float = 0.10) -> List[Dict]:
        """
        EV > min_ev の買い目のみ抽出

        Args:
            predictions: [{'combination': '1-2-3', 'prob': 0.25}, ...]
            odds_data: {'1-2-3': 5.2, '1-2-4': 8.7, ...}
            min_ev: 最低期待値（デフォルト10%）

        Returns:
            [
                {
                    'combination': '1-2-3',
                    'prob': 0.25,
                    'odds': 5.2,
                    'ev': 0.30,  # +30%
                    'kelly_fraction': 0.15  # ケリー基準
                },
                ...
            ]
        """
```

##### 2. 見送り判定
```python
def should_skip_race(positive_ev_bets: List[Dict]) -> bool:
    """
    レースを見送るべきか判定

    Returns:
        True: 見送り（EV > 0 の買い目がない）
        False: 購入推奨
    """
    return len(positive_ev_bets) == 0
```

##### 3. UI表示
```python
# ui/app.py のリアルタイム予想タブに追加

st.markdown("### 💰 期待値分析")

if positive_ev_bets:
    st.success(f"✅ 購入推奨: {len(positive_ev_bets)}通り")

    for bet in positive_ev_bets:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.write(f"**{bet['combination']}**")
        with col2:
            st.metric("予測確率", f"{bet['prob']*100:.1f}%")
        with col3:
            st.metric("オッズ", f"{bet['odds']:.1f}倍")
        with col4:
            st.metric("期待値", f"+{bet['ev']*100:.1f}%",
                     delta="推奨" if bet['ev'] > 0.2 else "")
else:
    st.warning("⚠️ 見送り推奨: 期待値プラスの買い目なし")
```

**期待効果**:
- 無駄打ち削減 → 回収率改善
- 数学的に正しい購入判断

---

### Sprint 2-3: 確率キャリブレーション（中優先）

**期間**: 2-3日
**難易度**: ⭐⭐⭐ (中-高)

#### 課題
ML予測の確率は「相対的」であり、「絶対的」な確率ではない。

例:
- モデルが「80%」と予測 → 実際は60%しか当たらない
- キャリブレーション（較正）が必要

#### 実装タスク

##### 1. キャリブレーション
```python
from sklearn.calibration import CalibratedClassifierCV

# モデル学習後にキャリブレーション
calibrated_model = CalibratedClassifierCV(
    xgb_model,
    method='sigmoid',  # またはisotonic
    cv=5
)
calibrated_model.fit(X_train, y_train)

# キャリブレーション済み確率
calibrated_probs = calibrated_model.predict_proba(X_test)
```

##### 2. 検証
```python
# 予測確率と実際の的中率の比較
# プロット: 予測30% → 実際30%なら理想的
```

**期待効果**:
- 期待値計算の精度向上
- 過大評価/過小評価の補正

---

### Sprint 2-4: 資金管理（ケリー基準）（低優先）

**期間**: 2日
**難易度**: ⭐⭐ (中)

#### 実装タスク

##### 1. ケリー基準の計算
```python
def calculate_kelly_fraction(prob: float, odds: float, conservative: float = 0.25) -> float:
    """
    ケリー基準でベット比率を計算

    Args:
        prob: 予測確率（キャリブレーション済み）
        odds: オッズ
        conservative: 保守係数（1/4ケリー推奨）

    Returns:
        ベット比率（0-1）

    例:
        予測35%、オッズ3.5倍
        kelly = (3.5 × 0.35 - (1 - 0.35)) / 3.5 = 0.16
        保守的kelly = 0.16 / 4 = 0.04 (資金の4%)
    """
    kelly = (odds * prob - (1 - prob)) / odds
    return max(0, kelly * conservative)
```

##### 2. 推奨ベット額
```python
def recommend_bet_amount(bankroll: int, kelly_fraction: float, max_bet: int = 10000) -> int:
    """
    推奨ベット額を計算

    Args:
        bankroll: 総資金
        kelly_fraction: ケリー比率
        max_bet: 最大ベット額（上限）

    Returns:
        推奨ベット額（円）
    """
    bet = int(bankroll * kelly_fraction)
    return min(bet, max_bet)
```

##### 3. UI表示
```python
st.markdown("### 💵 推奨ベット額")
st.write(f"総資金: {bankroll:,}円")

for bet in positive_ev_bets:
    kelly = calculate_kelly_fraction(bet['prob'], bet['odds'])
    amount = recommend_bet_amount(bankroll, kelly)

    st.write(f"**{bet['combination']}**: {amount:,}円 (資金の{kelly*100:.1f}%)")
```

**期待効果**:
- 破産リスク軽減
- 長期的な収益最大化

---

## 🚀 Phase 3: 運用自動化（1-2週間）

### 目標
- モデル劣化の自動検知
- 法則の鮮度管理
- 週次自動再学習

### Sprint 3-1: モデル劣化検知

**期間**: 1週間
**難易度**: ⭐⭐⭐ (中-高)

#### 実装タスク

##### 1. 性能モニタリング
```python
# src/monitoring/model_monitor.py

class ModelMonitor:
    """モデル性能モニタリング"""

    def check_model_performance(self, recent_predictions: List[Dict]) -> Dict:
        """
        直近の予測精度を評価

        Args:
            recent_predictions: [
                {'race_id': 1, 'predicted': [0.5, 0.2, ...], 'actual': [1, 0, ...]},
                ...
            ]

        Returns:
            {
                'recent_accuracy': 0.82,  # 直近100レース
                'baseline_accuracy': 0.88,  # ベースライン
                'drift_detected': True,  # 精度低下検知
                'should_retrain': True  # 再学習推奨
            }
        """
```

##### 2. 自動再学習トリガー
```python
if monitor.check_model_performance()['should_retrain']:
    # 自動再学習
    trainer = ModelTrainer()
    trainer.train_model()

    # モデル更新
    model_path = 'models/xgboost_latest.pkl'
    trainer.save_model(model_path)

    # 通知
    send_notification("モデルを再学習しました")
```

**期待効果**:
- 継続的な高精度維持

---

### Sprint 3-2: 法則劣化検知

**期間**: 3日
**難易度**: ⭐⭐ (中)

#### 実装タスク

##### 1. 法則の定期評価
```python
# src/analysis/rule_degradation_checker.py

class RuleDegradationChecker:
    """法則劣化検知"""

    def check_rule_freshness(self, rule_id: int, days: int = 90) -> Dict:
        """
        法則の直近性能を評価

        Returns:
            {
                'rule_id': 1,
                'recent_hit_rate': 0.52,  # 直近90日
                'historical_hit_rate': 0.65,  # 過去全体
                'degradation': -0.13,  # 劣化度
                'should_deactivate': True  # 無効化推奨
            }
        """
```

##### 2. 自動無効化
```python
checker = RuleDegradationChecker()

for rule in active_rules:
    freshness = checker.check_rule_freshness(rule.id)

    if freshness['should_deactivate']:
        # 法則を自動無効化
        db.update_rule(rule.id, is_active=0)
        log(f"法則#{rule.id}を無効化: 劣化検知")
```

**期待効果**:
- 古い法則の自動排除
- システムの鮮度維持

---

## 📋 実装チェックリスト

### Phase 1: 精度向上（2-3週間）

- [ ] **Sprint 1-1: 動的特徴量** (2-3日)
  - [ ] 直近5レース成績特徴量
  - [ ] モーター状態特徴量
  - [ ] 展示信頼度スコア
  - [ ] FeatureCalculatorに統合
  - [ ] MLモデル再学習
  - [ ] 精度検証（目標: +2-3%）

- [ ] **Sprint 1-2: 場×気象相互作用** (2-3日)
  - [ ] 会場×風の相互作用分析
  - [ ] 会場×天候の相互作用分析
  - [ ] config/venue_interactions.json作成
  - [ ] MLモデル再学習
  - [ ] 精度検証（目標: +2-5%）

- [ ] **Sprint 1-3: 潮汐データ** (1週間) ※低優先
  - [ ] TideScraperクラス実装
  - [ ] tide_dataテーブル作成
  - [ ] 海水場のみ適用
  - [ ] 効果検証

### Phase 2: 収益化（2-3週間）

- [ ] **Sprint 2-1: オッズ取得** (3-5日)
  - [ ] OddsScraperクラス実装
  - [ ] oddsテーブル作成
  - [ ] 発走5分前オッズ取得
  - [ ] レート制限・キャッシュ実装
  - [ ] 人気上位20組のみ取得

- [ ] **Sprint 2-2: 期待値計算** (2-3日)
  - [ ] ExpectedValueCalculatorクラス実装
  - [ ] 期待値計算ロジック
  - [ ] 見送り判定ロジック
  - [ ] UI表示（推奨買い目）
  - [ ] バックテストで検証

- [ ] **Sprint 2-3: 確率キャリブレーション** (2-3日)
  - [ ] CalibratedClassifierCV実装
  - [ ] キャリブレーション検証
  - [ ] モデル更新

- [ ] **Sprint 2-4: ケリー基準** (2日) ※低優先
  - [ ] ケリー基準計算
  - [ ] 推奨ベット額計算
  - [ ] UI表示

### Phase 3: 運用自動化（1-2週間）

- [ ] **Sprint 3-1: モデル劣化検知** (1週間)
  - [ ] ModelMonitorクラス実装
  - [ ] 性能モニタリング
  - [ ] 自動再学習トリガー
  - [ ] 通知機能

- [ ] **Sprint 3-2: 法則劣化検知** (3日)
  - [ ] RuleDegradationCheckerクラス実装
  - [ ] 法則鮮度評価
  - [ ] 自動無効化

---

## 📊 期待される成果

### フェーズ完了後の目標値

| 指標 | 現在 | Phase 1完了 | Phase 2完了 | Phase 3完了 |
|------|------|------------|------------|------------|
| 予測精度 | 85% | 88-90% | 88-90% | 88-90% |
| 回収率 | 80% | 82% | **105-110%** | **105-110%** |
| 見送り率 | 0% | 0% | **50%** | **50%** |
| 月次再学習 | 手動 | 手動 | 手動 | **自動** |

### 最終的なアウトプット例

```
━━━━━━━━━━━━━━━━━━━━━━━
🏁 第5レース - 若松競艇場
━━━━━━━━━━━━━━━━━━━━━━━

📊 推奨買い目（期待値プラス）

1-2-3
  予測確率: 35.2%
  オッズ: 3.5倍
  期待値: +23.2%
  推奨額: 1,200円 ✅

1-3-2
  予測確率: 18.4%
  オッズ: 8.2倍
  期待値: +50.9%
  推奨額: 700円 ✅

━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 見送り推奨: 56.4%
━━━━━━━━━━━━━━━━━━━━━━━

根拠:
- 1コース 松本選手: 直近5レース勝率60%（好調）
- モーター#45: 2連率上昇トレンド（+8%）
- 風速3m（向かい風）: 1コース有利
```

---

## 🎯 まとめ

### 優先度付き実装順序

1. **最優先（今すぐ）**: Sprint 1-1 動的特徴量
2. **高優先（1週間以内）**: Sprint 1-2 場×気象相互作用
3. **最重要（2週間以内）**: Sprint 2-1, 2-2 オッズ取得・期待値計算
4. **中優先（1ヶ月以内）**: Sprint 2-3 確率キャリブレーション
5. **低優先（後回しOK）**: Sprint 1-3 潮汐、Sprint 2-4 ケリー基準
6. **運用フェーズ（2ヶ月後）**: Sprint 3-1, 3-2 自動化

### 成功の鍵

✅ **Phase 1で精度を底上げ**してから Phase 2（収益化）へ
✅ オッズ取得は難易度高いが **収益化の核心**
✅ 期待値 > 0 の買い目のみ推奨 = **数学的に正しい戦略**
✅ 見送り判定で **無駄打ちを削減**
✅ 長期運用で **モデル劣化を監視**

### 最終目標

**「当てる」から「儲かる」AIへ進化**

---

**作成日**: 2025年11月1日
**次回更新予定**: Phase 1完了後
**作成者**: Claude (Anthropic)
