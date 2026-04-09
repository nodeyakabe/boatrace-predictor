# プロジェクト環境構築ガイド

**最終更新**: 2025-12-22
**目的**: 別PCで同じプロジェクト環境を再現するための手順書

---

## 📋 前提条件

- Python 3.10以上
- Git
- 元のPC（ソースPC）から最新のGitリポジトリをpull済み

---

## 🔍 ディレクトリ構成の理解

### Git管理対象（pushされる）

```
BoatRace/
├── README.md                 # プロジェクト概要
├── CLAUDE.md                 # AI設定
├── START_HERE.md             # 作業開始ガイド
├── requirements.txt          # 依存パッケージ
├── .gitignore                # Git除外設定
│
├── src/                      # ソースコード（Git管理）
├── config/                   # 設定ファイル（Git管理）
├── docs/                     # ドキュメント（Git管理）
├── scripts/                  # スクリプト（Git管理）
├── ui/                       # UIアプリ（Git管理）
└── tests/                    # テスト（Git管理）
```

### Git管理外（.gitignoreで除外）

```
BoatRace/
├── data/                     # データベース・データファイル（除外）
│   ├── boatrace.db           # メインDB（1.8GB）
│   ├── benchmark_results/    # ベンチマーク結果
│   ├── output/               # 出力ファイル
│   ├── rdmdb_tide_data/      # 潮位データ
│   ├── results/              # 予測結果
│   └── temp_files/           # 一時ファイル
│
├── models/                   # 学習済みモデル（除外）
│   └── stage2/               # Stage2モデル
│
├── backups/                  # バックアップ（除外）
│   ├── project_cleanup_20251222/
│   └── ...
│
├── logs/                     # ログファイル（除外）
├── venv/                     # Python仮想環境（除外）
├── .vscode/                  # VSCode設定（除外）
└── __pycache__/              # Pythonキャッシュ（除外）
```

### 整理により作成されたディレクトリ（Git管理）

```
BoatRace/
├── _archive/                 # 過去のルート.mdファイル
│   └── root_docs/
│
└── _deprecated/              # 過去のルート.pyファイル
    └── root_scripts/
```

---

## 🚀 セットアップ手順

### Step 1: Gitリポジトリのクローン

```bash
# リポジトリをクローン
git clone <リポジトリURL> BoatRace
cd BoatRace

# 最新状態を確認
git pull origin main
git status
```

### Step 2: Python仮想環境の作成

```bash
# 仮想環境作成
python -m venv venv

# 仮想環境有効化
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 依存パッケージインストール
pip install -r requirements.txt
```

### Step 3: Git管理外ディレクトリの作成

```bash
# data/ ディレクトリ構造
mkdir -p data/benchmark_results
mkdir -p data/benchmark_results/change_logs
mkdir -p data/output
mkdir -p data/rdmdb_tide_data
mkdir -p data/results
mkdir -p data/temp_files

# models/ ディレクトリ構造
mkdir -p models/stage2

# その他
mkdir -p logs
mkdir -p backups
```

**重要**: `data/boatrace.db`は別途転送が必要（1.8GB）

### Step 4: データベースの転送

#### オプションA: ファイル共有・クラウドストレージ

```bash
# 元のPC（ソースPC）で実行
# data/boatrace.db を OneDrive/Googleドライブ等にコピー

# 新しいPCで実行
# OneDrive/Googleドライブから data/boatrace.db をダウンロード
# BoatRace/data/ に配置
```

#### オプションB: 外部ストレージ（USB等）

```bash
# 元のPC（ソースPC）で実行
cp data/boatrace.db /path/to/usb/

# 新しいPCで実行
cp /path/to/usb/boatrace.db data/
```

#### オプションC: ネットワーク転送

```bash
# 元のPC（ソースPC）でサーバー起動
cd data
python -m http.server 8000

# 新しいPCで実行
curl -O http://<元のPCのIP>:8000/boatrace.db
mv boatrace.db data/
```

### Step 5: モデルファイルの転送（任意）

学習済みモデルがある場合は転送：

```bash
# 元のPC（ソースPC）
ls models/stage2/
# 例: stage2_model_20251201.pkl

# models/stage2/ 配下のファイルを新しいPCに転送
```

**注意**: モデルファイルがない場合は、後で再学習が必要

### Step 6: 環境設定ファイル（任意）

`.env`ファイルが必要な場合（API keyなど）：

```bash
# .env.example をコピー
cp .env.example .env

# .env を編集して必要な設定を追加
# API_KEY=your_api_key_here
```

