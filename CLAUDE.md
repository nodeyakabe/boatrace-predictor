# Claude Code プロジェクト設定

## AIモデル設定

- **デフォルト**: Sonnet を使用すること
- **Opus への切り替え**: ユーザーが「上位AIを使って」「Opusで」など明示的に指定した場合のみ
- Task ツールで子エージェントを起動する際も、特に指定がなければ `model: "sonnet"` を使用すること

## 言語設定

- ユーザーとのコミュニケーションは日本語で行うこと

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
