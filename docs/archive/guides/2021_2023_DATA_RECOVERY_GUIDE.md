# 2021年・2023年データ補完ガイド

## 概要

2021年・2023年のデータベース内のレースデータのうち、約83%が欠損していることが判明しました。
このガイドでは、欠損データを効率的に補完する手順を説明します。

## 現状

### 2021年
- **総レース数**: 55,728件
- **エントリー付き**: 14,546件（26.1%）
- **結果付き**: 14,441件（25.9%）
- **オッズ付き**: 9,494件（17.0%）
- **払戻付き**: 9,493件（17.0%）
- **欠損率**: 約**83%**

### 2023年
- **総レース数**: 55,980件
- **エントリー付き**: 15,192件（27.1%）
- **結果付き**: 15,054件（26.9%）
- **オッズ付き**: 9,077件（16.2%）
- **払戻付き**: 9,075件（16.2%）
- **欠損率**: 約**83%**

## 補完方針

### CSV方式を採用する理由

1. **DB負荷ゼロ**: 収集中はCSVに保存するだけで、DBをロックしない
2. **並行作業可能**: データ収集中も他のDB操作ができる
3. **障害耐性**: 50タスクごとに自動保存、途中で止まってもデータが残る
4. **リカバリが容易**: CSVファイルとして保存されるため、失敗時の再実行が簡単
5. **一括投入が高速**: 数万レコードを数分で投入可能

### 月別分割の理由

- 1年分を一度に実行すると30-40時間かかる
- 月別に分割することで、1-3時間ごとに区切れる
- 失敗時のリトライが容易
- ディスク容量を節約（投入後にCSV削除可能）

## 実行手順

### ステップ1: 欠損状況の確認

まず、どの月にどれだけ欠損があるか確認します。

```bash
# 2021年の欠損状況を確認
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021

# 2023年の欠損状況を確認
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2023
```

**出力例:**
```
=== 2021年のデータ状況確認 ===
  総レース数: 55,728
  エントリー欠損: 41,182 (73.9%)
  結果欠損: 41,287 (74.1%)
  オッズ欠損: 46,234 (83.0%)
  払戻欠損: 46,235 (83.0%)

=== 月別欠損状況 ===
 1月: 総4650レース | エントリー欠3420 | 結果欠3430 | オッズ欠3860
 2月: 総4200レース | エントリー欠3100 | 結果欠3110 | オッズ欠3480
...
```

### ステップ2: CSV収集（月別）

#### 方法1: 特定月のみ収集

```bash
# 2021年1月のデータを収集
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 1

# 2021年2月のデータを収集
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 2

# ... 以下同様
```

#### 方法2: 全月を自動収集

```bash
# 2021年全月を自動収集
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --all-months

# 2023年全月を自動収集
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2023 --all-months
```

#### 並列数の調整

```bash
# 並列数を8に設定（デフォルトは12）
python scripts/data_collection/補完_2021_2023_欠損データ.py \
  --year 2021 --month 1 --workers 8
```

**所要時間の目安:**
- 1ヶ月分: 約1-3時間（並列12ワーカー）
- 1年分: 約30-40時間（並列12ワーカー）

**出力先:**
```
data/csv/補完/2021/01/
├── races.csv           # レース基本情報
├── entries.csv         # 出走表
├── race_conditions.csv # レース条件（天候等）
├── race_details.csv    # 展示情報
├── results.csv         # レース結果
├── payouts.csv         # 払戻金
└── trifecta_odds.csv   # 3連単オッズ
```

### ステップ3: データ投入（検証モード）

**必ず検証を実行してから本番投入してください。**

```bash
# 2021年1月のCSVを検証
python scripts/maintenance/投入_2021_2023_補完データ.py \
  --year 2021 --month 1 --dry-run

# 2021年全月を検証
python scripts/maintenance/投入_2021_2023_補完データ.py \
  --year 2021 --all-months --dry-run
```

**確認項目:**
- CSVファイルの読み込み成功
- データ形式の妥当性
- 外部キー制約の整合性
- 投入件数が予想範囲内か

### ステップ4: データ投入（本番）

検証が成功したら、実際にDBに投入します。

```bash
# 2021年1月を投入
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 1

# 2021年全月を投入
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months

# 2023年全月を投入
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2023 --all-months
```

**所要時間の目安:**
- 1ヶ月分: 約1-2分
- 1年分: 約10-20分

### ステップ5: 結果確認

```python
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 2021年のデータ状況確認
cursor.execute('''
    SELECT COUNT(*) as total,
           COUNT(DISTINCT e.race_id) as with_entries,
           COUNT(DISTINCT res.race_id) as with_results,
           COUNT(DISTINCT t.race_id) as with_odds
    FROM races r
    LEFT JOIN entries e ON r.id = e.race_id
    LEFT JOIN results res ON r.id = res.race_id
    LEFT JOIN trifecta_odds t ON r.id = t.race_id
    WHERE r.race_date LIKE '2021%'
''')
result = cursor.fetchone()
print(f"総レース: {result[0]}")
print(f"エントリー付き: {result[1]} ({result[1]/result[0]*100:.1f}%)")
print(f"結果付き: {result[2]} ({result[2]/result[0]*100:.1f}%)")
print(f"オッズ付き: {result[3]} ({result[3]/result[0]*100:.1f}%)")

conn.close()
```

