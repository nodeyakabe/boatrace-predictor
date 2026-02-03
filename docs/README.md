# docs/ディレクトリ索引

**最終更新**: 2026-01-30

## 📋 主要ドキュメント（ルート直下）

| ファイル | 説明 | 優先度 |
|----------|------|:-----:|
| **残タスク一覧.md** | マスタータスク管理（最新状態情報源） | ★★★ |
| **HANDOVER.md** | セッション間引継ぎ | ★★★ |
| **QUICK_REFERENCE.md** | テーブル早見表・よく使うクエリ（★推奨） | ★★★ |

## 📁 ディレクトリ構造

### architecture/ - システム設計（★最新版）
| ファイル | 説明 |
|----------|------|
| **DATABASE_SCHEMA.md** | データベース仕様書（35テーブル、活用状況一覧付き） |
| **PREDICTION_LOGIC.md** | 予測ロジック仕様 |
| ARCHITECTURE.md | システムアーキテクチャ |
| SYSTEM_OVERVIEW.md | システム概要 |

### performance/ - パフォーマンス情報（★最新版）
| ファイル | 説明 |
|----------|------|
| **YEARLY_PERFORMANCE.md** | 年度別成績（2020-2025年） |
| **TEST_RESULTS.md** | バックテスト結果 |

### presets/ - 購入条件（★最新版）
| ファイル | 説明 |
|----------|------|
| **BET_CONDITIONS.md** | 10条件の詳細仕様 |

### improvement_attempts/ - 改善試行記録（★参照必須）
| ファイル | 説明 |
|----------|------|
| **REJECTED_IDEAS.md** | 不採用案の記録（宝探しの対象） |

### guides/ - 操作ガイド
| ファイル | 説明 |
|----------|------|
| **DATA_COLLECTION_MASTER.md** | データ収集マスターガイド |
| **SQL_QUERY_SAMPLES.md** | SQLクエリサンプル集（詳細版） |
| DATA_COLLECTION_SCRIPTS_CATALOG.md | スクリプトカタログ |
| CSV_DATA_COLLECTION_GUIDE.md | CSV方式データ収集ガイド |
| DATA_COMPLETION_ERROR_RECOVERY.md | エラー時リカバリー手順書 |
| DATA_COMPLETION_REVIEW_WORKFLOW.md | データ補完後の再検証ワークフロー |
| QUICKSTART.md | クイックスタート |
| OPERATIONS_GUIDE.md | 運用ガイド |
| backtest_guide.md | バックテストガイド |

### analysis/ - 最新の分析結果のみ
- ⚠️ 日付付きファイル（*_2025*.md等）は全てアーカイブ済み
- このディレクトリには最新の分析結果のみを配置

### knowledge/ - 知見ベース
| ファイル | 説明 |
|----------|------|
| prediction_logic_knowledge_base.md | 予測ロジック知見 |
| weather_preset_rules.md | 天候プリセットルール |

### maintenance/ - メンテナンス記録
- データベースメンテナンス記録
- システムメンテナンス記録

### archive/ - アーカイブ（★参照禁止）

**重要**: このディレクトリは過去ログです。参照不要。

| サブディレクトリ | 内容 | ファイル数 |
|----------------|------|:---------:|
| **analysis_2025/** | 2025年の分析レポート | 51ファイル |
| **implementation/** | 完了済み実装レポート | 29ファイル |
| **reports_2025/** | 2025年のその他レポート | 4ファイル |
| archive_2025_11_13/ | 既存アーカイブ | - |

**アーカイブ基準**:
1. 日付付きファイル（`*_2025*.md`, `*_2026*.md`）
2. 完了済み実装レポート（`phase*_completion_report.md`等）
3. 古い分析レポート

**例外（参照可能）**:
- `improvement_attempts/REJECTED_IDEAS.md` - 不採用案の確認に必須
- `guides/` 配下 - ハウツー情報として有効

---

## 🔍 ドキュメント検索のヒント

### すぐに情報が必要なとき
1. **テーブル・クエリ** → [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
2. **詳細なクエリ例** → [guides/SQL_QUERY_SAMPLES.md](guides/SQL_QUERY_SAMPLES.md)
3. **テーブル仕様** → [architecture/DATABASE_SCHEMA.md](architecture/DATABASE_SCHEMA.md)

### タスク・状況確認
1. **現在のタスク** → [残タスク一覧.md](残タスク一覧.md)
2. **前回の作業** → [HANDOVER.md](HANDOVER.md)

### 技術仕様
1. **予測ロジック** → [architecture/PREDICTION_LOGIC.md](architecture/PREDICTION_LOGIC.md)
2. **購入条件** → [presets/BET_CONDITIONS.md](presets/BET_CONDITIONS.md)
3. **年度別成績** → [performance/YEARLY_PERFORMANCE.md](performance/YEARLY_PERFORMANCE.md)

### データ収集
1. **マスターガイド** → [guides/DATA_COLLECTION_MASTER.md](guides/DATA_COLLECTION_MASTER.md)
2. **スクリプト一覧** → [guides/DATA_COLLECTION_SCRIPTS_CATALOG.md](guides/DATA_COLLECTION_SCRIPTS_CATALOG.md)

---

**最終更新**: 2026-01-30
**更新者**: Claude Sonnet 4.5