---

## ✅ セットアップ検証

### 1. ディレクトリ構成確認

```bash
# Git管理ファイル
ls -la

# 必須ディレクトリ
ls -d src/ config/ docs/ scripts/ ui/ tests/ data/ models/

# data/構造
ls data/
# 期待: boatrace.db, benchmark_results/, output/, ...
```

### 2. データベース確認

```bash
# DBファイルサイズ確認（約1.8GB）
ls -lh data/boatrace.db

# DBテーブル確認
python -c "
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cur = conn.cursor()
cur.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')
tables = [row[0] for row in cur.fetchall()]
print(f'テーブル数: {len(tables)}')
print('主要テーブル:', tables[:10])
conn.close()
"
```

**期待結果**: テーブル数35、races, race_predictions, payouts等が表示される

### 3. Python環境確認

```bash
# Pythonバージョン
python --version
# 期待: Python 3.10以上

# 主要パッケージ
pip list | grep -E "pandas|numpy|scikit-learn|xgboost|streamlit"
```

### 4. スクリプト実行テスト

```bash
# 知見検索テスト
python scripts/search_knowledge.py "テスト"

# ベンチマークテスト（データベースが必要）
python scripts/benchmark_prediction_system.py --year 2025
```

---

## 📦 完全バックアップからの復元（推奨）

整理作業前の完全バックアップがある場合：

### 方法1: backups/の利用

```bash
# 元のPC（ソースPC）で実行
# backups/project_cleanup_20251222/ を確認
ls backups/project_cleanup_20251222/

# 以下をzipで圧縮
zip -r project_backup.zip \
    backups/project_cleanup_20251222/ \
    data/boatrace.db \
    models/

# 新しいPCに転送後
unzip project_backup.zip
```

### 方法2: Git + 大容量ファイル転送の組み合わせ

```bash
# 1. Gitでコード取得
git clone <リポジトリURL>

# 2. 大容量ファイルのみ別途転送
# data/boatrace.db (1.8GB)
# models/ (学習済みモデル)
# backups/ (必要に応じて)
```

---

## 🔧 トラブルシューティング

### エラー: `data/boatrace.db` が見つからない

**原因**: データベースファイルが転送されていない

**解決策**:
```bash
# ファイルの存在確認
ls -lh data/boatrace.db

# なければ元のPCから転送（Step 4参照）
```

### エラー: `ModuleNotFoundError: No module named 'xxx'`

**原因**: 依存パッケージがインストールされていない

**解決策**:
```bash
# 仮想環境が有効化されているか確認
which python
# 期待: /path/to/BoatRace/venv/bin/python

# 再インストール
pip install -r requirements.txt
```

### エラー: スクリプトが見つからない

**原因**: 整理前の古いパスで実行している

**解決策**:
```bash
# 新しいパス構造を確認
ls scripts/
ls scripts/prediction/
ls scripts/backtest/

# scripts/README.md を参照
cat scripts/README.md
```

### Git管理対象外ファイルが見つからない

**原因**: .gitignoreで除外されているため、pushされていない

**解決策**:
1. `.gitignore`を確認
2. 必要なファイルを元のPCから手動転送
3. または、必要に応じて`.gitignore`を修正してpush

---

## 📋 チェックリスト

セットアップ完了時に以下を確認：

- [ ] Gitリポジトリをクローン済み
- [ ] Python仮想環境を作成済み
- [ ] 依存パッケージをインストール済み
- [ ] `data/boatrace.db`が存在する（1.8GB程度）
- [ ] `data/`配下のディレクトリ構造が作成済み
- [ ] `models/`配下のディレクトリ構造が作成済み
- [ ] データベース接続テスト成功
- [ ] スクリプト実行テスト成功
- [ ] UIアプリ起動テスト成功（`cd ui && python -m streamlit run app.py`）

---

## 📚 参考ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [README.md](../../README.md) | プロジェクト概要 |
| [docs/PROJECT_CLEANUP_LOG_20251222.md](../PROJECT_CLEANUP_LOG_20251222.md) | 整理作業ログ |
| [scripts/README.md](../../scripts/README.md) | スクリプト索引 |
| [docs/README.md](../README.md) | ドキュメント索引 |

---

## 🆘 サポート

問題が解決しない場合：

1. `.gitignore`の内容を確認
2. `git status`で管理状態を確認
3. `docs/PROJECT_CLEANUP_LOG_20251222.md`で移動履歴を確認

---

**作成日**: 2025-12-22
**作成者**: Claude Code
