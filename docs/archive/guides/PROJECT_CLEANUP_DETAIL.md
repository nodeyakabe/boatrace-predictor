# プロジェクト整理作業の詳細記録

**実施日**: 2025-12-22
**目的**: 別PCで同じ整理状態を再現するための詳細手順

---

## 📋 整理作業の全体像

### 整理前の状態

| ディレクトリ | ファイル数 | 問題点 |
|------------|-----------|--------|
| **ルート直下** | 173ファイル | .md, .pyが散在 |
| **docs/** | 199 .mdファイル | 日付付きドキュメントが大量 |
| **scripts/** | 296 .pyファイル | 重複スクリプト多数 |

### 整理後の状態

| ディレクトリ | ファイル数 | 変化 |
|------------|-----------|------|
| **ルート直下** | 3ファイル | **-98%** |
| **docs/** | 4ファイル | **-98%** |
| **scripts/** | 4ファイル | **-99%** |

---

## 🔄 Phase 1: マスタードキュメントの一元化

### 実施内容

#### 1. 残タスク一覧.mdの修正

**ファイル**: `docs/残タスク一覧.md`

**変更内容**:
- DB実測値を反映（2022年27.3%, 2023-2025年0%）
- 過去の誤った情報を削除
- 「緊急修正版」として更新日を明記

#### 2. HANDOVER.mdの新規作成

**ファイル**: `docs/HANDOVER.md`

**内容**:
- セッション間の引継ぎ情報を一元化
- 過去ドキュメントの誤情報を注意喚起
- DB確認コマンドを記載
- 常に最新状態に上書き更新（日付付きにしない）

**古いHANDOVERの処理**:
```bash
# 古いHANDOVERをarchiveへ移動
mkdir -p docs/archive/handover
mv docs/HANDOVER_20251221.md docs/archive/handover/
mv docs/HANDOVER_20251222.md docs/archive/handover/
```

#### 3. CLAUDE.mdの簡素化

**ファイル**: `CLAUDE.md`

**変更内容**:
- 参照ドキュメントを3つに限定
  1. `docs/残タスク一覧.md` - 現在の状態
  2. `docs/HANDOVER.md` - 前回の作業内容
  3. `docs/architecture/DATABASE_SCHEMA.md` - DB構造
- 日付付きドキュメントは過去ログと明記
- セッション開始時の確認を3ステップに簡素化

---

## 🔄 Phase 2: docs/ディレクトリの階層化

### 階層構造の作成

```bash
# 階層ディレクトリ作成
mkdir -p docs/architecture
mkdir -p docs/guides
mkdir -p docs/implementation
mkdir -p docs/analysis
mkdir -p docs/daily_reports
mkdir -p docs/knowledge
mkdir -p docs/improvement_attempts
mkdir -p docs/lessons_learned
mkdir -p docs/templates
mkdir -p docs/checklists
mkdir -p docs/archive
```

### ファイルの移動ルール

#### architecture/ へ移動

**対象**: システム設計、スキーマ、API構造

```bash
mv docs/ARCHITECTURE.md docs/architecture/
mv docs/DATABASE_SCHEMA.md docs/architecture/
mv docs/PREDICTION_LOGIC.md docs/architecture/
mv docs/SYSTEM_*.md docs/architecture/
mv docs/API_*.md docs/architecture/
# ... 計16ファイル
```

#### guides/ へ移動

**対象**: 操作ガイド、セットアップ手順

```bash
mv docs/SCRIPTS_GUIDE.md docs/guides/
mv docs/backtest_guide.md docs/guides/
mv docs/QUICKSTART.md docs/guides/
mv docs/*_GUIDE.md docs/guides/
# ... 計21ファイル
```

#### implementation/ へ移動

**対象**: 実装状況、完了レポート

```bash
mv docs/betting_implementation_status.md docs/implementation/
mv docs/phase*_completion_report.md docs/implementation/
mv docs/*_STATUS.md docs/implementation/
mv docs/*_implementation_*.md docs/implementation/
# ... 計29ファイル
```

#### analysis/ へ移動

**対象**: 日付付きレポート、分析結果

```bash
mv docs/DAILY_REPORT_*.md docs/analysis/
mv docs/*_ANALYSIS_*.md docs/analysis/
mv docs/*_20251[0-9]*.md docs/analysis/
mv docs/*_REPORT_*.md docs/analysis/
# ... 計90ファイル
```

#### archive/ へ移動

**対象**: 過去ドキュメント、完了済みプラン

```bash
mkdir -p docs/archive/2025_11_analysis
mkdir -p docs/archive/2025_12
mkdir -p docs/archive/plans
mkdir -p docs/archive/root_docs

mv docs/*_COMPLETED.md docs/archive/
mv docs/*_PLAN.md docs/archive/plans/
mv docs/OLD_*.md docs/archive/
# ... 過去ドキュメント多数
```

### docs/README.mdの作成

**ファイル**: `docs/README.md`

**内容**: docs/ディレクトリの索引として機能

---

## 🔄 Phase 3: scripts/ディレクトリの整理

### 階層構造の作成

```bash
# 階層ディレクトリ作成
mkdir -p scripts/prediction
mkdir -p scripts/backtest
mkdir -p scripts/analysis
mkdir -p scripts/data_collection
mkdir -p scripts/maintenance
mkdir -p scripts/batch
mkdir -p scripts/templates
mkdir -p scripts/_deprecated
```

### ファイルの移動ルール

#### prediction/ へ移動

**対象**: 予測生成系スクリプト

```bash
mv scripts/generate_*.py scripts/prediction/
mv scripts/regenerate_*.py scripts/prediction/
mv scripts/universal_prediction_generator.py scripts/prediction/
# ... 計28ファイル
```

#### backtest/ へ移動

**対象**: バックテスト系スクリプト

```bash
mv scripts/backtest_*.py scripts/backtest/
mv scripts/validate_*.py scripts/backtest/
mv scripts/verify_*.py scripts/backtest/
# ... 計68ファイル
```

#### analysis/ へ移動

**対象**: 分析系スクリプト

```bash
mv scripts/analyze_*.py scripts/analysis/
mv scripts/compare_*.py scripts/analysis/
mv scripts/evaluate_*.py scripts/analysis/
# ... 計99ファイル
```

#### data_collection/ へ移動

**対象**: データ収集系スクリプト

```bash
mv scripts/fetch_*.py scripts/data_collection/
mv scripts/collect_*.py scripts/data_collection/
mv scripts/bulk_*.py scripts/data_collection/
mv scripts/worker_*.py scripts/data_collection/
# ... 計35ファイル
```

#### maintenance/ へ移動

**対象**: メンテナンス系スクリプト

```bash
mv scripts/train_*.py scripts/maintenance/
mv scripts/retrain_*.py scripts/maintenance/
mv scripts/optimize_*.py scripts/maintenance/
mv scripts/cleanup_*.py scripts/maintenance/
# ... 計36ファイル
```

#### _deprecated/ へ移動

**対象**: テスト・デバッグ・旧バージョンスクリプト

```bash
mv scripts/test_*.py scripts/_deprecated/
mv scripts/debug_*.py scripts/_deprecated/
mv scripts/check_*.py scripts/_deprecated/
mv scripts/*_v2.py scripts/_deprecated/
mv scripts/*_v3.py scripts/_deprecated/
mv scripts/old_*.py scripts/_deprecated/
# ... 計96ファイル
```

### scripts/直下に残すファイル

**知見管理ツールのみ残す**:
- `search_knowledge.py` - 知見DB検索
- `register_experiment.py` - 施策登録
- `query_knowledge_db.py` - 知見DB詳細検索
- `safety_check.py` - 安全性チェック

### scripts/README.mdの作成

**ファイル**: `scripts/README.md`

**内容**: scripts/ディレクトリの索引、推奨スクリプト明記

---

## 🔄 Phase 4: ルートディレクトリの整理

### ルートに残すファイル（3つのみ）

```
/
├── README.md         # プロジェクト概要
├── CLAUDE.md         # AI設定
└── START_HERE.md     # 作業開始ガイド
```

### .mdファイルの移動

**対象**: すべてのルート直下.mdファイル（上記3つ除く）

```bash
# archiveディレクトリ作成
mkdir -p _archive/root_docs

# すべての.mdをarchiveへ移動（3つ除く）
find . -maxdepth 1 -name "*.md" \
    ! -name "README.md" \
    ! -name "CLAUDE.md" \
    ! -name "START_HERE.md" \
    -exec mv {} _archive/root_docs/ \;

# docs/へ移動すべきものは docs/ へ
# 例: IMPROVEMENT_PLAN.md, OPTIMIZATION_COMPLETE.md など
```

### .pyファイルの移動

**対象**: すべてのルート直下.pyファイル

```bash
# archiveディレクトリ作成
mkdir -p _deprecated/root_scripts

# すべての.pyをarchiveへ移動
find . -maxdepth 1 -name "*.py" \
    -exec mv {} _deprecated/root_scripts/ \;

# scripts/へ移動すべきものは scripts/ へ
# 例: backtest_*.py, analyze_*.py など
```

### その他ファイルの移動

```bash
# .lzhファイル
mkdir -p _archive/compressed
mv *.lzh _archive/compressed/ 2>/dev/null

# 古いデータファイル
mkdir -p _archive/old_data
mv missing_*.csv _archive/old_data/ 2>/dev/null
```

---

## 🔒 バックアップの作成

### プロジェクト全体のバックアップ

```bash
# バックアップディレクトリ作成
mkdir -p backups/project_cleanup_20251222

# docs/のバックアップ
cp -r docs/ backups/project_cleanup_20251222/docs_backup/

# scripts/のバックアップ
cp -r scripts/ backups/project_cleanup_20251222/scripts_backup/

# ルートファイルのバックアップ
mkdir -p backups/project_cleanup_20251222/root_backup
cp *.md *.py backups/project_cleanup_20251222/root_backup/ 2>/dev/null
```

### バックアップからの復元方法

```bash
# docs/を復元
rm -rf docs/
cp -r backups/project_cleanup_20251222/docs_backup/ docs/

# scripts/を復元
rm -rf scripts/
cp -r backups/project_cleanup_20251222/scripts_backup/ scripts/
```

---

## 📝 移動ログの作成

**ファイル**: `docs/PROJECT_CLEANUP_LOG_20251222.md`

**内容**:
- 移動したファイルの一覧
- ディレクトリ構造の変更
- バックアップの場所
- 復元方法

---

## 🔄 Git管理の確認

### .gitignoreの設定

```bash
# .gitignore に以下を確認
cat .gitignore | grep -E "data/|models/|backups/|venv/|__pycache__/"
```

**期待される内容**:
```
data/
models/
backups/
venv/
__pycache__/
logs/
*.db
*.sqlite
```

### Git管理対象の確認

```bash
# 管理対象ファイル
git ls-files | head -20

# 管理対象外ファイル
git status --ignored
```

---

## ✅ 検証チェックリスト

整理作業完了後に以下を確認：

- [ ] ルート直下に.mdファイルは3つのみ（README.md, CLAUDE.md, START_HERE.md）
- [ ] ルート直下に.pyファイルは0個
- [ ] `docs/`直下に.mdファイルは4つのみ（残タスク一覧.md, HANDOVER.md, README.md, LOG）
- [ ] `docs/architecture/`, `docs/guides/`等のディレクトリが存在
- [ ] `scripts/`直下に.pyファイルは4つのみ（知見管理ツール）
- [ ] `scripts/prediction/`, `scripts/backtest/`等のディレクトリが存在
- [ ] `_archive/root_docs/`にルート直下の古い.mdファイルが存在
- [ ] `_deprecated/root_scripts/`にルート直下の古い.pyファイルが存在
- [ ] `backups/project_cleanup_20251222/`にバックアップが存在
- [ ] `docs/PROJECT_CLEANUP_LOG_20251222.md`が存在
- [ ] `docs/README.md`と`scripts/README.md`が存在

---

## 🆘 トラブルシューティング

### 問題: 古いパスでスクリプトが実行できない

**原因**: スクリプトが移動されている

**解決策**:
1. `scripts/README.md`で新しいパスを確認
2. または`find scripts -name "スクリプト名.py"`で検索

### 問題: インポートエラーが発生

**原因**: 相対インポートのパスが変更された可能性

**解決策**:
1. `src/`配下のコードは変更されていないため、問題なし
2. `scripts/`内のスクリプトは絶対インポートを使用

### 問題: ドキュメントが見つからない

**原因**: ドキュメントが移動されている

**解決策**:
1. `docs/README.md`で新しいパスを確認
2. または`docs/PROJECT_CLEANUP_LOG_20251222.md`で移動履歴を確認

---

**作成日**: 2025-12-22
**作成者**: Claude Code
