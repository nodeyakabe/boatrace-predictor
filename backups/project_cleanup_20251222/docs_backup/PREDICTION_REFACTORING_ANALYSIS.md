# 予測システム リファクタリング調査報告書

**作成日**: 2025-12-15
**対象**: 予測エンジン再設計に向けた現状分析

---

## 1. 現状ロジックの詳細分析

### 1.1 スコアリング構造の全体像

現在のスコアリングは `RacePredictor.predict_race()` を中心に、複数のステージで構成されています。

```
[Phase 1: 基本スコア計算]
  course_score       → コース×ランク×会場特性
  racer_score        → 選手実績（勝率、連対率）
  motor_score        → モーター成績
  kimarite_score     → 決まり手適性
  grade_score        → グレード適性
  extended_score     → 拡張スコア（級別、F/L、ST等）
  compound_buff      → 複合条件バフ（会場×環境×特性）
      ↓
  [raw_total → 0-100正規化]
      ↓
[Phase 2: 後処理補正]
  _apply_exhibition_adjustment  → 展示データ補正
  _apply_rule_based_adjustment  → 法則ベース補正
  _apply_weather_adjustment     → 天候補正（風速、波高、風向）
  _apply_tide_adjustment        → 潮位補正
      ↓
[Phase 3: 直前情報統合]
  _apply_beforeinfo_integration → PRE_SCORE * 0.6 + BEFORE_SCORE * 0.4
  _apply_pattern_bonus          → BEFOREパターンボーナス
      ↓
[Phase 4: 最終調整]
  _apply_entry_prediction       → 進入予測適用
  _apply_probability_calibration → 確率キャリブレーション
  _add_top3_scores              → 三連対スコア追加
      ↓
  [FINAL_SCORE]
```

### 1.2 各スコア要素の詳細

#### 1.2.1 基本スコア（6要素）

| 要素 | 重み | 算出方法 | ファイル |
|-----|------|---------|---------|
| course_score | 動的（20-45） | コース基礎点70% + 勝率20% + 会場特性10% | race_predictor.py |
| racer_score | 動的（25-40） | 全国・コース別・当地の勝率複合 | racer_analyzer.py |
| motor_score | 動的（12-28） | モーター2連率、勝率、舟成績 | motor_analyzer.py |
| kimarite_score | 動的（2-8） | 決まり手実績×環境相性 | kimarite_scorer.py |
| grade_score | 動的（2-8） | SGG/G1実績、優出率 | grade_scorer.py |
| extended_score | 20固定 | 級別、F/L、ST、展示等（詳細後述） | extended_scorer.py |

#### 1.2.2 拡張スコア（extended_score）の内訳

```python
# config/settings.py より
EXTENDED_SCORE_WEIGHTS = {
    'class': 10,           # 級別（A1=10, A2=7, B1=4, B2=1）
    'fl_penalty': 10,      # F/Lペナルティ（最大-10）
    'session': 5,          # 節間成績
    'prev_race': 5,        # 前走レベル
    'course_entry': 5,     # 進入傾向
    'matchup': 5,          # 選手間相性
    'motor': 5,            # モーター特性
    'start_timing': 10,    # 平均ST
    'exhibition': 10,      # 展示タイム
    'tilt': 2,             # チルト角度
    'recent_form': 8,      # 直近成績
    'venue_affinity': 8,   # 会場別勝率
    'place_rate': 5,       # 連対率
}
# 最大: 78点、最小: -10点 → 20点満点に正規化
```

### 1.3 「事前予想」と「直前情報」の現状の分離

**現状の定義:**

| 情報タイプ | 含まれるデータ | 取得タイミング |
|-----------|---------------|---------------|
| 事前情報（PRE_SCORE） | 選手成績、モーター成績、級別、過去実績 | レース前日～数時間前 |
| 直前情報（BEFORE_SCORE） | 展示タイム、ST、進入隊形、前走、チルト、気象 | レース約30分前 |

**統合方法:**
```python
# beforeinfo_scorer.py より
FINAL_SCORE = PRE_SCORE * 0.6 + BEFORE_SCORE * 0.4

# BEFORE_SCORE の内訳（115点満点）
- 展示タイム: 25点
- ST: 25点
- 進入隊形: 20点
- 前走成績: 15点
- チルト・風: 10点
- 部品交換・重量: 5点
- 気象条件: 5点
- モーター成績: 5点
- 選手×コース別得意: 5点
```

**問題点:**
1. `extended_scorer.py` にも `exhibition` と `start_timing` が含まれ、**重複加点**の可能性
2. 事前/直前の境界が曖昧（平均STは事前情報だが、展示STは直前情報）
3. 統合比率（0.6:0.4）が固定で、レース状況に応じた最適化ができていない

### 1.4 プリセット・補正の現状

#### 1.4.1 会場特性プリセット

**ファイル:** `config/venue_characteristics.py`

