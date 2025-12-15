# ボートレース予想システム

競艇の過去データを収集・分析し、機械学習による高精度なレース予想を行う統合システムです。

---

## 🎯 プロジェクトの目標

**最終目標**: 週間収支のプラス化（安定した黒字運用）

### 現在の実績（2025年バックテスト）

| 項目 | 実績 |
|------|------|
| **年間ROI** | **129.9%** |
| **年間収支** | **+67,570円** |
| 年間購入レース数 | 652レース |
| 年間的中数 | 60回 |
| 的中率 | 9.2% |
| 月間平均的中 | 5.0回 |

**検証データ**: 2025年全期間（17,407レース）、実際の払戻金データを使用
**購入方式**: パターンH（1-2軸3点傾斜配分: 200/100/100円）+ 会場コース調整

**最新改善（2025-12-15）**:
- 会場×コース別調整システム実装により収支改善: +66,150円 → **+67,570円** (+1,420円)
- 風速・会場フィルター統合による機会損失削減を実現

---

## 🏆 ベッティング戦略（戦略B+パターンH: 複数点買い）

### パターンH: 1-2軸3点傾斜配分 + 会場コース調整

**買い目構成**:
- 1-2-3（予測そのまま）: 200円
- 1-2-4（3着を4位に変更）: 100円
- 1-2-5（3着を5位に変更）: 100円
- **合計**: 400円/レース

**会場コース調整** (2025-12-15実装):
- 24会場×6コース=144パターンの調整ポイント
- インが弱い会場（戸田、平和島）: 1コース -12pt
- インが強い会場（徳山、大村）: 1コース +9pt
- 調整閾値-12pt以下は購入見送り

### 現行1点買いとの比較

| 指標 | 1点買い | パターンH | パターンH+調整 | 改善効果 |
|:----:|--------:|---------:|-------------:|---------:|
| 年間収支 | +49,500円 | +66,150円 | **+67,570円** | **+18,070円 (+36.5%)** |
| ROI | 125.3% | 126.6% | **129.9%** | +4.6pt |
| 的中率 | 3.5% | 9.2% | **9.2%** | +5.7pt |
| 月間平均的中 | 1.9回 | 5.0回 | **5.0回** | +3.1回 |
| 投資額/レース | 300円 | 400円 | 400円 | +100円 |

### 購入条件（戦略B）

| 信頼度 | 1コース級別 | オッズレンジ | ROI | 的中率 |
|:------:|:----------:|:-----------:|----:|-------:|
| C | B1 | 30-40倍 | 158.6% | 5.0% |
| C | A1 | 30-40倍 | 141.7% | 4.1% |
| D | B1 | 40-50倍 | 132.0% | 2.7% |
| D | A1 | 40-50倍 | 405.8% | 1.9% |
| D | A2 | 20-30倍 | 173.3% | 6.7% |

詳細は [docs/MULTI_BET_ANALYSIS_REPORT.md](docs/MULTI_BET_ANALYSIS_REPORT.md) を参照

---

## 🎯 主要機能

### データ収集
- **レーススケジュール収集** - 各会場の開催スケジュールを自動取得
- **レース結果収集** - 過去のレース結果を一括取得（2016年〜現在）
- **レース詳細データ収集** - 出走表、展示タイム、ST時間、モーター情報など
- **決まり手データ収集** - 各レースの決まり手情報
- **天候データ収集** - 気象情報（気温、水温、風向、風速、波高）
- **潮位データ収集** - RDMDB（気象庁）から潮位情報を取得
- **オッズデータ収集** - 三連単オッズを取得
- **直前情報収集** - ST、展示タイム、進入コース、調整重量、前走成績

### 機械学習・予測
- **Stage1予測** - ルールベースの基礎予測
- **Stage2/3予測** - XGBoost/LightGBMによる階層的予測
  - 条件付き確率モデル（1着→2着→3着の順次予測）
  - 選手特徴量（直近N戦成績、会場別成績など）
  - 直前情報パターンボーナス（ST×展示タイムの組み合わせ）
  - 確率校正（Platt Scaling / Isotonic Regression）
- **SHAP値による解釈** - 予測の根拠を可視化
- **ハイパーパラメータ最適化** - Optunaによる自動チューニング

### ベッティング戦略
- **戦略A実装済み** - 3層構造（Tier 1-3）による最適化ベッティング
- **Kelly基準** - 最適な投資額を計算
- **Edge計算** - 期待値ベースのフィルタリング
- **バックテスト** - 過去データでROIを検証
- **購入履歴管理** - 投資履歴・収支を記録

