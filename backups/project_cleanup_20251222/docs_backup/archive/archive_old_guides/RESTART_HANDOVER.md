# PC再起動後の引継ぎ資料

## 現在の状況（2025-10-30）

### 問題の概要
- **V4（fetch_parallel_v4.py）がdatabase lockedエラーで全くデータを保存できない状態**
- 取得40件に対して保存0件という深刻な状況
- 原因：52個のバックグラウンドPythonプロセスが同時にDBにアクセス

### データ収集状況
- **2025-10月**: 2,987レース (96.7%完了)
- **2025-09月**: 1,504レース (50%のみ) ← **未完了・優先対応必要**
- **2025-08月**: 805レース
- **2024-10月**: 2,370レース (72.7%)

### 停止済みプロセス
- V4 (bash ID: 285122) - 手動停止済み
- V2 (PID: 13688) - auto_collect_next_monthが起動したプロセス、手動停止済み

### まだ稼働中のプロセス（再起動で全てクリーンアップされる）
52個のPythonプロセスがバックグラウンドで稼働中:
- V2関連: 複数（fetch_parallel_v2.py）
- テストスクリプト: 多数（test_*.py）
- Streamlit UI: 5インスタンス
- 分析スクリプト: 9インスタンス

---

## 再起動後の作業手順

### 1. 環境確認（最優先）

```bash
# 作業ディレクトリに移動
cd c:\Users\seizo\Desktop\BoatRace

# バックグラウンドプロセスが全てクリーンアップされたか確認
tasklist | findstr "python.exe"
# → 最小限のプロセスのみ表示されればOK

# データベースが正常か確認
venv\Scripts\python.exe -c "import sqlite3; conn = sqlite3.connect('data/boatrace.db'); print('DB OK'); conn.close()"
```

### 2. DataManagerの修正（必須）

**問題点**: `src/database/models.py` の `Database.connect()` にtimeoutパラメータがない

**修正箇所**: `src/database/models.py` の26-30行目

```python
# 修正前
def connect(self):
    """データベースに接続"""
    self.connection = sqlite3.connect(self.db_path)
    self.connection.row_factory = sqlite3.Row
    return self.connection

# 修正後
def connect(self):
    """データベースに接続"""
    self.connection = sqlite3.connect(
        self.db_path,
        timeout=30.0,  # 30秒のタイムアウトを設定
        check_same_thread=False  # マルチスレッド対応
    )
    self.connection.row_factory = sqlite3.Row
    return self.connection
```

**修正コマンド**:
```bash
# このファイルを編集してください
code src/database/models.py
# または
notepad src/database/models.py
```

### 3. 月別データ確認

```bash
# 現在のデータ収集状況を確認
venv\Scripts\python.exe check_monthly_data.py
```

### 4. V4の再起動（2025-09月データ収集）

```bash
# V4を再起動して2025-09月の残りデータを収集
venv\Scripts\python.exe fetch_parallel_v4.py --start 2025-09-01 --end 2025-09-30 --workers 10
```

**期待される動作**:
- database lockedエラーが発生しない
- 進捗が正常に表示される
- データが実際に保存される（保存数 > 0）

### 5. 監視とトラブルシューティング

**V4の状態確認**:
```bash
# 別のターミナルで実行中のプロセスを監視
tasklist | findstr "python.exe"

# データベースへの接続数を確認（WSLがあれば）
# lsof data/boatrace.db
```

**エラーが出た場合**:
1. すぐにV4を停止（Ctrl+C）
2. 競合プロセスを確認: `tasklist | findstr "python.exe"`
3. バックグラウンドプロセスがあれば停止

---

## ファイル一覧

### 重要なスクリプト
- `fetch_parallel_v4.py` - V4本体（バッチ書き込みアーキテクチャ）
- `src/database/models.py` - **修正が必要なファイル**
- `src/database/data_manager.py` - V4が使用するDB保存ロジック
- `check_monthly_data.py` - 月別データ確認スクリプト

### 設定ファイル
- `data/boatrace.db` - SQLiteデータベース本体
- `config/settings.py` - 設定ファイル

### 停止すべきスクリプト（再起動後に誤って起動しないこと）
- `auto_collect_next_month.py` - 自動でV2を起動してしまう
- `fetch_parallel_v2.py` - 古いV2（database locked頻発）
- 各種test_*.py - テストスクリプト

---

## V4の仕様

### アーキテクチャ
- **HTTPワーカー**: 10スレッド並列（データ取得のみ）
- **DBライター**: 1スレッド（Queueからデータを取り出して保存）
- **Queue**: HTTPワーカーとDBライターの間のバッファ

### 設計意図
- HTTPとDBアクセスを完全分離
- 1スレッドでDB書き込み → database locked回避
- バッチ書き込みで効率化

### 実際の問題
- DataManagerが毎回新しいDB接続を作成・破棄
- timeoutパラメータがない → 即座にエラー
- 複数プロセスが同時動作すると競合

---

## トラブルシューティング

### Q: 再起動後もdatabase lockedが出る
A:
1. 他のPythonプロセスがないか確認
2. DataManagerの修正が反映されているか確認
3. データベースファイルのロックファイル（.db-shm, .db-wal）を削除

### Q: V4の進捗が表示されない
A:
1. ネットワーク接続を確認
2. 競艇公式サイトがアクセス可能か確認
3. エラーメッセージを確認

### Q: データが保存されない（保存数=0）
A:
1. V4を即座に停止
2. DataManagerの修正を再確認
3. 手動でDBに接続して書き込みテスト

---

## 優先タスク

1. ☐ PC再起動
2. ☐ 環境確認（Pythonプロセスのクリーンアップ確認）
3. ☐ DataManager修正（timeout追加）
4. ☐ 月別データ確認
5. ☐ V4再起動（2025-09月収集）
6. ☐ 正常動作確認（database lockedが出ないこと）
7. ☐ 2025-09月データ収集完了まで監視

---

## 連絡事項

- **目標**: 2025-09月のデータを100%収集（現在50%）
- **推定時間**: V4が正常動作すれば2-3時間で完了
- **重要**: 他のバックグラウンドプロセスを起動しないこと

---

## 再起動後の最初のコマンド

```bash
cd c:\Users\seizo\Desktop\BoatRace
tasklist | findstr "python.exe"
code src/database/models.py
```

PC再起動後、この資料を参照して作業を再開してください。
