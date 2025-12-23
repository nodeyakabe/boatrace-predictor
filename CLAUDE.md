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

## ⚠️ 最重要: 参照すべきドキュメント（この3つだけ）

**認識間違い防止のため、情報源を以下の3つに限定する**：

| 質問 | ドキュメント | 理由 |
|------|------------|------|
| **現在の状態は？** | [docs/残タスク一覧.md](docs/残タスク一覧.md) | **唯一の最新状態情報源**（DB実測値に基づく） |
| **前回の作業内容は？** | [docs/HANDOVER.md](docs/HANDOVER.md) | セッション間の引継ぎ（常に上書き更新） |
| **DB構造は？** | [docs/architecture/DATABASE_SCHEMA.md](docs/architecture/DATABASE_SCHEMA.md) | データベース仕様書（35テーブル） |

**⚠️ 重要な注意事項**:
- **日付付きドキュメント**（`HANDOVER_20251220.md`, `REPORT_20251215.md`等）は**過去ログ**
- 過去ログには**誤った情報**が含まれる可能性が高い（例: 2022年予測データ100%完了と記載されているが実際は27.3%）
- **必ず上記3つのドキュメントを参照**すること
- 数値データが必要な場合は**データベースを直接確認**すること

**その他のドキュメント**（参考用）:
- [README.md](README.md) - プロジェクト概要（変更頻度低）
- [docs/implementation/betting_implementation_status.md](docs/implementation/betting_implementation_status.md) - ベッティングシステム実装状況

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

## セッション開始時の必須確認（3ステップ）

作業依頼があった場合、**以下の順番で確認**すること：

### Step 1: 現在の状態を確認

```bash
# 残タスク一覧.mdを読む
```

**確認内容**:
- 最優先タスクは何か
- 現在のシステム状態（ROI、予測データ生成状況など）
- 前回セッションで何が完了したか

### Step 2: 前回の作業内容を確認

```bash
# HANDOVER.mdを読む
```

**確認内容**:
- 前回セッションの作業内容
- 引継ぎ事項
- 注意すべき問題

### Step 3: 知見DBで過去の施策を検索（新規施策の場合のみ）

新規施策を検討する場合のみ、以下を実行：

```bash
python scripts/search_knowledge.py "検討中のキーワード"
```

**例**:
- 依頼「オッズを使って改善」→ `python scripts/search_knowledge.py "オッズ"`
- 依頼「2着精度改善」→ `python scripts/search_knowledge.py "2着"`

**確認内容**:
- 過去に同じ施策を実施していないか
- 不採用になった理由
- 既知の落とし穴

**⚠️ 重要**: 類似施策が見つかった場合は、ユーザーに報告して再検討の必要性を確認すること

---

### ⚠️ 絶対に避けるべきこと

- ❌ 日付付きドキュメント（`*_20251220.md`等）を最新情報として参照
- ❌ 過去の調査結果を確認せずに同じ分析を実施
- ❌ データベースを確認せずにドキュメントの数値を信用
- ❌ 既に不採用になった施策を再提案

### ✅ 必ず実施すること

- ✅ 残タスク一覧.mdとHANDOVER.mdを最初に読む
- ✅ 数値データはデータベースで直接確認
- ✅ 新規施策は知見DBで過去施策を検索
- ✅ 作業開始前にユーザーに報告と確認

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
