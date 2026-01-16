# オリジナル展示データ収集ガイド

## 概要

Boatersサイトから各競艇場のオリジナル展示データを自動収集し、DBに保存するシステムです。

**重要**: オリジナル展示データは**前日分のみ取得可能**なため、毎日の自動収集が必須です。

## 取得データ

各艇ごとに以下のデータを取得:

- `isshu_time`: 1周タイム
- `mawariashi_time`: 回り足タイム
- `chikusen_time`: 直線タイム（畜舎タイム）

## スクリプト一覧

| スクリプト | 用途 | 使い方 |
|-----------|------|--------|
| `collect_original_tenji.py` | データ収集のみ（JSON保存） | `python scripts/data_collection/collect_original_tenji.py --date 2026-01-15` |
| `save_tenji_to_db.py` | JSONをDBに保存 | `python scripts/data_collection/save_tenji_to_db.py data/tenji/boaters/tenji_20260115.json` |
| `collect_and_save_tenji.py` | 収集とDB保存を一括実行 | `python scripts/data_collection/collect_and_save_tenji.py --date 2026-01-15` |
| `daily_tenji_collector.py` | 自動収集（前日分） | `python scripts/automation/daily_tenji_collector.py --manual` |

## 使い方

### 1. 手動収集（特定日）

```bash
# 特定日・特定場を収集してDB保存
python scripts/data_collection/collect_and_save_tenji.py --date 2026-01-15 --venue 01

# 特定日・全場を収集してDB保存
python scripts/data_collection/collect_and_save_tenji.py --date 2026-01-15

# ブラウザを表示して確認
python scripts/data_collection/collect_and_save_tenji.py --date 2026-01-15 --venue 01 --show-browser
```

### 2. 前日分の自動収集（手動実行）

```bash
# 前日の全場データを収集してDB保存
python scripts/automation/daily_tenji_collector.py --manual

# テスト実行（即座に実行）
python scripts/automation/daily_tenji_collector.py --test
```

### 3. 自動スケジュール実行（推奨）

#### Windows タスクスケジューラーで設定

```bash
# 管理者権限で実行（右クリック → 管理者として実行）
scripts\automation\setup_tenji_scheduler.bat
```

設定内容:
- **タスク名**: BoatRace_Tenji_Collector
- **実行時刻**: 毎日朝8:00
- **実行内容**: 前日のオリジナル展示データを全場から収集

#### Pythonスケジューラーで常駐実行

```bash
# スケジューラーを起動（常駐）
python scripts/automation/daily_tenji_collector.py

# 毎日朝8時に自動実行されます
# 停止: Ctrl+C
```

## データ保存先

### JSONバックアップ

```
data/tenji/boaters/tenji_YYYYMMDD.json
```

### データベース

```
data/boatrace.db
  └── exhibition_data テーブル
      ├── isshu_time (1周タイム)
      ├── mawariashi_time (回り足タイム)
      ├── chikusen_time (直線タイム)
      └── data_source (データソース: "boaters")
```

### ログファイル

```
logs/tenji_collection/tenji_collector_YYYYMM.log
```

## コマンドラインオプション

### collect_and_save_tenji.py

```bash
python scripts/data_collection/collect_and_save_tenji.py [オプション]

オプション:
  --date DATE         対象日付 (YYYY-MM-DD)
  --venue VENUE       場コード (01-24)
  --race RACE         レース番号 (1-12、単一レースのみ)
  --headless          ヘッドレスモード（デフォルト）
  --show-browser      ブラウザを表示
  --update            既存データを更新
  --db DB_PATH        DBファイルパス（デフォルト: data/boatrace.db）
```

### daily_tenji_collector.py

```bash
python scripts/automation/daily_tenji_collector.py [オプション]

オプション:
  --test              テスト実行（即座に1回実行）
  --manual            手動実行（前日分を収集）
  --show-browser      ブラウザを表示

オプションなし: スケジューラー起動（常駐、毎日朝8時実行）
```

## トラブルシューティング

### ChromeDriverエラー

```bash
pip install webdriver-manager
```

### データが取得できない

- **前日分のみ取得可能**: 当日や過去のデータは取得不可
- **開催確認**: その日にレースが開催されているか確認
- **ブラウザ表示**: `--show-browser`で実際の画面を確認

### DB保存エラー

```bash
# DBファイルの権限を確認
# exhibition_dataテーブルが存在するか確認
python -c "import sqlite3; conn = sqlite3.connect('data/boatrace.db'); cursor = conn.cursor(); print(cursor.execute('SELECT COUNT(*) FROM exhibition_data').fetchone())"
```

## データ確認

### 最新の収集データを確認

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()
rows = cursor.execute('''
    SELECT r.venue_code, r.race_date, r.race_number,
           COUNT(*) as cnt
    FROM exhibition_data e
    JOIN races r ON e.race_id = r.id
    WHERE e.data_source = 'boaters'
    GROUP BY r.venue_code, r.race_date, r.race_number
    ORDER BY r.race_date DESC, r.venue_code, r.race_number
    LIMIT 10
''').fetchall()
for r in rows:
    print(f'{r[0]:02d}場 {r[1]} {r[2]:2d}R: {r[3]}艇')
"
```

### 収集データの統計

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()
total = cursor.execute('SELECT COUNT(*) FROM exhibition_data WHERE data_source=\"boaters\"').fetchone()[0]
print(f'Boatersから収集したデータ: {total}件')
"
```

## 運用方針

### 推奨設定

1. **Windowsタスクスケジューラー**で毎日朝8時に自動実行
2. ログファイルで収集状況を定期確認
3. 週次でデータ件数を確認

### データ保持期間

- JSONバックアップ: 永久保存
- DB: 永久保存
- ログ: 月次ローテーション

## 関連ファイル

- データ収集: `scripts/data_collection/`
- 自動化: `scripts/automation/`
- スクレイパー: `src/scraper/original_tenji_browser.py`
- DB保存: `scripts/data_collection/save_tenji_to_db.py`
- ログ: `logs/tenji_collection/`

## 既存システムとの統合

既存の`exhibition_data`テーブルを拡張する形で実装しています。

### 追加カラム

- `isshu_time`: 1周タイム
- `mawariashi_time`: 回り足タイム
- `chikusen_time`: 直線タイム
- `data_source`: データソース識別（"boaters"）

### 既存データとの共存

- 既存の`exhibition_time`カラムはそのまま維持
- 新しいデータは`data_source="boaters"`で識別可能
- 既存データへの影響なし
