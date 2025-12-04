# BEFORE_SCORE改善 実装計画書

作成日: 2025-12-04
作成者: Claude Code (Opus 4.5)

---

## 1. 現状分析

### 1.1 実装状況

#### 現在のファイル構成
```
src/analysis/
  beforeinfo_scorer.py    # 直前情報スコアリング（問題あり）
  dynamic_integration.py  # PRE/BEFORE統合（問題あり）
  extended_scorer.py      # 拡張スコアリング
  race_predictor.py       # 総合予測（統合ロジックあり）
  exhibition_analyzer.py  # 展示分析

config/
  feature_flags.py        # 機能フラグ（dynamic_integration: True）
  settings.py             # スコアリング重み設定
```

#### 現在のBEFORE_SCOREロジック（beforeinfo_scorer.py）
| 項目 | 配点 | 問題点 |
|------|------|--------|
| 展示タイム | 25% | 順位評価のみ、会場標準化なし |
| ST | 25% | 範囲評価が不適切、逆相関の可能性大 |
| 進入隊形 | 20% | **有効（37.8%的中）** |
| 前走成績 | 15% | 効果不明 |
| チルト・風 | 10% | 効果不明 |
| 部品交換・重量 | 5% | **有効（39.2%的中）** |

#### 現在の統合ロジック（race_predictor.py L1443-1541）
- レガシーモード: `FINAL = PRE * 0.6 + BEFORE * 0.4`
- 動的統合モード: `FINAL = PRE * weight_pre + BEFORE * weight_before`
  - CONDITION_WEIGHTS（dynamic_integration.py L40-45）が **0.5/0.5** に設定
  - BEFORE_SCOREが50%も影響 → 逆相関スコアが予測を破壊

### 1.2 問題箇所

#### 問題1: STスコア（_calc_st_score）が逆相関
```python
# 現在の実装 (beforeinfo_scorer.py L166-214)
# ST ≤ 0.10: +30点 → 良いはずだが実際は逆作用
# ST 0.11-0.14: +20点
# ...
# ST×course交互作用の実装が逆方向の可能性
course_importance = 0.8 + (6 - course) * 0.1  # 1コースで0.5、6コースで0.8
```
**問題**:
- 会場別STの標準偏差を考慮していない
- 級別（A1/A2/B1/B2）の補正がない
- 0%的中率 = 完全に逆作用

#### 問題2: 展示タイムスコア（_calc_exhibition_time_score）の評価方法
```python
# 現在の実装 (beforeinfo_scorer.py L136-164)
# 単純な順位評価のみ
rank_scores = {1: 25.0, 2: 18.0, 3: 12.0, ...}
```
**問題**:
- 絶対値の会場標準化がない
- 1位と2位の差（gap）を考慮していない
- 21.6%的中 = ランダム(16.7%)よりやや良いが不十分

#### 問題3: 統合重み（dynamic_integration.py）が過激
```python
# 現在の設定 (dynamic_integration.py L40-45)
CONDITION_WEIGHTS = {
    NORMAL: (0.5, 0.5),  # 壊れたBEFORE_SCOREが50%
    BEFOREINFO_CRITICAL: (0.4, 0.6),  # さらに悪化
    ...
}
```
**問題**:
- 逆相関スコアを50%も反映 → PRE予測を破壊
- 検証結果: 統合すると的中率が低下（43.3% → 16.7%）

### 1.3 データ準備状況

#### データベース（race_details テーブル）
| カラム | 説明 | 完備率 |
|--------|------|--------|
| exhibition_time | 展示タイム | 高 |
| st_time | 展示ST | 高 |
| exhibition_course | 進入コース | 高 |
| tilt_angle | チルト角 | 中 |
| parts_replacement | 部品交換 | 中 |
| adjusted_weight | 調整重量 | 中 |
| prev_race_* | 前走データ | 低 |

#### 不足データ
- 会場別ST平均/標準偏差（venue_st_stats）→ 要構築
- 会場別展示タイム平均/標準偏差 → 要構築
- 選手級別情報 → entriesテーブルに存在

---

## 2. 実装計画の評価

### STEP 1: BEFORE_SCORE完全停止
| 項目 | 評価 |
|------|------|
| 実装難易度 | **Easy** |
| 期待効果 | **High**（即座にPRE単体の精度に回復） |
| 実装時間 | **短期（30分）** |
| リスク | **Low**（ロールバック容易） |
| **推奨** | **即座実装** |

**理由**:
- 現状のBEFORE_SCOREは逆相関（統合すると的中率が低下）
- `feature_flags.py`の`dynamic_integration`をFalseにし、レガシーモードの重みを調整するだけ
- PRE単体で43.3%的中 vs 統合後16.7%的中 → 明らかにPRE単体が優秀