```python
VENUE_CHARACTERISTICS = {
    '01': {'name': '桐生', 'pit1_rate': 47.5, 'characteristic': '標準的', 'pit1_adjustment': 1.0},
    '24': {'name': '大村', 'pit1_rate': 65.8, 'characteristic': 'インが非常に強い', 'pit1_adjustment': 1.10},
    # ...全24会場
}

VENUE_COURSE_WIN_RATES = {
    # 会場別コース勝率（6コース分）
    '01': [47.5, 15.0, 12.5, 12.0, 8.0, 5.0],
    # ...
}
```

**適用方法:**
- `get_venue_adjustment()` → 1コースに乗算
- `get_venue_course_adjustment()` → 全コースに乗算

#### 1.4.2 天候補正プリセット

**ファイル:** `config/weather_rules.json`

```json
{
  "wind_speed_categories": {
    "low": {"min": 0, "max": 2, "label": "弱風"},
    "mid": {"min": 3, "max": 5, "label": "中風"},
    "high": {"min": 6, "max": 99, "label": "強風"}
  },
  "venue_wind_rules": {
    "08": {"name": "常滑", "diff": 0.490, "rule": "強風時は1コースが極端に不利"},
    // ...会場別ルール
  },
  "scoring_adjustments": {
    "strong_wind_course1_penalty": {
      "default": -0.10,
      "venue_specific": {"08": -0.30, "02": -0.20, ...}
    }
  }
}
```

**適用方法:**
- `WeatherAdjuster.calculate_adjustment()` → パーセント補正（最大±5点）

#### 1.4.3 潮位補正プリセット

**ファイル:** `src/analysis/tide_adjuster.py`（コード内定義）

```python
VENUE_TIDE_COEFFICIENTS = {
    '17': {  # 徳山
        'rising_course1_bonus': 0.07,
        'falling_course1_penalty': -0.07,
        'rising_outer_penalty': -0.02,
        'falling_outer_bonus': 0.02,
    },
    # ...海水会場のみ
}
```

**適用方法:**
- `TideAdjuster.calculate_adjustment()` → パーセント補正（最大±5点）

#### 1.4.4 複合条件バフ

**ファイル:** `src/analysis/compound_buff_system.py`

```python
# プリセットルール例
CompoundBuffRule(
    rule_id="tokuyama_a1_full_tide",
    name="徳山満潮A1イン",
    conditions=[
        BuffCondition(ConditionType.VENUE, "18"),
        BuffCondition(ConditionType.TIDE, "満潮"),
        BuffCondition(ConditionType.COURSE, 1),
        BuffCondition(ConditionType.RACER_RANK, "A1"),
    ],
    buff_value=10.0,
    confidence=0.90,
    hit_rate=0.78
)
```

**適用方法:**
- 条件マッチング → 直接スコア加算（最大15点）

### 1.5 スコア統合方式の分析

**現状の統合方式:**

```python
# 乗算方式
score = score * venue_adjustment  # 会場補正
score = score * course_adjustment  # コース補正

# 加算方式
total_score = course + racer + motor + kimarite + grade + extended + compound_buff

# パーセント×スコア方式（天候・潮位）
score_adjustment = original_score * adjustment_percent
adjusted_score = original_score + score_adjustment

# 重み付き加算（直前情報統合）
final = pre_score * 0.6 + before_score * 0.4
```

**問題点:**
1. 乗算・加算・パーセントが混在し、**影響度の可視化が困難**
2. 補正値の**上限・下限**がモジュールごとに異なる
3. 複合条件バフは**信頼度で減衰**させているが、他モジュールは固定値

---

## 2. 構想との整合性分析

### 2.1 ユーザー構想の要約

```
事前予想（ベーススコア）
    ↓
+ 直前情報（展示タイム、ST等）
+ 各法則性（コース別傾向、選手ランク等）
+ プリセット（会場特性、天候パターン等）
+ 会場特性による補正
    ↓
= 最終予測スコア
```

**重要ポイント:**
1. **事前予想をベース**として、各要素を「加算・減算」で調整
2. **プリセット**や**補正値**を個別に管理・検証可能にする
3. **値の最適化**を体系的に実施できる仕組み

### 2.2 現状システムとの一致点

| 構想の要素 | 現状の対応 | 一致度 |
|-----------|-----------|--------|
| 事前予想がベース | PRE_SCORE として存在 | 80% |
| 直前情報の補正 | BEFORE_SCORE として存在 | 80% |
| 会場特性補正 | venue_characteristics.py | 70% |
| 天候パターン | weather_rules.json | 70% |
| コース別傾向 | venue_course_win_rates.py | 60% |
| 選手ランク補正 | COURSE_RANK_WIN_RATES | 60% |

### 2.3 現状システムとの相違点

| 構想の要素 | 現状の課題 | 相違度 |
|-----------|-----------|--------|
| 加算・減算方式 | 乗算・パーセントが混在 | 高 |
| 個別検証可能 | 補正がコード内に分散 | 高 |
| 値の最適化 | 手動調整のみ、体系化なし | 高 |
| プリセット管理 | 設定形式がバラバラ | 中 |
| 事前/直前の明確な分離 | 重複・境界曖昧 | 中 |

---

## 3. ギャップ分析表

