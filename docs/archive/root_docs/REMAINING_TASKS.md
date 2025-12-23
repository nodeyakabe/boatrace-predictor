# 残タスク・今後の改善計画

## 📋 概要

2025年11月3日時点での実装完了状況と、今後取り組むべきタスクをまとめたドキュメントです。

---

## ✅ 完了済みタスク

### Stage1: レース選別モデル
- [x] レース選別モデル（RaceSelector）の実装
- [x] Stage1学習UIの追加
- [x] リアルタイム予想タブへの統合
- [x] buy_scoreの自動計算と表示

### Stage2: 予測モデル
- [x] XGBoostモデルの学習・評価
- [x] 特徴量エンジニアリング
- [x] モデル評価UIの実装
- [x] 予測シミュレーション機能

### 確率校正
- [x] ProbabilityCalibratorクラスの実装
- [x] ModelTrainerへの統合
- [x] 確率校正UIタブの追加
- [x] Platt Scaling / Isotonic Regressionの実装
- [x] 校正前後の評価指標表示

### Kelly基準投資戦略
- [x] KellyBettingStrategyクラスの実装
- [x] 期待値・エッジ・ROI計算
- [x] リアルタイム予想タブへの統合
- [x] 購入推奨UIの実装

### オッズAPI
- [x] OddsFetcherクラスの基本実装
- [x] モックオッズ生成機能
- [x] UIへの統合（自動フォールバック）
- [x] テストスクリプトの作成

---

## 🔄 残タスク

### 優先度：高（1〜2週間以内）

#### 1. Stage2モデル学習機能の実装 ✅ 完了
**ファイル:** `src/training/stage2_trainer.py`, `ui/components/stage2_training.py`

**完了日:** 2025-11-03

**実装内容:**
- LightGBMを使用した6つの二値分類器アンサンブル
- Optunaによるハイパーパラメータ最適化
- クロスバリデーション機能
- モデル評価・保存・読み込み機能
- UI統合（データ準備、学習、評価、管理の4タブ）

**詳細:** [STAGE2_MODEL_COMPLETED.md](STAGE2_MODEL_COMPLETED.md)

**ToDo:**
```markdown
- [ ] 特徴量生成の実装
  - [ ] Phase 3.3 特徴量の実装（feature_generator.py:137）
  - [ ] 直近N戦の平均着順
  - [ ] 当地相性スコア
  - [ ] 天候・水面条件との相関

- [ ] Stage2モデル学習機能の実装
  - [ ] XGBoost マルチクラス分類（6クラス: 1着〜6着）
  - [ ] 学習データの準備・分割
  - [ ] ハイパーパラメータの設定
  - [ ] モデルの保存・読み込み機能

- [ ] モデル評価機能の実装
  - [ ] Log Loss計算
  - [ ] 着順別の適合率・再現率
  - [ ] 混同行列の表示
  - [ ] 特徴量重要度の可視化

- [ ] UI実装
  - [ ] モデル学習タブの実装（model_training.py:299）
  - [ ] 学習パラメータ設定UI
  - [ ] 学習進捗表示
  - [ ] 評価結果の可視化
```

