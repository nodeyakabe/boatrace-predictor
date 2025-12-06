# 残タスク一覧

**最終更新**: 2025-12-07

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
