# 直前情報スクレイパー強化版 - 環境構築手順

作成日: 2025-12-02

## 概要

このドキュメントは、直前情報スクレイパーの強化版を別PCで構築する際の手順を記載しています。
GitからソースコードをPullするだけでは、データベーススキーマが古いままになるため、追加のマイグレーション作業が必要です。

## 変更内容サマリー

### 1. 新規取得データ

| データ種別 | 説明 | 格納先 |
|-----------|------|--------|
| ST（スタートタイミング） | フライング対応（負の値） | race_details.st_time |
| 展示進入コース | 展示での実際の進入コース | race_details.exhibition_course |
| 調整重量 | 体重調整用の重量（0.0〜5.0kg） | race_details.adjusted_weight |
| 前走進入コース | 前回レースでの進入コース | race_details.prev_race_course |
| 前走ST | 前回レースのスタートタイミング | race_details.prev_race_st |
| 前走着順 | 前回レースの着順 | race_details.prev_race_rank |
| 天候コード | 天候の数値コード（1=晴, 2=曇など） | weather.weather_code |
| 風向コード | 風向の数値コード | weather.wind_dir_code |

### 2. 主要な技術的変更

- **BeforeInfoScraper**: 大幅な機能拡張（8つの新規データフィールド追加）
- **データベーススキーマ**: race_detailsに5カラム、weatherに2カラム追加
- **UI統合**: BeforeInfoFetcherからBeforeInfoScraperへ置き換え
- **保存先変更**: exhibition_data/race_conditions → race_details/weather

---

## 環境構築手順

### Step 1: ソースコードの取得

```bash
cd c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032
git pull origin main
```

**確認ポイント:**
- `db_migration_add_beforeinfo_columns.py` が存在すること
- `src/scraper/beforeinfo_scraper.py` が更新されていること
- `ui/components/unified_race_list.py` が更新されていること

### Step 2: データベースマイグレーションの実行

**重要**: この手順を実行しないと、新しいデータが保存できません。

```bash
python db_migration_add_beforeinfo_columns.py
```

**期待される出力:**

```
======================================================================
DBスキーマ拡張: 直前情報の新規カラム追加
======================================================================

[1] race_detailsテーブルを拡張...
  [OK] adjusted_weight (調整重量) を追加
  [OK] exhibition_course (展示進入コース) を追加
  [OK] prev_race_course (前走進入コース) を追加
  [OK] prev_race_st (前走ST) を追加
  [OK] prev_race_rank (前走着順) を追加

[2] weatherテーブルを拡張...
  [OK] weather_code (天候コード) を追加
  [OK] wind_dir_code (風向コード) を追加

======================================================================
[SUCCESS] マイグレーション完了
======================================================================
```

**注意事項:**
- すでにカラムが存在する場合は `[SKIP]` と表示されます（エラーではありません）
- マイグレーションは冪等性があるため、複数回実行しても問題ありません

### Step 3: スキーマ確認

マイグレーションが正常に完了したか確認します。

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print('=== race_details テーブル ===')
cursor.execute('PRAGMA table_info(race_details)')
for row in cursor.fetchall():
    print(f'{row[1]} ({row[2]})')

print('\n=== weather テーブル ===')
cursor.execute('PRAGMA table_info(weather)')
for row in cursor.fetchall():
    print(f'{row[1]} ({row[2]})')

conn.close()
"
```

**確認ポイント:**
- race_details に以下のカラムが存在すること:
  - `exhibition_course (INTEGER)`
  - `prev_race_course (INTEGER)`
  - `prev_race_st (REAL)`
  - `prev_race_rank (INTEGER)`
  - `adjusted_weight (REAL)`
- weather に以下のカラムが存在すること:
  - `weather_code (INTEGER)`
  - `wind_dir_code (INTEGER)`

### Step 4: 動作確認

新しいスクレイパーが正常に動作するか確認します。

```bash
python -c "
from src.scraper.beforeinfo_scraper import BeforeInfoScraper

scraper = BeforeInfoScraper()

print('='*70)
print('BeforeInfoScraper 動作確認')
print('='*70)

# 当日の開催レースで確認（例: 芦屋）
result = scraper.get_race_beforeinfo('21', '20251202', 5)