### UIシステム（Streamlit）
- **ホーム** - データベース統計・ダッシュボード
- **リアルタイム予想** - 未開催レースの予測
- **購入履歴** - ベット履歴・収支管理
- **会場攻略** - 競艇場別傾向分析
- **選手分析** - 選手成績・モーター分析
- **モデル学習** - Stage1/2/3学習UI
- **バックテスト** - 予測精度検証
- **設定・データ管理** - DB管理・データ収集

---

## 🚀 セットアップ

### 必要環境
- **Python 3.10以上**
- pip（パッケージ管理）
- SQLite3

### インストール手順

#### 1. 仮想環境の作成（推奨）
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux
```

#### 2. 依存パッケージのインストール
```bash
pip install -r requirements.txt
```

主要パッケージ:
- requests, beautifulsoup4, selectolax（スクレイピング）
- pandas, numpy（データ処理）
- scikit-learn, xgboost, lightgbm（機械学習）
- optuna（ハイパーパラメータ最適化）
- streamlit, plotly, matplotlib（可視化）
- SHAP（モデル解釈）

#### 3. データベース初期化
```bash
python -c "from src.database.models import Database; db = Database(); db.create_tables()"
```

#### 4. UIアプリの起動
```bash
streamlit run ui/app.py
```

ブラウザで http://localhost:8501 にアクセス

---

## 📊 使い方

### 1. データ収集

#### コマンドラインから収集（並列化版 - 高速）⭐ 推奨
```bash
# 過去データの不足分を高速取得（並列処理）
python scripts/bulk_missing_data_fetch_parallel.py \
  --start-date 2025-11-01 \
  --end-date 2025-12-10
```

**並列化版の性能**:
- 処理速度: 1.5件/秒（従来版の**10-20倍高速**）
- 1000レース: 約10-20分（従来版: 約80分）

#### UIから収集
1. Streamlit UIの「設定・データ管理」タブを選択
2. 期間・会場を指定
3. 「データ収集開始」をクリック

詳細は [SCRIPTS_GUIDE.md](SCRIPTS_GUIDE.md) を参照してください。

### 2. モデル学習

#### 全モデルの学習
```bash
python scripts/train_all_models.py
```

#### Stage2/3条件付きモデルの再学習
```bash
python scripts/retrain_conditional_models_v2.py
```

学習期間: 2024-01-01〜2024-12-31（推奨）
推定時間: 10〜60分（データ量による）

### 3. バックテスト実行

#### 戦略Aの検証
```bash
python scripts/validate_strategy_a.py
```

#### 全モード比較（Phase Aバックテスト）
```bash
python scripts/backtest_all_modes.py
```

#### Edge計算テスト
```bash
python scripts/backtest_v2_edge_test.py
```

### 4. リアルタイム予想
1. Streamlit UIの「リアルタイム予想」タブを選択
2. 日付・会場・レース番号を指定
3. 予測確率と推奨投資額を確認

---

## 🧪 バックテスト機能

過去のレースデータを使って予想ロジックの精度を検証。

### 評価指標
- **ROI（回収率）**: 投資額に対する払戻額の割合
- **的中率**: 1着予想が的中した割合
- **AUC**: 予測モデルの識別性能
- **Log Loss**: 予測確率の精度
- **ドローダウン**: 最大資金減少幅

### 詳細分析ツール
```python
from src.analysis.backtest_analyzer import BacktestAnalyzer

