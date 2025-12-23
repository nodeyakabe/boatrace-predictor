# 2PC体制セットアップガイド

## 状況
- **このPC（データ収集専用）**: データ取得を継続実行
- **別PC（UI開発用）**: UI開発を進める

## このPC（データ収集専用PC）でやること

### 1. 不要なプロセスを停止

```bash
# すべてのStreamlitプロセスを停止
cmd //c "taskkill /F /IM streamlit.exe"

# Pythonプロセスは後で確認してから停止
```

### 2. データ収集プロセスの確認

現在実行中のデータ収集プロセス（9c71f0）の状態を確認：

```bash
# プロセス状態確認（Claude Codeで実行済み）
# 2025-09のデータ収集が完了しているか確認
```

### 3. 新しい期間のデータ収集を開始

```bash
# 仮想環境をアクティベート
venv\Scripts\activate

# 2025年10月のデータ収集を開始
python fetch_parallel_v4.py --start 2025-10-01 --end 2025-10-31 --workers 10

# または、より広い範囲で
python fetch_parallel_v4.py --start 2025-08-01 --end 2025-10-31 --workers 10
```

### 4. バックグラウンドで実行し続ける

PowerShellを使って、PCをスリープさせずに実行：

```powershell
# PowerShellでスリープ無効化
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 30

# データ収集を開始（ログファイルに出力）
python fetch_parallel_v4.py --start 2025-10-01 --end 2025-10-31 --workers 10 > logs/data_collection_$(Get-Date -Format "yyyyMMdd_HHmmss").log 2>&1
```

### 5. 定期的な進捗確認スクリプト

```python
# check_progress.py
import sqlite3
from datetime import datetime

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 総レース数
cursor.execute("SELECT COUNT(*) FROM races")
total_races = cursor.fetchone()[0]

# 最新のレース日付
cursor.execute("SELECT MAX(race_date) FROM races")
latest_date = cursor.fetchone()[0]

# 今日収集したレース数
today = datetime.now().strftime('%Y-%m-%d')
cursor.execute("SELECT COUNT(*) FROM races WHERE DATE(created_at) = ?", [today])
today_races = cursor.fetchone()[0]

print(f"総レース数: {total_races:,}")
print(f"最新レース日: {latest_date}")
print(f"今日収集: {today_races}件")

conn.close()
```

実行方法：
```bash
python check_progress.py
```

## 別PC（UI開発用PC）でやること

### 1. リポジトリのクローンまたはコピー

#### オプションA: Gitを使う場合（推奨）

```bash
# このPCでコミット＆プッシュ
git add .
git commit -m "Add database views and improve UI"
git push

# 別PCでクローン
git clone <your-repo-url>
cd BoatRace
```

#### オプションB: 直接コピー（Gitなしの場合）

```bash
# このPCでプロジェクトをZIP化
# エクスプローラーで BoatRace フォルダを右クリック → 送る → 圧縮フォルダー

# USBメモリやクラウド経由で別PCに転送
```

### 2. 別PCでの環境セットアップ

```bash
# Python仮想環境を作成
python -m venv venv

# 仮想環境をアクティベート（Windows）
venv\Scripts\activate

# 依存パッケージをインストール
pip install -r requirements.txt

# または、主要なパッケージを個別インストール
pip install streamlit pandas sqlite3 beautifulsoup4 requests lxml
```

### 3. データベースファイルのコピー

```bash
# このPCから data/boatrace.db を別PCの data/ フォルダにコピー
# ファイルサイズが大きい場合は、最新のバックアップを使用

# または、小規模なテスト用データベースを作成
```

### 4. UI開発モードで起動

```bash
# 仮想環境をアクティベート
venv\Scripts\activate

# Streamlit起動
streamlit run ui/app.py

# ブラウザで http://localhost:8501 を開く
```

### 5. 開発時の注意点

