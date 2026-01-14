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
| **標準テスト** | `python scripts/backtest/standard_backtest.py --full` |
| 知見検索 | `python scripts/search_knowledge.py "キーワード"` |
| 知見DB統計 | `python scripts/query_knowledge_db.py --stats` |

## 標準テスト（重要）

**「標準テストして」と言われたら必ずこのコマンドを実行:**
```bash
python scripts/backtest/standard_backtest.py --full
```

**出力内容:**
- 6年間（2020-2025年）の全体サマリー（ROI、収支、的中率）
- 条件別パフォーマンス（パターンH/1点買い区分付き）
- 年度別パフォーマンス（黒字年数判定）
- 2025年月別パフォーマンス（黒字月数判定）
- 条件別の年度詳細

**その他のオプション:**
- `--year 2024`: 特定年度の詳細テスト
- `--save-baseline`: ベースライン保存
- `--compare`: ベースラインと比較

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

## 新規購入条件の検証プロセス【重要】

**分析スクリプトで有望な条件を発見した場合の必須手順:**

### 1. 分析スクリプトでの注意点

```sql
-- ❌ 誤り: 枠番固定オッズ（1-2-3固定）
JOIN trifecta_odds t ON rp.race_id = t.race_id
    AND t.combination = '1-2-3'

-- ✅ 正しい: 予測順位ベースのオッズ（実際の買い目）
JOIN trifecta_odds t ON rp.race_id = t.race_id
    AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                     || CAST(rp2.pit_number AS TEXT) || '-'
                     || CAST(rp3.pit_number AS TEXT)
```

### 2. 採用前の必須検証

1. `standard_backtest.py` に条件を追加
2. 必ず `python scripts/backtest/standard_backtest.py --full` を実行
3. 以下の基準を確認:
   - **黒字年数 4/6年以上**
   - **累計収支がプラス**
   - **ROI 100%以上**

### 3. 異常に良い結果への対応

- ROI 200%超え、6/6年黒字 → **計算ミスを疑う**
- 分析と実テストの乖離が大きい → **JOIN条件を確認**

### 4. 不採用時の記録

不採用案は `docs/improvement_attempts/REJECTED_IDEAS.md` に追記

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
