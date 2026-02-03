# CSV経由データ収集ガイド

## 概要

長時間のデータ収集作業中にDBをロックせず、他の作業と並行して進められるCSV経由の収集方法を提供します。

### 従来の問題点

- データ収集に4-8日かかる
- その間DBがロック状態になり、他の更新作業ができない
- 途中で失敗した場合のリカバリが難しい

### 新しい方法の利点

✅ **DB負荷なし**: 収集中はCSVに保存するだけ
✅ **並行作業可能**: データ収集中も他のDB操作ができる
✅ **段階的保存**: 50タスクごとにCSV保存（途中で止まってもデータが残る）
✅ **リカバリが容易**: CSVファイルとして保存されるため、失敗時の再実行が簡単
✅ **一括投入が高速**: 数百万レコードを数分で投入可能

### 🆕 改善点（2026-01-14）

**問題**: 以前は全データ取得完了後に一括保存していたため、途中で止まると何も残らなかった

**解決**:
- **50タスクごとに自動保存**（約2-4レース分）
- ネットワークエラーや強制終了で止まっても、既に保存済みのデータは残る
- メモリ使用量も削減（大量データでも安定動作）

---

## 使用方法

### ステップ1: データ収集（CSV出力）

```bash
# 特定期間のデータをCSVに保存
python scripts/data_collection/fetch_to_csv_parallel.py \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --output data/csv/2020 \
  --workers 12
```

**パラメータ:**
- `--start`: 開始日（YYYY-MM-DD形式）
- `--end`: 終了日（YYYY-MM-DD形式）
- `--output`: CSV出力先ディレクトリ
- `--workers`: 並列スレッド数（デフォルト: 12）

**出力ファイル:**
```
data/csv/2020/
├── races.csv           # レース基本情報
├── entries.csv         # 出走表
├── race_conditions.csv # レース条件（天候等）
├── race_details.csv    # 展示情報
├── results.csv         # レース結果
└── payouts.csv         # 払戻金
```

### ステップ2: DB投入（検証モード）

**まず検証を実行:**

```bash
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020 \
  --dry-run
```

**確認内容:**
- CSVファイルの読み込み
- データ形式の検証
- 外部キー制約の整合性チェック
- 既存データとの重複チェック

### ステップ3: DB投入（本番）

検証が成功したら、実際に投入:

```bash
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020
```

**オプション:**
- `--overwrite`: 既存データを上書き（デフォルトはスキップ）
- `--db`: DBファイルパス（デフォルト: `data/boatrace.db`）

---

## 不整合防止の仕組み

### 1. レースIDの自動解決

CSVには `race_id` を含めず、`venue_code + race_date + race_number` の組み合わせで識別:

```python
# 既存レースIDを検索
existing_id = get_race_id(venue_code, race_date, race_number)

if existing_id:
    # 既存レースの場合、そのIDを使用
    race_id = existing_id
else:
    # 新規レースの場合、新しいIDを採番
    race_id = insert_new_race(...)
```

### 2. 外部キー制約の検証

投入前に外部キー制約を検証:

```sql
-- 外部キー違反チェック
PRAGMA foreign_key_check;

-- 孤立データチェック（entries）
SELECT COUNT(*) FROM entries e
LEFT JOIN races r ON e.race_id = r.id
WHERE r.id IS NULL;
```

### 3. トランザクション管理

全データを1つのトランザクションで処理:

```
BEGIN TRANSACTION
  ↓
races投入
  ↓
entries投入
  ↓
...他のテーブル
  ↓
整合性検証
  ↓
COMMIT (成功) / ROLLBACK (失敗)
```

---

## 実行例

### 例1: 2020年1月分を収集

```bash
# 1. CSV収集（約1-2時間）
python scripts/data_collection/fetch_to_csv_parallel.py \
  --start 2020-01-01 \
  --end 2020-01-31 \
  --output data/csv/2020_01

# 2. 検証
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020_01 \
  --dry-run

# 3. DB投入（数分）
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020_01
```

### 例2: バックグラウンド実行

```bash
# Git Bashで実行
nohup python scripts/data_collection/fetch_to_csv_parallel.py \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --output data/csv/2020 \
  > logs/csv_fetch_2020.log 2>&1 &

# 進捗確認
tail -f logs/csv_fetch_2020.log
```

### 例3: 既存データの上書き

```bash
# 同じ期間のデータを再取得して上書き
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020_01 \
  --overwrite
```

---

## トラブルシューティング

### Q1: 「race_id が見つかりません」エラー

**原因**: CSVファイルが部分的（racesデータが欠けている）

**対処**:
1. `races.csv` が存在するか確認
2. 該当の `venue_code + race_date + race_number` がracesに含まれているか確認

### Q2: 外部キー制約違反

**原因**: データ投入順序の問題

**対処**:
- スクリプトは自動的に親テーブル（races）→子テーブル（entries等）の順で投入します
- それでもエラーが出る場合は、CSVファイルの整合性を確認

### Q3: 重複データ

**原因**: 同じデータを複数回投入した

**対処**:
- デフォルトでは既存データをスキップ
- 上書きしたい場合は `--overwrite` オプションを使用

### Q4: CSV保存時にディレクトリが作成されない

**原因**: 親ディレクトリが存在しない

**対処**:
```bash
mkdir -p data/csv/2020
```

---

## パフォーマンス

### 収集速度（目安）

