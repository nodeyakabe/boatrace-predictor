# 2021年・2023年データ補完 - クイックスタート

## TL;DR（要約）

2021年・2023年のデータが約83%欠損しています。以下のコマンドで補完できます。

```bash
# 1. 欠損状況確認
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021

# 2. データ収集（CSV）- 全月自動実行
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --all-months

# 3. 検証
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months --dry-run

# 4. DB投入
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months

# 5. 2023年も同様
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2023 --all-months
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2023 --all-months --dry-run
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2023 --all-months
```

## 所要時間

| 作業 | 所要時間 |
|------|---------|
| 2021年 CSV収集 | 約30-40時間 |
| 2021年 DB投入 | 約10-20分 |
| 2023年 CSV収集 | 約30-40時間 |
| 2023年 DB投入 | 約10-20分 |
| **合計** | **約61-81時間** |

## 月別に実行する場合

```bash
# 2021年1月のみ
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 1
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 1

# 2021年2月のみ
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 2
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 2

# ... 以下同様
```

## 詳細ドキュメント

詳細は [2021_2023_DATA_RECOVERY_GUIDE.md](./2021_2023_DATA_RECOVERY_GUIDE.md) を参照してください。

## 作成されたファイル

### スクリプト

1. **scripts/data_collection/補完_2021_2023_欠損データ.py**
   - 2021年・2023年の欠損データをCSVに収集
   - 月別分割対応
   - 並列化（デフォルト12ワーカー）
   - 50タスクごとに自動保存

2. **scripts/maintenance/投入_2021_2023_補完データ.py**
   - CSVからDBへの一括投入
   - dry-runモードでの事前検証
   - トランザクション管理
   - 重複チェック

### ドキュメント

1. **docs/guides/2021_2023_DATA_RECOVERY_GUIDE.md**
   - 詳細な実行手順
   - トラブルシューティング
   - 推奨ワークフロー

2. **docs/guides/2021_2023_DATA_RECOVERY_README.md**（本ファイル）
   - クイックスタートガイド

## 注意事項

### ⚠️ 必須

1. **必ず検証してから投入**: `--dry-run` で事前チェック
2. **十分なディスク容量**: 3GB以上推奨
3. **DB負荷ゼロ**: CSV方式なので収集中も他の作業可能

### 💡 推奨

1. **月別実行**: 失敗時のリトライが容易
2. **バックグラウンド実行**: 長時間実行なので `nohup` 推奨
3. **投入後のCSV削除**: ディスク容量節約

## 期待される結果

### 補完前

| 年 | エントリー | 結果 | オッズ | 払戻 |
|----|-----------|------|-------|------|
| 2021 | 26.1% | 25.9% | 17.0% | 17.0% |
| 2023 | 27.1% | 26.9% | 16.2% | 16.2% |

### 補完後（目標）

| 年 | エントリー | 結果 | オッズ | 払戻 |
|----|-----------|------|-------|------|
| 2021 | **95%+** | **95%+** | **90%+** | **90%+** |
| 2023 | **95%+** | **95%+** | **90%+** | **90%+** |

## トラブル時の連絡先

- スクリプトの問題: 詳細ガイドの「トラブルシューティング」セクション参照
- その他の問題: プロジェクト管理者に連絡

## 参考

- [CSV経由データ収集ガイド](./CSV_DATA_COLLECTION_GUIDE.md)
- [データ収集マスターガイド](./DATA_COLLECTION_MASTER.md)
