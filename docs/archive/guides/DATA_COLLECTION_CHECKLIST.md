# データ収集チェックリスト

**最終更新**: 2026-02-04

このチェックリストは、データ収集作業の品質を確保するために使用します。
印刷またはコピーして使用してください。

---

## 1. 収集前チェックリスト

### 1.1 要件確認
- [ ] 収集対象のデータ種別を確認した
  - [ ] レース基本情報
  - [ ] 結果データ
  - [ ] オッズデータ
  - [ ] 直前情報
  - [ ] その他: _______________
- [ ] 収集期間を決定した: _______ 〜 _______
- [ ] 予想レース数を算出した: 約 _______ レース

### 1.2 スクリプト選択
- [ ] 推奨スクリプト一覧を確認した
- [ ] 適切なスクリプトを選択した: _______________________
- [ ] 非推奨スクリプトを使用していないことを確認した

### 1.3 収集方式の決定
- [ ] 1万レース以上の場合、CSV方式を選択した
- [ ] DB直接投入の場合、他の作業への影響を確認した
- [ ] ディスク空き容量を確認した（1年分: 約600MB-1.2GB）

### 1.4 環境設定
- [ ] 並列数を適切に設定した（推奨: 8-12）
- [ ] 出力ディレクトリを作成した（CSV方式の場合）
- [ ] ログディレクトリを確認した

---

## 2. 収集中チェックリスト

### 2.1 監視項目
- [ ] 進捗表示を定期的に確認している
- [ ] エラー率が高くないか確認している（目安: 5%未満）
- [ ] メモリ使用量が異常に増えていないか確認している

### 2.2 問題発生時
- [ ] Ctrl+Cで停止する場合、優雅な終了を待った
- [ ] 強制終了はしていない
- [ ] エラーログを確認した

---

## 3. 収集後チェックリスト

### 3.1 結果確認
- [ ] 処理完了メッセージを確認した
- [ ] 成功件数を確認した: _______ 件
- [ ] エラー件数を確認した: _______ 件
- [ ] 成功率を確認した: _______ %

### 3.2 CSV方式の場合
- [ ] dry-runで検証を実行した
- [ ] 検証結果に問題がないことを確認した
- [ ] 本番投入を実行した

### 3.3 データ検証
- [ ] 投入後のデータ件数を確認した
- [ ] サンプルデータをSQLで確認した
- [ ] 外部キー制約違反がないことを確認した

### 3.4 後処理
- [ ] 必要に応じて補完スクリプトを実行した
- [ ] 統計指標を再生成した（必要な場合）
- [ ] CSVファイルを削除/アーカイブした（必要な場合）

---

## 4. CSV方式専用チェックリスト

### 4.1 採用判断
以下の条件に1つでも当てはまる場合、CSV方式を採用:

- [ ] 収集対象が1万レース以上
- [ ] 推定所要時間が2時間以上
- [ ] 収集中も他のDB操作を実行したい
- [ ] ネットワーク障害のリスクがある（長時間実行）
- [ ] 投入前にデータ検証したい

### 4.2 収集手順
```bash
# 1. CSV収集
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
  --start YYYY-MM-DD --end YYYY-MM-DD \
  --output data/csv/YYYYMM \
  --workers 12
```
- [ ] 上記コマンドを実行した
- [ ] 完了まで待機した

### 4.3 検証手順
```bash
# 2. dry-run検証
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/YYYYMM \
  --dry-run
```
- [ ] 上記コマンドを実行した
- [ ] エラーがないことを確認した

### 4.4 投入手順
```bash
# 3. DB投入
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/YYYYMM
```
- [ ] 上記コマンドを実行した
- [ ] 完了メッセージを確認した

### 4.5 投入後検証
```sql
-- 4. データ確認
SELECT COUNT(*) FROM races WHERE race_date LIKE 'YYYY-MM%';
SELECT COUNT(*) FROM results WHERE race_id IN (
  SELECT id FROM races WHERE race_date LIKE 'YYYY-MM%'
);
```
- [ ] 上記クエリを実行した
- [ ] 件数が期待値と一致した

---

## 5. オッズ収集専用チェックリスト

### 5.1 事前確認
- [ ] 並列数を8-10に設定した
- [ ] リクエスト間隔を0.3秒以上に設定した
- [ ] ログファイルパスを指定した

### 5.2 実行コマンド
```bash
python scripts/data_collection/fetch_odds_parallel_safe.py \
  --start YYYY-MM-DD --end YYYY-MM-DD \
  --workers 10 \
  --delay 0.3
```
- [ ] 上記コマンドを実行した

### 5.3 監視項目
- [ ] 403エラーが発生していないか確認
- [ ] 自動バックアップが作成されているか確認

---

## 6. 補完作業チェックリスト

### 6.1 決まり手補完
```bash
python scripts/data_collection/補完_決まり手データ_改善版.py
```
- [ ] 実行した
- [ ] 補完件数を確認した: _______ 件

### 6.2 レース詳細補完
```bash
python scripts/data_collection/補完_レース詳細データ_改善版v4.py
```
- [ ] 実行した
- [ ] 補完件数を確認した: _______ 件

### 6.3 払戻金補完
```bash
python scripts/data_collection/補完_払戻金データ.py
```
- [ ] 実行した
- [ ] 補完件数を確認した: _______ 件

### 6.4 気象データ補完
```bash
python scripts/data_collection/fill_missing_weather_data.py
```
- [ ] 実行した
- [ ] 補完件数を確認した: _______ 件

---

## 7. 統計指標生成チェックリスト

```bash
# 年度別に実行
python scripts/data_collection/build_indicator_stats.py --year 2020
python scripts/data_collection/build_indicator_stats.py --year 2021
python scripts/data_collection/build_indicator_stats.py --year 2022
python scripts/data_collection/build_indicator_stats.py --year 2023
python scripts/data_collection/build_indicator_stats.py --year 2024
python scripts/data_collection/build_indicator_stats.py --year 2025
```

- [ ] 2020年を実行した
- [ ] 2021年を実行した
- [ ] 2022年を実行した
- [ ] 2023年を実行した
- [ ] 2024年を実行した
- [ ] 2025年を実行した

---

## 8. トラブルシューティング

### 8.1 よくある問題

| 問題 | 対処 |
|------|------|
| データ収集が遅い | `_parallel`付きスクリプトを使用 |
| 途中で止まる | CSV方式に切り替え |
| DBがロックされる | CSV方式に切り替え |
| 403エラー | ワーカー数を8以下に |

### 8.2 問題発生時の記録

発生日時: _______________
問題内容: _______________
対処内容: _______________
結果: _______________

---

## 関連ドキュメント

- [DATA_COLLECTION_OPTIMIZATION_GUIDE.md](DATA_COLLECTION_OPTIMIZATION_GUIDE.md) - 詳細ガイド
- [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md) - マスターガイド
- [CSV_DATA_COLLECTION_GUIDE.md](CSV_DATA_COLLECTION_GUIDE.md) - CSV方式詳細

---

**最終更新**: 2026-02-04
