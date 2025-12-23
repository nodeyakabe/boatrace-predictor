# 残タスク一覧

**最終更新**: 2025-12-11

---

## 優先度：中（直前情報データの活用拡大）

### 1. チルト角度の複合データ活用

**現状**:
- チルト角度は単独で使用すると逆相関になる（チルトを上げる＝モーター調整不足の可能性）
- BeforeInfoScorerで計算はしているがパターンボーナスでは未使用

**目標**:
- 複合的なデータ（モーター2連率、選手の調整力、会場特性など）と組み合わせて活用
- チルト角度の意味を正しく解釈できるモデル構築

**作業内容**:
- チルト角度×モーター2連率の交互作用を検証
- チルト角度変更（前節からの変化）の影響を検証
- 会場別のチルト影響係数を分析

**優先度**: 中（データ分析後に実装判断）

---

### 2. 前走成績の活用

**現状**:
- `race_details`テーブルに`prev_race_*`データあり（prev_race_course, prev_race_st, prev_race_rank）
- BeforeInfoScorerで15%配点で計算しているが、パターンボーナスでは未使用

**目標**:
- 前走の好成績（1-2着）やST良好は当日のコンディションの指標として活用
- 前走からの連続好走パターンを検出

**作業内容**:
- 前走成績と当レース結果の相関分析
- 前走ST×当日STの一貫性パターン検証
- パターンボーナスへの組み込み検討

**優先度**: 中（展示タイム・STと同様の効果が期待できる）

---

### 3. 気象データソースの分離

**現状**:
- 事前予想: `race_conditions`テーブルから気象データ取得
- 直前予想: 同じく`race_conditions`テーブルを使用

**目標**:
- 事前予想: `race_conditions`テーブル（過去データ）を使用
- 直前予想: `beforeinfo_scraper`で直前情報ページから最新気象データを取得

**作業内容**:
- `BeforeInfoScraper._extract_weather_data()`は実装・動作確認済み（2025-12-11）
- `race_predictor.py`の`_apply_weather_adjustment`を直前情報ページの気象データに対応させる
- 予測タイプ（事前/直前）に応じてデータソースを切り替えるロジック追加

**取得可能データ**:
- temperature: 気温（℃）
- water_temp: 水温（℃）
- wind_speed: 風速（m）
- wave_height: 波高（cm）
- weather_code: 天候コード（1=晴, 2=曇, 3=雨など）
- wind_dir_code: 風向コード

**優先度**: 中（リアルタイム予測の精度向上に寄与）

---

## 2025-12-06 分析結果: コース別特徴量の検証

### 検証内容
11月予測データに対し、以下の新規特徴量の効果を検証：
- `course_win_rate`: 選手×コース別勝率
- `course_2ren_rate`: 選手×コース別2連対率
- `venue_course_win`: 選手×会場×コース別勝率

### 検証結果

| テスト | AUC変化 | 結論 |
|--------|---------|------|
| venue_course_win 追加（生データ） | **-10.18%** | 過学習で大幅悪化 |
| Bayesian smoothing適用後 | -0.34% | 悪化は抑えたが改善なし |
| スムージング強度チューニング（0〜50） | -0.07%〜-0.68% | どの設定でも改善せず |

**ベースライン**: AUC 0.8224, 1着的中率 62.14%

### 結論
**コース別特徴量の追加は見送り**
- 既存の選手統計（win_rate, second_rate, third_rate）が十分な情報を含む
- 新特徴量は冗長であり、追加してもモデル性能は向上しない
- venue_course_win はスパースデータによる過学習リスクが高い

### 今後の方針
1. **新規特徴量追加より、以下のアプローチを優先**：
   - モデルパラメータのチューニング（n_estimators, max_depth, learning_rate）
   - 訓練データ期間の調整（直近データの重み付け）
   - 未使用データの活用（展示タイム、天候、節間成績など）

2. **作成した検証スクリプト（temp/配下）を今後の特徴量評価に再利用**：
   - `temp/additive_comparison.py`: 追加効果の検証
   - `temp/improved_features_test.py`: Bayesian smoothing付き検証
   - `temp/smoothing_tuning.py`: スムージング強度チューニング
   - `temp/strict_comparison.py`: 時系列厳密版比較

---

## 優先度：低（機能追加）

### 1. 統合スコア詳細のUI表示

**現状**:
- UIには統合後のスコアのみ表示

**目標**:
- PRE_SCORE、BEFORE_SCORE、重み配分を個別表示
- ユーザーが判断材料にできるようにする

**作業内容**:
- Streamlit UIの予測結果表示部分を拡張
- 各艇の詳細情報（PRE/BEFORE/重み）を表形式で表示

**見積もり**: 2-3時間

**優先度**: 低（分析用途では有用）

---

### 2. Walk-forward Backtestの実行

**現状**:
- Walk-forward Backtest機能は実装済み
- 実際のテストは未実行

**目標**:
- 時系列を考慮した精度検証
- 過学習の有無を確認

**作業内容**:
- [scripts/walkforward_backtest.py](../scripts/walkforward_backtest.py) を実行
- 結果を分析してレポート作成

**見積もり**: 半日（実行時間 + 分析）

**優先度**: 低（運用開始後でも可）

---

## 完了済みタスク

### ✅ Phase 1: 基本機能実装
- [x] 動的統合ロジック（DynamicIntegrator）
- [x] 進入予測モデル（EntryPredictionModel）
- [x] 直前情報スコアラー（BeforeInfoScorer）
- [x] 統合スコア計算

### ✅ Phase 2-3: 展開機能実装
- [x] Walk-forward Backtest
- [x] Performance Monitor
- [x] Gradual Rollout

### ✅ 検証・テスト
- [x] BeforeInfoScorer単体テスト
- [x] 統合スコア動作確認
- [x] 30レーステスト
- [x] 順位変動の確認

### ✅ ドキュメント作成
- [x] 最終検証レポート
- [x] パフォーマンス最適化計画
- [x] DB最適化タスク
- [x] 予想ロジック仕様書（更新）

### ✅ DB接続最適化（2025-12-07 確認）
- [x] DB接続プール実装（[src/utils/db_connection_pool.py](../src/utils/db_connection_pool.py)）
  - スレッドごとの接続再利用
  - WALモード、キャッシュサイズ64MB、メモリマップ256MB
- [x] バッチデータローダー実装（[src/database/batch_data_loader.py](../src/database/batch_data_loader.py)）
  - 日単位データ一括取得でN+1問題解消

### ✅ 動的統合・条件別重み配分（2025-12-07 確認）
- [x] 動的統合モジュール（[src/analysis/dynamic_integration.py](../src/analysis/dynamic_integration.py)）
  - 条件別重み: NORMAL(50/50), BEFOREINFO_CRITICAL(40/60), PREINFO_RELIABLE(50/50), UNCERTAIN(50/50)
  - 展示タイム分散、ST分散、進入変更、天候変化、事前予測信頼度で自動判定
- [x] BEFORE_SCOREのスケール調整
  - 展示タイム25点、ST30点（フライング-25点）、進入20点などの配点済み

### ✅ A/Bテスト機能（2025-12-07 確認）
- [x] A/Bテストフレームワーク（[src/evaluation/ab_test_dynamic_integration.py](../src/evaluation/ab_test_dynamic_integration.py)）
  - 動的統合 vs レガシーモードの比較
  - 精度向上率の自動計算
  - レポート自動生成

---

## 備考

- すべてのタスクは現在の機能を壊さないように実装
- 精度向上施策は必ずバックテストで効果確認
- 主要タスクは完了し、運用フェーズに移行済み
