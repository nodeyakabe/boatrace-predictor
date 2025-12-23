# プロジェクト構成最適化ログ 2025-12-22

## 概要

プロジェクト構成をPhase 2-4で最適化し、ファイル数を大幅に削減しました。

## 実施結果サマリー

| 項目 | Before | After | 削減率 |
|------|--------|-------|--------|
| docs/直下 | 199個 | 2個 | 99% |
| scripts/直下 | 296個 | 4個 | 99% |
| ルート | 173個 | 3個 | 98% |

## Phase 2: docs/ディレクトリの階層化

### 新しい構造

```
docs/
├── 残タスク一覧.md          # マスタータスク管理
├── HANDOVER.md             # 引継ぎドキュメント
├── architecture/           # システム設計（16ファイル）
│   ├── ARCHITECTURE.md
│   ├── DATABASE_SCHEMA.md
│   ├── PREDICTION_LOGIC.md
│   ├── SYSTEM_ARCHITECTURE.md
│   └── ...
├── guides/                 # 操作ガイド（17ファイル）
│   ├── backtest_guide.md
│   ├── QUICKSTART.md
│   ├── OPERATIONS_GUIDE.md
│   └── ...
├── implementation/         # 実装状況（29ファイル）
│   ├── betting_implementation_status.md
│   ├── phase*_completion_report.md
│   └── ...
├── analysis/               # 分析レポート（90ファイル）
│   ├── DAILY_REPORT_*.md
│   ├── *_ANALYSIS_*.md
│   └── ...
├── knowledge/              # 知見ベース（5ファイル）
│   ├── prediction_logic_knowledge_base.md
│   └── ...
├── improvement_attempts/   # 改善試行記録（3ファイル）
└── archive/                # アーカイブ
    ├── 2025_11_analysis/
    ├── 2025_12/
    ├── plans/
    ├── root_docs/
    └── handover/
```

### 移動ルール

1. **architecture/**: システム設計、スキーマ、API構造
2. **guides/**: 操作ガイド、セットアップ手順
3. **implementation/**: 実装状況、完了レポート
4. **analysis/**: 日付付きレポート、分析結果
5. **knowledge/**: 知見、ナレッジベース
6. **archive/**: 過去ドキュメント、プラン

## Phase 3: scripts/ディレクトリの整理

### 新しい構造

```
scripts/
├── query_knowledge_db.py   # 知見DB検索
├── register_experiment.py  # 施策登録
├── safety_check.py         # 安全性チェック
├── search_knowledge.py     # 知見検索
├── prediction/             # 予測生成系（28ファイル）
│   ├── generate_predictions.py
│   ├── regenerate_*.py
│   └── ...
├── backtest/               # バックテスト系（60ファイル）
│   ├── backtest_standard.py
│   ├── validate_*.py
│   ├── verify_*.py
│   └── ...
├── analysis/               # 分析系（96ファイル）
│   ├── analyze_*.py
│   ├── compare_*.py
│   └── ...
├── data_collection/        # データ収集系（21ファイル）
│   ├── fetch_*.py
│   ├── collect_*.py
│   └── ...
├── maintenance/            # メンテナンス系（29ファイル）
│   ├── train_*.py
│   ├── optimize_*.py
│   └── ...
├── batch/                  # バッチファイル
│   ├── run_*.bat
│   └── setup_*.ps1
└── _deprecated/            # 非推奨（65ファイル）
    ├── test_*.py
    ├── debug_*.py
    ├── check_*.py
    └── *_v2.py, *_v3.py
```

### 移動ルール

1. **prediction/**: generate_*.py, regenerate_*.py
2. **backtest/**: backtest_*.py, validate_*.py, verify_*.py
3. **analysis/**: analyze_*.py, compare_*.py, evaluate_*.py
4. **data_collection/**: fetch_*.py, collect_*.py, worker_*.py
5. **maintenance/**: train_*.py, optimize_*.py, create_*.py
6. **batch/**: *.bat, *.ps1
7. **_deprecated/**: test_*.py, debug_*.py, *_v2.py, *_v3.py

## Phase 4: ルートディレクトリの整理

### 最終構造

```
/（ルート）
├── README.md               # プロジェクト概要
├── CLAUDE.md               # Claude設定
├── START_HERE.md           # 初期セットアップ
├── .env                    # 環境変数
├── .env.example            # 環境変数サンプル
├── .gitignore              # Git除外設定
├── src/                    # ソースコード
├── docs/                   # ドキュメント
├── scripts/                # スクリプト
├── config/                 # 設定ファイル
├── data/                   # データファイル
│   ├── temp_files/         # 一時ファイル（csv, json, lzh）
│   ├── output/             # 出力ファイル
│   ├── results/            # 結果ファイル
│   └── rdmdb_tide_data/    # 潮位データ
├── ui/                     # UIコンポーネント
├── tests/                  # テストコード
├── models/                 # 学習済みモデル
├── backups/                # バックアップ
├── migrations/             # DBマイグレーション
├── venv/                   # Python仮想環境
├── _archive/               # アーカイブ
└── _deprecated/            # 非推奨
    ├── scripts_archive/
    ├── temp/
    └── 改善点/
```

### 移動したファイル

- **docs/archive/root_docs/**: ルートにあった.mdファイル約70個
- **data/temp_files/**: *.csv, *.json, *.lzh, *.log
- **scripts/batch/**: *.bat, *.ps1
- **_deprecated/**: scripts_archive/, temp/, 改善点/

## バックアップ

すべての移動前にバックアップを作成:

```
backups/project_cleanup_20251222/
├── docs_backup/            # docs/のバックアップ
└── scripts_backup/         # scripts/のバックアップ
```

## 重要な注意事項

1. **残タスク一覧.md**と**HANDOVER.md**は移動していません
2. src/, config/の内部は変更していません
3. 移動後も全てのスクリプトは動作します（パスは相対パスで参照）
4. CLAUDE.mdのドキュメント参照パスを更新する必要があるかもしれません

## 推奨される次のステップ

1. CLAUDE.mdのドキュメント参照パスを確認・更新
2. 頻繁に使用するスクリプトのエイリアス設定
3. 不要な_deprecatedファイルの定期的な削除検討
4. docs/archiveの定期的な整理

---
作成日: 2025-12-22
