# 潮位データ 本番DBインポート手順

## 概要

このSQLファイルには、以下のデータが含まれています：

- 2015-2021年: PyTides推定値
- 2022-2025年: RDMDB実測値

---

## インポート前の準備

### 1. バックアップ作成

```bash
# 本番DBのバックアップを作成
sqlite3 本番DB.db ".backup 本番DB_backup_$(date +%Y%m%d_%H%M%S).db"
```

### 2. テーブル確認

```bash
sqlite3 本番DB.db "SELECT COUNT(*) FROM race_tide_data"
```

---

## インポート方法

### 方法1: SQLファイルを直接適用（推奨）

```bash
sqlite3 本番DB.db < race_tide_data_20251110_155257.sql
```

### 方法2: SQLiteコマンドラインから適用

```bash
sqlite3 本番DB.db
sqlite> .read race_tide_data_20251110_155257.sql
sqlite> .exit
```

### 方法3: Pythonスクリプトから適用

```python
import sqlite3

conn = sqlite3.connect('本番DB.db')
with open('race_tide_data_20251110_155257.sql', 'r', encoding='utf-8') as f:
    sql = f.read()
    conn.executescript(sql)
conn.close()
print('インポート完了')
```

---

## インポート後の確認

### 1. レコード数確認

```sql
SELECT COUNT(*) FROM race_tide_data;
```

### 2. データソース別確認

```sql
SELECT 
    data_source,
    COUNT(*) as count
FROM race_tide_data
GROUP BY data_source
ORDER BY count DESC;
```

### 3. 期間別カバー率確認

```sql
SELECT 
    CASE 
        WHEN r.race_date < '2022-11-01' THEN '2015-2021'
        ELSE '2022-2025'
    END as period,
    COUNT(*) as total_races,
    SUM(CASE WHEN rtd.race_id IS NOT NULL THEN 1 ELSE 0 END) as with_tide
FROM races r
LEFT JOIN race_tide_data rtd ON r.id = rtd.race_id
WHERE r.venue_code IN ('15', '16', '17', '18', '20', '22', '24')
GROUP BY period;
```

---

## トラブルシューティング

### エラー: table race_tide_data has no column named ...

→ 本番DBのrace_tide_dataテーブル構造を確認してください

```sql
PRAGMA table_info(race_tide_data);
```

### エラー: UNIQUE constraint failed

→ INSERT OR REPLACE を使用しているため、通常は発生しません

### インポートが遅い

→ プラグマ設定でパフォーマンス改善

```sql
PRAGMA synchronous = OFF;
PRAGMA journal_mode = MEMORY;
-- SQLファイルを読み込み
PRAGMA synchronous = FULL;
PRAGMA journal_mode = DELETE;
```

---

## 注意事項

1. **必ずバックアップを取得してから実行してください**
2. INSERT OR REPLACE形式なので、既存データは上書きされます
3. インポート時間の目安: 約1-5分（レコード数による）
4. ディスク容量に余裕があることを確認してください