## 推奨ワークフロー

### パターンA: 月別に少しずつ実行

時間を分散させたい場合に推奨。

```bash
# 1. 月曜日: 2021年1-3月
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 1
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 1

python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 2
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 2

python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 3
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 3

# 2. 火曜日: 2021年4-6月
# ... 以下同様
```

### パターンB: 一気に全月実行

まとめて実行したい場合に推奨（PCを放置できる時間がある場合）。

```bash
# 2021年全月を収集（30-40時間）
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --all-months

# 検証
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months --dry-run

# 投入（10-20分）
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months

# 2023年も同様
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2023 --all-months
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2023 --all-months --dry-run
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2023 --all-months
```

### パターンC: バックグラウンド実行

```bash
# Git Bashでバックグラウンド実行
nohup python scripts/data_collection/補完_2021_2023_欠損データ.py \
  --year 2021 --all-months \
  > logs/csv_fetch_2021.log 2>&1 &

# 進捗確認
tail -f logs/csv_fetch_2021.log
```

## トラブルシューティング

### Q1: 収集が途中で止まった

**原因**: ネットワークエラー、PCスリープなど

**対処**:
- 50タスクごとに自動保存されているため、既に保存されたCSVは残っている
- 同じコマンドを再実行すれば、続きから収集できる
- CSVファイルは追記モードなので、重複の心配はない

### Q2: 「race_id が見つかりません」エラー

**原因**: racesテーブルにレース情報が存在しない

**対処**:
- 該当レースの `venue_code + race_date + race_number` を確認
- racesテーブルに該当データがあるか確認
- 存在しない場合は、races.csvから先に投入

### Q3: 外部キー制約違反

**原因**: データ投入順序の問題

**対処**:
- スクリプトは自動的に親テーブル（races）→子テーブル（entries等）の順で投入
- それでもエラーが出る場合は、CSVファイルの整合性を確認
- `--dry-run` モードで事前に検証

### Q4: 重複データ

**原因**: 同じデータを複数回投入した

**対処**:
- デフォルトでは既存データをスキップするため、重複しない
- 上書きしたい場合は `--overwrite` オプションを使用

### Q5: CSVファイルが大きすぎる

**原因**: 1年分を一度に収集した

**対処**:
- 月別に分割して収集することを推奨
- 投入後はCSVファイルを削除してディスク容量を節約可能

## ディスク容量

CSVファイルのサイズ目安:
- 1ヶ月分: 約50-100MB
- 1年分: 約600MB-1.2GB
- 2年分: 約1.2-2.4GB

十分な空き容量（3GB以上推奨）を確保してください。

## 予想所要時間

### 2021年（全月）

| フェーズ | 所要時間 |
|---------|---------|
| CSV収集 | 約30-40時間 |
| 検証 | 約5分 |
| DB投入 | 約10-20分 |
| **合計** | **約31-41時間** |

### 2023年（全月）

| フェーズ | 所要時間 |
|---------|---------|
| CSV収集 | 約30-40時間 |
| 検証 | 約5分 |
| DB投入 | 約10-20分 |
| **合計** | **約31-41時間** |

### 両年合計

- **CSV収集**: 約60-80時間（2.5-3.3日）
- **投入**: 約20-40分
- **総計**: 約61-81時間

## 補完後の期待値

### 2021年

| 項目 | 補完前 | 補完後（目標） |
|------|-------|--------------|
| エントリー | 26.1% | **95%以上** |
| 結果 | 25.9% | **95%以上** |
| オッズ | 17.0% | **90%以上** |
| 払戻 | 17.0% | **90%以上** |

### 2023年

| 項目 | 補完前 | 補完後（目標） |
|------|-------|--------------|
| エントリー | 27.1% | **95%以上** |
| 結果 | 26.9% | **95%以上** |
| オッズ | 16.2% | **90%以上** |
| 払戻 | 16.2% | **90%以上** |

**注意**:
- 公式サイトでデータが存在しないレースは補完不可
- オリジナル展示は前日分のみのため、過去分は取得不可

## 参考資料

- [CSV経由データ収集ガイド](./CSV_DATA_COLLECTION_GUIDE.md)
- [データ収集マスターガイド](./DATA_COLLECTION_MASTER.md)
- [データ収集スクリプトカタログ](./DATA_COLLECTION_SCRIPTS_CATALOG.md)

## まとめ

1. **確認**: `--year 2021` で欠損状況を把握
2. **収集**: `--all-months` で全月を自動収集（30-40時間）
3. **検証**: `--dry-run` で投入前検証（5分）
4. **投入**: 本番投入（10-20分）
5. **確認**: データベースで補完率を確認

CSV方式により、DB負荷ゼロで長時間のデータ収集が可能です。
月別分割により、失敗時のリトライも容易です。

**重要**: 必ず `--dry-run` で検証してから本番投入してください。
