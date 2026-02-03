# ドキュメント整理提案書

**作成日**: 2026-01-14
**目的**: プロジェクト資料の整理と最新情報へのアクセス改善

---

## 現状分析

### 問題点

1. **日付付きドキュメントが58ファイル存在**
   - 例: `*_20251220.md`, `*_20251221.md`等
   - HANDOVERによると「過去ログ」であり最新情報ではない

2. **analysisディレクトリに112ファイル**
   - 多くが過去の分析レポート
   - 最新の有効な情報との区別が困難

3. **参照すべきドキュメントが不明確**
   - CLAUDE.mdには明記されているが、実際のファイル数が多い

### 整理済みの構造（良い点）

✅ docs/直下は4ファイルのみに整理済み
- 残タスク一覧.md
- HANDOVER.md
- README.md
- PROJECT_CLEANUP_LOG_20251222.md

✅ サブディレクトリは階層化済み
- architecture/ - システム設計
- guides/ - 操作ガイド
- analysis/ - 分析レポート
- performance/ - 年度別成績
- presets/ - 購入条件
- improvement_attempts/ - 不採用案
- archive/ - アーカイブ

---

## 整理方針

### 原則

1. **最新情報は限定されたファイルのみに集約**
   - 残タスク一覧.md
   - HANDOVER.md
   - architecture/以下の仕様書
   - performance/以下の最新成績
   - presets/以下の購入条件

2. **日付付きドキュメントは過去ログとして扱う**
   - 参考情報として保持
   - archiveに移動するか、明確に「過去ログ」とマーク

3. **重複情報の削除**
   - 同じ内容が複数ファイルに存在する場合、最新版のみ残す

---

## 具体的な整理案

### Phase 1: 日付付きドキュメントの整理

**対象**: 58ファイル

**方針**:
```bash
# 2025年12月以前の日付付きファイルをarchiveに移動
mkdir -p docs/archive/historical_analysis_2025
mv docs/analysis/*_202512*.md docs/archive/historical_analysis_2025/
mv docs/analysis/*_202511*.md docs/archive/historical_analysis_2025/
# ... (以下同様)

# 2026年1月の日付付きファイルは一旦保持（最近のため）
# 必要に応じて後日整理
```

**例外**: 以下は残す
- HANDOVER.md（常に最新に更新）
- PROJECT_CLEANUP_LOG_20251222.md（整理履歴として重要）
- 直近2週間以内の分析レポート

### Phase 2: analysisディレクトリの整理

**現状**: 112ファイル

**目標**: 30ファイル程度に削減

**分類**:

1. **保持するファイル**（約15-20ファイル）
   - 直近2週間の分析レポート
   - 重要な知見を含むレポート
   - 不採用案の記録（improvement_attemptsに移動）

2. **archiveに移動**（約80-90ファイル）
   - 2025年12月以前の分析レポート
   - 既に施策化されたレポート
   - 重複内容のレポート

3. **削除候補**（約10ファイル）
   - 不完全なレポート
   - 明らかに古い情報

### Phase 3: READMEの更新

**docs/README.md**を更新:
- 各ディレクトリの役割を明確化
- 「最新情報はここを見る」を明示
- 過去ログの扱いを説明

---

## 実装手順

### ステップ1: バックアップ作成

```bash
# 念のため全体をバックアップ
mkdir -p backups/docs_cleanup_20260114
cp -r docs/ backups/docs_cleanup_20260114/
```

### ステップ2: 日付付きファイルの移動

```bash
# archiveディレクトリ作成
mkdir -p docs/archive/analysis_2025_12
mkdir -p docs/archive/analysis_2025_11

# 12月の分析ファイルを移動
find docs/analysis/ -name "*_202512*.md" -exec mv {} docs/archive/analysis_2025_12/ \;

# 11月の分析ファイルを移動
find docs/analysis/ -name "*_202511*.md" -exec mv {} docs/archive/analysis_2025_11/ \;

# ... (以下同様)
```

### ステップ3: 整理ログの記録

整理内容を`docs/DOCUMENT_CLEANUP_LOG_20260114.md`に記録:
- 移動したファイル一覧
- 削除したファイル一覧
- 理由

### ステップ4: README更新

docs/README.mdに追記:
```markdown
## 過去ログについて

**日付付きドキュメント（`*_YYYYMMDD.md`）は過去ログです。**

- 最新情報ではありません
- 参考情報として`docs/archive/`に保存
- 最新情報は以下を参照:
  - [残タスク一覧.md](残タスク一覧.md)
  - [HANDOVER.md](HANDOVER.md)
  - [architecture/](architecture/) - システム仕様
  - [performance/](performance/) - 最新成績
```

---

## 期待される効果

### メリット

1. **情報アクセスの高速化**
   - 必要な情報がすぐに見つかる
   - 最新情報と過去ログの区別が明確

2. **認識エラーの削減**
   - Claude Codeが古い情報を参照するリスク低減
   - 最新状態の把握が容易

3. **メンテナンス性の向上**
   - 更新すべきファイルが明確
   - 重複情報の削減

### 注意点

1. **過去の知見へのアクセス**
   - archiveに移動しても削除はしない
   - 必要時にarchiveから参照可能

2. **段階的な実施**
   - 一度に全て整理せず、Phase分けで実施
   - 各Phaseで動作確認

---

## 次のアクション

### 即実行可能

1. バックアップ作成
2. 12月以前の日付付きファイルをarchiveに移動
3. README更新（過去ログの扱いを明記）

### 要検討

1. どのファイルを「重要な知見」として保持するか
2. archiveの階層構造（年月で分けるか、テーマで分けるか）
3. 削除候補ファイルの最終判断

---

## まとめ

**現状**: 58個の日付付きファイル、112個の分析ファイル
**目標**: 最新情報への明確なアクセス、過去ログの整理

**整理後の姿**:
```
docs/
├── 残タスク一覧.md           ← 最新状態（必読）
├── HANDOVER.md               ← 引継ぎ情報（必読）
├── README.md                 ← 索引
├── architecture/             ← システム仕様（重要）
├── performance/              ← 最新成績（重要）
├── presets/                  ← 購入条件（重要）
├── guides/                   ← 操作ガイド
├── analysis/                 ← 直近2週間の分析のみ（約20ファイル）
├── improvement_attempts/     ← 不採用案
└── archive/                  ← 過去ログ（80-90ファイル）
    ├── analysis_2025_11/
    ├── analysis_2025_12/
    └── historical_analysis_2025/
```

**実施タイミング**: 今すぐ可能（バックアップ後）

---

*作成者: Claude Code*
*最終更新: 2026-01-14*
