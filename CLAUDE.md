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
| **データ収集** | [docs/guides/DATA_COLLECTION_MASTER.md](docs/guides/DATA_COLLECTION_MASTER.md) |

### すぐに情報が必要なとき（★推奨）

| 情報 | ドキュメント |
|------|------------|
| **テーブル早見表・よく使うクエリ** | [docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) |
| **SQLクエリサンプル集（詳細）** | [docs/guides/SQL_QUERY_SAMPLES.md](docs/guides/SQL_QUERY_SAMPLES.md) |

**注意**:
- 日付付きドキュメント（`*_20251220.md`等）は過去ログ。最新情報ではない
- 数値データはDBで直接確認すること

## ⚠️ 参照してはいけないドキュメント

以下のドキュメントは**過去ログ**であり、最新情報ではありません。参照すると誤認識の原因になります：

### 1. 日付付きファイル（`*_2025*.md`, `*_2026*.md`）

- 作成当時の分析結果であり、現在のシステムと乖離している可能性
- 例: `docs/analysis/*_20251215.md` ～ `*_20251222.md`（約45ファイル）
- 例: `docs/implementation/*_2025*.md`
- 例: `docs/PROJECT_CLEANUP_LOG_20251222.md`
- 例: `docs/DOCUMENT_CLEANUP_PROPOSAL_20260114.md`

### 2. docs/implementation/ 配下のレポート

- 完了済みの実装記録（過去ログ）
- 参照するなら `docs/architecture/` の最新版を使用

### 3. docs/archive/ 配下

- 明示的にアーカイブされた古いドキュメント
- 過去の経緯確認以外では参照不要

### 4. docs/analysis/ 配下の古いレポート

- 大半が過去の分析レポート
- 最新の分析結果は `docs/performance/` を参照

**例外（参照必須）**:
- `docs/improvement_attempts/REJECTED_IDEAS.md` - 不採用案の確認に必須
- `docs/guides/` 配下のガイド類 - ハウツー情報として有効

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

## データ収集タスク（重要）

**「データ収集」を依頼されたら必ず参照:**

### クイックリファレンス

| やりたいこと | 推奨スクリプト |
|-------------|---------------|
| **過去全データ（2020-2025）** | `python scripts/data_collection/auto_fetch_2020_2025.py` |
| **特定期間のデータ** | `python scripts/data_collection/fetch_historical_data_parallel.py --start 2024-01-01 --end 2024-12-31` |
| **大量CSV収集（DB負荷なし）** | `python scripts/data_collection/fetch_to_csv_parallel_improved.py --start 2020-01-01 --end 2020-12-31 --output data/csv/2020` |
| **決まり手補完** | `python scripts/data_collection/補完_決まり手データ_改善版.py` |
| **レース詳細補完** | `python scripts/data_collection/補完_レース詳細データ_改善版v4.py` |
| **オッズ収集** | `python scripts/data_collection/fetch_odds_parallel_safe.py --start 2024-01-01 --end 2024-12-31` |
| **本日の直前情報** | `python scripts/data_collection/fetch_today_beforeinfo.py` |
| **統計指標生成** | `python scripts/data_collection/build_indicator_stats.py --year 2024` |

### 基本原則

1. **大量データはCSV方式** - DB負荷を回避
2. **並列化を活用** - 高速化（8-12ワーカー）
3. **月別に分割** - リカバリ容易
4. **旧版は使わない** - 必ず推奨スクリプトを使用

### ⚠️ 重要な制約（必読）

| データ種別 | 取得可能期間 | 補完可否 |
|-----------|-------------|---------|
| レース基本情報・結果・オッズ | 2020年～ | ✅ 可能（公式APIで常時公開） |
| **オリジナル展示** | **前日のみ** | **❌ 不可（一度逃すと永久欠損）** |

**Claude Codeへの注意**:
- 公式データ（レース・結果・オッズ）は過去数年分取得可能
- オリジナル展示のみ前日限定、毎日の自動収集が必須

### 詳細ドキュメント

- **最適化ガイド**: [docs/guides/DATA_COLLECTION_OPTIMIZATION_GUIDE.md](docs/guides/DATA_COLLECTION_OPTIMIZATION_GUIDE.md) **(推奨)**
- **マスターガイド**: [docs/guides/DATA_COLLECTION_MASTER.md](docs/guides/DATA_COLLECTION_MASTER.md)
- **スクリプトカタログ**: [docs/guides/DATA_COLLECTION_SCRIPTS_CATALOG.md](docs/guides/DATA_COLLECTION_SCRIPTS_CATALOG.md)
- **CSV方式詳細**: [docs/guides/CSV_DATA_COLLECTION_GUIDE.md](docs/guides/CSV_DATA_COLLECTION_GUIDE.md)
- **競艇場独自データ**: [docs/guides/VENUE_SPECIFIC_DATA_COLLECTION.md](docs/guides/VENUE_SPECIFIC_DATA_COLLECTION.md)

## ディレクトリ構成

```
├── src/           # ソースコード
├── scripts/       # 運用スクリプト
│   ├── prediction/     # 予測生成
│   ├── backtest/       # バックテスト
│   ├── analysis/       # 分析
│   ├── data_collection/# データ収集
│   ├── maintenance/    # メンテナンス
│   └── templates/      # スクリプトテンプレート
├── config/        # 設定
├── docs/          # ドキュメント（最新版）
│   ├── architecture/        # システム設計・予測ロジック
│   ├── performance/         # 年度別成績・テスト結果
│   ├── presets/             # 購入条件・プリセット
│   ├── improvement_attempts/ # 不採用案・検証履歴
│   ├── guides/              # ガイド
│   ├── analysis/            # 最新の分析結果のみ
│   ├── maintenance/         # メンテナンス記録
│   └── archive/             # 過去ログ（★参照禁止）
│       ├── analysis_2025/   # 2025年の分析レポート（51ファイル）
│       ├── implementation/  # 完了済み実装レポート（29ファイル）
│       └── reports_2025/    # 2025年のその他レポート（4ファイル）
├── ui/            # Streamlit UI
├── tests/         # テスト
├── data/          # データ（Git管理外）
└── models/        # MLモデル（Git管理外）
```

**重要**: docs/archive/ 配下は過去ログです。参照不要。
