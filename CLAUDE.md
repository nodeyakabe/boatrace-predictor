# Claude Code プロジェクト設定

## 言語設定

- 日本語でコミュニケーション

## 参照すべきドキュメント

### 作業開始時（必須）

| 質問 | ドキュメント |
|------|------------|
| **現在の状態** | [docs/残タスク一覧.md](docs/残タスク一覧.md) |
| **前回の作業** | [docs/HANDOVER.md](docs/HANDOVER.md) |

### 技術情報（必要に応じて）

| カテゴリ | ドキュメント |
|---------|------------|
| **予測ロジック** | [docs/architecture/PREDICTION_LOGIC.md](docs/architecture/PREDICTION_LOGIC.md) |
| **年度別成績** | [docs/performance/YEARLY_PERFORMANCE.md](docs/performance/YEARLY_PERFORMANCE.md) |
| **テスト構成** | [docs/performance/TEST_RESULTS.md](docs/performance/TEST_RESULTS.md) |
| **不採用案** | [docs/improvement_attempts/REJECTED_IDEAS.md](docs/improvement_attempts/REJECTED_IDEAS.md) |
| **購入条件** | [docs/presets/BET_CONDITIONS.md](docs/presets/BET_CONDITIONS.md) |
| **DB構造** | [docs/architecture/DATABASE_SCHEMA.md](docs/architecture/DATABASE_SCHEMA.md) |

**注意**:
- 日付付きドキュメント（`*_20251220.md`等）は過去ログ。最新情報ではない
- 数値データはDBで直接確認すること

## よく使うコマンド

| 操作 | コマンド |
|------|---------|
| UI起動 | `cd ui && python -m streamlit run app.py` |
| 知見検索 | `python scripts/search_knowledge.py "キーワード"` |
| 知見DB統計 | `python scripts/query_knowledge_db.py --stats` |

## セッション開始時

1. `docs/残タスク一覧.md` を読む
2. `docs/HANDOVER.md` を読む
3. 新規施策の場合のみ: `python scripts/search_knowledge.py "キーワード"`

## 施策検証完了時

```bash
python scripts/register_experiment.py \
    --id "施策ID" --name "施策名" --category "カテゴリ" \
    --result "accepted/rejected" --effect "効果値" --keywords "キーワード"
```

## 残タスクへの追記

「残タスクに追記して」等のリクエスト → `docs/残タスク一覧.md` に追加

## ディレクトリ構成

```
├── src/           # ソースコード
├── scripts/       # 運用スクリプト
│   ├── prediction/     # 予測生成
│   ├── backtest/       # バックテスト
│   ├── analysis/       # 分析
│   ├── data_collection/# データ収集
│   └── maintenance/    # メンテナンス
├── config/        # 設定
├── docs/          # ドキュメント
│   ├── architecture/        # システム設計・予測ロジック
│   ├── performance/         # 年度別成績・テスト結果
│   ├── presets/             # 購入条件・プリセット
│   ├── improvement_attempts/ # 不採用案・検証履歴
│   ├── guides/              # ガイド
│   └── analysis/            # 分析レポート（過去ログ）
├── ui/            # Streamlit UI
├── tests/         # テスト
├── data/          # データ（Git管理外）
└── models/        # MLモデル（Git管理外）
```
