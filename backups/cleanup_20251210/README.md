# ボートレース予想システム

競艇の過去データを収集・分析し、機械学習による高精度なレース予想を行う統合システムです。

## 🎯 主要機能

### データ収集
- **レーススケジュール収集** - 各会場の開催スケジュールを自動取得
- **レース結果収集** - 過去のレース結果を一括取得（2016年〜現在）
- **レース詳細データ収集** - 出走表、展示タイム、ST時間、モーター情報など
- **決まり手データ収集** - 各レースの決まり手情報
- **天候データ収集** - 気象情報（気温、水温、風向、風速、波高）
- **潮位データ収集** - RDMDB（気象庁）から潮位情報を取得
- **オッズデータ収集** - 三連単オッズを取得

### 機械学習・予測
- **Stage1予測** - ルールベースの基礎予測
- **Stage2予測** - XGBoost/LightGBMによる高精度予測
  - 162パターンの確率予測
  - 選手特徴量（直近N戦成績、会場別成績など）
  - 確率校正（Platt Scaling / Isotonic Regression）
- **SHAP値による解釈** - 予測の根拠を可視化
- **ハイパーパラメータ最適化** - Optunaによる自動チューニング

### ベッティング戦略
- **Kelly基準** - 最適な投資額を計算
- **バックテスト** - 過去データでROIを検証
- **購入履歴管理** - 投資履歴・収支を記録

### UIシステム（Streamlit）
- **ホーム** - データベース統計・ダッシュボード
- **リアルタイム予想** - 未開催レースの予測
- **購入履歴** - ベット履歴・収支管理
- **会場攻略** - 競艇場別傾向分析
- **選手分析** - 選手成績・モーター分析
- **モデル学習** - Stage1/2学習UI
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

#### UIから収集
1. Streamlit UIの「設定・データ管理」タブを選択
2. 期間・会場を指定
3. 「データ収集開始」をクリック

#### コマンドラインから収集（並列化版 - 高速）⭐ 推奨
```bash
# 過去データの不足分を高速取得（並列処理）
python scripts/bulk_missing_data_fetch_parallel.py \
  --start-date 2025-11-01 \
  --end-date 2025-12-04

# オリジナル展示データ収集
python fetch_original_tenji_daily.py
```

**並列化版の性能**:
- 処理速度: 1.5件/秒（従来版の**10-20倍高速**）
- 1000レース: 約10-20分（従来版: 約80分）

詳細は [SCRIPTS_GUIDE.md](SCRIPTS_GUIDE.md) を参照してください。

### 2. モデル学習

#### Stage2モデルの学習
```bash
python tests/train_stage2_with_racer_features.py
```

学習期間: 2024-01-01〜2024-06-30（推奨）
推定時間: 5〜30分（データ量による）

### 3. バックテスト実行
```bash
python tests/backtest_with_racer_features.py
```

テスト期間: 2024-04-01〜2024-06-30
期待ROI改善: +10〜15%

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
│   ├── workflow/          # ワークフロー（並列化版）⭐ NEW
│   ├── scraper/           # データ取得
│   ├── database/          # データベース管理
│   ├── analysis/          # データ分析
│   ├── features/          # 特徴量抽出
│   ├── ml/                # 機械学習
│   ├── training/          # モデル学習
│   ├── prediction/        # 予測エンジン
│   ├── betting/           # 投資戦略
│   └── utils/             # ユーティリティ
├── scripts/               # 実行用スクリプト
│   ├── bulk_missing_data_fetch_parallel.py  # 並列化版データ取得 ⭐
│   └── background_today_prediction.py       # 今日の予測生成
├── ui/                    # Streamlit UI
├── _archive/              # 旧バージョン・実験コード
│   ├── legacy_scripts/    # 旧スクリプト
│   ├── experiments/       # 実験コード
│   └── tests/            # テストコード
├── tests/                 # テストコード
├── config/                # 設定ファイル
├── data/                  # データベース
├── models/                # 学習済みモデル
├── docs/                  # ドキュメント
├── SCRIPTS_GUIDE.md       # スクリプト使い方ガイド ⭐ NEW
└── requirements.txt       # 依存パッケージ
```

---

## 🔧 主要スクリプト

### データ収集
- `fetch_historical_data.py` - 過去データ一括取得
- `fetch_original_tenji_daily.py` - 最新データ取得
- `check_collection_status.py` - 収集状況確認
- `check_db_status.py` - データベース状況確認

### 機械学習
- `tests/train_stage2_with_racer_features.py` - Stage2モデル学習
- `tests/backtest_with_racer_features.py` - バックテスト実行
- `tests/test_racer_features.py` - 選手特徴量テスト
- `tests/test_dataset_with_racer_features.py` - データセットテスト

### ユーティリティ
- `cleanup_project.py` - プロジェクトクリーンアップ
- `backup_project.py` - プロジェクトバックアップ

---

## 📈 パフォーマンス

### データ収集
- 収集速度: 約0.3〜0.5レース/秒
- 対象期間: 2016年〜現在（約13万レース）
- データ品質: ST時間カバー率 70%以上

### 予測精度
- **ベースライン**: AUC 0.70, ROI 100%
- **選手特徴量追加後（目標）**: AUC 0.73〜0.75, ROI 110〜115%
- **全特徴量実装後（予想）**: AUC 0.78〜0.82, ROI 120〜134%

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
- データ期間を短縮（3ヶ月程度）
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

- [新特徴量提案書](docs/new_features_proposal.md) - ROI改善のための特徴量
- [データベーススキーマ](src/database/models.py) - テーブル構造
- [分析ツール](src/analysis/) - バックテスト分析、可視化

---

## 📝 更新履歴

- **2025-12-05**:
  - ✨ **並列化版データ取得** 実装（10-20倍高速化）
  - 📁 プロジェクト大規模整理（329個→7個のスクリプト）
  - 📚 `SCRIPTS_GUIDE.md` 作成、`_archive/` 導入
- **2025-11-13**: プロジェクト大規模整理、分析ツール追加、新特徴量提案
- **2025-11-11**: 選手特徴量（7個）実装、Stage2モデル改良
- **2025-11-09**: ST時間データ補充完了（カバー率70%達成）
- **2025-11-02**: プロジェクト整理、バックテスト機能追加、README作成

---

## ⚠️ 免責事項

本システムは教育・研究目的で開発されています。実際の投資判断は自己責任で行ってください。
投資による損失について、開発者は一切の責任を負いません。

## 📄 ライセンス

個人利用のみ。商用利用禁止。