**作業内容**:
1. `config/feature_flags.py`: `dynamic_integration: False`
2. `src/analysis/race_predictor.py` L1510-1516: レガシーモードを`PRE * 1.0 + BEFORE * 0.0`に変更

---

### STEP 2: BEFORE_SAFE構築
| 項目 | 評価 |
|------|------|
| 実装難易度 | **Easy** |
| 期待効果 | **Medium**（有効な要素のみで安全に統合） |
| 実装時間 | **短期（2-3時間）** |
| リスク | **Low**（既存コードへの影響小） |
| **推奨** | **Phase 1で実装** |

**理由**:
- 進入コース（37.8%）と部品交換（39.2%）は有効
- これらだけで`BEFORE_SAFE`を構築し、安全に統合
- ST/展示タイム等の逆相関要素を除外

**作業内容**:
1. 新規ファイル作成: `src/analysis/before_safe_scorer.py`
2. 進入コーススコア + 部品交換スコアのみを実装
3. 正規化してPREスケール（0-100）に合わせる

---

### STEP 3: PRE x BEFORE_SAFE安全統合
| 項目 | 評価 |
|------|------|
| 実装難易度 | **Easy** |
| 期待効果 | **Medium**（PRE精度を維持しつつ改善の可能性） |
| 実装時間 | **短期（1-2時間）** |
| リスク | **Low**（重みを保守的に設定） |
| **推奨** | **Phase 2で実装** |

**理由**:
- `FINAL = 0.90 * PRE + 0.10 * BEFORE_SAFE`
- PRE_SCOREを壊さない保守的な統合
- 段階的に重みを調整可能（0.10 → 0.15）

**作業内容**:
1. `src/analysis/safe_integrator.py` を新規作成
2. `race_predictor.py`の統合ロジックを差し替え
3. 設定ファイルで重みを調整可能に

---

### STEP 4: ST・展示タイムを再設計
| 項目 | 評価 |
|------|------|
| 実装難易度 | **Hard** |
| 期待効果 | **High**（正しく実装すれば大幅改善の可能性） |
| 実装時間 | **中期（3-5日）** |
| リスク | **Medium**（新ロジックが逆相関を生む可能性） |
| **推奨** | **Phase 3で段階的実装** |

**理由**:
- STと展示タイムは本来有効な指標だが、現在のロジックが逆作用
- 会場別標準化、級別補正、風向連動が必要
- 実装後に十分な検証が必要

**作業内容**:
1. 会場別ST統計テーブル構築
2. `src/scoring/st_scorer.py` 新規作成
3. `src/scoring/exhibition_scorer.py` 新規作成
4. バックテストで検証

---

## 3. 段階的実装ロードマップ

### Phase 1（即座実施）: BEFORE_SCORE停止 + BEFORE_SAFE基盤
**所要時間**: 3-4時間
**目標**: PRE単体の精度に回復し、BEFORE_SAFE基盤を構築

| タスク | 優先度 | 所要時間 |
|--------|--------|----------|
| 1.1 BEFORE_SCORE完全停止 | 最高 | 30分 |
| 1.2 BEFORE_SAFEスコアラー作成 | 高 | 2時間 |
| 1.3 単体テスト作成 | 高 | 1時間 |

### Phase 2（短期: 1-2日）: 安全統合の実装と検証
**所要時間**: 1-2日
**目標**: BEFORE_SAFEをPREと安全に統合

| タスク | 優先度 | 所要時間 |
|--------|--------|----------|
| 2.1 安全統合ロジック実装 | 高 | 2時間 |
| 2.2 バックテスト環境構築 | 高 | 2時間 |
| 2.3 30レースでの検証 | 高 | 1時間 |
| 2.4 重み調整（0.05→0.10→0.15） | 中 | 2時間 |

### Phase 3（中期: 1週間）: ST・展示タイム再設計
**所要時間**: 5-7日
**目標**: 逆相関を解消し、正しいスコアリングを実装

| タスク | 優先度 | 所要時間 |
|--------|--------|----------|
| 3.1 会場別統計テーブル構築 | 高 | 4時間 |
| 3.2 STスコア再実装 | 高 | 4時間 |
| 3.3 展示タイムスコア再実装 | 高 | 4時間 |
| 3.4 単体テスト | 高 | 2時間 |
| 3.5 100レースバックテスト | 高 | 2時間 |
| 3.6 段階的統合（0.05ずつ） | 中 | 継続 |

