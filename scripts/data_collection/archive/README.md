# データ収集スクリプト アーカイブ

**最終更新**: 2026-01-15

---

## このディレクトリについて

`scripts/data_collection/` ディレクトリから移動された、旧版・非推奨・特殊用途のスクリプトを保管しています。

**目的**:
- メインディレクトリを整理し、推奨スクリプトのみを残す
- 旧版スクリプトを誤って使用しないようにする
- 必要に応じて過去のスクリプトを参照できるようにする

---

## ディレクトリ構造

```
archive/
├── README.md           # このファイル
├── deprecated/         # 旧版・非推奨スクリプト
└── year_specific/      # 特定年度専用スクリプト
```

---

## deprecated/ - 旧版・非推奨スクリプト

**理由**: 改善版が存在するため使用禁止

| ファイル名 | 理由 | 代替スクリプト |
|-----------|------|---------------|
| `fetch_historical_data.py` | 並列化なし（遅い） | `fetch_historical_data_parallel.py` |
| `collect_beforeinfo_2020_2023.py` | 最適化前（8ワーカー） | `collect_beforeinfo_2020_2023_optimized.py` |
| `補完_決まり手データ_シンプル版.py` | 逐次処理（遅い） | `補完_決まり手データ_改善版.py` |
| `補完_決まり手データ_v2.py` | LIMIT 100制限、テスト用 | `補完_決まり手データ_改善版.py` |
| `fetch_odds_parallel.py` | エラー処理不足 | `fetch_odds_parallel_safe.py` |
| `import_missing_data.py` | バグあり | `import_missing_data_fixed.py` → `fill_missing_weather_data.py` |
| `fill_missing_weather_2022.py` | 特定年度専用 | `fill_missing_weather_data.py` |
| `fetch_historical_odds.py` | 最適化前 | `fetch_odds_parallel_safe.py` |
| `fetch_historical_odds_simple.py` | シンプル版 | `fetch_odds_parallel_safe.py` |

### その他（特殊用途・一時的）

| ファイル名 | 理由 |
|-----------|------|
| `collect_parts_exchange.py` | 部品交換データ（特殊用途） |
| `auto_collect_beforeinfo_after_advance.py` | advance予測後自動収集（特殊用途） |
| `complement_2020_2023_beforeinfo_and_predictions.py` | 特定期間補完 |
| `fetch_odds_2020_2024_background.py` | 特定期間オッズ収集 |
| `fetch_odds_fast.py` | 高速オッズ収集（実験版） |
| `update_historical_odds.py` | オッズ更新（特殊用途） |
| `fetch_original_tenji_daily.py` | オリジナル展示収集（逐次版） |
| `worker_tenji_collection.py` | 展示データワーカー |
| `worker_missing_data.py` | 不足データワーカー |
| `import_missing_data_fixed.py` | 不足データインポート修正版 |
| `import_remaining_data.py` | 残りデータインポート |
| `import_final_diff.py` | 最終差分インポート |
| `update_database.py` | データベース更新 |
| `test_kimarite_fetch.py` | 決まり手取得テスト |

---

## year_specific/ - 特定年度専用スクリプト

**理由**: 特定年度のみに使用するラッパースクリプト

| ファイル名 | 理由 |
|-----------|------|
| `collect_2024_all_data.py` | 2024年専用ラッパー |
| `collect_2024_missing_data.py` | 2024年不足データ専用 |
| `fetch_historical_data_2024.py` | 2024年専用ラッパー |

**代替方法**: 汎用スクリプトに `--start` `--end` オプションで期間指定

```bash
# 汎用スクリプトで代替可能
python scripts/data_collection/fetch_historical_data_parallel.py \
  --start 2024-01-01 \
  --end 2024-12-31
```

---

## ⚠️ 使用上の注意

### このアーカイブ内のスクリプトを使用する場合

1. **基本的に使用しない** - 推奨スクリプトを使用すること
2. **どうしても必要な場合** - 以下を確認:
   - なぜ推奨スクリプトでは不可なのか
   - 代替手段はないか
   - 使用するリスクを理解しているか

3. **使用する前に** - 必ず確認:
   - スクリプトの内容
   - 依存関係
   - DB互換性

---

## 削除履歴

### 2026-01-15
- 旧版・非推奨スクリプト: 23個をアーカイブ
- 特定年度専用スクリプト: 3個をアーカイブ
- メインディレクトリ残存: 21個（推奨スクリプト）

**移動前**: 47スクリプト
**移動後**: 21スクリプト（55%削減）

---

## 参照ドキュメント

- [DATA_COLLECTION_MASTER.md](../../../docs/guides/DATA_COLLECTION_MASTER.md) - データ収集マスターガイド
- [DATA_COLLECTION_SCRIPTS_CATALOG.md](../../../docs/guides/DATA_COLLECTION_SCRIPTS_CATALOG.md) - 全スクリプトカタログ

---

**作成日**: 2026-01-15
**最終更新**: 2026-01-15