| 期間 | レース数 | 所要時間（12並列） |
|------|---------|------------------|
| 1日 | 約100-150 | 5-10分 |
| 1ヶ月 | 約3,000-4,000 | 2-3時間 |
| 1年 | 約40,000-50,000 | 30-40時間 |

### DB投入速度（目安）

| データ量 | 所要時間 |
|---------|---------|
| 1ヶ月（3-4千レース） | 1-2分 |
| 1年（4-5万レース） | 5-10分 |
| 6年（20-30万レース） | 30-60分 |

---

## 推奨ワークフロー

### 大量データ収集（2020-2025年全期間）の場合

**月単位で分割して実行:**

```bash
# 2020年1月
python scripts/data_collection/fetch_to_csv_parallel.py \
  --start 2020-01-01 --end 2020-01-31 \
  --output data/csv/2020_01

# 2020年2月
python scripts/data_collection/fetch_to_csv_parallel.py \
  --start 2020-02-01 --end 2020-02-29 \
  --output data/csv/2020_02

# ... 以下同様

# 各月のCSVをDB投入
python scripts/maintenance/bulk_insert_from_csv.py --input data/csv/2020_01
python scripts/maintenance/bulk_insert_from_csv.py --input data/csv/2020_02
# ...
```

**メリット:**
- 失敗時のリトライが容易
- ディスク容量を節約（投入後にCSV削除可能）
- 進捗管理がしやすい

---

## 注意事項

### ⚠️ ディスク容量

CSVファイルのサイズ目安:
- 1ヶ月分: 約50-100MB
- 1年分: 約600MB-1.2GB

十分な空き容量を確保してください。

### ⚠️ データ整合性

- 必ず `--dry-run` で検証してから本番投入
- 投入後は必ずデータ件数を確認:

```sql
SELECT COUNT(*) FROM races WHERE race_date LIKE '2020-01%';
SELECT COUNT(*) FROM entries WHERE race_id IN (SELECT id FROM races WHERE race_date LIKE '2020-01%');
```

### ⚠️ 既存データの扱い

- デフォルトでは既存データをスキップ
- 同じ期間を再度投入しても重複しない
- 上書きしたい場合は明示的に `--overwrite` を指定

---

## 成功事例

### 事例1: wave_height補完プロジェクト（2026-01-29）

**背景**:
- wave_heightカバレッジ: 51.6%（113,757/220,413レース）
- 補完対象: 2020-2023年の4年間（約22万レース）
- 従来の直接DB投入では4-8日かかり、その間他の作業が不可能

**実施内容**:

```bash
# 年別にCSV収集（2020年の例）
python scripts/data_collection/fetch_race_conditions_to_csv.py \
  --start 2020-01-01 --end 2020-12-31 \
  --output data/csv/race_conditions/2020 \
  --workers 12

# 検証モードで確認
python scripts/maintenance/import_race_conditions_from_csv.py \
  --input data/csv/race_conditions/2020 \
  --dry-run

# DB投入
python scripts/maintenance/import_race_conditions_from_csv.py \
  --input data/csv/race_conditions/2020
```

**結果**:
- ✅ **収集レース数**: 220,813件
- ✅ **新規投入**: 109,595件のrace_conditions
- ✅ **補完率向上**: 51.6% → **97.1%** (+45.5%)
- ✅ **所要時間**: 約71.4時間（並列12ワーカー）
- ✅ **DB負荷**: ゼロ（収集中も他の作業が可能）
- ✅ **障害耐性**: 50タスクごと自動保存で途中障害に強い

**教訓**:
1. **月単位分割が効果的**: 1年分を一度に収集せず、月単位で実行すると管理しやすい
2. **dry-runは必須**: 本番投入前の検証で問題を事前発見
3. **バッチ保存が重要**: 50タスクごとの自動保存でネットワーク障害に耐性
4. **wave_height型変換に注意**: CSVに`'1.0'`形式で保存される場合、`int(float(value))`で変換必要

**詳細レポート**: [docs/DATA_QUALITY_IMPROVEMENT_FINAL_REPORT.md](../DATA_QUALITY_IMPROVEMENT_FINAL_REPORT.md)

---

### CSV方式採用チェックリスト

以下の条件に当てはまる場合、CSV方式を採用してください：

- [ ] 収集対象が1万レース以上
- [ ] 推定所要時間が2時間以上
- [ ] 収集中も他のDB操作を実行したい
- [ ] ネットワーク障害のリスクがある（長時間実行）
- [ ] 投入前にデータ検証したい

---

### 投入前検証チェックリスト

dry-run実行時に以下を確認：

- [ ] CSVファイルのエンコーディングが正しい（UTF-8）
- [ ] 数値型カラムのフォーマットが正しい（例: wave_height=`'1.0'` → `int(float())`変換必要）
- [ ] 外部キー制約違反がない（race_idが存在する）
- [ ] 重複データの扱いが明確（skip or overwrite）
- [ ] 投入件数が予想範囲内

---

## まとめ

CSV経由のデータ収集により:

1. **DB負荷ゼロ** で長時間のデータ収集が可能
2. **他の作業と並行** してデータ収集を進められる
3. **不整合防止機能** により安全にDB投入可能
4. **高速なバルク投入** で数分で完了
5. **実績**: wave_height補完で109,595件を71.4時間で収集・投入成功

この方法を使うことで、数日かかるデータ収集作業も安心して実行できます。