### Phase 4（保留）: 完全版BEFORE_SCORE復活
**理由**: ST・展示の再設計が成功した後に検討
**条件**: Phase 3の検証で正の相関が確認されること

| タスク | 条件 | 所要時間 |
|--------|------|----------|
| 4.1 前走成績の検証 | Phase 3完了後 | 2時間 |
| 4.2 チルト・風の検証 | 同上 | 2時間 |
| 4.3 BEFORE_ADVANCED構築 | 同上 | 4時間 |
| 4.4 Optuna最適化 | 同上 | 8時間 |

---

## 4. 詳細作業計画

### Phase 1の作業

#### タスク1.1: BEFORE_SCORE完全停止
- **ファイル**:
  - `config/feature_flags.py`
  - `src/analysis/race_predictor.py`
- **変更内容**:
  ```python
  # config/feature_flags.py L11
  'dynamic_integration': False,  # True → False

  # src/analysis/race_predictor.py L1510-1516
  # レガシーモードの重みを変更
  else:
      # BEFORE_SCORE停止: PRE * 1.0 + BEFORE * 0.0
      final_score = pre_score * 1.0 + before_score * 0.0
      pred['integration_mode'] = 'before_disabled'
      pred['pre_weight'] = 1.0
      pred['before_weight'] = 0.0
  ```
- **テスト方法**:
  ```bash
  python -c "from src.analysis.race_predictor import RacePredictor; p = RacePredictor(); print(p.predict_race(1))"
  ```
- **検証指標**: 予測結果にbeforeinfo_scoreが0の影響を確認
- **所要時間**: 30分
- **ロールバック**: 元の値に戻すだけ

#### タスク1.2: BEFORE_SAFEスコアラー作成
- **ファイル**: `src/analysis/before_safe_scorer.py`（新規作成）
- **変更内容**:
  ```python
  """
  BEFORE_SAFE スコアラー

  有効な直前情報のみを使用する安全版スコアリング
  - 進入コース（37.8%的中）
  - 部品交換・体重（39.2%的中）
  """

  class BeforeSafeScorer:
      # 進入コーススコア
      def calc_entry_score(self, pit_number, exhibition_courses):
          # 枠なり: 0点
          # 1コース奪取: +12点
          # 2コース奪取: +8点
          # 深イン: -10点
          ...

      # 部品交換スコア
      def calc_parts_score(self, parts_dict, weight_delta):
          # ピストン交換: -12点（交換は不調の兆候）
          # リング交換: -8点
          # 体重+1kg: -1点
          ...

      # 統合スコア
      def calculate_before_safe_score(self, race_id, pit_number):
          entry = self.calc_entry_score(...)
          parts = self.calc_parts_score(...)
          return 0.6 * entry + 0.4 * parts
  ```
- **テスト方法**:
  ```bash
  python -m pytest tests/test_before_safe_scorer.py -v
  ```
- **検証指標**:
  - 進入コーススコアと実際の着順の相関（正の相関であること）
  - 部品交換スコアと実際の着順の相関
- **所要時間**: 2時間

#### タスク1.3: 単体テスト作成
- **ファイル**: `tests/test_before_safe_scorer.py`（新規作成）
- **変更内容**:
  ```python
  import pytest
  from src.analysis.before_safe_scorer import BeforeSafeScorer

  def test_entry_score_in_grab():
      """1コース奪取は高スコア"""
      scorer = BeforeSafeScorer()
      # 2号艇が1コースを取った場合
      score = scorer.calc_entry_score(2, {1: 2, 2: 1, 3: 3, 4: 4, 5: 5, 6: 6})
      assert score > 0

  def test_parts_piston_penalty():
      """ピストン交換はペナルティ"""
      scorer = BeforeSafeScorer()
      score = scorer.calc_parts_score({'P': True}, 0)
      assert score < 0
  ```
- **所要時間**: 1時間

---

### Phase 2の作業

#### タスク2.1: 安全統合ロジック実装
- **ファイル**: `src/analysis/safe_integrator.py`（新規作成）
- **変更内容**:
  ```python
  """
  安全統合ロジック

  FINAL = 0.90 * PRE + 0.10 * BEFORE_SAFE
  """

  def normalize_to_0_100(arr):
      """BEFORE_SAFEをPREスケールに正規化"""
      ...

  def safe_integrate(pre_scores, before_safe_scores, w_before=0.10):
      """
      安全な統合

      Args:
          pre_scores: PRE_SCOREのリスト
          before_safe_scores: BEFORE_SAFEのリスト
          w_before: BEFORE_SAFEの重み（0.05-0.15推奨）
      """
      bf_norm = normalize_to_0_100(before_safe_scores)
      return (1.0 - w_before) * pre_scores + w_before * bf_norm
  ```