**関連ファイル:**
- [ui/components/model_training.py:299](ui/components/model_training.py#L299) - 未実装タブ
- [src/analysis/feature_generator.py:137](src/analysis/feature_generator.py#L137) - Phase 3.3 特徴量
- [src/ml/model_trainer.py](src/ml/model_trainer.py) - モデル学習クラス

---

#### 2. オッズAPI実装の完成
**ファイル:** `src/scraper/odds_fetcher.py`

**現状:**
- スクレイピングの基本構造は実装済み
- 実際のHTML構造は未確認（タイムアウト発生）
- モックオッズで動作中

**ToDo:**
```markdown
- [ ] BOAT RACE公式サイトのHTML構造を調査
  - [ ] ブラウザの開発者ツールでオッズページを確認
  - [ ] 実際のCSSセレクター、クラス名を特定
  - [ ] データ構造をドキュメント化

- [ ] fetch_sanrentan_odds()を実HTML構造に適合
  - [ ] 正しいCSSセレクターに変更
  - [ ] データ抽出ロジックの修正
  - [ ] エラーハンドリングの強化

- [ ] タイムアウト・リトライ処理の改善
  - [ ] タイムアウト時間の調整（10秒→30秒）
  - [ ] リトライ機能の追加（最大3回）
  - [ ] 指数バックオフの実装

- [ ] テストと検証
  - [ ] test_odds_fetcher.pyの実行
  - [ ] 実際のレースでオッズ取得確認
  - [ ] エラーケースのテスト
```

**参考ファイル:**
- [ODDS_API_STATUS.md](ODDS_API_STATUS.md) - 実装状況の詳細
- [test_odds_fetcher.py](test_odds_fetcher.py) - テストスクリプト

---

#### 3. 確率校正の効果検証
**ファイル:** `src/ml/model_trainer.py`, `ui/components/model_training.py`

**現状:**
- 確率校正機能は実装済み
- 実際のデータで効果は未検証

**ToDo:**
```markdown
- [ ] 実データでの確率校正実行
  - [ ] Stage2モデルを学習（データ準備タブ）
  - [ ] 確率校正を実行（確率校正タブ）
  - [ ] Log Loss、Brier Scoreの改善度を確認

- [ ] 校正曲線の可視化
  - [ ] plot_calibration_curve()の動作確認
  - [ ] 校正前後の比較グラフ作成
  - [ ] UIでの表示確認

- [ ] Kelly基準への影響確認
  - [ ] 校正前後での推奨賭け金の変化
  - [ ] 期待値計算の精度向上確認
  - [ ] バックテストでのROI比較
```

---

#### 4. Stage1モデルの精度向上
**ファイル:** `src/ml/race_selector.py`

**現状:**
- 基本的なレース選別機能は実装済み
- 特徴量エンジニアリングの余地あり

**ToDo:**
```markdown
- [ ] 特徴量の追加
  - [ ] 会場別の平均オッズ
  - [ ] 過去N日間の決着パターン
  - [ ] 天候・風速データ（取得可能なら）
  - [ ] 時間帯（午前/午後/ナイター）

- [ ] モデルのチューニング
  - [ ] GridSearchでハイパーパラメータ最適化
  - [ ] AUC > 0.75を目標
  - [ ] 過学習の防止（Early Stopping調整）

- [ ] バックテストでの検証
  - [ ] buy_score閾値の最適化（0.5 / 0.6 / 0.7）
  - [ ] 閾値別のROI比較
  - [ ] 見送りレースの精度確認
```

---

#### 5. リアルタイム予想の作りこみ
**ファイル:** `ui/components/realtime_prediction.py`, `src/analysis/realtime_predictor.py`

**現状:**
- 基本的なリアルタイム予想機能は実装済み
- UX改善、表示の最適化、エラーハンドリングの強化が必要
- より直感的でわかりやすいUIが求められる

**ToDo:**
```markdown
- [ ] UI/UX改善
  - [ ] 予想結果の見やすさ向上
  - [ ] ローディング表示の改善
  - [ ] エラー時のフィードバック強化
  - [ ] レスポンシブデザイン対応

- [ ] 機能追加
  - [ ] 予想履歴の保存・参照
  - [ ] 的中率・回収率のリアルタイム表示
  - [ ] お気に入り会場の登録
  - [ ] 通知機能（高確率レースのアラート）

- [ ] パフォーマンス最適化
  - [ ] 予測処理の高速化
  - [ ] キャッシュ機能の実装
  - [ ] 並列処理の導入
```

---

#### 6. 解析・法則だし・学習機能の簡易化 ✅（ドキュメント完成）
**ファイル:** `src/analysis/`, `ui/components/`

**実装完了日:** 2025年11月3日（ドキュメント整備フェーズ）

**完了内容:**
- [x] ドキュメント整備
  - [x] 各モジュールの役割を明記（ANALYSIS_MODULE_GUIDE.md）
  - [x] データフロー図の作成
  - [x] API仕様書の作成
  - [x] 使い方ガイドの作成
  - [x] 18モジュールの分類・依存関係マップ

**今後のタスク:**
```markdown
- [ ] アーキテクチャの見直し（次フェーズ）
  - [ ] モジュール間の依存関係を整理
  - [ ] 責任の明確化（単一責任の原則）
  - [ ] 不要な抽象化の削減

- [ ] コードの簡素化（次フェーズ）
  - [ ] 複雑なロジックの分割
  - [ ] 共通処理の統合
  - [ ] 冗長なコードの削除

- [ ] UI統合（次フェーズ）
  - [ ] 学習フローの簡素化
  - [ ] 設定項目の最小化
  - [ ] デフォルト値の最適化
```

**関連ドキュメント:**
- [ANALYSIS_MODULE_GUIDE.md](ANALYSIS_MODULE_GUIDE.md) - 包括的な分析モジュールガイド（450行）

---

#### 7. 各競艇場・選手データの解析 ✅
**ファイル:** `src/analysis/racer_analyzer.py`, `src/analysis/venue_analyzer.py`, `ui/components/venue_analysis.py`, `ui/components/racer_analysis.py`

**実装完了日:** 2025年11月3日

**実装内容:**
- [x] 会場別データ解析
  - [x] 各競艇場の特性分析（水面、風向、コース幅など）
  - [x] 会場別の勝率・決まり手パターン
  - [x] 季節・天候別のパフォーマンス
  - [x] 枠番別の有利不利分析

- [x] 選手データ解析
  - [x] 選手別の得意会場分析
  - [x] 直近成績のトレンド分析（improving/stable/declining判定）
  - [x] 全会場での成績比較

- [x] データ可視化
  - [x] ヒートマップでの会場別成績表示（全24会場のコース別勝率）
  - [x] レーダーチャートでの選手能力表示（5軸評価）
  - [x] バーチャート、パイチャートでの詳細分析

**関連ドキュメント:**
- [VENUE_RACER_ANALYSIS_UI_COMPLETED.md](VENUE_RACER_ANALYSIS_UI_COMPLETED.md) - 実装完了報告

---

#### 8. 公式の場データの組み込み ✅
**URL:** https://www.boatrace.jp/owpc/pc/data/stadium?jcd=01
**ファイル:** `src/scraper/official_venue_scraper.py`, `src/database/venue_data.py`, `fetch_venue_data.py`

**実装完了日:** 2025年11月3日

**実装内容:**
- [x] スクレイピング実装
  - [x] 公式サイトのHTML構造調査（WebFetchで確認）
  - [x] 24場（jcd=01〜24）のデータ取得機能
  - [x] 水面特性、コース情報、施設データの抽出
  - [x] エラーハンドリング・リトライ処理

- [x] データベース設計
  - [x] venue_data テーブルの作成
  - [x] 会場マスタデータの設計
  - [x] 更新履歴の管理（updated_atカラム）

- [ ] データ統合（次フェーズ）
  - [ ] 既存の予測モデルへの統合
  - [ ] 特徴量としての活用
  - [ ] 会場別の補正係数計算

- [x] UI統合
  - [x] 会場データ表示タブの追加（venue_analysis.py タブ3）
  - [x] データ更新機能（fetch_venue_data.py）
  - [x] 会場別統計情報の可視化

**実装済みスキーマ:**
```sql
CREATE TABLE venue_data (
    venue_code TEXT PRIMARY KEY,
    venue_name TEXT NOT NULL,
    water_type TEXT,
    tidal_range TEXT,
    motor_type TEXT,
    course_1_win_rate REAL,
    course_2_win_rate REAL,
    course_3_win_rate REAL,
    course_4_win_rate REAL,
    course_5_win_rate REAL,
    course_6_win_rate REAL,
    record_time TEXT,
    record_holder TEXT,
    record_date TEXT,
    characteristics TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**関連ドキュメント:**
- [OFFICIAL_VENUE_DATA_IMPLEMENTATION.md](OFFICIAL_VENUE_DATA_IMPLEMENTATION.md) - 実装完了報告

---

### 優先度：中（3〜4週間以内）

#### 9. 購入実績の記録・分析機能
**新規ファイル:** `src/betting/bet_tracker.py`

**目的:**
実際の購入結果を記録し、戦略の改善に活用

**ToDo:**
```markdown
- [ ] BetTrackerクラスの実装
  - [ ] データベーステーブル設計（bet_history）
  - [ ] 購入記録の保存機能
  - [ ] 結果の更新機能

- [ ] 分析機能の実装
  - [ ] ROI（投資収益率）の計算
  - [ ] 勝率・回収率の集計
  - [ ] 最大ドローダウンの追跡
  - [ ] 資金推移のグラフ表示

- [ ] UI統合
  - [ ] 購入履歴表示タブの追加
  - [ ] グラフ・統計情報の表示
  - [ ] CSVエクスポート機能
```

**データベーススキーマ例:**
```sql
CREATE TABLE bet_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_date TEXT NOT NULL,
    venue_code TEXT NOT NULL,
    race_number INTEGER NOT NULL,
    combination TEXT NOT NULL,
    bet_amount INTEGER NOT NULL,
    odds REAL NOT NULL,
    predicted_prob REAL NOT NULL,
    expected_value REAL NOT NULL,
    buy_score REAL NOT NULL,
    result INTEGER,  -- 1=的中, 0=不的中, NULL=未確定
    payout INTEGER,  -- 払戻金額
    profit INTEGER,  -- 純利益
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

#### 10. バックテスト機能の拡充
**ファイル:** `backtest_prediction.py`, 新規UI

**現状:**
- 基本的なバックテストスクリプトは存在
- UIからの実行は未実装

**ToDo:**
```markdown
- [ ] バックテストエンジンの改善
  - [ ] 期間指定での一括実行
  - [ ] 複数戦略の比較機能
  - [ ] パラメータの自動最適化

- [ ] 詳細なレポート生成
  - [ ] 期間別のROI分析
  - [ ] 会場別のパフォーマンス
  - [ ] 資金曲線のプロット
  - [ ] Sharpe Ratio計算

- [ ] UI統合
  - [ ] バックテストタブの追加
  - [ ] パラメータ設定UI
  - [ ] 結果の可視化（グラフ・表）
```

---

#### 11. リスク管理の強化
**新規ファイル:** `src/betting/risk_manager.py`

**目的:**
資金管理の高度化、破産リスクの最小化

**ToDo:**
```markdown
- [ ] RiskManagerクラスの実装
  - [ ] 最大ドローダウンの監視
  - [ ] 1日あたりの損失上限設定
  - [ ] 連敗時の賭け金自動削減
  - [ ] 資金が一定額以下で警告

- [ ] Kelly分数の動的調整
  - [ ] 資金状況に応じた調整
  - [ ] 連勝時: Kelly分数アップ（0.25 → 0.3）
  - [ ] 連敗時: Kelly分数ダウン（0.25 → 0.1）

- [ ] UI統合
  - [ ] リスク管理設定パネル
  - [ ] 資金推移グラフ
  - [ ] 警告・アラート表示
```

---

### 優先度：低（5週間以降）

#### 12. ポートフォリオ最適化の高度化
**新規ファイル:** `src/betting/portfolio_optimizer.py`

**ToDo:**
```markdown
- [ ] 組み合わせ間の相関を考慮した配分
- [ ] モンテカルロシミュレーション
- [ ] Mean-Variance最適化
- [ ] リスクパリティ戦略
```

---

#### 13. 自動購入システム（要慎重検討）
**新規ファイル:** `src/betting/auto_buyer.py`

**注意事項:**
- 公式APIの存在確認が必須
- 利用規約の確認
- 法的リスクの検討

**ToDo:**
```markdown
- [ ] 公式APIの調査・申請
- [ ] 購入APIの実装
- [ ] 自動実行のスケジューリング
- [ ] 緊急停止機能
- [ ] テスト環境での検証
```

---

#### 14. データ収集の自動化・強化
**ファイル:** `src/scraper/`

**ToDo:**
```markdown
- [ ] 定期実行スケジューラー
  - [ ] 毎日のレース結果自動取得
  - [ ] オッズ履歴の保存
  - [ ] エラー時のリトライ・通知

- [ ] 追加データの取得
  - [ ] 天候・風速データ
  - [ ] 水面状況
  - [ ] 選手のコメント（可能なら）

- [ ] データ品質チェック
  - [ ] 欠損値の検出・補完
  - [ ] 異常値の検出
  - [ ] データ整合性チェック
```

---

#### 15. UI/UX改善
**ファイル:** `ui/app.py`, `ui/components/*.py`

**ToDo:**
```markdown
- [ ] レスポンシブデザイン対応
- [ ] ダークモード対応
- [ ] グラフのインタラクティブ化
- [ ] 予想の保存・読み込み機能
- [ ] PDFレポート出力
```

---

## 📊 技術的改善項目

### パフォーマンス最適化
```markdown
- [ ] データベースクエリの最適化
  - [ ] インデックスの追加
  - [ ] N+1問題の解消
  - [ ] クエリキャッシュ

- [ ] 予測処理の高速化
  - [ ] モデル推論の並列化
  - [ ] 特徴量計算のキャッシュ
  - [ ] バッチ処理の最適化
```

### コード品質向上
```markdown
- [ ] ユニットテストの追加
  - [ ] 各モジュールのテストカバレッジ80%以上
  - [ ] CI/CD環境の構築（GitHub Actions）

- [ ] ドキュメント整備
  - [ ] APIドキュメント（docstring完備）
  - [ ] アーキテクチャ図の作成
  - [ ] ユーザーマニュアル作成
```

### エラーハンドリング強化
```markdown
- [ ] ロギング機能の実装
  - [ ] エラーログの記録
  - [ ] デバッグログの追加
  - [ ] ログローテーション

- [ ] 例外処理の統一
  - [ ] カスタム例外クラスの作成
  - [ ] ユーザーフレンドリーなエラーメッセージ
```

---

## 📈 KPI・目標設定

### 短期目標（1ヶ月）
- [ ] オッズAPI実装完了（リアルタイム取得成功率 > 80%）
- [ ] 確率校正によるLog Loss改善（5%以上改善）
- [ ] Stage1モデルのAUC > 0.75達成

### 中期目標（3ヶ月）
- [ ] バックテストでのROI > 110%
- [ ] 購入実績100レース以上記録
- [ ] リスク管理機能完全実装

### 長期目標（6ヶ月）
- [ ] 実運用での継続的プラス収支
- [ ] 完全自動化システムの構築
- [ ] データドリブン投資の確立

---

## 🔗 関連ドキュメント

- [KELLY_BETTING_INTEGRATION.md](KELLY_BETTING_INTEGRATION.md) - Kelly基準統合ガイド
- [ODDS_API_STATUS.md](ODDS_API_STATUS.md) - オッズAPI実装状況
- [README.md](README.md) - プロジェクト概要

---

## 📝 更新履歴

| 日付 | 更新内容 |
|------|----------|
| 2025-11-03 | 初版作成 - Stage1/確率校正/オッズAPI完了時点 |
| 2025-11-03 | Stage2モデル学習機能の実装を優先度高タスクに追加 |
| 2025-11-03 | 優先度高タスクに4項目追加: リアルタイム予想の作りこみ、解析・法則だし・学習機能の簡易化、各競艇場・選手データの解析、公式の場データの組み込み |
| 2025-11-03 | タスク#6（解析機能簡易化）完了 - ANALYSIS_MODULE_GUIDE.md作成 |
| 2025-11-03 | タスク#7（会場・選手データ解析）完了 - VenueAnalyzer/RacerAnalyzer/UI実装完了 |
| 2025-11-03 | タスク#8（公式場データ組み込み）完了 - OfficialVenueScraper/VenueDataManager実装完了 |

---

**最終更新:** 2025-11-03
**次回レビュー:** 2025-11-10（1週間後）
