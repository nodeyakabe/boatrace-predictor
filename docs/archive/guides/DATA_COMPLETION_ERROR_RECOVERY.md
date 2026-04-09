# データ補完エラー時のリカバリー手順書

**作成日**: 2026-01-30
**対象**: 2021年・2023年データ補完作業
**目的**: エラー発生時の迅速な対応と復旧

---

## 📋 目次

1. [エラー発生時の基本原則](#基本原則)
2. [エラー種別ごとの対応](#エラー種別ごとの対応)
3. [進捗確認方法](#進捗確認方法)
4. [完全復旧手順](#完全復旧手順)

---

## 基本原則

### ✅ 安全な設計

このデータ補完システムは以下の特性により、エラーに強い設計になっています：

1. **CSV方式**: DB負荷ゼロ、途中中断しても影響なし
2. **追記モード**: 同一コマンド再実行で続きから再開
3. **50タスクごとに自動保存**: 頻繁にCSV書き込み
4. **デフォルトでスキップ**: 既存データは上書きしない

### ⚠️ やってはいけないこと

- ❌ エラー発生後にすぐDB削除・初期化
- ❌ 複数の補完コマンドを同時実行
- ❌ `--overwrite`を安易に使用（データ上書きリスク）
- ❌ CSVファイルの手動編集

---

## エラー種別ごとの対応

### 1️⃣ ネットワークエラー

#### 症状
```
ConnectionError: Failed to connect to API
Timeout: Request timed out after 30s
```

#### 原因
- インターネット接続の一時的な不安定
- APIサーバーの一時的な過負荷
- ファイアウォール・プロキシの問題

#### 対応手順

**Step 1: 接続確認**
```bash
# インターネット接続を確認
ping 8.8.8.8

# 公式サイトへのアクセス確認
curl -I https://www.boatrace.jp/
```

**Step 2: 待機**
- 1-2分待ってから再実行
- スクリプト内に自動リトライ機能あり（3回まで）

**Step 3: 再実行**
```bash
# 同一コマンドを再実行すれば続きから再開
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 1
```

**効果**: CSVは50タスクごとに保存されているため、最大でも50レース分の再取得のみ

---

### 2️⃣ PCスリープ・再起動

#### 症状
- スクリプト実行中にPCがスリープ
- 停電・強制シャットダウン
- スクリプトのプロセスが終了

#### 対応手順

**Step 1: PC再起動後、作業ディレクトリに移動**
```bash
cd c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032
```

**Step 2: 進捗確認**
```bash
# CSVファイルの存在確認
dir data\csv\補完\2021\01

# 収集済みレース数確認（Pythonで）
python -c "import pandas as pd; df = pd.read_csv('data/csv/補完/2021/01/results.csv'); print(f'{len(df)}件収集済み')"
```

**Step 3: 同一コマンドで再実行**
```bash
# 続きから自動的に再開される
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 1
```

**効果**: 既存のCSVに追記されるため、重複なく続行

---

### 3️⃣ DB投入エラー

#### 症状（CSV→DB投入時）
```
FOREIGN KEY constraint failed
UNIQUE constraint failed: trifecta_odds.race_id, trifecta_odds.combination
```

#### 原因
- racesテーブルに該当race_idが存在しない（外部キー制約）
- 既に同じデータが存在する（UNIQUE制約）

#### 対応手順

**Step 1: dry-runで原因特定**
```bash
# 投入せずに検証のみ実行
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 1 --dry-run
```

**Step 2: エラー内容の確認**

**外部キー制約違反の場合**:
```bash
# racesテーブルに該当レースが存在するか確認
python -c "
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM races WHERE id = ?', (191367,))
print(f'races: {c.fetchone()[0]}件')
conn.close()
"
```

→ 0件の場合: そのrace_idのデータは投入不可（スキップ）

**UNIQUE制約違反の場合**:
```bash
# 既にデータが存在するか確認
python -c "
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM trifecta_odds WHERE race_id = ?', (191367,))
print(f'{c.fetchone()[0]}件存在')
conn.close()
"
```

→ デフォルトでスキップ、上書きする場合のみ `--overwrite` を使用

**Step 3: 問題のあるレースをスキップして投入**
```bash
# 通常はエラーが出てもスクリプトがスキップして続行
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 1
```

---

### 4️⃣ ディスク容量不足

#### 症状
```
OSError: [Errno 28] No space left on device
```

#### 原因
- CSV保存時にディスク容量不足

#### 対応手順

**Step 1: 容量確認**
```bash
# 空き容量確認
dir c:\

# 必要容量見積もり
# 1ヶ月分のCSV: 約100-150MB
# 2年分（24ヶ月）: 約2-3GB
```

**Step 2: 空き容量確保**

**オプションA: 不要ファイル削除**
```bash
# 一時ファイル削除
del /s /q %TEMP%\*
```

**オプションB: 月別投入後にCSV削除**
```bash
# 1ヶ月分のCSVをDBに投入
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 1

# 投入完了後、CSVを削除して容量確保
rmdir /s /q data\csv\補完\2021\01
```

**Step 3: 再実行**
```bash
# 次の月から続行
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 2
```

---

### 5️⃣ API制限エラー

#### 症状
```
HTTP 429: Too Many Requests
HTTP 503: Service Unavailable
```

#### 原因
- 短時間に大量リクエスト
- APIサーバーの負荷制限

#### 対応手順

**Step 1: 待機**
- 10-15分待機してから再実行

**Step 2: 並列数を減らして再実行**
```bash
# デフォルト12ワーカー → 8ワーカーに削減
python scripts/data_collection/補完_2021_2023_欠損データ.py \
    --year 2021 --month 1 --workers 8
```

**Step 3: それでもエラーが続く場合**
```bash
# さらに並列数を減らす（6ワーカー）
python scripts/data_collection/補完_2021_2023_欠損データ.py \
    --year 2021 --month 1 --workers 6
```

---

### 6️⃣ スクリプトの異常終了

#### 症状
- スクリプトが予期せず終了
- エラーメッセージなし

#### 対応手順

**Step 1: ログ確認**
```bash
# 標準出力・標準エラーを確認（実行時にリダイレクトしている場合）
type補完_2021_log.txt
```

**Step 2: Pythonエラーの確認**
```bash
# スクリプトを再実行してエラーメッセージを確認
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 1
```

**Step 3: 環境の確認**
```bash
# Pythonバージョン確認
python --version

# 必要なライブラリが揃っているか確認
python -c "import pandas, requests, sqlite3; print('OK')"
```

---

## 進捗確認方法

### 方法1: CSV収集の進捗確認

```bash
# CSVファイルの存在確認
dir data\csv\補完\2021\

# 各ファイルの行数確認（レース数）
python -c "
import os
import pandas as pd

year = 2021
for month in range(1, 13):
    csv_path = f'data/csv/補完/{year}/{month:02d}/results.csv'
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        print(f'{year}年{month:02d}月: {len(df)}件')
    else:
        print(f'{year}年{month:02d}月: 未収集')
"
```

### 方法2: DB投入状況の確認

```bash
# check_2021_2023_data.pyで確認
python scripts/analysis/check_2021_2023_data.py
```

### 方法3: 月別の詳細確認

```bash
# 特定月の整合性チェック
python scripts/maintenance/check_data_integrity.py --year 2021 --month-num 1
```

---

## 完全復旧手順

### ケース1: CSV収集中にエラー → 同一月を再実行

```bash
# 例: 2021年3月の収集中にエラー
# → 同一コマンドで再実行すれば続きから再開
python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --month 3
```

### ケース2: DB投入中にエラー → dry-runで確認後に再投入

```bash
# Step 1: dry-runで問題確認
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 3 --dry-run

# Step 2: 問題なければ本投入
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --month 3
```

### ケース3: DBが壊れた → バックアップから復旧

```bash
# Step 1: 現在のDBをバックアップ（念のため）
copy data\boatrace.db backups\boatrace_broken_%date:~0,4%%date:~5,2%%date:~8,2%.db

# Step 2: バックアップから復旧
copy backups\pre_data_completion_20260130\boatrace.db data\boatrace.db

# Step 3: CSV再投入（全月）
python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months
```

---

## チェックリスト：エラー発生時

- [ ] エラーメッセージを確認・記録
- [ ] エラー種別を特定（ネットワーク/PC/DB/ディスク/API/スクリプト）
- [ ] 本ドキュメントの該当セクションを参照
- [ ] 進捗確認（CSVファイル、DBデータ）
- [ ] 対応手順を実施
- [ ] 再実行後、正常に動作することを確認

---

## 緊急連絡先・参考資料

**関連ドキュメント**:
- [2021年・2023年データ補完ガイド](2021_2023_DATA_RECOVERY_GUIDE.md)
- [データ補完前の追加準備事項](../DATA_COMPLETION_PREPARATION_CHECKLIST.md)
- [データ収集マスターガイド](DATA_COLLECTION_MASTER.md)

**スクリプト**:
- CSV収集: `scripts/data_collection/補完_2021_2023_欠損データ.py`
- DB投入: `scripts/maintenance/投入_2021_2023_補完データ.py`
- 進捗確認: `scripts/analysis/check_2021_2023_data.py`

---

**作成日**: 2026-01-30
**作成者**: Claude Sonnet 4.5
**最終更新**: 2026-01-30