- **テスト方法**: 単体テスト + 30レースでの検証
- **検証指標**:
  - 統合前後の的中率比較
  - changed_races（予測が変わったレース）の的中率
- **所要時間**: 2時間

#### タスク2.2: バックテスト環境構築
- **ファイル**: `scripts/before_safe_backtest.py`（新規作成）
- **変更内容**:
  ```python
  """
  BEFORE_SAFEバックテスト

  比較対象:
  1. PRE単体（baseline）
  2. PRE + BEFORE_SAFE (w=0.05)
  3. PRE + BEFORE_SAFE (w=0.10)
  4. PRE + BEFORE_SAFE (w=0.15)
  """

  def run_backtest(test_races, weight):
      """指定重みでバックテスト実行"""
      ...

  def log_changed_races(pre_pred, final_pred, actual):
      """予測変化レースをログ"""
      ...
  ```
- **所要時間**: 2時間

#### タスク2.3: 30レースでの検証
- **方法**:
  1. 直近30レースを抽出
  2. PRE単体と各重みで予測
  3. 的中率を比較
- **検証指標**:
  - 単勝的中率
  - 予測変化レースの的中率（重要）
  - ROI（可能であれば）
- **所要時間**: 1時間

---

### Phase 3の作業

#### タスク3.1: 会場別統計テーブル構築
- **ファイル**: `scripts/build_venue_stats.py`（新規作成）
- **変更内容**:
  ```sql
  -- 会場別ST統計
  CREATE TABLE IF NOT EXISTS venue_st_stats (
      venue_code TEXT,
      avg_st REAL,
      std_st REAL,
      sample_count INTEGER,
      updated_at TEXT
  );

  -- 会場別展示タイム統計
  CREATE TABLE IF NOT EXISTS venue_exhibition_stats (
      venue_code TEXT,
      avg_time REAL,
      std_time REAL,
      sample_count INTEGER,
      updated_at TEXT
  );
  ```
- **所要時間**: 4時間

#### タスク3.2: STスコア再実装
- **ファイル**: `src/scoring/st_scorer.py`（新規作成）
- **変更内容**:
  ```python
  """
  STスコア再設計版

  特徴:
  - 会場別標準化（z-score）
  - 級別補正（A1/A2/B1/B2）
  - 風向連動（向い風/追い風）
  """

  ST_BUCKETS = [
      (0.00, 0.10, 35),  # 爆速
      (0.11, 0.13, 25),  # 速い
      (0.14, 0.16, 10),  # 普通
      (0.17, 0.20, 0),   # 遅い
      (0.21, 10.0, -15), # かなり遅い
  ]

  RANK_SCALE = {"A1": 1.05, "A2": 1.02, "B1": 0.95, "B2": 0.90}

  def st_score(st, course, racer_rank, wind_speed, wind_dir, venue_mu, venue_sigma):
      base = st_bucket_score(st)

      # 会場標準化
      if venue_mu and venue_sigma > 0:
          z = (st - venue_mu) / venue_sigma
          base += max(0, -z * 3.0)  # 小さいSTほど良い

      # 級別補正
      scale = RANK_SCALE.get(racer_rank, 1.0)

      # 風向補正
      wadj = wind_adjustment(course, wind_speed, wind_dir)

      return base * scale + wadj
  ```
- **所要時間**: 4時間

#### タスク3.3: 展示タイムスコア再実装
- **ファイル**: `src/scoring/exhibition_scorer.py`（新規作成）
- **変更内容**:
  ```python
  """
  展示タイムスコア再設計版

  特徴:
  - レース内順位評価（絶対値ではない）
  - 差分ボーナス（1位と2位の差が大きい時）
  - 会場標準化
  """

  RANK_BASE = {1: 20, 2: 15, 3: 10, 4: 5, 5: 2, 6: 0}

  def exhibition_score(ex_rank, ex_time, ex_times, venue_mean, venue_std):
      score = RANK_BASE.get(ex_rank, 0)

      # 差分ボーナス
      if ex_times and len(ex_times) >= 2:
          sorted_times = sorted(ex_times)
          gap_12 = sorted_times[1] - sorted_times[0]
          all_gaps = np.diff(sorted_times)
          mean_gap = np.mean(all_gaps)
          std_gap = np.std(all_gaps)
          if gap_12 > mean_gap + 0.8 * std_gap:
              score += 5

      # 会場標準化
      if venue_mean and venue_std > 0:
          z = (ex_time - venue_mean) / venue_std
          if z < -1.0:  # 会場平均より速い
              score += 4
          elif z > 1.0:  # 会場平均より遅い
              score -= 3

      return score
  ```