#### データベースの扱い
- データベースファイル（boatrace.db）は読み取り専用で使用
- 書き込みテストが必要な場合は、コピーを作成してテスト
- このPCのデータベースとは別々に管理

#### コード同期
- 開発中のコードは定期的にコミット
- このPCに戻ったときにプルして統合

```bash
# 別PCで開発後
git add .
git commit -m "Update UI features"
git push

# このPCで取り込む
git pull
```

## データベースファイルの共有方法

### オプション1: 定期的にコピー（簡単）

```bash
# このPCで定期的にデータベースをバックアップ
# backup_db.bat を作成

@echo off
set timestamp=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set timestamp=%timestamp: =0%
copy data\boatrace.db data\backups\boatrace_%timestamp%.db
echo Backup created: boatrace_%timestamp%.db
```

タスクスケジューラで1日1回実行し、別PCに手動またはクラウド経由でコピー。

### オプション2: 共有フォルダ（リアルタイム）

```bash
# このPCで data フォルダを共有
# 別PCから \\this-pc-name\BoatRace\data にアクセス

# 別PCのシンボリックリンクを作成
mklink /D "C:\dev\BoatRace\data" "\\this-pc-name\BoatRace\data"
```

注意: データベースファイルが大きくなるとネットワーク経由では遅い可能性あり。

### オプション3: クラウドストレージ（バランス型）

```bash
# このPCで定期的にOneDrive/Dropboxにバックアップ
# backup_to_cloud.bat

@echo off
copy data\boatrace.db "C:\Users\xxx\OneDrive\BoatRace\boatrace.db"
echo Synced to cloud
```

別PCではクラウドからダウンロードして使用。

## トラブルシューティング

### Q: このPCのデータ収集が止まってしまった
```bash
# プロセスを確認
tasklist | findstr python.exe

# ログファイルを確認
type logs\data_collection_*.log | more

# 再起動
python fetch_parallel_v4.py --start 2025-10-01 --end 2025-10-31 --workers 10
```

### Q: 別PCでUIが起動しない
```bash
# 依存パッケージを再インストール
pip install --upgrade streamlit pandas

# エラーログを確認
streamlit run ui/app.py --logger.level=debug

# データベースファイルのパスを確認
python -c "from config.settings import DATABASE_PATH; print(DATABASE_PATH)"
```

### Q: データベースが大きすぎて転送できない
```bash
# テスト用の小規模データベースを作成
# create_test_db.py

import sqlite3
import shutil

# 元のデータベースをコピー
shutil.copy('data/boatrace.db', 'data/boatrace_test.db')

conn = sqlite3.connect('data/boatrace_test.db')
cursor = conn.cursor()

# 最近30日分だけ残す
cursor.execute("""
    DELETE FROM races
    WHERE race_date < date('now', '-30 days')
""")

# 結果テーブルも削除
cursor.execute("""
    DELETE FROM results
    WHERE race_id NOT IN (SELECT id FROM races)
""")

# 同様に他のテーブルもクリーンアップ
conn.commit()
conn.close()

print("Test database created: boatrace_test.db")
```

## まとめ

### このPCでのチェックリスト
- [ ] Streamlitプロセスを停止
- [ ] データ収集プロセスの状況確認
- [ ] 新しい期間のデータ収集開始
- [ ] スリープ設定を無効化
- [ ] 定期的な進捗確認スクリプトを設置

### 別PCでのチェックリスト
- [ ] リポジトリをクローン/コピー
- [ ] Python仮想環境をセットアップ
- [ ] 依存パッケージをインストール
- [ ] データベースファイルをコピー
- [ ] UIを起動して動作確認
- [ ] 開発完了後にコミット＆プッシュ

### 戻ってきたときのチェックリスト
- [ ] データ収集の進捗確認
- [ ] 別PCでの変更をプル
- [ ] データベースファイルを統合（必要に応じて）
- [ ] 動作確認
