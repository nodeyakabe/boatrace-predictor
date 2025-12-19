# Claude Code プロジェクト設定

## AIモデル設定

- **デフォルト**: Sonnet を使用すること
- **Haiku への切り替え**: 以下のような軽量タスクでは `model: "haiku"` を使用すること
  - 「進捗状況を確認して」「状況を確認して」
  - 「残タスクは？」「何をすればいい？」
  - 「ドキュメントを読んで」「ファイルを見て」
  - 「リストアップして」「一覧を見せて」
  - 「簡単な修正」「typo修正」
  - その他、コード生成や複雑な分析を伴わない情報取得タスク
- **Opus への切り替え**: ユーザーが「上位AIを使って」「Opusで」など明示的に指定した場合のみ
- Task ツールで子エージェントを起動する際も、タスクの複雑度に応じて適切なモデルを選択すること

## 言語設定

- ユーザーとのコミュニケーションは日本語で行うこと

## よく使うドキュメント

ユーザーが以下の質問をした場合、対応するドキュメントを提示すること：

| 質問 | ドキュメント | 説明 |
|------|------------|------|
| 「DB構造は？」「データベースの構造は？」 | [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | データベース仕様書（全35テーブル） |
| 「残タスクは？」「何をすればいい？」 | [docs/残タスク一覧.md](docs/残タスク一覧.md) | 残タスク一覧、最優先タスク |
| 「戦略は？」「ベッティングシステムは？」 | [docs/betting_implementation_status.md](docs/betting_implementation_status.md) | 戦略A、実装状況 |
| 「プロジェクト概要は？」 | [README.md](README.md) | プロジェクト全体像、目標、実績 |

**重要**: これらの質問には、まずドキュメントを提示し、必要に応じて内容を読み取って回答すること

### 残タスクへの追記

ユーザーが以下のようなリクエストをした場合、[docs/残タスク一覧.md](docs/残タスク一覧.md)にタスクを追記すること：

- 「残タスクに残しておいて」
- 「残タスクに追記して」
- 「TODO に追加して」
- 「後でやるタスクとして記録して」
- 「次にやることとしてメモして」

**追記方法**:
1. まず現在の残タスク一覧.mdを読む
2. 適切なセクション（Phase 1, Phase 2など）または新規セクションにタスクを追加
3. タスクの優先度、概要、期待効果を明記
4. 関連ファイルや参考情報があれば記載

## よくある操作

### UI起動

ユーザーが「UIを起動して」「Streamlitを起動して」などと言った場合、以下のコマンドを使用すること：

```bash
cd ui && python -m streamlit run app.py
```

**重要**: `streamlit run ui/app.py` は使用しないこと（パスが通っていない可能性が高い）

バックグラウンドで起動する場合：
- `run_in_background: true` パラメータを使用
- 起動完了後、アクセスURLを表示すること（http://localhost:8501）

### Gitへのプッシュ

ユーザーが「プッシュして」「Gitにプッシュして」などと言った場合、必ず以下の手順を実行すること：

```bash
# 1. 全ファイルをステージング（必須）
git add .

# 2. コミット（HEREDOCで複数行メッセージ）
git commit -m "$(cat <<'EOF'
変更内容のタイトル

## 詳細
- 変更内容1
- 変更内容2

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"

# 3. プッシュ
git push origin main
```

**重要**:
- 必ず `git add .` で全ファイルをステージングすること
- コミットメッセージは詳細に記載すること
- フッターに必ず「🤖 Generated with [Claude Code]」と「Co-Authored-By」を含めること

## セッション開始時の必須確認事項

ユーザーから作業依頼があった場合、**必ず以下を確認してから作業を開始**すること：

### 0. 知見インデックスの検索（最優先）⭐NEW

**新規施策の検討前に必ず実施**:

```bash
python scripts/search_knowledge.py "検討中のキーワード"
```

**検索例**:
- 依頼「オッズを使って改善」→ `python scripts/search_knowledge.py "オッズ"`
- 依頼「2着精度改善」→ `python scripts/search_knowledge.py "2着"`
- 問題「検証が遅い」→ `python scripts/search_knowledge.py "検証が遅い"`

**確認内容**:
- 過去に同じ施策を実施していないか？
- 不採用になった理由は？
- 既知の落とし穴（パフォーマンス問題など）はないか？

**⚠️ 重要**: 検索結果で類似施策が見つかった場合：
1. 不採用理由と教訓を必ず確認
2. 同じ理由で再度失敗しないか検討
3. ユーザーに過去の結果を報告し、再検討の必要性を確認

### 1. 直近のDAILY_REPORT確認

```bash
# 直近3日分のDAILY_REPORTを確認
ls -lt docs/DAILY_REPORT_*.md | head -3
```

**目的**: 最近実施・完了・不採用になった施策を把握し、重複作業を防ぐ

**確認事項**:
- 同じテーマの調査が既に実施済みでないか
- 既に不採用になった施策ではないか
- 関連する知見や教訓が記録されていないか

### 2. キーワードで過去の調査結果を検索

ユーザーの依頼内容に関連するキーワードで検索：

```bash
# メインドキュメントを検索
grep -r "キーワード1\|キーワード2" docs/*.md

# 過去の改善試行結果を検索
grep -r "キーワード1\|キーワード2" docs/improvement_attempts/

# 最近更新されたドキュメントを確認
ls -lt docs/*.md | head -20
```

**例**:
- 依頼「2着・3着の精度改善」→ キーワード: `2着|3着|v2.*モデル|v3.*モデル|条件付き`
- 依頼「ROI改善方法」→ キーワード: `ROI.*改善|収支.*改善|戦略`

### 3. 残タスク一覧の「完了済みタスク」セクション確認

```bash
# 完了済みタスクセクションを確認
grep -A 50 "完了済みタスク" docs/残タスク一覧.md
```

**目的**: 既に実施済み・不採用になった施策を把握

### 4. 検索結果に基づいて判断

| 状況 | 対応 |
|------|------|
| **既に調査・実施済み** | その結果を報告し、重複作業しない |
| **既に不採用と判断済み** | 不採用理由を説明し、別のアプローチを提案 |
| **未調査** | 新規に調査・作業を開始 |
| **部分的に調査済み** | 既存の調査結果を踏まえて追加調査 |

### 5. 必須の報告

作業開始前に、以下を必ずユーザーに報告すること：

**パターンA（既存調査あり）**:
```
「〇〇について調査します。
過去のドキュメントを確認したところ、YYYY-MM-DD に同様の調査が実施されており、
結果は『XXX』でした（docs/DAILY_REPORT_YYYYMMDD.md）。
この結果を踏まえて作業を進めますか？それとも再調査しますか？」
```

**パターンB（重複作業の防止）**:
```
「〇〇について調査します。
過去のドキュメントを確認したところ、YYYY-MM-DD に既に実施済みで、
『不採用（ROI -XX pt）』という結論になっています（docs/DAILY_REPORT_YYYYMMDD.md）。
改めて調査しますか？」
```

**パターンC（新規調査）**:
```
「〇〇について調査します。
過去のドキュメントを確認しましたが、関連する調査は見つかりませんでした。
新規に調査を開始します。」
```

### 重要な注意事項

⚠️ **絶対に避けるべきこと**:
- DAILY_REPORTを確認せずに作業開始
- 過去の調査結果を検索せずに同じ分析を実施
- 既に不採用になった施策を再提案
- 重複ドキュメントの作成

✅ **必ず実施すること**:
- 作業開始前の文献調査（上記0-3の実施）
- 既存の調査結果の尊重
- ユーザーへの事前報告と確認

## 施策検証完了時の必須手順

新規施策の検証が完了したら、**必ず知見DBに登録**すること：

### 1. 知見DBへの登録

```bash
python scripts/register_experiment.py \
    --id "施策ID" \
    --name "施策名" \
    --category "カテゴリ" \
    --result "accepted/rejected/pending" \
    --effect "効果値（例: +2.5pt）" \
    --reason "不採用理由（rejectの場合）" \
    --lesson "教訓・学び" \
    --keywords "キーワード1,キーワード2" \
    --files "関連ファイル1,関連ファイル2" \
    --doc "詳細ドキュメントパス"
```

**例（不採用の場合）**:
```bash
python scripts/register_experiment.py \
    --id "rank23_odds_calibration" \
    --name "2着・3着オッズ校正" \
    --category "odds_integration" \
    --result "rejected" \
    --effect "2024年: +2.04pt, 2025年: ±0.00pt" \
    --reason "モデルドリフトにより2025年データで効果消失" \
    --lesson "年度別検証必須。過去データのみで判断しない" \
    --keywords "オッズ,2着,3着,市場確率" \
    --doc "docs/improvement_attempts/rank23_odds_calibration_rejection_20251218.md"
```

**例（採用の場合）**:
```bash
python scripts/register_experiment.py \
    --id "negative_patterns" \
    --name "ネガティブパターン" \
    --category "pattern_optimization" \
    --result "accepted" \
    --effect "+2.0%" \
    --keywords "パターン,ネガティブ,減算" \
    --files "src/analysis/scorers/pattern_scorer.py"
```

### 2. 追加ドキュメント作成

**不採用の場合**:
- `docs/improvement_attempts/` に詳細レポートを作成
- 検証結果、不採用理由、教訓を記録

**失敗事例の場合**:
- `docs/lessons_learned/` に教訓ドキュメントを作成

**採用の場合**:
- `config/feature_flags.py` にフラグを追加
- DAILY_REPORTに実装内容を記録

### 3. 知見DBの統計確認（オプション）

```bash
# 統計情報を確認
python scripts/query_knowledge_db.py --stats

# カテゴリ別検索
python scripts/query_knowledge_db.py --category odds_integration

# 不採用施策のみ
python scripts/query_knowledge_db.py --result rejected
```
