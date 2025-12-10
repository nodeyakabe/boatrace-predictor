# Claude Code プロジェクト設定

## AIモデル設定

- **デフォルト**: Sonnet を使用すること
- **Opus への切り替え**: ユーザーが「上位AIを使って」「Opusで」など明示的に指定した場合のみ
- Task ツールで子エージェントを起動する際も、特に指定がなければ `model: "sonnet"` を使用すること

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