- **所要時間**: 4時間

---

## 5. リスク管理

### リスク一覧

| リスク | 影響度 | 発生確率 | 対策 |
|--------|--------|----------|------|
| BEFORE停止で一時的に精度低下 | 低 | 低 | 検証結果ではPRE単体が優秀、問題なし |
| BEFORE_SAFEが逆相関 | 中 | 低 | 有効な項目のみ使用、事前検証で確認 |
| ST再設計が逆相関 | 中 | 中 | 段階的導入（0.05から）、モニタリング |
| 展示タイム再設計が逆相関 | 中 | 中 | 同上 |
| データベース更新時の不整合 | 低 | 低 | トランザクション使用、バックアップ |

### ロールバック手順

#### Phase 1のロールバック
```bash
# feature_flags.pyを元に戻す
git checkout config/feature_flags.py

# race_predictor.pyを元に戻す
git checkout src/analysis/race_predictor.py
```

#### Phase 2のロールバック
```bash
# 新規ファイルを削除
rm src/analysis/before_safe_scorer.py
rm src/analysis/safe_integrator.py

# race_predictor.pyのインポートと呼び出しをコメントアウト
```

#### Phase 3のロールバック
```bash
# 新規ファイルを削除
rm src/scoring/st_scorer.py
rm src/scoring/exhibition_scorer.py

# 統計テーブルを削除（必要に応じて）
sqlite3 data/boatrace.db "DROP TABLE IF EXISTS venue_st_stats;"
sqlite3 data/boatrace.db "DROP TABLE IF EXISTS venue_exhibition_stats;"
```

### モニタリング計画

#### 毎日確認する指標
1. **単勝的中率**: PRE単体 vs 統合後
2. **changed_races的中率**: 予測が変わったレースの的中率（最重要）
3. **スコア相関**: 各スコアと実際の着順の相関係数

#### 異常検知基準
- 単勝的中率が baseline - 3% 以下で警告
- changed_races的中率が 30% 以下で即座にロールバック
- スコア相関が負になったらロールバック

#### ログ出力
```python
# changed_races.csv
race_id, pit, pre_rank, final_rank, actual_rank, pre_score, before_safe_score, final_score
```

---

## 6. 実装推奨順序（最終結論）

### 即座に実施すべきこと（今日中）

1. **BEFORE_SCORE完全停止**（30分）
   - `dynamic_integration: False`
   - レガシーモードを `PRE * 1.0 + BEFORE * 0.0`
   - **効果**: 即座にPRE単体の精度（43.3%）に回復

2. **BEFORE_SAFEスコアラー作成**（2時間）
   - 進入コース + 部品交換のみ
   - 有効性が確認された項目だけを使用

### 明日以降（1-2日）

3. **安全統合の実装と検証**
   - `FINAL = 0.90 * PRE + 0.10 * BEFORE_SAFE`
   - 30レースでの検証
   - changed_races的中率が重要

### 来週以降（1週間）

4. **ST・展示タイム再設計**
   - 会場別統計テーブル構築が前提
   - 十分な検証期間を確保
   - 段階的に統合（0.05から開始）

### 当面保留

5. **完全版BEFORE_SCORE復活**
   - Phase 3の検証結果次第
   - ST・展示が正の相関を示してから

---

## 付録: クイックリファレンス

### 設定変更箇所一覧

| ファイル | 行 | 変更内容 |
|----------|-----|----------|
| `config/feature_flags.py` | L11 | `dynamic_integration: False` |
| `src/analysis/race_predictor.py` | L1510-1516 | 重みを `1.0/0.0` に変更 |
| `src/analysis/dynamic_integration.py` | L40-45 | CONDITION_WEIGHTS（Phase 3以降） |

### 検証コマンド

```bash
# BEFORE停止の確認
python -c "from config.feature_flags import is_feature_enabled; print(is_feature_enabled('dynamic_integration'))"
# 期待出力: False

# 単体テスト実行
python -m pytest tests/test_before_safe_scorer.py -v

# バックテスト実行
python scripts/before_safe_backtest.py --races 30 --weight 0.10
```

### 重要な検証指標

| 指標 | 目標値 | 警告基準 |
|------|--------|----------|
| 単勝的中率 | 43%以上 | 40%未満で要確認 |
| changed_races的中率 | 40%以上 | 30%未満でロールバック |
| スコア相関（Pearson） | 正の値 | 負でロールバック |

---

**作成完了: 2025-12-04**
**次のステップ**: Phase 1のタスク1.1（BEFORE_SCORE完全停止）を即座に実施