| 項目 | 現状 | 構想 | ギャップ | 改修難易度 | 優先度 |
|------|------|------|---------|-----------|--------|
| **事前/直前分離** | 部分的に分離（重複あり） | 明確に分離 | 中 | 中 | 高 |
| **スコア統合方式** | 乗算・加算・パーセント混在 | 加算・減算で統一 | 高 | 高 | 高 |
| **プリセット管理** | Python/JSON混在、形式バラバラ | 体系的管理（YAML等） | 中 | 低 | 中 |
| **値の最適化** | なし（手動調整） | 自動最適化スクリプト | 高 | 中 | 中 |
| **補正値の可視化** | デバッグ出力のみ | 詳細ログ＋UI表示 | 中 | 低 | 低 |
| **A/Bテスト機能** | なし | 複数モデル比較機能 | 高 | 中 | 中 |
| **バックテスト統合** | 別スクリプト（backtest.py） | 最適化と統合 | 中 | 低 | 中 |

---

## 4. 技術的課題の洗い出し

### 4.1 アーキテクチャ上の課題

1. **モジュール間の依存関係が複雑**
   - `race_predictor.py` が多数のモジュールをインポート
   - 変更時の影響範囲が読みにくい

2. **設定値の分散**
   - 重み・閾値がコード内にハードコード
   - 変更するたびにコード修正が必要

3. **テストの困難さ**
   - 単体テストがしにくい構造
   - モックオブジェクトの作成が煩雑

### 4.2 パフォーマンス上の課題

1. **DB接続の頻発**
   - 各Analyzerが個別にDB接続
   - BatchDataLoaderで改善されているが、さらなる最適化の余地

2. **キャッシュの不統一**
   - RaceDataCacheは一部のみ
   - プリセット値のキャッシュがない

### 4.3 保守性の課題

1. **ドキュメント不足**
   - 各補正値の根拠が不明確
   - 変更履歴が追えない

2. **バージョン管理の困難**
   - パラメータ変更がgitのdiffでは追いにくい
   - 設定ファイルの変更影響が可視化されない

---

## 5. 現状の強み（維持すべき点）

### 5.1 データドリブンな補正値

- `venue_course_win_rates.py`: 実データに基づく勝率テーブル（144パターン）
- `weather_rules.json`: 5,640件のデータ分析に基づく天候ルール
- `compound_buff_system.py`: 的中率付きの複合条件ルール

### 5.2 動的重み調整

- `_adjust_weights_dynamically()`: 会場・グレード・データ充実度に応じた動的配点
- 過学習を防ぐための信頼度スケーリング

### 5.3 多段階補正の仕組み

- 基本スコア → 環境補正 → 直前情報統合 → 最終調整
- 各段階で上限・下限を設定して過補正を防止

---

## 6. 推奨アプローチ

### 6.1 段階的リファクタリング

**Phase 1**: プリセット管理の体系化（影響範囲小）
**Phase 2**: スコア統合方式の統一（コア変更）
**Phase 3**: 事前/直前情報の明確な分離（設計変更）
**Phase 4**: 最適化システム構築（新規開発）

### 6.2 並行運用戦略

1. 新エンジン（V2）と旧エンジンを並行して動作させる
2. バックテストで性能比較
3. 段階的に本番移行

### 6.3 リスク管理

- 既存の回収率（約75%）を維持することを最低ラインとする
- 各Phase完了時に回帰テストを実施
- ロールバック手順を事前に準備

---

## 付録A: 調査対象ファイル一覧

| ファイル | 役割 | 行数 |
|---------|------|------|
| src/analysis/race_predictor.py | メイン予測エンジン | 2000+ |
| src/analysis/beforeinfo_scorer.py | 直前情報スコアリング | 973 |
| src/analysis/weather_adjuster.py | 天候補正 | 382 |
| src/analysis/tide_adjuster.py | 潮位補正 | 501 |
| src/analysis/extended_scorer.py | 拡張スコアリング | 600+ |
| src/analysis/compound_buff_system.py | 複合条件バフ | 500+ |
| src/analysis/dynamic_integration.py | 動的スコア統合 | 259 |
| config/venue_characteristics.py | 会場特性 | 277 |
| config/venue_course_win_rates.py | 会場×コース勝率 | 851 |
| config/weather_rules.json | 天候ルール | 177 |
| config/settings.py | 全般設定 | 336 |

---

## 付録B: 現状の補正値上限

| 補正タイプ | 最大加点 | 最大減点 | 適用先 |
|-----------|----------|----------|--------|
| 天候補正 | +5.0 | -5.0 | total_score |
| 潮位補正 | +5.0 | -5.0 | total_score |
| 法則ベース補正 | +10.0 | -10.0 | total_score |
| 複合条件バフ | +15.0 | -15.0 | total_score |
| パターンボーナス | 最大1.411倍 | 0.8倍 | スコア乗算 |
| 直前情報統合 | 40%重み | - | 全体統合 |

---

*本報告書は実装計画書(PREDICTION_REFACTORING_PLAN.md)の基礎資料として使用される*