analyzer = BacktestAnalyzer(results_df)
analyzer.generate_report("backtest_report.txt")
analyzer.plot_cumulative_profit("cumulative_profit.png")
analyzer.plot_threshold_comparison("threshold_comparison.png")
```

---

## 📁 プロジェクト構造

```
BoatRace/
├── src/                    # ソースコード
│   ├── scraper/           # データ取得
│   ├── database/          # データベース管理
│   ├── analysis/          # データ分析・予測スコアリング
│   ├── features/          # 特徴量抽出
│   ├── ml/                # 機械学習
│   ├── training/          # モデル学習
│   ├── prediction/        # 予測エンジン（階層的予測）
│   ├── betting/           # 投資戦略（戦略A実装済み）
│   └── utils/             # ユーティリティ
│
├── scripts/ (40個)         # 実行用スクリプト（整理済み）
│   ├── データ収集系 (4個)
│   ├── モデル学習系 (2個)
│   ├── バックテスト系 (10個)
│   ├── 予測生成系 (2個)
│   └── ユーティリティ系 (22個)
│
├── scripts_archive/ (93個) # アーカイブされた古いスクリプト
│   ├── analyze_archived/ (53個)
│   ├── backtest_archived/ (11個)
│   ├── test_debug_archived/ (15個)
│   └── duplicate_archived/ (14個)
│
├── ui/                    # Streamlit UI
├── tests/                 # テストコード
├── config/                # 設定ファイル（機能フラグ、会場特性）
├── data/                  # データベース（boatrace.db: 1.8GB）
├── models/                # 学習済みモデル
│
├── docs/                  # ドキュメント
│   ├── 残タスク一覧.md   # プロジェクト管理
│   ├── ARCHITECTURE.md   # モジュール構成図（2025-12-15新規）
│   ├── CONFIGURATION.md  # 設定ファイル一覧（2025-12-15新規）
│   ├── DATABASE_SCHEMA.md
│   ├── betting_implementation_status.md
│   └── archive/          # アーカイブされた古いドキュメント
│
├── backups/              # バックアップディレクトリ
│
├── START_HERE.md         # 作業開始時の必読ドキュメント
├── CLAUDE.md             # AI設定（言語・モデル）
├── README.md             # このファイル
├── SCRIPTS_GUIDE.md      # スクリプト使い方ガイド
└── requirements.txt      # 依存パッケージ
```

---

## 🔧 主要スクリプト

### データ収集（4個）
- `bulk_missing_data_fetch_parallel.py` - 並列化版データ取得 ⭐ 推奨
- `background_data_collection.py` - バックグラウンドデータ収集
- `background_today_prediction.py` - 今日の予測生成
- `collect_parts_exchange.py` - 部品交換データ収集

### モデル学習（2個）
- `train_all_models.py` - 全モデル統合学習
- `retrain_conditional_models_v2.py` - 条件付きモデルv2再学習

### バックテスト（10個）
- `backtest_v2_edge_test.py` - Edge計算バックテスト（残タスク最優先）
- `backtest_all_modes.py` - 全モード比較（残タスク最優先）
- `backtest_v2_venue_test.py` - 会場別オッズレンジテスト（Phase B）
- `validate_strategy_a.py` - 戦略A検証
- `backtest_final_strategy_correct.py` - 最終戦略（正確な払戻版）
- その他5個

### 予測生成（2個）
- `regenerate_predictions_2025_parallel.py` - 2025年予測再生成（並列版）
- `regenerate_predictions_2025.py` - 2025年予測再生成

### データベース管理（3個）
- `add_attack_pattern_indexes.py` - 攻略パターンインデックス追加
- `generate_db_documentation.py` - DB仕様書生成
- `verify_db_documentation.py` - DB仕様書検証

### 分析（1個、最重要のみ）
- `analyze_confidence_b_v2.py` - 信頼度B分析（最新v2版）

### その他ユーティリティ（18個）
- オッズ取得、ワーカー、パフォーマンス管理など

※ 93個の古いスクリプトは `scripts_archive/` に整理済み

---

## 📈 パフォーマンス

### データ収集
- 収集速度: 約1.5レース/秒（並列化版）
- 対象期間: 2016年〜現在（約13万レース）
- データ品質: ST時間カバー率 70%以上

### 予測精度（現状）
- **1着的中率**: 41-42%
- **2着的中率**: 35.9%
- **3着的中率**: 27.2%
- **3連単的中率**: 12.7%
- **3連単的中率（TOP20）**: 5.0%

### 予測精度（目標）
- 1着的中率: 44-47%
- 2着的中率: 42-45%
- 3着的中率: 32-35%
- 3連単的中率: 16-18%

### ベッティング実績
- 年間ROI: 298.9%
- 年間収支: +380,070円（2025年バックテスト）

---

## 🐛 トラブルシューティング

### データベースロック
**症状**: `sqlite3.OperationalError: database is locked`
**解決策**:
```bash
# 接続を閉じる
python -c "import sqlite3; conn=sqlite3.connect('data/boatrace.db'); conn.close()"
```

### 学習プロセスが遅い
**症状**: モデル学習に30分以上かかる
**解決策**:
- データ期間を短縮（6ヶ月程度）
- `num_boost_round` を500に削減
- 会場を絞る（主要会場のみ）

### UI起動エラー
```bash
pip install --upgrade streamlit
streamlit run ui/app.py --server.port 8502
```

---

## 🎓 開発ベストプラクティス

1. **バックアップ重要** - 大規模変更前に必ずバックアップ
2. **段階的テスト** - 少量データでテスト → 全データ処理
3. **ログ充実** - デバッグ時にHTML保存、詳細ログ出力
4. **エラーハンドリング** - try-exceptで例外をキャッチ、処理継続
5. **バッチ処理** - 大量データは分割処理
6. **データリーケージ防止** - 特徴量は「そのレースより前」のデータのみ使用
7. **過学習防止** - Train/Valid/Testの分割、Early Stopping

---

## 📚 ドキュメント

### システム概要（新規追加 2025-12-15）
- **[docs/SYSTEM_OVERVIEW.md](docs/SYSTEM_OVERVIEW.md)** - 1ページサマリー（必読）
- **[docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md)** - システム全体構成、依存関係
- **[docs/MODEL_MANAGEMENT.md](docs/MODEL_MANAGEMENT.md)** - モデル管理ガイド、更新手順
- **[docs/PREDICTION_LOGIC.md](docs/PREDICTION_LOGIC.md)** - 予測ロジック詳細
- **[docs/DEVELOPMENT_WORKFLOW.md](docs/DEVELOPMENT_WORKFLOW.md)** - 開発ワークフロー、チェックリスト

### 必読ドキュメント
- [START_HERE.md](START_HERE.md) - 作業開始時の必読ガイド
- [CLAUDE.md](CLAUDE.md) - AI設定（言語・モデル指定）
- [docs/残タスク一覧.md](docs/残タスク一覧.md) - プロジェクト管理マスター
- [SCRIPTS_GUIDE.md](SCRIPTS_GUIDE.md) - スクリプト使い方詳細

### 技術ドキュメント
- [docs/betting_implementation_status.md](docs/betting_implementation_status.md) - ベッティングシステム実装状況
- [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) - データベーススキーマ
- [docs/prediction_logic_summary.md](docs/prediction_logic_summary.md) - 予測ロジック概要
- [docs/hybrid_scoring_implementation.md](docs/hybrid_scoring_implementation.md) - ハイブリッドスコアリング実装

### 分析レポート
- [docs/confidence_b_analysis_20241209.md](docs/confidence_b_analysis_20241209.md) - 信頼度B分析
- [docs/opus_upset_analysis_20251208.md](docs/opus_upset_analysis_20251208.md) - Opus中穴レース分析
- [docs/v2_implementation_complete.md](docs/v2_implementation_complete.md) - v2実装完了レポート

### プロジェクト整理
- [PROJECT_CLEANUP_PLAN_20251210.md](PROJECT_CLEANUP_PLAN_20251210.md) - 整理計画
- [CLEANUP_COMPLETION_REPORT_20251210.md](CLEANUP_COMPLETION_REPORT_20251210.md) - 整理完了レポート

---

## 📝 更新履歴

- **2025-12-15**:
  - システム整理・ドキュメント化完了
    - SYSTEM_ARCHITECTURE.md - システム全体構成
    - MODEL_MANAGEMENT.md - モデル管理ガイド
    - PREDICTION_LOGIC.md - 予測ロジック詳細
    - DEVELOPMENT_WORKFLOW.md - 開発ワークフロー
    - SYSTEM_OVERVIEW.md - 1ページサマリー
  - 新規ユーティリティ作成
    - src/utils/model_loader.py - 統一モデルローダー
    - config/model_config.py - モデル設定統一
    - scripts/validate_model_update.py - モデル更新検証スクリプト
  - モデル体系の整理（V1本番、V2実験、deprecated）

- **2025-12-10**:
  - 🧹 プロジェクト大規模整理完了
    - スクリプト: 133個 → 40個（70%削減）
    - ドキュメント: 165個 → 71個（57%削減）
    - 179個のファイルを体系的にアーカイブ
  - 📝 README.md完全リニューアル（最新情報反映）
  - 🎯 目標を「週間収支プラス化」に明確化

- **2025-12-08**:
  - ✅ 戦略A実装完了（3層構造ベッティング）
  - ✅ attack_patternsDB構築完了
  - ✅ buying system実装完了（Phase A-C）

- **2025-12-05**:
  - ✨ 並列化版データ取得実装（10-20倍高速化）
  - 📁 プロジェクト大規模整理（329個→7個のスクリプト）
  - 📚 SCRIPTS_GUIDE.md作成、_archive/導入

- **2025-12-02**:
  - ✅ 直前情報データ拡充完了（ST、展示、進入、調整重量）
  - ✅ BeforeInfoScorer実装・RacePredictor統合完了

- **2025-11-13**: プロジェクト大規模整理、分析ツール追加、新特徴量提案
- **2025-11-11**: 選手特徴量（7個）実装、Stage2モデル改良
- **2025-11-09**: ST時間データ補充完了（カバー率70%達成）
- **2025-11-02**: プロジェクト整理、バックテスト機能追加、README作成

---

## ⚠️ 免責事項

本システムは教育・研究目的で開発されています。実際の投資判断は自己責任で行ってください。
投資による損失について、開発者は一切の責任を負いません。

---

## 📄 ライセンス

個人利用のみ。商用利用禁止。