if result:
    print(f'\nis_published: {result.get(\"is_published\")}')
    print(f'exhibition_times: {len(result.get(\"exhibition_times\", {}))}件')
    print(f'start_timings: {len(result.get(\"start_timings\", {}))}件')
    print(f'exhibition_courses: {len(result.get(\"exhibition_courses\", {}))}件')
    print(f'adjusted_weights: {len(result.get(\"adjusted_weights\", {}))}件')
    print(f'previous_race: {len(result.get(\"previous_race\", {}))}件')
    print(f'weather: {bool(result.get(\"weather\"))}')
    print('\n動作確認成功！')
else:
    print('\nエラー: データ取得に失敗しました')

scraper.close()
"
```

**期待される出力:**

```
======================================================================
BeforeInfoScraper 動作確認
======================================================================

is_published: True
exhibition_times: 6件
start_timings: 6件
exhibition_courses: 6件
adjusted_weights: 6件
previous_race: 1件
weather: True

動作確認成功！
```

### Step 5: UI確認

Streamlit UIで直前情報取得が正常に動作するか確認します。

```bash
streamlit run ui/app.py
```

1. ブラウザで http://localhost:8501 にアクセス
2. 「リアルタイム予想」タブを選択
3. 当日のレースを選択
4. 「直前情報取得」ボタンをクリック
5. データが正常に取得・保存されることを確認

---

## トラブルシューティング

### エラー: `no such column: exhibition_course`

**原因**: データベースマイグレーションが実行されていません。

**解決策**:
```bash
python db_migration_add_beforeinfo_columns.py
```

### エラー: `sqlite3.OperationalError: database is locked`

**原因**: 他のプロセスがデータベースを使用中です。

**解決策**:
1. Streamlit UIが起動している場合は停止
2. 他のPythonプロセスを終了
3. 再度マイグレーションを実行

### エラー: `ModuleNotFoundError: No module named 'src'`

**原因**: プロジェクトルートディレクトリで実行していません。

**解決策**:
```bash
cd c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032
# 上記のディレクトリから実行
```

### データが取得できない

**確認ポイント**:
1. レース時刻の40分前より前の場合、直前情報は未公開の可能性があります
2. ネットワーク接続を確認してください
3. 公式サイトが正常に動作しているか確認してください

---

## データベースバックアップ推奨

マイグレーション前に、念のためデータベースのバックアップを取得することを推奨します。

```bash
# バックアップ作成
copy data\boatrace.db data\boatrace_backup_20251202.db

# 問題が発生した場合の復元
copy data\boatrace_backup_20251202.db data\boatrace.db
```

---

## 補足情報

### マイグレーションスクリプトの内容

`db_migration_add_beforeinfo_columns.py` は以下の処理を実行します:

1. **race_detailsテーブルの拡張**
   ```sql
   ALTER TABLE race_details ADD COLUMN adjusted_weight REAL;
   ALTER TABLE race_details ADD COLUMN exhibition_course INTEGER;
   ALTER TABLE race_details ADD COLUMN prev_race_course INTEGER;
   ALTER TABLE race_details ADD COLUMN prev_race_st REAL;
   ALTER TABLE race_details ADD COLUMN prev_race_rank INTEGER;
   ```

2. **weatherテーブルの拡張**
   ```sql
   ALTER TABLE weather ADD COLUMN weather_code INTEGER;
   ALTER TABLE weather ADD COLUMN wind_dir_code INTEGER;
   ```

3. **冪等性の保証**
   - カラムが既に存在する場合は、`OperationalError: duplicate column name` をキャッチしてスキップ
   - 複数回実行しても安全

### 既存データへの影響

- **既存レコードへの影響**: なし（新規カラムはNULLで初期化されます）
- **後方互換性**: あり（既存のクエリは問題なく動作します）
- **パフォーマンス**: カラム追加のみのため、影響は最小限です

---

## 関連ドキュメント

- [残タスク一覧.md](残タスク一覧.md) - 実装済みタスクの詳細
- [improvement_tasks.md](improvement_tasks.md) - 予測精度改善タスク
- [README.md](../README.md) - プロジェクト全体の概要

---

## 変更履歴

| 日付 | 変更内容 | 担当者 |
|------|---------|--------|
| 2025-12-02 | 初版作成（直前情報スクレイパー強化版の環境構築手順） | Claude |

---

## お問い合わせ

不明点や問題が発生した場合は、プロジェクト管理者に連絡してください。
