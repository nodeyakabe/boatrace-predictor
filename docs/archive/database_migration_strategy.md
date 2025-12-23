# データベースマイグレーション戦略

## 現在の状況

- データは公式サイトからスクレイピングで取得
- 取得時にデータベーススキーマを自動生成（`src/database/schema.py`）
- race_details, results, entries などのテーブル構造は固定
- 決まり手（kimarite）は results テーブルに保存済み

## 問題点

UI機能追加時に「race_detailsにkimariteカラムがあると思って実装したがなかった」というケースが発生。スクレイピング元のデータ構造とアプリケーション要件の間にギャップがある。

## 推奨アプローチ

### 1. **ビューベースのアプローチ（推奨）**

スクレイピングで取得したテーブルは変更せず、アプリケーション層でSQLビューを作成。

**メリット:**
- 元データは変更しない（再スクレイピングしても安全）
- UI側の要件に合わせた「仮想テーブル」を作成できる
- マイグレーションが不要

**実装例:**
```sql
-- race_details_extended ビューを作成
CREATE VIEW IF NOT EXISTS race_details_extended AS
SELECT
    rd.*,
    res.rank,
    res.kimarite,
    res.trifecta_odds
FROM race_details rd
LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number;
```

**使い方:**
- UI側では `race_details_extended` ビューを使用
- 元の race_details テーブルはスクレイピングが更新
- ビューは起動時に自動作成

### 2. **マイグレーションスクリプト方式**

バージョン管理されたマイグレーションスクリプトで段階的にスキーマを変更。

**ディレクトリ構造:**
```
migrations/
  001_initial_schema.sql
  002_add_derived_columns.sql
  003_create_analysis_views.sql
  schema_version.txt
```

**実装:**
```python
# src/database/migrator.py
class DatabaseMigrator:
    def __init__(self, db_path):
        self.db_path = db_path

    def get_current_version(self):
        # schema_version テーブルから現在のバージョンを取得
        pass

    def apply_migrations(self):
        # 未適用のマイグレーションを順次実行
        pass
```

**メリット:**
- バージョン管理が明確
- ロールバックが可能
- チーム開発で共有しやすい

**デメリット:**
- 管理コストが高い
- スクレイピングでデータ再取得時に注意が必要

### 3. **派生テーブル方式**

元データとは別に、分析用の派生テーブルを作成。

**実装例:**
```python
# src/database/derived_tables.py
def create_analysis_tables(conn):
    """分析用の派生テーブルを作成"""

    # race_analysis テーブル（race + race_details + results を結合した分析用）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS race_analysis AS
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            rd.pit_number,
            rd.actual_course,
            rd.st_time,
            res.rank,
            res.kimarite
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    """)
```

**メリット:**
- 元データと分離されているため安全
- パフォーマンスが良い（事前結合済み）

**デメリット:**
- データの二重管理
- 同期処理が必要

## 今回のケースへの適用

### 現状の問題
- `race_details` に `kimarite` があると想定してコードを書いたが、実際は `results` テーブルにあった
- 複数箇所で `rd.kimarite` を参照するコードがあった

### 解決策（実施済み）
- SQL クエリを修正して `results` テーブルから取得するように変更
- `JOIN` を使って必要なデータを組み合わせる

### 今後の推奨対応

**オプション A: ビューを作成（最も簡単）**

```python
# src/database/views.py
def create_application_views(db_path):
    """アプリケーション用のビューを作成"""
    conn = sqlite3.connect(db_path)

    # レース詳細拡張ビュー
    conn.execute("""
        CREATE VIEW IF NOT EXISTS race_details_extended AS
        SELECT
            rd.id,
            rd.race_id,
            rd.pit_number,
            rd.exhibition_time,
            rd.tilt_angle,
            rd.actual_course,
            rd.st_time,
            res.rank,
            res.kimarite,
            res.trifecta_odds
        FROM race_details rd
        LEFT JOIN results res
            ON rd.race_id = res.race_id
            AND rd.pit_number = res.pit_number
    """)

    # 選手成績サマリービュー
    conn.execute("""
        CREATE VIEW IF NOT EXISTS racer_performance_summary AS
        SELECT
            e.racer_number,
            e.racer_name,
            COUNT(DISTINCT r.id) as total_races,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN res.rank <= '2' THEN 1 ELSE 0 END) as top2,
            SUM(CASE WHEN res.rank <= '3' THEN 1 ELSE 0 END) as top3
        FROM entries e
        JOIN races r ON e.race_id = r.id
        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
        GROUP BY e.racer_number, e.racer_name
    """)

    conn.commit()
    conn.close()
```

**使い方:**
```python
# ui/app.py の起動時
from src.database.views import create_application_views
create_application_views(DATABASE_PATH)
```

**メリット:**
- 既存コードへの影響が最小
- 元データは変更しない
- スクレイピングと独立

## 結論

**推奨アプローチ: ビューベース + 起動時自動作成**

1. `src/database/views.py` を作成
2. アプリケーション起動時にビューを自動作成
3. UI層ではビューを使用
4. スクレイピング層は元テーブルを更新

このアプローチなら：
- マイグレーション不要
- データの整合性が保たれる
- 再スクレイピングしても問題ない
- UI機能追加が簡単

## 実装タスク

1. [ ] `src/database/views.py` を作成
2. [ ] 起動時にビュー作成を実行するフックを追加
3. [ ] 既存のSQLクエリをビュー使用に移行（オプション）
4. [ ] ドキュメント更新
